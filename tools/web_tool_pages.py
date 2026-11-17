"""Write one search page per web-app tool: app.videl.app/compress-video and so on.

Why: the web app routes with "#/tool/<id>", and search engines ignore everything
after "#", so to Google the 15 tools were a single page. Each page written here
is a copy of web/index.html with its own <title>, description, canonical URL and
heading, a short how-to and FAQ under the tool, and <html data-tool> so the app
opens that tool straight away (see START_TOOL in web/js/main.js).

Also rewrites the footer tool links in web/index.html, and web/sitemap.xml and
web/robots.txt. Run it after editing web/index.html or the copy below:

    python tools/web_tool_pages.py
"""
from __future__ import annotations

import html
import re
from pathlib import Path

WEB = Path(__file__).resolve().parent.parent / "web"
SITE = "https://app.videl.app"

ENGINE = {
    "video": "FFmpeg, the video engine behind most video software, runs inside your browser tab",
    "pdf": "The PDF is opened and rebuilt inside your browser tab",
    "image": "The image is processed inside your browser tab",
    "ai": "The AI model downloads once and then runs inside your browser tab",
}

# slug, tool id, engine, heading, <title>, description, steps, extra FAQ (question, answer)
PAGES = [
    ("compress-video", "compress", "video", "Compress video",
     "Compress Video Online, Free and Without Uploading | Videl",
     "Make a video smaller to fit email, WhatsApp or Discord limits. Pick the strength and resolution. Free, no sign-up, and your video never leaves your device.",
     ["Add your video. MP4, MOV, WebM, MKV and most other formats work.",
      "Choose a strength. A lower resolution or removing the sound saves even more.",
      "Save the smaller MP4."],
     [("How much smaller will my video get?",
       "It depends on the video. Stronger compression and a lower resolution give the biggest savings, and the result is an MP4 that plays everywhere.")]),
    ("convert-video", "convert", "video", "Convert video and audio",
     "Convert Video and Audio Online: MP4, MP3, WebM, MOV | Videl",
     "Convert video to MP4, WebM, MOV or MKV, or save the sound as MP3, M4A, WAV or OGG. Free, no sign-up, and your files never leave your device.",
     ["Add a video or audio file.",
      "Choose the format to convert to. Pick MP3, M4A, WAV or OGG to keep only the sound.",
      "Save the converted file."],
     [("Can I turn a video into an MP3?", "Yes. Choose MP3 as the format and only the sound is kept."),
      ("What does Copy streams do?",
       "It changes the container without re-encoding, which is instant, but only works when the video and audio already fit the new format.")]),
    ("trim-video", "trim", "video", "Trim video and audio",
     "Trim Video Online: Cut Clips from Videos and Songs | Videl",
     "Cut a clip out of a video or song by dragging the start and end handles. Keep the original format or save as MP4. Free, private, nothing uploaded.",
     ["Add a video or audio file.",
      "Drag the start and end handles to the part you want.",
      "Save the clip."],
     [("Does trimming lower the quality?",
       "Fast cuts at the nearest keyframe and keeps the original quality. Frame-exact cuts at the exact frame and re-encodes the clip."),
      ("Can I trim a song?", "Yes. MP3, M4A, WAV and other audio files work the same way.")]),
    ("video-to-gif", "gif", "video", "Video to GIF",
     "Video to GIF Converter Online, Free and Private | Videl",
     "Turn a moment from a video into an animated GIF. Choose the width and smoothness. Free, no sign-up, and your video never leaves your device.",
     ["Add your video.",
      "Pick the moment, then choose the width and smoothness.",
      "Save the animated GIF."],
     [("How do I keep the GIF small?",
       "Choose a smaller width, lower smoothness and a short moment. GIFs grow quickly with size and length."),
      ("Why does WhatsApp on my computer send my GIF as a still picture?",
       "WhatsApp Desktop and Web flatten GIFs sent from a computer. Send it from your phone, or attach it as a document.")]),
    ("merge-videos", "merge", "video", "Merge videos",
     "Merge Videos Online: Join Clips into One MP4 | Videl",
     "Join several clips into one MP4, in the order you choose. Works with clips of different sizes too. Free, no sign-up, nothing uploaded.",
     ["Add two or more videos.",
      "Put them in the order you want.",
      "Save the joined MP4."],
     [("Can I join clips with different sizes or formats?",
       "Yes. Choose Compatible and the clips are re-encoded so they join cleanly. Fast is quicker for clips from the same camera or app.")]),
    ("remove-audio-from-video", "mux", "video", "Remove or replace audio in a video",
     "Remove Audio from Video Online, or Replace It | Videl",
     "Remove the sound from a video, or replace it with another audio file such as music or a voice-over. Free, private, done in your browser.",
     ["Add your video, and an audio file if you want to replace the sound.",
      "Choose whether to remove the sound or replace it.",
      "Save the video."],
     [("Can I add music to a video?", "Yes. Choose to replace the sound and add your music file.")]),
    ("merge-pdf", "pdf-merge", "pdf", "Merge PDF files",
     "Merge PDF Files Online, Free and Without Uploading | Videl",
     "Combine several PDFs into one file, in the order you choose. Free, no sign-up, and your documents never leave your device.",
     ["Add two or more PDF files.",
      "Put them in the order you want.",
      "Save the merged PDF."],
     [("Is it safe for private documents?",
       "Yes. The files are combined on your device and are never sent anywhere.")]),
    ("split-pdf", "pdf-split", "pdf", "Split a PDF",
     "Split PDF Online: Extract Pages for Free | Videl",
     "Take out the pages you need, or save every page as its own PDF. Free and private: the PDF never leaves your device.",
     ["Add a PDF.",
      "Choose the pages to keep, or split every page into its own file.",
      "Save the new PDF, or a ZIP of single pages."],
     []),
    ("rotate-pdf", "pdf-rotate", "pdf", "Rotate PDF pages",
     "Rotate PDF Pages Online, Free and Private | Videl",
     "Turn sideways or upside-down PDF pages the right way round, for every page or only the ones you pick. Free and private.",
     ["Add a PDF.",
      "Choose the angle and which pages to turn.",
      "Save the corrected PDF."],
     []),
    ("jpg-to-pdf", "images-to-pdf", "pdf", "Images to PDF",
     "JPG to PDF: Combine Images into One PDF Online | Videl",
     "Put photos or scans into one PDF, one image per page. JPG, PNG, WebP and more, with the page size you choose. Free, nothing uploaded.",
     ["Add your images.",
      "Choose the page size.",
      "Save the PDF."],
     []),
    ("pdf-to-jpg", "pdf-to-images", "pdf", "PDF to JPG or PNG",
     "PDF to JPG or PNG Online, Free and Private | Videl",
     "Save each page of a PDF as a JPG or PNG picture, at the quality you choose. Free, and the PDF stays on your device.",
     ["Add a PDF.",
      "Choose JPG or PNG and the quality.",
      "Save the pictures."],
     []),
    ("remove-background", "bg-eraser", "ai", "Remove the background from an image",
     "Remove Image Background Online: Free AI, No Upload | Videl",
     "Cut the subject out of a photo with an AI model that runs on your device. Save a transparent PNG or pick a new background colour. Free, no sign-up.",
     ["Add a photo.",
      "Keep the background transparent, or choose a colour, and adjust the edges.",
      "Save the result."],
     [("Is the AI really running without a server?",
       "Yes. The model downloads once, then runs in your browser, so your photo is never uploaded.")]),
    ("convert-image", "image-convert", "image", "Convert, resize and compress images",
     "Convert, Resize and Compress Images Online: JPG, PNG, WebP | Videl",
     "Change image format to JPG, PNG or WebP, shrink dimensions or reduce file size, for one image or many at once. Free and private.",
     ["Add one or more images.",
      "Choose the format, quality and longest side.",
      "Save the new images."],
     [("Can I convert many images at once?", "Yes. Add as many as you like and they are all converted with the same settings.")]),
    ("pixel-art-maker", "pixel-art", "image", "Pixel art maker",
     "Photo to Pixel Art Converter Online, Free | Videl",
     "Turn a photo into crisp pixel art with a retro colour palette. The preview updates as you change the settings. Free, and your photo stays on your device.",
     ["Add a photo.",
      "Choose the pixel size, palette and number of colours.",
      "Save the pixel art."],
     []),
    ("color-palette-generator", "palette", "image", "Colour palette from an image",
     "Color Palette Generator from Image, Free | Videl",
     "Pull the main colours out of an image, up to 32, and copy any hex code with a click. Free, and your image never leaves your device.",
     ["Add an image.",
      "Choose how many colours you want.",
      "Click a colour to copy its hex code, or save the palette."],
     []),
]


