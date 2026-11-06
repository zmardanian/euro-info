"""Per-user folders on each platform.

Linux    ~/.config/euro-info, ~/.local/share/euro-info, ~/.cache/euro-info (XDG)
Windows  %APPDATA%\\Euro Info, %LOCALAPPDATA%\\Euro Info, %LOCALAPPDATA%\\Euro Info\\Cache
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

IS_WINDOWS = sys.platform.startswith("win")
_overrides: dict[str, Path] = {}


def configure(config: str | Path | None = None, data: str | Path | None = None,
              cache: str | Path | None = None) -> None:
    """Use explicit folders instead of the platform defaults (portable installs, tests)."""
    for name, value in (("config", config), ("data", data), ("cache", cache)):
        if value is not None:
            _overrides[name] = Path(value)


def _windows(variable: str, *parts: str) -> Path:
    base = os.environ.get(variable) or str(Path.home() / "AppData" / ("Roaming" if variable == "APPDATA" else "Local"))
    return Path(base, "Euro Info", *parts)


def _base(variable: str, fallback: str) -> Path:
    value = os.environ.get(variable, "").strip()
    return Path(value) if value and Path(value).is_absolute() else Path.home() / fallback


def config_dir() -> Path:
    if "config" in _overrides:
        return _overrides["config"]
    if IS_WINDOWS and "XDG_CONFIG_HOME" not in os.environ:
        return _windows("APPDATA")
    return _base("XDG_CONFIG_HOME", ".config") / "euro-info"


def data_dir() -> Path:
    if "data" in _overrides:
        return _overrides["data"]
    if IS_WINDOWS and "XDG_DATA_HOME" not in os.environ:
        return _windows("LOCALAPPDATA")
    return _base("XDG_DATA_HOME", ".local/share") / "euro-info"


def cache_dir() -> Path:
    if "cache" in _overrides:
        return _overrides["cache"]
    if IS_WINDOWS and "XDG_CACHE_HOME" not in os.environ:
        return _windows("LOCALAPPDATA", "Cache")
    return _base("XDG_CACHE_HOME", ".cache") / "euro-info"


def settings_file() -> Path:
    return config_dir() / "settings.conf"


def legacy_settings_file() -> Path:
    """Where Euro Info 1.x-2.x kept its settings on Linux (QSettings 'EuroInfo/EuroInfo')."""
    return _base("XDG_CONFIG_HOME", ".config") / "EuroInfo" / "EuroInfo.conf"


def log_file() -> Path:
    return cache_dir() / "euro-info.log"


def ensure(path: Path) -> Path:
    path.mkdir(parents=True, exist_ok=True)
    return path
