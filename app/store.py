"""Local index: files with full-text search (SQLite FTS5, trigram so Thai and code both match) plus Odoo structure."""
from __future__ import annotations

import fnmatch
import json
import posixpath
import re
import sqlite3
from datetime import datetime, timezone

from . import odoo

SCHEMA = """
CREATE TABLE IF NOT EXISTS sources(
    repo TEXT PRIMARY KEY, branch TEXT, sha TEXT, synced_at TEXT, kind TEXT, file_count INTEGER DEFAULT 0);
CREATE TABLE IF NOT EXISTS files(
    id INTEGER PRIMARY KEY, repo TEXT NOT NULL, path TEXT NOT NULL, kind TEXT NOT NULL, content TEXT NOT NULL,
    UNIQUE(repo, path));
CREATE VIRTUAL TABLE IF NOT EXISTS files_fts USING fts5(
    path, content, content='files', content_rowid='id', tokenize='trigram');
CREATE TRIGGER IF NOT EXISTS files_ai AFTER INSERT ON files BEGIN
    INSERT INTO files_fts(rowid, path, content) VALUES (new.id, new.path, new.content); END;
CREATE TRIGGER IF NOT EXISTS files_ad AFTER DELETE ON files BEGIN
    INSERT INTO files_fts(files_fts, rowid, path, content) VALUES ('delete', old.id, old.path, old.content); END;
CREATE TRIGGER IF NOT EXISTS files_au AFTER UPDATE ON files BEGIN
    INSERT INTO files_fts(files_fts, rowid, path, content) VALUES ('delete', old.id, old.path, old.content);
    INSERT INTO files_fts(rowid, path, content) VALUES (new.id, new.path, new.content); END;
CREATE TABLE IF NOT EXISTS modules(
    repo TEXT, name TEXT, path TEXT, title TEXT, summary TEXT, version TEXT, category TEXT, depends TEXT,
    PRIMARY KEY(repo, name));
CREATE TABLE IF NOT EXISTS models(
    repo TEXT, module TEXT, model TEXT, kind TEXT, by_model TEXT, class_name TEXT, description TEXT,
    path TEXT, line INTEGER);
CREATE INDEX IF NOT EXISTS models_model ON models(model);
CREATE INDEX IF NOT EXISTS models_path ON models(repo, path);
CREATE TABLE IF NOT EXISTS fields(
    repo TEXT, module TEXT, model TEXT, name TEXT, type TEXT, string TEXT, comodel TEXT, attrs TEXT,
    path TEXT, line INTEGER);
CREATE INDEX IF NOT EXISTS fields_model ON fields(model, name);
CREATE INDEX IF NOT EXISTS fields_path ON fields(repo, path);
"""

# What gets indexed. Everything else (images, fonts, binaries, big vendored files) is skipped.
TEXT_EXT = {".py", ".xml", ".csv", ".md", ".rst", ".txt", ".js", ".ts", ".jsx", ".tsx", ".scss", ".css",
            ".json", ".yml", ".yaml", ".toml", ".cfg", ".ini", ".html", ".sql", ".sh", ".po"}
SKIP_DIRS = {"node_modules", ".git", "__pycache__", "static/lib", "static/src/lib", ".venv", "dist", "build"}
SECRET_NAMES = re.compile(r"(^|/)(\.env(\..*)?|.*\.(pem|key|p12|pfx)|id_(rsa|ed25519|ecdsa).*|"
                          r"secrets?\.[\w.]+|credentials?\.[\w.]+|\.netrc|\.pgpass)$", re.I)
MAX_FILE_BYTES = 600_000
KNOWLEDGE_EXT = {".md", ".txt", ".rst", ".markdown"}


def should_index(path: str, size: int, kind: str = "code") -> bool:
    low = path.lower()
    if size > MAX_FILE_BYTES or SECRET_NAMES.search(low):
        return False
    ext = posixpath.splitext(low)[1]
    if kind == "knowledge":
        return ext in KNOWLEDGE_EXT
    if ext not in TEXT_EXT or low.endswith((".min.js", ".min.css", ".pot")):
        return False
    if ext == ".po" and posixpath.basename(low) != "th.po":  # Thai labels help map Thai questions to fields
        return False
    parts = low.split("/")
    return not any(p in SKIP_DIRS for p in parts) and not any(d in low for d in ("static/lib/", "static/src/lib/"))


