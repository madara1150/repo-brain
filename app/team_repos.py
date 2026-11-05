"""The team's repository list (`repos.txt` in the shared knowledge location).

One person sets up the repositories once and saves them as the team list; every other copy of the app
reads that list on "Update" and adds (or drops) those repositories by itself, so nobody types them again.

Format, one repository per line (`#` starts a comment, the branch is optional):

    owner/name 16.0
    https://github.com/owner/other
"""
from __future__ import annotations

import os
from datetime import datetime

from .config import Config, Source
from .github import GitHub, GitHubError, parse_repo

FILE = "repos.txt"
HEADER = ("# Repositories every Repo Brain in the team reads, one per line: owner/name [branch]\n"
          "# Saved from the Repo Brain app; you can also edit this file by hand.\n")


def parse(text: str) -> list[tuple[str, str]]:
    out, seen = [], set()
    for line in (text or "").splitlines():
        line = line.split("#", 1)[0].strip()
        if not line:
            continue
        parts = line.split()
        repo = parse_repo(parts[0])
        if not repo or repo.lower() in seen:
            continue
        seen.add(repo.lower())
        out.append((repo, parts[1] if len(parts) > 1 else ""))
    return out


def render(sources) -> str:
    lines = [f"{s.repo} {s.branch}".strip() for s in sources]
    return HEADER + "\n" + "\n".join(lines) + "\n"


def fetch(cfg: Config, gh: GitHub) -> list[tuple[str, str]] | None:
    """The team list, or None when the knowledge location has no repos.txt (or none is set)."""
    k = cfg.knowledge
    if k.mode == "github" and k.repo:
        try:
            branch = k.branch or gh.default_branch(k.repo)
            return parse(gh.raw_file(k.repo, branch, FILE).decode("utf-8", "replace"))
        except GitHubError as e:
            if e.status == 404:
                return None
            raise
    if k.mode == "folder" and k.folder:
        path = os.path.join(k.folder, FILE)
        if not os.path.isfile(path):
            return None
        with open(path, encoding="utf-8") as fh:
            return parse(fh.read())
    return None


def apply(cfg: Config, entries: list[tuple[str, str]]) -> bool:
    """Make cfg.sources follow the team list: team repositories first (in list order), then your own.

    A repository that came from the team list and is no longer on it is dropped; ones you added yourself
    are kept. Returns True when the sources changed.
    """
    before = [(s.repo, s.branch, s.team) for s in cfg.sources]
    mine = {s.repo.lower(): s for s in cfg.sources}
    team_keys = {repo.lower() for repo, _ in entries}
    team = []
    for repo, branch in entries:
        old = mine.get(repo.lower())
        team.append(Source(repo, branch or (old.branch if old else ""), team=True))
    own = [s for s in cfg.sources if not s.team and s.repo.lower() not in team_keys]
    cfg.sources = team + own
    return before != [(s.repo, s.branch, s.team) for s in cfg.sources]


def publish(cfg: Config, gh: GitHub | None = None) -> str:
    """Save the current repositories as the team list; returns where it was written."""
    text = render(cfg.sources).encode("utf-8")
    k = cfg.knowledge
    if k.mode == "github" and k.repo:
        gh = gh or GitHub(cfg.github_token)
        sha = ""
        try:
            sha = gh.file_sha(k.repo, k.branch, FILE)
        except GitHubError as e:
            if e.status != 404:
                raise
        stamp = datetime.now().strftime("%Y-%m-%d %H:%M")
        gh.put_file(k.repo, k.branch, FILE, text, f"Update team repository list ({stamp})", sha=sha)
        where = f"{k.repo}/{FILE}"
    elif k.mode == "folder" and k.folder:
        path = os.path.join(k.folder, FILE)
        with open(path, "wb") as fh:
            fh.write(text)
        where = path
    else:
        raise ValueError("no shared knowledge location is set")
    for s in cfg.sources:
        s.team = True
    return where
