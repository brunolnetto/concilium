"""CampanhaEquipamentoBuilder — detecta campanhas de permanência de equipamentos (ADR-059).

Para cada tipo de equipamento usado no projeto, identifica grupos de atividades
consecutivas (gap ≤ threshold_dismissal) que podem compartilhar uma campanha —
evitando custos duplicados de mobilização/desmobilização.

Emite VAL-CAMP-01 quando campanhas candidatas NÃO foram detectadas mas o custo
de dismissal seria superior ao de standby.
"""

from __future__ import annotations

from collections import defaultdict
from datetime import UTC, datetime
from typing import Any

from concilium.domain.models.campaign.campanha_equipamento import (
    AnaliseFrequenciaCampanhas,
    CampanhaEquipamento,
    InstanciaEquipamento,
    RegimePermanencia,
)


def _ceb_start_week_key(u: dict) -> int:
    """Sort key for usage dict by start_week."""
    return u["start_week"]


def _ceb_collect_uso_por_tipo(canonical_in: object, sched_lookup: dict) -> dict:
    """Collects equipment usage records keyed by equip_id."""
    uso_por_tipo: dict = defaultdict(list)
    for equipe in canonical_in.equipes_diretas or []:
        sa = sched_lookup.get(equipe.item_id)
        if not sa:
            continue
        for equip in equipe.equipamentos:
            if not equip.equip_id:
                continue
            uso_por_tipo[equip.equip_id].append(
                {
                    "item_id": equipe.item_id,
                    "num_unidades": equip.num_unidades,
                    "start_week": sa.start_week,
                    "end_week": sa.end_week,
                    "custo_mensal": equip.custo_mensal,
                }
            )
    return uso_por_tipo


def _ceb_group_sorted_usos(sorted_usos: list, gap_limit: int, regime: object, tipo_id: str) -> tuple:
    """Groups sorted equipment usages into campaigns. Returns (groups, alertas)."""
    groups = []
    alertas = []
    i = 0
    while i < len(sorted_usos):
        group = [sorted_usos[i]]
        j = i + 1
        while j < len(sorted_usos):
            prev_end = max(u["end_week"] for u in group)
            gap = sorted_usos[j]["start_week"] - prev_end - 1
            if gap <= gap_limit:
                group.append(sorted_usos[j])
                j += 1
            else:
                standby_cost = gap * regime.custo_standby_semanal
                mob_cost = regime.custo_mob + regime.custo_demob
                if mob_cost > standby_cost and gap <= regime.threshold_dismissal:
                    alertas.append(
                        f"VAL-CAMP-01: {tipo_id} gap={gap} sem. entre "
                        f"'{group[-1]['item_id']}' e '{sorted_usos[j]['item_id']}'. "
                        f"Standby(R${standby_cost:.0f}) < Dismissal(R${mob_cost:.0f}). "
                        "Considere campanha compartilhada."
                    )
                break
        groups.append(group)
        i = j
    return groups, alertas


def _ceb_build_campanha(group: list, tipo_id: str, instancia_num: int, regime: object, inst_id: str) -> tuple:
    """Builds (InstanciaEquipamento, CampanhaEquipamento) from a usage group."""
    from concilium.domain.models.campaign.campanha_equipamento import CampanhaEquipamento, InstanciaEquipamento

    active_weeks: set = set()
    for u in group:
        active_weeks.update(range(u["start_week"], u["end_week"] + 1))
    semanas_ativas = len(active_weeks)
    semana_entrada = min(u["start_week"] for u in group)
    semana_saida = max(u["end_week"] for u in group)
    semanas_standby = (semana_saida - semana_entrada + 1) - semanas_ativas
    custo_standby = round(max(0, semanas_standby) * regime.custo_standby_semanal, 2)
    custo_camp = round(regime.custo_mob + regime.custo_demob + custo_standby, 2)
    custo_sem_camp = round(len(group) * (regime.custo_mob + regime.custo_demob), 2)
    economia = round(max(0, custo_sem_camp - custo_camp), 2)
    instancia = InstanciaEquipamento(
        instancia_id=inst_id,
        tipo_id=tipo_id,
        numero=instancia_num,
        regime=regime,
    )
    campanha = CampanhaEquipamento(
        instancia_id=inst_id,
        tipo_id=tipo_id,
        semana_entrada=semana_entrada,
        semana_saida=semana_saida,
        atividades=tuple(u["item_id"] for u in group),
        semanas_ativas=semanas_ativas,
        semanas_standby=max(0, semanas_standby),
        custo_mob=regime.custo_mob,
        custo_demob=regime.custo_demob,
        custo_standby_total=custo_standby,
        custo_campanha=custo_camp,
        economia_vs_dismissal=economia,
    )
    return instancia, campanha


