"""Projeções (faces) do Cubo de Pool Instancial — ADR-086 Fases 3-4.

Constantes e helpers compartilhados (baseline homogênea, formatação).
"""

from __future__ import annotations

from typing import Any

from concilium.application.services.analytics.cube_projection_views import FaceGranularity, bucket_from_week_iso

_COMP_LABEL = {"mo": "Mão-de-obra", "eq": "Equipamento", "comb": "Combustível", "mat": "Material"}


_ESTADO_LABEL = {"prod": "Produtivo", "idle": "Ocioso", "off": "Desmobilizado"}


_FACES: dict[str, dict] = {
    "utilizacao_temporal": {
        "label": "Utilização no tempo",
        "natureza": "fisica",
        "unit_type": "count",
        "chart_hint": "bar_stacked",
    },
    "custo_estado_componente": {
        "label": "Custo por estado × componente",
        "natureza": "fisica",
        "unit_type": "currency_brl",
        "chart_hint": "heatmap",
    },
    "instancia_ciclo_vida": {
        "label": "Ciclo de vida por instância",
        "natureza": "fisica",
        "unit_type": "currency_brl",
        "chart_hint": "table",
    },
    "atividade_instancia": {
        "label": "Rastreabilidade atividade ↔ slot",
        "natureza": "fisica",
        "unit_type": "count",
        "chart_hint": "table",
    },
    "causa_custo": {
        "label": "Causa do custo (Euler)",
        "natureza": "causal",
        "unit_type": "currency_brl",
        "chart_hint": "bar_stacked",
    },
    "economia_pool": {
        "label": "Economia vs. execução autônoma",
        "natureza": "causal",
        "unit_type": "currency_brl",
        "chart_hint": "bar",
    },
    "cadeia_perpetuacao": {
        "label": "Cadeias de perpetuação",
        "natureza": "estrutural",
        "unit_type": "count",
        "chart_hint": "table",
    },
}


_GRANULARIDADES = ["semana", "mes", "trimestre", "ano"]


_GRANULARIDADES_VALIDAS: dict[str, FaceGranularity] = {
    "semana": "semana",
    "mes": "mes",
    "bimestre": "bimestre",
    "trimestre": "trimestre",
    "semestre": "semestre",
    "ano": "ano",
}


def _planejamento_sem_bdi_total(plan: Any) -> float:
    subtotal = getattr(plan, "subtotal", None)
    sem_bdi = getattr(subtotal, "sem_bdi", None) if subtotal is not None else None
    total = getattr(sem_bdi, "total", 0.0) if sem_bdi is not None else 0.0
    return round(float(total or 0.0), 2)


def _autonomo_total_por_item(eq: Any) -> float:
    """Retorna baseline autônomo total do item, expandindo custo por frente quando necessário."""
    custo_1_frente = float(getattr(eq, "custo_total_autonomo", 0.0) or 0.0)
    if custo_1_frente <= 0.0:
        return 0.0
    n_frentes = max(1, int(getattr(eq, "num_equipes_base", 1) or 1))
    return round(custo_1_frente * n_frentes, 2)


def _baseline_from_planejamento(canonical_in: Any, baseline: dict[str, float], source: dict[str, str]) -> None:
    for plan in getattr(canonical_in, "planejamento", None) or []:
        item_id = str(getattr(plan, "item_id", "") or "")
        if not item_id:
            continue
        total = _planejamento_sem_bdi_total(plan)
        if total > 0.0:
            baseline[item_id] = total
            source[item_id] = "planejamento_sem_bdi"


def _baseline_from_equipes_diretas(canonical_in: Any, baseline: dict[str, float], source: dict[str, str]) -> None:
    for eq in getattr(canonical_in, "equipes_diretas", None) or []:
        item_id = str(getattr(eq, "item_id", "") or "")
        if not item_id or item_id in baseline:
            continue
        total = _autonomo_total_por_item(eq)
        if total > 0.0:
            baseline[item_id] = total
            source[item_id] = "operacional_autonomo_fallback"


def _baseline_homogenea_por_item(canonical_in: Any) -> tuple[dict[str, float], dict[str, str]]:
    """Retorna baseline por item no mesmo referencial do planejamento (sem BDI).

    Preferência:
    1. subtotal.sem_bdi.total do planejamento (referencial homogêneo de orçamento)
    2. custo_total_autonomo operacional expandido por frentes (fallback legado)
    """
    baseline: dict[str, float] = {}
    source: dict[str, str] = {}

    _baseline_from_planejamento(canonical_in, baseline, source)
    _baseline_from_equipes_diretas(canonical_in, baseline, source)

    return baseline, source


def _count_mob_demob_por_periodo(cubo: Any, granularidade: FaceGranularity) -> dict[str, dict[str, int]]:
    """Conta eventos de mobilização e desmobilização por bucket temporal."""
    counts: dict[str, dict[str, int]] = {}

    def _bucket(week_label: str) -> str:
        # Só é chamada dentro de `if semana_mob:`/`if semana_demob:` abaixo,
        # logo txt nunca é vazio aqui.
        txt = str(week_label)
        if "-W" not in txt:
            return txt
        return bucket_from_week_iso(txt, granularidade)

    for data in (cubo.ciclo_vida_instancias() or {}).values():
        semana_mob = str(data.get("semana_mob", "") or "")
        semana_demob = str(data.get("semana_demob", "") or "")
        if semana_mob:
            bucket = _bucket(semana_mob)
            counts.setdefault(bucket, {"mob": 0, "demob": 0})["mob"] += 1
        if semana_demob:
            bucket = _bucket(semana_demob)
            counts.setdefault(bucket, {"mob": 0, "demob": 0})["demob"] += 1
    return counts


def _fmt(v: float) -> str:
    return f"R$ {v:,.0f}"


