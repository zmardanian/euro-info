"""A small stroke icon set, rendered from SVG and tinted per theme."""
from __future__ import annotations

from functools import lru_cache

from PySide6.QtCore import QByteArray, QRectF, QSize, Qt
from PySide6.QtGui import QIcon, QPainter, QPixmap
from PySide6.QtSvg import QSvgRenderer
from PySide6.QtWidgets import QApplication

_PATHS = {
    "refresh": '<path d="M20 11a8 8 0 1 0-2.3 5.7"/><polyline points="20 4 20 10 14 10"/>',
    "search": '<circle cx="11" cy="11" r="6.5"/><line x1="20" y1="20" x2="15.8" y2="15.8"/>',
    "star": '<polygon points="12 3 14.8 8.8 21 9.6 16.5 14 17.6 20.3 12 17.3 6.4 20.3 7.5 14 3 9.6 9.2 8.8"/>',
    "star-filled": '<polygon fill="currentColor" points="12 3 14.8 8.8 21 9.6 16.5 14 17.6 20.3 12 17.3 6.4 20.3 7.5 14 3 9.6 9.2 8.8"/>',
    "sparkle": '<path d="M11 3.5l1.8 4.9 4.9 1.8-4.9 1.8L11 16.9l-1.8-4.9L4.3 10.2l4.9-1.8z"/>'
               '<path d="M18.5 14.5l.8 2 2 .8-2 .8-.8 2-.8-2-2-.8 2-.8z"/>',
    "translate": '<path d="M3.5 5.5h9"/><path d="M8 3.5v2"/><path d="M5.5 9.5c1.4 2.6 3.4 4.4 6 5.4"/>'
                 '<path d="M11 5.5c-1 4-3.4 7.3-7 9.3"/><path d="M13 20.5l4-9 4 9"/><path d="M14.4 17.5h5.2"/>',
    "more": '<circle cx="5.5" cy="12" r="1.3" fill="currentColor"/><circle cx="12" cy="12" r="1.3" fill="currentColor"/>'
            '<circle cx="18.5" cy="12" r="1.3" fill="currentColor"/>',
    "newspaper": '<rect x="3.5" y="4.5" width="17" height="15" rx="2"/><line x1="7.5" y1="9" x2="16.5" y2="9"/>'
                 '<line x1="7.5" y1="12.5" x2="16.5" y2="12.5"/><line x1="7.5" y1="16" x2="12.5" y2="16"/>',
    "bookmark": '<path d="M6.5 3.5h11v17l-5.5-3.8-5.5 3.8z"/>',
    "library": '<rect x="4" y="4" width="4" height="16" rx="1"/><rect x="10" y="4" width="4" height="16" rx="1"/>'
               '<path d="M16.3 5.2l3-.8 3.2 14.6-3 .8z"/>',
    "history": '<circle cx="12" cy="12" r="8.5"/><polyline points="12 7.5 12 12 15 14"/>',
    "layers": '<polygon points="12 3.5 20.5 8 12 12.5 3.5 8"/><polyline points="3.5 12.5 12 17 20.5 12.5"/>',
    "copy": '<rect x="8.5" y="8.5" width="11.5" height="11.5" rx="2"/>'
            '<path d="M15.5 8.5V5.5a1.5 1.5 0 0 0-1.5-1.5H5.5A1.5 1.5 0 0 0 4 5.5V14a1.5 1.5 0 0 0 1.5 1.5h3"/>',
    "reset": '<path d="M4 12a8 8 0 1 0 2.3-5.7"/><polyline points="4 4 4 10 10 10"/>',
    "rss": '<path d="M5 11a8 8 0 0 1 8 8"/><path d="M5 4.5a14.5 14.5 0 0 1 14.5 14.5"/>'
           '<circle cx="6" cy="18" r="1.4" fill="currentColor"/>',
    "image": '<rect x="3.5" y="4.5" width="17" height="15" rx="2"/><circle cx="9" cy="10" r="1.8"/>'
             '<path d="M20.5 15.5l-4.5-4.5-8.5 8.5"/>',
    "sliders": '<line x1="4" y1="7" x2="20" y2="7"/><line x1="4" y1="17" x2="20" y2="17"/>'
               '<circle cx="9" cy="7" r="2.2" fill="currentColor"/><circle cx="15" cy="17" r="2.2" fill="currentColor"/>',
    "type": '<path d="M3.5 19l5-13 5 13"/><path d="M5.5 14h6"/><path d="M14.5 19l3-8 3 8"/><path d="M15.6 16.2h3.8"/>',
    "pin": '<path d="M12 21s-6.5-5.8-6.5-10.5a6.5 6.5 0 0 1 13 0C18.5 15.2 12 21 12 21z"/><circle cx="12" cy="10.5" r="2.3"/>',
    "external": '<path d="M14 4h6v6"/><path d="M20 4l-8.5 8.5"/><path d="M18.5 14v4.5a1.5 1.5 0 0 1-1.5 1.5H5.5A1.5 1.5 0 0 1 4 18.5V7a1.5 1.5 0 0 1 1.5-1.5H10"/>',
    "check": '<polyline points="5 12.5 10 17 19 7.5"/>',
    "close": '<line x1="6.5" y1="6.5" x2="17.5" y2="17.5"/><line x1="17.5" y1="6.5" x2="6.5" y2="17.5"/>',
    "back": '<polyline points="15 18 9 12 15 6"/>',
    "forward": '<polyline points="9 18 15 12 9 6"/>',
    "pencil": '<path d="M4 20h4L19 9l-4-4L4 16z"/><line x1="13.5" y1="6.5" x2="17.5" y2="10.5"/>',
    "download": '<path d="M12 4v11"/><polyline points="7 10.5 12 15.5 17 10.5"/><path d="M5 20h14"/>',
    "link": '<path d="M10 14a4.5 4.5 0 0 0 6.4 0l2.6-2.6a4.5 4.5 0 0 0-6.4-6.4L11.5 6"/>'
            '<path d="M14 10a4.5 4.5 0 0 0-6.4 0L5 12.6a4.5 4.5 0 0 0 6.4 6.4l1.1-1"/>',
    "globe": '<circle cx="12" cy="12" r="8.5"/><path d="M3.5 12h17"/><path d="M12 3.5c2.5 2.6 3.6 5.4 3.6 8.5s-1.1 5.9-3.6 8.5c-2.5-2.6-3.6-5.4-3.6-8.5s1.1-5.9 3.6-8.5z"/>',
}

_TEMPLATE = ('<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="{color}" '
             'stroke-width="{width}" stroke-linecap="round" stroke-linejoin="round" color="{color}">{body}</svg>')


@lru_cache(maxsize=512)
def _pixmap(name: str, color: str, size: int, ratio: float, width: float) -> QPixmap:
    body = _PATHS[name].replace("currentColor", color)
    svg = _TEMPLATE.format(color=color, width=width, body=body)
    renderer = QSvgRenderer(QByteArray(svg.encode()))
    pixels = max(1, round(size * ratio))
    pixmap = QPixmap(pixels, pixels)
    pixmap.fill(Qt.GlobalColor.transparent)
    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    renderer.render(painter, QRectF(0, 0, pixels, pixels))
    painter.end()
    pixmap.setDevicePixelRatio(ratio)
    return pixmap


def icon(name: str, color: str, size: int = 18, width: float = 1.8) -> QIcon:
    application = QApplication.instance()
    ratio = application.devicePixelRatio() if application else 1.0
    result = QIcon()
    result.addPixmap(_pixmap(name, color, size, max(1.0, ratio), width))
    return result


def icon_size(size: int = 18) -> QSize:
    return QSize(size, size)


def names() -> list[str]:
    return sorted(_PATHS)
