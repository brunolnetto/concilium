"""Ferramentas MCP do sistema — ping / health check (sem side effects)."""

from __future__ import annotations

from typing import Any

from mcp.server.fastmcp import FastMCP

from concilium.presentation.mcp_server._context import (
    _config_root,
    _projetos_root,
    _runtime,
    _wrap_response,
)


def register(server: FastMCP) -> None:
    """Registra ferramentas de sistema no servidor MCP."""

    @server.tool()
    def ping() -> dict[str, Any]:
        """Verifica a saúde do servidor MCP sem criar nem alterar dados.

        Retorna:
        - status geral (SAUDAVEL | DEGRADADO | ERRO)
        - caminhos de configuração e se existem
        - lista de contextos disponíveis
        - contagem de projetos existentes
        - saúde resumida de cada catálogo (erros críticos, total de CPUs)

        Use como primeira chamada para calibrar o estado do sistema antes
        de qualquer operação de planejamento.
        """
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

        # Saúde por catálogo (read-only)
        catalogos: list[dict[str, Any]] = []
        if contexto_ids and config_dir.exists():
            from concilium.application.orchestrators.catalog_governance import (
                collect_catalog_critical_errors,
            )

            rt = _runtime()
            for ctx_id in contexto_ids:
                try:
                    ctx = rt.load_contexto(ctx_id)
                    catalogo = rt.load_catalogo(ctx.catalogo_id)
                    erros = collect_catalog_critical_errors(catalogo)
                    catalogos.append(
                        {
                            "contexto_id": ctx_id,
                            "catalogo_id": ctx.catalogo_id,
                            "status": "SAUDAVEL" if not erros else "DEGRADADO",
                            "erros_criticos": len(erros),
                            "total_cpus": len(catalogo.get("cpus", [])),
                        }
                    )
                except Exception as exc:
                    catalogos.append(
                        {
                            "contexto_id": ctx_id,
                            "status": "ERRO",
                            "erro": str(exc),
                        }
                    )

        # Status geral
        if not config_dir.exists():
            status_geral = "ERRO"
        elif any(c.get("status") != "SAUDAVEL" for c in catalogos):
            status_geral = "DEGRADADO"
        else:
            status_geral = "SAUDAVEL"

        return _wrap_response(
            {
                "status": status_geral,
                "config_root": str(config_dir),
                "config_root_exists": config_dir.exists(),
                "projetos_root": str(proj_root),
                "projetos_root_exists": proj_root.exists(),
                "contextos": contexto_ids,
                "total_projetos": n_projetos,
                "catalogos": catalogos,
            }
        )
