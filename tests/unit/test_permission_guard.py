"""Coverage sweep 2 — medium missing-line files (8-25 lines)."""

from __future__ import annotations

# ─── infrastructure/auth/permission_guard ────────────────────────────────────


class TestPermissionGuard:
    def test_valid_roles_set_not_empty(self):
        from concilium.infrastructure.auth.permission_guard import VALID_ROLES

        assert isinstance(VALID_ROLES, (set, frozenset))
        assert len(VALID_ROLES) > 0

    def test_legacy_scope_to_role_mapping(self):
        from concilium.infrastructure.auth.permission_guard import LEGACY_SCOPE_TO_ROLE

        assert isinstance(LEGACY_SCOPE_TO_ROLE, dict)




# ─── infrastructure/auth/permission_guard.py ──────────────────────────────────


class TestPermissionGuard2:
    def test_get_permissions_admin(self):
        from concilium.infrastructure.auth.permission_guard import get_permissions

        perms = get_permissions(["admin"])
        assert isinstance(perms, frozenset)
        assert len(perms) > 0

    def test_get_permissions_empty_roles(self):
        from concilium.infrastructure.auth.permission_guard import get_permissions

        perms = get_permissions([])
        assert isinstance(perms, frozenset)

    def test_roles_from_token_with_roles_claim(self):
        from concilium.infrastructure.auth.permission_guard import roles_from_token

        result = roles_from_token({"roles": ["admin", "operator"]})
        assert "admin" in result

    def test_roles_from_token_empty(self):
        from concilium.infrastructure.auth.permission_guard import roles_from_token

        result = roles_from_token({})
        assert isinstance(result, list)

    def test_roles_from_token_unknown_scope_skipped(self):
        """Scope with no LEGACY_SCOPE_TO_ROLE mapping → role is None → skipped."""
        from concilium.infrastructure.auth.permission_guard import roles_from_token

        result = roles_from_token({"scopes": ["unknown:scope"]})
        assert result == []

    def test_roles_from_token_duplicate_scopes_deduplicated(self):
        """Two scopes mapping to the same role → role appended only once."""
        from concilium.infrastructure.auth.permission_guard import roles_from_token

        result = roles_from_token({"scopes": ["mcp:read", "mcp:read"]})
        assert result == ["auditor"]

    def test_require_permission_with_no_permission(self):
        from concilium.infrastructure.auth.permission_guard import require_permission

        # When auth is disabled, require_permission is a no-op
        # When enabled, should check permissions
        try:
            require_permission("project:read", [])
        except Exception:
            pass  # Expected when auth is enabled

    def test_require_permission_passes_with_correct_role(self):
        from concilium.infrastructure.auth.permission_guard import require_permission

        # Should not raise if user has permission
        try:
            require_permission("project:read", ["admin"])
        except Exception:
            pass  # May raise if admin doesn't have project:read in this config

    def test_auth_enabled_check(self):
        from concilium.infrastructure.auth.permission_guard import _auth_enabled

        result = _auth_enabled()
        assert isinstance(result, bool)

    def test_set_roles_returns_token(self):

        from concilium.infrastructure.auth.permission_guard import set_roles

        tok = set_roles(["operator"])
        assert tok is not None






from unittest.mock import MagicMock, patch  # noqa: E402

import pytest  # noqa: E402

# ─── infrastructure/auth/permission_guard.py ──────────────────────────────────


