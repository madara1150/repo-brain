# PyInstaller spec for macOS -> dist/Repo Brain.app
# The same executable runs the window, or the MCP server with --mcp (started by Claude Desktop).
import os
ROOT = os.path.abspath(os.path.join(SPECPATH, ".."))
VERSION = os.environ.get("APP_VERSION", "1.0.2")

EXCLUDES = ["tkinter", "unittest", "PySide6.QtWebEngineCore", "PySide6.QtWebEngineWidgets", "PySide6.Qt3DCore",
            "PySide6.QtQuick", "PySide6.QtQml", "PySide6.QtMultimedia", "PySide6.QtCharts",
            "PySide6.QtDataVisualization", "PySide6.QtPdf", "PySide6.QtBluetooth", "PySide6.QtSql"]

a = Analysis([os.path.join(ROOT, "main.py")], pathex=[ROOT],
             datas=[(os.path.join(ROOT, "assets"), "assets")], excludes=EXCLUDES)
pyz = PYZ(a.pure)
exe = EXE(pyz, a.scripts, [], exclude_binaries=True, name="Repo Brain",
          console=False, upx=False, argv_emulation=False)
coll = COLLECT(exe, a.binaries, a.datas, name="Repo Brain", upx=False)
app = BUNDLE(
    coll,
    name="Repo Brain.app",
    icon=os.path.join(ROOT, "build", "icon.icns"),
    bundle_identifier="com.madara1150.repobrain",
    version=VERSION,
    info_plist={
        "CFBundleDisplayName": "Repo Brain",
        "CFBundleShortVersionString": VERSION,
        "NSHighResolutionCapable": True,
        "LSMinimumSystemVersion": "11.0",
        "NSHumanReadableCopyright": "Copyright (c) 2026 Tanathip",
    },
)
