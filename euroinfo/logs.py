"""Application log in ~/.cache/euro-info/euro-info.log (rotated, about 3 MB total)."""
from __future__ import annotations

import logging
import logging.handlers
import sys

from . import __version__, paths

_configured = False


def setup(verbose: bool = False) -> logging.Logger:
    global _configured
    logger = logging.getLogger("euroinfo")
    if _configured:
        return logger
    _configured = True
    logger.setLevel(logging.DEBUG if verbose else logging.INFO)
    formatter = logging.Formatter("%(asctime)s %(levelname)-7s %(name)s: %(message)s")
    try:
        paths.ensure(paths.cache_dir())
        handler = logging.handlers.RotatingFileHandler(
            paths.log_file(), maxBytes=1_000_000, backupCount=2, encoding="utf-8")
        handler.setFormatter(formatter)
        logger.addHandler(handler)
    except OSError:
        pass
    if verbose or sys.stderr is not None and sys.stderr.isatty():
        console = logging.StreamHandler(sys.stderr)
        console.setFormatter(formatter)
        console.setLevel(logging.DEBUG if verbose else logging.WARNING)
        logger.addHandler(console)
    logger.info("Euro Info %s starting", __version__)
    return logger


def get(name: str) -> logging.Logger:
    return logging.getLogger(f"euroinfo.{name}")
