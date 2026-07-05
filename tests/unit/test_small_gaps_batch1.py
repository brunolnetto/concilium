"""Tests for small-gap files: benchmark repository port, week_sequence, config mixin,
permission_guard, rate_limit, jwt_auth, replan MCP tool."""

from __future__ import annotations

import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest


# ─── domain/benchmark/repository.py (abstract methods) ────────────────────────
class TestWeekIndex:
    def test_seq_format(self):
        from concilium.domain.services.planning.week_sequence import week_index

        assert week_index("S001") == 1
        assert week_index("S052") == 52

    def test_iso_format(self):
        from concilium.domain.services.planning.week_sequence import week_index

        assert week_index("2026-W01") > 0
        assert week_index("2026-W02") > week_index("2026-W01")

    def test_numeric_fallback(self):
        from concilium.domain.services.planning.week_sequence import week_index

        assert week_index("10") == 10

    def test_invalid_returns_zero(self):
        from concilium.domain.services.planning.week_sequence import week_index

        assert week_index("bad") == 0

    def test_iso_bad_date_returns_zero(self):
        from concilium.domain.services.planning.week_sequence import week_index

        assert week_index("2026-W99") == 0


class TestNextWeek:
    def test_seq_increments(self):
        from concilium.domain.services.planning.week_sequence import next_week

        assert next_week("S001") == "S002"
        assert next_week("S010") == "S011"

    def test_iso_increments(self):
        from concilium.domain.services.planning.week_sequence import next_week

        result = next_week("2026-W01")
        assert result == "2026-W02"

    def test_iso_year_rollover(self):
        from concilium.domain.services.planning.week_sequence import next_week

        result = next_week("2026-W52")
        assert "-W" in result

    def test_numeric_fallback(self):
        from concilium.domain.services.planning.week_sequence import next_week

        assert next_week("5") == "6"

    def test_invalid_returns_unchanged(self):
        from concilium.domain.services.planning.week_sequence import next_week

        assert next_week("bad") == "bad"


class TestEnumerarSemanas:
    def test_seq_range(self):
        from concilium.domain.services.planning.week_sequence import enumerar_semanas

        result = enumerar_semanas("S001", "S003")
        assert result == ["S001", "S002", "S003"]

    def test_iso_range(self):
        from concilium.domain.services.planning.week_sequence import enumerar_semanas

        result = enumerar_semanas("2026-W01", "2026-W03")
        assert len(result) == 3

    def test_empty_when_fim_before_inicio(self):
        from concilium.domain.services.planning.week_sequence import enumerar_semanas

        assert enumerar_semanas("S003", "S001") == []

    def test_empty_when_none(self):
        from concilium.domain.services.planning.week_sequence import enumerar_semanas

        assert enumerar_semanas(None, "S001") == []
        assert enumerar_semanas("S001", None) == []
        assert enumerar_semanas("", "S001") == []

    def test_single_week(self):
        from concilium.domain.services.planning.week_sequence import enumerar_semanas

        assert enumerar_semanas("S005", "S005") == ["S005"]


# ─── application/runtime/mixins/config.py ─────────────────────────────────────


