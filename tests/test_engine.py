"""Engine tests: Odoo parsing, index/search, sync (full + incremental) with a fake GitHub, knowledge, MCP, Claude config."""
import io
import json
import os
import subprocess
import sys
import tarfile

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


@pytest.fixture(autouse=True)
def home(tmp_path, monkeypatch):
    monkeypatch.setenv("REPO_BRAIN_HOME", str(tmp_path / "home"))
    return tmp_path / "home"


MANIFEST = '{"name": "Demo Request", "version": "16.0.1.0.0", "summary": "Requests", "depends": ["base", "mail"]}'
MODEL = '''
from odoo import fields, models


class DemoRequest(models.Model):
    _name = "demo.request"
    _inherit = ["mail.thread"]
    _description = "Demo Request"

    name = fields.Char("Reference", required=True)
    partner_id = fields.Many2one("res.partner", string="ผู้ขอซื้อ")
    line_ids = fields.One2many("demo.request.line", "request_id")


class ResPartner(models.Model):
    _inherit = "res.partner"

    demo_count = fields.Integer(compute="_compute_demo_count")
'''
EXT_MANIFEST = '{"name": "Demo Ext", "depends": ["demo_request", "purchase_request"]}'
EXT_MODEL = '''
from odoo import fields, models


class DemoRequest(models.Model):
    _inherit = "demo.request"

    budget_code = fields.Char(string="รหัสงบประมาณ")
'''


class FakeResp(io.BytesIO):
    def __enter__(self):
        return self

    def __exit__(self, *a):
        self.close()


class FakeGitHub:
    """Serves commits of an in-memory repository: {sha: {path: text}}."""

    def __init__(self, commits, head):
        self.commits, self.head, self.raw_calls, self.put = commits, head, [], []

    def default_branch(self, repo):
        return "16.0"

    def head_sha(self, repo, branch):
        return self.head

    def compare(self, repo, base, head):
        a, b = self.commits[base], self.commits[head]
        files = [{"filename": p, "status": "removed"} for p in a if p not in b]
        files += [{"filename": p, "status": "added" if p not in a else "modified"} for p in b if a.get(p) != b[p]]
        return {"status": "ahead", "files": files}

    def open_tarball(self, repo, ref):
        buf = io.BytesIO()
        with tarfile.open(fileobj=buf, mode="w:gz") as tar:
            for path, text in self.commits[ref].items():
                data = text.encode()
                info = tarfile.TarInfo(f"repo-{ref}/{path}")
                info.size = len(data)
                tar.addfile(info, io.BytesIO(data))
        return FakeResp(buf.getvalue())

    def raw_file(self, repo, ref, path):
        self.raw_calls.append(path)
        return self.commits[ref][path].encode()

    def current_user(self):
        return "tester"

    def put_file(self, repo, branch, path, content, message):
        self.put.append((repo, branch, path, content.decode(), message))
        return {}


def make_store():
    from app.config import index_path
    from app.store import Store
    return Store(index_path())


V1 = {"demo_request/__manifest__.py": MANIFEST, "demo_request/models/demo.py": MODEL,
      "demo_request/README.md": "# Demo\nApproval rules live here.", "demo_request/static/img/logo.png": "\x00PNG",
      ".env": "SECRET=1", "demo_request/i18n/fr.po": "msgid x", "demo_request/i18n/th.po": 'msgstr "ผู้ขอซื้อ"'}
V2 = dict(V1)
V2.update({"demo_ext/__manifest__.py": EXT_MANIFEST, "demo_ext/models/demo.py": EXT_MODEL})
del V2["demo_request/README.md"]


# ---------------------------------------------------------------- odoo parsing
def test_parse_models_and_fields():
    from app.odoo import parse_manifest, parse_models
    m = parse_manifest(MANIFEST)
    assert m["depends"] == ["base", "mail"] and m["title"] == "Demo Request"
    models = parse_models(MODEL)
    kinds = {(x["model"], x["kind"]) for x in models}
    assert ("demo.request", "define") in kinds and ("mail.thread", "mixin") in kinds and ("res.partner", "inherit") in kinds
    demo = next(x for x in models if x["model"] == "demo.request")
    f = {x["name"]: x for x in demo["fields"]}
    assert f["partner_id"]["comodel"] == "res.partner" and f["partner_id"]["string"] == "ผู้ขอซื้อ"
    assert f["name"]["string"] == "Reference" and "required" in f["name"]["attrs"]
    assert parse_models("def broken(:") == []


