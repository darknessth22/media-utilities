"""Silent rotating application logger with credential masking.

Usage:
    from utils.app_logger import get_logger
    log = get_logger()
    log.error("Download failed: %s", err)

The log file is capped at 2 MB, rotated into one backup, and never shown to the
user directly — it exists for diagnostics only.  Sensitive strings (cookie paths,
session tokens, --cookies flags) are automatically redacted before writing.
"""
from __future__ import annotations

import logging
import logging.handlers
import os
import platform
import re
from pathlib import Path

# ---------------------------------------------------------------------------
# Credential masking
# ---------------------------------------------------------------------------

_MASK_PATTERNS: list[tuple[re.Pattern, str]] = [
    # --cookies /path/to/file  or  --cookies-from-browser chrome
    (re.compile(r'(--cookies(?:-from-browser)?)\s+\S+', re.IGNORECASE), r'\1 [REDACTED]'),
    # cookiefile=/path  or  cookiesfrombrowser=chrome
    (re.compile(r'(cookie(?:s?file|sfrombrowser)\s*[=:]\s*)\S+', re.IGNORECASE), r'\1[REDACTED]'),
    # Bearer / Authorization tokens
    (re.compile(r'(Authorization:\s*(?:Bearer|Basic)\s+)\S+', re.IGNORECASE), r'\1[REDACTED]'),
    # session= or token= query/form parameters
    (re.compile(r'((?:session|token|api[_-]?key)\s*[=:]\s*)[^\s&"\']+', re.IGNORECASE), r'\1[REDACTED]'),
    # Spotify client_secret
    (re.compile(r'(client_secret\s*[=:]\s*)\S+', re.IGNORECASE), r'\1[REDACTED]'),
]


def mask_credentials(text: str) -> str:
    """Redact known sensitive patterns from *text*."""
    for pattern, replacement in _MASK_PATTERNS:
        text = pattern.sub(replacement, text)
    return text


# ---------------------------------------------------------------------------
# Custom formatter that masks before writing
# ---------------------------------------------------------------------------

class _MaskingFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        formatted = super().format(record)
        return mask_credentials(formatted)


# ---------------------------------------------------------------------------
# Log file location
# ---------------------------------------------------------------------------

def _log_path() -> Path:
    system = platform.system()
    if system == "Windows":
        base = Path(os.environ.get("APPDATA", Path.home() / "AppData" / "Roaming"))
    elif system == "Darwin":
        base = Path.home() / "Library" / "Application Support"
    else:
        base = Path(os.environ.get("XDG_DATA_HOME", Path.home() / ".local" / "share"))
    log_dir = base / "media-utilities" / "logs"
    log_dir.mkdir(parents=True, exist_ok=True)
    return log_dir / "app.log"


# ---------------------------------------------------------------------------
# Singleton logger
# ---------------------------------------------------------------------------

_logger: logging.Logger | None = None


def get_log_path() -> Path:
    """Return the active log file path (creates the directory if needed)."""
    return _log_path()


def get_logger(name: str = "media_utilities") -> logging.Logger:
    """Return (and create on first call) the application logger."""
    global _logger
    if _logger is not None:
        return _logger

    logger = logging.getLogger(name)
    logger.setLevel(logging.DEBUG)

    # Avoid adding duplicate handlers if module is reloaded
    if not logger.handlers:
        handler = logging.handlers.RotatingFileHandler(
            _log_path(),
            maxBytes=2 * 1024 * 1024,  # 2 MB cap
            backupCount=1,
            encoding="utf-8",
        )
        handler.setFormatter(
            _MaskingFormatter(
                fmt="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
                datefmt="%Y-%m-%dT%H:%M:%S",
            )
        )
        logger.addHandler(handler)
        # Prevent propagation to root logger (which might write to stderr)
        logger.propagate = False

    _logger = logger
    return logger
