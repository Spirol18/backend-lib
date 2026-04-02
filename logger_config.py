"""
Centralized logging configuration for backend-lib.
Import `logger` from this module in any file that needs logging.
"""

import logging
import os
from logging.handlers import RotatingFileHandler

LOG_FILE = os.path.join(os.path.dirname(__file__), "log.txt")
LOG_LEVEL = logging.DEBUG  # Change to logging.INFO in production

# ── formatter ────────────────────────────────────────────────────────────────
_fmt = "%(asctime)s | %(levelname)-8s | %(name)s | %(message)s"
_datefmt = "%Y-%m-%d %H:%M:%S"
formatter = logging.Formatter(_fmt, datefmt=_datefmt)

# ── root logger ───────────────────────────────────────────────────────────────
_root = logging.getLogger("backend_lib")
_root.setLevel(LOG_LEVEL)

if not _root.handlers:
    # Console handler
    _console = logging.StreamHandler()
    _console.setLevel(LOG_LEVEL)
    _console.setFormatter(formatter)
    _root.addHandler(_console)

    # Rotating file handler (max 5 MB × 3 backup files)
    _file = RotatingFileHandler(LOG_FILE, maxBytes=5 * 1024 * 1024, backupCount=3, encoding="utf-8")
    _file.setLevel(LOG_LEVEL)
    _file.setFormatter(formatter)
    _root.addHandler(_file)


def get_logger(name: str) -> logging.Logger:
    """Return a child logger namespaced under 'backend_lib'."""
    return _root.getChild(name)