def test_should_index_filters():
    from app.store import should_index
    assert should_index("a/models/x.py", 10)
    assert not should_index(".env", 10)
    assert not should_index("keys/server.pem", 10)
    assert not should_index("a/static/img/logo.png", 10)
    assert not should_index("a/i18n/fr.po", 10) and should_index("a/i18n/th.po", 10)
    assert not should_index("a/static/lib/jquery.js", 10)
    assert not should_index("a/big.py", 10_000_000)
    assert should_index("notes/x.md", 10, "knowledge") and not should_index("x.py", 10, "knowledge")


# ---------------------------------------------------------------- sync
def test_full_then_incremental_sync():
    from app.config import Config, Source
    from app.sync import Syncer
    store = make_store()
    cfg = Config(sources=[Source("me/erp", "")])
    gh = FakeGitHub({"c1": V1, "c2": V2}, "c1")
    res = Syncer(cfg, store, gh).run()
    assert res[0].mode == "full" and res[0].new_sha == "c1"
    paths = {r["path"] for r in store.list_files()[0]}
    assert "demo_request/models/demo.py" in paths and ".env" not in paths
    assert "demo_request/static/img/logo.png" not in paths and "demo_request/i18n/fr.po" not in paths
    assert store.module("demo_request")["depends"] == ["base", "mail"]

    # nothing new: no download, snapshot kept
    assert Syncer(cfg, store, gh).run()[0].mode == "unchanged"

    gh.head = "c2"
    res = Syncer(cfg, store, gh).run()
    assert res[0].mode == "incremental" and res[0].changed == 3
    assert sorted(gh.raw_calls) == ["demo_ext/__manifest__.py", "demo_ext/models/demo.py"]
    assert store.read_file("me/erp", "demo_request/README.md") is None
    rows = store.model_rows(model="demo.request")
    assert {(r["module"], r["kind"]) for r in rows} == {("demo_request", "define"), ("demo_ext", "inherit")}
    assert store.field_rows(model="demo.request", name="budget_code")[0]["module"] == "demo_ext"
    assert store.missing_depends() == ["base", "mail", "purchase_request"]
    assert store.source("me/erp")["sha"] == "c2"


def test_removed_source_is_forgotten():
    from app.config import Config, Source
    from app.sync import Syncer
    store = make_store()
    gh = FakeGitHub({"c1": V1}, "c1")
    Syncer(Config(sources=[Source("me/erp")]), store, gh).run()
    Syncer(Config(sources=[]), store, gh).run()
    assert store.sources() == [] and store.list_files()[1] == 0


def test_search_thai_and_code():
    from app.config import Config, Source
    from app.sync import Syncer
    store = make_store()
    Syncer(Config(sources=[Source("me/erp")]), store, FakeGitHub({"c1": V2}, "c1")).run()
    hits = store.search("ผู้ขอซื้อ")
    assert {h["path"] for h in hits} >= {"demo_request/models/demo.py", "demo_request/i18n/th.po"}
    line, ctx = hits[0]["hits"][0]
    assert any("ผู้ขอซื้อ" in text for _, text in ctx)
    assert store.search("budget_code demo.request")[0]["path"] == "demo_ext/models/demo.py"
    assert store.search("id")  # short terms fall back to a substring scan
    assert store.search("nothing_like_this_anywhere") == []


