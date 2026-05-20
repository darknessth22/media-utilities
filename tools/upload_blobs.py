"""Upload content-addressed blobs for delta updates to the 'files-store' release.

For each unique file in a built onedir tree, the blob is uploaded as a release
asset named by its sha256. Identical content (across files or across versions)
dedupes to a single blob. Blobs already present on the rolling 'files-store'
GitHub Release are skipped — so each release only uploads what actually changed.

The 'files-store' release is created on first run, marked --latest=false so it
never shadows the real version release that the updater queries.

Requires the `gh` CLI authenticated — GitHub Actions provides GITHUB_TOKEN; set
it as GH_TOKEN in the step env.

Usage:
    python tools/upload_blobs.py dist/Videl --repo darknessth22/media-utilities
"""
from __future__ import annotations

import argparse
import hashlib
import os
import shutil
import subprocess
import sys
import tempfile

_BLOB_TAG = "files-store"
_BATCH = 40  # blobs per `gh release upload` invocation


def _sha256(path: str) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def _gh(args: list[str], repo: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        ["gh", *args, "--repo", repo],
        capture_output=True, text=True, encoding="utf-8", errors="replace",
    )


def _ensure_release(repo: str) -> None:
    if _gh(["release", "view", _BLOB_TAG], repo).returncode == 0:
        return
    print(f"Creating rolling blob-store release '{_BLOB_TAG}'...")
    res = _gh([
        "release", "create", _BLOB_TAG,
        "--title", "Videl delta-update blob store",
        "--notes", "Content-addressed blobs for in-app delta updates. Do not delete.",
        "--latest=false",
    ], repo)
    if res.returncode != 0:
        print(res.stdout, res.stderr, file=sys.stderr)
        raise SystemExit("Failed to create blob-store release.")


def _existing_assets(repo: str) -> set[str]:
    res = _gh(["release", "view", _BLOB_TAG,
               "--json", "assets", "--jq", ".assets[].name"], repo)
    if res.returncode != 0:
        return set()
    return {ln.strip() for ln in res.stdout.splitlines() if ln.strip()}


def main() -> int:
    p = argparse.ArgumentParser(description="Upload content-addressed delta blobs")
    p.add_argument("tree", help="Built onedir tree, e.g. dist/Videl")
    p.add_argument("--repo", required=True, help="owner/name")
    args = p.parse_args()

    if not os.path.isdir(args.tree):
        print(f"Tree not found: {args.tree}", file=sys.stderr)
        return 2

    _ensure_release(args.repo)
    have = _existing_assets(args.repo)
    print(f"Blob store already holds {len(have)} blobs.")

    # Map sha -> one source file (dedupes identical content within the tree).
    by_sha: dict[str, str] = {}
    for root, _dirs, names in os.walk(args.tree):
        for name in names:
            ap = os.path.join(root, name)
            by_sha.setdefault(_sha256(ap), ap)

    missing = {sha: src for sha, src in by_sha.items() if sha not in have}
    print(f"Tree has {len(by_sha)} unique blobs; {len(missing)} new to upload.")
    if not missing:
        print("Nothing to upload.")
        return 0

    staging = tempfile.mkdtemp(prefix="videl-blobs-")
    try:
        staged: list[str] = []
        for sha, src in missing.items():
            dst = os.path.join(staging, sha)  # asset name == sha256
            shutil.copyfile(src, dst)
            staged.append(dst)

        for i in range(0, len(staged), _BATCH):
            batch = staged[i:i + _BATCH]
            res = _gh(["release", "upload", _BLOB_TAG, *batch], args.repo)
            if res.returncode != 0:
                print(res.stdout, res.stderr, file=sys.stderr)
                raise SystemExit("Blob upload failed.")
            print(f"Uploaded {min(i + _BATCH, len(staged))}/{len(staged)} blobs.")
    finally:
        shutil.rmtree(staging, ignore_errors=True)

    print("Blob upload complete.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
