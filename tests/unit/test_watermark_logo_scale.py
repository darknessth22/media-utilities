"""A video logo is a share of the video's width, like on images, not of the logo's own size."""
from core import watermarker


def test_video_logo_follows_video_width(monkeypatch, tmp_path):
    seen = {}
    monkeypatch.setattr("core.subtitles.probe_resolution", lambda path: (1080, 1920))
    monkeypatch.setattr(watermarker, "tracked_run", lambda cmd, *a, **k: seen.setdefault("cmd", cmd))
    video = tmp_path / "clip.mp4"
    video.write_bytes(b"x")
    assert watermarker.watermark_logo(str(video), "logo.png", scale=0.15)
    graph = seen["cmd"][seen["cmd"].index("-filter_complex") + 1]
    assert graph.startswith("[1:v]scale=162:-2,")      # 15% of 1080 px


def test_unknown_video_width_keeps_old_scaling(monkeypatch, tmp_path):
    seen = {}
    monkeypatch.setattr("core.subtitles.probe_resolution", lambda path: (0, 0))
    monkeypatch.setattr(watermarker, "tracked_run", lambda cmd, *a, **k: seen.setdefault("cmd", cmd))
    video = tmp_path / "clip.mp4"
    video.write_bytes(b"x")
    assert watermarker.watermark_logo(str(video), "logo.png", scale=0.15)
    assert "[1:v]scale=iw*0.15:-1," in seen["cmd"][seen["cmd"].index("-filter_complex") + 1]
