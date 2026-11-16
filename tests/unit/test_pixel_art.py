"""Pixel Art: the engine's promises, and the tool screen driving them."""
from __future__ import annotations

import os
import subprocess

import pytest
from PIL import Image, ImageDraw

from core import pixel_art as pa


def _scene(w=320, h=200) -> Image.Image:
    img = Image.new("RGB", (w, h))
    d = ImageDraw.Draw(img)
    for y in range(h):
        d.line([(0, y), (w, y)], fill=(40 + y // 2, 90 + y // 4, 200 - y // 2))
    d.ellipse([200, 30, 290, 120], fill=(250, 210, 60))
    d.rectangle([30, 110, 150, 190], fill=(160, 40, 50))
    return img


def _colours(img: Image.Image) -> set:
    return {c for _n, c in img.convert("RGB").getcolors(1 << 20)}


# ── Engine ────────────────────────────────────────────────────────────────────

def test_auto_palette_respects_the_colour_count():
    out = pa.pixelate(_scene(), pa.PixelSettings(pixel_size=4, colors=8))
    assert len(_colours(out)) <= 8


@pytest.mark.parametrize("name", list(pa.PALETTES))
def test_presets_only_use_their_own_colours(name):
    allowed = {pa._rgb(c) for c in pa.PALETTES[name]}
    out = pa.pixelate(_scene(), pa.PixelSettings(pixel_size=4, palette=name,
                                                 dither=pa.DITHER_FLOYD))
    assert _colours(out) <= allowed


def test_output_is_exactly_the_source_size():
    """Blocks round up at the edge; the result must not grow (640 -> 642)."""
    src = _scene(641, 401)
    for px in (3, 6, 7):
        assert pa.pixelate(src, pa.PixelSettings(pixel_size=px)).size == src.size


def test_small_output_is_one_pixel_per_block():
    out = pa.pixelate(_scene(320, 200), pa.PixelSettings(pixel_size=8, upscale=False))
    assert out.size == (40, 25)


def test_upscaled_blocks_are_solid():
    out = pa.pixelate(_scene(), pa.PixelSettings(pixel_size=8))
    block = out.crop((8, 8, 16, 16))
    assert len(_colours(block)) == 1, "a block must be one flat colour"


def test_ramp_palettes_keep_dark_things_dark():
    """Game Boy matched by RGB distance turned a red house into the sky."""
    out = pa.pixelate(_scene(), pa.PixelSettings(pixel_size=4, palette="gameboy"))
    darkest = pa._rgb(min(pa.PALETTES["gameboy"], key=pa._luma))
    house = out.getpixel((90, 150))
    sun = out.getpixel((245, 75))
    assert pa._luma("#%02X%02X%02X" % house) < pa._luma("#%02X%02X%02X" % sun)
    assert house in {darkest, pa._rgb(sorted(pa.PALETTES["gameboy"], key=pa._luma)[1])}


def test_transparency_stays_hard_edged():
    sprite = Image.new("RGBA", (100, 100), (0, 0, 0, 0))
    ImageDraw.Draw(sprite).ellipse([10, 10, 90, 90], fill=(30, 200, 90, 255))
    out = pa.pixelate(sprite, pa.PixelSettings(pixel_size=10, colors=4))
    assert out.mode == "RGBA"
    hist = out.getchannel("A").histogram()
    assert not any(hist[1:255]), "only fully clear or fully solid pixels"


def test_ordered_dither_makes_a_pattern_not_a_wash():
    flat = Image.new("RGB", (64, 64), (128, 128, 128))
    out = pa.pixelate(flat, pa.PixelSettings(pixel_size=1, palette="grayscale",
                                             dither=pa.DITHER_ORDERED,
                                             contrast=1.0, saturation=1.0))
    assert len(_colours(out)) >= 2, "mid-grey on a 4-level ramp should crosshatch"


def test_gif_frames_share_one_palette(tmp_path):
    """A palette per frame flickers; the whole clip must use one."""
    frames = []
    for i in range(8):
        f = _scene()
        ImageDraw.Draw(f).ellipse([10 + i * 30, 10, 60 + i * 30, 60], fill=(255, 255, 255))
        frames.append(f)
    src = tmp_path / "anim.gif"
    frames[0].save(src, save_all=True, append_images=frames[1:], duration=80, loop=0)

    out = Image.open(pa.convert(str(src), pa.PixelSettings(pixel_size=8, colors=10)))
    seen = set()
    for i in range(out.n_frames):
        out.seek(i)
        seen |= _colours(out)
    assert out.n_frames == 8
    assert len(seen) <= 10


def test_output_names(tmp_path):
    assert pa.default_output("a/photo.jpg").endswith("photo_pixel.png"), "JPEG would smear"
    assert pa.default_output("a/clip.mov").endswith("clip_pixel.mp4")
    assert pa.default_output("a/anim.gif").endswith("anim_pixel.gif")
    with pytest.raises(ValueError):
        pa.convert(str(tmp_path / "notes.txt"), pa.PixelSettings())


def _ffmpeg():
    try:
        from utils.ffmpeg import ffmpeg_path
        subprocess.run([ffmpeg_path, "-version"], capture_output=True, check=True)
        return ffmpeg_path
    except Exception:
        return None


def test_video_keeps_size_frames_and_sound(tmp_path):
    ffmpeg = _ffmpeg()
    if not ffmpeg:
        pytest.skip("ffmpeg not available")
    src = tmp_path / "clip.mp4"
    subprocess.run([ffmpeg, "-y", "-v", "error", "-f", "lavfi", "-i", "testsrc=size=160x120:rate=12",
                    "-f", "lavfi", "-i", "sine=frequency=440", "-t", "1", "-c:v", "libx264",
                    "-pix_fmt", "yuv420p", "-c:a", "aac", str(src)], check=True)
    out = pa.convert(str(src), pa.PixelSettings(pixel_size=4, palette="pico8"))
    w, h, _fps, frames = pa._probe(out)
    streams = subprocess.run([ffmpeg.replace("ffmpeg", "ffprobe"), "-v", "error",
                              "-show_entries", "stream=codec_type", "-of", "csv=p=0", out],
                             capture_output=True, text=True).stdout.split()
    assert (w, h) == (160, 120)
    assert frames >= 11
    assert "audio" in streams


def test_cancelled_video_leaves_no_file(tmp_path):
    ffmpeg = _ffmpeg()
    if not ffmpeg:
        pytest.skip("ffmpeg not available")
    src = tmp_path / "clip.mp4"
    subprocess.run([ffmpeg, "-y", "-v", "error", "-f", "lavfi", "-i", "testsrc=size=160x120:rate=12",
                    "-t", "2", "-pix_fmt", "yuv420p", str(src)], check=True)
    calls = []
    with pytest.raises(InterruptedError):
        pa.convert(str(src), pa.PixelSettings(), cancel=lambda: calls.append(1) or len(calls) > 4)
    assert not os.path.exists(pa.default_output(str(src)))


# ── The screen ────────────────────────────────────────────────────────────────

@pytest.fixture()
def section():
    pytest.importorskip("PySide6.QtWidgets")
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    from PySide6.QtWidgets import QApplication
    from core.settings import SettingsManager
    from gui.tabs.pixel_art_section import PixelArtSection

    QApplication.instance() or QApplication([])
    widget = PixelArtSection(SettingsManager.load())
    yield widget
    widget.close()


def test_loading_a_file_shows_both_previews_and_the_palette(section, tmp_path):
    src = tmp_path / "photo.png"
    _scene().save(src)
    section.load(str(src))

    assert section._before._pixmap is not None
    assert section._after._pixmap is not None
    assert 2 <= len(section._swatches._colours) <= 16


def test_preset_palette_disables_the_colour_count(section):
    idx = section._palette.findData("gameboy")
    section._palette.setCurrentIndex(idx)
    assert not section._colours.isEnabled()
    section._palette.setCurrentIndex(0)
    assert section._colours.isEnabled()


def test_preview_pixel_size_scales_with_the_preview_copy(section, tmp_path):
    """The preview is a reduced copy; the same blocks must look the same."""
    src = tmp_path / "big.png"
    _scene(2880, 1800).save(src)
    section.load(str(src))
    section._pixel.setValue(16)
    scaled = section._settings_from_ui(section._preview_scale)
    assert section._preview_scale == pytest.approx(720 / 2880)
    assert scaled.pixel_size == 4


def test_screen_is_fully_translated(section):
    from PySide6.QtWidgets import QCheckBox, QLabel, QPushButton
    from core import i18n

    i18n.I18n.instance().set_language("ar")
    try:
        section.retranslate_ui()
        texts = []
        for cls in (QLabel, QPushButton, QCheckBox):
            texts += [w.text() for w in section.findChildren(cls) if w.text().strip()]
        latin_only = [t for t in texts
                      if not any("؀" <= c <= "ۿ" for c in t)]
        assert latin_only == []
    finally:
        i18n.I18n.instance().set_language("en")
