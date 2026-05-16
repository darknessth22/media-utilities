"""Burn-in subtitles into a video via FFmpeg `subtitles=` filter (libass).

Pure ffmpeg — no extra deps. Hardcodes captions into the video stream so
they render on every player without separate sub track.
"""
from __future__ import annotations

import os
import re
import subprocess
import sys
import tempfile
import uuid
from queue import Queue, Empty
from threading import Thread

from utils.ffmpeg import ffmpeg_path, ffprobe_path
from utils.process_registry import register, tracked_run, unregister

_WIN_FLAGS = {"creationflags": 0x08000000} if sys.platform == "win32" else {}

_VIDEO_EXTS = {".mp4", ".mkv", ".avi", ".mov", ".webm", ".flv", ".m4v", ".wmv"}
_SUB_EXTS = {".srt", ".ass", ".ssa", ".vtt"}


def _escape_filter_path(p: str) -> str:
    """Escape a path for ffmpeg `subtitles=` filter argument."""
    p = p.replace("\\", "/")
    p = p.replace(":", "\\:").replace("'", "\\'").replace(",", "\\,")
    p = p.replace("[", "\\[").replace("]", "\\]")
    return p


def _hex_to_ass_color(color: str) -> str | None:
    """Convert hex color to libass `&HAABBGGRR` literal.

    Accepts `#RRGGBB` (alpha defaults to 00 = opaque) or Qt's `#AARRGGBB`
    8-char form. libass alpha is inverted: 00 = opaque, FF = transparent —
    Qt uses 00 = transparent so we flip it.
    """
    s = color.strip().lstrip("#")
    if re.fullmatch(r"[0-9A-Fa-f]{6}", s):
        rr, gg, bb = s[0:2], s[2:4], s[4:6]
        aa = "00"
    elif re.fullmatch(r"[0-9A-Fa-f]{8}", s):
        qa, rr, gg, bb = s[0:2], s[2:4], s[4:6], s[6:8]
        # Qt: 00=transparent, FF=opaque. libass: 00=opaque, FF=transparent.
        aa = f"{255 - int(qa, 16):02X}"
    else:
        return None
    return f"&H{aa}{bb}{gg}{rr}".upper()


def _build_force_style(
    font: str | None,
    size: int | None,
    color: str | None,
    outline: int | None,
    outline_color: str | None = None,
    back_color: str | None = None,
    bold: bool = False,
    italic: bool = False,
    alignment: int | None = None,
    margin_v: int | None = None,
    border_style: int | None = None,
    shadow: int | None = None,
) -> str | None:
    parts: list[str] = []
    if font:
        parts.append(f"FontName={font}")
    if size:
        parts.append(f"FontSize={size}")
    if color:
        c = _hex_to_ass_color(color)
        if c:
            parts.append(f"PrimaryColour={c}")
    if outline_color:
        c = _hex_to_ass_color(outline_color)
        if c:
            parts.append(f"OutlineColour={c}")
    if back_color:
        c = _hex_to_ass_color(back_color)
        if c:
            parts.append(f"BackColour={c}")
    if outline is not None:
        parts.append(f"Outline={outline}")
    if shadow is not None:
        parts.append(f"Shadow={shadow}")
    if border_style is not None:
        parts.append(f"BorderStyle={border_style}")
    if bold:
        parts.append("Bold=-1")
    if italic:
        parts.append("Italic=-1")
    if alignment is not None and 1 <= alignment <= 9:
        parts.append(f"Alignment={alignment}")
    # libass quirk: for middle alignments (4/5/6) MarginV is applied as a
    # from-top offset, pushing centered text toward the top of the frame.
    # Skip the field so true vertical centering works.
    if margin_v is not None and alignment not in (4, 5, 6):
        parts.append(f"MarginV={margin_v}")
    return ",".join(parts) if parts else None


def probe_duration(video_path: str) -> float:
    """Return video duration in seconds, 0.0 on failure."""
    try:
        r = subprocess.run(
            [ffprobe_path, "-v", "error", "-show_entries", "format=duration",
             "-of", "default=noprint_wrappers=1:nokey=1", video_path],
            capture_output=True, text=True, timeout=15, **_WIN_FLAGS,
        )
        return float(r.stdout.strip() or 0.0)
    except Exception:
        return 0.0


