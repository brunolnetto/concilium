"""Builder do Cubo de Pool Instancial — ADR-086 Fase 2.

Materializa as células físicas (instância × semana × estado) a partir das estruturas já
decididas pelo ADR-085 (``InstanciaRecurso``: ciclo de vida, segmentos prod/idle, custos por
componente) e ``RecursoContrato`` (span). **Não recomputa** a economia idle/off (ADR-086 R3):
distribui os custos por componente já gravados na instância pelas suas semanas prod/idle,
garantindo por construção a invariante H1 (Σ células == custo_total_contrato).
"""

from __future__ import annotations

from typing import Any

from concilium.domain.models.cubo_pool import CelulaPoolInstancial, CuboPoolInstancial
from concilium.domain.services.week_sequence import enumerar_semanas

_IDLE_MARKER = "__idle__"


def _get_projeto_id(canonical_in):
    proj = getattr(canonical_in, "projeto", None)
    if proj is None:
        return ""
    return str(getattr(proj, "nome", "") or getattr(proj, "id", "") or "")


def _make_prod_map(inst) -> dict[str, str]:
    prod_map: dict[str, str] = {}
    for seg in getattr(inst, "segmentos_atividade", None) or []:
        for wk in enumerar_semanas(seg.semana_inicio, seg.semana_fim):
            prod_map[wk] = seg.activity_id
    return prod_map


def _make_idle_set(inst) -> set[str]:
    idle_set: set[str] = set()
    for seg in getattr(inst, "segmentos_idle", None) or []:
        for wk in enumerar_semanas(seg.semana_inicio, seg.semana_fim):
            idle_set.add(wk)
    return idle_set


def _get_span(inst, contrato, prod_map, idle_set) -> list[str]:
    span = enumerar_semanas(contrato.semana_inicio, contrato.semana_fim)
    if not span:
        span = sorted(set(prod_map) | idle_set, key=lambda w: w)
    return span


def _prod_weeks_count(span, prod_map) -> int:
    return sum(1 for w in span if w in prod_map)


def _idle_weeks_count(span, idle_set, prod_map) -> int:
    return sum(1 for w in span if w in idle_set and w not in prod_map)


def _per(total: float, n: int) -> float:
    return (float(total or 0.0) / n) if n > 0 else 0.0


def _compute_per_week_costs(inst, n_prod: int, n_idle: int) -> dict:
    return {
        "p_mo": _per(getattr(inst, "custo_ativo_mo", 0.0), n_prod),
        "p_eq": _per(getattr(inst, "custo_ativo_eq", 0.0), n_prod),
        "p_comb": _per(getattr(inst, "custo_ativo_comb", 0.0), n_prod),
        "p_mat": _per(getattr(inst, "custo_ativo_mat", 0.0), n_prod),
        "i_mo": _per(getattr(inst, "custo_idle_mo", 0.0), n_idle),
        "i_eq": _per(getattr(inst, "custo_idle_eq", 0.0), n_idle),
    }


def _append_week_cells(out, wk, inst, contrato, prod_map, idle_set, costs):
    if wk in prod_map:
        out.append(CelulaPoolInstancial(
            contrato_id=contrato.contrato_id, tipo_id=inst.tipo_id,
            instancia_numero=inst.numero, semana_iso=wk, estado="prod",
            atividade_id=prod_map[wk],
            custo_mo=round(costs["p_mo"], 2), custo_eq=round(costs["p_eq"], 2),
            custo_comb=round(costs["p_comb"], 2), custo_mat=round(costs["p_mat"], 2),
        ))
    elif wk in idle_set:
        out.append(CelulaPoolInstancial(
            contrato_id=contrato.contrato_id, tipo_id=inst.tipo_id,
            instancia_numero=inst.numero, semana_iso=wk, estado="idle",
            atividade_id=None,
            custo_mo=round(costs["i_mo"], 2), custo_eq=round(costs["i_eq"], 2),
            custo_comb=0.0, custo_mat=0.0,
        ))
    else:
        out.append(CelulaPoolInstancial(
            contrato_id=contrato.contrato_id, tipo_id=inst.tipo_id,
            instancia_numero=inst.numero, semana_iso=wk, estado="off",
            atividade_id=None,
        ))


def _check_off_zero(cubo) -> dict | None:
    for c in cubo.celulas:
        if c.estado == "off" and c.custo_total != 0.0:
            return {"codigo": "VAL-POOL-CUBO-OFF-ZERO", "instancia": c.instancia_id,
                    "semana": c.semana_iso, "custo": c.custo_total}
    return None


def _sum_by_contrato(cubo) -> dict[str, float]:
    soma: dict[str, float] = {}
    for c in cubo.celulas:
        soma[c.contrato_id] = soma.get(c.contrato_id, 0.0) + c.custo_total
    return soma


def _contract_custo(contrato) -> float:
    return float(getattr(contrato, "custo_total_contrato", 0.0) or 0.0)


def _check_h1(soma_por_contrato, contratos) -> list[dict]:
    violacoes: list[dict] = []
    for contrato in (contratos or []):
        esperado = _contract_custo(contrato)
        obtido = round(soma_por_contrato.get(contrato.contrato_id, 0.0), 2)
        if abs(obtido - esperado) > max(1.0, esperado * 0.001):
            violacoes.append({"codigo": "VAL-POOL-CUBO-SOMA", "contrato": contrato.contrato_id,
                              "esperado": round(esperado, 2), "obtido": obtido})
    return violacoes


class CuboPoolInstancialBuilder:
    def build(self, canonical_in: Any, *, gerado_em: str = "") -> CuboPoolInstancial:
        projeto_id = _get_projeto_id(canonical_in)
        contratos = list(getattr(canonical_in, "contratos_recurso", None) or [])
        instancias = list(getattr(canonical_in, "instancias_recurso", None) or [])
        contrato_por_id = {c.contrato_id: c for c in contratos}
        celulas = self._build_celulas(instancias, contrato_por_id)
        return CuboPoolInstancial(
            projeto_id=projeto_id,
            gerado_em=gerado_em,
            celulas=tuple(celulas),
        )

    def _build_celulas(self, instancias, contrato_por_id) -> list:
        celulas: list[CelulaPoolInstancial] = []
        for inst in instancias:
            contrato = contrato_por_id.get(inst.contrato_id)
            if contrato is None:
                continue
            celulas.extend(self._celulas_da_instancia(inst, contrato))
        return celulas

    def _celulas_da_instancia(self, inst: Any, contrato: Any) -> list[CelulaPoolInstancial]:
        prod_map = _make_prod_map(inst)
        idle_set = _make_idle_set(inst)
        span = _get_span(inst, contrato, prod_map, idle_set)
        n_prod = _prod_weeks_count(span, prod_map)
        n_idle = _idle_weeks_count(span, idle_set, prod_map)
        costs = _compute_per_week_costs(inst, n_prod, n_idle)
        out: list[CelulaPoolInstancial] = []
        for wk in span:
            _append_week_cells(out, wk, inst, contrato, prod_map, idle_set, costs)
        return out


def validar_invariantes_cubo_pool(cubo: CuboPoolInstancial, contratos: Any) -> list[dict]:
    """Verifica H1 (soma), H3 (off zero). Retorna lista de violações (vazia = OK)."""
    violacoes: list[dict] = []
    h3 = _check_off_zero(cubo)
    if h3 is not None:
        violacoes.append(h3)
    violacoes.extend(_check_h1(_sum_by_contrato(cubo), contratos))
    return violacoes
