"""Outlier thresholds must use measured ratios consistently in both interfaces."""

from __future__ import annotations

import json

import pytest

from tools.youtube_skills import find_viral_outliers, swipe


@pytest.mark.parametrize("views, threshold, included", [
    (1496, 1.5, False), (1499, 1.5, False), (1500, 1.5, True), (1501, 1.5, True),
    (1996, 2.0, False), (2000, 2.0, True),
])
@pytest.mark.parametrize("wrapped", [False, True])
def test_cli_and_api_filter_before_rounding(tmp_path, monkeypatch, capsys, views, threshold, included, wrapped):
    rows = [{"channel": "fixture", "title": "Attention research", "views": count}
            for count in (800, 1000, 1000, views)]
    path = tmp_path / "collected.json"
    path.write_text(json.dumps({"videos": rows} if wrapped else rows))
    monkeypatch.setattr("sys.argv", ["swipe.py", str(path), "--min", str(threshold), "--json"])
    swipe.main()
    cli = json.loads(capsys.readouterr().out)
    api = find_viral_outliers(path, min_multiple=threshold)
    assert cli == api
    assert bool(api["outliers"]) is included
    if included:
        assert api["outliers"][0]["views"] == views
        assert api["outliers"][0]["median"] == 1000
        assert api["outliers"][0]["multiple"] == round(views / 1000, 2)


def test_ranking_keeps_channels_separate_and_reports_small_samples():
    rows = [{"channel": "small", "views": n} for n in (10, 10, 10, 20)]
    rows += [{"channel": "large", "views": n} for n in (1000, 1000, 1000, 1400)]
    rows += [{"channel": "thin", "views": n} for n in (1, 2, 100)]
    result = swipe.rank_outliers(rows)
    assert [(row["channel"], row["multiple"]) for row in result["outliers"]] == [("small", 2.0)]
    assert result["skipped_thin_channels"] == [("thin", 3)]


def test_cli_text_summary_uses_shared_outlier_results(tmp_path, monkeypatch, capsys):
    rows = [{"channel": "fixture", "views": n} for n in (800, 1000, 1000, 1496)]
    path = tmp_path / "collected.json"
    path.write_text(json.dumps(rows))
    monkeypatch.setattr("sys.argv", ["swipe.py", str(path)])
    swipe.main()
    text = capsys.readouterr().out
    assert "4 videos across 1 channels" in text
    assert "nothing cleared the threshold" in text
