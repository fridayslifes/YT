"""Receipt safety using a fake YouTube service; never authenticates."""

import json
import multiprocessing
import os
from pathlib import Path

import pytest

from tools import upload_api as api

CHANNEL = "UC6hwVBnsfvfUGxfZi2sFT3A"
REMOTE = "abcdefghijk"


class Execute:
    def __init__(self, value):
        self.value = value

    def execute(self):
        return self.value


class FakeService:
    def __init__(self):
        self.channel = CHANNEL
        self.inserts = []
        self.queries = []
        self.error = None
        self.response_status = {"privacyStatus": "unlisted", "selfDeclaredMadeForKids": False}
        self.remote_title = "Dunning-Kruger: Why 12th Felt Like 62nd"

    def channels(self):
        return self

    def videos(self):
        return self

    def list(self, **kw):
        self.queries.append(kw)
        if kw.get("mine"):
            return Execute({"items": [{"id": self.channel}]})
        return Execute(
            {
                "items": [
                    {
                        "id": REMOTE,
                        "snippet": {"channelId": self.channel, "title": self.remote_title},
                        "status": self.response_status,
                        "processingDetails": {"processingStatus": "succeeded"},
                    }
                ]
            }
        )

    def insert(self, **kw):
        self.inserts.append(kw)
        return self

    def next_chunk(self):
        if self.error:
            raise self.error
        return None, {"id": REMOTE}

    def commentThreads(self):
        pytest.fail("engagement forbidden")

    def rate(self, **kw):
        pytest.fail("engagement forbidden")


@pytest.fixture
def upload(tmp_path, monkeypatch):
    from googleapiclient import http

    folder = tmp_path / "short_fixture"
    (folder / "output").mkdir(parents=True)
    (folder / "project.json").write_text(json.dumps({"id": "SH-13"}))
    (folder / "UPLOAD_KIT_TEST.md").write_text("kit")
    (folder / "output/short_fixture.mp4").write_bytes(b"test-media")
    service = FakeService()
    monkeypatch.setattr(api, "YT_ROOT", tmp_path)
    monkeypatch.setattr(api, "get_authenticated_service", lambda: service)
    monkeypatch.setattr(
        api,
        "parse_upload_kit",
        lambda _: {
            "title": service.remote_title,
            "description": "Study #shorts",
            "tags": ["science"],
            "pinned_comment": "Never post me",
        },
    )
    monkeypatch.setattr(api, "update_content_tracker", lambda *a: True)
    monkeypatch.setattr(api, "_backoff_sleep", lambda *a, **kw: None)
    monkeypatch.setattr(http, "MediaFileUpload", lambda *a, **kw: object())
    return folder, service, tmp_path / "channel_assets" / "upload_receipts" / "SH-13.json"


def test_wrong_channel_blocks_before_insert(upload):
    folder, service, _ = upload
    service.channel = "wrong"
    with pytest.raises(RuntimeError, match="channel"):
        api.upload_via_api(folder)
    assert not service.inserts


def test_unlisted_synthetic_upload_has_atomic_external_receipt_and_no_engagement(upload, monkeypatch):
    folder, service, receipt = upload
    states = []
    replace = Path.replace

    def observe(source, target):
        if Path(target) == receipt:
            states.append(json.loads(source.read_text())["state"])
        return replace(source, target)

    monkeypatch.setattr(Path, "replace", observe)
    assert api.upload_via_api(folder, contains_synthetic_media=True) == REMOTE
    assert service.inserts[0]["body"]["status"] == {
        "privacyStatus": "unlisted",
        "selfDeclaredMadeForKids": False,
        "containsSyntheticMedia": True,
    }
    saved = json.loads(receipt.read_text())
    assert states == ["prepared", "uploading", "uploaded", "verified"]
    assert saved["remote_id"] == REMOTE
    assert saved["channel_id"] == CHANNEL
    assert saved["state"] == "verified"
    assert saved["remote_verification"]["containsSyntheticMedia"] == "unknown"
    assert len(saved["media_sha256"]) == len(saved["metadata_sha256"]) == len(saved["operation_key"]) == 64
    assert not receipt.is_relative_to(folder)
    assert not list(receipt.parent.glob("*.tmp"))


def test_ambiguous_upload_blocks_second_run(upload):
    folder, service, receipt = upload
    service.error = OSError("lost final response")
    with pytest.raises(RuntimeError, match="[Aa]mbiguous|reconcil"):
        api.upload_via_api(folder)
    assert json.loads(receipt.read_text())["state"] == "ambiguous"
    with pytest.raises(RuntimeError, match="reconcil"):
        api.upload_via_api(folder)
    assert len(service.inserts) == 1


