"""Generate + sign the Videl onedir file manifest for delta updates.

Walks a built onedir tree (dist/Videl/), records every file's path (POSIX-style,
relative to the tree root), sha256 and size, then signs the canonical JSON with
the Ed25519 private key (same key as tools/sign_installer.py).

Manifest schema (videl-files.manifest.json):
    {
      "version": "x.y.z",
      "files": [ {"path": "Videl.exe", "sha256": "<hex>", "size": <int>}, ... ],
      "sig": "<urlsafe-b64 ed25519 sig over compact JSON of {version, files}>"
    }

`files` is sorted by path so the signed payload is reproducible. The in-app
updater (core/updater.py) rebuilds the same canonical form
(json.dumps sort_keys=True, separators=(",",":")) before Ed25519.verify().

Usage:
    python tools/gen_manifest.py dist/Videl --version 3.7.0 \
        --out videl-files.manifest.json
    # In CI (PEM contents, not a path):
    python tools/gen_manifest.py dist/Videl --version "$V" \
        --priv-key "$VIDEL_PRIV_KEY_PEM" --out artifacts/clean/videl-files.manifest.json
"""
from __future__ import annotations

import argparse
import base64
import hashlib
import json
import os
import sys

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey


_HERE = os.path.dirname(os.path.abspath(__file__))
_DEFAULT_PRIV_PATH = os.path.join(_HERE, "private_key.pem")


def _b64u(b: bytes) -> str:
    return base64.urlsafe_b64encode(b).rstrip(b"=").decode("ascii")


def _sha256_file(path: str) -> tuple[str, int]:
    h = hashlib.sha256()
    size = 0
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
            size += len(chunk)
    return h.hexdigest(), size


def _load_priv(pem_text_or_none: str | None) -> Ed25519PrivateKey:
    if pem_text_or_none:
        priv = serialization.load_pem_private_key(
            pem_text_or_none.encode("utf-8"), password=None
        )
    else:
        if not os.path.isfile(_DEFAULT_PRIV_PATH):
            raise SystemExit(
                f"Private key not found: {_DEFAULT_PRIV_PATH}\n"
                f"Pass --priv-key with the Ed25519 PEM contents."
            )
        with open(_DEFAULT_PRIV_PATH, "rb") as f:
            priv = serialization.load_pem_private_key(f.read(), password=None)
    if not isinstance(priv, Ed25519PrivateKey):
        raise SystemExit("Private key is not Ed25519.")
    return priv


def build_manifest(tree_dir: str, version: str) -> dict:
    """Build the unsigned {version, files} payload from a onedir tree."""
    files: list[dict] = []
    for root, _dirs, names in os.walk(tree_dir):
        for name in names:
            abs_path = os.path.join(root, name)
            rel = os.path.relpath(abs_path, tree_dir).replace(os.sep, "/")
            sha, size = _sha256_file(abs_path)
            files.append({"path": rel, "sha256": sha, "size": size})
    files.sort(key=lambda e: e["path"])
    return {"version": version.lstrip("vV").strip(), "files": files}


def main() -> int:
    p = argparse.ArgumentParser(
        description="Generate + sign the Videl delta-update file manifest"
    )
    p.add_argument("tree", help="Built onedir tree, e.g. dist/Videl")
    p.add_argument("--version", required=True, help="Semver, e.g. 3.7.0")
    p.add_argument("--priv-key", default=None,
                   help="Ed25519 PEM contents (NOT a path). Default: tools/private_key.pem")
    p.add_argument("--out", default="videl-files.manifest.json",
                   help="Manifest output path.")
    args = p.parse_args()

    if not os.path.isdir(args.tree):
        print(f"Tree not found: {args.tree}", file=sys.stderr)
        return 2

    payload = build_manifest(args.tree, args.version)
    payload_bytes = json.dumps(
        payload, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")
    priv = _load_priv(args.priv_key)
    sig = priv.sign(payload_bytes)
    manifest = {**payload, "sig": _b64u(sig)}

    out_dir = os.path.dirname(os.path.abspath(args.out))
    os.makedirs(out_dir, exist_ok=True)
    with open(args.out, "w", encoding="utf-8") as f:
        json.dump(manifest, f, indent=2)

    total = sum(e["size"] for e in payload["files"])
    print(f"Wrote {args.out}")
    print(f"  version: {payload['version']}")
    print(f"  files:   {len(payload['files'])}")
    print(f"  total:   {total / 1e6:.1f} MB")
    return 0


if __name__ == "__main__":
    sys.exit(main())