def decode(data: bytes) -> str | None:
    if b"\x00" in data[:8192]:
        return None
    try:
        return data.decode("utf-8")
    except UnicodeDecodeError:
        return data.decode("utf-8", "replace")


def now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


class Store:
    def __init__(self, path: str, readonly: bool = False):
        self.path = path
        if readonly:
            self.conn = sqlite3.connect(f"file:{path}?mode=ro", uri=True, check_same_thread=False)
        else:
            self.conn = sqlite3.connect(path, check_same_thread=False)
            self.conn.execute("PRAGMA journal_mode=WAL")
            self.conn.executescript(SCHEMA)
        self.conn.row_factory = sqlite3.Row
        self.conn.execute("PRAGMA busy_timeout=10000")

    def close(self):
        self.conn.close()

    # ------------------------------------------------------------------ writing
    def clear_repo(self, repo: str):
        for table in ("files", "modules", "models", "fields"):
            self.conn.execute(f"DELETE FROM {table} WHERE repo=?", (repo,))

    def put_file(self, repo: str, path: str, kind: str, text: str):
        self.conn.execute(
            "INSERT INTO files(repo, path, kind, content) VALUES(?,?,?,?) "
            "ON CONFLICT(repo, path) DO UPDATE SET content=excluded.content, kind=excluded.kind",
            (repo, path, kind, text))

    def delete_file(self, repo: str, path: str):
        self.conn.execute("DELETE FROM files WHERE repo=? AND path=?", (repo, path))
        self.conn.execute("DELETE FROM models WHERE repo=? AND path=?", (repo, path))
        self.conn.execute("DELETE FROM fields WHERE repo=? AND path=?", (repo, path))
        if odoo.is_manifest(path):
            self.conn.execute("DELETE FROM modules WHERE repo=? AND path=?", (repo, posixpath.dirname(path)))

    def set_source(self, repo: str, branch: str, sha: str, kind: str):
        count = self.conn.execute("SELECT COUNT(*) FROM files WHERE repo=?", (repo,)).fetchone()[0]
        self.conn.execute(
            "INSERT INTO sources(repo, branch, sha, synced_at, kind, file_count) VALUES(?,?,?,?,?,?) "
            "ON CONFLICT(repo) DO UPDATE SET branch=excluded.branch, sha=excluded.sha, "
            "synced_at=excluded.synced_at, kind=excluded.kind, file_count=excluded.file_count",
            (repo, branch, sha, now_iso(), kind, count))

    def remove_source(self, repo: str):
        with self.conn:
            self.clear_repo(repo)
            self.conn.execute("DELETE FROM sources WHERE repo=?", (repo,))

    def reindex_odoo(self, repo: str, paths: list[str] | None = None):
        """Rebuild modules/models/fields for `paths` (all files of the repo when None)."""
        manifests = {posixpath.dirname(r["path"]) for r in self.conn.execute(
            "SELECT path FROM files WHERE repo=? AND (path LIKE '%__manifest__.py' OR path LIKE '%__openerp__.py')",
            (repo,)) if odoo.is_manifest(r["path"])}
        if paths is None:
            for table in ("modules", "models", "fields"):
                self.conn.execute(f"DELETE FROM {table} WHERE repo=?", (repo,))
            rows = self.conn.execute("SELECT path, content FROM files WHERE repo=? AND path LIKE '%.py'", (repo,))
        else:
            for p in paths:
                self.conn.execute("DELETE FROM models WHERE repo=? AND path=?", (repo, p))
                self.conn.execute("DELETE FROM fields WHERE repo=? AND path=?", (repo, p))
                if odoo.is_manifest(p):
                    self.conn.execute("DELETE FROM modules WHERE repo=? AND path=?", (repo, posixpath.dirname(p)))
            wanted = [p for p in paths if p.endswith(".py")]
            rows = []
            for i in range(0, len(wanted), 500):
                chunk = wanted[i:i + 500]
                rows += self.conn.execute(
                    f"SELECT path, content FROM files WHERE repo=? AND path IN ({','.join('?' * len(chunk))})",
                    (repo, *chunk)).fetchall()
        for row in list(rows):
            path, text = row["path"], row["content"]
            if odoo.is_manifest(path):
                info = odoo.parse_manifest(text)
                if info:
                    folder = posixpath.dirname(path)
                    self.conn.execute(
                        "INSERT OR REPLACE INTO modules(repo, name, path, title, summary, version, category, depends) "
                        "VALUES(?,?,?,?,?,?,?,?)",
                        (repo, posixpath.basename(folder) or repo.split("/")[-1], folder, info["title"],
                         info["summary"], info["version"], info["category"], json.dumps(info["depends"])))
                continue
            if "fields." not in text and "_inherit" not in text and "_name" not in text:
                continue
            root = odoo.module_root(path, manifests)
            module = posixpath.basename(root) if root else ""
            for m in odoo.parse_models(text):
                self.conn.execute(
                    "INSERT INTO models(repo, module, model, kind, by_model, class_name, description, path, line) "
                    "VALUES(?,?,?,?,?,?,?,?,?)",
                    (repo, module, m["model"], m["kind"], m.get("by", ""), m["class_name"], m["description"],
                     path, m["line"]))
                for f in m["fields"]:
                    self.conn.execute(
                        "INSERT INTO fields(repo, module, model, name, type, string, comodel, attrs, path, line) "
                        "VALUES(?,?,?,?,?,?,?,?,?,?)",
                        (repo, module, m["model"], f["name"], f["type"], f["string"], f["comodel"], f["attrs"],
                         path, f["line"]))

    # ------------------------------------------------------------------ reading
    def sources(self) -> list[dict]:
        return [dict(r) for r in self.conn.execute("SELECT * FROM sources ORDER BY kind, repo")]

    def source(self, repo: str) -> dict | None:
        r = self.conn.execute("SELECT * FROM sources WHERE repo=?", (repo,)).fetchone()
        return dict(r) if r else None

    def counts(self) -> dict:
        q = lambda sql: self.conn.execute(sql).fetchone()[0]  # noqa: E731
        return {"files": q("SELECT COUNT(*) FROM files WHERE kind='code'"),
                "knowledge": q("SELECT COUNT(*) FROM files WHERE kind='knowledge' AND path NOT LIKE 'questions/%'"),
                "questions": q("SELECT COUNT(*) FROM files WHERE kind='knowledge' AND path LIKE 'questions/%'"),
                "modules": q("SELECT COUNT(*) FROM modules"),
                "models": q("SELECT COUNT(DISTINCT model) FROM models")}

    def read_file(self, repo: str, path: str) -> str | None:
        row = self.conn.execute("SELECT content FROM files WHERE repo=? AND path=?", (repo, path)).fetchone()
        if row is None and not repo:
            row = self.conn.execute("SELECT content FROM files WHERE path=? LIMIT 1", (path,)).fetchone()
        return row["content"] if row else None

    def find_paths(self, path: str) -> list[dict]:
        return [dict(r) for r in self.conn.execute(
            "SELECT repo, path FROM files WHERE path=? OR path LIKE ? LIMIT 20", (path, "%/" + path))]

    def list_files(self, repo: str = "", prefix: str = "", pattern: str = "", kind: str = "", limit: int = 300):
        sql, args = "SELECT repo, path, length(content) AS size FROM files WHERE 1=1", []
        if repo:
            sql += " AND repo=?"
            args.append(repo)
        if prefix:
            sql += " AND path LIKE ?"
            args.append(prefix.rstrip("/") + "/%")
        if kind:
            sql += " AND kind=?"
            args.append(kind)
        rows = [dict(r) for r in self.conn.execute(sql + " ORDER BY repo, path", args)]
        if pattern:
            rows = [r for r in rows if fnmatch.fnmatch(r["path"], pattern) or fnmatch.fnmatch(posixpath.basename(r["path"]), pattern)]
        return rows[:limit], len(rows)

    def search(self, query: str, kind: str = "code", repo: str = "", path_filter: str = "", limit: int = 10):
        """Full-text search. Returns [{repo, path, kind, hits: [(line_no, [context lines])]}]."""
        terms = [t for t in re.findall(r'"[^"]+"|\S+', query or "") if t]
        terms = [t.strip('"') for t in terms]
        if not terms:
            return []
        long_terms = [t for t in terms if len(t) >= 3]
        base = "SELECT f.repo, f.path, f.kind, f.content FROM files f"
        where, args = [], []
        if kind:
            where.append("f.kind=?")
            args.append(kind)
        if repo:
            where.append("f.repo=?")
            args.append(repo)
        if path_filter:
            where.append("f.path GLOB ?")
            args.append(path_filter if any(c in path_filter for c in "*?[") else f"*{path_filter}*")
        rows = []
        if long_terms:
            for joiner in (" AND ", " OR "):
                match = joiner.join('"' + t.replace('"', '""') + '"' for t in long_terms)
                sql = (base + " JOIN files_fts ON files_fts.rowid=f.id WHERE files_fts MATCH ?"
                       + "".join(" AND " + w for w in where) + " ORDER BY bm25(files_fts, 4.0, 1.0) LIMIT ?")
                rows = self.conn.execute(sql, (match, *args, limit * 3)).fetchall()
                if rows or len(long_terms) == 1:
                    break
        else:  # only short terms (e.g. "id"): plain substring scan
            sql = base + " WHERE " + " AND ".join(where + ["f.content LIKE ?"]) + " LIMIT ?"
            rows = self.conn.execute(sql, (*args, f"%{terms[0]}%", limit * 3)).fetchall()
        results = []
        for r in rows:
            hits = _snippets(r["content"], terms)
            if hits or any(t.lower() in r["path"].lower() for t in terms):
                results.append({"repo": r["repo"], "path": r["path"], "kind": r["kind"], "hits": hits})
            if len(results) >= limit:
                break
        return results

    # ---- odoo
    def modules(self, query: str = "", repo: str = "") -> list[dict]:
        sql, args = "SELECT * FROM modules WHERE 1=1", []
        if repo:
            sql += " AND repo=?"
            args.append(repo)
        if query:
            sql += " AND (name LIKE ? OR title LIKE ? OR summary LIKE ?)"
            args += [f"%{query}%"] * 3
        out = []
        for r in self.conn.execute(sql + " ORDER BY name", args):
            d = dict(r)
            d["depends"] = json.loads(d["depends"] or "[]")
            out.append(d)
        return out

    def module(self, name: str) -> dict | None:
        rows = self.modules()
        for d in rows:
            if d["name"] == name:
                return d
        return None

    def reverse_depends(self, name: str) -> list[str]:
        return sorted(d["name"] for d in self.modules() if name in d["depends"])

    def model_rows(self, model: str = "", module: str = "", repo: str = "") -> list[dict]:
        sql, args = "SELECT * FROM models WHERE 1=1", []
        for col, val in (("model", model), ("module", module), ("repo", repo)):
            if val:
                sql += f" AND {col}=?"
                args.append(val)
        return [dict(r) for r in self.conn.execute(sql + " ORDER BY model, kind, module", args)]

    def field_rows(self, model: str = "", name: str = "", module: str = "") -> list[dict]:
        sql, args = "SELECT * FROM fields WHERE 1=1", []
        for col, val in (("model", model), ("name", name), ("module", module)):
            if val:
                sql += f" AND {col}=?"
                args.append(val)
        return [dict(r) for r in self.conn.execute(sql + " ORDER BY model, module, line", args)]

    def similar_models(self, text: str, limit: int = 15) -> list[str]:
        return [r[0] for r in self.conn.execute(
            "SELECT DISTINCT model FROM models WHERE model LIKE ? ORDER BY length(model) LIMIT ?",
            (f"%{text}%", limit))]

    def missing_depends(self) -> list[str]:
        mods = self.modules()
        have = {m["name"] for m in mods}
        return sorted({d for m in mods for d in m["depends"]} - have)


def _snippets(content: str, terms: list[str], max_hits: int = 3, context: int = 2):
    lines = content.splitlines()
    low_terms = [t.lower() for t in terms]
    scored = []
    for i, line in enumerate(lines):
        low = line.lower()
        n = sum(1 for t in low_terms if t in low)
        if n:
            scored.append((n, i))
    scored.sort(key=lambda x: (-x[0], x[1]))
    chosen, hits = [], []
    for _, i in scored:
        if any(abs(i - j) <= context * 2 for j in chosen):
            continue
        chosen.append(i)
        if len(chosen) >= max_hits:
            break
    for i in sorted(chosen):
        lo, hi = max(0, i - context), min(len(lines), i + context + 1)
        hits.append((i + 1, [(n + 1, lines[n][:300]) for n in range(lo, hi)]))
    return hits
