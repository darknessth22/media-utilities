"""Sign a Videl installer build.

Reads the Ed25519 private key from tools/private_key.pem (matching the
public half baked into core/_signing.py), hashes the installer, and writes
a `<installer>.sig.json` next to it.

Manifest schema:
    {
        "sha256": "<hex>",
        "size":   <int>,
        "version": "x.y.z",
        "sig":    "<urlsafe-b64 ed25519 signature>"
    }

Signature is over the compact JSON of {sha256, size, version} with sorted keys
and (",", ":") separators — the verifier in core/updater.py reproduces the
same canonical form before calling Ed25519.verify().

Usage:
    python tools/sign_installer.py <installer_path> --version 1.2.3
    # In CI:
    python tools/sign_installer.py Output/Videl_Setup.exe --version "$VERSION"
        --priv-key "$VIDEL_PRIV_KEY_PEM"   # contents, not path

If --priv-key is omitted, falls back to tools/private_key.pem.
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
                f"Private key not found at: {_DEFAULT_PRIV_PATH}\n"
                f"Pass --priv-key with the PEM contents, or generate one with `python -c \"from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey; from cryptography.hazmat.primitives import serialization; print(Ed25519PrivateKey.generate().private_bytes(serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8, serialization.NoEncryption()).decode())\"`."
            )
        with open(_DEFAULT_PRIV_PATH, "rb") as f:
            priv = serialization.load_pem_private_key(f.read(), password=None)
    if not isinstance(priv, Ed25519PrivateKey):
        raise SystemExit("Private key is not Ed25519.")
    return priv


def main() -> int:
    p = argparse.ArgumentParser(description="Sign a Videl installer")
    p.add_argument("installer", help="Path to Videl_Setup.exe")
    p.add_argument("--version", required=True, help="Semver, e.g. 1.2.3")
    p.add_argument("--priv-key", default=None,
                   help="PEM contents (NOT a path). Default: tools/private_key.pem")
    p.add_argument("--out", default=None,
                   help="Manifest output path. Default: <installer>.sig.json")
    args = p.parse_args()

    if not os.path.isfile(args.installer):
        print(f"Installer not found: {args.installer}", file=sys.stderr)
        return 2

    priv = _load_priv(args.priv_key)

    sha256, size = _sha256_file(args.installer)
    payload = {
        "sha256": sha256,
        "size": size,
        "version": args.version.lstrip("vV").strip(),
    }
    payload_bytes = json.dumps(payload, sort_keys=True,
                               separators=(",", ":")).encode("utf-8")
    sig = priv.sign(payload_bytes)

    manifest = {**payload, "sig": _b64u(sig)}
    out_path = args.out or (args.installer + ".sig.json")
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(manifest, f, indent=2)

    print(f"Wrote {out_path}")
    print(f"  sha256:  {sha256}")
    print(f"  size:    {size}")
    print(f"  version: {payload['version']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
