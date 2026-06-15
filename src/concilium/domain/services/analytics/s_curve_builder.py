"""SCurveBuilder — constrói a Curva S e agregações semanais de equipamentos (ADR-058 D3/D4).

A curva S expõe a trajetória planejada de desembolso semanal e acumulado,
integrando custos diretos das equipes com custos indiretos semanais.

Fórmula por semana w:
    custo_direto(w) = Σ_atividades { custo_fixo_mensal / SEMANAS_POR_MES × num_equipes(w) }
    custo_indireto(w) = Σ IndiretoSemanal[semana_offset == w].custo_semanal
    custo_total(w) = custo_direto(w) + custo_indireto(w)
"""

from __future__ import annotations

from collections import defaultdict
from datetime import UTC, datetime
from typing import Any

from concilium.domain.constants import SEMANAS_POR_MES
from concilium.domain.models.analytics.analitica import AgregacaoSemanalEquipamentos, SCurve
from concilium.domain.services.planning.week_sequence import next_week


def _scb_collect_semanas(sched_activities: list) -> tuple:
    """Returns (semanas_sorted, semana_to_offset) or (None, None) if no weeks found."""
    semanas_set: set = set()
    for sa in sched_activities:
        semanas_set.update(sa.distribuicao_semanal.keys())
    if not semanas_set:
        return None, None
    semanas_sorted = sorted(semanas_set)
    semana_to_offset = {s: i for i, s in enumerate(semanas_sorted)}
    return semanas_sorted, semana_to_offset


def _scb_extend_weeks_for_offsets(semanas_sorted: list[str], max_offset: int) -> list[str]:
    """Extende série ISO para cobrir offsets indiretos fora da malha de atividades."""
    if not semanas_sorted:
        return semanas_sorted
    if max_offset < len(semanas_sorted):
        return semanas_sorted
    out = list(semanas_sorted)
    cur = out[-1]
    while len(out) <= max_offset:
        cur = next_week(cur)
        out.append(cur)
    return out


def _scb_collect_direct_costs(sched_activities: list, equipe_lookup: dict) -> tuple:
    """Returns (custo_por_semana, equip_por_semana, n_equipes_por_semana) dicts."""
    from collections import defaultdict

    custo_por_semana: dict = defaultdict(float)
    equip_por_semana: dict = defaultdict(lambda: defaultdict(int))
    n_equipes_por_semana: dict = defaultdict(int)
    for sa in sched_activities:
        equipe = equipe_lookup.get(sa.activity_id)
        if not equipe:
            continue
        custo_semanal_base = (
            equipe.custo_mao_obra_mensal + equipe.custo_equipamentos_mensal + equipe.custo_material_mensal
        ) / SEMANAS_POR_MES
        comb_semanal = equipe.custo_combustivel_total_mensal / SEMANAS_POR_MES
        for semana_iso, dist in sa.distribuicao_semanal.items():
            n = dist.num_equipes
            if n <= 0:
                continue
            # ADR-082: combustível escala com a produtividade efetiva (η_j = praticabilidade
            # × utilização = fator_total), não com a utilização isolada (eficiencia).
            eta = float(getattr(dist, "fator_total", None) or dist.eficiencia)
            custo_semana = (custo_semanal_base + comb_semanal * eta) * n
            custo_por_semana[semana_iso] += custo_semana
            n_equipes_por_semana[semana_iso] += n
            for eq in equipe.equipamentos:
                if eq.equip_id:
                    equip_por_semana[semana_iso][eq.equip_id] += eq.num_unidades * n
    return custo_por_semana, equip_por_semana, n_equipes_por_semana


def _scb_collect_direct_costs_pool(canonical_in: Any) -> dict[str, float]:
    """Custos diretos instanciais por semana (prod+idle+off) a partir do cubo pool."""
    from concilium.domain.services.analytics.cubo_pool_builder import CuboPoolInstancialBuilder

    custo_por_semana: dict[str, float] = defaultdict(float)
    try:
        cubo_pool = CuboPoolInstancialBuilder().build(canonical_in)
    except Exception:
        return {}
    for cell in getattr(cubo_pool, "celulas", ()):
        custo_por_semana[cell.semana_iso] += float(cell.custo_total or 0.0)
    return dict(custo_por_semana)