def probe_resolution(video_path: str) -> tuple[int, int]:
    """Return (width, height), (0,0) on failure."""
    try:
        r = subprocess.run(
            [ffprobe_path, "-v", "error", "-select_streams", "v:0",
             "-show_entries", "stream=width,height",
             "-of", "csv=p=0:s=x", video_path],
            capture_output=True, text=True, timeout=15, **_WIN_FLAGS,
        )
        w, h = r.stdout.strip().split("x")
        return int(w), int(h)
    except Exception:
        return 0, 0


def probe_embedded_subs(video_path: str) -> list[dict]:
    """Return list of embedded subtitle streams: [{'index', 'lang', 'title', 'codec'}]."""
    try:
        r = subprocess.run(
            [ffprobe_path, "-v", "error", "-select_streams", "s",
             "-show_entries", "stream=index,codec_name:stream_tags=language,title",
             "-of", "default=noprint_wrappers=1", video_path],
            capture_output=True, text=True, timeout=15, **_WIN_FLAGS,
        )
        tracks: list[dict] = []
        cur: dict = {}
        for line in r.stdout.splitlines():
            line = line.strip()
            if line.startswith("[STREAM]"):
                cur = {}
            elif line.startswith("[/STREAM]"):
                if cur:
                    tracks.append(cur)
            elif "=" in line:
                k, v = line.split("=", 1)
                if k == "index":
                    cur["index"] = int(v)
                elif k == "codec_name":
                    cur["codec"] = v
                elif k == "TAG:language":
                    cur["lang"] = v
                elif k == "TAG:title":
                    cur["title"] = v
        return tracks
    except Exception:
        return []


def extract_embedded_sub(video_path: str, stream_index: int, out_path: str) -> str:
    """Extract embedded sub stream to SRT file. Returns out_path."""
    cmd = [ffmpeg_path, "-y", "-i", video_path,
           "-map", f"0:{stream_index}", "-c:s", "srt", out_path]
    proc = tracked_run(cmd, str(uuid.uuid4()), capture_output=True, text=True,
                       timeout=120, **_WIN_FLAGS)
    if proc.returncode != 0:
        raise RuntimeError(f"sub extract failed: {proc.stderr[-1000:]}")
    return out_path


def read_sub_preview(sub_path: str, max_lines: int = 6, encoding: str = "auto") -> str:
    """Read first few text cues from SRT/VTT/ASS for UI preview."""
    encs = [encoding] if encoding and encoding != "auto" else \
        ["utf-8-sig", "utf-8", "windows-1256", "cp1252", "latin-1"]
    for enc in encs:
        try:
            with open(sub_path, "r", encoding=enc) as f:
                text = f.read(4000)
            ext = os.path.splitext(sub_path)[1].lower()
            lines: list[str] = []
            if ext in (".srt", ".vtt"):
                for ln in text.splitlines():
                    s = ln.strip()
                    if not s or s.isdigit() or "-->" in s or s.upper().startswith("WEBVTT"):
                        continue
                    lines.append(s)
                    if len(lines) >= max_lines:
                        break
            elif ext in (".ass", ".ssa"):
                for ln in text.splitlines():
                    if ln.startswith("Dialogue:"):
                        parts = ln.split(",", 9)
                        if len(parts) == 10:
                            lines.append(parts[9].strip())
                            if len(lines) >= max_lines:
                                break
            else:
                lines = text.splitlines()[:max_lines]
            return "\n".join(lines) if lines else text[:300]
        except (UnicodeDecodeError, UnicodeError):
            continue
        except Exception:
            return ""
    return ""


