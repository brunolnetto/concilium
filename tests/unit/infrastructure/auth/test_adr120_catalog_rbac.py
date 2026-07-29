"""Testes de ADR-120 — RBAC para Ciclo de Vida do Catálogo.

Cobre:
  F1: CATALOG_VALIDATE, CATALOG_MERGE, role catalog-manager
  F2: auditar_catalogo agora requer catalog:validate (não catalog:read)
  F4: CatalogAction dataclass
  F5: engineer NÃO tem catalog:merge; catalog-manager NÃO tem project:run
"""

from __future__ import annotations

import pytest

# ── F1: Novas permissões e role catalog-manager ───────────────────────────────


class TestNewPermissions:
    def test_catalog_validate_constant_exists(self):
        from concilium.infrastructure.auth.permission_guard import CATALOG_VALIDATE

        assert CATALOG_VALIDATE == "catalog:validate"

    def test_catalog_merge_constant_exists(self):
        from concilium.infrastructure.auth.permission_guard import CATALOG_MERGE

        assert CATALOG_MERGE == "catalog:merge"

    def test_catalog_manager_role_exists(self):
        from concilium.infrastructure.auth.permission_guard import ROLE_PERMISSIONS

        assert "catalog-manager" in ROLE_PERMISSIONS

    def test_catalog_manager_has_merge(self):
        from concilium.infrastructure.auth.permission_guard import ROLE_PERMISSIONS

        assert "catalog:merge" in ROLE_PERMISSIONS["catalog-manager"]

    def test_catalog_manager_has_validate(self):
        from concilium.infrastructure.auth.permission_guard import ROLE_PERMISSIONS

        assert "catalog:validate" in ROLE_PERMISSIONS["catalog-manager"]

    def test_catalog_manager_has_write(self):
        from concilium.infrastructure.auth.permission_guard import ROLE_PERMISSIONS

        assert "catalog:write" in ROLE_PERMISSIONS["catalog-manager"]

    def test_catalog_manager_has_financials(self):
        from concilium.infrastructure.auth.permission_guard import ROLE_PERMISSIONS

        assert "financials:read" in ROLE_PERMISSIONS["catalog-manager"]

    def test_catalog_manager_no_project_run(self):
        from concilium.infrastructure.auth.permission_guard import ROLE_PERMISSIONS

        assert "project:run" not in ROLE_PERMISSIONS["catalog-manager"]

    def test_catalog_manager_no_project_create(self):
        from concilium.infrastructure.auth.permission_guard import ROLE_PERMISSIONS

        assert "project:create" not in ROLE_PERMISSIONS["catalog-manager"]

    def test_catalog_manager_no_auth_manage(self):
        from concilium.infrastructure.auth.permission_guard import ROLE_PERMISSIONS

        assert "auth:manage" not in ROLE_PERMISSIONS["catalog-manager"]


class TestEngineerDoesNotHaveMerge:
    """ADR-120 D3: princípio dos 4 olhos — engineer edita, catalog-manager/admin aprova."""

    def test_engineer_no_catalog_merge(self):
        from concilium.infrastructure.auth.permission_guard import ROLE_PERMISSIONS

        assert "catalog:merge" not in ROLE_PERMISSIONS["engineer"]

    def test_engineer_no_longer_has_catalog_write(self):
        """ADR-163 D7 (emenda): engineer restrito a domínio projeto — catalog:write
        passa a ser exclusivo de catalog-manager/admin."""
        from concilium.infrastructure.auth.permission_guard import ROLE_PERMISSIONS

        assert "catalog:write" not in ROLE_PERMISSIONS["engineer"]

    def test_engineer_has_catalog_validate(self):
        from concilium.infrastructure.auth.permission_guard import ROLE_PERMISSIONS

        assert "catalog:validate" in ROLE_PERMISSIONS["engineer"]

    def test_admin_has_catalog_merge(self):
        from concilium.infrastructure.auth.permission_guard import ROLE_PERMISSIONS

        assert "catalog:merge" in ROLE_PERMISSIONS["admin"]

    def test_operator_no_catalog_merge(self):
        from concilium.infrastructure.auth.permission_guard import ROLE_PERMISSIONS

        assert "catalog:merge" not in ROLE_PERMISSIONS["operator"]

    def test_operator_has_catalog_validate(self):
        """ADR-120 D3: operator pode rodar health checks."""
        from concilium.infrastructure.auth.permission_guard import ROLE_PERMISSIONS

        assert "catalog:validate" in ROLE_PERMISSIONS["operator"]

    def test_auditor_no_catalog_write(self):
        from concilium.infrastructure.auth.permission_guard import ROLE_PERMISSIONS

        assert "catalog:write" not in ROLE_PERMISSIONS["auditor"]


