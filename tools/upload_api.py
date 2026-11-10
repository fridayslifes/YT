#!/usr/bin/env python3
"""
tools/upload_api.py

Official YouTube Data API v3 Headless Uploader.
The low-level upload function transmits through Google's official REST API; the project-path
command first runs the master's strict reviewed release gate.
YouTube picks the feed thumbnail from the video's own frames, so no image is uploaded here.
Zero browser interaction, zero Playwright, 100% chunked resumable network reliability.

Prerequisites:
  Place your Google Cloud OAuth Client Secrets JSON file at:
  channel_assets/client_secrets.json
"""

import argparse
import fcntl
import hashlib
import json
import os
import re
import sys
import time
import tempfile
from datetime import datetime, timezone
from pathlib import Path

YT_ROOT = Path(__file__).resolve().parent.parent
# `python tools/upload_api.py --sync` puts tools/ on sys.path, not the repo root, so the deferred
# `from tools import tracker` below would fail. Bootstrap the root the way the other entrypoints do.
if str(YT_ROOT) not in sys.path:
    sys.path.insert(0, str(YT_ROOT))
CLIENT_SECRETS_LOCATIONS = [
    YT_ROOT / "channel_assets" / "client_secrets.json",
    YT_ROOT / "client_secrets.json",
    Path.home() / ".yt_client_secrets.json",
]
TOKEN_CACHE = Path.home() / ".yt_oauth_token.json"
SCOPES = [
    "https://www.googleapis.com/auth/youtube.upload",
    "https://www.googleapis.com/auth/youtube.force-ssl",
]
EXPECTED_COGNITIVE_CORE_CHANNEL_ID = "UC6hwVBnsfvfUGxfZi2sFT3A"
TITLE_HARD_LIMIT = 100
# HTTP statuses worth retrying: rate limit + transient gateway/server failures.
RETRYABLE_HTTP_STATUS = {408, 429, 500, 502, 503, 504}
MAX_UPLOAD_CHUNK_RETRIES = 4
MAX_API_CALL_RETRIES = 3


def _err(msg: str) -> None:
    """Real errors go to stderr - never swallow them."""
    print(msg, file=sys.stderr)


def _http_status(err) -> int | None:
    return getattr(getattr(err, "resp", None), "status", None)


def _is_retryable_http(err) -> bool:
    return _http_status(err) in RETRYABLE_HTTP_STATUS


def _backoff_sleep(attempt: int, cap: float = 60.0, label: str = "") -> None:
    delay = min(cap, 2.0 ** attempt)
    _err(f"  ⚠️ {label}transient failure - retry {attempt} in {delay:.0f}s")
    time.sleep(delay)


