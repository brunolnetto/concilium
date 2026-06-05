#!/usr/bin/env python3
"""Agrupa violações do Ruff (stdin JSON) em categorias para leitura pelo agente de código.

Stdin:  ruff check --output-format json
Stdout: JSON estruturado com violações agrupadas por regra, severidade e arquivo.

Uso (via Makefile):
    python3 -m ruff check src/ --output-format json | python3 scripts/lint_report.py > .lint-report.json
"""

from __future__ import annotations

import ast
import json
import re
import sys
from collections import defaultdict
from pathlib import Path
from typing import Any

# Regras que têm correção automática via --fix
AUTO_FIX_RULES = {
    "F401", "F841", "I001", "UP037", "B905", "B007",
    "UP042", "F541", "UP045", "UP024", "UP017", "E731",
    "UP035", "B028", "F811",
}

# Categorias semânticas para facilitar priorização
CATEGORIES: dict[str, set[str]] = {
    "syntax":     {"invalid-syntax", "E999"},
    "imports":    {"F401", "I001", "F811"},
    "unused":     {"F841", "B007"},
    "style":      {"E501", "E741", "E722", "E731"},
    "upgrade":    {"UP037", "UP042", "UP045", "UP024", "UP017", "UP035"},
    "safety":     {"B904", "B905", "B008", "B027", "B028"},
    "undefined":  {"F821", "F541"},
}


def _category(code: str) -> str:
    for cat, codes in CATEGORIES.items():
        if code in codes:
            return cat
    return "other"


def _has_call(node: ast.AST, module: str, func: str) -> bool:
    """Return True if AST node contains a call like `module.func(...)`."""
    for child in ast.walk(node):
        if not isinstance(child, ast.Call):
            continue
        attr = child.func
        if (isinstance(attr, ast.Attribute)
                and attr.attr == func
                and isinstance(attr.value, ast.Name)
                and attr.value.id == module):
            return True
    return False


def _scan_raw_json_ui(ui_root: Path) -> list[dict[str, Any]]:
    """ADR-064 §F2: detect st.text_area + json.loads pattern in UI files.

    Uses AST-level call detection (not regex) to avoid false positives
    from docstrings or comments that mention these names.

    Flags any UI Python function that has BOTH:
      - a call to st.text_area(...)
      - a call to json.loads(...)
    as actual expressions (not string literals / comments).
    """
    hits: list[dict[str, Any]] = []
    if not ui_root.exists():
        return hits

    for pyfile in ui_root.rglob("*.py"):
        try:
            source = pyfile.read_text(encoding="utf-8")
        except OSError:
            continue

        try:
            tree = ast.parse(source)
        except SyntaxError:
            continue

        for node in ast.walk(tree):
            if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                continue
            has_text_area = _has_call(node, "st", "text_area")
            has_json_loads = _has_call(node, "json", "loads")
            if has_text_area and has_json_loads:
                hits.append({
                    "file": str(pyfile),
                    "function": node.name,
                    "line": node.lineno,
                    "code": "UI-JSON-RAW",
                    "message": (
                        f"Function '{node.name}' uses st.text_area + json.loads — "
                        "replace with render_typed_form() per ADR-064"
                    ),
                    "auto_fix": False,
                    "category": "ui-json-raw",
                })
    return hits


def main() -> None:
    try:
        violations: list[dict[str, Any]] = json.load(sys.stdin)
    except json.JSONDecodeError:
        violations = []

    # ADR-064 §F2: scan UI files for raw JSON editing antipattern
    ui_root = Path(__file__).parent.parent / "src" / "concilium" / "presentation" / "ui"
    raw_json_hits = _scan_raw_json_ui(ui_root)

    by_rule: dict[str, dict] = defaultdict(lambda: {
        "count": 0, "auto_fix": False, "category": "", "description": "", "files": []
    })
    by_file: dict[str, list] = defaultdict(list)
    fixable_total = 0

    for v in violations:
        code = v.get("code") or "unknown"
        msg  = v.get("message") or ""
        path = v.get("filename") or ""
        row  = v.get("location", {}).get("row", 0)
        col  = v.get("location", {}).get("column", 0)
        fixable = bool(v.get("fix"))

        entry = by_rule[code]
        entry["count"] += 1
        entry["auto_fix"] = code in AUTO_FIX_RULES
        entry["category"] = _category(code)
        entry["description"] = entry["description"] or msg[:80]
        if path not in entry["files"]:
            entry["files"].append(path)

        by_file[path].append({"code": code, "row": row, "col": col, "message": msg})

        if fixable:
            fixable_total += 1

    # Top violations per file (for targeted agent fixing)
    file_summary = []
    for filepath, issues in sorted(by_file.items(), key=lambda x: -len(x[1])):
        codes_in_file = defaultdict(int)
        for i in issues:
            codes_in_file[i["code"]] += 1
        file_summary.append({
            "file": filepath,
            "total": len(issues),
            "codes": dict(sorted(codes_in_file.items(), key=lambda x: -x[1])),
            "fixable": sum(1 for i in issues if i["code"] in AUTO_FIX_RULES),
            "violations": issues[:20],  # first 20 for brevity
        })

    # Merge ADR-064 raw JSON hits into by_rule
    for hit in raw_json_hits:
        code = hit["code"]
        path = hit["file"]
        entry = by_rule[code]
        entry["count"] += 1
        entry["auto_fix"] = False
        entry["category"] = "ui-json-raw"
        entry["description"] = entry["description"] or "st.text_area + json.loads antipattern (ADR-064)"
        if path not in entry["files"]:
            entry["files"].append(path)
        by_file[path].append({"code": code, "row": hit["line"], "col": 1, "message": hit["message"]})

    report = {
        "summary": {
            "total": len(violations),
            "fixable": fixable_total,
            "manual": len(violations) - fixable_total,
            "files_affected": len(by_file),
            "rules_violated": len(by_rule),
            "ui_json_raw_violations": len(raw_json_hits),
        },
        "by_rule": [
            {
                "code": code,
                "count": info["count"],
                "auto_fix": info["auto_fix"],
                "category": info["category"],
                "description": info["description"],
                "files_count": len(info["files"]),
                "files": info["files"][:10],
            }
            for code, info in sorted(by_rule.items(), key=lambda x: -x[1]["count"])
        ],
        "by_file": file_summary[:50],  # top 50 files
        "ui_json_raw": raw_json_hits,  # ADR-064: explicit section for raw JSON editing violations
        "agent_instructions": (
            "Run `make fmt` to auto-fix all rules with auto_fix=true. "
            "For manual fixes: syntax errors first, then undefined names (F821), "
            "then safety rules (B904, E722). "
            "B008 violations in FastAPI/typer code are expected and can be ignored. "
            "UI-JSON-RAW: replace st.text_area+json.loads with render_typed_form() (ADR-064)."
        ),
    }

    json.dump(report, sys.stdout, indent=2, ensure_ascii=False)
    sys.stdout.write("\n")


if __name__ == "__main__":
    main()
