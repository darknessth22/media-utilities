"""Upload content-addressed blobs for delta updates to sharded blob-store releases.

For each unique non-empty file in a built onedir tree, the blob is uploaded as a
release asset named by its sha256. Blobs are sharded across 16 rolling releases
`files-store-0` ... `files-store-f`, keyed by the first hex char of the sha —
GitHub caps a single release at 1000 assets and a full build has ~2400+ unique
blobs. Identical content dedupes to one blob; blobs already present in their
shard are skipped, so each release only uploads what actually changed.

Rate limits: the default Actions GITHUB_TOKEN allows ~1000 requests/hour, which
the first full seed (~2400 uploads) exceeds. On a rate-limit error the uploader
retries with backoff, and if still blocked it exits 0 with a warning — the build
still ships and the remaining blobs upload on the next release run (the updater
falls back to the full installer for any blob not yet seeded). Set GH_TOKEN to a
PAT (5000 requests/hour) to seed the whole store in a single run.

Shard releases are created `--prerelease --latest=false` so they never shadow
the real version release. 0-byte files are skipped (GitHub rejects empty
assets); the updater recreates them empty.

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
import time

_SHARD_CHARS = "0123456789abcdef"
_BATCH = 40          # blobs per `gh release upload` invocation
_MAX_RETRIES = 3     # per-batch retries on a rate-limit error
_BACKOFF_SEC = 90    # base backoff; grows linearly per retry


class RateLimited(Exception):
    """Raised when GitHub rate limits persist past all retries."""


class ShardFull(Exception):
    """Raised when a shard release has hit GitHub's 1000-asset cap."""


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


def _is_rate_limit(res: subprocess.CompletedProcess) -> bool:
    blob = ((res.stdout or "") + (res.stderr or "")).lower()
    return res.returncode != 0 and ("rate limit" in blob or "http 403" in blob)


def _is_asset_cap(res: subprocess.CompletedProcess) -> bool:
    """HTTP 422 with 'file_count limited' means the shard release hit 1000 assets."""
    blob = ((res.stdout or "") + (res.stderr or "")).lower()
    return res.returncode != 0 and ("http 422" in blob or "file_count limited" in blob)


def _ensure_release(repo: str, tag: str) -> None:
    if _gh(["release", "view", tag], repo).returncode == 0:
        return
    print(f"Creating blob-store shard release '{tag}'...")
    res = _gh([
        "release", "create", tag,
        "--title", f"Videl delta-update blob store ({tag})",
        "--notes", "Content-addressed blobs for in-app delta updates. Do not delete.",
        "--prerelease", "--latest=false",
    ], repo)
    if res.returncode != 0:
        print(res.stdout, res.stderr, file=sys.stderr)
        raise SystemExit(f"Failed to create blob-store release '{tag}'.")


def _existing_assets(repo: str, tag: str) -> set[str]:
    res = _gh(["release", "view", tag,
               "--json", "assets", "--jq", ".assets[].name"], repo)
    if res.returncode != 0:
        return set()
    return {ln.strip() for ln in res.stdout.splitlines() if ln.strip()}


def _upload_batch(repo: str, tag: str, paths: list[str]) -> None:
    """Upload one batch, retrying on rate limits. --clobber keeps it idempotent."""
    for attempt in range(_MAX_RETRIES):
        res = _gh(["release", "upload", tag, "--clobber", *paths], repo)
        if res.returncode == 0:
            return
        if _is_asset_cap(res):
            raise ShardFull(tag)
        if _is_rate_limit(res):
            if attempt < _MAX_RETRIES - 1:
                wait = _BACKOFF_SEC * (attempt + 1)
                print(f"    {tag}: rate limited — retrying in {wait}s "
                      f"(attempt {attempt + 2}/{_MAX_RETRIES})...")
                time.sleep(wait)
                continue
            raise RateLimited()
        print(res.stdout, res.stderr, file=sys.stderr)
        raise SystemExit(f"Blob upload to '{tag}' failed.")


def _upload_shard(repo: str, tag: str, missing: dict[str, str]) -> None:
    staging = tempfile.mkdtemp(prefix=f"videl-blobs-{tag}-")
    try:
        items = list(missing.items())
        for i in range(0, len(items), _BATCH):
            batch = items[i:i + _BATCH]
            paths: list[str] = []
            for sha, src in batch:
                dst = os.path.join(staging, sha)  # asset name == sha256
                shutil.copyfile(src, dst)
                paths.append(dst)
            _upload_batch(repo, tag, paths)
            print(f"    {tag}: uploaded {min(i + _BATCH, len(items))}/{len(items)}")
    finally:
        shutil.rmtree(staging, ignore_errors=True)


def main() -> int:
    p = argparse.ArgumentParser(description="Upload sharded content-addressed delta blobs")
    p.add_argument("tree", help="Built onedir tree, e.g. dist/Videl")
    p.add_argument("--repo", required=True, help="owner/name")
    args = p.parse_args()

    if not os.path.isdir(args.tree):
        print(f"Tree not found: {args.tree}", file=sys.stderr)
        return 2

    # Map sha -> one source file (dedupes identical content within the tree).
    # 0-byte files are skipped: GitHub's upload API rejects empty assets
    # ("HTTP 400: Bad Content-Length"). The updater recreates them empty.
    by_sha: dict[str, str] = {}
    skipped_empty = 0
    for root, _dirs, names in os.walk(args.tree):
        for name in names:
            ap = os.path.join(root, name)
            if os.path.getsize(ap) == 0:
                skipped_empty += 1
                continue
            by_sha.setdefault(_sha256(ap), ap)
    if skipped_empty:
        print(f"Skipped {skipped_empty} empty (0-byte) file(s) — no blob needed.")
    print(f"Tree has {len(by_sha)} unique blobs to distribute across 16 shards.")

    total_uploaded = 0
    full_shards: list[str] = []
    try:
        for char in _SHARD_CHARS:
            tag = f"files-store-{char}"
            shard = {sha: src for sha, src in by_sha.items() if sha[0] == char}
            if not shard:
                continue
            _ensure_release(args.repo, tag)
            have = _existing_assets(args.repo, tag)
            missing = {sha: src for sha, src in shard.items() if sha not in have}
            print(f"  {tag}: {len(shard)} blobs, {len(have)} present, {len(missing)} new")
            if missing:
                try:
                    _upload_shard(args.repo, tag, missing)
                    total_uploaded += len(missing)
                except ShardFull:
                    full_shards.append(tag)
                    print(f"  WARNING: {tag} has hit GitHub's 1000-asset cap — "
                          f"skipping remaining blobs for this shard. Delta updates "
                          f"fall back to full installer for blobs in this shard.")
    except RateLimited:
        print(f"\nWARNING: GitHub rate limit hit after {total_uploaded} upload(s) "
              f"this run. Blob store is PARTIALLY seeded — remaining blobs upload "
              f"on the next release run (idempotent skip). Delta updates fall back "
              f"to the full installer for any blob not yet present. To seed the "
              f"whole store in one run, set GH_TOKEN to a PAT (5000 req/hour).")
        return 0

    if full_shards:
        print(f"\nWARNING: {len(full_shards)} shard(s) are full: {', '.join(full_shards)}. "
              f"Consider increasing shard count (SHARD_CHARS) to spread blobs thinner.")

    print(f"Blob upload complete. {total_uploaded} new blob(s) uploaded.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