# The how-to heading, phrased the way people search.
HOW = {
    "compress-video": "How to compress a video",
    "convert-video": "How to convert a video or audio file",
    "trim-video": "How to trim a video or song",
    "video-to-gif": "How to make a GIF from a video",
    "merge-videos": "How to merge videos",
    "remove-audio-from-video": "How to remove or replace the sound in a video",
    "merge-pdf": "How to merge PDF files",
    "split-pdf": "How to split a PDF",
    "rotate-pdf": "How to rotate PDF pages",
    "jpg-to-pdf": "How to turn images into a PDF",
    "pdf-to-jpg": "How to turn a PDF into JPG or PNG images",
    "remove-background": "How to remove the background from a photo",
    "convert-image": "How to convert, resize or compress images",
    "pixel-art-maker": "How to turn a photo into pixel art",
    "color-palette-generator": "How to get a colour palette from an image",
}
assert set(HOW) == {p[0] for p in PAGES}


def esc(s: str) -> str:
    return html.escape(s, quote=True)


def faq(engine: str, extra: list[tuple[str, str]]) -> list[tuple[str, str]]:
    return extra + [
        ("Is it free?", "Yes. There is no sign-up, no watermark and no limit on how often you use it."),
        ("Are my files uploaded?", f"No. {ENGINE[engine]}, so your files stay on your device."),
    ]


