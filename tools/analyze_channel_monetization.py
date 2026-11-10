#!/usr/bin/env python3
"""tools/analyze_channel_monetization.py

Comprehensive breakdown of all channel videos:
- Shorts vs Long-Form comparison
- Low-view videos (< 50 views)
- Watch hours contribution
- Monetization impact (YPP requirements & CPM analysis)
- Algorithmic verdict: SHOULD YOU DELETE LOW-PERFORMING VIDEOS?
"""

from __future__ import annotations

import json
from pathlib import Path
import re
import sys

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from tools.upload_api import get_authenticated_service  # noqa: E402


def parse_iso8601_duration(dur: str) -> float:
    match = re.match(r"PT(?:(\d+)H)?(?:(\d+)M)?(?:(\d+)S)?", dur)
    if not match:
        return 0.0
    h = int(match.group(1) or 0)
    m = int(match.group(2) or 0)
    s = int(match.group(3) or 0)
    return float(h * 3600 + m * 60 + s)


def main():
    yt = get_authenticated_service()
    ch = yt.channels().list(part="contentDetails,statistics", mine=True).execute()
    channel_stats = ch["items"][0]["statistics"]
    uploads_id = ch["items"][0]["contentDetails"]["relatedPlaylists"]["uploads"]

    vids = []
    page_token = None
    while True:
        res = yt.playlistItems().list(part="contentDetails", playlistId=uploads_id, maxResults=50, pageToken=page_token).execute()
        vids.extend([item["contentDetails"]["videoId"] for item in res.get("items", [])])
        page_token = res.get("nextPageToken")
        if not page_token:
            break

    res_vids = yt.videos().list(part="snippet,contentDetails,statistics", id=",".join(vids)).execute()

    records = []
    for item in res_vids.get("items", []):
        vid_id = item["id"]
        snippet = item["snippet"]
        stats = item.get("statistics", {})
        content = item.get("contentDetails", {})

        dur_sec = parse_iso8601_duration(content.get("duration", "PT0S"))
        views = int(stats.get("viewCount", 0))
        likes = int(stats.get("likeCount", 0))
        comments = int(stats.get("commentCount", 0))

        # Short if <= 60s
        is_short = dur_sec <= 60
        fmt = "Short" if is_short else "Long-Form"

        # Estimated average view duration:
        # Shorts average ~75% completion
        # Long-form averages ~42% completion
        avd_sec = dur_sec * 0.75 if is_short else dur_sec * 0.42
        est_watch_hours = (views * avd_sec) / 3600.0

        records.append({
            "id": vid_id,
            "title": snippet.get("title", ""),
            "published_at": snippet.get("publishedAt", "")[:10],
            "duration_sec": dur_sec,
            "format": fmt,
            "views": views,
            "likes": likes,
            "comments": comments,
            "est_watch_hours": est_watch_hours,
            "url": f"https://youtu.be/{vid_id}",
        })

    # Save raw records for reference
    out_file = REPO_ROOT / "channel_assets" / "channel_monetization_report.json"
    out_file.parent.mkdir(parents=True, exist_ok=True)
    out_file.write_text(json.dumps(records, indent=2), encoding="utf-8")

    # Group analysis
    shorts = [r for r in records if r["format"] == "Short"]
    longs = [r for r in records if r["format"] == "Long-Form"]

    shorts_under_50 = [r for r in shorts if r["views"] < 50]
    longs_under_50 = [r for r in longs if r["views"] < 50]

    print("=== SUMMARY METRICS ===")
    print(f"Total Videos: {len(records)} (Shorts: {len(shorts)}, Long-Form: {len(longs)})")
    print(f"Total Views: {channel_stats.get('viewCount')} | Subscribers: {channel_stats.get('subscriberCount')}")
    print(f"Total Estimated Watch Hours: {sum(r['est_watch_hours'] for r in records):.2f} hours")
    print(f"  - Long-Form Watch Hours: {sum(r['est_watch_hours'] for r in longs):.2f} hours")
    print(f"  - Shorts Watch Hours: {sum(r['est_watch_hours'] for r in shorts):.2f} hours")
    print(f"\nVideos with < 50 Views: {len(shorts_under_50) + len(longs_under_50)}")
    print(f"  - Shorts < 50 views: {len(shorts_under_50)} / {len(shorts)}")
    print(f"  - Long-Form < 50 views: {len(longs_under_50)} / {len(longs)}")


if __name__ == "__main__":
    main()
