"""MCP Server do Concilium â€” orquestrador modular.

Usa FastMCP do SDK oficial mcp. ExpÃµe operaÃ§Ãµes de negÃ³cio que o Claude Desktop
pode invocar via configuraÃ§Ã£o de MCP server stdio.

ConfiguraÃ§Ã£o no Claude Desktop (claude_desktop_config.json):

    {
      "mcpServers": {
        "concilium": {
          "command": "python",
          "args": ["-m", "concilium.presentation.mcp"],
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

from pathlib import Path
from typing import TYPE_CHECKING

from mcp.server.fastmcp import FastMCP

if TYPE_CHECKING:
    from starlette.applications import Starlette

from concilium.application.tool_invocations.repository import reset_tool_invocation_repository
from concilium.infrastructure.auth.permission_guard import patch_mcp_auth_permissions, validate_tool_coverage
from concilium.infrastructure.observability.logging_config import configure_logging
from concilium.infrastructure.storage.store_factory import get_tool_invocation_store
from concilium.infrastructure.telemetry import patch_fastmcp_server, setup_telemetry
from concilium.presentation.mcp._context import _config_root
from concilium.presentation.mcp.audit import patch_fastmcp_server_with_audit
from concilium.presentation.mcp.middleware import McpAuthMiddleware
from concilium.presentation.mcp.tools import (
    analise,
    artifacts,
    auth_self,
    benchmark,
    benchmark_nep039,
    campaign,
    catalogo,
    escopo,
    formulario,
    pipeline,
    projeto,
    replan,
    spec,
    system,
    tributacao,
)

_APPS_DIR = Path(__file__).parent / "apps"


class _AuthenticatedFastMCP(FastMCP):
    """FastMCP cujos apps ASGI HTTP/SSE são envolvidos por McpAuthMiddleware (ADR-099).

    Sobrescreve os métodos em vez de fazer monkey-patch dos atributos de
    instância `streamable_http_app`/`sse_app` (o que conflitava com a
    assinatura de método herdada e gerava `invalid-assignment` no ty).

    O tipo de retorno declarado permanece `Starlette` — é o tipo público da
    classe-base — mas em runtime devolvemos `McpAuthMiddleware`, um wrapper
    ASGI compatível (implementa `__call__(scope, receive, send)`) que não é
    uma subclasse de `Starlette`. Não há alternativa tipada limpa para expor
    isso sem alterar a assinatura pública do FastMCP upstream, daí o
    `ty: ignore` documentado abaixo.
    """

    def streamable_http_app(self) -> Starlette:
        return McpAuthMiddleware(super().streamable_http_app())  # ty: ignore[invalid-return-type]

    def sse_app(self, mount_path: str | None = None) -> Starlette:
        return McpAuthMiddleware(super().sse_app(mount_path))  # ty: ignore[invalid-return-type]


def build_server(host: str = "127.0.0.1", port: int = 8000) -> FastMCP:
    """Monta o servidor MCP registrando todas as ferramentas dos sub-módulos."""
    setup_telemetry()
    configure_logging(json_format=True)
    reset_tool_invocation_repository(get_tool_invocation_store())  # ADR-118: blob-backed audit
    server = _AuthenticatedFastMCP("concilium", host=host, port=port)
    system.register(server)  # ping / health — sempre primeiro
    auth_self.register(server)  # ADR-123 F5: self-service de dispositivos
    catalogo.register(server)
    projeto.register(server)
    pipeline.register(server)
    formulario.register(server)  # ADR-092: criar_projeto_formulario
    spec.register(server)  # ProjetoSpec unificado
    analise.register(server)
    replan.register(server)
    escopo.register(server)  # ADR-031
    benchmark.register(server)  # execução, empacotamento e download de benchmark

    # NEP-039: Register benchmark metadata tools
    benchmark_nep039.register(server)

    artifacts.register(server)  # ADR-093: listar/ler/baixar/bundle de artefatos
    tributacao.register(server)  # ADR-097 F6: INSS, IRRF, custo empregador CLT
    campaign.register(server)  # ADR-070: exploração do espaço GO (sweep paramétrico)
    _register_ui_resources(server)  # ADR-101: MCP Apps — recursos ui://
    patch_fastmcp_server(server)  # ADR-095: OTEL tracing em todas as tools
    patch_mcp_auth_permissions(server)  # ADR-099: RBAC enforcement via TOOL_PERMISSIONS
    patch_fastmcp_server_with_audit(server)  # ADR-118: audit log de invocações
    validate_tool_coverage(server)  # Loga warnings para tools sem mapeamento
    return server


def _register_ui_resources(server: FastMCP) -> None:
    """Registra recursos ui:// para MCP Apps (ADR-101).

    Cada recurso serve o HTML/JS do app correspondente. Os tools que suportam
    MCP Apps declaram _meta.ui.resourceUri apontando para esses URIs.
    """
    _apps = {
        "ui://concilium/formulario-qqp": "formulario-qqp/index.html",
        "ui://concilium/dashboard-resultado": "dashboard-resultado/index.html",
        "ui://concilium/diagnostico-pe": "diagnostico-pe/index.html",
        "ui://concilium/artefatos": "artefatos/index.html",
    }

    for uri, rel_path in _apps.items():
        html_path = _APPS_DIR / rel_path
        if not html_path.exists():
            continue

        html_content = html_path.read_text(encoding="utf-8")

        # Cria closure para capturar html_content por valor
        def _make_handler(content: str, resource_uri: str):
            @server.resource(resource_uri, mime_type="text/html")
            def _handler() -> str:  # type: ignore[no-untyped-def]
                return content

            return _handler

        _make_handler(html_content, uri)


def main() -> None:
    """Entry point para `python -m concilium.presentation.mcp`.

    Variáveis de ambiente:
      CONCILIUM__MCP_TRANSPORT  — "stdio" (padrão), "streamable-http" ou "sse"
      CONCILIUM__MCP_HOST       — bind host para transporte HTTP (padrão: 0.0.0.0)
      CONCILIUM__MCP_PORT       — porta para transporte HTTP (padrão: 8080)
    """
    import sys
    from datetime import datetime
    from typing import Literal

    config_root = _config_root()
    if not config_root.exists():
        raise RuntimeError(f"Diretório de configuração não encontrado: {config_root}. Defina CONCILIUM__CONFIG_ROOT.")
    if not config_root.is_dir():
        raise RuntimeError(f"Configuração inválida: {config_root} não é diretório.")

    from concilium.infrastructure.settings import get_mcp, startup_check
    from concilium.infrastructure.storage.store_factory import ensure_storage_root

    startup_check()
    ensure_storage_root()
    mcp = get_mcp()
    transport_raw = mcp.transport
    transport: Literal["stdio", "sse", "streamable-http"]
    if transport_raw == "stdio":
        transport = "stdio"
    elif transport_raw == "sse":
        transport = "sse"
    elif transport_raw == "streamable-http":
        transport = "streamable-http"
    else:
        raise RuntimeError(
            f"CONCILIUM__MCP_TRANSPORT inválido: '{transport_raw}'. Valores válidos: stdio, sse, streamable-http."
        )
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

    server.run(transport=transport)


if __name__ == "__main__":
    main()
