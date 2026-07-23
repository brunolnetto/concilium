"""Tests for ROLE_VISIBILITY / visible_roles_for / AUTH_LIST_VISIBLE (ADR-143 D1/D2)."""

from __future__ import annotations

from concilium.infrastructure.auth.permission_guard import (
    AUTH_LIST_VISIBLE,
    ROLE_PERMISSIONS,
    ROLE_VISIBILITY,
    VALID_ROLES,
    visible_roles_for,
)


class TestAuthListVisiblePermission:
    def test_all_valid_roles_have_the_permission(self):
        """Todo role pode chamar a tool — a matriz de visibilidade filtra o quê, não o se."""
        for role in VALID_ROLES:
            assert AUTH_LIST_VISIBLE in ROLE_PERMISSIONS[role], f"role '{role}' sem auth:list-visible"


class TestRoleVisibilityMatrix:
    def test_every_valid_role_has_a_visibility_entry(self):
        assert set(ROLE_VISIBILITY.keys()) == set(VALID_ROLES)

    def test_admin_sees_all_roles(self):
        assert ROLE_VISIBILITY["admin"] == VALID_ROLES

    def test_auditor_sees_all_roles(self):
        assert ROLE_VISIBILITY["auditor"] == VALID_ROLES

    def test_engineer_sees_engineer_and_admin_only(self):
        assert ROLE_VISIBILITY["engineer"] == frozenset({"engineer", "admin"})

    def test_operator_sees_operator_engineer_admin(self):
        assert ROLE_VISIBILITY["operator"] == frozenset({"operator", "engineer", "admin"})

    def test_catalog_manager_sees_catalog_manager_and_admin_only(self):
        assert ROLE_VISIBILITY["catalog-manager"] == frozenset({"catalog-manager", "admin"})


class TestVisibleRolesFor:
    def test_single_role(self):
        assert visible_roles_for(["operator"]) == frozenset({"operator", "engineer", "admin"})

    def test_union_across_multiple_roles(self):
        """auditor sozinho já vê tudo — a união com catalog-manager não reduz nada."""
        result = visible_roles_for(["catalog-manager", "auditor"])
        assert result == VALID_ROLES

    def test_union_of_two_narrow_roles(self):
        result = visible_roles_for(["catalog-manager", "engineer"])
        assert result == frozenset({"catalog-manager", "admin", "engineer"})

    def test_unknown_role_contributes_nothing(self):
        assert visible_roles_for(["not-a-real-role"]) == frozenset()

    def test_empty_roles_returns_empty_set(self):
        assert visible_roles_for([]) == frozenset()
