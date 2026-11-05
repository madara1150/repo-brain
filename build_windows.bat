@echo off
REM Build Repo Brain for Windows. Requires Python 3.10+ (python.org) and optionally Inno Setup 6.5+.
setlocal
cd /d "%~dp0"

if not exist .venv-win (
    python -m venv .venv-win || goto :error
)
call .venv-win\Scripts\activate.bat
python -m pip install --upgrade pip
python -m pip install -r requirements.txt pyinstaller || goto :error
python tools\version_info.py %APP_VERSION% || goto :error

pyinstaller --noconfirm --clean --distpath dist --workpath build\pyi build_tools\repo_brain.spec || goto :error
dist\RepoBrain\RepoBrainMCP.exe --selftest || goto :error
echo.
echo  Portable build: dist\RepoBrain\RepoBrain.exe

set ISCC="%ProgramFiles(x86)%\Inno Setup 6\ISCC.exe"
if exist %ISCC% (
    if defined APP_VERSION (
        %ISCC% /DAppVersion=%APP_VERSION% build_tools\installer.iss || goto :error
    ) else (
        %ISCC% build_tools\installer.iss || goto :error
    )
    echo  Installer: dist\RepoBrain-Windows-Setup.exe
) else (
    echo  Inno Setup not found - skipping installer. Get it from https://jrsoftware.org/isdl.php
)
exit /b 0

:error
echo Build failed.
exit /b 1
