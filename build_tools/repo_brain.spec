# PyInstaller spec (Windows) -> dist\RepoBrain\
#   RepoBrain.exe     the window (windowed, no console)
#   RepoBrainMCP.exe  the MCP server for Claude Desktop (console app: needs real stdin/stdout)
# One-folder build and no UPX keep antivirus false positives down.
import os
ROOT = os.path.abspath(os.path.join(SPECPATH, ".."))

EXCLUDES = ["tkinter", "unittest", "PySide6.QtWebEngineCore", "PySide6.QtWebEngineWidgets", "PySide6.Qt3DCore",
            "PySide6.QtQuick", "PySide6.QtQml", "PySide6.QtMultimedia", "PySide6.QtCharts",
            "PySide6.QtDataVisualization", "PySide6.QtPdf", "PySide6.QtBluetooth", "PySide6.QtSql"]
ICON = os.path.join(ROOT, "assets", "icon.ico")
VERSION_FILE = os.path.join(ROOT, "build", "version_info.txt")

gui = Analysis([os.path.join(ROOT, "main.py")], pathex=[ROOT],
               datas=[(os.path.join(ROOT, "assets"), "assets")], excludes=EXCLUDES)
mcp = Analysis([os.path.join(ROOT, "mcp_main.py")], pathex=[ROOT], excludes=EXCLUDES + ["PySide6"])

gui_exe = EXE(PYZ(gui.pure), gui.scripts, [], exclude_binaries=True, name="RepoBrain", icon=ICON,
              version=VERSION_FILE, console=False, upx=False, strip=False)
mcp_exe = EXE(PYZ(mcp.pure), mcp.scripts, [], exclude_binaries=True, name="RepoBrainMCP", icon=ICON,
              version=VERSION_FILE, console=True, upx=False, strip=False)
coll = COLLECT(gui_exe, gui.binaries, gui.datas, mcp_exe, mcp.binaries, mcp.datas,
               name="RepoBrain", upx=False, strip=False)
