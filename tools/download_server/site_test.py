"""Check which sites download from this machine's IP address.

Run it on a candidate host before renting it for longer (see
specs/002-downloader-server/spec.md). Needs yt-dlp, FFmpeg, Deno and
videl_dl.py (the Android module, for Spotify) next to this file.

    python3 site_test.py -4            # over IPv4
    python3 site_test.py -6            # over IPv6
    python3 site_test.py -4 --burst 20 # plus 20 YouTube look-ups in a row
"""
import os
import shutil
import sys
import tempfile
import time

import yt_dlp

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import videl_dl  # noqa: E402

SITES = [
    ("YouTube", "https://www.youtube.com/watch?v=jNQXAC9IVRw"),
    ("YouTube Music", "https://music.youtube.com/watch?v=jNQXAC9IVRw"),
    ("TikTok", "https://www.tiktok.com/@ceciliaconejo/video/7668090902816017671"),
    ("Instagram", "https://www.instagram.com/p/aye83DjauH/"),
    ("Facebook", "https://www.facebook.com/video.php?v=274175099429670"),
    ("X", "https://twitter.com/captainamerica/status/719944021058060289"),
    ("LinkedIn", "https://www.linkedin.com/posts/mishalkhawaja_sendinblueviews-toronto-digitalmarketing-ugcPost-6850898786781339649-mM20"),
    ("Twitch", "https://clips.twitch.tv/FaintLightGullWholeWheat"),
    ("YouTube 1080p (speed)", "https://www.youtube.com/watch?v=aqz-KE-bpKQ"),
]
SPOTIFY = "https://open.spotify.com/track/4uLU6hMCjMI75M1A2tKUQC"
# What the server will ask for: H.264 up to 1080p, so nothing needs re-encoding.
FMT = "bv*[height<=1080][vcodec^=avc1]+ba[ext=m4a]/b[height<=1080]/bv*[height<=1080]+ba/b"


class _Quiet:
    def debug(self, msg): pass
    def warning(self, msg): pass
    def error(self, msg): pass


def _first_line(e):
    return str(e).replace("ERROR: ", "").splitlines()[0][:160]


def fetch(url, out_dir, source, fmt=FMT, audio=False):
    """Download one item; return (seconds, bytes, path)."""
    opts = {"format": fmt, "outtmpl": os.path.join(out_dir, "%(id)s.%(ext)s"), "noplaylist": True,
            "merge_output_format": "mp4", "source_address": source, "logger": _Quiet(),
            "quiet": True, "no_warnings": True, "retries": 3}
    if audio:
        opts["postprocessors"] = [{"key": "FFmpegExtractAudio", "preferredcodec": "mp3"}]
        del opts["merge_output_format"]
    start = time.time()
    with yt_dlp.YoutubeDL(opts) as ydl:
        ydl.download([url])
    files = [os.path.join(out_dir, f) for f in os.listdir(out_dir)]
    path = max(files, key=os.path.getsize)
    return time.time() - start, os.path.getsize(path), path


def report(name, fn):
    try:
        secs, size, path = fn()
        print(f"OK    {name:24} {size / 1e6:7.1f} MB  {secs:6.1f} s  {size / 1e6 / secs:6.1f} MB/s", flush=True)
        return path
    except Exception as e:
        print(f"FAIL  {name:24} {_first_line(e)}", flush=True)


def burst(count, source):
    """Look up `count` different YouTube videos in a row; stop at the first refusal."""
    with yt_dlp.YoutubeDL({"extract_flat": True, "quiet": True, "logger": _Quiet(), "source_address": source}) as ydl:
        ids = [e["id"] for e in ydl.extract_info(f"ytsearch{count}:official music video", download=False)["entries"]]
    ok = 0
    with yt_dlp.YoutubeDL({"quiet": True, "logger": _Quiet(), "source_address": source}) as ydl:
        for vid in ids:
            try:
                ydl.extract_info(f"https://www.youtube.com/watch?v={vid}", download=False)
                ok += 1
            except Exception as e:
                print(f"FAIL  burst after {ok} look-ups: {_first_line(e)}", flush=True)
                return
    print(f"OK    burst: {ok} of {len(ids)} YouTube look-ups in a row", flush=True)


def main():
    source = "::" if "-6" in sys.argv else "0.0.0.0"
    print(f"yt-dlp {yt_dlp.version.__version__}, IPv{'6' if source == '::' else '4'}", flush=True)
    keep = "/root/speed.mp4"
    for name, url in SITES:
        out = tempfile.mkdtemp()
        path = report(name, lambda: fetch(url, out, source))
        if path and "speed" in name:
            shutil.move(path, keep)   # kept to time the copy to your PC
        shutil.rmtree(out, ignore_errors=True)

    def spotify():
        _, tracks = videl_dl.spotify_tracks(SPOTIFY)
        out = tempfile.mkdtemp()
        try:
            return fetch(tracks[0]["query"], out, source, fmt="ba/b", audio=True)
        finally:
            shutil.rmtree(out, ignore_errors=True)
    report("Spotify (song via YouTube)", spotify)

    if "--burst" in sys.argv:
        burst(int(sys.argv[sys.argv.index("--burst") + 1]), source)


if __name__ == "__main__":
    main()
