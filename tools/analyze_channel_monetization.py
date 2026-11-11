#!/usr/bin/env python3
"""tools/analyze_channel_monetization.py

Channel & video analytics report for the configured FrameForge YouTube channel:
- Queries YouTube Data API v3 for public video inventory and view/like/comment counts.
- Queries YouTube Analytics API v2 (`yt-analytics.readonly` scope) when an authorized
  analytics token is available and the API is enabled on the Google Cloud project.
- Never invents or estimates watch hours from hardcoded completion percentages (e.g. 75% or 42%).
  When YouTube Analytics API metrics are unavailable, analytics fields remain `None` (`null`),
  not `0`, and ordinary watch time is never labeled YPP-qualified.
"""

from __future__ import annotations

import json
import os
import re
import sys
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from tools.upload_api import get_authenticated_service, resolve_expected_channel_id  # noqa: E402

ANALYTICS_TOKEN_CANDIDATES = (
    Path(os.environ.get("YT_ANALYTICS_TOKEN_PATH", "")) if os.environ.get("YT_ANALYTICS_TOKEN_PATH") else None,
    Path.home() / ".frameforge_analytics_token.json",
    REPO_ROOT / "channel_assets" / "youtube_analytics_token.json",
)
ANALYTICS_SCOPES = ["https://www.googleapis.com/auth/yt-analytics.readonly"]


def parse_iso8601_duration(dur: str) -> float:
    match = re.match(r"PT(?:(\d+)H)?(?:(\d+)M)?(?:(\d+)S)?", dur or "")
    if not match:
        return 0.0
    h = int(match.group(1) or 0)
    m = int(match.group(2) or 0)
    s = int(match.group(3) or 0)
    return float(h * 3600 + m * 60 + s)


def fetch_real_analytics_by_video(
    channel_id: str | None = None,
    start_date: str = "2026-10-01",
    end_date: str = "2026-11-10",
) -> tuple[dict[str, dict[str, Any]], str | None]:
    """Query YouTube Analytics API v2 for real per-video metrics, or return ({}, blocker_reason)."""
    token_path = next((p for p in ANALYTICS_TOKEN_CANDIDATES if p is not None and p.is_file()), None)
    if token_path is None:
        return {}, "No yt-analytics.readonly token file found; Analytics metrics kept NULL."

    try:
        from google.auth.transport.requests import Request
        from google.oauth2.credentials import Credentials
        from googleapiclient.discovery import build

        creds = Credentials.from_authorized_user_file(str(token_path), ANALYTICS_SCOPES)
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        yta = build("youtubeAnalytics", "v2", credentials=creds)
        resolved_channel_id = channel_id or resolve_expected_channel_id()
        if not resolved_channel_id:
            return {}, "No YouTube channel_id configured; analytics query skipped."
        resp = (
            yta.reports()
            .query(
                ids=f"channel=={resolved_channel_id}",
                startDate=start_date,
                endDate=end_date,
                metrics="views,estimatedMinutesWatched,averageViewDuration,averageViewPercentage,subscribersGained",
                dimensions="video",
                maxResults=200,
                sort="-views",
            )
            .execute()
        )
        headers = [h["name"] for h in resp.get("columnHeaders", [])]
        by_video: dict[str, dict[str, Any]] = {}
        for row in resp.get("rows", []) or []:
            rec = dict(zip(headers, row))
            vid = str(rec.get("video") or "")
            if vid:
                mins = rec.get("estimatedMinutesWatched")
                by_video[vid] = {
                    "analytics_views": rec.get("views"),
                    "estimated_minutes_watched": float(mins) if mins is not None else None,
                    "measured_watch_hours": round(float(mins) / 60.0, 4) if mins is not None else None,
                    "average_view_duration_sec": float(rec["averageViewDuration"])
                    if rec.get("averageViewDuration") is not None
                    else None,
                    "average_view_percentage": float(rec["averageViewPercentage"])
                    if rec.get("averageViewPercentage") is not None
                    else None,
                    "subscribers_gained": int(rec["subscribersGained"])
                    if rec.get("subscribersGained") is not None
                    else None,
                }
        return by_video, None
    except Exception as exc:
        return {}, f"YouTube Analytics API query unavailable ({type(exc).__name__}); metrics kept NULL."


