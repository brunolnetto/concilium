"""Ferramentas MCP do sistema — ping / health check (sem side effects)."""

from __future__ import annotations

import asyncio
from typing import Any

from mcp.server.fastmcp import FastMCP

from concilium.application.services.system_novelties import check_and_report_novidades
from concilium.infrastructure.auth.permission_guard import get_current_user_id, permission
from concilium.presentation.mcp._context import (
    TOOL_IO_TIMEOUT_S,
    _config_root,
    _projetos_root,
    _wrap_response,
)


def register(server: FastMCP) -> None:
    """Registra ferramentas de sistema no servidor MCP."""

    @server.tool()
    @permission("health:read")
    async def ping() -> dict[str, Any]:
        """Verifica a saúde do servidor MCP sem criar nem alterar dados.

        Retorna:
        - status geral (SAUDAVEL | DEGRADADO | ERRO)
        - caminhos de configuração e se existem
        - lista de contextos disponíveis
        - contagem de projetos existentes

        NÃO inclui saúde de catálogo (erros críticos, total de CPUs) — isso
        é responsabilidade de `auditar_catalogo(contexto_id, modo="saude")`,
        chamada por contexto (use a lista `contextos` retornada aqui). ping()
        é deliberadamente barato: um health check não deveria pagar o custo
        de carregar catálogos inteiros (achado de produção 2026-08-11 — essa
        varredura, não o storage em si, era a causa raiz dos hangs de ping()
        sob catálogos grandes/cache frio).

        Use como primeira chamada para calibrar o estado do sistema antes
        de qualquer operação de planejamento.
        """
        # issue #148/#149 + ADR-180: o corpo inteiro (health_check,
        # check_and_report_novidades) roda sob UM único deadline (TOOL_IO_TIMEOUT_S).
        # health_check() usa o caminho assíncrono nativo (cancelamento real) quando
        # o backend é SharePoint (ADR-180 D5); check_and_report_novidades
        # continua síncrono em thread (fora de escopo desta ADR — passa por
        # DeployLogStore, não diretamente pelo BlobStoragePort). load_catalogo NÃO
        # roda mais aqui — ver docstring de ping() (removido, causa raiz dos hangs).
        try:
            return await asyncio.wait_for(_ping_async(), timeout=TOOL_IO_TIMEOUT_S)
        except TimeoutError:
            return _wrap_response(
                {
                    "status": "ERRO",
                    "erro": (
                        f"ping excedeu {TOOL_IO_TIMEOUT_S:.0f}s aguardando storage. "
                        "Se o backend for SharePoint, a chamada foi cancelada de verdade "
                        "(sem thread presa); para o restante (novidades) uma thread de "
                        "I/O pode continuar rodando em segundo plano. Tente novamente; "
                        "se persistir, é sintoma de degradação de rede/Graph API, não "
                        "do servidor MCP em si."
                    ),
                }
            )

    async def _ping_async() -> dict[str, Any]:
        storage_health = await _storage_health_async()
        return await asyncio.to_thread(_ping_impl, storage_health)

    async def _storage_health_async() -> dict[str, Any]:
        """ADR-180 D5: health_check via AsyncSharePointBlobStorage quando disponível
        (cancelamento real); cai para o caminho síncrono via to_thread para os
        demais backends (ADR-180 D6, comportamento inalterado)."""
        from concilium.infrastructure.storage.store_factory import build_async_blob_storage, build_blob_storage

        try:
            async_storage = build_async_blob_storage()
        except NotImplementedError:
            async_storage = None

        if async_storage is not None:
            try:
                return await async_storage.health_check()
            except Exception as exc:
                return {"status": "error", "message": str(exc)}

        def _sync_health_check() -> dict[str, Any]:
            try:
                return build_blob_storage().health_check()
            except Exception as exc:
                return {"status": "error", "message": str(exc)}

        return await asyncio.to_thread(_sync_health_check)

    def _ping_impl(storage_health: dict[str, Any]) -> dict[str, Any]:
        config_dir = _config_root()
        proj_root = _projetos_root()

        # Contextos disponíveis
        contextos_dir = config_dir / "contextos"
        contexto_ids: list[str] = []
        if contextos_dir.exists():
            contexto_ids = [p.stem for p in sorted(contextos_dir.glob("*.json"))]

        # Contagem de projetos
        n_projetos = 0
        if proj_root.exists():
            n_projetos = sum(1 for p in proj_root.iterdir() if p.is_dir() and (p / "meta.json").exists())

        # Status geral — só storage/config. Saúde de catálogo (erros críticos,
        # total_cpus) NÃO entra aqui — é responsabilidade de auditar_catalogo
        # por contexto (ver docstring). Uma varredura de todos os catálogos a
        # cada ping() é o tipo de custo que um health check não deveria pagar.
        if not config_dir.exists() or storage_health.get("status") == "error":
            status_geral = "ERRO"
        elif storage_health.get("status") not in ("ok", "SAUDAVEL"):
            status_geral = "DEGRADADO"
        else:
            status_geral = "SAUDAVEL"

        result: dict[str, Any] = {
            "status": status_geral,
            "config_root": str(config_dir),
            "config_root_exists": config_dir.exists(),
            "projetos_root": str(proj_root),
            "projetos_root_exists": proj_root.exists(),
            "contextos": contexto_ids,
            "total_projetos": n_projetos,
            "storage": storage_health,
        }

        # ADR-144 D2: novidades de deploy/skill embutidas na resposta — sem
        # identidade resolvível não há cursor de client_id a comparar.
        client_id = get_current_user_id()
        if client_id is not None:
            novidades = check_and_report_novidades(client_id)
            if novidades is not None:
                result["novidades"] = novidades

        return _wrap_response(result)
