#!/usr/bin/env python3
"""Schema-aware row writer for CONTENT_TRACKER.md.

The tracker is a hand-maintained Markdown table whose columns have changed over the channel's life.
The 2026-10-31 rewrite of section 2 dropped the Concept / Science / Upload-Kit / Related columns and
re-ordered the rest as:

    | ID | Format | Live Title | Live Link & ID | Views | Local Project | Status |

Two writers used to assume the old shape:

  * ``pipeline.append_to_tracker`` emitted one hardcoded 10-column row, so any rebuild silently
    widened section 2 by three columns and shoved every later row out of alignment.
  * ``upload_api.update_content_tracker`` matched that shape with a regex requiring
    ``*Pending Upload*`` immediately followed by two backticked cells and ``**Ready**``. Against the
    current table it never matched, so a successful upload printed "noted" and left the row saying
    *Pending Upload* forever.

Both now go through :func:`update_tracker_row`, which reads the header of the table it is about to
write into and maps values by COLUMN NAME. Columns it has no value for keep whatever the row already
says, and a column name it does not recognise is left alone rather than guessed.

Nothing here imports the render stack, so the uploader can use it without pulling in torch/MLX.
"""

from __future__ import annotations

import re
from collections.abc import Callable
from pathlib import Path

from tools.atomic_files import durable_write_text, exclusive_lock

DEFAULT_TRACKER = Path(__file__).resolve().parent.parent / "CONTENT_TRACKER.md"

# Canonical field -> the header names that mean it. Compared after normalising (lowercase, "&" ->
# "and", markdown emphasis and backticks stripped, whitespace collapsed), so "Live Link & ID",
# "live link" and "Link and ID" all resolve to `live_link`.
TRACKER_COLUMNS: dict[str, tuple[str, ...]] = {
    "video_id": ("id",),
    "fmt_label": ("format",),
    "title": ("live title", "title", "video title"),
    "concept": ("concept",),
    "science": ("science", "source", "citation"),
    "live_link": ("live link and id", "live link", "link and id", "link", "url", "live url"),
    "views": ("views",),
    "rel_mp4": ("local project", "local mp4", "mp4", "video file", "local file"),
    "rel_kit": ("upload kit", "kit"),
    "status": ("status", "state"),
    "related_target": ("related", "related target", "related video"),
}

# Used only when a row has to be CREATED: a fresh video has nothing worth preserving.
TRACKER_DEFAULTS: dict[str, str] = {
    "fmt_label": "Short (9:16)",
    "live_link": "*Pending Upload*",
    "status": "**Ready**",
    "views": "—",
    "related_target": "—",
}


class _Keep:
    """Sentinel: leave the existing cell untouched."""

    def __repr__(self) -> str:  # pragma: no cover - debugging aid
        return "KEEP"


KEEP = _Keep()

_SEP_CELL = re.compile(r"^:?-{2,}:?$")
_ROW_START_TMPL = r"^\s*\|\s*\*\*{vid}\*\*\s*\|"


def normalise_header(cell: str) -> str:
    key = str(cell).strip().strip("*_`").strip().lower().replace("&", " and ")
    key = re.sub(r"\s+", " ", key).strip(" .")
    return key


def canon_of(cell: str) -> str | None:
    """The canonical field a header cell names, or None if the table has a column we don't own."""
    key = normalise_header(cell)
    for canon, aliases in TRACKER_COLUMNS.items():
        if key in aliases:
            return canon
    return None


def split_row(line: str) -> list[str]:
    text = line.strip()
    if text.startswith("|"):
        text = text[1:]
    if text.endswith("|"):
        text = text[:-1]
    return [c.strip() for c in text.split("|")]


def is_separator(line: str) -> bool:
    text = line.strip()
    if not text.startswith("|"):
        return False
    cells = split_row(text)
    return bool(cells) and all(_SEP_CELL.match(c) for c in cells)


