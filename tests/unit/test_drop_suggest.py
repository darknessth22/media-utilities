"""core.drop_suggest: the tools Home suggests for dropped files."""
from core.drop_suggest import MULTI, suggest_tools


def test_video_gets_video_tools_first():
    tools = suggest_tools(["C:/clips/holiday.MP4"])
    assert tools[:4] == ["convert", "compress", "trim", "gif"]
    assert "subtitles" in tools and "video_upscaler" in tools
    assert "pdf_toolkit" not in tools and "bg_eraser" not in tools


def test_audio_image_pdf_and_subtitles():
    assert suggest_tools(["song.flac"])[:2] == ["convert", "trim"]
    assert "vocal_isolator" in suggest_tools(["song.flac"])
    assert "gif" not in suggest_tools(["song.flac"])
    image = suggest_tools(["photo.jpg"])
    assert {"bg_eraser", "upscaler", "photo_restore", "compress"} <= set(image)
    assert suggest_tools(["report.pdf"]) == ["pdf_toolkit", "document"]
    assert suggest_tools(["slides.pptx"]) == ["document"]
    assert suggest_tools(["film.srt"]) == ["subtitles"]


def test_several_files_only_offer_tools_that_take_several():
    tools = suggest_tools(["a.mp4", "b.mp4"])
    assert tools and set(tools) <= MULTI
    assert "merge" in tools and "trim" not in tools
    # A mix only fits tools that take every one of the files.
    assert suggest_tools(["a.mp4", "b.jpg"]) == ["convert", "watermark", "pixel_art"]


def test_unknown_or_empty():
    assert suggest_tools(["notes.xyz"]) == []
    assert suggest_tools([]) == []
