"""Small reusable widgets: banners, the AI status button and filter chips."""
from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QColor, QIcon, QPainter, QPixmap
from PySide6.QtWidgets import QFrame, QHBoxLayout, QLabel, QPushButton

from .common import color, tool_button, tr


class Banner(QFrame):
    """A dismissible message strip with optional action buttons."""

    closed = Signal()

    def __init__(self, text: str = "", parent=None):
        super().__init__(parent)
        self.setObjectName("banner")
        self.row = QHBoxLayout(self)
        self.row.setContentsMargins(14, 8, 8, 8)
        self.row.setSpacing(8)
        self.label = QLabel(text)
        self.label.setWordWrap(True)
        self.row.addWidget(self.label, 1)
        self.actions: list[QPushButton] = []
        self.close_button = tool_button("close", tr("Close"), self, object_name="cardAction", size=16)
        self.close_button.clicked.connect(self.dismiss)
        self.row.addWidget(self.close_button)
        self.hide()

    def set_actions(self, actions: list[tuple[str, object, bool]]) -> None:
        for button in self.actions:
            button.deleteLater()
        self.actions = []
        for text, slot, primary in actions:
            button = QPushButton(text)
            if primary:
                button.setObjectName("primary")
            button.clicked.connect(slot)
            self.row.insertWidget(self.row.count() - 1, button)
            self.actions.append(button)

    def show_message(self, text: str, actions: list[tuple[str, object, bool]] | None = None) -> None:
        self.label.setText(text)
        self.set_actions(actions or [])
        self.show()

    def dismiss(self):
        self.hide()
        self.closed.emit()


def dot_icon(tone: str, size: int = 10) -> QIcon:
    pixmap = QPixmap(size * 2, size * 2)
    pixmap.fill(Qt.GlobalColor.transparent)
    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    painter.setBrush(QColor(color(tone)))
    painter.setPen(Qt.PenStyle.NoPen)
    painter.drawEllipse(size // 2, size // 2, size, size)
    painter.end()
    return QIcon(pixmap)


class AIStatusButton(QPushButton):
    """Shows which local model is in use, with a fix when something is missing."""

    TONES = {"ready": "success", "checking": "faint", "stopped": "faint", "no-model": "warning",
             "missing": "warning", "error": "danger"}

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("aiStatus")
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.state = "checking"
        self.show_state("checking", tr("Checking local AI…"))

    def show_state(self, state: str, text: str, tooltip: str = "") -> None:
        self.state = state
        self.setIcon(dot_icon(self.TONES.get(state, "faint")))
        self.setText(text)
        self.setToolTip(tooltip or text)
        self.setAccessibleName(text)