def header_index(lines: list[str], row_idx: int) -> int | None:
    """Index of the header row of the table containing `row_idx`.

    The header is found by walking up through the table's data rows to its alignment row
    (`| :--- | ... |`) and taking the line directly above it - the nearest pipe line above a data
    row is another DATA row, which is why mapping by the closest line instead silently wrote
    nothing at all.
    """
    i = row_idx - 1
    while i >= 0:
        if is_separator(lines[i]):
            if i - 1 >= 0 and lines[i - 1].strip().startswith("|"):
                return i - 1
            return None
        if not lines[i].strip().startswith("|"):
            return None
        i -= 1
    return None


def find_row(lines: list[str], video_id: str) -> int | None:
    pattern = re.compile(_ROW_START_TMPL.format(vid=re.escape(video_id)))
    for i, line in enumerate(lines):
        if pattern.match(line):
            return i
    return None


def first_table_with_column(tracker_text: str, canon: str = "video_id") -> int | None:
    """Index of the header row of the first table that has a column of `canon`."""
    lines = tracker_text.splitlines()
    for i, line in enumerate(lines):
        if not line.strip().startswith("|") or is_separator(line):
            continue
        cells = split_row(line)
        if i + 1 < len(lines) and is_separator(lines[i + 1]) and any(canon_of(c) == canon for c in cells):
            return i
    return None


def row_for_live_id(youtube_video_id: str, tracker_path: Path | None = None) -> str | None:
    """The row ID (e.g. "SH-16") whose Live Link cell carries this YouTube video id.

    Rows are keyed by the channel's own ID, while the API returns 11-character video ids, so a
    caller holding only a video id cannot use :func:`update_tracker_row` directly - it would miss
    ``find_row`` and append a duplicate row instead of editing the live one.
    """
    path = Path(tracker_path) if tracker_path else DEFAULT_TRACKER
    if not path.exists():
        return None
    lines = path.read_text(encoding="utf-8").splitlines(keepends=True)
    for idx, line in enumerate(lines):
        if not line.strip().startswith("|") or is_separator(line):
            continue
        header_idx = header_index(lines, idx)
        if header_idx is None:
            continue
        header = split_row(lines[header_idx])
        cells = split_row(line)
        if len(cells) != len(header):
            continue
        row = {canon_of(name): cell for name, cell in zip(header, cells) if canon_of(name)}
        link = row.get("live_link") or ""
        if youtube_video_id in link:
            return (row.get("video_id") or "").strip("* ").strip() or None
    return None


def read_tracker_row(video_id: str, tracker_path: Path | None = None) -> dict[str, str]:
    """Current cell values of a row, keyed by canonical column name. Empty dict if no row."""
    path = Path(tracker_path) if tracker_path else DEFAULT_TRACKER
    if not path.exists():
        return {}
    lines = path.read_text(encoding="utf-8").splitlines(keepends=True)
    row_idx = find_row(lines, video_id)
    if row_idx is None:
        return {}
    header_idx = header_index(lines, row_idx)
    if header_idx is None:
        return {}
    header = split_row(lines[header_idx])
    cells = split_row(lines[row_idx])
    return {canon_of(name): cell for name, cell in zip(header, cells) if canon_of(name)}


def update_tracker_text(
    transform: Callable[[str], str | None], tracker_path: Path | None = None,
) -> bool:
    """Apply one text transformation under the shared tracker transaction lock.

    The callback receives the latest content and returns replacement text, or None
    to refuse the update. It must not call another tracker writer while holding
    this lock. Missing trackers and refused updates return False; unchanged text
    succeeds without a write.
    """
    path = Path(tracker_path) if tracker_path else DEFAULT_TRACKER
    if not path.exists():
        return False
    path = path.resolve()
    with exclusive_lock(path.with_name(path.name + ".lock")):
        if not path.exists():
            return False
        text = path.read_text(encoding="utf-8")
        updated = transform(text)
        if updated is None:
            return False
        if updated != text:
            durable_write_text(path, updated)
        return True