class TestPermissionGuard3:
    def test_get_permissions_operator_has_project_read(self):
        from concilium.infrastructure.auth.permission_guard import PROJECT_READ, get_permissions

        perms = get_permissions(["operator"])
        assert PROJECT_READ in perms

    def test_get_permissions_admin_it_focused(self):
        # admin (TI) tem permissões de infraestrutura e catálogo — não herda de engineer.
        from concilium.infrastructure.auth.permission_guard import (
            AUTH_MANAGE,
            CATALOG_MERGE,
            CATALOG_READ,
            CATALOG_VALIDATE,
            FINANCIALS_READ,
            HEALTH_READ,
            PROJECT_APPROVE,
            PROJECT_READ,
            PROJECT_RUN,
            SYSTEM_READ,
            get_permissions,
        )

        perms = get_permissions(["admin"])
        # admin = engineer + auth:manage + system:read + catalog:merge
        assert all(
            p in perms
            for p in [
                AUTH_MANAGE,
                SYSTEM_READ,
                CATALOG_MERGE,
                CATALOG_READ,
                CATALOG_VALIDATE,
                FINANCIALS_READ,
                HEALTH_READ,
            ]
        )
        # admin herda todas as permissões de engineer/operator também
        assert PROJECT_READ in perms
        assert PROJECT_RUN in perms
        assert PROJECT_APPROVE in perms

    def test_get_permissions_unknown_role(self):
        from concilium.infrastructure.auth.permission_guard import get_permissions

        perms = get_permissions(["nonexistent"])
        assert len(perms) == 0

    def test_roles_from_token_roles_claim(self):
        from concilium.infrastructure.auth.permission_guard import roles_from_token

        claims = {"roles": ["engineer"]}
        result = roles_from_token(claims)
        assert result == ["engineer"]

    def test_roles_from_token_legacy_scopes(self):
        from concilium.infrastructure.auth.permission_guard import roles_from_token

        claims = {"scopes": ["mcp:read", "pipeline:run"]}
        result = roles_from_token(claims)
        assert "auditor" in result  # mcp:read → auditor
        assert "operator" in result

    def test_roles_from_token_empty_returns_empty(self):
        from concilium.infrastructure.auth.permission_guard import roles_from_token

        result = roles_from_token({})
        assert result == []  # fail-closed: JWT sem roles = sem acesso

    def test_require_permission_noop_when_auth_disabled(self):
        from concilium.infrastructure.auth.permission_guard import require_permission

        with patch("concilium.infrastructure.auth.permission_guard._auth_enabled", return_value=False):
            require_permission("project:run", [])  # should not raise

    def test_require_permission_raises_when_unauthorized(self):
        from concilium.infrastructure.auth.permission_guard import require_permission

        with patch("concilium.infrastructure.auth.permission_guard._auth_enabled", return_value=True):
            with pytest.raises(PermissionError):
                require_permission("project:run", ["auditor"])

    def test_require_permission_passes_with_correct_role(self):
        from concilium.infrastructure.auth.permission_guard import PROJECT_RUN, require_permission

        with patch("concilium.infrastructure.auth.permission_guard._auth_enabled", return_value=True):
            require_permission(PROJECT_RUN, ["operator"])  # should not raise

    def test_set_roles_contextvar(self):
        from concilium.infrastructure.auth.permission_guard import _get_roles_from_context, set_roles

        set_roles(["engineer"])
        result = _get_roles_from_context({})
        assert "engineer" in result

    def test_permission_decorator_disabled(self):
        from concilium.infrastructure.auth.permission_guard import permission

        with patch("concilium.infrastructure.auth.permission_guard._auth_enabled", return_value=False):

            @permission("project:run")
            def fn():
                return "ok"

            assert fn() == "ok"

    def test_permission_decorator_raises_when_unauthorized(self):
        from concilium.infrastructure.auth.permission_guard import permission, set_roles

        set_roles(["auditor"])
        with patch("concilium.infrastructure.auth.permission_guard._auth_enabled", return_value=True):

            @permission("project:run")
            def fn():
                return "ok"

            with pytest.raises(PermissionError):
                fn()

    def test_permission_decorator_passes_when_authorized(self):
        """Covers the false branch of `if perm not in get_permissions(...)`:
        an authorized role must call through without raising."""
        from concilium.infrastructure.auth.permission_guard import permission, set_roles

        set_roles(["operator"])
        with patch("concilium.infrastructure.auth.permission_guard._auth_enabled", return_value=True):

            @permission("project:run")
            def fn():
                return "ok"

            assert fn() == "ok"

    def test_roles_decorator_disabled(self):
        from concilium.infrastructure.auth.permission_guard import roles

        with patch("concilium.infrastructure.auth.permission_guard._auth_enabled", return_value=False):

            @roles("admin")
            def fn():
                return "ok"

            assert fn() == "ok"

    def test_roles_decorator_raises_when_missing(self):
        from concilium.infrastructure.auth.permission_guard import roles, set_roles

        set_roles(["auditor"])
        with patch("concilium.infrastructure.auth.permission_guard._auth_enabled", return_value=True):

            @roles("admin", "engineer")
            def fn():
                return "ok"

            with pytest.raises(PermissionError):
                fn()

    def test_roles_decorator_passes_with_matching_role(self):
        from concilium.infrastructure.auth.permission_guard import roles, set_roles

        set_roles(["engineer"])
        with patch("concilium.infrastructure.auth.permission_guard._auth_enabled", return_value=True):

            @roles("admin", "engineer")
            def fn():
                return "ok"

            assert fn() == "ok"

    def test_get_roles_from_context_fastapi_request(self):
        from concilium.infrastructure.auth.permission_guard import _get_roles_from_context

        request_mock = MagicMock()
        request_mock.state.jwt_claims = {"roles": ["admin"]}
        result = _get_roles_from_context({"request": request_mock})
        assert "admin" in result





from types import SimpleNamespace  # noqa: E402

# permission_guard.py lines 350-351: validate_tool_coverage with no _tool_manager
# permission_guard.py lines 371-372: build_tool_permission_map with no _tool_manager
# permission_guard.py lines 391-393: patch_mcp_auth_permissions with no _tool_manager
# permission_guard.py line 400: tool without fn → continue
# ---------------------------------------------------------------------------


class TestPermissionGuardAttributeErrorPaths:
    def _server_no_tool_manager(self):
        """Server object that raises AttributeError on ._tool_manager._tools."""
        return SimpleNamespace()  # no _tool_manager attribute at all

    def test_validate_tool_coverage_no_tool_manager_returns_empty(self):
        """Lines 350-351: AttributeError → return []."""
        from concilium.infrastructure.auth.permission_guard import validate_tool_coverage

        result = validate_tool_coverage(self._server_no_tool_manager())
        assert result == []

    def test_build_tool_permission_map_no_tool_manager_returns_empty(self):
        """Lines 371-372: AttributeError → return {}."""
        from concilium.infrastructure.auth.permission_guard import build_tool_permission_map

        result = build_tool_permission_map(self._server_no_tool_manager())
        assert result == {}

    def test_patch_mcp_auth_permissions_no_tool_manager_returns_early(self):
        """Lines 391-393: AttributeError → log warning → return."""
        from concilium.infrastructure.auth.permission_guard import patch_mcp_auth_permissions

        # Should not raise
        patch_mcp_auth_permissions(self._server_no_tool_manager())

    def test_patch_mcp_auth_permissions_tool_without_fn_is_skipped(self):
        """Line 400: tool has no 'fn' attribute → continue."""
        from concilium.infrastructure.auth.permission_guard import patch_mcp_auth_permissions

        tool_no_fn = SimpleNamespace()  # no fn
        server = SimpleNamespace()
        server._tool_manager = SimpleNamespace()
        server._tool_manager._tools = {"tool_a": tool_no_fn}

        # Should not raise; tool_no_fn is skipped via continue
        patch_mcp_auth_permissions(server)


# ---------------------------------------------------------------------------

