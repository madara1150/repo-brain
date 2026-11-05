"""The "Update" button: bring the local index up to date with GitHub (and the shared knowledge)."""
from __future__ import annotations

import os
import tarfile
import threading
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass

from . import odoo, team_repos
from .config import Config
from .github import GitHub, GitHubError
from .store import Store, decode, should_index

MAX_INCREMENTAL_FILES = 250
LOCAL_KNOWLEDGE = "local/knowledge"


class Cancelled(Exception):
    pass


@dataclass
class SyncResult:
    repo: str
    mode: str          # "full" | "incremental" | "unchanged" | "folder" | "error"
    old_sha: str = ""
    new_sha: str = ""
    changed: int = 0
    error: str = ""


@dataclass
class UpdateCheck:
    repo: str
    branch: str
    local_sha: str
    remote_sha: str
    error: str = ""

    @property
    def has_update(self) -> bool:
        return bool(self.remote_sha) and self.remote_sha != self.local_sha


def knowledge_repo(cfg: Config) -> str:
    k = cfg.knowledge
    if k.mode == "github" and k.repo:
        return k.repo
    if k.mode == "folder" and k.folder:
        return LOCAL_KNOWLEDGE
    return ""


def planned_sources(cfg: Config) -> list[tuple[str, str, str]]:
    """(repo, branch, kind) for every GitHub repository in the config."""
    out = [(s.repo, s.branch, "code") for s in cfg.sources]
    if cfg.knowledge.mode == "github" and cfg.knowledge.repo:
        out.append((cfg.knowledge.repo, cfg.knowledge.branch, "knowledge"))
    return out


def check_updates(cfg: Config, store: Store, gh: GitHub | None = None) -> list[UpdateCheck]:
    """Compare the indexed commit with the latest one on GitHub; reads no code."""
    gh = gh or GitHub(cfg.github_token)
    out = []
    for repo, branch, _kind in planned_sources(cfg):
        local = store.source(repo) or {}
        try:
            br = branch or local.get("branch") or gh.default_branch(repo)
            out.append(UpdateCheck(repo, br, local.get("sha", ""), gh.head_sha(repo, br)))
        except GitHubError as e:
            out.append(UpdateCheck(repo, branch, local.get("sha", ""), "", str(e)))
    return out