def _trim_srt_overlaps(text: str, gap_ms: int = 1) -> str:
    """Trim each cue's end time so it stops at the next cue's start.

    Kills the stacked-lyrics effect where 3-4 cues remain on screen because
    each line's end timestamp extends past the next line's start. Operates on
    SRT timecode lines `HH:MM:SS,mmm --> HH:MM:SS,mmm`.
    """
    pat = re.compile(
        r"(\d{2}):(\d{2}):(\d{2})[,.](\d{3})\s*-->\s*"
        r"(\d{2}):(\d{2}):(\d{2})[,.](\d{3})"
    )

    def _to_ms(h, m, s, ms) -> int:
        return ((h * 3600 + m * 60 + s) * 1000) + ms

    def _to_tc(total_ms: int) -> str:
        if total_ms < 0:
            total_ms = 0
        h, rem = divmod(total_ms, 3_600_000)
        m, rem = divmod(rem, 60_000)
        s, ms = divmod(rem, 1000)
        return f"{h:02d}:{m:02d}:{s:02d},{ms:03d}"

    matches = list(pat.finditer(text))
    if len(matches) < 2:
        return text
    # Walk backwards so earlier index replacements don't shift later spans.
    pieces = [text]
    new = text
    starts_ms = [_to_ms(int(m[5]), int(m[6]), int(m[7]), int(m[8])) for m in matches]
    # `starts_ms[i]` is the END of cue i; we want each cue i's END < START of cue i+1.
    # The cue's START is matches[i] groups 1-4. Build replacement list.
    replacements: list[tuple[int, int, str]] = []
    for i, m in enumerate(matches):
        cur_start_ms = _to_ms(int(m[1]), int(m[2]), int(m[3]), int(m[4]))
        cur_end_ms = _to_ms(int(m[5]), int(m[6]), int(m[7]), int(m[8]))
        if i + 1 < len(matches):
            next_start_ms = _to_ms(
                int(matches[i + 1][1]), int(matches[i + 1][2]),
                int(matches[i + 1][3]), int(matches[i + 1][4]),
            )
            if cur_end_ms > next_start_ms - gap_ms:
                cur_end_ms = max(cur_start_ms + 1, next_start_ms - gap_ms)
        new_line = f"{_to_tc(cur_start_ms)} --> {_to_tc(cur_end_ms)}"
        replacements.append((m.start(), m.end(), new_line))
    out: list[str] = []
    pos = 0
    for s, e, repl in replacements:
        out.append(text[pos:s])
        out.append(repl)
        pos = e
    out.append(text[pos:])
    return "".join(out)


def _shift_srt_timecodes(text: str, offset_sec: float) -> str:
    """Add `offset_sec` to every `HH:MM:SS,mmm --> HH:MM:SS,mmm` line."""
    pat = re.compile(
        r"(\d{2}):(\d{2}):(\d{2})[,.](\d{3})\s*-->\s*"
        r"(\d{2}):(\d{2}):(\d{2})[,.](\d{3})"
    )

    def _shift_tc(h: int, m: int, s: int, ms: int) -> str:
        total_ms = ((h * 3600 + m * 60 + s) * 1000 + ms) + int(offset_sec * 1000)
        if total_ms < 0:
            total_ms = 0
        h2, rem = divmod(total_ms, 3_600_000)
        m2, rem = divmod(rem, 60_000)
        s2, ms2 = divmod(rem, 1000)
        return f"{h2:02d}:{m2:02d}:{s2:02d},{ms2:03d}"

    def repl(m):
        a = _shift_tc(int(m[1]), int(m[2]), int(m[3]), int(m[4]))
        b = _shift_tc(int(m[5]), int(m[6]), int(m[7]), int(m[8]))
        return f"{a} --> {b}"

    return pat.sub(repl, text)


_ASS_STYLE_FIELDS = [
    "Name", "Fontname", "Fontsize", "PrimaryColour", "SecondaryColour",
    "OutlineColour", "BackColour", "Bold", "Italic", "Underline", "StrikeOut",
    "ScaleX", "ScaleY", "Spacing", "Angle", "BorderStyle", "Outline", "Shadow",
    "Alignment", "MarginL", "MarginR", "MarginV", "Encoding",
]


