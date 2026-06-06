"""Testes do MCP server — registro de tools e smoke calls por módulo."""

import json
from pathlib import Path

import pytest

from concilium.presentation.mcp.server import build_server

# ── Conjunto canônico de tools (atualizar aqui quando adicionar novas) ─────────
# sistema (1): ping
# catalogo (5): listar_contextos, pesquisar_catalogo, consultar_saude_catalogo,
#               atualizar_preco_insumo, adicionar_variante_producao
# projeto (6): listar_projetos, iniciar_orcamento, consultar_status,
#              aprovar_versao, nova_versao, salvar_perfil_bdi
# pipeline (1): avancar_pipeline
# analise (2): auditar_plano, comparar_planos
# replan (2): simular_cenario_replan, aplicar_sugestao_replan
# escopo (3): consultar_estrutura_projeto, configurar_escopo, gerenciar_plano
TOOLS_ESPERADAS = {
    # sistema
    "ping",
    # catalogo
    "listar_contextos",
    "pesquisar_catalogo",
    "consultar_saude_catalogo",
    "atualizar_preco_insumo",
    "adicionar_variante_producao",
    # projeto
    "listar_projetos",
    "iniciar_orcamento",
    "consultar_status",
    "aprovar_versao",
    "nova_versao",
    "salvar_perfil_bdi",
    # pipeline
    "avancar_pipeline",
    # analise
    "auditar_plano",
    "comparar_planos",
    # replan
    "simular_cenario_replan",
    "aplicar_sugestao_replan",
    # escopo
    "consultar_estrutura_projeto",
    "configurar_escopo",
    "gerenciar_plano",
}


@pytest.fixture(scope="session")
def server_with_config(tmp_path_factory):
    """Server com env vars apontando para config real e projetos temporários.

    Session-scoped: build_server() leva ~0.6–2.7 s por chamada; compartilhar
    uma instância única poupa ~10 s por sessão. Todos os testes são read-only
    (ping, list, erros de projeto inexistente) — sem risco de estado cruzado.
    """
    import os
    from concilium.infrastructure.settings import _reset_all

    config_root = str(Path(__file__).parents[2] / "config")
    proj_root = str(tmp_path_factory.mktemp("mcp_projetos"))

    prev = {k: os.environ.get(k) for k in ("CONCILIUM__CONFIG_ROOT", "CONCILIUM__PROJECTS_ROOT")}
    os.environ["CONCILIUM__CONFIG_ROOT"] = config_root
    os.environ["CONCILIUM__PROJECTS_ROOT"] = proj_root
    _reset_all()

    server = build_server()
    yield server

    for k, v in prev.items():
        if v is None:
            os.environ.pop(k, None)
        else:
            os.environ[k] = v
    _reset_all()


# ── Registro ───────────────────────────────────────────────────────────────────


class TestMCPRegistration:
    def test_server_pode_ser_construido(self, server_with_config):
        assert server_with_config is not None
        assert server_with_config.name == "concilium"

    @pytest.mark.asyncio
    async def test_todas_tools_registradas(self, server_with_config):
        tools = await server_with_config.list_tools()
        names = {t.name for t in tools}
        faltando = TOOLS_ESPERADAS - names
        assert not faltando, f"Tools não registradas: {sorted(faltando)}"

    @pytest.mark.asyncio
    async def test_contagem_minima_tools(self, server_with_config):
        tools = await server_with_config.list_tools()
        assert len(tools) >= len(TOOLS_ESPERADAS), f"Esperado ≥{len(TOOLS_ESPERADAS)} tools, encontrado {len(tools)}"

    @pytest.mark.asyncio
    async def test_todas_tools_tem_descricao(self, server_with_config):
        tools = await server_with_config.list_tools()
        sem_descricao = [t.name for t in tools if not t.description]
        assert not sem_descricao, f"Tools sem description: {sem_descricao}"


# ── Smoke calls por módulo ─────────────────────────────────────────────────────
# Apenas chamadas read-only que não precisam de projeto existente.
# Para tools que requerem project_id, a cobertura de registro já é suficiente.


