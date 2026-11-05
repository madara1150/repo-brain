"""Register the MCP server with Claude Desktop (claude_desktop_config.json) or show the Claude Code command."""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys

from .config import MCP_NAME


def server_command() -> tuple[str, list[str]]:
    """How Claude should start our MCP server."""
    if getattr(sys, "frozen", False):
        exe = sys.executable
        if sys.platform == "win32":  # the GUI exe has no console streams; a console twin is shipped beside it
            twin = os.path.join(os.path.dirname(exe), "RepoBrainMCP.exe")
            if os.path.exists(twin):
                return twin, []
        return exe, ["--mcp"]
    main = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "main.py"))
    return sys.executable, [main, "--mcp"]


def desktop_config_paths() -> list[str]:
    if sys.platform == "darwin":
        return [os.path.expanduser("~/Library/Application Support/Claude/claude_desktop_config.json")]
    if sys.platform == "win32":
        paths = [os.path.join(os.environ.get("APPDATA", ""), "Claude", "claude_desktop_config.json")]
        # Microsoft Store build keeps its files in a virtualised folder
        pkgs = os.path.join(os.environ.get("LOCALAPPDATA", ""), "Packages")
        if os.path.isdir(pkgs):
            for name in os.listdir(pkgs):
                if name.lower().startswith("claude_"):
                    paths.append(os.path.join(pkgs, name, "LocalCache", "Roaming", "Claude",
                                              "claude_desktop_config.json"))
        return paths
    return [os.path.expanduser("~/.config/Claude/claude_desktop_config.json")]


def desktop_config_path() -> str:
    paths = desktop_config_paths()
    for p in paths:
        if os.path.exists(p):
            return p
    for p in paths:
        if os.path.isdir(os.path.dirname(p)):
            return p
    return paths[0]


def claude_desktop_found() -> bool:
    return any(os.path.isdir(os.path.dirname(p)) for p in desktop_config_paths())


def _read(path: str) -> dict:
    try:
        with open(path, encoding="utf-8") as fh:
            data = json.load(fh)
        return data if isinstance(data, dict) else {}
    except FileNotFoundError:
        return {}


def entry() -> dict:
    cmd, args = server_command()
    return {"command": cmd, "args": args}


def status(path: str | None = None) -> str:
    """"connected" | "outdated" (points at another copy of the app) | "missing"."""
    try:
        cur = (_read(path or desktop_config_path()).get("mcpServers") or {}).get(MCP_NAME)
    except ValueError:
        return "missing"
    if not cur:
        return "missing"
    return "connected" if cur.get("command") == entry()["command"] and cur.get("args", []) == entry()["args"] else "outdated"


def install(path: str | None = None) -> str:
    path = path or desktop_config_path()
    data = _read(path)  # raises ValueError on a broken file: we never overwrite what we can't read
    os.makedirs(os.path.dirname(path), exist_ok=True)
    if os.path.exists(path):
        shutil.copy2(path, path + ".bak")
    servers = data.get("mcpServers")
    if not isinstance(servers, dict):
        servers = data["mcpServers"] = {}
    servers[MCP_NAME] = entry()
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as fh:
        json.dump(data, fh, indent=2, ensure_ascii=False)
    os.replace(tmp, path)
    return path


def uninstall(path: str | None = None) -> bool:
    path = path or desktop_config_path()
    data = _read(path)
    servers = data.get("mcpServers") or {}
    if MCP_NAME not in servers:
        return False
    shutil.copy2(path, path + ".bak")
    del servers[MCP_NAME]
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(data, fh, indent=2, ensure_ascii=False)
    return True


def claude_code_command() -> str:
    cmd, args = server_command()
    quote = subprocess.list2cmdline if sys.platform == "win32" else (lambda xs: " ".join(_sh(x) for x in xs))
    return f"claude mcp add --scope user {MCP_NAME} -- " + quote([cmd, *args])


def _sh(s: str) -> str:
    import shlex
    return shlex.quote(s)
