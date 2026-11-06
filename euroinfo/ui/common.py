"""State shared by every window: interface language, theme and the research library."""
from __future__ import annotations

from PySide6.QtCore import QDate, QLocale, QUrl
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import QToolButton, QWidget

from ..core.i18n import tr as translate
from ..core.workspace import ReaderWorkspace
from . import icons, theme

COUNTRY_NAMES = {
    "AT": "Austria", "BE": "Belgium", "BG": "Bulgaria", "CH": "Switzerland",
    "CY": "Cyprus", "CZ": "Czechia", "DE": "Germany", "DK": "Denmark",
    "EE": "Estonia", "ES": "Spain", "FI": "Finland", "FR": "France",
    "GB": "United Kingdom", "GR": "Greece", "HR": "Croatia", "HU": "Hungary",
    "IE": "Ireland", "IT": "Italy", "LT": "Lithuania", "LU": "Luxembourg",
    "LV": "Latvia", "MT": "Malta", "NL": "Netherlands", "NO": "Norway",
    "PL": "Poland", "PT": "Portugal", "RO": "Romania", "SE": "Sweden",
    "SI": "Slovenia", "SK": "Slovakia", "EU": "Europe",
}
_LOCALES = {"en": "en_GB", "fr": "fr_FR", "de": "de_DE", "it": "it_IT", "ro": "ro_RO", "pl": "pl_PL", "es": "es_ES"}


class _State:
    language = "en"
    mode = "standard"
    workspace: ReaderWorkspace | None = None


state = _State()


def tr(text: str) -> str:
    return translate(text, state.language)


def explain(reasons) -> list[str]:
    """Translate the engine's (template, values) ranking reasons."""
    lines = []
    for template, values in reasons:
        values = {key: (", ".join(tr(item) for item in value) if isinstance(value, (list, tuple)) else tr(str(value)))
                  for key, value in values.items()}
        lines.append(tr(template).format(**values))
    return lines


def plain_label(text: str) -> str:
    """Text for buttons and menu actions, where Qt reads "&" as a shortcut marker."""
    return text.replace("&", "&&")


def palette() -> dict[str, str]:
    return theme.palette(state.mode)


def color(name: str) -> str:
    return palette()[name]


def icon(name: str, tone: str = "muted", size: int = 18):
    return icons.icon(name, color(tone), size)


def workspace() -> ReaderWorkspace:
    if state.workspace is None:
        state.workspace = ReaderWorkspace()
    return state.workspace


def age(timestamp, fallback: str = "") -> str:
    """'32m ago' in the interface language."""
    import time as _time
    if not timestamp:
        return fallback or tr("Unknown time")
    delta = max(0.0, _time.time() - float(timestamp))
    if delta < 60:
        return tr("now")
    if delta < 3600:
        return tr("{n}m ago").format(n=int(delta // 60))
    if delta < 86400:
        return tr("{n}h ago").format(n=int(delta // 3600))
    if delta < 7 * 86400:
        return tr("{n}d ago").format(n=int(delta // 86400))
    return fallback or tr("Older")


def short_date(date) -> str:
    return QLocale(_LOCALES.get(state.language, "en_GB")).toString(date, "d MMM")


def localized_date(language: str | None = None) -> str:
    locale = QLocale(_LOCALES.get(language or state.language, "en_GB"))
    return locale.toString(QDate.currentDate(), "dddd, d MMMM yyyy")


def run_dialog(dialog) -> int:
    """Run a modal dialog and release it (and any embedded web page) afterwards."""
    try:
        return dialog.exec()
    finally:
        dialog.deleteLater()


def open_url(url: str) -> None:
    QDesktopServices.openUrl(QUrl(url))


def tool_button(name: str, tooltip: str, parent: QWidget | None = None, *, object_name: str = "iconButton",
                tone: str = "muted", size: int = 18, checkable: bool = False) -> QToolButton:
    button = QToolButton(parent)
    button.setObjectName(object_name)
    button.setIcon(icon(name, tone, size))
    button.setIconSize(icons.icon_size(size))
    button.setToolTip(tooltip)
    button.setAccessibleName(tooltip)
    button.setCheckable(checkable)
    button.setAutoRaise(object_name == "cardAction")
    button.setProperty("iconName", name)
    button.setProperty("iconTone", tone)
    return button
