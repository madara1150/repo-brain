"""MCP server over stdio (JSON-RPC 2.0, one message per line) that Claude Desktop starts.

It only reads the local index. The index changes only when someone presses Update in the app,
so answers always come from a known snapshot (the commit is reported by repo_status).
"""
from __future__ import annotations

import json
import os
import sys
import traceback

from . import config as C
from .store import Store
from .teach import NOTE_TYPES, PROMPTS, get_prompt

PROTOCOL_VERSIONS = ["2025-11-25", "2025-06-18", "2025-03-26", "2024-11-05"]
READ_LIMIT = 400

INSTRUCTIONS = """Repo Brain gives you a local, searchable snapshot of the team's code repositories (often an \
Odoo system together with its OCA dependencies) plus the team's shared knowledge notes.
- Call repo_status first in a conversation to learn which repositories and commits the snapshot holds.
- Look things up before answering; never guess file contents. Cite sources as repo/path:line.
- Odoo questions: odoo_model (where a model is defined/extended, its fields), odoo_module (manifest, \
dependencies, models), then read_file for details. Thai labels are searchable with search_code (th.po and views).
- Team knowledge (business rules, conventions, how-tos written by the team) comes from search_knowledge; \
prefer it for "how do we..." questions and mention when it disagrees with the code.
- add_knowledge / update_knowledge save a note for the whole team: only after the user asked to record something AND confirmed the final draft. Never store personal data (names, phones, emails, ID/account numbers) - use roles.
- Team questions (questions/*.md): answered ones are facts confirmed by the team - prefer them over guesses from code; \
open ones mean nobody has confirmed it yet, so say so. When a user knows an answer, they may give it to you and you save it \
with answer_question after they confirm the wording.
- When the user wants to teach you (a LINE chat case, screenshots, or a work flow), interview them a few questions at a time, check against the code, explain it back until they agree, show the draft, then save on confirmation (the analyze_line_case and teach_flow prompts describe this in detail).
- The snapshot is only refreshed when a user presses Update in the Repo Brain app. If something seems \
missing or outdated, say so and suggest pressing Update (check_for_updates tells whether GitHub has newer commits)."""


def _tool(name, description, props=None, required=None):
    return {"name": name, "description": description,
            "inputSchema": {"type": "object", "properties": props or {}, "required": required or []}}


