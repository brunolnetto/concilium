"""Builder do Cubo de Estoque Consumível — ADR-128 F6.

Reconstrói ``CuboEstoqueConsumivel`` a partir só do canônico (``recursos_consumiveis`` +
``Cronograma.scheduled_activities``), reaproveitando ``project_estoque_semanal``/
``project_overflow_semanal`` (``application/scheduling/replenishable.py``) — não
reimplementa a matemática de projeção de estoque.

Divergência de camada deliberada frente a ``CuboPoolInstancialBuilder``
(``domain/services/analytics/``): este builder precisa importar de
``application/scheduling``, e ``domain`` não depende de ``application`` no resto do
código — por isso vive em ``application/services/analytics/``, não em
``domain/services/analytics/``. Os modelos de dado (``CuboEstoqueConsumivel``/
``CelulaEstoqueConsumivel``) continuam em ``domain/models/analytics/``, sem dependência
de ``application``.
"""

from __future__ import annotations

from datetime import date, timedelta
from typing import Any

from concilium.application.scheduling.models import ReplenishableResource, ScheduledActivity
from concilium.application.scheduling.replenishable import (
    _taxa_por_semana,
    project_estoque_semanal,
    project_overflow_semanal,
)
from concilium.domain.models.analytics.cubo_estoque_consumivel import (
    CelulaEstoqueConsumivel,
    CuboEstoqueConsumivel,
    EstadoEstoque,
)
from concilium.domain.models.catalog.disponibilidade_consumivel import DisponibilidadeConsumivel


def _get_projeto_id(canonical_in: Any) -> str:
    proj = getattr(canonical_in, "projeto", None)
    if proj is None:
        return ""
    return str(getattr(proj, "nome", "") or getattr(proj, "id", "") or "")


def _iso_week_key(d: date) -> str:
    """Chave de semana ISO 'AAAA-Www' — mesma convenção de `_skill_helpers/_custos.py`."""
    iso = d.isocalendar()
    return f"{iso.year}-W{iso.week:02d}"


def _to_scheduled_activity(sa: Any) -> ScheduledActivity:
    return ScheduledActivity(
        activity_id=sa.activity_id,
        start_week=sa.start_week,
        end_week=sa.end_week,
        duration_weeks=sa.duration_weeks,
    )


def _to_replenishable_resource(rec: Any) -> ReplenishableResource:
    disp = rec.disponibilidade
    return ReplenishableResource(
        resource_id=rec.resource_id,
        disponibilidade=DisponibilidadeConsumivel(
            capacidade_armazenamento=disp.capacidade_armazenamento,
            estoque_inicial=disp.estoque_inicial,
            taxa_reabastecimento_max=disp.taxa_reabastecimento_max,
            lead_time_reabastecimento_dias=disp.lead_time_reabastecimento_dias,
            # ADR-184: sem isto, a projeção reconstruída aqui (para as faces
            # "estoque_temporal"/"fluxo_componente") mostraria estoque negativo para
            # um recurso que o cronograma real já reparou via provisionamento
            # externo (ADR-151) — déficit some do canônico, projeção diverge do
            # cronograma de verdade.
            deficit_provisionado_externamente=disp.deficit_provisionado_externamente,
            preco_provisionamento_externo=disp.preco_provisionamento_externo,
        ),
        consumo_por_semana=dict(rec.consumo_por_semana),
        producao_por_semana=dict(rec.producao_por_semana),
    )


class CuboEstoqueConsumivelBuilder:
    """Reconstrói ``CuboEstoqueConsumivel`` a partir só do canônico (ADR-128 F6)."""

    def build(self, canonical_in: Any, *, gerado_em: str = "") -> CuboEstoqueConsumivel:
        projeto_id = _get_projeto_id(canonical_in)
        recursos = list(getattr(canonical_in, "recursos_consumiveis", None) or [])
        scheduled = self._scheduled_activities(canonical_in)
        data_inicio = self._data_inicio(canonical_in)

        celulas: list[CelulaEstoqueConsumivel] = []
        for rec in recursos:
            celulas.extend(self._celulas_do_recurso(rec, scheduled, data_inicio))

        return CuboEstoqueConsumivel(projeto_id=projeto_id, gerado_em=gerado_em, celulas=tuple(celulas))

    @staticmethod
    def _scheduled_activities(canonical_in: Any) -> list[ScheduledActivity]:
        cronograma = getattr(canonical_in, "cronograma", None)
        return [_to_scheduled_activity(sa) for sa in getattr(cronograma, "scheduled_activities", None) or []]

    @staticmethod
    def _data_inicio(canonical_in: Any) -> date | None:
        proj = getattr(canonical_in, "projeto", None)
        return getattr(proj, "data_inicio", None) if proj is not None else None

    @staticmethod
    def _celulas_do_recurso(
        rec: Any, scheduled: list[ScheduledActivity], data_inicio: date | None
    ) -> list[CelulaEstoqueConsumivel]:
        resource = _to_replenishable_resource(rec)
        niveis = project_estoque_semanal(resource, scheduled)
        overflow = project_overflow_semanal(resource, scheduled)
        consumo_por_t = _taxa_por_semana(resource.consumo_por_semana, scheduled)
        producao_por_t = _taxa_por_semana(resource.producao_por_semana, scheduled)
        reabastecimento = resource.disponibilidade.taxa_reabastecimento_max or 0.0

        celulas: list[CelulaEstoqueConsumivel] = []
        for t in sorted(niveis):
            nivel = niveis[t]
            ovf = overflow.get(t, 0.0)
            estado: EstadoEstoque = "deficit" if nivel < 0 else "overflow" if ovf > 0 else "normal"
            semana_iso = _iso_week_key(data_inicio + timedelta(weeks=t)) if data_inicio else str(t)
            celulas.append(
                CelulaEstoqueConsumivel(
                    resource_id=rec.resource_id,
                    semana_iso=semana_iso,
                    estado=estado,
                    estoque_nivel=round(nivel, 6),
                    consumo=round(consumo_por_t.get(t, 0.0), 6),
                    producao=round(producao_por_t.get(t, 0.0), 6),
                    reabastecimento_externo=reabastecimento,
                    overflow=round(ovf, 6),
                )
            )
        return celulas