class CampanhaEquipamentoBuilder:
    """Constrói AnaliseFrequenciaCampanhas a partir de canonical + schedule.

    Args:
        gap_max_semanas: gap máximo entre atividades para considerar campanha compartilhada.
                         Se None, usa threshold_dismissal de cada equipamento.
        regimes_override: dict de {tipo_id → RegimePermanencia} para sobrescrever estimativas.
    """

    def __init__(
        self,
        gap_max_semanas: int | None = None,
        regimes_override: dict[str, RegimePermanencia] | None = None,
    ) -> None:
        self._gap_max = gap_max_semanas
        self._regimes = regimes_override or {}

    def build(self, canonical_in: Any) -> AnaliseFrequenciaCampanhas:
        projeto_id = str(getattr(getattr(canonical_in, "projeto", None), "nome", "?"))
        cronograma = canonical_in.cronograma
        if not cronograma or not cronograma.scheduled_activities:
            return self._empty(projeto_id)

        sched_lookup = {sa.activity_id: sa for sa in cronograma.scheduled_activities}

        uso_por_tipo = _ceb_collect_uso_por_tipo(canonical_in, sched_lookup)

        campanhas: list[CampanhaEquipamento] = []
        alertas: list[str] = []
        instancias: dict[str, list[InstanciaEquipamento]] = {}

        for tipo_id, usos in uso_por_tipo.items():
            if not usos:
                continue
            sorted_usos = sorted(usos, key=_ceb_start_week_key)
            regime = self._get_regime(tipo_id, sorted_usos[0]["custo_mensal"])
            gap_limit = self._gap_max if self._gap_max is not None else int(regime.threshold_dismissal)
            gap_limit = max(0, gap_limit)
            groups, type_alertas = _ceb_group_sorted_usos(sorted_usos, gap_limit, regime, tipo_id)
            alertas.extend(type_alertas)
            instancias[tipo_id] = []
            for instancia_num, group in enumerate(groups, 1):
                inst_id = f"{tipo_id}#{instancia_num}"
                instancia, campanha = _ceb_build_campanha(group, tipo_id, instancia_num, regime, inst_id)
                instancias[tipo_id].append(instancia)
                campanhas.append(campanha)

        economia_total = sum(c.economia_vs_dismissal for c in campanhas)
        custo_standby_total = sum(c.custo_standby_total for c in campanhas)

        return AnaliseFrequenciaCampanhas(
            projeto_id=projeto_id,
            gerado_em=datetime.now(UTC).isoformat(),
            n_campanhas=len(campanhas),
            n_instancias=len(campanhas),
            economia_total=round(economia_total, 2),
            custo_standby_total=round(custo_standby_total, 2),
            economia_liquida=round(economia_total - custo_standby_total, 2),
            campanhas=tuple(campanhas),
            alertas_custo_duplicado=tuple(alertas),
        )

    def _get_regime(self, tipo_id: str, custo_mensal_ref: float) -> RegimePermanencia:
        if tipo_id in self._regimes:
            return self._regimes[tipo_id]
        return RegimePermanencia.estimado(tipo_id, custo_mensal_ref)

    @staticmethod
    def _empty(projeto_id: str) -> AnaliseFrequenciaCampanhas:
        return AnaliseFrequenciaCampanhas(
            projeto_id=projeto_id,
            gerado_em=datetime.now(UTC).isoformat(),
            n_campanhas=0,
            n_instancias=0,
            economia_total=0.0,
            custo_standby_total=0.0,
            economia_liquida=0.0,
            campanhas=(),
            alertas_custo_duplicado=(),
        )
