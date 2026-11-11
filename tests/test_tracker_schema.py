"""tests/test_tracker_schema.py - CONTENT_TRACKER.md rows are written by column NAME, not position.

Why this file exists: the tracker's section 2 table was rewritten on 2026-10-31 from a 10-column
layout to 7 columns (ID | Format | Live Title | Live Link & ID | Views | Local Project | Status),
and both writers kept assuming the old shape. `pipeline.append_to_tracker` emitted a fixed
10-column row, so any rebuild widened section 2 and shoved the rows below it out of alignment;
`upload_api.update_content_tracker` matched the old shape with a regex, so a completed upload
never updated the row and the tracker went on saying *Pending Upload* for a live video.

tools/tracker.py is the single writer now, and these tests pin the behaviour that matters: the
column count never changes, columns it has no value for are preserved, and a table it cannot
interpret is refused instead of guessed at.
"""

from __future__ import annotations

import re
import multiprocessing
import os
from pathlib import Path

import pytest

from conftest import REPO_ROOT
from tools import tracker

TRACKER = REPO_ROOT / "CONTENT_TRACKER.md"


# --------------------------------------------------------------------------- #
# the real file, read-only
# --------------------------------------------------------------------------- #
def test_every_table_in_the_tracker_is_a_rectangle():
    """A Markdown table only renders if every row has the header's cell count.

    This covers the hand-written tables too (section 1 overview, section 4 citation queue), because
    those are edited by hand and by writers other than tools/tracker.py.
    """
    lines = TRACKER.read_text(encoding="utf-8").splitlines()
    tables, ragged, i = 0, [], 0
    while i < len(lines):
        if lines[i].strip().startswith("|") and i + 1 < len(lines) and tracker.is_separator(lines[i + 1]):
            tables += 1
            width = len(tracker.split_row(lines[i]))
            j = i + 2
            while j < len(lines) and lines[j].strip().startswith("|") and not tracker.is_separator(lines[j]):
                if len(tracker.split_row(lines[j])) != width:
                    ragged.append(f"line {j + 1}: {len(tracker.split_row(lines[j]))} cells vs header's {width} - {lines[j].strip()[:60]}")
                j += 1
            i = j
        else:
            i += 1
    assert tables >= 3, f"expected the overview, inventory and citation tables, found {tables}"
    assert not ragged, ragged


def test_the_inventory_header_names_columns_this_module_understands():
    header = next(ln for ln in TRACKER.read_text(encoding="utf-8").splitlines() if ln.strip().startswith("| ID | Format |"))
    unknown = [c for c in tracker.split_row(header) if tracker.canon_of(c) is None]
    assert not unknown, (
        f"the tracker gained {unknown}; add them to tools/tracker.py TRACKER_COLUMNS so a rebuild "
        "writes them instead of leaving them as an em-dash"
    )


# --------------------------------------------------------------------------- #
# the writer, on a copy
# --------------------------------------------------------------------------- #
@pytest.fixture()
def copy(tmp_path):
    dest = tmp_path / "CONTENT_TRACKER.md"
    base = TRACKER.read_text(encoding="utf-8").rstrip("\n")
    sample_rows = (
        "\n| **SH-13** | Short (9:16) | *Sample Row 13* | *Pending Upload* | 0 | `shorts/sample_13/output/s.mp4` | **Ready** |"
        "\n| **SH-15** | Short (9:16) | *Sample Row 15* | [Watch](https://youtu.be/test1234567) (`test1234567`) | 42 | `shorts/sample_15/output/s.mp4` | **Live** |\n"
    )
    marker = "| ID | Format | Live Title | Live Link & ID | Views | Local Project | Status |\n| :--- | :--- | :--- | :--- | :--- | :--- | :--- |"
    assert marker in base
    dest.write_text(base.replace(marker, marker + sample_rows, 1) + "\n", encoding="utf-8")
    return dest


def row_of(path, video_id: str) -> str:
    lines = path.read_text(encoding="utf-8").splitlines()
    idx = tracker.find_row(lines, video_id)
    assert idx is not None, f"{video_id} disappeared from the tracker"
    return lines[idx]


