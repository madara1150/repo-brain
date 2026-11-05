"""Shared team knowledge: add or update a note (commit to the knowledge repo, or write to the shared folder)."""
from __future__ import annotations

import os
import re
from datetime import datetime

from .config import Config
from .github import GitHub
from .store import Store
from .sync import LOCAL_KNOWLEDGE, knowledge_repo


class KnowledgeError(Exception):
    pass


def slugify(title: str) -> str:
    ascii_part = re.sub(r"[^a-z0-9]+", "-", title.lower()).strip("-")[:50].strip("-")
    return ascii_part or "note"


def _clean_list(items) -> list[str]:
    return [str(t).strip() for t in (items or []) if str(t).strip()]


def render(title: str, content: str, author: str, tags: list[str], when: datetime,
           note_type: str = "", modules: list[str] | None = None) -> str:
    meta = [f"- date: {when:%Y-%m-%d %H:%M}"]
    if note_type:
        meta.append(f"- type: {note_type}")
    if author:
        meta.append(f"- author: {author}")
    if modules:
        meta.append("- modules: " + ", ".join(_clean_list(modules)))
    if tags:
        meta.append("- tags: " + ", ".join(_clean_list(tags)))
    body = content.strip()
    first = body.splitlines()[0].strip() if body else ""
    if first.lstrip("# ").strip() == title.strip():  # Claude sometimes repeats the title
        body = "\n".join(body.splitlines()[1:]).strip()
    return "\n".join([f"# {title.strip()}", ""] + meta + ["", body, ""])


def _target(cfg: Config):
    k = cfg.knowledge
    if k.mode == "github" and k.repo:
        return "github"
    if k.mode == "folder" and k.folder:
        if not os.path.isdir(k.folder):
            raise KnowledgeError(f"knowledge folder not found: {k.folder}")
        return "folder"
    raise KnowledgeError("no shared knowledge location is set - choose one in the Repo Brain app")


def add_entry(cfg: Config, store: Store, title: str, content: str, tags: list[str] | None = None,
              gh: GitHub | None = None, when: datetime | None = None, note_type: str = "",
              modules: list[str] | None = None) -> str:
    """Save a new note for the whole team and index it right away. Returns where it went."""
    title, content = (title or "").strip(), (content or "").strip()
    if not title or not content:
        raise KnowledgeError("title and content are required")
    when = when or datetime.now()
    k = cfg.knowledge
    name = f"{when:%Y-%m-%d-%H%M%S}-{slugify(title)}.md"
    kind = _target(cfg)
    if kind == "github":
        gh = gh or GitHub(cfg.github_token)
        author = cfg.author or _safe_login(gh)
        text = render(title, content, author, tags or [], when, note_type, modules)
        rel = "/".join(p for p in (k.subdir.strip("/"), name) if p)
        gh.put_file(k.repo, k.branch, rel, text.encode("utf-8"), f"Add knowledge: {title[:60]}")
        repo, where = k.repo, f"github.com/{k.repo}/{rel}"
    else:
        text = render(title, content, cfg.author, tags or [], when, note_type, modules)
        sub = os.path.join(k.folder, k.subdir) if k.subdir else k.folder
        os.makedirs(sub, exist_ok=True)
        with open(os.path.join(sub, name), "w", encoding="utf-8") as fh:
            fh.write(text)
        rel = os.path.relpath(os.path.join(sub, name), k.folder).replace(os.sep, "/")
        repo, where = LOCAL_KNOWLEDGE, os.path.join(sub, name)
    with store.conn:
        store.put_file(repo, rel, "knowledge", text)
    return where


def update_entry(cfg: Config, store: Store, path: str, content: str, title: str = "",
                 tags: list[str] | None = None, gh: GitHub | None = None, when: datetime | None = None,
                 note_type: str = "", modules: list[str] | None = None) -> str:
    """Replace an existing note (path as listed by list_knowledge, with or without the repo prefix)."""
    repo = knowledge_repo(cfg)
    if not repo:
        raise KnowledgeError("no shared knowledge location is set - choose one in the Repo Brain app")
    path = path.strip().lstrip("/")
    if path.startswith(repo + "/"):
        path = path[len(repo) + 1:]
    old = store.read_file(repo, path)
    if old is None:
        raise KnowledgeError(f"note not found: {path} (use list_knowledge for exact paths)")
    if ".." in path.split("/"):
        raise KnowledgeError("invalid path")
    old_title = next((ln.lstrip("# ").strip() for ln in old.splitlines() if ln.startswith("# ")), path)
    old_meta = dict(re.findall(r"^- (\w+): (.*)$", old, re.M))
    title = (title or old_title).strip()
    note_type = note_type or old_meta.get("type", "")
    modules = modules if modules is not None else _clean_list(old_meta.get("modules", "").split(","))
    tags = tags if tags is not None else _clean_list(old_meta.get("tags", "").split(","))
    when = when or datetime.now()
    kind = _target(cfg)
    if kind == "github":
        gh = gh or GitHub(cfg.github_token)
        author = cfg.author or _safe_login(gh)
        text = render(title, content, author, tags, when, note_type, modules)
        gh.put_file(cfg.knowledge.repo, cfg.knowledge.branch, path, text.encode("utf-8"),
                    f"Update knowledge: {title[:60]}", sha=gh.file_sha(cfg.knowledge.repo, cfg.knowledge.branch, path))
        where = f"github.com/{cfg.knowledge.repo}/{path}"
    else:
        text = render(title, content, cfg.author, tags, when, note_type, modules)
        full = os.path.join(cfg.knowledge.folder, *path.split("/"))
        with open(full, "w", encoding="utf-8") as fh:
            fh.write(text)
        where = full
    with store.conn:
        store.put_file(repo, path, "knowledge", text)
    return where


def _safe_login(gh: GitHub) -> str:
    try:
        return gh.current_user()
    except Exception:
        return ""