class TestConfigMixin:
    def _make(self, tmp_path):
        from concilium.application.runtime.mixins.config import ConfigMixin

        return ConfigMixin(config_root=tmp_path)

    def test_load_tema_default_when_missing(self, tmp_path):
        cm = self._make(tmp_path)
        tema = cm.load_tema()  # no tema dir → falls back to TEMA_DEFAULT
        assert tema is not None

    def test_load_tema_cached(self, tmp_path):
        cm = self._make(tmp_path)
        t1 = cm.load_tema()
        t2 = cm.load_tema()
        assert t1 is t2

    def test_load_tema_invalid_json_returns_default(self, tmp_path):
        tema_dir = tmp_path / "temas" / "custom"
        tema_dir.mkdir(parents=True)
        (tema_dir / "tema.json").write_text("NOT JSON")
        cm = self._make(tmp_path)
        tema = cm.load_tema("custom")
        from concilium.domain.models.catalog.tema import TEMA_DEFAULT

        assert tema is TEMA_DEFAULT

    def test_load_contexto_missing_raises(self, tmp_path):
        from concilium.application.runtime.exceptions import RuntimeDomainError

        cm = self._make(tmp_path)
        with pytest.raises(RuntimeDomainError):
            cm.load_contexto("nonexistent")

    def test_load_jurisdicao_with_parent(self, tmp_path):
        jur_dir = tmp_path / "jurisdicoes"
        jur_dir.mkdir()
        (jur_dir / "parent.json").write_text('{"name": "Parent", "base": 1}')
        (jur_dir / "child.json").write_text('{"parent_id": "parent", "base": 2}')
        cm = self._make(tmp_path)
        result = cm.load_jurisdicao("child")
        assert result["base"] == 2  # child overrides parent

    def test_load_calendario_operacional_merges_all_levels(self, tmp_path):
        cal_dir = tmp_path / "calendarios"
        (cal_dir).mkdir()
        global_cal = {"eventos": [{"id": "E1", "tipo": "feriado"}]}
        (cal_dir / "global.json").write_text(json.dumps(global_cal))
        jur_dir = cal_dir / "jurisdicao"
        jur_dir.mkdir()
        (jur_dir / "jur-1.json").write_text('{"eventos": [{"id": "E2", "tipo": "regional"}]}')
        proj_dir = cal_dir / "projeto"
        proj_dir.mkdir()
        (proj_dir / "proj-1.json").write_text('{"eventos": [{"id": "E1", "tipo": "override"}]}')
        cm = self._make(tmp_path)
        cal = cm.load_calendario_operacional(jurisdicao_id="jur-1", project_id="proj-1")
        event_ids = {e["id"] for e in cal["eventos"]}
        assert "E1" in event_ids  # global (overridden by project)
        assert "E2" in event_ids  # jurisdicao

    def test_load_calendario_cached(self, tmp_path):
        cm = self._make(tmp_path)
        c1 = cm.load_calendario_operacional()
        c2 = cm.load_calendario_operacional()
        assert c1 is c2

    def test_deep_merge(self, tmp_path):
        cm = self._make(tmp_path)
        result = cm._deep_merge({"a": 1, "b": {"c": 2}}, {"b": {"d": 3}, "e": 5})
        assert result["a"] == 1
        assert result["b"]["c"] == 2
        assert result["b"]["d"] == 3
        assert result["e"] == 5


# ─── infrastructure/auth/permission_guard.py ──────────────────────────────────


class TestPermissionGuard:
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


# ─── presentation/api/rate_limit.py ───────────────────────────────────────────


class TestRateLimit:
    def test_rate_limit_key_uses_jwt_sub(self):
        from concilium.presentation.api.rate_limit import _rate_limit_key

        req = MagicMock()
        req.headers = {"Authorization": "Bearer mytoken"}
        with patch(
            "concilium.infrastructure.auth.token_service.decode_token",
            return_value={"sub": "user-123"},
        ):
            result = _rate_limit_key(req)
        assert result == "user:user-123"

    def test_rate_limit_key_falls_back_to_ip(self):
        from concilium.presentation.api.rate_limit import _rate_limit_key

        req = MagicMock()
        req.headers = {}
        with patch("concilium.presentation.api.rate_limit.get_remote_address", return_value="1.2.3.4"):
            result = _rate_limit_key(req)
        assert result == "ip:1.2.3.4"

    def test_rate_limit_key_decode_exception_falls_back(self):
        from concilium.presentation.api.rate_limit import _rate_limit_key

        req = MagicMock()
        req.headers = {"Authorization": "Bearer badtoken"}
        with (
            patch("concilium.infrastructure.auth.token_service.decode_token", side_effect=ValueError("bad")),
            patch("concilium.presentation.api.rate_limit.get_remote_address", return_value="5.6.7.8"),
        ):
            result = _rate_limit_key(req)
        assert result == "ip:5.6.7.8"

    def test_rate_limit_exceeded_handler_does_not_raise(self):
        from slowapi.errors import RateLimitExceeded

        from concilium.presentation.api.rate_limit import rate_limit_exceeded_handler

        req = MagicMock()
        req.url.path = "/runs"
        exc = MagicMock(spec=RateLimitExceeded)
        with (
            patch("concilium.infrastructure.telemetry.record_rate_limit_exceeded"),
            patch("concilium.presentation.api.rate_limit._slowapi_429", return_value=MagicMock()),
        ):
            result = rate_limit_exceeded_handler(req, exc)
        assert result is not None


# ─── presentation/api/middleware/jwt_auth.py ──────────────────────────────────