class Syncer:
    def __init__(self, cfg: Config, store: Store, gh: GitHub | None = None, progress=None,
                 cancel: threading.Event | None = None):
        self.cfg = cfg
        self.store = store
        self.gh = gh or GitHub(cfg.github_token)
        self.progress = progress or (lambda msg, frac=None: None)
        self.cancel = cancel or threading.Event()
        self.team_changed = False
        self.team_error = ""

    def _check_cancel(self):
        if self.cancel.is_set():
            raise Cancelled()

    def apply_team_list(self) -> bool:
        """Follow the team repository list (repos.txt) before updating; True when the sources changed."""
        self.team_changed = False
        try:
            entries = team_repos.fetch(self.cfg, self.gh)
        except Exception as e:  # an unreadable list must not stop the update
            self.team_error = str(e)
            return False
        if entries is not None:
            self.team_changed = team_repos.apply(self.cfg, entries)
        return self.team_changed

    def run(self) -> list[SyncResult]:
        results = []
        self.team_error = ""
        self.progress(team_repos.FILE, 0.0)
        self.apply_team_list()
        wanted = planned_sources(self.cfg)
        # forget repositories that were removed from the settings
        keep = {r for r, _, _ in wanted} | ({LOCAL_KNOWLEDGE} if self.cfg.knowledge.mode == "folder" else set())
        for src in self.store.sources():
            if src["repo"] not in keep:
                self.store.remove_source(src["repo"])
        total = len(wanted) + (1 if self.cfg.knowledge.mode == "folder" else 0)
        for i, (repo, branch, kind) in enumerate(wanted):
            self._check_cancel()
            self.progress(repo, i / max(total, 1))
            try:
                results.append(self.sync_repo(repo, branch, kind))
            except Cancelled:
                raise
            except Exception as e:  # keep going with the other repositories
                results.append(SyncResult(repo, "error", error=str(e)))
        if self.cfg.knowledge.mode == "folder":
            self.progress(self.cfg.knowledge.folder, (total - 1) / max(total, 1))
            try:
                results.append(self.sync_folder(self.cfg.knowledge.folder))
            except Exception as e:
                results.append(SyncResult(LOCAL_KNOWLEDGE, "error", error=str(e)))
        self.progress("", 1.0)
        return results

    def sync_repo(self, repo: str, branch: str, kind: str = "code") -> SyncResult:
        local = self.store.source(repo) or {}
        branch = branch or local.get("branch") or self.gh.default_branch(repo)
        head = self.gh.head_sha(repo, branch)
        old = local.get("sha", "") if local.get("branch") == branch else ""
        if old == head:
            with self.store.conn:
                self.store.set_source(repo, branch, head, kind)  # refresh the "checked" time
            return SyncResult(repo, "unchanged", old, head)
        if old:
            try:
                res = self._incremental(repo, branch, kind, old, head)
                if res is not None:
                    return res
            except GitHubError:
                pass  # e.g. history rewritten (force push): fall back to a full download
        return self._full(repo, branch, kind, head, old)

    def _incremental(self, repo, branch, kind, old, head) -> SyncResult | None:
        cmp = self.gh.compare(repo, old, head)
        files = cmp.get("files") or []
        if cmp.get("status") not in ("ahead", "identical") or len(files) >= MAX_INCREMENTAL_FILES:
            return None
        wanted = [f["filename"] for f in files if f.get("status") != "removed" and should_index(f["filename"], 0, kind)]

        def fetch(path):
            self._check_cancel()
            return path, decode(self.gh.raw_file(repo, head, path))

        fetched = {}
        with ThreadPoolExecutor(max_workers=8) as pool:
            for n, (path, text) in enumerate(pool.map(fetch, wanted)):
                self.progress(f"{repo}: {n + 1}/{len(wanted)} {path}", None)
                if text is not None and len(text.encode("utf-8", "ignore")) <= 600_000:
                    fetched[path] = text
        touched = []
        with self.store.conn:
            for f in files:
                path, status = f["filename"], f.get("status")
                if status == "renamed" and f.get("previous_filename"):
                    self.store.delete_file(repo, f["previous_filename"])
                    touched.append(f["previous_filename"])
                if path in fetched:
                    self.store.put_file(repo, path, kind, fetched[path])
                else:
                    self.store.delete_file(repo, path)
                touched.append(path)
            if kind == "code":
                if any(odoo.is_manifest(p) for p in touched):
                    self.store.reindex_odoo(repo)
                else:
                    self.store.reindex_odoo(repo, touched)
            self.store.set_source(repo, branch, head, kind)
        return SyncResult(repo, "incremental", old, head, len(files))

    def _full(self, repo, branch, kind, head, old) -> SyncResult:
        self.progress(f"{repo}: downloading", None)
        entries = []
        with self.gh.open_tarball(repo, head) as resp:
            with tarfile.open(fileobj=resp, mode="r|gz") as tar:
                for member in tar:
                    self._check_cancel()
                    if not member.isfile():
                        continue
                    path = member.name.split("/", 1)[1] if "/" in member.name else ""
                    if not path or not should_index(path, member.size, kind):
                        continue
                    fh = tar.extractfile(member)
                    text = decode(fh.read()) if fh else None
                    if text is not None:
                        entries.append((path, text))
                    if len(entries) % 200 == 0:
                        self.progress(f"{repo}: {len(entries)} files", None)
        self._check_cancel()
        self.progress(f"{repo}: indexing {len(entries)} files", None)
        with self.store.conn:
            self.store.clear_repo(repo)
            for path, text in entries:
                self.store.put_file(repo, path, kind, text)
            if kind == "code":
                self.store.reindex_odoo(repo)
            self.store.set_source(repo, branch, head, kind)
        return SyncResult(repo, "full", old, head, len(entries))

    def sync_folder(self, folder: str) -> SyncResult:
        if not os.path.isdir(folder):
            raise FileNotFoundError(folder)
        entries = []
        for root, dirs, names in os.walk(folder):
            dirs[:] = [d for d in dirs if not d.startswith(".")]
            for name in names:
                full = os.path.join(root, name)
                rel = os.path.relpath(full, folder).replace(os.sep, "/")
                try:
                    size = os.path.getsize(full)
                except OSError:
                    continue
                if should_index(rel, size, "knowledge"):
                    with open(full, "rb") as fh:
                        text = decode(fh.read())
                    if text is not None:
                        entries.append((rel, text))
        with self.store.conn:
            self.store.clear_repo(LOCAL_KNOWLEDGE)
            for rel, text in entries:
                self.store.put_file(LOCAL_KNOWLEDGE, rel, "knowledge", text)
            self.store.set_source(LOCAL_KNOWLEDGE, "", "", "knowledge")
        return SyncResult(LOCAL_KNOWLEDGE, "folder", changed=len(entries))