@pytest.mark.parametrize("state", ["uploaded", "verified"])
def test_completed_receipt_is_remotely_checked_and_reused(upload, state):
    folder, service, receipt = upload
    assert api.upload_via_api(folder) == REMOTE
    saved = json.loads(receipt.read_text())
    saved["state"] = state
    receipt.write_text(json.dumps(saved))
    assert api.upload_via_api(folder) == REMOTE
    assert len(service.inserts) == 1
    assert json.loads(receipt.read_text())["state"] == "verified"
    assert service.queries[-1]["part"] == "id,snippet,status,contentDetails,processingDetails"


def test_tracker_failure_leaves_verified_receipt_and_no_second_insert(upload, monkeypatch):
    folder, service, receipt = upload

    def fail(*args):
        raise OSError("tracker unavailable")

    monkeypatch.setattr(api, "update_content_tracker", fail)
    assert api.upload_via_api(folder) == REMOTE
    saved = json.loads(receipt.read_text())
    assert saved["state"] == "verified"
    assert any("tracker" in note.lower() for note in saved["notes"])
    assert api.upload_via_api(folder) == REMOTE
    assert len(service.inserts) == 1


def test_changed_operation_and_remote_mismatch_never_reinsert(upload):
    folder, service, receipt = upload
    api.upload_via_api(folder)
    service.response_status["privacyStatus"] = "public"
    with pytest.raises(RuntimeError, match="privacy"):
        api.upload_via_api(folder)
    (folder / "output/short_fixture.mp4").write_bytes(b"changed-media")
    with pytest.raises(RuntimeError, match="operation|reconcil"):
        api.upload_via_api(folder)
    assert len(service.inserts) == 1


def test_uploading_receipt_blocks_and_prepared_can_resume(upload):
    folder, service, receipt = upload
    api.upload_via_api(folder)
    saved = json.loads(receipt.read_text())
    saved["state"] = "uploading"
    receipt.write_text(json.dumps(saved))
    with pytest.raises(RuntimeError, match="reconcil"):
        api.upload_via_api(folder)
    assert len(service.inserts) == 1
    # A fresh prepared operation has never started an insert.
    saved["state"] = "prepared"
    saved.pop("remote_id", None)
    saved.pop("remote_url", None)
    receipt.write_text(json.dumps(saved))
    api.upload_via_api(folder)
    assert len(service.inserts) == 2


def test_receipt_is_durable_and_verified_before_tracker(upload, monkeypatch):
    folder, _, receipt = upload

    def tracker(*args):
        saved = json.loads(receipt.read_text())
        assert saved["state"] == "verified"
        assert saved["remote_id"] == REMOTE

    monkeypatch.setattr(api, "update_content_tracker", tracker)
    api.upload_via_api(folder)


def test_known_incorrect_synthetic_response_blocks_verified_state(upload):
    folder, service, receipt = upload
    service.response_status["containsSyntheticMedia"] = False
    with pytest.raises(RuntimeError, match="synthetic"):
        api.upload_via_api(folder, contains_synthetic_media=True)
    assert json.loads(receipt.read_text())["state"] == "uploaded"
    with pytest.raises(RuntimeError, match="synthetic"):
        api.upload_via_api(folder, contains_synthetic_media=True)
    assert len(service.inserts) == 1


def test_tracker_note_storage_failure_still_returns_saved_remote_id(upload, monkeypatch):
    folder, service, receipt = upload
    write = api._write_receipt

    def fail_tracker(*args):
        raise OSError("tracker failed")

    def fail_note(path, saved):
        if saved["notes"]:
            raise OSError("cannot save tracker note")
        write(path, saved)

    monkeypatch.setattr(api, "update_content_tracker", fail_tracker)
    monkeypatch.setattr(api, "_write_receipt", fail_note)
    assert api.upload_via_api(folder) == REMOTE
    assert json.loads(receipt.read_text())["state"] == "verified"
    assert len(service.inserts) == 1


def test_upload_tracker_atomic_failure_leaves_original_row(tmp_path, monkeypatch):
    # The real upload-to-tracker adapter must retain the old row on a disk failure.
    tracker_path = tmp_path / "CONTENT_TRACKER.md"
    original = b"| ID | Live Link | Status |\n| --- | --- | --- |\n| **SH-13** | pending | ready |\n"
    tracker_path.write_bytes(original)
    monkeypatch.setattr(api, "YT_ROOT", tmp_path)

    def fail(*args):
        raise OSError("tracker replace failed")

    monkeypatch.setattr(os, "replace", fail)
    with pytest.raises(OSError, match="tracker replace"):
        api.update_content_tracker("SH-13", f"https://youtu.be/{REMOTE}")
    assert tracker_path.read_bytes() == original
    assert not list(tmp_path.glob("*.tmp"))


