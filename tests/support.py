"""Imported first by every test: keeps tests away from the user's real data.

All XDG folders point into a temporary directory, so tests never read or
write ~/.config/euro-info, the research library or the caches.
"""
import atexit
import os
import shutil
import sys
import tempfile
from pathlib import Path

ROOT = Path(tempfile.mkdtemp(prefix="euro-info-tests-"))
for variable, folder in (("XDG_CONFIG_HOME", "config"), ("XDG_DATA_HOME", "data"), ("XDG_CACHE_HOME", "cache")):
    os.environ[variable] = str(ROOT / folder)
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ.pop("OLLAMA_HOST", None)
atexit.register(shutil.rmtree, ROOT, ignore_errors=True)

PROJECT = Path(__file__).resolve().parents[1]
if str(PROJECT) not in sys.path:
    sys.path.insert(0, str(PROJECT))


def application():
    from PySide6.QtCore import QCoreApplication, Qt
    from PySide6.QtWidgets import QApplication
    QCoreApplication.setAttribute(Qt.ApplicationAttribute.AA_ShareOpenGLContexts)
    return QApplication.instance() or QApplication([])
