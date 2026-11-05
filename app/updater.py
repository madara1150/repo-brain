"""Check for a new Repo Brain release on GitHub and update in place.

Only release metadata and, on request, the installer are downloaded from github.com; nothing about the
user is sent. The download is verified against the SHA-256 published with the release.
- macOS: the new .app replaces the current one (same location, so the Claude Desktop link keeps working)
  by a small helper script that runs after the app quits, then reopens it.
- Windows (installed): the installer runs silently, closes the app and starts the new version.
- Windows portable / running from source: open the release page instead.
"""
from __future__ import annotations

import hashlib
import json
import os
import ssl
import subprocess
import sys
import tempfile
import urllib.request
from dataclasses import dataclass

from .config import VERSION

REPO = "madara1150/repo-brain"
API_LATEST = f"https://api.github.com/repos/{REPO}/releases/latest"
RELEASES_PAGE = f"https://github.com/{REPO}/releases/latest"
SUMS_NAME = "SHA256SUMS.txt"
ASSET_WINDOWS = "RepoBrain-Windows-Setup.exe"
ASSET_MAC = "RepoBrain-macOS.dmg"
MAC_APP_NAME = "Repo Brain.app"
TIMEOUT = 20


class UpdateError(Exception):
    pass


@dataclass
class Release:
    version: str
    notes: str
    page: str
    asset_name: str = ""
    asset_url: str = ""
    sums_url: str = ""


def parse_version(v: str) -> tuple:
    v = (v or "").strip().lstrip("vV").split("-")[0].split("+")[0]
    parts = []
    for p in v.split("."):
        digits = "".join(ch for ch in p if ch.isdigit())
        parts.append(int(digits) if digits else 0)
    while len(parts) < 3:
        parts.append(0)
    return tuple(parts)


def is_newer(latest: str, current: str = VERSION) -> bool:
    return parse_version(latest) > parse_version(current)


def _ssl_context():
    try:
        import certifi
        return ssl.create_default_context(cafile=certifi.where())
    except Exception:
        return ssl.create_default_context()


def _open(url: str, accept: str = "application/octet-stream"):
    req = urllib.request.Request(url, headers={"User-Agent": f"RepoBrain/{VERSION}", "Accept": accept})
    return urllib.request.urlopen(req, timeout=TIMEOUT, context=_ssl_context())


def platform_asset() -> str:
    return {"win32": ASSET_WINDOWS, "darwin": ASSET_MAC}.get(sys.platform, "")


def installed_with_setup() -> bool:
    """The Windows installer build has an uninstaller next to the exe; the portable zip doesn't."""
    if sys.platform != "win32" or not getattr(sys, "frozen", False):
        return False
    folder = os.path.dirname(sys.executable)
    return any(n.lower().startswith("unins") and n.lower().endswith(".exe") for n in os.listdir(folder))


def current_app_bundle() -> str:
    """/Applications/Repo Brain.app when running from a bundle on macOS, else ""."""
    if sys.platform != "darwin" or not getattr(sys, "frozen", False):
        return ""
    path = os.path.abspath(sys.executable)
    while path and path != "/":
        if path.endswith(".app"):
            return path
        path = os.path.dirname(path)
    return ""


def can_self_update() -> bool:
    if sys.platform == "win32":
        return installed_with_setup()
    if sys.platform == "darwin":
        bundle = current_app_bundle()
        # needs write access to the folder holding the app, and must not run from the read-only .dmg
        return bool(bundle) and not bundle.startswith("/Volumes/") and os.access(os.path.dirname(bundle), os.W_OK)
    return False


def release_from_json(data: dict) -> Release:
    rel = Release(version=(data.get("tag_name") or "").lstrip("vV"), notes=data.get("body") or "",
                  page=data.get("html_url") or RELEASES_PAGE)
    want = platform_asset()
    for a in data.get("assets", []):
        if a.get("name") == want:
            rel.asset_name, rel.asset_url = a["name"], a["browser_download_url"]
        elif a.get("name") == SUMS_NAME:
            rel.sums_url = a["browser_download_url"]
    return rel


