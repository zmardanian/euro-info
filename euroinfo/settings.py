"""One settings store for the whole app: ~/.config/euro-info/settings.conf.

Euro Info 1.x-2.x kept settings in ~/.config/EuroInfo/EuroInfo.conf. On first
start, those values are copied here once; the old file is left untouched.
"""
from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QSettings

from . import logs, paths

log = logs.get("settings")
_store: QSettings | None = None

DEFAULTS = {
    "interface_language": "en",
    "display_mode": "standard",
    "compact_layout": True,
    "large_reading_text": False,
    "article_images_enabled": False,
    "coverage_region": "ALL",
    "news_focus_country": "AUTO",
    "refresh_minutes": 15,
    "ai_model": "auto",
    "ai_profile": "balanced",
    "ai_keep_alive": "10m",
    "ai_reading_size": 18,
    "ai_stop_on_exit": True,
    "translation_provider": "",  # "", "off", "local" or "google"
    "check_updates": True,
    "focus_mode": False,
    "personalise": True,
    "notify_watches": True,
    "catalogue_version": 0,
}


def _migrate(store: QSettings) -> None:
    legacy = paths.legacy_settings_file()
    if store.value("migrated_from_legacy", False, type=bool) or not legacy.is_file():
        return
    old = QSettings(str(legacy), QSettings.Format.IniFormat)
    copied = 0
    for key in old.allKeys():
        if not store.contains(key):
            store.setValue(key, old.value(key))
            copied += 1
    store.setValue("migrated_from_legacy", True)
    store.sync()
    log.info("Copied %d settings from %s", copied, legacy)


def get() -> QSettings:
    global _store
    if _store is None:
        paths.ensure(paths.config_dir())
        _store = QSettings(str(paths.settings_file()), QSettings.Format.IniFormat)
        _migrate(_store)
    return _store


def use_file(path: str | Path | None) -> QSettings | None:
    """Point the app at another settings file (tests) or reset with None."""
    global _store
    _store = None if path is None else QSettings(str(path), QSettings.Format.IniFormat)
    return _store


def text(key: str) -> str:
    return str(get().value(key, DEFAULTS.get(key, "")) or "")


def flag(key: str) -> bool:
    return bool(get().value(key, DEFAULTS.get(key, False), type=bool))


def number(key: str) -> int:
    try:
        return int(get().value(key, DEFAULTS.get(key, 0), type=int))
    except (TypeError, ValueError):
        return int(DEFAULTS.get(key, 0))


def put(key: str, value) -> None:
    get().setValue(key, value)
