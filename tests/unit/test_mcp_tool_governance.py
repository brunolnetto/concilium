"""ADR-116 — Governança da superfície de tools MCP (anti-deriva).

Guarda contra a reincidência do crescimento descontrolado que o ADR-037
(>25 micro → ~9 macro) pretendia evitar:
  - teto de superfície (MCP_TOOL_CEILING)
  - sem verbos duplicados (ex: listar_benchmarks vs listar_benchmarks_nep039)
  - toda tool registrada tem cobertura RBAC (TOOL_PERMISSIONS — ADR-099)
"""

from __future__ import annotations

import ast
import glob
import os

import pytest

# Teto pós-limpeza ADR-116 (55 → 52). Subir exige decisão consciente: editar aqui.
MCP_TOOL_CEILING = 48

_TOOLS_GLOB = "src/concilium/presentation/mcp/tools/*.py"


def _is_server_tool(dec) -> bool:
    return (isinstance(dec, ast.Attribute) and dec.attr == "tool") or (
        isinstance(dec, ast.Call) and isinstance(dec.func, ast.Attribute) and dec.func.attr == "tool"
    )


def _is_permission(dec) -> bool:
    return isinstance(dec, ast.Call) and isinstance(dec.func, ast.Name) and dec.func.id == "permission"


def _discover_registered_tools() -> list[tuple[str, str, bool]]:
    """Descobre (módulo, nome, tem_permission) de toda função @server.tool().

    tem_permission: se a função também tem o decorator @permission inline (ADR-117).
    """
    root = os.path.join(os.path.dirname(__file__), "..", "..")
    rows: list[tuple[str, str, bool]] = []
    for f in sorted(glob.glob(os.path.join(root, _TOOLS_GLOB))):
        mod = os.path.basename(f).replace(".py", "")
        tree = ast.parse(open(f, encoding="utf-8").read())
        for node in ast.walk(tree):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                decs = node.decorator_list
                if any(_is_server_tool(d) for d in decs):
                    has_perm = any(_is_permission(d) for d in decs)
                    rows.append((mod, node.name, has_perm))
    return rows


@pytest.fixture(scope="module")
def tools() -> list[tuple[str, str, bool]]:
    return _discover_registered_tools()


def test_tool_count_under_ceiling(tools):
    """Superfície de tools não pode exceder o teto sem decisão consciente (ADR-116 D4)."""
    n = len(tools)
    assert n <= MCP_TOOL_CEILING, (
        f"{n} tools registradas > teto {MCP_TOOL_CEILING}. Se o crescimento é "
        "intencional, suba MCP_TOOL_CEILING explicitamente e registre o motivo. "
        f"Tools: {sorted(name for _, name, _ in tools)}"
    )


def test_removed_legacy_tools_absent(tools):
    """ADR-116: tools legadas removidas não devem reaparecer."""
    names = {name for _, name, _ in tools}
    removed = {"listar_benchmarks", "executar_benchmark", "avancar_pipeline"}
    reincidentes = removed & names
    assert not reincidentes, f"Tools legadas removidas pelo ADR-116 reapareceram: {reincidentes}"


def test_no_duplicate_verb_intents(tools):
    """Sem pares de tools com a mesma intenção (verbo+objeto), ex: X e X_nep039."""
    names = {name for _, name, _ in tools}
    suffixes = ("_nep039", "_v2", "_novo", "_legacy", "_old")
    duplicados = []
    for name in names:
        for suf in suffixes:
            if name.endswith(suf):
                base = name[: -len(suf)]
                if base in names:
                    duplicados.append((base, name))
    assert not duplicados, (
        f"Pares de tools duplicadas (base + variante sufixada): {duplicados}. "
        "Mantenha apenas uma — a duplicação confunde a seleção do agente (ADR-116 P2)."
    )


def test_every_tool_has_permission_decorator(tools):
    """ADR-117 D4 (fail-closed): toda @server.tool deve ter @permission inline.

    A permissão é a fonte única de RBAC (substitui o dict TOOL_PERMISSIONS).
    Uma tool sem @permission é erro de governança — segurança não pode ser esquecida.
    """
    sem_perm = sorted(f"{mod}.{name}" for mod, name, has_perm in tools if not has_perm)
    assert not sem_perm, (
        f"{len(sem_perm)} tool(s) @server.tool SEM @permission inline: {sem_perm}. "
        "Adicione @permission(\"<perm>\") logo abaixo de @server.tool() (ADR-117)."
    )