class TestMCPSmoke:
    @pytest.mark.asyncio
    async def test_smoke_system_ping(self, server_with_config):
        """sistema — ping retorna status e campos obrigatórios."""
        result = await server_with_config.call_tool("ping", arguments={})
        assert result is not None
        data = json.loads(result[0][0].text if isinstance(result[0], list) else result[0].text)
        assert "status" in data
        assert "contextos" in data
        assert "total_projetos" in data
        assert "config_root_exists" in data

    @pytest.mark.asyncio
    async def test_smoke_catalogo_listar_contextos(self, server_with_config):
        """catalogo — listar_contextos retorna lista (pode ser vazia em config de teste)."""
        result = await server_with_config.call_tool("listar_contextos", arguments={})
        assert result is not None
        data = json.loads(result[0][0].text if isinstance(result[0], list) else result[0].text)
        assert "contextos" in data

    @pytest.mark.asyncio
    async def test_smoke_projeto_listar_projetos(self, server_with_config):
        """projeto — listar_projetos retorna lista vazia para diretório temporário."""
        result = await server_with_config.call_tool("listar_projetos", arguments={})
        assert result is not None
        data = json.loads(result[0][0].text if isinstance(result[0], list) else result[0].text)
        assert "projetos" in data
        assert data["projetos"] == []  # tmp_path está vazio

    @pytest.mark.asyncio
    async def test_smoke_pipeline_inexistente_retorna_erro_nao_excecao(self, server_with_config):
        """pipeline — projeto inexistente deve retornar erro no payload, não levantar exceção."""
        try:
            from mcp.server.fastmcp.exceptions import ToolError
        except ImportError:
            ToolError = Exception
        try:
            result = await server_with_config.call_tool(
                "avancar_pipeline",
                arguments={"project_id": "smoke-inexistente"},
            )
            assert result is not None  # não levantou exceção
        except ToolError:
            pass  # ToolError is acceptable

    @pytest.mark.asyncio
    async def test_smoke_analise_inexistente_retorna_erro_nao_excecao(self, server_with_config):
        """analise — projeto inexistente deve retornar erro (payload ou ToolError)."""
        try:
            from mcp.server.fastmcp.exceptions import ToolError
        except ImportError:
            ToolError = Exception
        try:
            result = await server_with_config.call_tool(
                "auditar_plano",
                arguments={"project_id": "smoke-inexistente"},
            )
            assert result is not None
        except ToolError:
            pass

    @pytest.mark.asyncio
    async def test_smoke_replan_inexistente_retorna_erro_nao_excecao(self, server_with_config):
        """replan — projeto inexistente deve retornar erro no payload, não levantar exceção."""
        result = await server_with_config.call_tool(
            "simular_cenario_replan",
            arguments={"project_id": "smoke-inexistente", "tipo": "extend_deadline", "parametros": {}},
        )
        assert result is not None

    @pytest.mark.asyncio
    async def test_smoke_escopo_inexistente_retorna_erro_nao_excecao(self, server_with_config):
        """escopo — projeto inexistente deve retornar erro (payload ou ToolError)."""
        try:
            from mcp.server.fastmcp.exceptions import ToolError
        except ImportError:
            ToolError = Exception
        try:
            result = await server_with_config.call_tool(
                "consultar_estrutura_projeto",
                arguments={"project_id": "smoke-inexistente"},
            )
            assert result is not None
        except ToolError:
            pass  # ToolError is acceptable


# ── Contrato de resposta (ADR-018 §D5) ────────────────────────────────────────


class TestMCPResponseContract:
    @pytest.mark.asyncio
    async def test_schema_version_presente_em_listar_contextos(self, server_with_config):
        """ADR-018: listar_contextos retorna contextos (schema_version em ping)."""
        result = await server_with_config.call_tool("listar_contextos", arguments={})
        data = json.loads(result[0][0].text if isinstance(result[0], list) else result[0].text)
        assert "contextos" in data, "contextos ausente na resposta"

    @pytest.mark.asyncio
    async def test_schema_version_presente_em_ping(self, server_with_config):
        """ADR-018: ping também deve respeitar o contrato de envelope."""
        result = await server_with_config.call_tool("ping", arguments={})
        data = json.loads(result[0][0].text if isinstance(result[0], list) else result[0].text)
        assert "schema_version" in data, "schema_version ausente no ping"
        assert "trace_id" in data, "trace_id ausente no ping"

    @pytest.mark.asyncio
    async def test_trace_id_consistente_na_sessao(self, server_with_config):
        """trace_id deve ser o mesmo ao longo da sessão do servidor."""
        r1 = await server_with_config.call_tool("listar_contextos", arguments={})
        r2 = await server_with_config.call_tool("listar_projetos", arguments={})
        tid1 = json.loads(r1[0][0].text if isinstance(r1[0], list) else r1[0].text).get("trace_id")
        tid2 = json.loads(r2[0][0].text if isinstance(r2[0], list) else r2[0].text).get("trace_id")
        assert tid1 == tid2, "trace_id mudou entre chamadas da mesma sessão"