class StatsService:
    """Offline channel, playlist and video responses for the real sync writer."""

    def channels(self):
        return self

    def playlistItems(self):
        return self

    def videos(self):
        return self

    def list(self, **kwargs):
        if kwargs.get("mine"):
            return Execute({"items": [{
                "id": CHANNEL,
                "snippet": {"title": "Fixture channel", "customUrl": "@fixture"},
                "statistics": {"subscriberCount": "42", "viewCount": "1234", "videoCount": "1"},
                "contentDetails": {"relatedPlaylists": {"uploads": "fixture-uploads"}},
            }]})
        if "playlistId" in kwargs:
            return Execute({"items": [{"snippet": {"resourceId": {"videoId": REMOTE}}}]})
        return Execute({"items": [{
            "id": REMOTE, "snippet": {"title": "Fixture video"},
            "statistics": {"viewCount": "87", "likeCount": "3"},
        }]})


@pytest.fixture
def stats_tracker(tmp_path, monkeypatch):
    path = tmp_path / "CONTENT_TRACKER.md"
    path.write_text(
        "| Metric | Value |\n| --- | --- |\n"
        "| **Current Subscribers** | **1** |\n"
        "| **Total Channel Views** | **2+** |\n\n"
        "| ID | Live Link | Views | Status |\n| --- | --- | --- | --- |\n"
        f"| **SH-13** | https://youtu.be/{REMOTE} | 0 | old |\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(api, "YT_ROOT", tmp_path)
    monkeypatch.setattr(api, "get_authenticated_service", lambda: StatsService())
    return path


@pytest.mark.skipif(os.name != "posix", reason="POSIX filesystem locking")
def test_concurrent_stats_overview_and_row_updates_survive(stats_tracker):
    # An unlocked overview replacement overwrites a row committed after its read.
    from tools import tracker

    path = stats_tracker
    context = multiprocessing.get_context("fork")
    overview_read, row_started, row_read, release = [context.Event() for _ in range(4)]

    def sync():
        read = Path.read_text

        def paused_read(target, *args, **kwargs):
            content = read(target, *args, **kwargs)
            if target == path and not overview_read.is_set():
                overview_read.set()
                assert release.wait(5)
            return content

        Path.read_text = paused_read
        api.sync_channel_stats()

    def update_row():
        read = Path.read_text

        def observed_read(target, *args, **kwargs):
            content = read(target, *args, **kwargs)
            if target == path:
                row_read.set()
            return content

        Path.read_text = observed_read
        row_started.set()
        assert tracker.update_tracker_row("SH-13", {"status": "complete"}, tracker_path=path)

    overview, row = context.Process(target=sync), context.Process(target=update_row)
    try:
        overview.start()
        assert overview_read.wait(5)
        row.start()
        assert row_started.wait(5)
        if row_read.wait(0.3):
            row.join(5)  # Without the shared lock, commit the row before overview resumes.
            assert row.exitcode == 0
        release.set()
        for process in (overview, row):
            process.join(5)
            assert not process.is_alive(), "tracker transaction deadlocked"
            assert process.exitcode == 0
        content = path.read_text()
        assert "| **Current Subscribers** | **42** |" in content
        assert "| **Total Channel Views** | **1,234+** |" in content
        saved = tracker.read_tracker_row("SH-13", path)
        assert saved["views"] == "87"
        assert saved["status"] == "complete"
        print(f"overview PID={overview.pid}; row PID={row.pid}; final tracker:\n{content}")
    finally:
        release.set()
        for process in (overview, row):
            if process.pid and process.is_alive():
                process.kill()
                process.join()


def test_stats_overview_atomic_failure_preserves_bytes(stats_tracker, monkeypatch):
    # A staging failure must not expose even a partial overview update.
    original = stats_tracker.read_bytes()

    def fail(*args):
        raise OSError("overview replace failed")

    monkeypatch.setattr(os, "replace", fail)
    with pytest.raises(OSError, match="overview replace"):
        api.sync_channel_stats()
    assert stats_tracker.read_bytes() == original
    assert not list(stats_tracker.parent.glob("*.tmp"))
    print(f"overview failure surviving bytes={original!r}")