S = {"type": "string"}
I = {"type": "integer"}
TOOLS = [
    _tool("repo_status", "Which repositories are in the snapshot, at which commit, when they were last updated, "
          "and how much is indexed. Call this first."),
    _tool("search_code", "Full-text search over the indexed code and docs (Python, XML views, CSV, Markdown, Thai "
          "th.po translations...). Returns matching files with line numbers and surrounding lines. Terms are "
          "ANDed (falls back to OR); quote a phrase with double quotes. Terms shorter than 3 characters match weakly.",
          {"query": S, "repo": {**S, "description": "limit to one repository, e.g. owner/name"},
           "path_filter": {**S, "description": "glob on the path, e.g. '*/models/*.py' or 'purchase*'"},
           "limit": {**I, "description": "max files (default 10, max 30)"}}, ["query"]),
    _tool("read_file", f"Read a file from the snapshot with line numbers (at most {READ_LIMIT} lines per call).",
          {"path": {**S, "description": "path inside the repo, e.g. purchase_request/models/purchase_request.py"},
           "repo": {**S, "description": "owner/name; optional when the path is unique"},
           "start_line": I, "end_line": I}, ["path"]),
    _tool("list_files", "List indexed files, optionally under a folder or matching a glob.",
          {"repo": S, "path_prefix": S, "pattern": {**S, "description": "glob such as '*.xml' or '*wizard*'"}}),
    _tool("list_modules", "List Odoo modules (addons) in the snapshot with their titles; filter by text.",
          {"query": S, "repo": S}),
    _tool("odoo_module", "Details of one Odoo module: manifest (title, summary, version), dependencies (and whether "
          "each is in the snapshot), modules that depend on it, models it defines or extends, docs it ships.",
          {"name": {**S, "description": "technical module name, e.g. purchase_request"}}, ["name"]),
    _tool("odoo_model", "Where an Odoo model is defined and every module that extends it (with path:line), plus its "
          "fields grouped by module. Pass field to get only that field's declarations.",
          {"model": {**S, "description": "e.g. account.move"}, "field": S}, ["model"]),
    _tool("search_knowledge", "Search the team's shared knowledge notes (business rules, conventions, how-tos).",
          {"query": S, "limit": I}, ["query"]),
    _tool("list_knowledge", "List all team knowledge notes (titles and paths)."),
    _tool("add_knowledge", "Save a NEW note to the team's shared knowledge (pushed to the team's knowledge repository; "
          "teammates get it after they press Update). Only call after the user has read the final draft in the chat "
          "and explicitly confirmed it. Search existing notes first and prefer update_knowledge for the same topic. "
          "Never include personal data (names, phone numbers, emails, ID/account numbers): use roles instead.",
          {"title": {**S, "description": "the question or problem people would search for"},
           "content": {**S, "description": "Markdown body following the template (without repeating the title)"},
           "type": {"type": "string", "enum": NOTE_TYPES,
                    "description": "case = solved Q&A/problem, flow = business process, rule = policy/condition, "
                                   "howto = step-by-step task, faq = short answer"},
           "modules": {"type": "array", "items": S, "description": "related Odoo modules"},
           "tags": {"type": "array", "items": S}}, ["title", "content"]),
    _tool("update_knowledge", "Replace an existing team note (same rules as add_knowledge: only after the user confirmed "
          "the full new version). Read it first with read_file; path as shown by list_knowledge.",
          {"path": S, "content": {**S, "description": "full new Markdown body (without the title)"},
           "title": {**S, "description": "new title; omit to keep"}, "type": {"type": "string", "enum": NOTE_TYPES},
           "modules": {"type": "array", "items": S}, "tags": {"type": "array", "items": S}}, ["path", "content"]),
    _tool("list_questions", "List the team's questions (questions/*.md in the knowledge repository): open ones waiting "
          "for an answer, or answered ones whose answers are facts confirmed by the team. Read one with read_file.",
          {"status": {"type": "string", "enum": ["open", "answered", "all"], "description": "default open"},
           "area": {**S, "description": "Thai area name, e.g. งบประมาณ"}, "query": S}),
    _tool("answer_question", "Append an answer to a team question and push it for everyone. Only use when the user "
          "states the answer themselves and confirms the exact wording; never invent or infer answers. No personal data.",
          {"path": {**S, "description": "questions/<file>.md as listed by list_questions"},
           "answer": S}, ["path", "answer"]),
    _tool("ask_question", "Add a new open question for the team when the user asks to record something nobody knows yet.",
          {"question": S, "area": S, "details": S}, ["question", "area"]),
    _tool("check_for_updates", "Ask GitHub whether newer commits exist than the snapshot (reads no code). The "
          "snapshot itself is only updated with the Update button in the Repo Brain app."),
]


class ToolError(Exception):
    pass