def update_tracker_row(video_id: str, values: dict[str, object], tracker_path: Path | None = None) -> bool:
    """Write `values` (canonical field -> cell text) into the row for `video_id`.

    Updates the matching row in place, mapping by header name and preserving any column this module
    has no value for. Creates the row at the end of the inventory table when it does not exist yet.
    Returns False, without writing, when the tracker is missing or has no table with an ID column -
    a wrong-shaped table is refused rather than silently mangled.
    """
    return update_tracker_text(lambda text: _updated_row_text(text, video_id, values), tracker_path)


def append_uploaded_video_record(
    video_id: str,
    youtube_url: str,
    title: str = "",
    privacy: str = "PUBLIC",
    tracker_file: Path | None = None,
) -> Path:
    """Append a human-readable upload entry to channel/uploaded_videos.txt."""
    from datetime import datetime, timezone
    import re

    path = tracker_file or (Path(__file__).resolve().parent.parent / "channel" / "uploaded_videos.txt")
    path.parent.mkdir(parents=True, exist_ok=True)

    now_str = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M")
    vid_code_match = re.search(r"(?:v=|youtu\.be/|shorts/)([a-zA-Z0-9_-]{11})", youtube_url)
    remote_id = vid_code_match.group(1) if vid_code_match else ""

    # Reject known placeholders from entering production log unless explicitly targeting custom file
    if tracker_file is None and remote_id in {"dQw4w9WgXcQ", "test_video_id"}:
        return path

    # Deduplicate by remote_id if file already contains it
    if path.exists() and remote_id:
        existing_text = path.read_text(encoding="utf-8", errors="ignore")
        if f"Video ID     : {remote_id}" in existing_text:
            return path

    entry = [
        f"[{now_str}] {video_id} | {title or video_id}",
        f"  YouTube Link : {youtube_url}",
        f"  Video ID     : {remote_id}",
        f"  Privacy      : {privacy.upper()}",
        "-" * 80,
        "",
    ]
    with path.open("a", encoding="utf-8") as f:
        f.write("\n".join(entry))
    return path


def _updated_row_text(text: str, video_id: str, values: dict[str, object]) -> str | None:
    lines = text.splitlines(keepends=True)

    row_idx = find_row(lines, video_id)
    if row_idx is not None:
        header_idx = header_index(lines, row_idx)
        if header_idx is None:
            return None
        header = split_row(lines[header_idx])
        cells = split_row(lines[row_idx])
        if len(cells) != len(header):
            return None
        changed = False
        for position, name in enumerate(header):
            canon = canon_of(name)
            if canon is None or canon == "video_id":
                continue
            value = values.get(canon, KEEP)
            if isinstance(value, _Keep) or value is None:
                continue
            if str(value) != cells[position]:
                cells[position] = str(value)
                changed = True
        if not changed:
            return text
        lines[row_idx] = "| " + " | ".join(cells) + " |\n"
        return "".join(lines)

    header_idx = first_table_with_column(text, "video_id")
    if header_idx is None:
        return None
    header = split_row(lines[header_idx])
    cells = []
    for name in header:
        canon = canon_of(name)
        if canon is None:
            cells.append("—")
        elif canon == "video_id":
            cells.append(f"**{video_id}**")
        else:
            value = values.get(canon, KEEP)
            if isinstance(value, _Keep) or value is None:
                value = TRACKER_DEFAULTS.get(canon, "—")
            cells.append(str(value))
    new_row = "| " + " | ".join(cells) + " |\n"

    # Append after the last contiguous data row of that table, not before the next section.
    insert_at = header_idx + 2  # past the separator
    while insert_at < len(lines) and lines[insert_at].strip().startswith("|") and not is_separator(lines[insert_at]):
        insert_at += 1
    lines.insert(insert_at, new_row)
    return "".join(lines)