def _convert_to_ass(sub_path: str) -> str | None:
    """Use ffmpeg to convert SRT/VTT → temp .ass. Returns path or None."""
    out = tempfile.NamedTemporaryFile(suffix=".ass", delete=False)
    out.close()
    try:
        r = subprocess.run(
            [ffmpeg_path, "-y", "-i", sub_path, out.name],
            capture_output=True, timeout=30, **_WIN_FLAGS,
        )
        if r.returncode == 0 and os.path.getsize(out.name) > 0:
            return out.name
    except Exception:
        pass
    try:
        os.remove(out.name)
    except Exception:
        pass
    return None


def _patch_ass_style(ass_path: str, overrides: dict) -> None:
    """Rewrite the V4+ Default Style line with our overrides.

    libass's `force_style` doesn't enable ASS_OVERRIDE_BIT_POSITION via ffmpeg,
    so Alignment/MarginV overrides are silently ignored. Patching the style
    line directly bypasses that bug.
    """
    if not overrides:
        return
    try:
        with open(ass_path, "r", encoding="utf-8") as f:
            text = f.read()
    except Exception:
        return

    lines = text.splitlines()
    fmt_idx = -1
    fields: list[str] = []
    for i, ln in enumerate(lines):
        s = ln.strip()
        if s.lower().startswith("format:") and fmt_idx == -1 and "Name" in s:
            fmt_idx = i
            fields = [f.strip() for f in s.split(":", 1)[1].split(",")]
            continue
        if fmt_idx >= 0 and s.lower().startswith("style:"):
            values = [v.strip() for v in s.split(":", 1)[1].split(",")]
            if len(values) != len(fields):
                continue
            row = dict(zip(fields, values))
            if row.get("Name", "").lower() != "default":
                continue
            for k, v in overrides.items():
                # Match field name case-insensitively against the format row.
                for fk in fields:
                    if fk.lower() == k.lower():
                        row[fk] = str(v)
                        break
            new_vals = [row[f] for f in fields]
            lines[i] = "Style: " + ",".join(new_vals)
            break

    try:
        with open(ass_path, "w", encoding="utf-8") as f:
            f.write("\n".join(lines))
    except Exception:
        pass


def _style_overrides_for_ass(
    font: str | None, size: int | None, color: str | None,
    outline: int | None, outline_color: str | None, back_color: str | None,
    bold: bool, italic: bool, alignment: int | None, margin_v: int | None,
    border_style: int | None, shadow: int | None,
) -> dict:
    """Build dict of Style-line field overrides matching the ASS Format row.

    Values written verbatim into the comma-separated Style line; colors are
    raw `&HAABBGGRR` and bool fields use ASS's `-1` (true) / `0` (false).
    """
    o: dict = {}
    if font:
        o["Fontname"] = font
    if size:
        o["Fontsize"] = size
    if color:
        c = _hex_to_ass_color(color)
        if c:
            o["PrimaryColour"] = c
    if outline_color:
        c = _hex_to_ass_color(outline_color)
        if c:
            o["OutlineColour"] = c
    if back_color:
        c = _hex_to_ass_color(back_color)
        if c:
            o["BackColour"] = c
    if bold:
        o["Bold"] = -1
    if italic:
        o["Italic"] = -1
    if outline is not None:
        o["Outline"] = outline
    if shadow is not None:
        o["Shadow"] = shadow
    if border_style is not None:
        o["BorderStyle"] = border_style
    if alignment is not None and 1 <= alignment <= 9:
        o["Alignment"] = alignment
    if margin_v is not None and (alignment is None or alignment not in (4, 5, 6)):
        o["MarginV"] = margin_v
    return o


def _prepare_sub_file(
    sub_path: str, encoding: str, time_offset: float,
    trim_overlaps: bool = False,
) -> tuple[str, str | None]:
    """Return (path_to_use, tempfile_to_cleanup_or_None).

    Re-encode to UTF-8 + apply time-offset + optional overlap trim.
    """
    needs_reencode = encoding and encoding not in ("auto", "utf-8")
    needs_shift = abs(time_offset) > 0.0005
    if not (needs_reencode or needs_shift or trim_overlaps):
        return sub_path, None
    ext = os.path.splitext(sub_path)[1].lower()
    if ext not in (".srt", ".vtt"):
        # ASS shift / re-encoding skipped — ffmpeg/libass handles native
        return sub_path, None
    encs = [encoding] if needs_reencode else \
        ["utf-8-sig", "utf-8", "windows-1256", "cp1252", "latin-1"]
    text: str | None = None
    for enc in encs:
        try:
            with open(sub_path, "r", encoding=enc) as f:
                text = f.read()
            break
        except (UnicodeDecodeError, UnicodeError):
            continue
    if text is None:
        return sub_path, None
    if needs_shift:
        text = _shift_srt_timecodes(text, time_offset)
    if trim_overlaps:
        text = _trim_srt_overlaps(text)
    tmp = tempfile.NamedTemporaryFile(
        mode="w", encoding="utf-8", suffix=ext, delete=False
    )
    tmp.write(text)
    tmp.close()
    return tmp.name, tmp.name