def test_a_rebuild_keeps_the_column_count_and_the_cells_it_does_not_own(copy):
    before = tracker.split_row(row_of(copy, "SH-13"))
    assert len(before) == 7, before
    wrote = tracker.update_tracker_row(
        "SH-13",
        {"rel_mp4": "`shorts/fixture_rebuild/output/fixture.mp4`", "status": "**Rendered — Gate PASS**"},
        tracker_path=copy,
    )
    assert wrote
    after = tracker.split_row(row_of(copy, "SH-13"))
    assert len(after) == 7, "a rebuild must never change the width of section 2"
    assert (after[0], after[1], after[2]) == (before[0], before[1], before[2])
    assert after[3] == before[3], "the live link is not this writer's to invent"
    assert after[4] == before[4], "Views was not passed and must survive the write"
    assert after[5] == "`shorts/fixture_rebuild/output/fixture.mp4`"
    assert after[6] == "**Rendered — Gate PASS**"


def test_an_unrequested_status_leaves_a_live_row_saying_live(copy):
    """Re-rendering something already Live must not imply the new file is what viewers see."""
    before = row_of(copy, "SH-15")
    tracker.update_tracker_row("SH-15", {"rel_mp4": "`shorts/short_15/output.mp4`"}, tracker_path=copy)
    assert tracker.split_row(row_of(copy, "SH-15"))[6] == "**Live**"
    assert "[Watch](https://youtu.be/test1234567)" in row_of(copy, "SH-15")
    assert before != row_of(copy, "SH-15"), "the mp4 cell should still have been written"


def test_the_upload_writer_finds_the_current_row_shape(copy, monkeypatch):
    """The bug that motivated this module: the old regex only matched the pre-2026-10-31 row."""
    from tools import upload_api

    monkeypatch.setattr(upload_api, "YT_ROOT", copy.parent)
    upload_api.update_content_tracker("SH-16", "https://youtu.be/dQw4w9WgXcQ")
    cells = tracker.split_row(row_of(copy, "SH-16"))
    assert "[Watch](https://youtu.be/dQw4w9WgXcQ) (`dQw4w9WgXcQ`)" in cells, cells
    assert cells[-1] == "**Uploaded**", cells
    assert "*Pending Upload*" not in "".join(cells)


def test_mapping_is_by_name_not_by_position(copy):
    legacy = "| ID | Format | Title | Concept | Science | Live Link | Local MP4 | Upload Kit | Status | Views | Related |\n"
    legacy += "| :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- |\n"
    legacy += "| **SH-99** | Short (9:16) | *Old* | c | s | *Pending Upload* | `old.mp4` | `KIT.md` | **Ready** | 7 | Link to LV-02 |\n"
    copy.write_text(copy.read_text(encoding="utf-8") + "\n## Legacy table\n\n" + legacy, encoding="utf-8")
    tracker.update_tracker_row("SH-99", {"rel_mp4": "`new.mp4`"}, tracker_path=copy)
    cells = tracker.split_row(row_of(copy, "SH-99"))
    assert cells[6] == "`new.mp4`", cells
    assert cells[9] == "7", "Views sat in a different column here and must still be preserved"
    assert len(cells) == 11


def test_a_column_this_module_does_not_know_is_left_alone(tmp_path):
    doc = tmp_path / "CONTENT_TRACKER.md"
    doc.write_text(
        "## 2. Inventory\n\n"
        "| ID | Format | Live Title | Live Link & ID | Views | Local Project | Status | Owner Notes |\n"
        "| :--- | :---: | :--- | :--- | :---: | :--- | :---: | :--- |\n"
        "| **SH-13** | Short (9:16) | *The Dunning-Kruger Trap* | *Pending Upload* | — | `old` | **Re-render** | hand-written, keep me |\n",
        encoding="utf-8",
    )
    assert tracker.update_tracker_row("SH-13", {"status": "**Uploaded**"}, tracker_path=doc)
    cells = tracker.split_row(row_of(doc, "SH-13"))
    assert len(cells) == 8
    assert cells[6] == "**Uploaded**"
    assert cells[7] == "hand-written, keep me", "a column outside TRACKER_COLUMNS is the owner's, not ours"


