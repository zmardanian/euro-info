"""Application startup: fonts, single instance and the main window."""
from __future__ import annotations

import os
import sys
from pathlib import Path

from PySide6.QtCore import QCoreApplication, Qt
from PySide6.QtGui import QFontDatabase, QGuiApplication, QIcon
from PySide6.QtNetwork import QLocalServer, QLocalSocket
from PySide6.QtWidgets import QApplication, QMessageBox

from .. import APP_NAME, __version__, logs

log = logs.get("app")


def resource(*parts: str) -> Path:
    """A bundled file, both from a source checkout and from the packaged app."""
    base = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parents[2]))
    return base.joinpath(*parts)


def _user_tag() -> str:
    """Per-user name for the single-instance channel (Linux socket or Windows pipe)."""
    if hasattr(os, "getuid"):
        return str(os.getuid())
    import getpass
    import hashlib
    return hashlib.sha256(getpass.getuser().encode()).hexdigest()[:12]


def create_application(argv: list[str]) -> QApplication:
    # Required before the QApplication exists so Qt WebEngine can be imported
    # later, the first time a story is opened.
    QCoreApplication.setAttribute(Qt.ApplicationAttribute.AA_ShareOpenGLContexts)
    application = QApplication.instance() or QApplication(argv)
    application.setApplicationName("euro-info")
    application.setApplicationDisplayName(APP_NAME)
    application.setApplicationVersion(__version__)
    QGuiApplication.setDesktopFileName("euro-info")
    font = resource("assets", "fonts", "Newsreader[opsz,wght].ttf")
    if font.is_file():
        QFontDatabase.addApplicationFont(str(font))
    icon = resource("assets", "euro-info.svg")
    if icon.is_file():
        application.setWindowIcon(QIcon(str(icon)))
    return application


def run(argv: list[str]) -> int:
    application = create_application(argv)
    name = f"euro-info-reader-{_user_tag()}"
    probe = QLocalSocket()
    probe.connectToServer(name)
    if probe.waitForConnected(250):
        probe.write(b"activate")
        probe.waitForBytesWritten(250)
        probe.disconnectFromServer()
        log.info("Another window is open; activated it")
        return 0
    server = QLocalServer(application)
    if not server.listen(name):
        QLocalServer.removeServer(name)
        if not server.listen(name):
            QMessageBox.critical(None, APP_NAME, server.errorString())
            return 1

    from .main_window import MainWindow
    try:
        window = MainWindow()
    except Exception as exc:  # show startup failures instead of exiting silently
        log.exception("Startup failed")
        QMessageBox.critical(None, APP_NAME, str(exc))
        return 1

    def activate():
        while server.hasPendingConnections():
            client = server.nextPendingConnection()
            client.disconnectFromServer()
            client.deleteLater()
        target = application.activeModalWidget() or window
        target.showNormal() if target.isMinimized() else target.show()
        target.raise_()
        target.activateWindow()

    server.newConnection.connect(activate)
    window.show()
    return application.exec()


def self_test(report: str, timeout: float = 45.0) -> int:
    """Build the window headless in a throwaway profile, refresh once, and write a JSON report.

    Used by the release builds (the Windows app has no console to print to).
    """
    import json
    import tempfile
    import time
    from PySide6.QtCore import QTimer
    from .. import paths
    began = time.monotonic()
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    scratch = Path(tempfile.mkdtemp(prefix="euro-info-self-test-"))
    paths.configure(scratch / "config", scratch / "data", scratch / "cache")
    result = {"version": __version__, "platform": sys.platform, "window": False, "webengine": False,
              "stories": 0, "developing_stories": 0, "errors": []}
    try:
        application = create_application([sys.argv[0]])
        from .main_window import MainWindow
        window = MainWindow()
        window.show()
        result["window"] = True
        try:
            from . import reader  # noqa: F401  (Qt WebEngine is bundled and loads)
            result["webengine"] = True
        except Exception as exc:  # reported, not fatal for the test itself
            result["errors"].append(f"webengine: {exc}")
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline and (window.refresh_job is not None or not window.news):
            application.processEvents()
            time.sleep(0.05)
        window.set_view("briefing")
        application.processEvents()
        result["stories"] = len(window.news)
        result["developing_stories"] = len(window.index.stories())
        window.close()
        QTimer.singleShot(0, application.quit)
    except Exception as exc:  # the report must always be written
        result["errors"].append(repr(exc))
    result["seconds"] = round(time.monotonic() - began, 2)
    Path(report).write_text(json.dumps(result, indent=2), encoding="utf-8")
    return 0 if result["window"] and result["webengine"] and not result["errors"] else 1