class TestJWTAuthMiddleware:
    def _make_middleware(self):
        from concilium.presentation.api.middleware.jwt_auth import JWTAuthMiddleware

        app_mock = MagicMock()
        return JWTAuthMiddleware(app_mock)

    def _make_request(self, path: str = "/runs", auth_header: str = "") -> MagicMock:
        req = MagicMock()
        req.url.path = path
        req.headers = {"Authorization": auth_header} if auth_header else {}
        req.state = MagicMock()
        return req

    @pytest.mark.asyncio
    async def test_skip_path_passes_through(self):
        mw = self._make_middleware()
        req = self._make_request(path="/health")
        call_next = AsyncMock(return_value=MagicMock())
        with patch("concilium.presentation.api.middleware.jwt_auth._auth_enabled", return_value=True):
            await mw.dispatch(req, call_next)
        call_next.assert_called_once_with(req)

    @pytest.mark.asyncio
    async def test_auth_disabled_passes_through(self):
        mw = self._make_middleware()
        req = self._make_request(path="/runs")
        call_next = AsyncMock(return_value=MagicMock())
        with patch("concilium.presentation.api.middleware.jwt_auth._auth_enabled", return_value=False):
            await mw.dispatch(req, call_next)
        call_next.assert_called_once()

    @pytest.mark.asyncio
    async def test_missing_bearer_returns_401(self):
        from fastapi.responses import JSONResponse

        mw = self._make_middleware()
        req = self._make_request(path="/runs", auth_header="")
        call_next = AsyncMock()
        with patch("concilium.presentation.api.middleware.jwt_auth._auth_enabled", return_value=True):
            result = await mw.dispatch(req, call_next)
        assert isinstance(result, JSONResponse)
        assert result.status_code == 401
        call_next.assert_not_called()

    @pytest.mark.asyncio
    async def test_invalid_token_returns_401(self):
        from fastapi.responses import JSONResponse

        mw = self._make_middleware()
        req = self._make_request(path="/runs", auth_header="Bearer badtoken")
        call_next = AsyncMock()
        with (
            patch("concilium.presentation.api.middleware.jwt_auth._auth_enabled", return_value=True),
            patch("concilium.infrastructure.auth.token_service.decode_token", side_effect=ValueError("bad")),
        ):
            result = await mw.dispatch(req, call_next)
        assert isinstance(result, JSONResponse)
        assert result.status_code == 401

    @pytest.mark.asyncio
    async def test_valid_token_sets_claims_and_passes_through(self):
        mw = self._make_middleware()
        req = self._make_request(path="/runs", auth_header="Bearer validtoken")
        call_next = AsyncMock(return_value=MagicMock())
        with (
            patch("concilium.presentation.api.middleware.jwt_auth._auth_enabled", return_value=True),
            patch("concilium.infrastructure.auth.token_service.decode_token", return_value={"sub": "u1"}),
        ):
            await mw.dispatch(req, call_next)
        assert req.state.jwt_claims == {"sub": "u1"}
        call_next.assert_called_once()


# ─── presentation/mcp/tools/replan.py (missing lines 122-129, 145-146) ────────


class TestReplanMcpTool:
    def _register_tools(self, monkeypatch, tmp_path):
        import importlib

        config_dir = tmp_path / "config"
        config_dir.mkdir(parents=True, exist_ok=True)
        monkeypatch.setenv("CONCILIUM__CONFIG_ROOT", str(config_dir))
        from mcp.server.fastmcp import FastMCP

        mod = importlib.import_module("concilium.presentation.mcp.tools.replan")
        server = FastMCP("test-replan")
        mod.register(server)
        tools: dict = {}
        for t in server._tool_manager.list_tools():
            fn = getattr(t, "fn", None) or getattr(t, "func", None)
            tools[t.name] = fn
        return tools

    def _make_flat_store(self, canonical):
        store = MagicMock()
        store.escopo.side_effect = RuntimeError("sem escopos")
        store.load_canonical.return_value = canonical
        return store

    def test_simular_cenario_no_canonical(self, monkeypatch, tmp_path):
        tools = self._register_tools(monkeypatch, tmp_path)
        store = self._make_flat_store(None)
        with patch("concilium.presentation.mcp._context._project", return_value=store):
            result = tools["simular_cenario_replan"](project_id="proj-1", tipo="lever_adjust", parametros={})
        assert "erro" in result

    def test_simular_cenario_unsupported_type(self, monkeypatch, tmp_path):
        tools = self._register_tools(monkeypatch, tmp_path)
        store = self._make_flat_store(MagicMock())
        with patch("concilium.presentation.mcp._context._project", return_value=store):
            result = tools["simular_cenario_replan"](project_id="proj-1", tipo="unsupported_type", parametros={})
        assert "erro" in result
        assert "tipos_suportados" in result

    def test_simular_cenario_exception(self, monkeypatch, tmp_path):
        tools = self._register_tools(monkeypatch, tmp_path)
        with patch(
            "concilium.presentation.mcp._context._project",
            side_effect=RuntimeError("boom"),
        ):
            result = tools["simular_cenario_replan"](project_id="proj-1", tipo="lever_adjust", parametros={})
        assert "erro" in result
