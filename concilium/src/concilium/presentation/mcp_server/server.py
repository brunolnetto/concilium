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
            "CONCILIUM_CONFIG_ROOT": "/path/to/config",
            "CONCILIUM_PROJECTS_ROOT": "/path/to/projetos"
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

from concilium.presentation.mcp_server._context import _config_root
from concilium.presentation.mcp_server.tools import (
    analise,
    benchmark,
    catalogo,
    escopo,
    pipeline,
    projeto,
    replan,
    system,
)


def build_server() -> FastMCP:
    """Monta o servidor MCP registrando todas as ferramentas dos sub-módulos."""
    server = FastMCP("concilium")
    system.register(server)  # ping / health — sempre primeiro
    catalogo.register(server)
    projeto.register(server)
    pipeline.register(server)
    analise.register(server)
    replan.register(server)
    escopo.register(server)  # ADR-031
    benchmark.register(server)  # execução, empacotamento e download de benchmark
    return server


def main() -> None:
    """Entry point para `python -m concilium.mcp_server`."""
    import sys
    from datetime import datetime

    config_root = _config_root()
    if not config_root.exists():
        raise RuntimeError(
            "Diretório de configuração não encontrado: "
            f"{config_root}. Defina CONCILIUM_CONFIG_ROOT ou CONCILIUM_CONFIG."
        )
    if not config_root.is_dir():
        raise RuntimeError(f"Configuração inválida: {config_root} não é diretório.")

    server = build_server()

    try:
        n_tools = len(server._tool_manager._tools)
    except Exception:
        n_tools = "?"  # type: ignore[assignment]
    ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    banner = (
        "\n"
        "╔══════════════════════════════════════════════════╗\n"
        "║          CONCILIUM  MCP SERVER  — ONLINE         ║\n"
        "╠══════════════════════════════════════════════════╣\n"
        f"║  Transport  : stdio                              ║\n"
        f"║  Ferramentas: {n_tools:<35} ║\n"
        f"║  Config     : {str(config_root)[-35:]:<35} ║\n"
        f"║  Iniciado   : {ts:<35} ║\n"
        "╚══════════════════════════════════════════════════╝\n"
    )
    print(banner, file=sys.stderr, flush=True)

    server.run()


if __name__ == "__main__":
    main()
