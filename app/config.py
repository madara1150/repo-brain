"""App settings and data locations (config.json + index.db in the user's data folder)."""
from __future__ import annotations

import json
import os
import sys
from dataclasses import asdict, dataclass, field

APP_NAME = "Repo Brain"
APP_ID = "RepoBrain"
MCP_NAME = "repo-brain"
VERSION = "1.0.0"


def data_dir() -> str:
    """Folder that holds config.json and index.db. REPO_BRAIN_HOME overrides it (tests, portable use)."""
    override = os.environ.get("REPO_BRAIN_HOME")
    if override:
        path = override
    elif sys.platform == "darwin":
        path = os.path.expanduser(f"~/Library/Application Support/{APP_ID}")
    elif sys.platform == "win32":
        path = os.path.join(os.environ.get("APPDATA") or os.path.expanduser("~"), APP_ID)
    else:
        base = os.environ.get("XDG_DATA_HOME") or os.path.expanduser("~/.local/share")
        path = os.path.join(base, "repo-brain")
    os.makedirs(path, exist_ok=True)
    return path


def config_path() -> str:
    return os.path.join(data_dir(), "config.json")


def index_path() -> str:
    return os.path.join(data_dir(), "index.db")


@dataclass
class Source:
    repo: str                 # "owner/name"
    branch: str = ""          # empty = the repository's default branch


@dataclass
class Knowledge:
    mode: str = "none"        # "none" | "github" | "folder"
    repo: str = ""            # for github: "owner/name" (usually private)
    branch: str = ""
    subdir: str = "knowledge"  # where new entries are written inside the repo
    folder: str = ""          # for folder mode: a local or shared-drive folder


@dataclass
class Config:
    sources: list = field(default_factory=list)      # list[Source]
    knowledge: Knowledge = field(default_factory=Knowledge)
    github_token: str = ""
    author: str = ""
    odoo_version: str = "16.0"
    language: str = "th"

    def to_json(self) -> dict:
        return {
            "sources": [asdict(s) for s in self.sources],
            "knowledge": asdict(self.knowledge),
            "github_token": self.github_token,
            "author": self.author,
            "odoo_version": self.odoo_version,
            "language": self.language,
        }

    @classmethod
    def from_json(cls, data: dict) -> "Config":
        cfg = cls()
        cfg.sources = [Source(repo=s.get("repo", ""), branch=s.get("branch", ""))
                       for s in data.get("sources", []) if s.get("repo")]
        k = data.get("knowledge") or {}
        cfg.knowledge = Knowledge(**{f: k[f] for f in Knowledge.__dataclass_fields__ if f in k})
        for name in ("github_token", "author", "odoo_version", "language"):
            if isinstance(data.get(name), str):
                setattr(cfg, name, data[name])
        return cfg


def load_config() -> Config:
    try:
        with open(config_path(), encoding="utf-8") as fh:
            return Config.from_json(json.load(fh))
    except (OSError, ValueError):
        return Config()


def save_config(cfg: Config) -> None:
    path = config_path()
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as fh:
        json.dump(cfg.to_json(), fh, ensure_ascii=False, indent=2)
    try:
        os.chmod(tmp, 0o600)  # holds the GitHub token
    except OSError:
        pass
    os.replace(tmp, path)
