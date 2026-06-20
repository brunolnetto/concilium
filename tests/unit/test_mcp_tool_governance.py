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
MCP_TOOL_CEILING = 52

_TOOLS_GLOB = "src/concilium/presentation/mcp/tools/*.py"


def _discover_registered_tools() -> list[tuple[str, str]]:
    """Descobre (módulo, nome) de toda função decorada com @server.tool()."""
    root = os.path.join(os.path.dirname(__file__), "..", "..")
    rows: list[tuple[str, str]] = []
    for f in sorted(glob.glob(os.path.join(root, _TOOLS_GLOB))):
        mod = os.path.basename(f).replace(".py", "")
        tree = ast.parse(open(f, encoding="utf-8").read())
        for node in ast.walk(tree):
            if isinstance(node, ast.FunctionDef):
                for dec in node.decorator_list:
                    is_tool = (isinstance(dec, ast.Attribute) and dec.attr == "tool") or (
                        isinstance(dec, ast.Call)
                        and isinstance(dec.func, ast.Attribute)
                        and dec.func.attr == "tool"
                    )
                    if is_tool:
                        rows.append((mod, node.name))
    return rows


@pytest.fixture(scope="module")
def tools() -> list[tuple[str, str]]:
    return _discover_registered_tools()


def test_tool_count_under_ceiling(tools):
    """Superfície de tools não pode exceder o teto sem decisão consciente (ADR-116 D4)."""
    n = len(tools)
    assert n <= MCP_TOOL_CEILING, (
        f"{n} tools registradas > teto {MCP_TOOL_CEILING}. Se o crescimento é "
        "intencional, suba MCP_TOOL_CEILING explicitamente e registre o motivo. "
        f"Tools: {sorted(name for _, name in tools)}"
    )


def test_removed_legacy_tools_absent(tools):
    """ADR-116: tools legadas removidas não devem reaparecer."""
    names = {name for _, name in tools}
    removed = {"listar_benchmarks", "executar_benchmark", "avancar_pipeline"}
    reincidentes = removed & names
    assert not reincidentes, f"Tools legadas removidas pelo ADR-116 reapareceram: {reincidentes}"


def test_no_duplicate_verb_intents(tools):
    """Sem pares de tools com a mesma intenção (verbo+objeto), ex: X e X_nep039.

    Detecta o padrão de duplicação P2 do ADR-116: uma tool e sua variante sufixada
    que fazem a mesma coisa. Sufixos conhecidos toleráveis devem ser exceção explícita.
    """
    names = {name for _, name in tools}
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


def test_every_tool_has_rbac_coverage(tools):
    """ADR-099/ADR-116 D4: toda tool registrada tem entrada em TOOL_PERMISSIONS."""
    from concilium.infrastructure.auth.permission_guard import TOOL_PERMISSIONS

    names = {name for _, name in tools}
    sem_rbac = sorted(names - set(TOOL_PERMISSIONS))
    assert not sem_rbac, (
        f"Tools sem cobertura RBAC (faltam em TOOL_PERMISSIONS): {sem_rbac}. "
        "Toda tool precisa de uma permissão mapeada (ADR-099)."
    )


def test_tool_permissions_has_no_orphans(tools):
    """TOOL_PERMISSIONS não deve ter entradas para tools inexistentes (limpeza)."""
    from concilium.infrastructure.auth.permission_guard import TOOL_PERMISSIONS

    names = {name for _, name in tools}
    # Aliases legados conhecidos que podem permanecer no mapa (compat de roles)
    aliases_ok = {"ler_artefato", "listar_cpus", "buscar_cpu", "derivar_recursos_do_catalogo",
                  "consultar_viabilidade_prazo", "identificar_gargalos_recurso",
                  "simular_impacto_replan", "aplicar_sugestao_replan", "iniciar_orcamento",
                  "auditar_plano"}
    orfas = sorted(set(TOOL_PERMISSIONS) - names - aliases_ok)
    assert not orfas, (
        f"Entradas órfãs em TOOL_PERMISSIONS (tool não existe): {orfas}. "
        "Remova ou registre como alias conhecido."
    )