def _scb_build_agregacoes(
    semanas_sorted: list,
    semana_to_offset: dict,
    custo_por_semana: dict,
    custo_indireto_por_semana: dict,
    equip_por_semana: dict,
    n_equipes_por_semana: dict,
) -> tuple:
    """Returns (agregacoes, custo_semanal_list) for the weekly aggregated records."""
    agregacoes = []
    custo_semanal_list: list = []
    for semana_iso in semanas_sorted:
        c_dir = custo_por_semana[semana_iso]
        c_ind = custo_indireto_por_semana[semana_iso]
        c_total = c_dir + c_ind
        custo_semanal_list.append(round(c_total, 2))
        equips = dict(equip_por_semana[semana_iso])
        agregacoes.append(
            AgregacaoSemanalEquipamentos(
                semana_iso=semana_iso,
                semana_offset=semana_to_offset[semana_iso],
                equipamentos_ativos=equips,
                n_equipamentos_unicos=len([k for k, v in equips.items() if v > 0]),
                n_equipes_totais=n_equipes_por_semana[semana_iso],
                custo_direto_semana=round(c_dir, 2),
                custo_indireto_semana=round(c_ind, 2),
                custo_total_semana=round(c_total, 2),
            )
        )
    return agregacoes, custo_semanal_list


def _scb_build_curves(custo_semanal_list: list, total_proj: float) -> tuple:
    """Returns (custo_acum_list, pct_acum_list) cumulative series."""
    custo_acum_list = []
    pct_acum_list = []
    acum = 0.0
    for c in custo_semanal_list:
        acum += c
        custo_acum_list.append(round(acum, 2))
        pct_acum_list.append(round(acum / total_proj, 6) if total_proj > 0 else 0.0)
    return custo_acum_list, pct_acum_list


class SCurveBuilder:
    """Constrói SCurve e AgregacaoSemanalEquipamentos a partir de um CanonicalModel."""

    def build(self, canonical_in: Any) -> SCurve:
        projeto_id = str(getattr(getattr(canonical_in, "projeto", None), "nome", "?"))
        cronograma = canonical_in.cronograma
        if not cronograma or not cronograma.scheduled_activities:
            return self._empty(projeto_id)

        equipe_lookup = {e.item_id: e for e in (canonical_in.equipes_diretas or [])}
        indireto_semanal_lookup: dict[int, float] = defaultdict(float)
        for ind in canonical_in.indiretos_semanal or []:
            indireto_semanal_lookup[ind.semana] += ind.custo_semanal

        semanas_sorted, semana_to_offset = _scb_collect_semanas(cronograma.scheduled_activities)
        if semanas_sorted is None:
            return self._empty(projeto_id)

        # Fonte única para direto: agregação instancial do pool quando disponível.
        custo_por_semana, equip_por_semana, n_equipes_por_semana = _scb_collect_direct_costs(
            cronograma.scheduled_activities, equipe_lookup
        )
        custo_por_semana_pool = _scb_collect_direct_costs_pool(canonical_in)
        if custo_por_semana_pool:
            custo_por_semana = defaultdict(float, custo_por_semana_pool)
            semanas_sorted = sorted(set(semanas_sorted) | set(custo_por_semana_pool.keys()))
            semana_to_offset = {s: i for i, s in enumerate(semanas_sorted)}

        # Indirect costs — map offset → semana_iso; cobre cauda de offsets fora da malha de atividades.
        max_ind_offset = max(indireto_semanal_lookup.keys(), default=-1)
        semanas_sorted = _scb_extend_weeks_for_offsets(semanas_sorted, max_ind_offset)
        semana_to_offset = {s: i for i, s in enumerate(semanas_sorted)}
        custo_indireto_por_semana: dict = defaultdict(float)
        for semana_iso in semanas_sorted:
            offset = semana_to_offset[semana_iso]
            custo_indireto_por_semana[semana_iso] += indireto_semanal_lookup.get(offset, 0.0)

        agregacoes, custo_semanal_list = _scb_build_agregacoes(
            semanas_sorted,
            semana_to_offset,
            custo_por_semana,
            custo_indireto_por_semana,
            equip_por_semana,
            n_equipes_por_semana,
        )

        total_dir = sum(custo_por_semana.values())
        total_ind = sum(custo_indireto_por_semana.values())
        total_proj = total_dir + total_ind

        custo_acum_list, pct_acum_list = _scb_build_curves(custo_semanal_list, total_proj)

        return SCurve(
            projeto_id=projeto_id,
            gerado_em=datetime.now(UTC).isoformat(),
            total_custo_direto=round(total_dir, 2),
            total_custo_indireto=round(total_ind, 2),
            total_projeto=round(total_proj, 2),
            semanas_iso=tuple(semanas_sorted),
            custo_semanal=tuple(custo_semanal_list),
            custo_acumulado=tuple(custo_acum_list),
            pct_acumulado=tuple(pct_acum_list),
            agregacao_semanal=tuple(agregacoes),
        )

    @staticmethod
    def _empty(projeto_id: str) -> SCurve:
        return SCurve(
            projeto_id=projeto_id,
            gerado_em=datetime.now(UTC).isoformat(),
            total_custo_direto=0.0,
            total_custo_indireto=0.0,
            total_projeto=0.0,
            semanas_iso=(),
            custo_semanal=(),
            custo_acumulado=(),
            pct_acumulado=(),
            agregacao_semanal=(),
        )
