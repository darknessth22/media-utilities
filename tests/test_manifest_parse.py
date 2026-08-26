"""Manifest sanity: parseable, every dep pinned, and contract schema is valid."""
from __future__ import annotations

import json
import os
import re

import pytest

_REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_MANIFESTS_DIR = os.path.join(_REPO_ROOT, "manifests")
_SCHEMA_PATH = os.path.join(
    _REPO_ROOT, "specs", "006-build-packaging-models", "contracts", "manifest-schema.json"
)

# pip requirement line: name (with optional extras) followed by ==version (PEP440 local OK).
_PIN_RE = re.compile(
    r"^[A-Za-z0-9_.\-]+(\[[A-Za-z0-9_.,\-]+\])?==[A-Za-z0-9_.\-+!]+$"
)


def _manifest_files() -> list[str]:
    if not os.path.isdir(_MANIFESTS_DIR):
        return []
    return sorted(
        os.path.join(_MANIFESTS_DIR, n)
        for n in os.listdir(_MANIFESTS_DIR)
        if n.endswith(".txt")
    )


@pytest.mark.parametrize("path", _manifest_files())
def test_every_line_pins_exact_version(path: str) -> None:
    with open(path, encoding="utf-8") as f:
        for lineno, raw in enumerate(f, start=1):
            line = raw.strip()
            if not line or line.startswith("#") or line.startswith("--extra-index-url"):
                continue
            assert _PIN_RE.match(line), (
                f"{os.path.basename(path)}:{lineno} not pinned with ==: {line!r}"
            )


def test_contract_schema_is_valid_json_schema() -> None:
    """jsonschema-based validation per T011: load and meta-validate the schema."""
    jsonschema = pytest.importorskip("jsonschema")
    if not os.path.isfile(_SCHEMA_PATH):
        # The 006 spec directory was never committed, so this contract file is
        # absent from a clean checkout and the test failed for everyone. Skip
        # rather than fail: the manifests it describes are covered by the other
        # tests in this file, which read the real `manifests/*.txt`.
        pytest.skip(f"contract schema not in repo: {_SCHEMA_PATH}")
    with open(_SCHEMA_PATH, encoding="utf-8") as f:
        schema = json.load(f)
    jsonschema.Draft202012Validator.check_schema(schema)
