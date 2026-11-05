"""Team questions: open questions stored as Markdown files in the knowledge repository (questions/*.md).

Anyone on the team answers in the app (or through Claude); the answer is appended to the file with the
answerer's name and pushed, so teammates get it on their next Update and Claude can use it.

File format:
    # <question>

    - status: open | answered
    - area: <Thai area>
    - note: knowledge/<related note>.md
    - asked: YYYY-MM-DD
    - asked_by: <who asked>

    ## รายละเอียด
    <context>

    ## คำตอบ
    ### <answerer> · YYYY-MM-DD HH:MM
    <answer>
"""
from __future__ import annotations

import os
import re
from datetime import datetime

from .config import Config
from .github import GitHub, GitHubError
from .knowledge import KnowledgeError, slugify
from .store import Store
from .sync import knowledge_repo

QUESTION_DIR = "questions"
ANSWERS_HEADING = "## คำตอบ"


def parse(text: str) -> dict:
    lines = text.splitlines()
    title = next((ln[2:].strip() for ln in lines if ln.startswith("# ")), "")
    meta = dict(re.findall(r"^- (\w+): (.*)$", text.split("\n## ", 1)[0], re.M))
    details = ""
    m = re.search(r"\n## รายละเอียด\n(.*?)(?=\n## |\Z)", text, re.S)
    if m:
        details = m.group(1).strip()
    answers = []
    if ANSWERS_HEADING in text:
        block = text.split(ANSWERS_HEADING, 1)[1]
        for am in re.finditer(r"^### (.+?) · (\d{4}-\d{2}-\d{2}(?: \d{2}:\d{2})?)\n(.*?)(?=^### |\Z)", block, re.S | re.M):
            answers.append({"author": am.group(1).strip(), "date": am.group(2), "text": am.group(3).strip()})
    status = meta.get("status", "open").strip()
    if answers and status == "open":
        status = "answered"
    return {"title": title, "meta": meta, "status": status, "area": meta.get("area", "").strip(),
            "note": meta.get("note", "").strip(), "details": details, "answers": answers}


def add_answer(text: str, author: str, answer: str, when: datetime) -> str:
    """Append an answer and mark the question answered."""
    answer = answer.strip()
    if not answer:
        raise KnowledgeError("the answer is empty")
    if re.search(r"^- status: .*$", text, re.M):
        text = re.sub(r"^- status: .*$", "- status: answered", text, count=1, flags=re.M)
    if ANSWERS_HEADING not in text:
        text = text.rstrip("\n") + f"\n\n{ANSWERS_HEADING}\n"
    entry = f"### {author or 'ไม่ระบุชื่อ'} · {when:%Y-%m-%d %H:%M}\n{answer}\n"
    return text.rstrip("\n") + "\n" + entry


def render_question(title: str, area: str, details: str, asked_by: str, when: datetime, note: str = "") -> str:
    lines = [f"# {title.strip()}", "", "- status: open", f"- area: {area.strip()}"]
    if note:
        lines.append(f"- note: {note.strip()}")
    lines += [f"- asked: {when:%Y-%m-%d}", f"- asked_by: {asked_by or 'ไม่ระบุชื่อ'}", "",
              "## รายละเอียด", details.strip() or "-", "", ANSWERS_HEADING, ""]
    return "\n".join(lines)


def list_questions(store: Store, repo: str) -> list[dict]:
    rows, _ = store.list_files(repo=repo, prefix=QUESTION_DIR, kind="knowledge", limit=5000)
    out = []
    for r in rows:
        text = store.read_file(r["repo"], r["path"]) or ""
        q = parse(text)
        q["path"] = r["path"]
        q["repo"] = r["repo"]
        out.append(q)
    return sorted(out, key=lambda q: q["path"])


def _author(cfg: Config, gh: GitHub | None) -> str:
    if cfg.author:
        return cfg.author
    if gh is not None:
        try:
            return gh.current_user()
        except Exception:
            return ""
    return ""


def _github_update(cfg: Config, gh: GitHub, path: str, change, message: str) -> str:
    """Read the latest file from GitHub, apply `change`, write it back; retry once if someone else wrote first."""
    k = cfg.knowledge
    for attempt in range(3):
        raw, sha = gh.get_file(k.repo, k.branch, path)
        new = change(raw.decode("utf-8"))
        try:
            gh.put_file(k.repo, k.branch, path, new.encode("utf-8"), message, sha=sha)
            return new
        except GitHubError as e:
            if e.status in (409, 422) and attempt < 2:
                continue  # the file changed meanwhile: re-read and re-apply
            raise
    raise KnowledgeError("could not save the answer, please try again")


def answer_question(cfg: Config, store: Store, path: str, answer: str, gh: GitHub | None = None,
                    when: datetime | None = None) -> str:
    """Append an answer to questions/<file>.md and index it locally right away. Returns the new file text."""
    repo = knowledge_repo(cfg)
    if not repo:
        raise KnowledgeError("no shared knowledge location is set - choose one in the Repo Brain app")
    path = path.strip().lstrip("/")
    if path.startswith(repo + "/"):
        path = path[len(repo) + 1:]
    if not path.startswith(QUESTION_DIR + "/") or ".." in path.split("/"):
        raise KnowledgeError(f"not a question file: {path}")
    if store.read_file(repo, path) is None:
        raise KnowledgeError(f"question not found: {path} (press Update first)")
    when = when or datetime.now()
    k = cfg.knowledge
    if k.mode == "github":
        gh = gh or GitHub(cfg.github_token)
        author = _author(cfg, gh)
        title = parse(store.read_file(repo, path) or "")["title"][:60]
        new = _github_update(cfg, gh, path, lambda t: add_answer(t, author, answer, when), f"Answer question: {title}")
    else:
        full = os.path.join(k.folder, *path.split("/"))
        with open(full, encoding="utf-8") as fh:
            new = add_answer(fh.read(), cfg.author, answer, when)
        with open(full, "w", encoding="utf-8") as fh:
            fh.write(new)
    with store.conn:
        store.put_file(repo, path, "knowledge", new)
    return new


def ask_question(cfg: Config, store: Store, title: str, area: str, details: str = "", note: str = "",
                 gh: GitHub | None = None, when: datetime | None = None) -> str:
    """Add a new open question for the team. Returns its path."""
    title = (title or "").strip()
    if not title:
        raise KnowledgeError("the question is empty")
    repo = knowledge_repo(cfg)
    if not repo:
        raise KnowledgeError("no shared knowledge location is set - choose one in the Repo Brain app")
    when = when or datetime.now()
    name = f"{QUESTION_DIR}/{when:%Y%m%d-%H%M%S}-{slugify(title)}.md"
    k = cfg.knowledge
    if k.mode == "github":
        gh = gh or GitHub(cfg.github_token)
        text = render_question(title, area, details, _author(cfg, gh), when, note)
        gh.put_file(k.repo, k.branch, name, text.encode("utf-8"), f"Ask question: {title[:60]}")
    else:
        text = render_question(title, area, details, cfg.author, when, note)
        os.makedirs(os.path.join(k.folder, QUESTION_DIR), exist_ok=True)
        with open(os.path.join(k.folder, *name.split("/")), "w", encoding="utf-8") as fh:
            fh.write(text)
    with store.conn:
        store.put_file(repo, name, "knowledge", text)
    return name
