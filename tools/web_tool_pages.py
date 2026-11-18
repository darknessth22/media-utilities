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
import json
import re
from pathlib import Path

WEB = Path(__file__).resolve().parent.parent / "web"
SITE = "https://app.videl.app"
HOME_H1 = "Media tools that never leave your browser"   # the home page's heading in main.js

ENGINE = {
    "video": "FFmpeg, the video engine behind most video software, runs inside your browser tab",
    "pdf": "The PDF is opened and rebuilt inside your browser tab",
    "image": "The image is processed inside your browser tab",
    "ai": "The AI model downloads once and then runs inside your browser tab",
}

# slug, tool id, engine, heading, <title>, description, steps, extra FAQ (question, answer),
# and optionally the settings the tool opens with (field key -> value, see workspace.js).
# A preset page targets a search the tool already answers ("video to mp3"), so its
# copy must describe what the preset really does.
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
    ("video-to-mp3", "convert", "video", "Video to MP3",
     "Video to MP3 Converter Online, Free and Private | Videl",
     "Pull the sound out of a video and save it as an MP3. Works with MP4, MOV, WebM, MKV and more. Free, no sign-up, and your video never leaves your device.",
     ["Add your video.",
      "MP3 is already chosen. Pick M4A, WAV or OGG instead if you prefer.",
      "Save the MP3."],
     [("What quality is the MP3?", "192 kbps, which sounds the same as the original to most ears and keeps the file small."),
      ("Can I keep only part of the sound?", "Yes. Cut the part you want with Trim video and audio, before or after converting.")],
     {"format": "mp3"}),
    ("audio-converter", "convert", "video", "Audio converter",
     "Audio Converter Online: MP3, M4A, WAV, OGG | Videl",
     "Convert audio files to MP3, M4A, WAV or OGG, or save the sound of a video as audio. Free, no sign-up, and your files never leave your device.",
     ["Add an audio file, such as MP3, M4A, WAV, FLAC or OGG.",
      "Choose the format to convert to.",
      "Save the converted file."],
     [("Can I convert FLAC to MP3?", "Yes. FLAC, Opus and most other audio files open, and you can save them as MP3, M4A, WAV or OGG."),
      ("Which format should I pick?", "MP3 plays everywhere. M4A is a little smaller at the same quality. WAV keeps every detail but is large.")],
     {"format": "mp3"}),
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
      "Pick the moment, then choose the width and smoothness, or type your own.",
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
    ("split-video", "split", "video", "Split video",
     "Split Video Online: Cut into Parts by Length or Size | Videl",
     "Cut a long video or recording into parts of any length, such as 1 or 10 minutes, or into files under a size you choose, such as 25 MB. Nothing is re-encoded, so it's fast and the quality stays the same. Free and private.",
     ["Add your video or audio file.",
      "Choose to split by length or by file size, from the list or typed in.",
      "Save the parts one by one, or all together as a ZIP."],
     [("Why do some parts run a few seconds over?",
       "Without re-encoding, a video can only be cut at a keyframe, so each part ends at the first keyframe after the length you chose."),
      ("Will each part really be under the size I chose?",
       "Videl checks the parts and splits again with shorter parts if one came out too big."),
      ("Can I split audio too?", "Yes. MP3, M4A, WAV and other audio files split the same way.")]),
    ("rotate-video", "transform", "video", "Rotate video",
     "Rotate Video Online: Turn Sideways Videos Upright | Videl",
     "Turn a sideways or upside-down video the right way round, tilt it by any angle, or mirror it. You can crop and resize in the same step. Free, no sign-up, and your video never leaves your device.",
     ["Add your video.",
      "Choose 90° right, 90° left or 180°, type any angle, or mirror it.",
      "Save the MP4."],
     [("Does rotating lower the quality?",
       "The video is re-encoded at high quality, so the difference is hard to see, and the result is an MP4 that plays everywhere.")]),
    ("crop-video", "transform", "video", "Crop video",
     "Crop Video Online to 9:16, 1:1, 4:5 or 16:9 | Videl",
     "Crop a video to 9:16 for Reels, TikTok and Shorts, square, 4:5 for Instagram posts, 16:9 for YouTube, or any shape you type, such as 3:2. The centre of the picture is kept. Free and private.",
     ["Add your video.",
      "Choose the shape to crop to, or type your own, such as 3:2.",
      "Save the MP4."],
     [("Which part of the picture is kept?",
       "The centre. If the video is sideways, rotate it in the same step: the crop is applied after rotating.")]),
    ("resize-video", "transform", "video", "Resize video",
     "Resize Video Online: 1080p, 720p or 480p | Videl",
     "Make a video smaller in pixels: 1080p, 720p, 480p or any size you type, measured on the shorter side so vertical videos work too. Free, no sign-up, and your video never leaves your device.",
     ["Add your video.",
      "Choose 1080p, 720p or 480p, or type a size.",
      "Save the MP4."],
     [("Can it make a video bigger?",
       "No. A video already smaller than the size you choose keeps its size. To enlarge videos, use the AI video upscaler in the Videl desktop app."),
      ("Should I resize or compress?",
       "Resizing lowers the number of pixels. To make the file smaller without changing its size, use Compress video.")]),
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
    ("compress-image", "image-convert", "image", "Compress images",
     "Compress Images Online: Make JPG, PNG and WebP Smaller | Videl",
     "Make photos smaller for email, upload forms and websites. Lower the quality or the size, for one image or many at once. Free, and your images never leave your device.",
     ["Add one or more images.",
      "JPG at 70% quality is already chosen. Lower the quality or pick a smaller longest side to save more.",
      "Save the smaller images."],
     [("Which format gives the smallest file?", "WebP is usually the smallest. JPG works everywhere, including sites and forms that don't accept WebP."),
      ("Will transparent areas stay transparent?", "Only as PNG or WebP. JPG has no transparency, so transparent areas turn white.")],
     {"format": "jpg", "quality": 70}),
    ("resize-image", "image-convert", "image", "Resize images",
     "Resize Images Online: Make Photos Smaller in Pixels | Videl",
     "Shrink photos to 3840, 1920, 1280 or 800 pixels on the longest side, or any size you type, keeping their shape and format. One image or many at once. Free and private.",
     ["Add one or more images.",
      "Choose the longest side, or type your own. 1920 px is already chosen.",
      "Save the resized images."],
     [("Will the image be stretched?", "No. The width and height shrink together, so the shape stays the same."),
      ("Can it make an image bigger?", "No, it only makes images smaller, and a smaller image is left as it is. To enlarge photos, use the AI image upscaler in the Videl desktop app.")],
     {"format": "keep", "maxSide": "1920"}),
    ("png-to-jpg", "image-convert", "image", "PNG to JPG",
     "PNG to JPG Converter Online, Free and Private | Videl",
     "Convert PNG images to JPG, one or many at once, at the quality you choose. Free, no sign-up, and your images never leave your device.",
     ["Add one or more PNG images.",
      "JPG is already chosen. Set the quality.",
      "Save the JPGs."],
     [("What happens to transparent areas?", "JPG has no transparency, so they are filled with white.")],
     {"format": "jpg"}),
    ("webp-to-jpg", "image-convert", "image", "WebP to JPG",
     "WebP to JPG Converter Online, Free and Private | Videl",
     "Turn WebP images saved from websites into JPGs that open everywhere. One or many at once. Free, no sign-up, nothing uploaded.",
     ["Add one or more WebP images.",
      "JPG is already chosen. Set the quality.",
      "Save the JPGs."],
     [("Why convert WebP to JPG?", "Some apps, printers and upload forms still don't accept WebP. JPG works everywhere.")],
     {"format": "jpg"}),
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
    "video-to-mp3": "How to convert a video to MP3",
    "audio-converter": "How to convert an audio file",
    "trim-video": "How to trim a video or song",
    "video-to-gif": "How to make a GIF from a video",
    "merge-videos": "How to merge videos",
    "remove-audio-from-video": "How to remove or replace the sound in a video",
    "split-video": "How to split a video into parts",
    "rotate-video": "How to rotate a video",
    "crop-video": "How to crop a video",
    "resize-video": "How to resize a video",
    "merge-pdf": "How to merge PDF files",
    "split-pdf": "How to split a PDF",
    "rotate-pdf": "How to rotate PDF pages",
    "jpg-to-pdf": "How to turn images into a PDF",
    "pdf-to-jpg": "How to turn a PDF into JPG or PNG images",
    "remove-background": "How to remove the background from a photo",
    "convert-image": "How to convert, resize or compress images",
    "compress-image": "How to compress an image",
    "resize-image": "How to resize an image",
    "png-to-jpg": "How to convert PNG to JPG",
    "webp-to-jpg": "How to convert WebP to JPG",
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