def tool_links(current: str = "") -> str:
    items = "".join(
        f'<li><a href="/{slug}"{" aria-current=\"page\"" if slug == current else ""}>{esc(h1)}</a></li>'
        for slug, _, _, h1, *_ in PAGES)
    return f'<nav class="foot-tools" aria-label="All tools"><ul>{items}</ul></nav>'


def page(template: str, slug, tool_id, engine, h1, title, desc, steps, extra) -> str:
    url = f"{SITE}/{slug}"
    s = template.replace('<html lang="en">', f'<html lang="en" data-tool="{tool_id}" data-h1="{esc(h1)}">', 1)
    s = re.sub(r"<title>.*?</title>", f"<title>{esc(title)}</title>", s, count=1)
    for pattern, value in ((r'(<meta name="description" content=")[^"]*', desc),
                           (r'(<meta property="og:title" content=")[^"]*', title),
                           (r'(<meta property="og:description" content=")[^"]*', desc),
                           (r'(<meta property="og:url" content=")[^"]*', url),
                           (r'(<link rel="canonical" href=")[^"]*', url)):
        s, n = re.subn(pattern, lambda m: m.group(1) + esc(value), s, count=1)
        assert n == 1, pattern
    s = re.sub(r'\s*<script type="application/ld\+json">.*?</script>', "", s, count=1)  # WebSite data: home page only
    questions = "".join(f"<details><summary>{esc(q)}</summary><p>{esc(a)}</p></details>" for q, a in faq(engine, extra))
    how = "".join(f"<li>{esc(st)}</li>" for st in steps)
    section = (f'  <section class="seo-copy wrap" aria-labelledby="how-h">\n'
               f'    <h2 id="how-h">{esc(HOW[slug])}</h2>\n'
               f'    <ol>{how}</ol>\n'
               f'    <h2>Questions</h2>\n    {questions}\n'
               f'  </section>\n\n  <footer class="foot">')
    s = s.replace("  <footer class=\"foot\">", section, 1)
    return set_links(s, slug)


def set_links(s: str, current: str = "") -> str:
    s, n = re.subn(r"(<!-- tool-links: [^>]*-->).*?(<!-- /tool-links -->)",
                   lambda m: f"{m.group(1)}\n    {tool_links(current)}\n    {m.group(2)}", s, count=1, flags=re.S)
    assert n == 1, "tool-links markers missing from web/index.html"
    return s


def main() -> None:
    index = WEB / "index.html"
    template = set_links(index.read_text(encoding="utf-8"))
    index.write_text(template, encoding="utf-8", newline="\n")
    for slug, *rest in PAGES:
        (WEB / f"{slug}.html").write_text(page(template, slug, *rest), encoding="utf-8", newline="\n")
    urls = [f"{SITE}/"] + [f"{SITE}/{slug}" for slug, *_ in PAGES]
    (WEB / "sitemap.xml").write_text(
        '<?xml version="1.0" encoding="UTF-8"?>\n<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n'
        + "".join(f"  <url><loc>{u}</loc></url>\n" for u in urls) + "</urlset>\n", encoding="utf-8", newline="\n")
    (WEB / "robots.txt").write_text(f"User-agent: *\nAllow: /\n\nSitemap: {SITE}/sitemap.xml\n",
                                    encoding="utf-8", newline="\n")
    print(f"wrote {len(PAGES)} tool pages, sitemap.xml ({len(urls)} URLs) and robots.txt in {WEB}")


if __name__ == "__main__":
    main()