class TestAdr163EngineerCatalogWriteRemoved:
    """ADR-163 D7 (emenda ADR-099/ADR-120): engineer = domínio projeto;
    catalog:write/catalog:merge ficam exclusivos de catalog-manager/admin.
    """

    def test_admin_still_has_catalog_write(self):
        """Guarda de regressão: _ADMIN não pode perder catalog:write por herança
        silenciosa de _ENGINEER quando catalog:write for removida de _ENGINEER."""
        from concilium.infrastructure.auth.permission_guard import ROLE_PERMISSIONS

        assert "catalog:write" in ROLE_PERMISSIONS["admin"]

    def test_catalog_manager_still_has_catalog_write(self):
        from concilium.infrastructure.auth.permission_guard import ROLE_PERMISSIONS

        assert "catalog:write" in ROLE_PERMISSIONS["catalog-manager"]

    def test_get_permissions_engineer_alone_no_catalog_write(self):
        from concilium.infrastructure.auth.permission_guard import get_permissions

        assert "catalog:write" not in get_permissions(["engineer"])

    def test_get_permissions_engineer_plus_catalog_manager_has_catalog_write(self):
        """Composição multi-role: engineer + catalog-manager recupera catalog:write
        (e catalog:merge) via união de permissões — mecanismo já existente, sem
        código novo (ADR-120, 'role pode ser combinado')."""
        from concilium.infrastructure.auth.permission_guard import get_permissions

        perms = get_permissions(["engineer", "catalog-manager"])
        assert "catalog:write" in perms
        assert "catalog:merge" in perms
        assert "project:approve" in perms  # continua tendo o lado projeto do engineer

    def test_get_permissions_admin_has_catalog_write(self):
        from concilium.infrastructure.auth.permission_guard import get_permissions

        assert "catalog:write" in get_permissions(["admin"])


class TestAdrOneNinteenIntegration:
    """catalog-manager não tem ProcurementIntent permitido (sem projeto)."""

    def test_catalog_manager_no_allowed_intents(self):
        from concilium.infrastructure.auth.permission_guard import ROLE_ALLOWED_INTENTS

        assert ROLE_ALLOWED_INTENTS.get("catalog-manager", frozenset()) == frozenset()


# ── F2: auditar_catalogo requer catalog:validate ──────────────────────────────


class TestAuditarCatalogoPermission:
    def test_auditar_catalogo_has_catalog_validate(self):
        """ADR-120 F2: auditar_catalogo deve ter @permission('catalog:validate')."""
        import ast

        content = open("src/concilium/presentation/mcp/tools/catalogo.py").read()
        tree = ast.parse(content)
        for node in ast.walk(tree):
            if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                continue
            if node.name != "auditar_catalogo":
                continue
            for d in node.decorator_list:
                if (
                    isinstance(d, ast.Call)
                    and isinstance(d.func, ast.Name)
                    and d.func.id == "permission"
                    and d.args
                    and isinstance(d.args[0], ast.Constant)
                ):
                    assert d.args[0].value == "catalog:validate", (
                        f"auditar_catalogo deve ter catalog:validate, mas tem {d.args[0].value}"
                    )
                    return
        pytest.fail("auditar_catalogo não encontrada ou sem @permission")


# ── F4: CatalogAction ─────────────────────────────────────────────────────────


class TestCatalogAction:
    def test_catalog_action_fields(self):
        from concilium.application.services.project.audit_service import CatalogAction

        ca = CatalogAction(
            action="merge",
            contexto_id="mendeslobo",
            actor_id="catalog-mgr",
            actor_role="catalog-manager",
            rascunho_id="v3",
            n_insumos_afetados=12,
            detalhes={"justificativa": "Reajuste INCC"},
        )
        assert ca.action == "merge"
        assert ca.contexto_id == "mendeslobo"
        assert ca.n_insumos_afetados == 12

    def test_catalog_action_to_dict(self):
        from concilium.application.services.project.audit_service import CatalogAction

        ca = CatalogAction(action="write_draft", contexto_id="samples", actor_id="eng-x")
        d = ca.to_dict()
        assert d["action"] == "write_draft"
        assert "ts" in d

    def test_catalog_action_valid_actions(self):
        from concilium.application.services.project.audit_service import CatalogAction

        for action in ("write_draft", "validate", "merge", "reject"):
            ca = CatalogAction(action=action, contexto_id="ctx")
            assert ca.action == action


# ── F5: Novas tools têm permissions corretas ──────────────────────────────────


class TestNewCatalogToolPermissions:
    def _get_perm(self, tool_name: str) -> str | None:
        import ast
        import glob

        root = "src/concilium/presentation/mcp/tools"
        for f in glob.glob(f"{root}/*.py"):
            tree = ast.parse(open(f).read())
            for node in ast.walk(tree):
                if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    continue
                if node.name != tool_name:
                    continue
                for d in node.decorator_list:
                    if (
                        isinstance(d, ast.Call)
                        and isinstance(d.func, ast.Name)
                        and d.func.id == "permission"
                        and d.args
                        and isinstance(d.args[0], ast.Constant)
                    ):
                        return d.args[0].value
        return None

    def test_criar_rascunho_requires_catalog_write(self):
        assert self._get_perm("criar_rascunho_catalogo") == "catalog:write"

    def test_listar_divergencias_requires_catalog_validate(self):
        assert self._get_perm("listar_divergencias_rascunho") == "catalog:validate"

    def test_consultar_impacto_requires_catalog_validate(self):
        assert self._get_perm("consultar_impacto_reajuste") == "catalog:validate"

    def test_aprovar_merge_requires_catalog_merge(self):
        assert self._get_perm("aprovar_merge_catalogo") == "catalog:merge"

    def test_rejeitar_rascunho_requires_catalog_merge(self):
        assert self._get_perm("rejeitar_rascunho_catalogo") == "catalog:merge"
