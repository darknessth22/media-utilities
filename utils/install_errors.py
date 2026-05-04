"""Classify pip-install failure text into actionable user-facing messages."""
from __future__ import annotations

from core.i18n import tr


def classify(last_error: str | None, *, target: str = "", required_mb: int = 0) -> str:
    text = (last_error or "").lower()
    if not text:
        return tr("install_error_generic").format(error="unknown")
    if any(k in text for k in (
        "could not resolve", "temporary failure", "name or service",
        "connection", "timed out", "timeout", "ssl", "proxy",
        "network is unreachable", "failed to establish",
    )):
        return tr("install_error_network")
    if any(k in text for k in ("no space left", "disk full", "errno 28")):
        return tr("install_error_disk").format(
            required_mb=required_mb, target=target or "?"
        )
    if any(k in text for k in (
        "permission denied", "errno 13", "access is denied", "winerror 5",
    )):
        return tr("install_error_permission").format(target=target or "?")
    return tr("install_error_generic").format(error=(last_error or "")[:200])