class Server:
    def __init__(self, index_path: str | None = None):
        self.index_path = index_path or C.index_path()
        self._store = None

    def close(self):
        if self._store is not None:
            self._store.close()
            self._store = None

    @property
    def store(self) -> Store:
        if self._store is None:
            if not os.path.exists(self.index_path):
                raise ToolError("The snapshot is empty. Open the Repo Brain app, add repositories and press Update.")
            self._store = Store(self.index_path)
        return self._store

    # ------------------------------------------------------------------ tools
    def t_repo_status(self, a):
        st, cfg = self.store, C.load_config()
        lines = ["Snapshot (refreshed only when someone presses Update in the Repo Brain app):"]
        for s in st.sources():
            sha = (s["sha"] or "")[:10] or "-"
            lines.append(f"- [{s['kind']}] {s['repo']} @ {s['branch'] or '-'} commit {sha}, "
                         f"updated {s['synced_at']}, {s['file_count']} files")
        if len(lines) == 1:
            lines.append("- nothing indexed yet")
        c = st.counts()
        lines.append(f"Totals: {c['files']} code files, {c['modules']} Odoo modules, {c['models']} models, "
                     f"{c['knowledge']} knowledge notes, {c['questions']} team questions. Odoo version setting: {cfg.odoo_version}.")
        missing = st.missing_depends()
        if missing:
            lines.append(f"Dependencies not in the snapshot ({len(missing)}; usually Odoo core): "
                         + ", ".join(missing[:60]) + (" ..." if len(missing) > 60 else ""))
        return "\n".join(lines)

    def _format_hits(self, results):
        out = []
        for r in results:
            out.append(f"## {r['repo']}/{r['path']}")
            for _line, ctx in r["hits"]:
                out.extend(f"{n:>5}: {text}" for n, text in ctx)
                out.append("  ...")
        return "\n".join(out)

    def t_search_code(self, a):
        limit = max(1, min(int(a.get("limit") or 10), 30))
        res = self.store.search(a["query"], "code", a.get("repo", ""), a.get("path_filter", ""), limit)
        return self._format_hits(res) if res else f"No matches for {a['query']!r}."

    def t_read_file(self, a):
        path = a["path"].strip().lstrip("/")
        repo = (a.get("repo") or "").strip()
        st = self.store
        if repo and path.startswith(repo + "/"):
            path = path[len(repo) + 1:]
        text = st.read_file(repo, path)
        if text is None and not repo:  # "owner/name/path" given as path
            parts = path.split("/", 2)
            if len(parts) == 3:
                text = st.read_file(f"{parts[0]}/{parts[1]}", parts[2])
                if text is not None:
                    repo, path = f"{parts[0]}/{parts[1]}", parts[2]
        if text is None:
            cands = st.find_paths(path)
            if len(cands) == 1:
                repo, path = cands[0]["repo"], cands[0]["path"]
                text = st.read_file(repo, path)
            elif cands:
                return "Several files match; pass repo and the full path:\n" + "\n".join(
                    f"- {c['repo']}/{c['path']}" for c in cands)
        if text is None:
            raise ToolError(f"File not found in the snapshot: {path}")
        lines = text.splitlines()
        start = max(1, int(a.get("start_line") or 1))
        end = min(len(lines), int(a.get("end_line") or start + READ_LIMIT - 1), start + READ_LIMIT - 1)
        body = "\n".join(f"{n:>5}: {lines[n - 1]}" for n in range(start, end + 1))
        more = f"\n(lines {start}-{end} of {len(lines)}; read more with start_line={end + 1})" if end < len(lines) else ""
        return f"{repo + '/' if repo else ''}{path}\n{body}{more}"

    def t_list_files(self, a):
        rows, total = self.store.list_files(a.get("repo", ""), a.get("path_prefix", ""), a.get("pattern", ""))
        if not rows:
            return "No files."
        out = [f"{r['repo']}/{r['path']}" for r in rows]
        if total > len(rows):
            out.append(f"... {total - len(rows)} more; narrow with path_prefix or pattern")
        return "\n".join(out)

    def t_list_modules(self, a):
        mods = self.store.modules(a.get("query", ""), a.get("repo", ""))
        if not mods:
            return "No modules found."
        return "\n".join(f"- {m['name']} ({m['repo']}): {m['title']}" for m in mods[:400]) + (
            f"\n... {len(mods) - 400} more" if len(mods) > 400 else "")

    def t_odoo_module(self, a):
        st, name = self.store, a["name"].strip()
        m = st.module(name)
        if not m:
            near = [x["name"] for x in st.modules(name)][:20]
            raise ToolError(f"Module {name!r} is not in the snapshot." + (f" Similar: {', '.join(near)}" if near else ""))
        have = {x["name"]: x["repo"] for x in st.modules()}
        out = [f"# {m['name']} — {m['title']}", f"repo: {m['repo']}  path: {m['path']}/  version: {m['version']}",
               f"category: {m['category']}"]
        if m["summary"]:
            out.append(f"summary: {m['summary']}")
        out.append("depends: " + ", ".join(f"{d}" + ("" if d in have else " (not in snapshot)") for d in m["depends"]))
        rdeps = st.reverse_depends(name)
        out.append("used by: " + (", ".join(rdeps) if rdeps else "-"))
        rows = st.model_rows(module=name, repo=m["repo"])
        defined = sorted({r["model"] for r in rows if r["kind"] == "define"})
        extended = sorted({r["model"] for r in rows if r["kind"] == "inherit"})
        out.append("defines models: " + (", ".join(defined) or "-"))
        out.append("extends models: " + (", ".join(extended) or "-"))
        files, _ = st.list_files(m["repo"], m["path"])
        docs = [f["path"] for f in files if f["path"].lower().endswith((".md", ".rst")) and "/i18n/" not in f["path"]]
        if docs:
            out.append("docs: " + ", ".join(docs[:30]))
        out.append(f"files: {len(files)} indexed (list_files repo={m['repo']} path_prefix={m['path']})")
        return "\n".join(out)

    def t_odoo_model(self, a):
        st, model, field = self.store, a["model"].strip(), (a.get("field") or "").strip()
        rows = st.model_rows(model=model)
        if not rows:
            near = st.similar_models(model.split(".")[-1])
            raise ToolError(f"Model {model!r} not found." + (f" Similar: {', '.join(near)}" if near else ""))
        out = [f"# {model}"]
        for kind, label in (("define", "defined in"), ("inherit", "extended in"),
                            ("mixin", "inherited as mixin by"), ("delegate", "delegated (_inherits) by")):
            part = [r for r in rows if r["kind"] == kind]
            if part:
                out.append(f"{label}:")
                for r in part:
                    by = f" -> {r['by_model']}" if r["by_model"] else ""
                    desc = f" — {r['description']}" if r["description"] else ""
                    out.append(f"  - {r['module'] or '?'}{by}: {r['repo']}/{r['path']}:{r['line']} "
                               f"class {r['class_name']}{desc}")
        fields = st.field_rows(model=model, name=field)
        if field and not fields:
            out.append(f"field {field!r}: not declared on {model} in the snapshot (it may come from Odoo core).")
        elif fields:
            out.append(f"fields ({len(fields)}):")
            current = None
            for f in fields:
                if f["module"] != current:
                    current = f["module"]
                    out.append(f"  [{current or '?'}]")
                extra = []
                if f["comodel"]:
                    extra.append(f"-> {f['comodel']}")
                if f["string"]:
                    extra.append(f'"{f["string"]}"')
                if f["attrs"]:
                    extra.append(f"({f['attrs']})")
                out.append(f"    {f['name']}: {f['type']} {' '.join(extra)}  @{f['path']}:{f['line']}")
        return "\n".join(out)

    def t_search_knowledge(self, a):
        limit = max(1, min(int(a.get("limit") or 8), 30))
        res = self.store.search(a["query"], "knowledge", limit=limit)
        if not res:
            return f"No team knowledge matches {a['query']!r}."
        return self._format_hits(res)

    def t_list_knowledge(self, a):
        rows, total = self.store.list_files(kind="knowledge", limit=5000)
        rows = [r for r in rows if not r["path"].startswith("questions/")]  # see list_questions
        if not rows:
            return "No team knowledge notes yet."
        out = []
        for r in rows:
            text = self.store.read_file(r["repo"], r["path"]) or ""
            title = next((ln.lstrip("# ").strip() for ln in text.splitlines() if ln.strip()), r["path"])
            kind = next((ln[8:].strip() for ln in text.splitlines() if ln.startswith("- type: ")), "")
            out.append(f"- {'[' + kind + '] ' if kind else ''}{title}  ({r['repo']}/{r['path']})")
        return "\n".join(out)

    def t_add_knowledge(self, a):
        from .knowledge import KnowledgeError, add_entry
        try:
            where = add_entry(C.load_config(), self.store, a["title"], a["content"], a.get("tags") or [],
                              note_type=a.get("type", ""), modules=a.get("modules") or [])
        except KnowledgeError as e:
            raise ToolError(str(e)) from None
        return f"Saved for the team: {where}. Teammates get it after they press Update."

    def t_update_knowledge(self, a):
        from .knowledge import KnowledgeError, update_entry
        try:
            where = update_entry(C.load_config(), self.store, a["path"], a["content"], a.get("title", ""),
                                 a.get("tags"), note_type=a.get("type", ""), modules=a.get("modules"))
        except KnowledgeError as e:
            raise ToolError(str(e)) from None
        return f"Updated for the team: {where}. Teammates get it after they press Update."

    def t_list_questions(self, a):
        from .questions import list_questions
        from .sync import knowledge_repo
        repo = knowledge_repo(C.load_config())
        if not repo:
            raise ToolError("No team knowledge location is configured in the Repo Brain app.")
        status = (a.get("status") or "open").strip()
        area, query = (a.get("area") or "").strip(), (a.get("query") or "").strip().lower()
        qs = [q for q in list_questions(self.store, repo)
              if (status == "all" or q["status"] == status) and (not area or area in q["area"])
              and (not query or query in (q["title"] + q["details"]).lower())]
        if not qs:
            return "No matching questions."
        out = [f"{len(qs)} question(s):"]
        for q in qs[:200]:
            out.append(f"- [{q['status']}] {q['area']} | {q['title']}  ({q['path']}, {len(q['answers'])} answer(s))")
        return "\n".join(out)

    def t_answer_question(self, a):
        from .knowledge import KnowledgeError
        from .questions import answer_question
        try:
            answer_question(C.load_config(), self.store, a["path"], a["answer"])
        except KnowledgeError as e:
            raise ToolError(str(e)) from None
        return f"Answer saved to {a['path']} for the team. Teammates see it after they press Update."

    def t_ask_question(self, a):
        from .knowledge import KnowledgeError
        from .questions import ask_question
        try:
            path = ask_question(C.load_config(), self.store, a["question"], a["area"], a.get("details", ""))
        except KnowledgeError as e:
            raise ToolError(str(e)) from None
        return f"Question added for the team: {path}"

    def t_check_for_updates(self, a):
        from .sync import check_updates
        checks = check_updates(C.load_config(), self.store)
        if not checks:
            return "No GitHub repositories are configured."
        out = []
        for c in checks:
            if c.error:
                out.append(f"- {c.repo}: could not check ({c.error})")
            elif c.has_update:
                out.append(f"- {c.repo}@{c.branch}: NEWER commit on GitHub ({c.remote_sha[:10]}; "
                           f"snapshot {c.local_sha[:10] or 'empty'})")
            else:
                out.append(f"- {c.repo}@{c.branch}: up to date ({c.local_sha[:10]})")
        if any(c.has_update for c in checks):
            out.append("Press Update in the Repo Brain app to load the new commits.")
        return "\n".join(out)

    # ------------------------------------------------------------------ protocol
    def handle(self, msg: dict) -> dict | None:
        mid, method, params = msg.get("id"), msg.get("method"), msg.get("params") or {}
        if mid is None:  # notification
            return None
        try:
            if method == "initialize":
                asked = params.get("protocolVersion")
                version = asked if asked in PROTOCOL_VERSIONS else PROTOCOL_VERSIONS[0]
                result = {"protocolVersion": version, "capabilities": {"tools": {"listChanged": False},
                                                                     "prompts": {"listChanged": False}},
                          "serverInfo": {"name": C.MCP_NAME, "title": C.APP_NAME, "version": C.VERSION},
                          "instructions": INSTRUCTIONS}
            elif method == "ping":
                result = {}
            elif method == "tools/list":
                result = {"tools": TOOLS}
            elif method == "tools/call":
                result = self.call_tool(params.get("name", ""), params.get("arguments") or {})
            elif method == "prompts/list":
                result = {"prompts": PROMPTS}
            elif method == "prompts/get":
                try:
                    result = get_prompt(params.get("name", ""), params.get("arguments") or {})
                except KeyError:
                    return {"jsonrpc": "2.0", "id": mid,
                            "error": {"code": -32602, "message": f"Unknown prompt {params.get('name')}"}}
            elif method == "resources/list":
                result = {"resources": []}
            else:
                return {"jsonrpc": "2.0", "id": mid, "error": {"code": -32601, "message": f"Unknown method {method}"}}
        except Exception as e:  # protocol-level failure
            return {"jsonrpc": "2.0", "id": mid, "error": {"code": -32603, "message": str(e)}}
        return {"jsonrpc": "2.0", "id": mid, "result": result}

    def call_tool(self, name: str, args: dict) -> dict:
        fn = getattr(self, "t_" + name, None)
        if fn is None:
            return {"content": [{"type": "text", "text": f"Unknown tool {name}"}], "isError": True}
        try:
            text = fn(args)
            return {"content": [{"type": "text", "text": text}], "isError": False}
        except (ToolError, KeyError, ValueError) as e:
            msg = f"Missing argument {e}" if isinstance(e, KeyError) else str(e)
            return {"content": [{"type": "text", "text": msg}], "isError": True}
        except Exception as e:
            traceback.print_exc(file=sys.stderr)
            return {"content": [{"type": "text", "text": f"{type(e).__name__}: {e}"}], "isError": True}


def run(stdin=None, stdout=None):
    stdin = stdin or sys.stdin.buffer
    stdout = stdout or sys.stdout.buffer
    sys.stdout = sys.stderr  # stray prints must never corrupt the protocol stream
    server = Server()
    for raw in stdin:
        raw = raw.strip()
        if not raw:
            continue
        try:
            msg = json.loads(raw)
        except ValueError:
            reply = {"jsonrpc": "2.0", "id": None, "error": {"code": -32700, "message": "Parse error"}}
        else:
            batch = msg if isinstance(msg, list) else [msg]
            replies = [r for r in (server.handle(m) for m in batch if isinstance(m, dict)) if r]
            if not replies:
                continue
            reply = replies if isinstance(msg, list) else replies[0]
        try:
            stdout.write(json.dumps(reply, ensure_ascii=False).encode("utf-8") + b"\n")
            stdout.flush()
        except (BrokenPipeError, OSError):  # Claude closed the connection
            return
