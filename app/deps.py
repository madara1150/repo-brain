"""Find which GitHub repository provides an Odoo module that the indexed code depends on.

OCA publishes every addon on PyPI as odoo-addon-<module> (odoo14-addon-<module> before 16.0)
with its GitHub repository as the home page, so missing dependencies can be mapped to repos.
"""
from __future__ import annotations

import json
import re
import urllib.request
from concurrent.futures import ThreadPoolExecutor

from .github import _ssl_context, parse_repo


def package_names(module: str, odoo_version: str) -> list[str]:
    major = odoo_version.split(".")[0] if odoo_version else ""
    names = ["odoo-addon-" + module]
    if major.isdigit() and int(major) < 16:
        names.insert(0, f"odoo{major}-addon-{module}")
    return names


def lookup(module: str, odoo_version: str, ctx=None) -> str:
    """"owner/repo" that ships `module`, or "" (Odoo core modules and private ones are not on PyPI)."""
    ctx = ctx or _ssl_context()
    for pkg in package_names(module, odoo_version):
        data = _get(f"https://pypi.org/pypi/{pkg}/json", ctx)
        if not data:
            continue
        info = data.get("info", {})
        # addons move between OCA repositories across Odoo versions: use a release for our version
        ours = sorted((v for v in data.get("releases", {}) if v.startswith(odoo_version + ".")), key=_vkey)
        if ours and not info.get("version", "").startswith(odoo_version + "."):
            info = (_get(f"https://pypi.org/pypi/{pkg}/{ours[-1]}/json", ctx) or {}).get("info", info)
        urls = [info.get("home_page") or ""] + list((info.get("project_urls") or {}).values())
        for u in urls:
            if re.search(r"github\.com/", u or ""):
                repo = parse_repo(u)
                if repo:
                    return repo
    return ""


def _get(url: str, ctx):
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "RepoBrain"})
        with urllib.request.urlopen(req, timeout=20, context=ctx) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except Exception:
        return None


def _vkey(v: str):
    return [int(p) if p.isdigit() else 0 for p in re.split(r"[.]", v)]


def suggest_repos(missing: list[str], odoo_version: str, progress=None) -> tuple[dict, list]:
    """({repo: [modules]}, [modules not found anywhere, usually Odoo core])."""
    ctx = _ssl_context()
    found, unknown = {}, []
    with ThreadPoolExecutor(max_workers=8) as pool:
        for i, (mod, repo) in enumerate(zip(missing, pool.map(lambda m: lookup(m, odoo_version, ctx), missing))):
            if progress:
                progress(mod, (i + 1) / max(len(missing), 1))
            if repo:
                found.setdefault(repo, []).append(mod)
            else:
                unknown.append(mod)
    return found, unknown
