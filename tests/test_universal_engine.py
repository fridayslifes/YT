import tempfile
from pathlib import Path
from tools import universal_engine


def test_get_font_fallback():
    font = universal_engine.get_font(Path("/nonexistent/font.ttf"), 24)
    assert font is not None


def test_render_all_archetypes_short_probe():
    with tempfile.TemporaryDirectory() as tmpdir:
        tmp_path = Path(tmpdir)

        # Probe 0.2s render (6 frames) for speed in test suite
        p1 = universal_engine.render_photobook_from_scratch(
            tmp_path / "probe_01.mp4", duration=0.2, fps=30, width=540, height=960
        )
        assert p1.exists()
        assert p1.stat().st_size > 500

        p2 = universal_engine.render_riddle_from_scratch(
            tmp_path / "probe_02.mp4", duration=0.2, fps=30, width=540, height=960
        )
        assert p2.exists()
        assert p2.stat().st_size > 500

        p3 = universal_engine.render_stickman_from_scratch(
            tmp_path / "probe_03.mp4", duration=0.2, fps=30, width=540, height=960
        )
        assert p3.exists()
        assert p3.stat().st_size > 500

        p4 = universal_engine.render_hybrid_from_scratch(
            tmp_path / "probe_04.mp4", duration=0.2, fps=30, width=540, height=960
        )
        assert p4.exists()
        assert p4.stat().st_size > 500