def _parse_progress_time(line: str) -> float | None:
    """Parse `out_time_ms=` or `out_time=` from ffmpeg -progress output."""
    if line.startswith("out_time_ms="):
        try:
            return int(line.split("=", 1)[1]) / 1_000_000.0
        except Exception:
            return None
    if line.startswith("out_time="):
        v = line.split("=", 1)[1].strip()
        m = re.match(r"(\d+):(\d+):(\d+\.?\d*)", v)
        if m:
            return int(m[1]) * 3600 + int(m[2]) * 60 + float(m[3])
    return None


def burn_subtitles(
    video_path: str,
    subtitle_path: str,
    output_path: str | None = None,
    *,
    font: str | None = None,
    font_size: int | None = None,
    font_color: str | None = None,
    outline: int | None = None,
    outline_color: str | None = None,
    back_color: str | None = None,
    bold: bool = False,
    italic: bool = False,
    alignment: int | None = None,
    margin_v: int | None = None,
    border_style: int | None = None,
    shadow: int | None = None,
    encoding: str = "auto",
    time_offset: float = 0.0,
    trim_overlaps: bool = False,
    crf: int = 18,
    preset: str = "medium",
    hw_accel: str = "none",
    cancel_check=None,
    progress_cb=None,
    info_cb=None,
) -> str:
    """Burn `subtitle_path` into `video_path`. Return output file path.

    `progress_cb(done_sec, total_sec)` called periodically.
    `cancel_check()` polled — return True to abort.
    """
    if not os.path.isfile(video_path):
        raise FileNotFoundError(video_path)
    if not os.path.isfile(subtitle_path):
        raise FileNotFoundError(subtitle_path)

    base, ext = os.path.splitext(video_path)
    if not output_path:
        output_path = f"{base}_subbed{ext or '.mp4'}"

    duration = probe_duration(video_path)
    sub_actual, sub_tmp = _prepare_sub_file(
        subtitle_path, encoding, time_offset, trim_overlaps=trim_overlaps,
    )
    extra_tmp: str | None = None

    try:
        # Convert SRT/VTT → temp ASS so we can patch the Default Style line
        # directly. ffmpeg's `force_style` does NOT enable libass's POSITION
        # override bit, so Alignment/MarginV go through this path instead.
        in_ext = os.path.splitext(sub_actual)[1].lower()
        overrides = _style_overrides_for_ass(
            font, font_size, font_color, outline, outline_color, back_color,
            bold, italic, alignment, margin_v, border_style, shadow,
        )
        if overrides:
            if in_ext in (".ass", ".ssa"):
                _patch_ass_style(sub_actual, overrides)
            elif in_ext in (".srt", ".vtt"):
                converted = _convert_to_ass(sub_actual)
                if converted:
                    _patch_ass_style(converted, overrides)
                    sub_actual = converted
                    extra_tmp = converted

        sub_filter = f"subtitles=filename='{_escape_filter_path(sub_actual)}'"
        # Keep force_style as fallback for fields the Style-line patch can't
        # cover or when conversion failed (covers font tweaks on unmodified
        # .ass inputs).
        style = _build_force_style(
            font, font_size, font_color, outline,
            outline_color=outline_color, back_color=back_color,
            bold=bold, italic=italic, alignment=None, margin_v=None,
            border_style=border_style, shadow=shadow,
        )
        if style:
            sub_filter += f":force_style='{style}'"

        if hw_accel == "nvidia":
            enc = ["-c:v", "h264_nvenc", "-preset", "p4", "-rc", "constqp",
                   "-qp", str(crf), "-b:v", "0", "-pix_fmt", "yuv420p"]
        elif hw_accel == "amd":
            enc = ["-c:v", "h264_amf", "-quality", "balanced", "-rc", "1",
                   "-qp_i", str(crf), "-qp_p", str(crf), "-qp_b", str(crf),
                   "-pix_fmt", "yuv420p"]
        elif hw_accel == "intel":
            enc = ["-c:v", "h264_qsv", "-preset", "fast",
                   "-global_quality", str(crf), "-pix_fmt", "nv12"]
        else:
            enc = ["-c:v", "libx264", "-preset", preset, "-crf", str(crf),
                   "-pix_fmt", "yuv420p"]

        # GPU decode flags before `-i`. Subtitle filter needs frames in system
        # memory, so no `-hwaccel_output_format` — ffmpeg auto-downloads to RAM
        # for libass then NVENC/AMF/QSV re-uploads for encode.
        hw_decode: list[str] = []
        if hw_accel == "nvidia":
            hw_decode = ["-hwaccel", "cuda"]
        elif hw_accel == "amd":
            hw_decode = ["-hwaccel", "d3d11va"]
        elif hw_accel == "intel":
            hw_decode = ["-hwaccel", "qsv"]

        cmd = [
            ffmpeg_path, "-y",
            *hw_decode,
            "-i", video_path,
            "-vf", sub_filter,
            *enc,
            "-c:a", "copy",
            "-progress", "pipe:1", "-nostats",
            output_path,
        ]

        if info_cb:
            try:
                info_cb(f"Requested encoder: {enc[1]} (hw_accel={hw_accel})")
            except Exception:
                pass

        job_id = str(uuid.uuid4())
        proc = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE, stderr=subprocess.PIPE,
            text=True, bufsize=1,
            encoding="utf-8", errors="replace",
            **_WIN_FLAGS,
        )
        register(job_id, proc)

        q: Queue = Queue()

        def _reader(stream, tag: str) -> None:
            try:
                for line in iter(stream.readline, ""):
                    q.put((tag, line.rstrip()))
            finally:
                try:
                    stream.close()
                except Exception:
                    pass
                q.put((tag, None))

        Thread(target=_reader, args=(proc.stdout, "out"), daemon=True).start()
        Thread(target=_reader, args=(proc.stderr, "err"), daemon=True).start()

        stderr_tail: list[str] = []
        done_streams = 0
        cancelled = False
        encoder_announced = False
        while True:
            if cancel_check and cancel_check():
                cancelled = True
                try:
                    proc.terminate()
                except Exception:
                    pass
                break
            try:
                tag, line = q.get(timeout=0.1)
            except Empty:
                if proc.poll() is not None and q.empty():
                    break
                continue
            if line is None:
                done_streams += 1
                if done_streams >= 2:
                    break
                continue
            if tag == "out" and progress_cb and duration > 0:
                t = _parse_progress_time(line)
                if t is not None:
                    try:
                        progress_cb(min(t, duration), duration)
                    except Exception:
                        pass
            elif tag == "err":
                stderr_tail.append(line)
                if len(stderr_tail) > 80:
                    del stderr_tail[:20]
                if not encoder_announced and info_cb:
                    for enc_name in ("h264_nvenc", "h264_amf", "h264_qsv", "libx264"):
                        if enc_name in line:
                            try:
                                info_cb(f"Encoder: {enc_name}")
                            except Exception:
                                pass
                            encoder_announced = True
                            break

        rc = proc.wait(timeout=10)
        unregister(job_id, proc)
        if cancelled:
            try:
                if os.path.isfile(output_path):
                    os.remove(output_path)
            except Exception:
                pass
            raise RuntimeError("Cancelled")
        if rc != 0:
            raise RuntimeError("ffmpeg failed: " + "\n".join(stderr_tail[-30:]))
        return output_path
    finally:
        for p in (sub_tmp, extra_tmp):
            if p:
                try:
                    os.remove(p)
                except Exception:
                    pass
