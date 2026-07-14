"""
Índice de Tendência de Preços do Catálogo — ADR-041 §D5 (Skill 20).

Calcula índice de inflação interna por categoria de insumo usando o
histórico SCD Type 2 (historico_precos) e os preços de referência SICRO/ANP
injetados em regionalizacao.

O "Índice MendesLôbo" (IML) mede quanto o custo de cada categoria cresceu
em relação a uma data base, permitindo:
  - Detectar categorias com inflação acima da média de mercado
  - Subsidiar revisões periódicas de tabelas BDI
  - Gerar evidência auditável para repactuação contratual
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, date, datetime
from typing import Any


@dataclass
class TendenciaInsumo:
    codigo: str
    descricao: str
    tipo: str
    unidade: str
    preco_atual: float
    preco_referencia: float | None  # primeiro registro histórico disponível
    data_referencia: str | None
    variacao_abs: float | None
    variacao_pct: float | None
    n_registros_historico: int
    fonte_atual: str  # "preco_unitario" | "SICRO_REGIONAL"


@dataclass
class IndiceCategoria:
    tipo: str
    n_insumos_com_historico: int
    n_insumos_total: int
    variacao_media_pct: float | None  # média de variacao_pct dos insumos com dados
    variacao_mediana_pct: float | None
    variacao_max_pct: float | None
    variacao_min_pct: float | None
    insumos: list[TendenciaInsumo] = field(default_factory=list)


@dataclass
class RelatorioTendencia:
    contexto_id: str
    gerado_em: str
    data_base_analise: str  # data de referência para o cálculo
    jurisdicao_id: str | None
    indices_por_categoria: list[IndiceCategoria]
    resumo: dict[str, Any]


# ── Funções de apoio ──────────────────────────────────────────────────────────


def _mediana(valores: list[float]) -> float | None:
    if not valores:
        return None
    s = sorted(valores)
    n = len(s)
    return s[n // 2] if n % 2 else (s[n // 2 - 1] + s[n // 2]) / 2


def _parse_date(s: str | None) -> date | None:
    if not s:
        return None
    try:
        return date.fromisoformat(str(s)[:10])
    except (ValueError, TypeError):
        return None


def _preco_historico_mais_antigo(insumo: dict) -> tuple[float | None, str | None]:
    """Retorna (preco, data_inicio_vigencia) do registro mais antigo no historico_precos."""
    hist = insumo.get("historico_precos") or []
    if not hist:
        return None, None
    try:
        ordenado = sorted(
            hist,
            key=lambda r: _parse_date(r.get("data_inicio_vigencia")) or date.min,
        )
        mais_antigo = ordenado[0]
        return float(mais_antigo.get("preco_unitario") or 0), mais_antigo.get("data_inicio_vigencia")
    except (TypeError, ValueError, KeyError):
        return None, None


def _preco_sicro_regional(insumo: dict, jurisdicao_id: str) -> float | None:
    """Extrai preço SICRO da regionalizacao (dict ou list)."""
    regz = insumo.get("regionalizacao")
    if not regz:
        return None
    if isinstance(regz, dict):
        reg = regz.get(jurisdicao_id) or {}
    elif isinstance(regz, list):
        reg = next((r for r in regz if r.get("jurisdicao_id") == jurisdicao_id), {})
    else:
        return None
    preco = reg.get("preco")
    return float(preco) if preco is not None else None


def _ct_make_tendencia(ins: dict, jurisdicao_id: str | None) -> TendenciaInsumo | None:
    """Builds TendenciaInsumo for a single insumo, or None if no valid price."""
    cod = ins.get("codigo", "?")
    desc = ins.get("descricao", "")
    tipo = ins.get("tipo", "OUTRO")
    unid = ins.get("unidade", "un")
    if jurisdicao_id:
        preco_atual = _preco_sicro_regional(ins, jurisdicao_id)
        fonte_atual = "SICRO_REGIONAL"
    else:
        preco_atual = None
        fonte_atual = "preco_unitario"
    if preco_atual is None or preco_atual <= 0:
        preco_atual = float(ins.get("preco_unitario") or 0)
        fonte_atual = "preco_unitario"
    if preco_atual <= 0:
        return None
    preco_ref, data_ref_str = _preco_historico_mais_antigo(ins)
    n_hist = len(ins.get("historico_precos") or [])
    var_abs = None
    var_pct = None
    if preco_ref and preco_ref > 0:
        var_abs = round(preco_atual - preco_ref, 4)
        var_pct = round(var_abs / preco_ref * 100, 2)
    return TendenciaInsumo(
        codigo=cod,
        descricao=desc,
        tipo=tipo,
        unidade=unid,
        preco_atual=preco_atual,
        preco_referencia=preco_ref,
        data_referencia=data_ref_str,
        variacao_abs=var_abs,
        variacao_pct=var_pct,
        n_registros_historico=n_hist,
        fonte_atual=fonte_atual,
    )


def _ct_build_indice(tipo: str, lista: list[TendenciaInsumo]) -> IndiceCategoria:
    """Builds IndiceCategoria from a list of TendenciaInsumo for a given tipo."""
    variacoes = [t.variacao_pct for t in lista if t.variacao_pct is not None]
    com_historico = sum(1 for t in lista if t.n_registros_historico > 0)
    return IndiceCategoria(
        tipo=tipo,
        n_insumos_com_historico=com_historico,
        n_insumos_total=len(lista),
        variacao_media_pct=round(sum(variacoes) / len(variacoes), 2) if variacoes else None,
        variacao_mediana_pct=_mediana(variacoes),
        variacao_max_pct=max(variacoes, default=None),
        variacao_min_pct=min(variacoes, default=None),
        insumos=sorted(lista, key=lambda t: t.variacao_pct or 0, reverse=True),
    )


def _ct_build_resumo(insumos: list, indices: list, jurisdicao_id: str | None) -> dict:
    """Builds the resumo summary dict from computed indices."""
    return {
        "total_insumos": len(insumos),
        "total_com_historico": sum(i.n_insumos_com_historico for i in indices),
        "total_com_sicro_regional": sum(
            1 for i in insumos if jurisdicao_id and _preco_sicro_regional(i, jurisdicao_id) is not None
        ),
        "indices": {
            i.tipo: {
                "variacao_media_pct": i.variacao_media_pct,
                "variacao_mediana_pct": i.variacao_mediana_pct,
                "n_com_historico": i.n_insumos_com_historico,
                "n_total": i.n_insumos_total,
            }
            for i in indices
        },
    }


# ── Calculadora principal ─────────────────────────────────────────────────────


def calcular_tendencia(
    insumos: list[dict],
    jurisdicao_id: str | None = None,
    data_base: date | None = None,
    contexto_id: str = "?",
) -> RelatorioTendencia:
    """
    Calcula o índice de tendência de preços por categoria.

    Estratégia de cálculo por insumo:
      1. Preço atual  = regionalizacao[jurisdicao_id].preco   (se jurisdicao disponível)
                       OU  preco_unitario  (fallback)
      2. Preço ref    = historico_precos ordenado por data — o mais antigo disponível
      3. Variação     = (atual - ref) / ref × 100

    Args:
        insumos:      Lista de dicts de insumo do bundle do catálogo.
        jurisdicao_id: Se informado, usa regionalizacao para o preço atual.
        data_base:    Data de referência (filtra apenas registros ≤ data_base).
        contexto_id:  ID do contexto para o relatório.

    Returns:
        RelatorioTendencia com índices por categoria.
    """
    now_str = datetime.now(UTC).strftime("%Y-%m-%d")
    data_base_str = data_base.isoformat() if data_base else now_str
    por_tipo: dict = {}
    for ins in insumos:
        if ins.get("tipo") == "MATERIAL" and ins.get("origem_material") == "GERACAO_INTERNA":
            # ADR-139 D1: material gerado internamente (ex.: solo de corte) não tem
            # preço de mercado nem fornecedor — tendência de preço não se aplica.
            continue
        tendencia = _ct_make_tendencia(ins, jurisdicao_id)
        if tendencia is not None:
            por_tipo.setdefault(tendencia.tipo, []).append(tendencia)
    indices = [_ct_build_indice(tipo, lista) for tipo, lista in sorted(por_tipo.items())]
    resumo = _ct_build_resumo(insumos, indices, jurisdicao_id)

    return RelatorioTendencia(
        contexto_id=contexto_id,
        gerado_em=now_str,
        data_base_analise=data_base_str,
        jurisdicao_id=jurisdicao_id,
        indices_por_categoria=indices,
        resumo=resumo,
    )