def related(slug: str, tool_id: str, engine: str) -> list[tuple[str, str]]:
    """Up to four (slug, heading) pages of the same kind: the same tool first, then the same category."""
    kind = "image" if engine == "ai" else engine
    same = [p for p in PAGES if p[0] != slug and ("image" if p[2] == "ai" else p[2]) == kind]
    same.sort(key=lambda p: p[1] != tool_id)   # stable: keeps PAGES order within each group
    return [(p[0], p[3]) for p in same[:4]]


def set_main(s: str, h1: str, text: str) -> str:
    """Put the heading and intro in the page's own HTML, for crawlers that don't run
    JavaScript (Bing, AI search). main.js replaces it with the live page."""
    s, n = re.subn(r'(<main id="main" tabindex="-1">).*?(</main>)',
                   lambda m: f'{m.group(1)}<div class="wrap"><h1>{esc(h1)}</h1><p>{esc(text)}</p></div>{m.group(2)}',
                   s, count=1, flags=re.S)
    assert n == 1, "<main> missing from web/index.html"
    return s


def page(template: str, slug, tool_id, engine, h1, title, desc, steps, extra, preset=None) -> str:
    url = f"{SITE}/{slug}"
    attrs = f'data-tool="{tool_id}" data-h1="{esc(h1)}"' + (f' data-preset="{esc(json.dumps(preset))}"' if preset else "")
    s = template.replace('<html lang="en">', f'<html lang="en" {attrs}>', 1)
    s = set_main(s, h1, desc)
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
               f'    <h2>Related tools</h2>\n    <ul class="related">{"".join(f'<li><a href="/{s}">{esc(n)}</a></li>' for s, n in related(slug, tool_id, engine))}</ul>\n'
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
    home_desc = re.search(r'<meta name="description" content="([^"]*)"', template).group(1)
    template = set_main(template, HOME_H1, html.unescape(home_desc))
    index.write_text(template, encoding="utf-8", newline="\n")
    for slug, *rest in PAGES:
        (WEB / f"{slug}.html").write_text(page(template, slug, *rest), encoding="utf-8", newline="\n")
    # The app links each tool to its own page (the one without a preset), so the
    # address and the how-to always match the tool on screen.
    own = {}
    for p in PAGES:
        if len(p) == 8:
            own.setdefault(p[1], p[0])
    # The same copy for the app, which swaps pages in place (renderCopy in main.js).
    data = {slug: {"tool": tool_id, "h1": h1, "title": title, "how": HOW[slug], "steps": steps,
                   "faq": faq(engine, extra), "related": related(slug, tool_id, engine),
                   "preset": rest[0] if rest else None}
            for slug, tool_id, engine, h1, title, desc, steps, extra, *rest in PAGES}
    (WEB / "js" / "pages.js").write_text(
        "// Written by tools/web_tool_pages.py: every tool page's copy, and the page that opens each tool.\n"
        f"export const PAGES = {json.dumps(data, ensure_ascii=False, separators=(',', ':'))};\n"
        f"export const PAGE_OF = {json.dumps(own, indent=2)};\n", encoding="utf-8", newline="\n")
    urls =[f"{SITE}/"] + [f"{SITE}/{slug}" for slug, *_ in PAGES]
    (WEB / "sitemap.xml").write_text(
        '<?xml version="1.0" encoding="UTF-8"?>\n<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n'
        + "".join(f"  <url><loc>{u}</loc></url>\n" for u in urls) + "</urlset>\n", encoding="utf-8", newline="\n")
    (WEB / "robots.txt").write_text(f"User-agent: *\nAllow: /\n\nSitemap: {SITE}/sitemap.xml\n",
                                    encoding="utf-8", newline="\n")
    print(f"wrote {len(PAGES)} tool pages, sitemap.xml ({len(urls)} URLs) and robots.txt in {WEB}")


if __name__ == "__main__":
    main()