# ---------------------------------------------------------------- knowledge
def test_knowledge_github_and_folder(tmp_path):
    from app.config import Config, Knowledge
    from app.knowledge import add_entry
    from app.sync import LOCAL_KNOWLEDGE, Syncer
    store = make_store()
    gh = FakeGitHub({}, "")
    cfg = Config(knowledge=Knowledge(mode="github", repo="me/notes", subdir="knowledge"), github_token="x")
    where = add_entry(cfg, store, "ลำดับอนุมัติ", "เกิน 1 แสนต้องผ่าน ผอ.", ["purchase"], gh=gh)
    repo, branch, path, text, msg = gh.put[0]
    assert repo == "me/notes" and path.startswith("knowledge/") and path.endswith("-note.md")
    assert "author: tester" in text and "tags: purchase" in text and where.endswith(path)
    assert store.search("ผ่าน ผอ", kind="knowledge")  # searchable before anyone presses Update

    folder = tmp_path / "shared"
    folder.mkdir()
    cfg = Config(knowledge=Knowledge(mode="folder", folder=str(folder), subdir="knowledge"), author="Boat")
    add_entry(cfg, store, "Closing", "Lock the period.")
    (folder / "old.md").write_text("# Old note\nhello team", encoding="utf-8")
    Syncer(cfg, store, gh).run()
    rows = [r for r in store.list_files(kind="knowledge")[0] if r["repo"] == LOCAL_KNOWLEDGE]
    assert len(rows) == 2


# ---------------------------------------------------------------- MCP server
def _rpc(server, method, params=None, mid=1):
    return server.handle({"jsonrpc": "2.0", "id": mid, "method": method, "params": params or {}})


def _call(server, tool, **args):
    res = _rpc(server, "tools/call", {"name": tool, "arguments": args})["result"]
    return res["content"][0]["text"], res["isError"]


def test_mcp_tools():
    from app.config import Config, Source, save_config
    from app.mcp_server import Server
    from app.sync import Syncer
    store = make_store()
    cfg = Config(sources=[Source("me/erp")])
    save_config(cfg)
    Syncer(cfg, store, FakeGitHub({"c1": V2}, "c1")).run()
    s = Server()
    init = _rpc(s, "initialize", {"protocolVersion": "2025-06-18"})["result"]
    assert init["protocolVersion"] == "2025-06-18" and "tools" in init["capabilities"]
    assert s.handle({"jsonrpc": "2.0", "method": "notifications/initialized"}) is None
    names = {t["name"] for t in _rpc(s, "tools/list")["result"]["tools"]}
    assert {"search_code", "odoo_model", "add_knowledge", "repo_status"} <= names

    text, err = _call(s, "repo_status")
    assert "me/erp" in text and "c1" in text and not err
    text, _ = _call(s, "odoo_model", model="demo.request")
    assert "defined in" in text and "demo_ext" in text and "budget_code" in text
    text, _ = _call(s, "odoo_model", model="demo.request", field="partner_id")
    assert "res.partner" in text and "budget_code" not in text
    text, err = _call(s, "odoo_model", model="demo.requestx")
    assert err and "demo.request" in text  # suggests the near match
    text, _ = _call(s, "odoo_module", name="demo_ext")
    assert "purchase_request (not in snapshot)" in text and "extends models: demo.request" in text
    text, _ = _call(s, "read_file", path="demo_ext/models/demo.py", start_line=5, end_line=6)
    assert "    5: class DemoRequest" in text
    text, _ = _call(s, "read_file", path="me/erp/demo_ext/__manifest__.py")
    assert "Demo Ext" in text
    text, err = _call(s, "read_file", path="nope.py")
    assert err
    text, _ = _call(s, "search_code", query="รหัสงบประมาณ")
    assert "demo_ext/models/demo.py" in text
    text, err = _call(s, "add_knowledge", title="x", content="y")
    assert err and "knowledge" in text  # no location configured
    assert "error" in _rpc(s, "no/such")


def test_mcp_stdio_roundtrip(home):
    from app.config import Config, Source, save_config
    from app.sync import Syncer
    store = make_store()
    save_config(Config(sources=[Source("me/erp")]))
    Syncer(Config(sources=[Source("me/erp")]), store, FakeGitHub({"c1": V1}, "c1")).run()
    store.close()
    msgs = [{"jsonrpc": "2.0", "id": 0, "method": "initialize", "params": {"protocolVersion": "2024-11-05"}},
            {"jsonrpc": "2.0", "method": "notifications/initialized"},
            {"jsonrpc": "2.0", "id": 1, "method": "tools/call", "params": {"name": "list_modules", "arguments": {}}}]
    out = subprocess.run([sys.executable, os.path.join(ROOT, "main.py"), "--mcp"],
                         input="\n".join(json.dumps(m) for m in msgs) + "\n", capture_output=True, text=True,
                         env={**os.environ, "REPO_BRAIN_HOME": str(home)}, timeout=60)
    lines = [json.loads(x) for x in out.stdout.splitlines()]
    assert [x["id"] for x in lines] == [0, 1]  # stdout carries protocol messages only
    assert "demo_request" in lines[1]["result"]["content"][0]["text"]


