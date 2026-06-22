"""Ferramentas MCP de Catálogo — Simplificadas (ADR-037)."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from mcp.server.fastmcp import FastMCP

from ._catalogo_tools_helpers_a import (
    _impl_adicionar_variante_producao,
    _impl_atualizar_preco_insumo,
    _impl_consultar_preco_insumo_temporal,
    _impl_consultar_saude_catalogo,
    _impl_listar_contextos,
    _impl_pesquisar_catalogo,
)
from ._catalogo_tools_helpers_b import (
    _impl_avaliar_plausibilidade_catalogo,
    _impl_calcular_pu_producao,
    _impl_comparar_rfi_catalogo,
    _impl_tendencia_precos_catalogo,
    _impl_verificar_integridade_catalogo,
)


def _catalog_root(config_dir: Path, catalogo_id: str) -> Path:
    return config_dir / "catalogos" / catalogo_id


from concilium.infrastructure.auth.permission_guard import permission

def register(server: FastMCP) -> None:
    """Registra as ferramentas consolidadas de catálogo."""

    # ── Lookup / pesquisa ────────────────────────────────────────────────────

    @server.tool(
        description="Lista os contextos de catálogo disponíveis (ex: mendeslobo, test). Ponto de entrada para descobrir contexto_id."
    )
    @permission("catalog:read")
    def listar_contextos() -> dict[str, Any]:
        return _impl_listar_contextos()

    @server.tool(
        description="Busca CPUs por código ou descrição (ex: query='escavação 1ª cat'). Use para encontrar cpu_id antes de criar projeto."
    )
    @permission("catalog:read")
    def pesquisar_catalogo(
        contexto_id: str,
        query: str | None = None,
        tipo_obra: str | None = None,
        limite: int = 20,
    ) -> dict[str, Any]:
        return _impl_pesquisar_catalogo(contexto_id, query, tipo_obra, limite)

    # ── Diagnóstico — use um de cada vez ────────────────────────────────────
    # consultar_saude_catalogo  → cobertura (quantos insumos têm preço, % CPUs calculáveis)
    # avaliar_plausibilidade_catalogo → valores fora de faixa (outliers, razões anômalas)
    # verificar_integridade_catalogo  → consistência referencial (insumos pendentes, ciclos, PUs)

    @server.tool(
        description=(
            "Auditoria do catálogo em três modos: "
            "'saude' — cobertura (% insumos com preço, % CPUs calculáveis); "
            "'plausibilidade' — outliers de preço e razões de produtividade anômalas; "
            "'integridade' — consistência referencial, ciclos e recálculo de PUs."
        )
    )
    @permission("catalog:read")
    def auditar_catalogo(
        contexto_id: str,
        modo: str = "saude",
        alpha_clt: float = 1.777,
        alpha_pj: float = 1.06,
        preco_diesel: float = 6.50,
    ) -> dict[str, Any]:
        """Audita o catálogo de referência.

        modos disponíveis:
        - saude: cobertura — % insumos com preço, % CPUs calculáveis. Use antes de orçar.
        - plausibilidade: detecta outliers e razões de produtividade anômalas.
        - integridade: verifica insumos ausentes, ciclos e recalcula PUs com encargos/diesel.

        Args:
            contexto_id: ID do contexto do catálogo a auditar.
            modo: "saude" | "plausibilidade" | "integridade" (padrão: "saude").
            alpha_clt: Multiplicador CLT — só usado no modo "integridade".
            alpha_pj: Multiplicador PJ — só usado no modo "integridade".
            preco_diesel: Preço do diesel (R$/L) — só usado no modo "integridade".
        """
        if modo == "saude":
            return _impl_consultar_saude_catalogo(contexto_id)
        elif modo == "plausibilidade":
            return _impl_avaliar_plausibilidade_catalogo(contexto_id)
        elif modo == "integridade":
            return _impl_verificar_integridade_catalogo(contexto_id, alpha_clt, alpha_pj, preco_diesel)
        else:
            from concilium.presentation.mcp._context import _wrap_response
            return _wrap_response({"erro": f"modo '{modo}' inválido. Use: saude | plausibilidade | integridade"})

    # ── Mutação / atualização ────────────────────────────────────────────────

    @server.tool(
        description="Atualiza o preço de um insumo (ex: novo preço de diesel após cotação). Use projeto_id para override de projeto em vez de alterar o master."
    )
    @permission("catalog:write")
    def atualizar_preco_insumo(
        contexto_id: str,
        insumo_id: str,
        novo_preco: float,
        projeto_id: str | None = None,
        jurisdicao_id: str | None = None,
        nota: str | None = None,
    ) -> dict[str, Any]:
        return _impl_atualizar_preco_insumo(contexto_id, insumo_id, novo_preco, projeto_id, jurisdicao_id, nota)

    @server.tool(
        description="Adiciona uma variante de produtividade a uma producao existente (ex: equipe alternativa com custo/hora diferente)."
    )
    @permission("catalog:write")
    def adicionar_variante_producao(
        contexto_id: str,
        producao_id: str,
        variante_id: str,
        nome_variante: str,
        valor_horario: float,
        equipe_json: str,
        projeto_id: str | None = None,
    ) -> dict[str, Any]:
        return _impl_adicionar_variante_producao(
            contexto_id, producao_id, variante_id, nome_variante, valor_horario, equipe_json, projeto_id
        )

    # ── Análise temporal / RFI ───────────────────────────────────────────────

    @server.tool(
        description=(
            "Consulta histórico de preços do catálogo em dois modos: "
            "'pontual' — preço de um insumo específico em uma data (para verificar preço vigente na época do contrato); "
            "'tendencia' — evolução histórica de todos os insumos (para detectar inflação/deflação sistêmica)."
        )
    )
    @permission("catalog:read")
    def historico_preco_insumo(
        contexto_id: str,
        modo: str = "tendencia",
        insumo_id: str | None = None,
        data_referencia: str | None = None,
        projeto_id: str | None = None,
        jurisdicao_id: str | None = None,
    ) -> dict[str, Any]:
        """Histórico temporal de preços do catálogo.

        modos disponíveis:
        - pontual: preço de um insumo em data específica. Requer insumo_id e data_referencia.
        - tendencia: evolução de todos os insumos. Parâmetros insumo_id e data_referencia ignorados.
        """
        if modo == "pontual":
            if not insumo_id or not data_referencia:
                from concilium.presentation.mcp._context import _wrap_response
                return _wrap_response({"erro": "modo='pontual' requer insumo_id e data_referencia"})
            return _impl_consultar_preco_insumo_temporal(contexto_id, insumo_id, data_referencia, projeto_id, jurisdicao_id)
        elif modo == "tendencia":
            return _impl_tendencia_precos_catalogo(contexto_id, jurisdicao_id)
        else:
            from concilium.presentation.mcp._context import _wrap_response
            return _wrap_response({"erro": f"modo '{modo}' inválido. Use: pontual | tendencia"})

    @server.tool(
        description="Compara dados de RFI (Request for Information) com o catálogo master e lista divergências. dry_run=True (padrão) apenas mostra — use dry_run=False para aplicar as diferenças."
    )
    @permission("financials:read")
    def comparar_rfi_catalogo(
        contexto_id: str,
        dry_run: bool = True,
    ) -> dict[str, Any]:
        return _impl_comparar_rfi_catalogo(contexto_id, dry_run)

    @server.tool(
        description="Recalcula o preço unitário de uma produção específica dado alpha_clt, alpha_pj e preço do diesel. Use para simular impacto de mudança de encargos ou combustível em uma CPU."
    )
    @permission("catalog:read")
    def calcular_pu_producao(
        contexto_id: str,
        producao_id: str,
        alpha_clt: float = 1.777,
        alpha_pj: float = 1.06,
        preco_diesel: float = 6.50,
        horas_mes: float = 208.0,
    ) -> dict[str, Any]:
        return _impl_calcular_pu_producao(contexto_id, producao_id, alpha_clt, alpha_pj, preco_diesel, horas_mes)

    # ── Versionamento de contexto (ADR-062) ─────────────────────────────────

    @server.tool(
        description=(
            "Gerencia versões de um contexto de catálogo (ADR-062) em dois modos: "
            "'listar' — histórico de versões com datas e autores; "
            "'comparar' — diff lado a lado entre versao_a e versao_b (requer ambas)."
        )
    )
    @permission("catalog:read")
    def versoes_catalogo(
        contexto_id: str,
        modo: str = "listar",
        versao_a: str | None = None,
        versao_b: str | None = None,
    ) -> dict[str, Any]:
        """Gerencia versões do catálogo (ADR-062).

        modos disponíveis:
        - listar: histórico de versões — versão atual, datas, autores.
        - comparar: diff entre versao_a e versao_b. Requer ambos os parâmetros.
        """
        from concilium.application.services.catalog.contexto_version_service import ContextoVersionService
        from concilium.infrastructure.settings import get_storage

        config_root = get_storage().config_root
        svc = ContextoVersionService(config_root)
        try:
            if modo == "listar":
                versions = svc.list_versions(contexto_id)
                current = svc.current_version(contexto_id)
                return {"contexto_id": contexto_id, "versao_atual": current,
                        "total_versoes": len(versions), "historico": versions}
            elif modo == "comparar":
                if not versao_a or not versao_b:
                    from concilium.presentation.mcp._context import _wrap_response
                    return _wrap_response({"erro": "modo='comparar' requer versao_a e versao_b"})
                diff = svc.compare(contexto_id, versao_a, versao_b)
                return {"contexto_id": contexto_id, "versao_a": versao_a, "versao_b": versao_b, "diff": diff}
            else:
                from concilium.presentation.mcp._context import _wrap_response
                return _wrap_response({"erro": f"modo '{modo}' inválido. Use: listar | comparar"})
        except Exception as exc:
            return {"erro": str(exc)}
