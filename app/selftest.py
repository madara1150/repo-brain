"""--selftest: quick check that a built app has everything it needs (SQLite FTS5 trigram, SSL, MCP replies)."""
import json
import os
import sqlite3
import ssl
import sys
import tempfile


def run() -> int:
    ok = True

    def check(name, fn):
        nonlocal ok
        try:
            fn()
            print(f"ok   {name}")
        except Exception as e:  # report every failure, then exit non-zero
            ok = False
            print(f"FAIL {name}: {e}")

    def fts():
        con = sqlite3.connect(":memory:")
        con.execute("CREATE VIRTUAL TABLE t USING fts5(x, tokenize='trigram')")
        con.execute("INSERT INTO t VALUES ('ใบขอซื้อ purchase.request')")
        assert con.execute("SELECT count(*) FROM t WHERE t MATCH '\"ขอซื้อ\"'").fetchone()[0] == 1

    def certs():
        from .github import _ssl_context
        assert isinstance(_ssl_context(), ssl.SSLContext)
        import certifi
        assert os.path.exists(certifi.where())

    def mcp():
        from .mcp_server import Server
        from .store import Store
        with tempfile.TemporaryDirectory() as d:
            db = os.path.join(d, "index.db")
            st = Store(db)
            with st.conn:
                st.put_file("me/x", "m/__manifest__.py", "code", '{"name": "M", "depends": ["base"]}')
                st.put_file("me/x", "m/models/a.py", "code",
                            "from odoo import fields, models\nclass A(models.Model):\n    _name = 'a.a'\n    n = fields.Char()\n")
                st.reindex_odoo("me/x")
                st.set_source("me/x", "main", "abc", "code")
            st.close()
            s = Server(db)
            init = s.handle({"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {}})
            assert init["result"]["serverInfo"]["name"] == "repo-brain"
            res = s.handle({"jsonrpc": "2.0", "id": 2, "method": "tools/call",
                            "params": {"name": "odoo_model", "arguments": {"model": "a.a"}}})
            s.close()  # Windows cannot delete the temp folder while the database is open
            assert "defined in" in res["result"]["content"][0]["text"], json.dumps(res)

    check("sqlite fts5 trigram", fts)
    check("ssl certificates", certs)
    check("mcp server", mcp)
    print("selftest", "passed" if ok else "FAILED", f"(python {sys.version.split()[0]})")
    return 0 if ok else 1
