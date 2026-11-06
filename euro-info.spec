from PyInstaller.building.build_main import Analysis, PYZ, EXE, COLLECT


# ------------------------------------------------------------
# Euro Info — PyInstaller specification
# ------------------------------------------------------------

import sys

APP_NAME = "euro-info"
WINDOWS = sys.platform.startswith("win")


# Qt modules that this QWidget application does NOT use.
EXCLUDED_QT_MODULES = [
    "PySide6.Qt3DCore",
    "PySide6.Qt3DAnimation",
    "PySide6.Qt3DExtras",
    "PySide6.Qt3DInput",
    "PySide6.Qt3DLogic",
    "PySide6.Qt3DRender",
    "PySide6.Qt3DScene2D",
    "PySide6.QtCharts",
    "PySide6.QtConcurrent",
    "PySide6.QtDataVisualization",
    "PySide6.QtGraphs",
    "PySide6.QtGraphsWidgets",
    "PySide6.QtHttpServer",
    "PySide6.QtLocation",
    "PySide6.QtMultimedia",
    "PySide6.QtMultimediaWidgets",
    "PySide6.QtNfc",
    "PySide6.QtOpenGLWidgets",
    "PySide6.QtPdf",
    "PySide6.QtPdfWidgets",
    "PySide6.QtQml",
    "PySide6.QtQmlModels",
    "PySide6.QtQuick3D",
    "PySide6.QtQuickControls2",
    "PySide6.QtQuickTest",
    "PySide6.QtRemoteObjects",
    "PySide6.QtSensors",
    "PySide6.QtSerialBus",
    "PySide6.QtSerialPort",
    "PySide6.QtSpatialAudio",
    "PySide6.QtSql",
    "PySide6.QtStateMachine",
    "PySide6.QtTest",
    "PySide6.QtTextToSpeech",
    "PySide6.QtUiTools",
    "PySide6.QtWebSockets",
    "PySide6.QtWebView",
    "PySide6.QtXml",
    "PySide6.QtXmlPatterns",
]


analysis = Analysis(
    ["app.py"],

    pathex=["."],

    binaries=[],
    datas=[
        ("assets/fonts/Newsreader[opsz,wght].ttf", "assets/fonts"),
        ("assets/fonts/Newsreader-OFL.txt", "assets/fonts"),
        ("assets/euro-info.svg", "assets"),
        ("assets/euro-info.ico", "assets"),
    ],

    hiddenimports=[
        "PySide6.QtCore",
        "PySide6.QtGui",
        "PySide6.QtWidgets",
        "PySide6.QtNetwork",
        "PySide6.QtWebEngineCore",
        "PySide6.QtWebEngineWidgets",
        "PySide6.QtSvg",
        # Imported on demand, the first time a story or an analysis is opened.
        "euroinfo.ui.reader",
        "euroinfo.ui.summary",
    ],

    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],

    excludes=[
        "tkinter",
        "unittest",
        "pydoc",
        "matplotlib",
        "numpy",
        "pandas",
        *EXCLUDED_QT_MODULES,
    ],

    noarchive=False,
)


pyz = PYZ(
    analysis.pure,
    analysis.zipped_data,
)


# IMPORTANT:
#
# a.binaries and a.datas are NOT passed into EXE().
#
# They are collected separately by COLLECT() below.
#
# exclude_binaries=True makes this a proper PyInstaller
# onedir build.

exe = EXE(
    pyz,
    analysis.scripts,
    [],

    name=APP_NAME,

    debug=False,
    bootloader_ignore_signals=False,

    strip=False,
    upx=False,

    console=False,
    icon="assets/euro-info.ico" if WINDOWS else None,

    exclude_binaries=True,
)


coll = COLLECT(
    exe,

    analysis.binaries,
    analysis.datas,

    strip=False,
    upx=False,

    name=APP_NAME,
)