def test_a_new_video_is_appended_inside_the_inventory_table(copy):
    tracker.update_tracker_row(
        "SH-99",
        {"title": "*Ego Depletion*", "rel_mp4": "`shorts/short_17/output.mp4`", "rel_kit": "`shorts/short_17/UPLOAD_KIT.md`"},
        tracker_path=copy,
    )
    cells = tracker.split_row(row_of(copy, "SH-99"))
    assert len(cells) == 7, cells
    assert cells[2] == "*Ego Depletion*"
    assert cells[3] == "*Pending Upload*"
    assert cells[-1] == "**Ready**"
    body = copy.read_text(encoding="utf-8")
    assert body.index("SH-99") < body.index("## 3."), "a new row must land in section 2, not after it"


def test_a_table_without_an_id_column_is_refused_not_guessed(tmp_path):
    other = tmp_path / "CONTENT_TRACKER.md"
    other.write_text("# Notes\n\n| Thing | Count |\n| :--- | :--- |\n| a | 1 |\n", encoding="utf-8")
    before = other.read_text(encoding="utf-8")
    assert tracker.update_tracker_row("SH-13", {"status": "**Uploaded**"}, tracker_path=other) is False
    assert other.read_text(encoding="utf-8") == before, "refusing is only honest if nothing was written"


def test_reading_a_row_gives_the_live_link_back(copy):
    row = tracker.read_tracker_row("SH-15", tracker_path=copy)
    assert row["status"] == "**Live**", row
    assert re.search(r"youtu\.be/[a-zA-Z0-9_-]{11}", row["live_link"]), row
    assert tracker.read_tracker_row("SH-908", tracker_path=copy) == {}


@pytest.mark.skipif(os.name != "posix", reason="POSIX filesystem locking")
def test_concurrent_tracker_updates_preserve_both_rows(tmp_path):
    # Locking only replacement loses the second row after the first read resumes.
    path = tmp_path / "CONTENT_TRACKER.md"
    path.write_text("| ID | Status |\n| --- | --- |\n| **SH-A** | old |\n| **SH-B** | old |\n")
    context = multiprocessing.get_context("fork")
    first_read, second_started, second_read, release = [context.Event() for _ in range(4)]

    def update(video_id):
        read = Path.read_text

        def delayed_read(target, *args, **kwargs):
            text = read(target, *args, **kwargs)
            if target == path:
                if video_id == "SH-A":
                    first_read.set()
                    assert release.wait(5)
                else:
                    second_read.set()
            return text

        Path.read_text = delayed_read
        if video_id == "SH-B":
            second_started.set()
        assert tracker.update_tracker_row(video_id, {"status": "complete"}, tracker_path=path)

    first, second = [context.Process(target=update, args=(video_id,)) for video_id in ("SH-A", "SH-B")]
    try:
        first.start()
        assert first_read.wait(5)
        second.start()
        assert second_started.wait(5)
        if second_read.wait(0.3):
            second.join(5)  # The unlocked writer finishes before the stale first write.
        release.set()
        for process in (first, second):
            process.join(5)
            assert not process.is_alive()
            assert process.exitcode == 0
        assert tracker.read_tracker_row("SH-A", path)["status"] == "complete"
        assert tracker.read_tracker_row("SH-B", path)["status"] == "complete"
        print(f"tracker pids={[first.pid, second.pid]}; final rows:\n{path.read_text()}")
    finally:
        release.set()
        for process in (first, second):
            if process.pid and process.is_alive():
                process.kill()
                process.join()


@pytest.mark.parametrize("video_id", ["SH-A", "SH-NEW"])
def test_tracker_atomic_failure_preserves_original_bytes(tmp_path, monkeypatch, video_id):
    # Existing-row and append writes both need staged atomic replacement.
    path = tmp_path / "CONTENT_TRACKER.md"
    original = b"| ID | Status |\n| --- | --- |\n| **SH-A** | old |\n"
    path.write_bytes(original)

    def fail(*args):
        raise OSError("injected replace failure")

    monkeypatch.setattr(os, "replace", fail)
    with pytest.raises(OSError, match="injected"):
        tracker.update_tracker_row(video_id, {"status": "complete"}, tracker_path=path)
    assert path.read_bytes() == original
    assert not list(tmp_path.glob("*.tmp"))