def _write_private_text(path: Path, text: str) -> None:
    """Write a secrets-bearing file with 0600 permissions (create + harden, no world-readable window)."""
    fd = os.open(str(path), os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    try:
        os.write(fd, text.encode("utf-8"))
    finally:
        os.close(fd)
    try:
        os.chmod(str(path), 0o600)
    except OSError as e:
        _err(f"  ⚠️ Could not chmod {path} to 0600: {e}")


def _protect_secrets_file(path: Path) -> None:
    """OAuth client secrets must never be world-readable."""
    try:
        os.chmod(str(path), 0o600)
    except OSError as e:
        _err(f"  ⚠️ Could not chmod {path} to 0600: {e}")


def get_client_secrets_path() -> Path | None:
    """Locate the client_secrets.json file in known paths."""
    for p in CLIENT_SECRETS_LOCATIONS:
        if p.exists():
            _protect_secrets_file(p)
            return p
    return None


def get_authenticated_service():
    """Authenticate and return the YouTube service object."""
    from google.auth.transport.requests import Request
    from google.oauth2.credentials import Credentials
    from google_auth_oauthlib.flow import InstalledAppFlow
    from googleapiclient.discovery import build
    from googleapiclient.errors import HttpError

    creds = None
    if TOKEN_CACHE.exists():
        try:
            creds = Credentials.from_authorized_user_file(str(TOKEN_CACHE), SCOPES)
        except Exception as e:
            # A corrupt/unsupported token file is recoverable, but say what it actually was.
            _err(f"  ⚠️ Could not read OAuth token cache {TOKEN_CACHE}: {type(e).__name__}: {e}")
            creds = None

    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            try:
                creds.refresh(Request())
            except HttpError as e:
                _err(f"  ⚠️ OAuth token refresh failed (HTTP {_http_status(e)}): {e}")
                creds = None
            except Exception as e:
                # Revoked / expired-grant tokens land here. Say so instead of silently
                # falling into an invisible re-auth loop.
                _err(
                    f"  ❌ OAuth token refresh failed: {type(e).__name__}: {e}\n"
                    f"     Token file: {TOKEN_CACHE}\n"
                    "     If the token was revoked, delete that file and re-authorize once."
                )
                creds = None

        if not creds:
            secrets_path = get_client_secrets_path()
            if not secrets_path:
                print("\n" + "=" * 70)
                print("❌ MISSING CLIENT SECRETS FILE (Google Cloud OAuth)")
                print("=" * 70)
                print("To use the official YouTube Data API v3, you need client_secrets.json.")
                print("Please save your OAuth 2.0 Client credentials to:")
                print(f"  👉 {YT_ROOT / 'channel_assets' / 'client_secrets.json'}\n")
                print("Quick 3-step setup in Google Cloud Console:")
                print("  1. Visit: https://console.cloud.google.com/")
                print("  2. Enable 'YouTube Data API v3' in APIs & Services -> Library")
                print("  3. Create an OAuth 2.0 Client ID (Application Type: Desktop App)")
                print("     and download the JSON file.")
                print("=" * 70 + "\n")
                sys.exit(1)

            print(f"🔑 Authorizing via {secrets_path.name}...")
            flow = InstalledAppFlow.from_client_secrets_file(str(secrets_path), SCOPES)
            creds = flow.run_local_server(port=0)

        # Save credentials for future runs (refresh tokens are secrets -> owner-only file)
        _write_private_text(TOKEN_CACHE, creds.to_json())
        print("✓ OAuth token saved to persistent cache (~/.yt_oauth_token.json, mode 0600)")

    return build("youtube", "v3", credentials=creds)


def resolve_video_target(project_dir: Path, kit_rel_path: str | None = None) -> Path | None:
    """Pick deterministically which file will be published.

    An unsorted glob over output/*.mp4 picks an arbitrary render whenever a project folder holds
    more than one (re-runs and renamed drafts leave stale ones behind), which can publish the wrong
    video. Preference order:
      1. output/<project_dir.name>.mp4  - the canonical name the pipeline builds to
      2. the file the UPLOAD_KIT names, if it exists
      3. the newest output/*.mp4 by mtime
    """
    out_dir = project_dir / "output"
    exact = out_dir / f"{project_dir.name}.mp4"
    if exact.is_file():
        return exact
    if kit_rel_path:
        kit_target = Path(kit_rel_path)
        if not kit_target.is_absolute():
            kit_target = YT_ROOT / kit_rel_path
        if kit_target.is_file() and kit_target.suffix.lower() == ".mp4":
            return kit_target.resolve()
    if out_dir.exists():
        mp4s = [p for p in out_dir.glob("*.mp4") if p.is_file()]
        if mp4s:
            return max(mp4s, key=lambda p: p.stat().st_mtime)
    return None


def parse_upload_kit(kit_path: Path) -> dict:
    """Extract metadata from UPLOAD_KIT_*.md."""
    text = kit_path.read_text(encoding="utf-8")

    video_match = (
        re.search(r"\*\*Target Video File\*\*:\s*`([^`]+)`", text)
        or re.search(r"\*\*Output Target\*\*:\s*`([^`]+)`", text)
    )
    video_rel_path = video_match.group(1).strip() if video_match else None
    if not video_rel_path or not (YT_ROOT / video_rel_path).exists():
        out_dir = kit_path.parent / "output"
        if out_dir.exists():
            mp4s = sorted(out_dir.glob("*.mp4"), key=lambda p: p.stat().st_mtime, reverse=True)
            if mp4s:
                try:
                    video_rel_path = str(mp4s[0].relative_to(YT_ROOT))
                except ValueError:
                    video_rel_path = str(mp4s[0])

    title_match = (
        re.search(r"##\s*\d*\.?\s*Title[^\n]*\n+```(?:text|markdown)?\n(.*?)\n```", text, re.DOTALL | re.IGNORECASE)
        or re.search(r"\* \*\*Primary[^\*]*\*\*:\s*[\r\n]+>\s*`?([^`\r\n]+)`?", text)
        or re.search(r"-\s*\*\*Primary[^\*]*\*\*:\s*[\r\n]+\s*`([^`\r\n]+)`", text)
        or re.search(r"###\s*Video Title\s*\n+```text\n(.*?)\n```", text, re.DOTALL)
        or re.search(r">\s*`?([^\r\n`]+#shorts)`?", text, re.IGNORECASE)
        or re.search(r"# YouTube Upload Kit — [^:]+:\s*([^\r\n]+)", text)
    )
    title = title_match.group(1).strip() if title_match else None

    desc_match = (
        re.search(r"##\s*\d*\.?\s*(?:Humanized|SEO-Optimized)?\s*Description[^\n]*\n+```(?:text|markdown)?\n(.*?)\n```", text, re.DOTALL | re.IGNORECASE)
        or re.search(r"###\s*(?:Video\s*)?Description[^\n]*\n+```(?:text|markdown)?\n(.*?)\n```", text, re.DOTALL | re.IGNORECASE)
        or re.search(r"###\s*Description[^\n]*\n(.*?)(?=\n##|\Z)", text, re.DOTALL | re.IGNORECASE)
    )
    description = desc_match.group(1).strip() if desc_match else None

    tags_match = (
        re.search(r"##\s*\d*\.?\s*(?:Defensive|Optimized|Lowercase)?\s*(?:Search\s*)?Tags[^\n]*\n+```(?:text|markdown)?\n(.*?)\n```", text, re.DOTALL | re.IGNORECASE)
        or re.search(r"###\s*(?:Search\s*)?Tags[^\n]*\n+```(?:text|markdown)?\n(.*?)\n```", text, re.DOTALL | re.IGNORECASE)
        or re.search(r"##\s*🏷️?\s*(?:Search\s*)?Tags[^\n]*\n+(.*?)(?=\n##|\Z)", text, re.DOTALL | re.IGNORECASE)
    )
    tags_raw = tags_match.group(1).strip() if tags_match else ""
    tag_list = [t.strip().lower() for t in tags_raw.replace("\n", ",").split(",") if t.strip()]

    # Extract Pinned Comment
    pin_match = (
        re.search(r"#{2,3}\s*(?:\d+\.\s*)?(?:High-Engagement )?Pinned(?: First)? Comment[^\n]*\n+```text\n(.*?)\n```", text, re.DOTALL)
        or re.search(r"#{2,3}\s*(?:\d+\.\s*)?(?:High-Engagement )?Pinned Comment[^\n]*\n+>\s*\*\*\"?(.*?)\"?\*\*", text)
        or re.search(r"Pinned Comment[^\n]*:\s*\n+```text\n(.*?)\n```", text, re.DOTALL)
    )
    pinned_comment = pin_match.group(1).strip() if pin_match else ""

    # Strict lowercase #shorts enforcement
    if title:
        title = re.sub(r"#shorts\b", "#shorts", title, flags=re.IGNORECASE)
    if description:
        description = re.sub(r"#shorts\b", "#shorts", description, flags=re.IGNORECASE)

    return {
        "video_file": video_rel_path,
        "title": title,
        "description": description,
        "tags": tag_list,
        "pinned_comment": pinned_comment,
    }


def update_content_tracker(video_id: str, youtube_url: str):
    """Update CONTENT_TRACKER.md row with the live YouTube Link & ID and status.

    Written through tools/tracker.py, which maps values by the header names of the table it is
    writing into. The previous implementation matched the pre-2026-10-31 row shape with a regex
    (``*Pending Upload*`` followed by two backticked cells and ``**Ready**``); against the current
    7-column table it never matched, so a completed upload printed "noted" and the row went on
    claiming the video was still pending.
    """
    root = YT_ROOT
    if str(root) not in sys.path:
        sys.path.insert(0, str(root))
    from tools.tracker import append_uploaded_video_record, update_tracker_row

    if not (root / "CONTENT_TRACKER.md").exists():
        return

    vid_code_match = re.search(r"(?:v=|youtu\.be/|shorts/)([a-zA-Z0-9_-]{11})", youtube_url)
    vid_code = vid_code_match.group(1) if vid_code_match else ""
    wrote = update_tracker_row(
        video_id,
        {
            "live_link": f"[Watch]({youtube_url}) (`{vid_code}`)" if vid_code else f"[Watch]({youtube_url})",
            "status": "**Uploaded**",
        },
        tracker_path=root / "CONTENT_TRACKER.md",
    )
    try:
        append_uploaded_video_record(video_id, youtube_url)
    except Exception as txt_err:
        print(f"  [WARNING] Could not append to uploaded_videos.txt: {txt_err}", file=sys.stderr)
    if wrote:
        print(f"  ✓ Updated CONTENT_TRACKER.md for {video_id} -> Live Link: {youtube_url}")
    else:
        print(
            f"  ⚠️ CONTENT_TRACKER.md row for {video_id} was NOT updated - no table with an ID column "
            f"matched it. Live link to record by hand: {youtube_url}",
            file=sys.stderr,
        )
    return wrote


def _receipt_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _normalized_sha256(value: dict) -> str:
    return hashlib.sha256(
        json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
    ).hexdigest()


def _write_receipt(path: Path, receipt: dict) -> None:
    """Flush a complete replacement before atomically exposing it to later runs."""
    receipt["updated_at"] = _receipt_now()
    with tempfile.NamedTemporaryFile(
        mode="w", encoding="utf-8", dir=path.parent, suffix=".tmp", delete=False
    ) as handle:
        json.dump(receipt, handle, indent=2, ensure_ascii=False)
        handle.write("\n")
        handle.flush()
        os.fsync(handle.fileno())
        temp = Path(handle.name)
    temp.replace(path)
    # Persist the directory entry as well as the contents across a machine crash.
    fd = os.open(path.parent, os.O_RDONLY)
    try:
        os.fsync(fd)
    finally:
        os.close(fd)


def _verify_remote(youtube, remote_id: str, *, channel_id: str, title: str, privacy: str, synthetic: bool) -> dict:
    response = (
        youtube.videos()
        .list(
            part="id,snippet,status,contentDetails,processingDetails",
            id=remote_id,
        )
        .execute()
    )
    items = response.get("items", [])
    if len(items) != 1 or items[0].get("id") != remote_id:
        raise RuntimeError(f"remote verification failed: video {remote_id} missing or mismatched")
    item = items[0]
    snippet, status = item.get("snippet", {}), item.get("status", {})
    for label, actual, expected in (
        ("channel", snippet.get("channelId"), channel_id),
        ("title", snippet.get("title"), title),
        ("privacy", status.get("privacyStatus"), privacy),
    ):
        if actual != expected:
            raise RuntimeError(
                f"remote verification failed: {label} {actual!r} != {expected!r}; reconcile before retrying"
            )
    if "containsSyntheticMedia" in status and status["containsSyntheticMedia"] != synthetic:
        raise RuntimeError("remote verification failed: synthetic media disclosure differs; reconcile before retrying")
    if status.get("selfDeclaredMadeForKids") is True:
        raise RuntimeError("remote verification failed: made-for-kids setting differs; reconcile before retrying")
    return {
        "checked_at": _receipt_now(),
        "id": remote_id,
        "channel_id": snippet.get("channelId"),
        "title": snippet.get("title"),
        "privacy": status.get("privacyStatus"),
        "containsSyntheticMedia": status.get("containsSyntheticMedia", "unknown"),
        "selfDeclaredMadeForKids": status.get("selfDeclaredMadeForKids", "unknown"),
        "status": status,
        "contentDetails": item.get("contentDetails", {}),
        "processingDetails": item.get("processingDetails", {}),
    }


def upload_via_api(
    project_dir: Path,
    public: bool = False,
    *,
    expected_channel_id: str = EXPECTED_COGNITIVE_CORE_CHANNEL_ID,
    contains_synthetic_media: bool = False,
    receipt_path: Path | None = None,
) -> str:
    """Upload once per durable operation; uncertain outcomes require reconciliation."""
    project_dir = Path(project_dir).resolve()
    kits = sorted(project_dir.glob("UPLOAD_KIT*.md"))
    if len(kits) != 1:
        raise ValueError(f"expected exactly one UPLOAD_KIT_*.md in {project_dir}")
    meta = parse_upload_kit(kits[0])
    video_path = resolve_video_target(project_dir, meta.get("video_file"))
    if video_path is None:
        raise ValueError(f"no video to publish for {project_dir.name}; render it first")
    title = (meta.get("title") or "").strip()
    if not title or len(title) > TITLE_HARD_LIMIT:
        raise ValueError(f"snippet.title requires 1-{TITLE_HARD_LIMIT} characters")
    project_json = project_dir / "project.json"
    project = json.loads(project_json.read_text(encoding="utf-8")) if project_json.exists() else {}
    video_id = project.get("id")
    if not video_id:
        match = re.search(r"SH(?:ORT)?[_-]?(\d+[A-Z]?)", project_dir.name.upper())
        video_id = f"SH-{match.group(1)}" if match else project_dir.name
    if not re.fullmatch(r"[A-Za-z0-9_-]+", str(video_id)):
        raise ValueError("internal video ID must be a safe receipt filename")
    privacy = "public" if public else "unlisted"
    body = {
        "snippet": {
            "title": title,
            "description": meta.get("description") or "",
            "tags": meta.get("tags") or [],
            "categoryId": "27",
        },
        "status": {
            "privacyStatus": privacy,
            "selfDeclaredMadeForKids": False,
            "containsSyntheticMedia": bool(contains_synthetic_media),
        },
    }
    media_hash = _sha256_file(video_path)
    metadata_hash = _normalized_sha256(body)
    operation_key = _normalized_sha256(
        {"video_id": video_id, "media_sha256": media_hash, "metadata_sha256": metadata_hash}
    )
    path = (
        Path(receipt_path)
        if receipt_path is not None
        else YT_ROOT / "channel_assets" / "upload_receipts" / f"{video_id}.json"
    )
    path = path.resolve()
    if path.is_relative_to(project_dir):
        raise ValueError("upload receipt must be outside the project directory")
    path.parent.mkdir(parents=True, exist_ok=True)
    # Serialize receipt readers and writers, including concurrent invocations of this operation.
    with path.with_suffix(path.suffix + ".lock").open("a") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        return _upload_receipted(
            project_dir=project_dir,
            video_path=video_path,
            video_id=str(video_id),
            expected_channel_id=expected_channel_id,
            body=body,
            path=path,
            operation_key=operation_key,
            media_hash=media_hash,
            metadata_hash=metadata_hash,
        )


def _upload_receipted(
    *,
    project_dir: Path,
    video_path: Path,
    video_id: str,
    expected_channel_id: str,
    body: dict,
    path: Path,
    operation_key: str,
    media_hash: str,
    metadata_hash: str,
) -> str:
    from googleapiclient.errors import HttpError
    from googleapiclient.http import MediaFileUpload

    receipt = json.loads(path.read_text(encoding="utf-8")) if path.exists() else None
    if receipt is not None:
        if receipt.get("operation_key") != operation_key or receipt.get("channel_id") != expected_channel_id:
            raise RuntimeError("receipt operation/channel differs; reconcile existing upload before any new insert")
        if receipt.get("state") in {"uploading", "ambiguous"}:
            raise RuntimeError("upload outcome requires reconciliation; no new insert is permitted")
        if receipt.get("state") not in {"prepared", "uploaded", "verified"}:
            raise RuntimeError("unknown receipt state; reconcile before any new insert")
        if receipt.get("state") == "prepared" and receipt.get("remote_id"):
            raise RuntimeError("prepared receipt contains a remote ID; reconcile before any new insert")
    youtube = get_authenticated_service()
    channels = youtube.channels().list(part="id,snippet", mine=True).execute().get("items", [])
    if len(channels) != 1 or channels[0].get("id") != expected_channel_id:
        raise RuntimeError(f"authenticated channel does not match expected channel {expected_channel_id}")
    privacy = body["status"]["privacyStatus"]
    if receipt is None:
        receipt = {
            "schema_version": 1,
            "video_id": video_id,
            "operation_key": operation_key,
            "media_sha256": media_hash,
            "metadata_sha256": metadata_hash,
            "channel_id": expected_channel_id,
            "privacy": privacy,
            "contains_synthetic_media": body["status"]["containsSyntheticMedia"],
            "self_declared_made_for_kids": False,
            "state": "prepared",
            "created_at": _receipt_now(),
            "remote_verification": {},
            "notes": [],
        }
        _write_receipt(path, receipt)
    if receipt["state"] == "prepared":
        # All local preparation happens before the durable transition marking insert as begun.
        media = MediaFileUpload(str(video_path), chunksize=4 * 1024 * 1024, resumable=True)
        receipt["state"] = "uploading"
        receipt["upload_started_at"] = _receipt_now()
        _write_receipt(path, receipt)
        try:
            request = youtube.videos().insert(part="snippet,status", body=body, media_body=media)
            response = None
            attempt = 0
            while response is None:
                try:
                    _, response = request.next_chunk()
                    attempt = 0
                except (HttpError, OSError) as exc:
                    if (
                        isinstance(exc, HttpError) and not _is_retryable_http(exc)
                    ) or attempt >= MAX_UPLOAD_CHUNK_RETRIES:
                        raise
                    attempt += 1
                    _backoff_sleep(attempt, label="chunk upload - ")
            remote_id = response.get("id")
            if not remote_id or not re.fullmatch(r"[A-Za-z0-9_-]{11}", remote_id):
                raise RuntimeError("upload returned no valid video ID")
        except BaseException as exc:
            receipt["state"] = "ambiguous"
            receipt["notes"].append(f"Insert began but outcome is uncertain: {type(exc).__name__}: {exc}")
            _write_receipt(path, receipt)
            raise RuntimeError("Ambiguous upload outcome; reconcile with YouTube before retrying") from exc
        receipt.update(
            {
                "state": "uploaded",
                "remote_id": remote_id,
                "remote_url": f"https://youtu.be/{remote_id}",
                "uploaded_at": _receipt_now(),
            }
        )
        _write_receipt(path, receipt)
    remote_id = receipt.get("remote_id")
    if not remote_id:
        raise RuntimeError("completed receipt has no remote ID; reconcile before retrying")
    verification = _verify_remote(
        youtube,
        remote_id,
        channel_id=expected_channel_id,
        title=body["snippet"]["title"],
        privacy=privacy,
        synthetic=body["status"]["containsSyntheticMedia"],
    )
    receipt.update({"state": "verified", "remote_verification": verification, "verified_at": _receipt_now()})
    _write_receipt(path, receipt)
    try:
        if update_content_tracker(video_id, receipt["remote_url"]) is False:
            raise RuntimeError("tracker row was not updated")
    except Exception as exc:
        note = f"Tracker update failed after verified upload: {type(exc).__name__}: {exc}"
        receipt["notes"].append(note)
        try:
            _write_receipt(path, receipt)
        except OSError as note_error:
            _err(f"Could not persist tracker warning; verified receipt and remote ID are retained: {note_error}")
        _err(note)
    return remote_id


def sync_channel_stats():
    """Fetch live channel and video stats from YouTube API and update CONTENT_TRACKER.md."""
    youtube = get_authenticated_service()

    # 1. Channel stats
    ch_resp = youtube.channels().list(mine=True, part="snippet,statistics,contentDetails").execute()
    item = ch_resp["items"][0]
    sub_count = item["statistics"].get("subscriberCount", "0")
    total_views = item["statistics"].get("viewCount", "0")
    total_vids = item["statistics"].get("videoCount", "0")
    uploads_id = item["contentDetails"]["relatedPlaylists"]["uploads"]

    print("\n" + "=" * 65)
    print("📊 COGNITIVE CORE — LIVE CHANNEL ANALYTICS")
    print("=" * 65)
    print(f"Channel: {item['snippet']['title']} ({item['snippet'].get('customUrl', '@CognitiveCoreOfficial')})")
    print(f"👥 Subscribers: {sub_count}")
    print(f"👀 Total Channel Views: {int(total_views):,}")
    print(f"🎬 Total Videos: {total_vids}")
    print("=" * 65 + "\n")

    # 2. Video stats
    pl_resp = youtube.playlistItems().list(playlistId=uploads_id, part="snippet", maxResults=50).execute()
    vid_ids = [it["snippet"]["resourceId"]["videoId"] for it in pl_resp["items"]]

    v_resp = youtube.videos().list(id=",".join(vid_ids), part="snippet,statistics").execute()
    vid_stats = {}
    print("Live Video Performance:")
    for v in v_resp["items"]:
        v_id = v["id"]
        v_views = v["statistics"].get("viewCount", "0")
        v_likes = v["statistics"].get("likeCount", "0")
        v_title = v["snippet"]["title"]
        vid_stats[v_id] = int(v_views)
        print(f"  • [{v_views.rjust(4)} views | {v_likes.rjust(2)} likes] {v_title[:55]} (https://youtu.be/{v_id})")

    # 3. Update CONTENT_TRACKER.md
    tracker_path = YT_ROOT / "CONTENT_TRACKER.md"
    if tracker_path.exists():
        from tools import tracker

        def update_overview(content):
            updated = re.sub(r"\|\s*\*\*Current Subscribers\*\*\s*\|\s*\*\*\d+\*\*", f"| **Current Subscribers** | **{sub_count}**", content)
            return re.sub(r"\|\s*\*\*Total Channel Views\*\*\s*\|\s*\*\*[\d\+,]+\*\*", f"| **Total Channel Views** | **{int(total_views):,}+**", updated)

        tracker.update_tracker_text(update_overview, tracker_path=tracker_path)

        # Update individual video rows through the schema-aware writer: tracker rows are keyed by
        # channel ID (SH-16), so each video id has to be resolved to its row first.
        written, unmatched = 0, []
        for v_id, count in vid_stats.items():
            row_id = tracker.row_for_live_id(v_id, tracker_path=tracker_path)
            if not row_id:
                unmatched.append(v_id)
                continue
            if tracker.update_tracker_row(row_id, {"views": f"{count:,}"}, tracker_path=tracker_path):
                written += 1
        print(f"\n✓ Synchronized CONTENT_TRACKER.md: {written}/{len(vid_stats)} video rows updated.")
        if unmatched:
            print(f"  ⚠️ Not in the tracker (row not written): {', '.join(unmatched)}")


def main() -> int:
    parser = argparse.ArgumentParser(description="Official YouTube Data API v3 Uploader")
    parser.add_argument("project_path", nargs="?", help="Path to project directory (e.g. shorts/short_17_topic)")
    parser.add_argument("--auth-only", action="store_true", help="Run 1-time OAuth authentication and save token cache")
    parser.add_argument("--sync", action="store_true", help="Fetch live channel stats and sync with CONTENT_TRACKER.md")
    parser.add_argument("--public", action="store_true", help="Publish as Public after strict release (default: Unlisted)")
    parser.add_argument("--evidence", type=Path, help="Reviewed evidence JSON required for upload")
    parser.add_argument("--yes", action="store_true", help="Approve irreversible upload after strict release checks")

    args = parser.parse_args()
    if args.sync:
        sync_channel_stats()
        return 0

    if args.auth_only or not args.project_path:
        get_authenticated_service()
        print("✓ Authentication successful! Token cached permanently.")
        return 0

    pdir = Path(args.project_path)
    if not pdir.is_absolute():
        pdir = YT_ROOT / pdir

    if not pdir.exists():
        print(f"❌ Error: Directory not found: {pdir}")
        return 1

    if str(YT_ROOT) not in sys.path:
        sys.path.insert(0, str(YT_ROOT))
    from tools.orchestrator.cli import legacy_upload_command

    return legacy_upload_command(pdir, args.evidence, public=args.public, approve=args.yes)


if __name__ == "__main__":
    raise SystemExit(main())