def test_mcp_without_index(home):
    from app.mcp_server import Server
    text, err = _call(Server(str(home / "missing.db")), "repo_status")
    assert err and "Update" in text


# ---------------------------------------------------------------- Claude Desktop config
def test_claude_desktop_install_keeps_other_servers(tmp_path):
    from app import claude_connect
    path = tmp_path / "Claude" / "claude_desktop_config.json"
    path.parent.mkdir()
    path.write_text(json.dumps({"mcpServers": {"other": {"command": "x"}}, "theme": "dark"}))
    assert claude_connect.status(str(path)) == "missing"
    claude_connect.install(str(path))
    data = json.loads(path.read_text())
    assert data["theme"] == "dark" and "other" in data["mcpServers"]
    entry = data["mcpServers"]["repo-brain"]
    assert entry["args"][-1] == "--mcp" and os.path.exists(entry["command"])
    assert claude_connect.status(str(path)) == "connected"
    assert (tmp_path / "Claude" / "claude_desktop_config.json.bak").exists()
    assert claude_connect.uninstall(str(path))
    assert "repo-brain" not in json.loads(path.read_text())["mcpServers"]

    path.write_text("{broken")
    with pytest.raises(ValueError):
        claude_connect.install(str(path))
    assert path.read_text() == "{broken"  # never overwrite a file we can't read


def test_parse_repo():
    from app.github import parse_repo
    assert parse_repo("https://github.com/OCA/purchase-workflow/tree/16.0") == "OCA/purchase-workflow"
    assert parse_repo("git@github.com:OCA/web.git") == "OCA/web"
    assert parse_repo("OCA/server-ux") == "OCA/server-ux"
    assert parse_repo("not a repo") == ""


def test_config_roundtrip():
    from app.config import Config, Knowledge, Source, config_path, load_config, save_config
    save_config(Config(sources=[Source("a/b", "16.0")], knowledge=Knowledge(mode="folder", folder="/x"),
                       github_token="t", language="en"))
    cfg = load_config()
    assert cfg.sources[0].branch == "16.0" and cfg.knowledge.folder == "/x" and cfg.language == "en"
    if os.name != "nt":
        assert oct(os.stat(config_path()).st_mode & 0o777) == "0o600"


def test_team_settings_roundtrip(tmp_path):
    from app.config import (Config, Knowledge, Source, TeamFileError, apply_team, export_team, read_team)
    mine = Config(sources=[Source("me/erp", "16.0"), Source("OCA/web", "16.0")],
                  knowledge=Knowledge(mode="github", repo="me/notes", subdir="knowledge"),
                  github_token="github_pat_x", author="Owner", odoo_version="16.0", language="en")
    path = tmp_path / "team.repobrain"
    export_team(mine, str(path), include_token=True)
    data = read_team(str(path))
    assert data["github_token"] == "github_pat_x" and "author" not in data and "language" not in data
    if os.name != "nt":
        assert oct(os.stat(path).st_mode & 0o777) == "0o600"

    friend = Config(author="Friend", language="th", github_token="own")
    got = apply_team(friend, data)
    assert [s.repo for s in got.sources] == ["me/erp", "OCA/web"] and got.knowledge.repo == "me/notes"
    assert got.github_token == "github_pat_x" and got.author == "Friend" and got.language == "th"

    export_team(mine, str(path), include_token=False)
    data = read_team(str(path))
    assert "github_token" not in data and apply_team(friend, data).github_token == "own"

    folder = Config(knowledge=Knowledge(mode="folder", folder="/Users/me/Drive/notes"))
    export_team(folder, str(path))
    assert read_team(str(path))["knowledge"]["folder"] == ""  # local paths don't travel

    (tmp_path / "x.json").write_text('{"sources": []}')
    with pytest.raises(TeamFileError):
        read_team(str(tmp_path / "x.json"))


