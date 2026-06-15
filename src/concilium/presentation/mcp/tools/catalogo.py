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


def register(server: FastMCP) -> None:
    """Registra as ferramentas consolidadas de catálogo."""

    # ── Lookup / pesquisa ────────────────────────────────────────────────────

    @server.tool(
        description="Lista os contextos de catálogo disponíveis (ex: mendeslobo, test). Ponto de entrada para descobrir contexto_id."
    )
    def listar_contextos() -> dict[str, Any]:
        return _impl_listar_contextos()

    @server.tool(
        description="Busca CPUs por código ou descrição (ex: query='escavação 1ª cat'). Use para encontrar cpu_id antes de criar projeto."
    )
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
        description="Cobertura do catálogo: % de insumos com preço, % de CPUs calculáveis. Use para saber se o catálogo está pronto para orçamento."
    )
    def consultar_saude_catalogo(contexto_id: str) -> dict[str, Any]:
        return _impl_consultar_saude_catalogo(contexto_id)

    @server.tool(
        description="Detecta valores fora de faixa no catálogo (outliers de preço, razões de produtividade anômalas). Use quando suspeitar de calibração errada."
    )
    def avaliar_plausibilidade_catalogo(
        contexto_id: str,
    ) -> dict[str, Any]:
        return _impl_avaliar_plausibilidade_catalogo(contexto_id)

    @server.tool(
        description="Verifica consistência referencial (insumos ausentes, ciclos de dependência) e recalcula PUs com encargos e diesel informados. Use para auditoria de integridade."
    )
    def verificar_integridade_catalogo(
        contexto_id: str,
        alpha_clt: float = 1.777,
        alpha_pj: float = 1.06,
        preco_diesel: float = 6.50,
    ) -> dict[str, Any]:
        return _impl_verificar_integridade_catalogo(contexto_id, alpha_clt, alpha_pj, preco_diesel)

    # ── Mutação / atualização ────────────────────────────────────────────────

    @server.tool(
        description="Atualiza o preço de um insumo (ex: novo preço de diesel após cotação). Use projeto_id para override de projeto em vez de alterar o master."
    )
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
        description="Retorna o preço de um insumo específico em uma data passada. Use para verificar o preço vigente na época do contrato (diferente de tendencia_precos_catalogo que mostra evolução agregada)."
    )
    def consultar_preco_insumo_temporal(
        contexto_id: str,
        insumo_id: str,
        data_referencia: str,
        projeto_id: str | None = None,
        jurisdicao_id: str | None = None,
    ) -> dict[str, Any]:
        return _impl_consultar_preco_insumo_temporal(contexto_id, insumo_id, data_referencia, projeto_id, jurisdicao_id)

    @server.tool(
        description="Mostra evolução histórica dos preços de todos os insumos do catálogo. Use para detectar inflação ou deflação sistêmica (diferente de consultar_preco_insumo_temporal que retorna ponto único)."
    )
    def tendencia_precos_catalogo(
        contexto_id: str,
        jurisdicao_id: str | None = None,
    ) -> dict[str, Any]:
        return _impl_tendencia_precos_catalogo(contexto_id, jurisdicao_id)

    @server.tool(
        description="Compara dados de RFI (Request for Information) com o catálogo master e lista divergências. dry_run=True (padrão) apenas mostra — use dry_run=False para aplicar as diferenças."
    )
    def comparar_rfi_catalogo(
        contexto_id: str,
        dry_run: bool = True,
    ) -> dict[str, Any]:
        return _impl_comparar_rfi_catalogo(contexto_id, dry_run)

    @server.tool(
        description="Recalcula o preço unitário de uma produção específica dado alpha_clt, alpha_pj e preço do diesel. Use para simular impacto de mudança de encargos ou combustível em uma CPU."
    )
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
            "Lista o histórico de versões de um contexto de catálogo (ADR-062). "
            "Retorna versão atual, histórico com datas e autores, e número total de versões. "
            "Use antes de comparar_versoes_catalogo para saber quais versões existem."
        )
    )
    def listar_versoes_catalogo(contexto_id: str) -> dict[str, Any]:
        from concilium.application.services.catalog.contexto_version_service import ContextoVersionService
        from concilium.infrastructure.settings import get_storage

        config_root = get_storage().config_root
        svc = ContextoVersionService(config_root)
        try:
            versions = svc.list_versions(contexto_id)
            current = svc.current_version(contexto_id)
        except Exception as exc:
            return {"erro": str(exc)}
        return {
            "contexto_id": contexto_id,
            "versao_atual": current,
            "total_versoes": len(versions),
            "historico": versions,
        }

    @server.tool(
        description=(
            "Compara duas versões de um contexto de catálogo lado a lado (ADR-062). "
            "Retorna campos adicionados, removidos e modificados entre as versões. "
            "Use para auditar o que mudou entre uma versão de catálogo e outra "
            "antes de aprovar uma atualização de preços ou composições."
        )
    )
    def comparar_versoes_catalogo(
        contexto_id: str,
        versao_a: str,
        versao_b: str,
    ) -> dict[str, Any]:
        from concilium.application.services.catalog.contexto_version_service import ContextoVersionService
        from concilium.infrastructure.settings import get_storage

        config_root = get_storage().config_root
        svc = ContextoVersionService(config_root)
        try:
            diff = svc.compare(contexto_id, versao_a, versao_b)
        except Exception as exc:
            return {"erro": str(exc)}
        return {
            "contexto_id": contexto_id,
            "versao_a": versao_a,
            "versao_b": versao_b,
            "diff": diff,
        }
