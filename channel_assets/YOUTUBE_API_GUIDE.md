# FrameForge — Official YouTube Data API v3 Architecture & Daily Guide

This document records the official Google Cloud YouTube Data API v3 integration for the active channel configured in `configs/channels/default.yaml` (or overridden via `FRAMEFORGE_CHANNEL_ID`).

---

## 1. Project & Credential Architecture

| Component | Location / Value | Description |
| :--- | :--- | :--- |
| **Google Cloud Project** | `YT-Autopilot` (`yt-autopilot-504515`) | Dedicated Google Cloud console project with YouTube Data API v3 enabled |
| **Project Number** | `231112129685` | Google Cloud project registration number |
| **OAuth Client Credentials** | `channel_assets/client_secrets.json` | Desktop App OAuth 2.0 client secret |
| **Token Cache** | `~/.yt_oauth_token.json` | Persistent user token (auto-refreshes permanently; zero login prompts) |
| **Authorized Scopes** | `youtube.upload`, `youtube.force-ssl` | Grants upload and metadata/read access; the uploader performs no engagement actions |

---

## 2. Daily Commands (Terminal Engine)

Always execute using the local `.venv` virtual environment:

### A. Validate and Release Reviewed Existing Artifacts

Run validation without a publish task or YouTube request:

```bash
.venv/bin/python tools/master.py release-existing --project path/to/project.json --evidence path/to/evidence.json --privacy unlisted
```

After explicit upload authorization, add `--publish --yes`. Research, script, project, render,
packaging, precompose and consistency must all pass. This workflow imports the single upload kit
and canonical MP4; it never regenerates artifacts. Public visibility is a separate authorization.

The compatibility commands `tools/pipeline.py --upload-api <project_directory>` and
`tools/upload_api.py <project_directory>` require `--evidence <reviewed-evidence.json> --yes`.
They run the same strict release gate as the master before calling the shared uploader. All
callers receive exact-channel preflight, unlisted default privacy, atomic receipts and duplicate
prevention. The publisher passes `contains_synthetic_media` from the reviewed project.

Receipts stay at `channel_assets/upload_receipts/<internal-video-id>.json` outside disposable
projects. They bind the internal video ID, media SHA-256 and normalized request metadata SHA-256.
States are `prepared`, `uploading`, `ambiguous`, `uploaded`, and `verified`. An uncertain outcome
blocks every later insert until independently reconciled; never remove the receipt to retry.
Uploaded/verified states query the saved remote ID and return it after validation, without inserting.
Tracker failure is recorded after the remote ID and verified receipt are saved, and cannot cause
a second upload. Concurrent calls serialize on a receipt lock.

### B. Live Channel Analytics & Tracker Sync (2-Second Sync)
Fetches live view counts, like counts, and subscriber counts across all channel videos from Google's servers, and updates `CONTENT_TRACKER.md` automatically:

```bash
.venv/bin/python tools/pipeline.py --sync-stats
```

### C. Re-Authorize OAuth (Only needed if credentials expire or change)
```bash
.venv/bin/python tools/upload_api.py --auth-only
```

---

## 3. What the API Handles Automatically vs. Manual Studio Touchpoints

### 100% Automated by API:
- [x] **Video Bytes**: 4MB chunked resumable upload directly to Google's video ingestion cluster.
- [x] **Title**: Strict lowercase `#shorts` enforcement.
- [x] **Description**: Multi-line narrative, timestamps, and citations.
- [x] **Tags**: Strictly 100% lowercase comma-separated keywords.
- [x] **Category**: Set to Education (`27`).
- [x] **COPPA**: Set to Not Made for Kids (`selfDeclaredMadeForKids: false`).
- [x] **Preview frame**: chosen by YouTube from the video's own frames; the uploader sends no image.
- [x] **Synthetic disclosure**: The master sends the project setting as `status.containsSyntheticMedia`; generated photorealistic scenes require `true`. A missing response field is recorded as unknown and needs Studio confirmation.
- [x] **Production Tracker**: Updates `CONTENT_TRACKER.md` status from `Ready` to `Uploaded` with live YouTube URL.

### Remote verification and later Studio checks

The uploader preflights `channels.list(part="id,snippet", mine=True)` and requires an exact match
against the configured target `channel_id` (from `configs/channels/default.yaml` or `FRAMEFORGE_CHANNEL_ID`)
before insertion; an unconfigured empty channel ID fails closed. It saves the returned remote ID before tracker work,
then independently queries the video and validates channel, title and privacy. The receipt keeps
processing details and returned synthetic/COPPA status. A known mismatch blocks verification;
an omitted disclosure value is unknown, never false.

Inspect processing and playback independently before any later public transition. If the API
omits synthetic disclosure, confirm it in Studio. Comments, replies, likes, pins, related-video
and playlist changes require separate instructions and are never automatic uploader actions.