# ---------------------------------------------------------------- LINE cases / teaching
DEMO_CHAT = os.path.join(ROOT, "tools", "demo_line_chat.txt")


def test_line_export_split_and_redacted():
    from app.line_chat import split_cases
    with open(DEMO_CHAT, encoding="utf-8") as fh:
        cases = split_cases(fh.read())
    # 3 cases: morning thread, afternoon thread (>3h gap), next day
    assert [c.date for c in cases] == ["2026/11/03", "2026/11/03", "2026/11/04"]
    first = cases[0].text
    assert "สมชาย" not in first and "แอดมิน" not in first
    assert "คน A" in first and "คน B" in first
    assert "02-123-4567" not in first and "[เบอร์โทร]" in first
    assert "finance@example.com" not in first and "[อีเมล]" in first
    assert "dropdown ไม่มีให้เลือก" in first  # multi-line message kept
    assert "081-234-5678" not in cases[2].text
    assert len(cases[0].messages) == 5 and cases[0].key != cases[1].key


def test_pasted_text_becomes_one_case():
    from app.line_chat import split_cases
    cases = split_cases("ลูกค้าถามว่า reset รหัสผ่านยังไง โทร 0812345678 หรือ id 1-2345-67890-12-3")
    assert len(cases) == 1
    assert "0812345678" not in cases[0].text and "[เลขบัตรประชาชน]" in cases[0].text
    assert split_cases("   ") == []


def test_prompts_and_typed_notes(tmp_path):
    from app.config import Config, Knowledge, save_config
    from app.mcp_server import Server
    from app.teach import case_prompt, flow_prompt
    assert "add_knowledge" in case_prompt("คน A: hi") and "คน A: hi" in case_prompt("คน A: hi")
    assert "โอนงบ" in flow_prompt("โอนงบ") and "อธิบายกลับ" in flow_prompt()

    folder = tmp_path / "notes"
    folder.mkdir()
    save_config(Config(knowledge=Knowledge(mode="folder", folder=str(folder), subdir="knowledge"), author="Boat"))
    make_store().close()
    s = Server()
    init = _rpc(s, "initialize")["result"]
    assert "prompts" in init["capabilities"]
    names = [p["name"] for p in _rpc(s, "prompts/list")["result"]["prompts"]]
    assert names == ["analyze_line_case", "teach_flow"]
    got = _rpc(s, "prompts/get", {"name": "teach_flow", "arguments": {"topic": "เบิกจ่าย"}})["result"]
    assert "เบิกจ่าย" in got["messages"][0]["content"]["text"]
    assert "error" in _rpc(s, "prompts/get", {"name": "nope"})

    text, err = _call(s, "add_knowledge", title="ยืนยันใบขอซื้อไม่ได้", content="# ยืนยันใบขอซื้อไม่ได้\n## สรุป\nต้องมีงบ",
                      type="case", modules=["purchase_request"], tags=["งบ"])
    assert not err, text
    path = next(folder.rglob("*.md"))
    saved = path.read_text(encoding="utf-8")
    assert "- type: case" in saved and "- modules: purchase_request" in saved and "- author: Boat" in saved
    assert saved.count("ยืนยันใบขอซื้อไม่ได้") == 1  # repeated title removed from the body
    listing, _ = _call(s, "list_knowledge")
    assert "[case] ยืนยันใบขอซื้อไม่ได้" in listing

    rel = path.relative_to(folder).as_posix()
    text, err = _call(s, "update_knowledge", path=f"local/knowledge/{rel}", content="## สรุป\nต้องได้รับจัดสรรงบก่อน")
    assert not err, text
    saved = path.read_text(encoding="utf-8")
    assert "ต้องได้รับจัดสรรงบก่อน" in saved and "- type: case" in saved and "- modules: purchase_request" in saved
    text, err = _call(s, "update_knowledge", path="knowledge/missing.md", content="x")
    assert err and "list_knowledge" in text