def fetch_latest() -> Release:
    with _open(API_LATEST, "application/vnd.github+json") as r:
        return release_from_json(json.load(r))


def expected_sha256(sums_text: str, name: str) -> str:
    for line in sums_text.splitlines():
        parts = line.strip().split()
        if len(parts) >= 2 and parts[-1].lstrip("*") == name and len(parts[0]) == 64:
            return parts[0].lower()
    return ""


def download(rel: Release, progress=None) -> str:
    """Download this platform's installer, verify its SHA-256 and return the local path."""
    if not rel.asset_url:
        raise UpdateError("no installer for this platform in the release")
    if not rel.sums_url:
        raise UpdateError(f"{SUMS_NAME} is missing from the release")
    with _open(rel.sums_url) as r:
        want = expected_sha256(r.read().decode("utf-8", "replace"), rel.asset_name)
    if not want:
        raise UpdateError(f"{rel.asset_name} is not listed in {SUMS_NAME}")
    folder = tempfile.mkdtemp(prefix="repobrain-update-")
    path = os.path.join(folder, rel.asset_name)
    h = hashlib.sha256()
    with _open(rel.asset_url) as r, open(path, "wb") as f:
        total = int(r.headers.get("Content-Length") or 0)
        done = 0
        while True:
            chunk = r.read(256 * 1024)
            if not chunk:
                break
            f.write(chunk)
            h.update(chunk)
            done += len(chunk)
            if progress:
                progress(done, total)
    if h.hexdigest() != want:
        os.remove(path)
        raise UpdateError("checksum mismatch: the download was damaged or changed")
    return path


MAC_SCRIPT = r"""#!/bin/bash
# Repo Brain updater: wait for the app to quit, swap in the new bundle, reopen it.
PID="$1"; DMG="$2"; APP="$3"; LOG="$4"
exec >>"$LOG" 2>&1
for i in $(seq 1 120); do kill -0 "$PID" 2>/dev/null || break; sleep 0.5; done
MNT=$(mktemp -d /tmp/repobrain-mnt.XXXXXX)
if hdiutil attach -nobrowse -readonly -noautoopen -mountpoint "$MNT" "$DMG"; then
  if [ -d "$MNT/__APPNAME__" ]; then
    rm -rf "$APP.new" && ditto "$MNT/__APPNAME__" "$APP.new" && rm -rf "$APP.old" && mv "$APP" "$APP.old" \
      && mv "$APP.new" "$APP" && rm -rf "$APP.old" && echo "updated $APP"
  fi
  hdiutil detach "$MNT" -quiet
fi
open "$APP"
"""


def mac_script(path: str) -> str:
    with open(path, "w") as fh:
        fh.write(MAC_SCRIPT.replace("__APPNAME__", MAC_APP_NAME))
    os.chmod(path, 0o755)
    return path


def launch_installer(path: str):
    """Start the update; the caller quits the app right after."""
    if sys.platform == "win32":
        flags = getattr(subprocess, "DETACHED_PROCESS", 0) | getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0)
        subprocess.Popen([path, "/SILENT", "/SP-", "/CLOSEAPPLICATIONS", "/NORESTART"], creationflags=flags,
                         close_fds=True)
    elif sys.platform == "darwin":
        bundle = current_app_bundle()
        if not bundle:
            subprocess.Popen(["open", path])
            return
        folder = os.path.dirname(path)
        script = mac_script(os.path.join(folder, "update.sh"))
        log = os.path.join(folder, "update.log")
        subprocess.Popen(["/bin/bash", script, str(os.getpid()), path, bundle, log],
                         start_new_session=True, close_fds=True)
    else:
        raise UpdateError("unsupported platform")