def build_monetization_report(
    records: list[dict[str, Any]],
    channel_stats: dict[str, Any],
    analytics_blocker: str | None = None,
) -> dict[str, Any]:
    shorts = [r for r in records if r["format"] == "Short"]
    longs = [r for r in records if r["format"] == "Long-Form"]
    long_hours = [r["measured_watch_hours"] for r in longs if r.get("measured_watch_hours") is not None]
    short_hours = [r["measured_watch_hours"] for r in shorts if r.get("measured_watch_hours") is not None]

    return {
        "channel_id": channel_stats.get("id") or resolve_expected_channel_id() or "",
        "subscribers": int(channel_stats.get("subscriberCount", 0)) if channel_stats.get("subscriberCount") is not None else None,
        "channel_total_views": int(channel_stats.get("viewCount", 0)) if channel_stats.get("viewCount") is not None else None,
        "total_videos": len(records),
        "shorts_count": len(shorts),
        "long_form_count": len(longs),
        "analytics_status": "ok" if analytics_blocker is None else "blocked",
        "analytics_blocker": analytics_blocker,
        "measured_long_form_watch_hours": round(sum(long_hours), 4) if long_hours else None,
        "measured_shorts_watch_hours_non_ypp_hour_eligible": round(sum(short_hours), 4) if short_hours else None,
        "ypp_qualification_note": (
            "Ordinary Shorts watch hours do not count toward the 3,000h/4,000h YPP public watch-hour threshold; "
            "YPP requires either valid public long-form watch hours (3,000h / 4,000h in 12 months) or valid "
            "public Shorts views (3M / 10M in 90 days)."
        ),
        "videos": records,
    }


def main() -> int:
    yt = get_authenticated_service()
    ch = yt.channels().list(part="contentDetails,statistics", mine=True).execute()
    channel_stats = ch["items"][0]["statistics"]
    uploads_id = ch["items"][0]["contentDetails"]["relatedPlaylists"]["uploads"]

    vids: list[str] = []
    page_token = None
    while True:
        res = (
            yt.playlistItems()
            .list(part="contentDetails", playlistId=uploads_id, maxResults=50, pageToken=page_token)
            .execute()
        )
        vids.extend([item["contentDetails"]["videoId"] for item in res.get("items", [])])
        page_token = res.get("nextPageToken")
        if not page_token:
            break

    res_vids = yt.videos().list(part="snippet,contentDetails,statistics", id=",".join(vids)).execute()
    analytics_by_vid, analytics_blocker = fetch_real_analytics_by_video()

    records: list[dict[str, Any]] = []
    for item in res_vids.get("items", []):
        vid_id = item["id"]
        snippet = item["snippet"]
        stats = item.get("statistics", {})
        content = item.get("contentDetails", {})

        dur_sec = parse_iso8601_duration(content.get("duration", "PT0S"))
        views = int(stats.get("viewCount", 0)) if stats.get("viewCount") is not None else None
        likes = int(stats.get("likeCount", 0)) if stats.get("likeCount") is not None else None
        comments = int(stats.get("commentCount", 0)) if stats.get("commentCount") is not None else None

        is_short = dur_sec <= 60
        fmt = "Short" if is_short else "Long-Form"
        a_rec = analytics_by_vid.get(vid_id, {})

        records.append({
            "id": vid_id,
            "title": snippet.get("title", ""),
            "published_at": snippet.get("publishedAt", "")[:10],
            "duration_sec": dur_sec,
            "format": fmt,
            "views": views,
            "likes": likes,
            "comments": comments,
            "estimated_minutes_watched": a_rec.get("estimated_minutes_watched"),
            "measured_watch_hours": a_rec.get("measured_watch_hours"),
            "average_view_duration_sec": a_rec.get("average_view_duration_sec"),
            "average_view_percentage": a_rec.get("average_view_percentage"),
            "subscribers_gained": a_rec.get("subscribers_gained"),
            "url": f"https://youtu.be/{vid_id}",
        })

    report = build_monetization_report(records, channel_stats, analytics_blocker=analytics_blocker)
    out_file = REPO_ROOT / "channel_assets" / "channel_monetization_report.json"
    out_file.parent.mkdir(parents=True, exist_ok=True)
    out_file.write_text(json.dumps(report, indent=2), encoding="utf-8")

    print("=== SUMMARY METRICS ===")
    print(f"Total Videos: {report['total_videos']} (Shorts: {report['shorts_count']}, Long-Form: {report['long_form_count']})")
    print(f"Total Views: {report['channel_total_views']} | Subscribers: {report['subscribers']}")
    print(f"Analytics Status: {report['analytics_status']}" + (f" ({analytics_blocker})" if analytics_blocker else ""))
    print(f"Measured Long-Form Watch Hours: {report['measured_long_form_watch_hours']}")
    print(f"Measured Shorts Watch Hours (non-YPP-hour eligible): {report['measured_shorts_watch_hours_non_ypp_hour_eligible']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