def test_update_on_github_sends_sha():
    from app.config import Config, Knowledge
    from app.knowledge import add_entry, update_entry
    store = make_store()

    class GH(FakeGitHub):
        def file_sha(self, repo, branch, path):
            return "abc123"

        def put_file(self, repo, branch, path, content, message, sha=""):
            self.put.append((path, sha, message))
            return {}
    gh = GH({}, "")
    cfg = Config(knowledge=Knowledge(mode="github", repo="me/notes", subdir="knowledge"), github_token="t", author="A")
    add_entry(cfg, store, "Title", "body", gh=gh)
    path = gh.put[0][0]
    update_entry(cfg, store, f"me/notes/{path}", "new body", gh=gh)
    assert gh.put[1] == (path, "abc123", "Update knowledge: Title")


def test_case_preview_is_redacted():
    from app.line_chat import split_cases
    case = split_cases("2026/11/01(Sat)\n10:00\tสมศรี\tโทรหา 0812345678 ด่วน\n")[0]
    assert "0812345678" not in case.preview and "[เบอร์โทร]" in case.preview and "สมศรี" not in case.preview


# ---------------------------------------------------------------- team questions
QTEXT = """# งบจัดสรรเปิดให้กรอกเดือนไหน

- status: open
- area: งบประมาณ
- note: knowledge/budget.md
- asked: 2026-11-05
- asked_by: x

## รายละเอียด
ผู้ใช้ถามบ่อย

## คำตอบ
"""


def test_question_parse_and_answer():
    from datetime import datetime
    from app.questions import add_answer, parse
    q = parse(QTEXT)
    assert q["title"] == "งบจัดสรรเปิดให้กรอกเดือนไหน" and q["status"] == "open" and q["area"] == "งบประมาณ"
    assert q["details"] == "ผู้ใช้ถามบ่อย" and q["answers"] == []
    t = add_answer(QTEXT, "Boat", "มิถุนายน", datetime(2026, 11, 6, 9, 30))
    t = add_answer(t, "Ann", "ส่งภายในกรกฎาคม\nบรรทัดสอง", datetime(2026, 11, 7, 10, 0))
    q = parse(t)
    assert q["status"] == "answered" and [a["author"] for a in q["answers"]] == ["Boat", "Ann"]
    assert q["answers"][1]["text"] == "ส่งภายในกรกฎาคม\nบรรทัดสอง" and q["answers"][0]["date"] == "2026-11-06 09:30"


def test_answer_question_folder_and_ask(tmp_path):
    from app.config import Config, Knowledge
    from app.questions import answer_question, ask_question, list_questions
    from app.sync import LOCAL_KNOWLEDGE, Syncer
    folder = tmp_path / "team"
    (folder / "questions").mkdir(parents=True)
    (folder / "questions" / "budget-001.md").write_text(QTEXT, encoding="utf-8")
    cfg = Config(knowledge=Knowledge(mode="folder", folder=str(folder)), author="Boat")
    store = make_store()
    Syncer(cfg, store, FakeGitHub({}, "")).run()
    qs = list_questions(store, LOCAL_KNOWLEDGE)
    assert [q["path"] for q in qs] == ["questions/budget-001.md"]
    answer_question(cfg, store, "questions/budget-001.md", "มิถุนายน")
    assert "### Boat ·" in (folder / "questions" / "budget-001.md").read_text(encoding="utf-8")
    assert list_questions(store, LOCAL_KNOWLEDGE)[0]["status"] == "answered"  # indexed before any Update
    path = ask_question(cfg, store, "ใครอนุมัติเงินยืม", "ยืมเงิน", "ถามบ่อย")
    assert (folder / path).exists() and len(list_questions(store, LOCAL_KNOWLEDGE)) == 2
    import pytest as _p
    from app.knowledge import KnowledgeError
    with _p.raises(KnowledgeError):
        answer_question(cfg, store, "knowledge/note.md", "x")  # only question files
    with _p.raises(KnowledgeError):
        answer_question(cfg, store, "questions/budget-001.md", "   ")


