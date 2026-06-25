"""ADR-116 — Governança da superfície de tools MCP e contratos de infraestrutura (anti-deriva).

Guarda contra a reincidência do crescimento descontrolado que o ADR-037
(>25 micro → ~9 macro) pretendia evitar:
  - sem verbos duplicados (ex: listar_benchmarks vs listar_benchmarks_nep039)
  - toda tool registrada tem cobertura RBAC (TOOL_PERMISSIONS — ADR-099)

Também guarda os contratos de RBAC e storage:
  - roles válidos: viewer e service-ci foram removidos intencionalmente
  - BlobStoragePort: deletar_blob deve estar presente nos adapters que suportam delete
"""

from __future__ import annotations

import ast
import glob
import os

import pytest

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
        'Adicione @permission("<perm>") logo abaixo de @server.tool() (ADR-117).'
    )


# ── Governança de RBAC — roles válidos ────────────────────────────────────────


def test_removed_roles_absent_from_valid_roles():
    """viewer e service-ci foram removidos intencionalmente — não devem reaparecer.

    viewer: removido pois operator já cobre toda a superfície de leitura.
    service-ci: removido pois não há disparadores de CI no sistema.
    """
    from concilium.infrastructure.auth.permission_guard import VALID_ROLES

    reintroduced = {"viewer", "service-ci"} & VALID_ROLES
    assert not reintroduced, (
        f"Roles removidos intencionalmente reapareceram em VALID_ROLES: {reintroduced}. "
        "viewer e service-ci foram eliminados — use operator, engineer, admin, auditor ou catalog-manager."
    )


def test_active_roles_are_exactly_the_expected_set():
    """Conjunto de roles deve ser exatamente {operator, engineer, admin, auditor, catalog-manager}.

    Garante que nenhum role foi adicionado ou removido sem revisão explícita.
    """
    from concilium.infrastructure.auth.permission_guard import VALID_ROLES

    expected = {"operator", "engineer", "admin", "auditor", "catalog-manager"}
    assert VALID_ROLES == expected, (
        f"VALID_ROLES divergiu do esperado.\n"
        f"  Esperado:  {sorted(expected)}\n"
        f"  Atual:     {sorted(VALID_ROLES)}\n"
        "Se adicionou ou removeu um role intencionalmente, atualize este teste."
    )


# ── Governança de storage — contratos de BlobStoragePort ─────────────────────


def test_sharepoint_adapter_implements_deletar_blob():
    """SharePointBlobStorage deve implementar deletar_blob (não apenas o noop da porta).

    deletar_blob foi adicionado ao BlobStoragePort com noop default, mas SharePoint
    tem suporte real via Graph DELETE. Se a implementação desaparecer, o teardown
    de projetos de teste ficará silenciosamente quebrado.
    """
    from concilium.domain.repositories.blob_storage_port import BlobStoragePort
    from concilium.infrastructure.adapters.blob_storage.sharepoint import SharePointBlobStorage

    assert hasattr(SharePointBlobStorage, "deletar_blob"), (
        "SharePointBlobStorage não tem deletar_blob — implementação foi removida?"
    )
    # Garante que é override real, não o noop herdado da porta
    assert SharePointBlobStorage.deletar_blob is not BlobStoragePort.deletar_blob, (
        "SharePointBlobStorage.deletar_blob é o noop herdado da porta — "
        "a implementação real via Graph DELETE foi perdida."
    )
