"""TDD — Item 5: RBAC role ↔ MCP tool mapping.

Cobre:
  - TOOL_PERMISSIONS cobre todas as 55 tools MCP registradas
  - patch_mcp_auth_permissions() bloqueia chamadas não autorizadas
  - patch_mcp_auth_permissions() permite chamadas autorizadas
  - validate_tool_coverage() detecta tools sem mapeamento
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

# ─────────────────────────────────────────────────────────────────────────────
# Fixtures
# ─────────────────────────────────────────────────────────────────────────────

ALL_TOOL_NAMES = [
    # analise
    "auditar_plano",
    "comparar_planos",
    "explorar_pool_recursos",
    # artifacts
    "listar_artefatos_projeto",
    "obter_artefato",  # ADR-116 F5
    # benchmark (ADR-116: listar_benchmarks/executar_benchmark removidas — dup de nep039)
    "empacotar_benchmark",
    "download_benchmark_zip",
    # benchmark_nep039
    "consultar_benchmark",
    # campaign
    "explorar_configuracoes_go",
    "listar_runs_campanha",
    "obter_resultado_campanha",
    # catalogo
    "listar_contextos",
    "pesquisar_catalogo",
    "auditar_catalogo",  # ADR-116 F5: consultar_saude + avaliar_plausibilidade + verificar_integridade
    "atualizar_preco_insumo",
    "adicionar_variante_producao",
    "historico_preco_insumo",  # ADR-116 F5
    "comparar_rfi_catalogo",
    "calcular_pu_producao",
    "versoes_catalogo",  # ADR-116 F5
    # escopo
    "consultar_estrutura_projeto",
    "gerir_escopo",  # ADR-116 F5
    # formulario
    "criar_projeto",  # ADR-116 F5
    # pipeline
    "disparar_pipeline",
    "consultar_job_pipeline",
    "listar_jobs_pipeline",
    "cancelar_job_pipeline",
    # (ADR-116: avancar_pipeline removida — deprecada, substituída por disparar_pipeline)
    # projeto
    "listar_projetos",
    "iniciar_orcamento",
    "consultar_status",
    "aprovar_versao",
    "nova_versao",
    "salvar_perfil_bdi",
    # replan
    "simular_cenario_replan",
    # spec
    # system
    "ping",
    # tributacao (ADR-116 F5: 3 → 1 tool unificada)
    "calcular_tributos",
    # catalogo — ciclo de vida (ADR-120: rascunho → merge)
    "criar_rascunho_catalogo",
    "listar_divergencias_rascunho",
    "consultar_impacto_reajuste",
    "aprovar_merge_catalogo",
    "rejeitar_rascunho_catalogo",
    # auth_directory (ADR-143: visibilidade de usuários entre roles)
    "listar_usuarios_visiveis",
]


# ─────────────────────────────────────────────────────────────────────────────
# F1: TOOL_PERMISSIONS cobre todas as tools
# ─────────────────────────────────────────────────────────────────────────────


def _ast_tool_permission_map() -> dict[str, str]:
    """ADR-117: deriva nome→permissão das tags @permission no source das tools (sem servidor vivo)."""
    import ast
    import glob
    import os

    root = os.path.join(os.path.dirname(__file__), "..", "..", "..", "..")
    mapping: dict[str, str] = {}
    for f in sorted(glob.glob(os.path.join(root, "src/concilium/presentation/mcp/tools/*.py"))):
        tree = ast.parse(open(f, encoding="utf-8").read())
        for node in ast.walk(tree):
            if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                continue
            is_tool = any(
                (isinstance(d, ast.Attribute) and d.attr == "tool")
                or (isinstance(d, ast.Call) and isinstance(d.func, ast.Attribute) and d.func.attr == "tool")
                for d in node.decorator_list
            )
            if not is_tool:
                continue
            for d in node.decorator_list:
                if isinstance(d, ast.Call) and isinstance(d.func, ast.Name) and d.func.id == "permission":
                    if d.args and isinstance(d.args[0], ast.Constant):
                        mapping[node.name] = d.args[0].value
    return mapping


class TestToolPermissionsCoverage:
    """ADR-117: toda tool tem @permission inline (fonte única, derivada por introspecção)."""

    def test_all_tools_have_permission_tag(self):
        perm_map = _ast_tool_permission_map()
        missing = [t for t in ALL_TOOL_NAMES if t not in perm_map]
        assert not missing, f"{len(missing)} tools sem @permission inline:\n  " + "\n  ".join(sorted(missing))

    def test_tool_permissions_values_are_valid_permissions(self):
        """Cada permissão declarada via @permission deve ser uma string conhecida."""
        TOOL_PERMISSIONS = _ast_tool_permission_map()

        valid_perms = {
            "project:read",
            "project:create",
            "project:run",
            "project:approve",
            "catalog:read",
            "catalog:write",
            "catalog:validate",  # ADR-120
            "catalog:merge",  # ADR-120
            "artifacts:read",
            "artifacts:download",
            "financials:read",
            "auth:manage",
            "auth:list-visible",  # ADR-143
            "system:read",
            "health:read",
        }
        invalid = {k: v for k, v in TOOL_PERMISSIONS.items() if v not in valid_perms}
        assert not invalid, f"Permissões inválidas: {invalid}"

    def test_write_tools_require_at_least_operator_permission(self):
        """Tools que modificam dados não devem exigir apenas catalog:read ou project:read."""
        TOOL_PERMISSIONS = _ast_tool_permission_map()

        write_tools = {
            "iniciar_orcamento",
            "criar_projeto",
            "disparar_pipeline",
            "atualizar_preco_insumo",
            "adicionar_variante_producao",
            "aprovar_versao",
            "criar_rascunho_catalogo",  # ADR-120
            "aprovar_merge_catalogo",  # ADR-120
            "rejeitar_rascunho_catalogo",  # ADR-120
        }
        read_only = {"project:read", "catalog:read", "artifacts:read", "system:read", "catalog:validate"}
        for tool in write_tools:
            perm = TOOL_PERMISSIONS.get(tool)
            assert perm not in read_only, (
                f"Tool de escrita '{tool}' requer apenas '{perm}' (leitura). "
                "Deve exigir pelo menos project:create, project:run ou catalog:write."
            )


# ─────────────────────────────────────────────────────────────────────────────
# F2: validate_tool_coverage() detecta gaps
# ─────────────────────────────────────────────────────────────────────────────


class TestValidateToolCoverage:
    """validate_tool_coverage(server) detecta tools SEM tag @permission (ADR-117)."""

    def _make_server(self, tools_spec: dict[str, str | None]):
        """Cria servidor simulado. tools_spec: {nome: perm|None}.

        perm=None → fn sem _required_permission (deve ser detectada como não-coberta).
        """
        server = MagicMock()
        tools = {}
        for name, perm in tools_spec.items():
            t = MagicMock()

            def fn():
                return None

            fn.__name__ = name
            if perm is not None:
                fn._required_permission = perm
            t.fn = fn  # fn real (não MagicMock) — sem auto-criação de atributo
            tools[name] = t
        server._tool_manager._tools = tools
        return server

    def test_returns_empty_when_all_tools_tagged(self):
        from concilium.infrastructure.auth.permission_guard import validate_tool_coverage

        server = self._make_server({"a": "project:read", "b": "project:run"})
        assert validate_tool_coverage(server) == []

    def test_returns_untagged_tools(self):
        from concilium.infrastructure.auth.permission_guard import validate_tool_coverage

        server = self._make_server({"ferramenta_nova_sem_permissao": None})
        missing = validate_tool_coverage(server)
        assert "ferramenta_nova_sem_permissao" in missing


# ─────────────────────────────────────────────────────────────────────────────
# F3: patch_mcp_auth_permissions() enforcement
# ─────────────────────────────────────────────────────────────────────────────


class TestPatchMcpAuthPermissions:
    """patch_mcp_auth_permissions() envolve tools com verificação de permissão."""

    def _make_server_with_tool(self, tool_name: str, tool_fn=None, perm: str | None = None):
        server = MagicMock()
        if tool_fn is None:

            def tool_fn():
                return "ok"

            tool_fn.__name__ = tool_name
        if perm is not None:
            tool_fn._required_permission = perm  # ADR-117: tag posta por @permission
        tool = MagicMock()
        tool.fn = tool_fn
        server._tool_manager._tools = {tool_name: tool}
        return server

    def test_authorized_call_passes_through(self):
        """operator pode chamar disparar_pipeline (project:run)."""
        from concilium.infrastructure.auth.permission_guard import (
            _current_roles,
            patch_mcp_auth_permissions,
            set_roles,
        )

        result_holder = []

        def fn():
            result_holder.append("called")

        fn.__name__ = "disparar_pipeline"
        server = self._make_server_with_tool("disparar_pipeline", fn, perm="project:run")
        patch_mcp_auth_permissions(server)
        # Simula roles de operator
        tok = set_roles(["operator"])
        try:
            server._tool_manager._tools["disparar_pipeline"].fn()
        finally:
            _current_roles.reset(tok)
        assert "called" in result_holder

    def test_unauthorized_call_raises_permission_error(self):
        """auditor não pode chamar disparar_pipeline (project:run) quando auth ativo."""
        from concilium.infrastructure.auth.permission_guard import (
            _current_roles,
            patch_mcp_auth_permissions,
            set_roles,
        )

        def fn():
            pass

        fn.__name__ = "disparar_pipeline"
        server = self._make_server_with_tool("disparar_pipeline", fn, perm="project:run")
        patch_mcp_auth_permissions(server)
        tok = set_roles(["auditor"])
        with patch("concilium.infrastructure.auth.permission_guard._auth_enabled", return_value=True):
            try:
                with pytest.raises(PermissionError):
                    server._tool_manager._tools["disparar_pipeline"].fn()
            finally:
                _current_roles.reset(tok)

    def test_authorized_call_passes_through_with_auth_enabled(self):
        """Com auth explicitamente ativo, role correta faz o `if` em get_permissions
        avaliar False e cair no `return fn(...)` (branch 420->426, não exercitado
        pelos outros testes pois eles não forçam _auth_enabled=True com role válida)."""
        from concilium.infrastructure.auth.permission_guard import (
            _current_roles,
            patch_mcp_auth_permissions,
            set_roles,
        )

        result_holder = []

        def fn():
            result_holder.append("called")

        fn.__name__ = "disparar_pipeline"
        server = self._make_server_with_tool("disparar_pipeline", fn, perm="project:run")
        patch_mcp_auth_permissions(server)
        tok = set_roles(["operator"])
        with patch("concilium.infrastructure.auth.permission_guard._auth_enabled", return_value=True):
            try:
                server._tool_manager._tools["disparar_pipeline"].fn()
            finally:
                _current_roles.reset(tok)
        assert "called" in result_holder

    def test_auditor_can_call_read_tool(self):
        """auditor pode chamar listar_projetos (project:read)."""
        from concilium.infrastructure.auth.permission_guard import (
            _current_roles,
            patch_mcp_auth_permissions,
            set_roles,
        )

        result_holder = []

        def fn():
            result_holder.append("read_ok")

        fn.__name__ = "listar_projetos"
        server = self._make_server_with_tool("listar_projetos", fn, perm="project:read")
        patch_mcp_auth_permissions(server)
        tok = set_roles(["auditor"])
        try:
            server._tool_manager._tools["listar_projetos"].fn()
        finally:
            _current_roles.reset(tok)
        assert "read_ok" in result_holder

    def test_untagged_tool_is_fail_closed(self):
        """ADR-117: tool sem tag @permission → fail-closed (exige auth:manage, só admin).

        operator NÃO tem auth:manage → negado quando auth ativo. O default deixou de
        ser project:read (permissivo) para auth:manage (restritivo) — segurança por omissão.
        """
        from concilium.infrastructure.auth.permission_guard import (
            _current_roles,
            patch_mcp_auth_permissions,
            set_roles,
        )

        def fn():
            return "executou"

        fn.__name__ = "tool_nova_sem_mapeamento"
        server = self._make_server_with_tool("tool_nova_sem_mapeamento", fn)  # sem perm= → sem tag
        patch_mcp_auth_permissions(server)
        tok = set_roles(["operator"])
        with patch("concilium.infrastructure.auth.permission_guard._auth_enabled", return_value=True):
            try:
                with pytest.raises(PermissionError):
                    server._tool_manager._tools["tool_nova_sem_mapeamento"].fn()
            finally:
                _current_roles.reset(tok)


class _FakeMcpRequest:
    """Request-like stub exposing só o que _mcp_message_claims()/get_current_mcp_session_id()
    leem: .headers.get(...)."""

    def __init__(self, authorization: str | None, mcp_session_id: str | None = None):
        self._authorization = authorization
        self._mcp_session_id = mcp_session_id

    @property
    def headers(self):
        headers = {}
        if self._authorization:
            headers["authorization"] = self._authorization
        if self._mcp_session_id:
            headers["mcp-session-id"] = self._mcp_session_id
        return headers


class TestStatefulSessionRoleResolution:
    """Regressão: roles de tool call MCP devem vir da mensagem atual (request_ctx do
    SDK), não do contextvar _current_roles — que fica congelado no contexto da
    sessão em transporte streamable-http *stateful* (padrão do SDK MCP), já que o
    SDK despacha tools/call de requisições subsequentes numa task persistente
    criada na abertura da sessão. Sintoma real reportado: 'Roles do token:
    [(nenhum)]' para um token com roles corretos, porque o contextvar setado pelo
    McpAuthMiddleware na requisição HTTP da tool call nunca chegava à task que
    de fato invoca a tool."""

    def _patch_request_ctx(self, fake_ctx):
        # contextvars.ContextVar.get é read-only em nível de C — não dá para
        # patchear o atributo diretamente; substitui-se o objeto inteiro.
        return patch(
            "mcp.server.lowlevel.server.request_ctx",
            MagicMock(get=MagicMock(return_value=fake_ctx)),
        )

    def test_uses_per_message_roles_over_stale_contextvar(self):
        """_current_roles vazio/sem permissão (simula sessão congelada) mas o
        request_ctx da mensagem atual carrega um Bearer válido com roles
        corretos → a tool executa usando os roles da mensagem, não o contextvar."""
        from concilium.infrastructure.auth.permission_guard import (
            _current_roles,
            patch_mcp_auth_permissions,
            set_roles,
        )

        def fn():
            return "executou"

        fn.__name__ = "disparar_pipeline"
        server = self._make_server_with_tool("disparar_pipeline", fn, perm="project:run")
        patch_mcp_auth_permissions(server)

        fake_ctx = MagicMock(request=_FakeMcpRequest("Bearer real-jwt"))
        tok = set_roles([])  # contextvar deliberadamente sem nenhum role (congelado/vazio)
        try:
            with (
                patch("concilium.infrastructure.auth.permission_guard._auth_enabled", return_value=True),
                self._patch_request_ctx(fake_ctx),
                patch(
                    "concilium.infrastructure.auth.token_service.decode_token",
                    return_value={"sub": "bruno", "roles": ["operator"]},
                ),
            ):
                result = server._tool_manager._tools["disparar_pipeline"].fn()
        finally:
            _current_roles.reset(tok)
        assert result == "executou"

    def test_falls_back_to_contextvar_when_no_request_ctx(self):
        """Sem request_ctx ativo (ex.: stdio, ou teste que só chama set_roles direto)
        continua caindo no contextvar legado — comportamento pré-existente preservado."""
        from concilium.infrastructure.auth.permission_guard import (
            _current_roles,
            patch_mcp_auth_permissions,
            set_roles,
        )

        def fn():
            return "executou"

        fn.__name__ = "disparar_pipeline"
        server = self._make_server_with_tool("disparar_pipeline", fn, perm="project:run")
        patch_mcp_auth_permissions(server)

        tok = set_roles(["operator"])
        try:
            with (
                patch("concilium.infrastructure.auth.permission_guard._auth_enabled", return_value=True),
                self._patch_request_ctx(None),
            ):
                result = server._tool_manager._tools["disparar_pipeline"].fn()
        finally:
            _current_roles.reset(tok)
        assert result == "executou"

    def test_falls_back_to_contextvar_when_no_bearer_header(self):
        """request_ctx presente mas sem Authorization Bearer → cai no contextvar."""
        from concilium.infrastructure.auth.permission_guard import (
            _current_roles,
            patch_mcp_auth_permissions,
            set_roles,
        )

        def fn():
            return "executou"

        fn.__name__ = "disparar_pipeline"
        server = self._make_server_with_tool("disparar_pipeline", fn, perm="project:run")
        patch_mcp_auth_permissions(server)

        fake_ctx = MagicMock(request=_FakeMcpRequest(None))
        tok = set_roles(["operator"])
        try:
            with (
                patch("concilium.infrastructure.auth.permission_guard._auth_enabled", return_value=True),
                self._patch_request_ctx(fake_ctx),
            ):
                result = server._tool_manager._tools["disparar_pipeline"].fn()
        finally:
            _current_roles.reset(tok)
        assert result == "executou"

    def test_stale_contextvar_roles_do_not_leak_into_a_different_message(self):
        """Regressão inversa: _current_roles com role INSUFICIENTE (simulando o
        snapshot congelado de outra sessão/chamada) não deve vazar autorização —
        os roles corretos da mensagem atual (via request_ctx) é que decidem."""
        from concilium.infrastructure.auth.permission_guard import (
            _current_roles,
            patch_mcp_auth_permissions,
            set_roles,
        )

        def fn():
            return "executou"

        fn.__name__ = "disparar_pipeline"
        server = self._make_server_with_tool("disparar_pipeline", fn, perm="project:run")
        patch_mcp_auth_permissions(server)

        fake_ctx = MagicMock(request=_FakeMcpRequest("Bearer real-jwt"))
        # contextvar deliberadamente com role AMPLO (admin) — se ele vazasse para
        # esta mensagem, a chamada passaria indevidamente. Só deve valer o que
        # vem do request_ctx (roles=["auditor"], sem project:run).
        tok = set_roles(["admin"])
        try:
            with (
                patch("concilium.infrastructure.auth.permission_guard._auth_enabled", return_value=True),
                self._patch_request_ctx(fake_ctx),
                patch(
                    "concilium.infrastructure.auth.token_service.decode_token",
                    return_value={"sub": "bruno", "roles": ["auditor"]},  # sem project:run
                ),
            ):
                with pytest.raises(PermissionError):
                    server._tool_manager._tools["disparar_pipeline"].fn()
        finally:
            _current_roles.reset(tok)

    def _make_server_with_tool(self, tool_name: str, tool_fn, perm: str):
        server = MagicMock()
        tool_fn._required_permission = perm  # ADR-117: tag posta por @permission
        tool = MagicMock()
        tool.fn = tool_fn
        server._tool_manager._tools = {tool_name: tool}
        return server


class TestCurrentUserTenantIdPreferPerMessageClaims:
    """get_current_user_id/get_current_tenant_id têm o mesmo bug de contextvar
    congelado (usados para audit log e ownership check) — mesma correção."""

    def test_user_id_prefers_message_claims_over_contextvar(self):
        from concilium.infrastructure.auth.permission_guard import get_current_user_id, set_auth_context

        tokens = set_auth_context("stale-user-from-frozen-session", "stale-tenant")
        try:
            fake_ctx = MagicMock(request=_FakeMcpRequest("Bearer real-jwt"))
            with (
                patch(
                    "mcp.server.lowlevel.server.request_ctx",
                    MagicMock(get=MagicMock(return_value=fake_ctx)),
                ),
                patch(
                    "concilium.infrastructure.auth.token_service.decode_token",
                    return_value={"sub": "bruno", "tid": "mendeslobo", "roles": ["operator"]},
                ),
            ):
                assert get_current_user_id() == "bruno"
        finally:
            from concilium.infrastructure.auth.permission_guard import reset_auth_context

            reset_auth_context(tokens)

    def test_tenant_id_prefers_message_claims_over_contextvar(self):
        from concilium.infrastructure.auth.permission_guard import get_current_tenant_id, set_auth_context

        tokens = set_auth_context("stale-user", "stale-tenant-from-frozen-session")
        try:
            fake_ctx = MagicMock(request=_FakeMcpRequest("Bearer real-jwt"))
            with (
                patch(
                    "mcp.server.lowlevel.server.request_ctx",
                    MagicMock(get=MagicMock(return_value=fake_ctx)),
                ),
                patch(
                    "concilium.infrastructure.auth.token_service.decode_token",
                    return_value={"sub": "bruno", "tid": "mendeslobo", "roles": ["operator"]},
                ),
            ):
                assert get_current_tenant_id() == "mendeslobo"
        finally:
            from concilium.infrastructure.auth.permission_guard import reset_auth_context

            reset_auth_context(tokens)

    def test_falls_back_to_contextvar_without_request_ctx(self):
        from concilium.infrastructure.auth.permission_guard import (
            get_current_tenant_id,
            get_current_user_id,
            reset_auth_context,
            set_auth_context,
        )

        tokens = set_auth_context("bruno", "mendeslobo")
        try:
            with patch(
                "mcp.server.lowlevel.server.request_ctx",
                MagicMock(get=MagicMock(return_value=None)),
            ):
                assert get_current_user_id() == "bruno"
                assert get_current_tenant_id() == "mendeslobo"
        finally:
            reset_auth_context(tokens)


class TestCurrentDeviceIdAndMcpSessionId:
    """ADR-138 (sessões por dispositivo): device_id (claim JWT do fluxo de
    refresh) e mcp_session_id (header de protocolo, não é claim) seguem o
    mesmo padrão per-message-primeiro dos demais getters de identidade."""

    def test_device_id_prefers_message_claims_over_contextvar(self):
        from concilium.infrastructure.auth.permission_guard import get_current_device_id, set_auth_context

        tokens = set_auth_context("bruno", "mendeslobo", device_id="stale-device-from-frozen-session")
        try:
            fake_ctx = MagicMock(request=_FakeMcpRequest("Bearer real-jwt"))
            with (
                patch(
                    "mcp.server.lowlevel.server.request_ctx",
                    MagicMock(get=MagicMock(return_value=fake_ctx)),
                ),
                patch(
                    "concilium.infrastructure.auth.token_service.decode_token",
                    return_value={"sub": "bruno", "roles": ["operator"], "device_id": "falcon-falcon"},
                ),
            ):
                assert get_current_device_id() == "falcon-falcon"
        finally:
            from concilium.infrastructure.auth.permission_guard import reset_auth_context

            reset_auth_context(tokens)

    def test_device_id_none_when_claim_absent(self):
        """Fluxos sem device (client_id/secret direto) não têm claim device_id."""
        from concilium.infrastructure.auth.permission_guard import get_current_device_id, set_auth_context

        tokens = set_auth_context("bruno", "mendeslobo")
        try:
            fake_ctx = MagicMock(request=_FakeMcpRequest("Bearer real-jwt"))
            with (
                patch(
                    "mcp.server.lowlevel.server.request_ctx",
                    MagicMock(get=MagicMock(return_value=fake_ctx)),
                ),
                patch(
                    "concilium.infrastructure.auth.token_service.decode_token",
                    return_value={"sub": "bruno", "roles": ["operator"]},
                ),
            ):
                assert get_current_device_id() is None
        finally:
            from concilium.infrastructure.auth.permission_guard import reset_auth_context

            reset_auth_context(tokens)

    def test_device_id_falls_back_to_contextvar_without_request_ctx(self):
        from concilium.infrastructure.auth.permission_guard import (
            get_current_device_id,
            reset_auth_context,
            set_auth_context,
        )

        tokens = set_auth_context("bruno", "mendeslobo", device_id="falcon-falcon")
        try:
            with patch(
                "mcp.server.lowlevel.server.request_ctx",
                MagicMock(get=MagicMock(return_value=None)),
            ):
                assert get_current_device_id() == "falcon-falcon"
        finally:
            reset_auth_context(tokens)

    def test_mcp_session_id_reads_header_from_request_ctx(self):
        """mcp_session_id não é claim JWT — vem do header mcp-session-id da
        própria mensagem (nunca de contextvar: não há staleness a proteger
        contra, e não há sentido em 'sessão anterior' como fallback)."""
        from concilium.infrastructure.auth.permission_guard import get_current_mcp_session_id

        fake_ctx = MagicMock(request=_FakeMcpRequest("Bearer real-jwt", mcp_session_id="sess-abc123"))
        with patch(
            "mcp.server.lowlevel.server.request_ctx",
            MagicMock(get=MagicMock(return_value=fake_ctx)),
        ):
            assert get_current_mcp_session_id() == "sess-abc123"

    def test_mcp_session_id_none_without_request_ctx(self):
        from concilium.infrastructure.auth.permission_guard import get_current_mcp_session_id

        with patch(
            "mcp.server.lowlevel.server.request_ctx",
            MagicMock(get=MagicMock(return_value=None)),
        ):
            assert get_current_mcp_session_id() is None


# ADR-120: 5 novas tools de ciclo de vida de catálogo (appended after original list close)