def test_answer_question_github_retries_on_conflict():
    from app.config import Config, Knowledge
    from app.github import GitHubError
    from app.questions import answer_question
    store = make_store()
    with store.conn:
        store.put_file("me/notes", "questions/q1.md", "knowledge", QTEXT)

    class GH(FakeGitHub):
        def __init__(self):
            super().__init__({}, "")
            self.remote = QTEXT
            self.calls = 0

        def get_file(self, repo, branch, path):
            return self.remote.encode(), f"sha{self.calls}"

        def put_file(self, repo, branch, path, content, message, sha=""):
            self.calls += 1
            if self.calls == 1:  # someone else answered meanwhile
                self.remote = self.remote + "### Other · 2026-11-06 08:00\nก่อนหน้า\n"
                raise GitHubError("conflict", 409)
            self.put.append((path, sha, content.decode()))
            return {}
    gh = GH()
    cfg = Config(knowledge=Knowledge(mode="github", repo="me/notes"), github_token="t", author="Boat")
    answer_question(cfg, store, "questions/q1.md", "คำตอบใหม่", gh=gh)
    saved = gh.put[0][2]
    assert "### Other ·" in saved and "### Boat ·" in saved and saved.index("Other") < saved.index("Boat")
    assert gh.put[0][1] == "sha1"  # wrote against the re-read version


def test_mcp_question_tools(tmp_path):
    from app.config import Config, Knowledge, save_config
    from app.mcp_server import Server
    from app.sync import Syncer
    folder = tmp_path / "team"
    (folder / "questions").mkdir(parents=True)
    (folder / "questions" / "budget-001.md").write_text(QTEXT, encoding="utf-8")
    cfg = Config(knowledge=Knowledge(mode="folder", folder=str(folder)), author="Boat")
    save_config(cfg)
    Syncer(cfg, make_store(), FakeGitHub({}, "")).run()
    s = Server()
    text, err = _call(s, "list_questions")
    assert not err and "งบจัดสรรเปิดให้กรอกเดือนไหน" in text and "[open]" in text
    text, err = _call(s, "answer_question", path="questions/budget-001.md", answer="มิถุนายน")
    assert not err, text
    text, _ = _call(s, "list_questions", status="answered")
    assert "1 answer" in text
    text, err = _call(s, "ask_question", question="ใครดูแลเมนูทดสอบ", area="ทั้งระบบ")
    assert not err and "questions/" in text


# ---------------------------------------------------------------- app updates
def test_updater_versions_and_release_parsing():
    from app import updater
    assert updater.is_newer("v1.0.10", "1.0.9") and not updater.is_newer("1.0.5", "1.0.5")
    assert updater.parse_version("v2.1") == (2, 1, 0)
    data = {"tag_name": "v1.2.0", "body": "notes", "html_url": "https://x/rel", "assets": [
        {"name": "RepoBrain-macOS.dmg", "browser_download_url": "https://x/mac"},
        {"name": "RepoBrain-Windows-Setup.exe", "browser_download_url": "https://x/win"},
        {"name": "SHA256SUMS.txt", "browser_download_url": "https://x/sums"}]}
    rel = updater.release_from_json(data)
    assert rel.version == "1.2.0" and rel.sums_url == "https://x/sums"
    assert rel.asset_name == updater.platform_asset() or not updater.platform_asset()
    sums = "a" * 64 + "  RepoBrain-macOS.dmg\n" + "b" * 64 + " *RepoBrain-Windows-Setup.exe\n"
    assert updater.expected_sha256(sums, "RepoBrain-Windows-Setup.exe") == "b" * 64
    assert updater.expected_sha256(sums, "other") == ""
    assert not updater.can_self_update()  # running from source never replaces itself


def test_updater_download_verifies_checksum(monkeypatch):
    import hashlib
    from app import updater
    payload = b"installer-bytes" * 1000
    good = hashlib.sha256(payload).hexdigest()

    class R(io.BytesIO):
        headers = {"Content-Length": str(len(payload))}
        def __enter__(self): return self
        def __exit__(self, *a): self.close()

    def fake_open(sums):
        def _open(url, accept=""):
            return R((sums + "  X.dmg\n").encode() if url.endswith("sums") else payload)
        return _open
    rel = updater.Release("9.9.9", "", "", "X.dmg", "https://x/asset", "https://x/sums")
    monkeypatch.setattr(updater, "_open", fake_open(good))
    seen = []
    path = updater.download(rel, lambda d, t: seen.append((d, t)))
    assert open(path, "rb").read() == payload and seen[-1] == (len(payload), len(payload))
    monkeypatch.setattr(updater, "_open", fake_open("0" * 64))
    with pytest.raises(updater.UpdateError):
        updater.download(rel)
