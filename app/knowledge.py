"""Shared team knowledge: add an entry (commit to the knowledge repo, or write to the shared folder)."""
from __future__ import annotations

import os
import re
from datetime import datetime

from .config import Config
from .github import GitHub
from .store import Store
from .sync import LOCAL_KNOWLEDGE


class KnowledgeError(Exception):
    pass


def slugify(title: str) -> str:
    ascii_part = re.sub(r"[^a-z0-9]+", "-", title.lower()).strip("-")[:50].strip("-")
    return ascii_part or "note"


def render(title: str, content: str, author: str, tags: list[str], when: datetime) -> str:
    head = [f"# {title.strip()}", ""]
    meta = [f"- date: {when:%Y-%m-%d %H:%M}"]
    if author:
        meta.append(f"- author: {author}")
    if tags:
        meta.append("- tags: " + ", ".join(t.strip() for t in tags if t.strip()))
    return "\n".join(head + meta + ["", content.strip(), ""])


def add_entry(cfg: Config, store: Store, title: str, content: str, tags: list[str] | None = None,
              gh: GitHub | None = None, when: datetime | None = None) -> str:
    """Save a knowledge entry for the whole team and index it right away. Returns where it went."""
    title, content = (title or "").strip(), (content or "").strip()
    if not title or not content:
        raise KnowledgeError("title and content are required")
    when = when or datetime.now()
    tags = tags or []
    k = cfg.knowledge
    name = f"{when:%Y-%m-%d-%H%M%S}-{slugify(title)}.md"
    if k.mode == "github" and k.repo:
        gh = gh or GitHub(cfg.github_token)
        author = cfg.author or _safe_login(gh)
        text = render(title, content, author, tags, when)
        rel = "/".join(p for p in (k.subdir.strip("/"), name) if p)
        gh.put_file(k.repo, k.branch, rel, text.encode("utf-8"), f"Add knowledge: {title[:60]}")
        repo = k.repo
        where = f"github.com/{k.repo}/{rel}"
    elif k.mode == "folder" and k.folder:
        if not os.path.isdir(k.folder):
            raise KnowledgeError(f"knowledge folder not found: {k.folder}")
        text = render(title, content, cfg.author, tags, when)
        sub = os.path.join(k.folder, k.subdir) if k.subdir else k.folder
        os.makedirs(sub, exist_ok=True)
        with open(os.path.join(sub, name), "w", encoding="utf-8") as fh:
            fh.write(text)
        rel = os.path.relpath(os.path.join(sub, name), k.folder).replace(os.sep, "/")
        repo = LOCAL_KNOWLEDGE
        where = os.path.join(sub, name)
    else:
        raise KnowledgeError("no shared knowledge location is set - choose one in the Repo Brain app")
    with store.conn:
        store.put_file(repo, rel, "knowledge", text)
    return where


def _safe_login(gh: GitHub) -> str:
    try:
        return gh.current_user()
    except Exception:
        return ""
