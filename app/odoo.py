"""Read Odoo structure from source: module manifests, models (_name/_inherit) and fields."""
from __future__ import annotations

import ast
import posixpath

RELATIONAL = {"Many2one", "One2many", "Many2many", "Many2oneReference"}


def module_root(path: str, manifest_dirs: set[str]) -> str:
    """The folder of the nearest enclosing module ("" if the file is not inside one)."""
    d = posixpath.dirname(path)
    while d:
        if d in manifest_dirs:
            return d
        d = posixpath.dirname(d)
    return ""


def is_manifest(path: str) -> bool:
    return posixpath.basename(path) in ("__manifest__.py", "__openerp__.py")


def parse_manifest(text: str) -> dict | None:
    try:
        data = ast.literal_eval(text.strip())
    except (ValueError, SyntaxError, MemoryError, RecursionError):
        return None
    if not isinstance(data, dict):
        return None
    depends = data.get("depends") or []
    return {
        "title": str(data.get("name", "")),
        "summary": str(data.get("summary", "") or data.get("description", "") or "").strip()[:500],
        "version": str(data.get("version", "")),
        "category": str(data.get("category", "")),
        "depends": [str(d) for d in depends if isinstance(d, str)],
        "application": bool(data.get("application", False)),
    }


def _str(node) -> str | None:
    return node.value if isinstance(node, ast.Constant) and isinstance(node.value, str) else None


def _strs(node) -> list[str]:
    if (s := _str(node)) is not None:
        return [s]
    if isinstance(node, (ast.List, ast.Tuple)):
        return [s for e in node.elts if (s := _str(e)) is not None]
    return []


def _field_call(node):
    """fields.Char(...) / fields.Many2one(...) -> (type, call)."""
    if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute) \
            and isinstance(node.func.value, ast.Name) and node.func.value.id == "fields":
        return node.func.attr, node
    return None


def parse_models(text: str) -> list[dict]:
    """Models declared in a Python file.

    Each item: {"model", "kind" (define|inherit|mixin|delegate), "class_name", "line", "fields": [...], "by"?}.
    mixin/delegate rows describe a parent model that another model ("by") builds on.
    A class with _name and a different _inherit both defines its model and extends the parent.
    """
    try:
        tree = ast.parse(text)
    except (SyntaxError, ValueError, MemoryError, RecursionError):
        return []
    out = []
    for cls in ast.walk(tree):
        if not isinstance(cls, ast.ClassDef):
            continue
        name, inherit, inherits, fields, description = None, [], [], [], ""
        for stmt in cls.body:
            if not isinstance(stmt, ast.Assign) or len(stmt.targets) != 1 or not isinstance(stmt.targets[0], ast.Name):
                continue
            target = stmt.targets[0].id
            if target == "_name":
                name = _str(stmt.value)
            elif target == "_inherit":
                inherit = _strs(stmt.value)
            elif target == "_inherits" and isinstance(stmt.value, ast.Dict):
                inherits = [s for k in stmt.value.keys if (s := _str(k))]
            elif target == "_description":
                description = _str(stmt.value) or ""
            elif (fc := _field_call(stmt.value)) is not None:
                ftype, call = fc
                label = comodel = None
                if call.args:
                    first = _str(call.args[0])
                    if ftype in RELATIONAL:
                        comodel = first
                        if len(call.args) > 1 and ftype == "Many2one":
                            label = _str(call.args[1])
                    else:
                        label = first
                for kw in call.keywords:
                    if kw.arg == "string":
                        label = _str(kw.value) or label
                    elif kw.arg == "comodel_name":
                        comodel = _str(kw.value) or comodel
                extra = [kw.arg for kw in call.keywords if kw.arg in ("compute", "related", "store", "required")]
                fields.append({"name": target, "type": ftype, "string": label or "",
                               "comodel": comodel or "", "line": stmt.lineno, "attrs": ",".join(extra)})
        if not name and not inherit:
            continue
        main = name or inherit[0]
        if name and name not in inherit:
            out.append({"model": name, "kind": "define", "class_name": cls.name, "line": cls.lineno,
                        "description": description, "fields": fields})
            for parent in inherit:
                out.append({"model": parent, "kind": "mixin", "class_name": cls.name, "line": cls.lineno,
                            "description": "", "fields": [], "by": name})
        else:
            out.append({"model": main, "kind": "inherit", "class_name": cls.name, "line": cls.lineno,
                        "description": description, "fields": fields})
            for parent in inherit[1:]:
                out.append({"model": parent, "kind": "inherit", "class_name": cls.name, "line": cls.lineno,
                            "description": "", "fields": []})
        for parent in inherits:
            out.append({"model": parent, "kind": "delegate", "class_name": cls.name, "line": cls.lineno,
                        "description": "", "fields": [], "by": main})
    return out
