"""MCP Server do Concilium — orquestrador modular.

Usa FastMCP do SDK oficial mcp. Expõe operações de negócio que o Claude Desktop
pode invocar via configuração de MCP server stdio.

Configuração no Claude Desktop (claude_desktop_config.json):

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

Princípio de design:
    - Operações expostas são de NEGÓCIO (iniciar orçamento, avançar pipeline),
      não de IMPLEMENTAÇÃO (skill 02, skill 03, etc.).
    - Operações irreversíveis (aprovar) requerem confirmação humana antes
      de serem invocadas — Claude Desktop deve apresentar para o usuário.
    - Erros de pré-condição (ex.: skill anterior não rodou) retornam mensagem
      legível pelo Claude para que ele possa pedir o input necessário ao usuário.

Estrutura de módulos:
    tools/catalogo.py  — listar_contextos, sugerir_eap, listar_cpus, buscar_cpu,
                         derivar_recursos_do_catalogo
    tools/projeto.py   — listar_projetos, iniciar_orcamento, consultar_status,
                         aprovar_versao
    tools/pipeline.py  — avancar_pipeline
    tools/analise.py   — consultar_viabilidade_prazo, identificar_gargalos_recurso,
                         consultar_alternativas_replan
    tools/replan.py    — simular_cenario_replan (ADR-101 F4: tipo='lever_adjust',
                         consumido pelos sliders do app ui://concilium/diagnostico-pe)
    tools/cenarios.py  — explorar_alternativas
"""

from __future__ import annotations

import logging
import os
import threading
from pathlib import Path
from typing import TYPE_CHECKING

from mcp.server.fastmcp import FastMCP

if TYPE_CHECKING:
    from starlette.applications import Starlette

from concilium.application.tool_invocations.repository import reset_tool_invocation_repository
from concilium.infrastructure.auth.permission_guard import patch_mcp_auth_permissions, validate_tool_coverage
from concilium.infrastructure.observability.logging_config import configure_logging
from concilium.infrastructure.observability.pipeline import bronze_storage_for_bootstrap
from concilium.infrastructure.storage.store_factory import get_tool_invocation_store
from concilium.infrastructure.telemetry import patch_fastmcp_server, setup_telemetry
from concilium.presentation.mcp._context import _config_root, _runtime
from concilium.presentation.mcp.audit import patch_fastmcp_server_with_audit
from concilium.presentation.mcp.middleware import McpAuthMiddleware
from concilium.presentation.mcp.tools import (
    analise,
    artifacts,
    auth_directory,
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
    bronze_storage = bronze_storage_for_bootstrap()
    setup_telemetry(bronze_storage=bronze_storage)
    configure_logging(json_format=True, bronze_storage=bronze_storage)
    reset_tool_invocation_repository(get_tool_invocation_store())  # ADR-118: blob-backed audit
    server = _AuthenticatedFastMCP("concilium", host=host, port=port)
    system.register(server)  # ping / health — sempre primeiro
    auth_self.register(server)  # ADR-123 F5: self-service de dispositivos
    auth_directory.register(server)  # ADR-143: visibilidade de usuários entre roles
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


# 2026-08-11: desabilitado por padrão — ver comentário no ponto de disparo em
# main(). Defina CONCILIUM__CATALOG_WARMUP_STARTUP=1 para reabilitar.
_CATALOG_WARMUP_ENABLED = os.environ.get("CONCILIUM__CATALOG_WARMUP_STARTUP", "0") == "1"


def _warm_up_catalogos_background() -> None:
    """Pré-carrega catálogos com backend remoto (SharePoint/S3/...) numa thread
    separada, em paralelo ao startup do servidor (issue #153 follow-up).

    `load_catalogo_via_storage` (`_catalog_storage.py`) tem cache local (TTL 1h,
    `.catalog_bundle_remote.json`) — aquecer aqui faz a primeira request REAL do
    usuário, que senão pagaria o cold-load inteiro (~800 round-trips ao Graph
    pro catálogo "mendeslobo", ver incidente 2026-08-11), já encontrar o cache
    pronto. Backend "filesystem" não sofre desse problema (leitura local já é
    rápida) — pula sem nem importar o Runtime.

    Roda numa thread daemon disparada em `main()` ANTES de `server.run()`: o
    processo já está de pé, mas ainda não aceita conexões — por isso não some
    junto com o event loop nem atrasa o startup/health check. Best-effort: uma
    falha aqui (Graph fora, credencial inválida, contexto malformado) só loga
    — nunca derruba o servidor, que continua respondendo mesmo com o catálogo
    ainda frio (só mais lento na primeira request real, exatamente como antes
    desta mudança).
    """
    logger = logging.getLogger(__name__)
    try:
        from concilium.application.runtime.mixins._catalog_storage import catalog_storage_backend

        if catalog_storage_backend() == "filesystem":
            return

        contextos_dir = _config_root() / "contextos"
        if not contextos_dir.exists():
            return

        rt = _runtime()
        catalogo_ids: list[str] = []
        seen: set[str] = set()
        for p in sorted(contextos_dir.glob("*.json")):
            try:
                ctx = rt.load_contexto(p.stem)
            except Exception:
                continue
            if ctx.catalogo_id not in seen:
                seen.add(ctx.catalogo_id)
                catalogo_ids.append(ctx.catalogo_id)

        for catalogo_id in catalogo_ids:
            try:
                logger.info("Warm-up: pré-carregando catálogo '%s' (backend remoto)...", catalogo_id)
                rt.load_catalogo(catalogo_id)
                logger.info("Warm-up: catálogo '%s' pronto.", catalogo_id)
            except Exception:
                logger.warning(
                    "Warm-up: falha ao pré-carregar catálogo '%s' (best-effort, seguindo).",
                    catalogo_id,
                    exc_info=True,
                )
    except Exception:
        logger.warning("Warm-up de catálogo falhou de forma inesperada (best-effort).", exc_info=True)


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

    if transport != "stdio" and _CATALOG_WARMUP_ENABLED:
        # Container de vida longa (streamable-http/sse) — vale a pena aquecer o
        # cache de catálogo em paralelo ao startup (ver _warm_up_catalogos_background).
        # stdio (uso local via Claude Desktop) tipicamente roda backend "filesystem"
        # (já rápido) e é um processo de vida curta; a função já é um no-op nesse
        # caso, mas o gate aqui deixa a intenção explícita.
        #
        # 2026-08-11 DESABILITADO por padrão (CONCILIUM__CATALOG_WARMUP_STARTUP=0):
        # no primeiro deploy com este warm-up ativo, os smoke tests de
        # concilium-api falharam (GET /api/projects/ e X-RateLimit-Limit) —
        # logs do container mostraram SharePoint devolvendo 429 repetido
        # (Graph API throttling por app/tenant) durante o restart simultâneo
        # de concilium-mcp (fazendo o warm-up) e concilium-api (fazendo seu
        # próprio cold-load de catálogo na primeira request). Rollback
        # automático manteve produção estável. O warm-up em si (cache local,
        # sem custo pro usuário) não é o problema — é a falta de stagger/
        # backoff entre os dois processos competindo pelo mesmo throttle do
        # Graph logo no restart. Reabilitar requer coordenar isso (ex.: delay
        # aleatório antes do warm-up, ou um lock distribuído entre os apps).
        threading.Thread(target=_warm_up_catalogos_background, name="catalog-warmup", daemon=True).start()

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
