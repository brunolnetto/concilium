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

    @server.tool(description="Lista os contextos de catálogo disponíveis.")
    def listar_contextos() -> dict[str, Any]:
        return _impl_listar_contextos()

    @server.tool(description="Pesquisa CPUs e recursos no catálogo de um contexto.")
    def pesquisar_catalogo(
        contexto_id: str,
        query: str | None = None,
        tipo_obra: str | None = None,
        limite: int = 20,
    ) -> dict[str, Any]:
        return _impl_pesquisar_catalogo(contexto_id, query, tipo_obra, limite)

    @server.tool(description="Consulta indicadores de saúde e cobertura do catálogo do contexto.")
    def consultar_saude_catalogo(contexto_id: str) -> dict[str, Any]:
        return _impl_consultar_saude_catalogo(contexto_id)

    @server.tool(description="Atualiza preço de um insumo no contexto/projeto informado.")
    def atualizar_preco_insumo(
        contexto_id: str,
        insumo_id: str,
        novo_preco: float,
        projeto_id: str | None = None,
        jurisdicao_id: str | None = None,
        nota: str | None = None,
    ) -> dict[str, Any]:
        return _impl_atualizar_preco_insumo(contexto_id, insumo_id, novo_preco, projeto_id, jurisdicao_id, nota)

    @server.tool(description="Consulta preço temporal de insumo para uma data de referência.")
    def consultar_preco_insumo_temporal(
        contexto_id: str,
        insumo_id: str,
        data_referencia: str,
        projeto_id: str | None = None,
        jurisdicao_id: str | None = None,
    ) -> dict[str, Any]:
        return _impl_consultar_preco_insumo_temporal(contexto_id, insumo_id, data_referencia, projeto_id, jurisdicao_id)

    @server.tool(description="Adiciona variante de produção com equipe e valor horário.")
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

    # ── Ferramentas de Merge RFI + Integridade ────────────────────────────────

    @server.tool(description="Analisa tendência histórica de preços no catálogo do contexto.")
    def tendencia_precos_catalogo(
        contexto_id: str,
        jurisdicao_id: str | None = None,
    ) -> dict[str, Any]:
        return _impl_tendencia_precos_catalogo(contexto_id, jurisdicao_id)

    @server.tool(description="Compara dados RFI com catálogo e retorna divergências.")
    def comparar_rfi_catalogo(
        contexto_id: str,
        dry_run: bool = True,
    ) -> dict[str, Any]:
        return _impl_comparar_rfi_catalogo(contexto_id, dry_run)

    @server.tool(description="Calcula PU de produção a partir de parâmetros de custos e encargos.")
    def calcular_pu_producao(
        contexto_id: str,
        producao_id: str,
        alpha_clt: float = 1.777,
        alpha_pj: float = 1.06,
        preco_diesel: float = 6.50,
        horas_mes: float = 208.0,
    ) -> dict[str, Any]:
        return _impl_calcular_pu_producao(contexto_id, producao_id, alpha_clt, alpha_pj, preco_diesel, horas_mes)

    @server.tool(description="Avalia plausibilidade dos dados do catálogo para um contexto.")
    def avaliar_plausibilidade_catalogo(
        contexto_id: str,
    ) -> dict[str, Any]:
        return _impl_avaliar_plausibilidade_catalogo(contexto_id)

    @server.tool(description="Verifica integridade estrutural e consistência do catálogo.")
    def verificar_integridade_catalogo(
        contexto_id: str,
        alpha_clt: float = 1.777,
        alpha_pj: float = 1.06,
        preco_diesel: float = 6.50,
    ) -> dict[str, Any]:
        return _impl_verificar_integridade_catalogo(contexto_id, alpha_clt, alpha_pj, preco_diesel)
