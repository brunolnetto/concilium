"""MCP Server do Concilium â€” orquestrador modular.

Usa FastMCP do SDK oficial mcp. ExpÃµe operaÃ§Ãµes de negÃ³cio que o Claude Desktop
pode invocar via configuraÃ§Ã£o de MCP server stdio.

ConfiguraÃ§Ã£o no Claude Desktop (claude_desktop_config.json):

    {
      "mcpServers": {
        "concilium": {
          "command": "python",
          "args": ["-m", "concilium.presentation.mcp_server"],
          "env": {
            "CONCILIUM__CONFIG_ROOT": "/path/to/config",
            "CONCILIUM__PROJECTS_ROOT": "/path/to/projetos"
          }
        }
      }
    }

PrincÃ­pio de design:
    - OperaÃ§Ãµes expostas sÃ£o de NEGÃ“CIO (iniciar orÃ§amento, avanÃ§ar pipeline),
      nÃ£o de IMPLEMENTAÃ‡ÃƒO (skill 02, skill 03, etc.).
    - OperaÃ§Ãµes irreversÃ­veis (aprovar) requerem confirmaÃ§Ã£o humana antes
      de serem invocadas â€” Claude Desktop deve apresentar para o usuÃ¡rio.
    - Erros de prÃ©-condiÃ§Ã£o (ex.: skill anterior nÃ£o rodou) retornam mensagem
      legÃ­vel pelo Claude para que ele possa pedir o input necessÃ¡rio ao usuÃ¡rio.

Estrutura de mÃ³dulos:
    tools/catalogo.py  â€” listar_contextos, sugerir_eap, listar_cpus, buscar_cpu,
                         derivar_recursos_do_catalogo
    tools/projeto.py   â€” listar_projetos, iniciar_orcamento, consultar_status,
                         aprovar_versao
    tools/pipeline.py  â€” avancar_pipeline
    tools/analise.py   â€” consultar_viabilidade_prazo, identificar_gargalos_recurso,
                         consultar_alternativas_replan
    tools/replan.py    â€” simular_impacto_replan, aplicar_sugestao_replan,
                         simular_impacto_indiretos
    tools/cenarios.py  â€” explorar_alternativas
"""

from __future__ import annotations

from mcp.server.fastmcp import FastMCP

from concilium.infrastructure.telemetry import patch_fastmcp_server, setup_telemetry
from concilium.presentation.mcp_server._context import _config_root
from concilium.presentation.mcp_server.middleware import McpAuthMiddleware
from concilium.presentation.mcp_server.tools import (
    analise,
    artifacts,
    benchmark,
    catalogo,
    escopo,
    formulario,
    pipeline,
    projeto,
    replan,
    system,
)


def build_server(host: str = "127.0.0.1", port: int = 8000) -> FastMCP:
    """Monta o servidor MCP registrando todas as ferramentas dos sub-módulos."""
    setup_telemetry()
    server = FastMCP("concilium", host=host, port=port)
    system.register(server)  # ping / health — sempre primeiro
    catalogo.register(server)
    projeto.register(server)
    pipeline.register(server)
    formulario.register(server)  # ADR-092: criar_projeto_formulario
    analise.register(server)
    replan.register(server)
    escopo.register(server)  # ADR-031
    benchmark.register(server)  # execução, empacotamento e download de benchmark
    artifacts.register(server)  # ADR-093: listar/ler/baixar/bundle de artefatos
    patch_fastmcp_server(server)  # ADR-095: OTEL tracing em todas as tools
    _patch_mcp_with_auth(server)  # ADR-099: JWT middleware para transport HTTP
    return server


def _patch_mcp_with_auth(server: FastMCP) -> None:
    """Envolve os apps ASGI do FastMCP (HTTP + SSE) com McpAuthMiddleware.

    No-op se AUTH_ENABLED=0 (stdio/dev) — o middleware trata isso internamente,
    mas embrulhar os apps não faz mal em nenhum modo.
    """
    _original_http = server.streamable_http_app
    _original_sse = server.sse_app

    def _http_with_auth(*args, **kwargs):
        return McpAuthMiddleware(_original_http(*args, **kwargs))

    def _sse_with_auth(*args, **kwargs):
        return McpAuthMiddleware(_original_sse(*args, **kwargs))

    server.streamable_http_app = _http_with_auth  # type: ignore[method-assign]
    server.sse_app = _sse_with_auth               # type: ignore[method-assign]


def main() -> None:
    """Entry point para `python -m concilium.mcp_server`.

    Variáveis de ambiente:
      CONCILIUM__MCP_TRANSPORT  — "stdio" (padrão), "streamable-http" ou "sse"
      CONCILIUM__MCP_HOST       — bind host para transporte HTTP (padrão: 0.0.0.0)
      CONCILIUM__MCP_PORT       — porta para transporte HTTP (padrão: 8080)
    """
    import sys
    from datetime import datetime

    config_root = _config_root()
    if not config_root.exists():
        raise RuntimeError(
            "Diretório de configuração não encontrado: "
            f"{config_root}. Defina CONCILIUM__CONFIG_ROOT ou CONCILIUM__CONFIG."
        )
    if not config_root.is_dir():
        raise RuntimeError(f"Configuração inválida: {config_root} não é diretório.")

    from concilium.infrastructure.settings import get_mcp, startup_check
    startup_check()
    mcp = get_mcp()
    transport = mcp.transport
    if transport != "stdio":
        mcp_host, mcp_port = mcp.host, mcp.port
    else:
        mcp_host, mcp_port = "127.0.0.1", 8000

    server = build_server(host=mcp_host, port=mcp_port)

    try:
        n_tools = len(server._tool_manager._tools)
    except Exception:
        n_tools = "?"  # type: ignore[assignment]
    ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    addr = f"{mcp_host}:{mcp_port}" if transport != "stdio" else "stdio"
    banner = (
        "\n"
        "╔══════════════════════════════════════════════════╗\n"
        "║          CONCILIUM  MCP SERVER  — ONLINE         ║\n"
        "╠══════════════════════════════════════════════════╣\n"
        f"║  Transport  : {transport:<35} ║\n"
        f"║  Endereço   : {addr:<35} ║\n"
        f"║  Ferramentas: {n_tools:<35} ║\n"
        f"║  Config     : {str(config_root)[-35:]:<35} ║\n"
        f"║  Iniciado   : {ts:<35} ║\n"
        "╚══════════════════════════════════════════════════╝\n"
    )
    print(banner, file=sys.stderr, flush=True)

    server.run(transport=transport)  # type: ignore[arg-type]


if __name__ == "__main__":
    main()
