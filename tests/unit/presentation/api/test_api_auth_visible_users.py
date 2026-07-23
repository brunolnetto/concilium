"""Tests for GET /auth/users/visible (ADR-143) — chamada direta da função de rota.

Segue o padrão de tests/unit/test_adr126_project_ownership.py: chama a função
de rota diretamente com um Request fake (SimpleNamespace), em vez de subir o
app inteiro via TestClient — mais rápido e isola a lógica de autorização.
"""

from __future__ import annotations

import os
from types import SimpleNamespace
from unittest.mock import patch

import pytest


def _fake_request(roles: list[str], sub: str | None = None) -> SimpleNamespace:
    claims: dict = {"roles": roles}
    if sub is not None:
        claims["sub"] = sub
    return SimpleNamespace(state=SimpleNamespace(jwt_claims=claims))


class TestListVisibleUsersRoute:
    def _call(self, roles, sub=None):
        from concilium.presentation.api.routes.auth import list_visible_users_route

        return list_visible_users_route(request=_fake_request(roles, sub))

    def test_delegates_to_visibility_service_with_claims(self):
        with patch(
            "concilium.application.services.visibility_service.list_visible_users",
            return_value=[{"client_id": "adm1", "email": "adm1@x.com", "roles": ["admin"], "active": True}],
        ) as mock_list:
            result = self._call(["engineer"], sub="eng1")

        mock_list.assert_called_once_with("eng1", ["engineer"])
        assert result.total == 1
        assert result.usuarios[0]["client_id"] == "adm1"

    def test_role_without_permission_denied_when_auth_enabled(self):
        """auditor tem auth:list-visible (todos os roles têm) — usa um role inválido para provar o gate."""
        with (
            patch.dict(os.environ, {"CONCILIUM__AUTH_ENABLED": "1"}),
            patch(
                "concilium.application.services.visibility_service.list_visible_users",
                return_value=[],
            ),
            pytest.raises(PermissionError),
        ):
            self._call(["not-a-real-role"], sub="ghost")

    def test_valid_role_passes_when_auth_enabled(self):
        with (
            patch.dict(os.environ, {"CONCILIUM__AUTH_ENABLED": "1"}),
            patch(
                "concilium.application.services.visibility_service.list_visible_users",
                return_value=[],
            ),
        ):
            result = self._call(["operator"], sub="op1")

        assert result.total == 0
