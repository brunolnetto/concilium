"""ADR-152 — Timelapse de Ocupação de Instância de Recurso (Pool): TDD.

Cobre:
  - `project_ocupacao_semanal`: expande segmentos_atividade/segmentos_idle de uma
    InstanciaRecurso num dict semana→status ("prod"/"idle"/"off"), análogo a
    project_estoque_semanal (ADR-128) para material.
  - `project_ocupacao_contrato_semanal`: agregação por contrato — soma prod/idle/off
    por semana entre todas as instâncias de um RecursoContrato.

Escrito antes da implementação (red phase). Nenhuma mudança em InstanciaRecurso/
RecursoContrato/CP-SAT — função pura de leitura sobre dado já persistido.
"""

from __future__ import annotations

from concilium.application.scheduling.pool_timelapse import (
    project_ocupacao_contrato_semanal,
    project_ocupacao_semanal,
)
from concilium.domain.models.canonical import (
    InstanciaRecurso,
    RecursoContrato,
    SegmentoAtividade,
)


def _contrato(contrato_id: str = "contrato-esc-3cat", **overrides) -> RecursoContrato:
    defaults = dict(
        contrato_id=contrato_id,
        tipo_id="ESC-3CAT",
        quantidade_contratada=2,
        semana_inicio="2026-W01",
        semana_fim="2026-W04",
        semanas_contrato=4,
        custo_unit_semanal=1000.0,
        custo_total_contrato=8000.0,
    )
    defaults.update(overrides)
    return RecursoContrato(**defaults)


def _instancia(numero: int = 1, contrato_id: str = "contrato-esc-3cat", **overrides) -> InstanciaRecurso:
    defaults = dict(
        instancia_id=f"ESC-3CAT-{numero:02d}",
        contrato_id=contrato_id,
        tipo_id="ESC-3CAT",
        numero=numero,
        semana_entrada="2026-W01",
        semana_saida="2026-W04",
    )
    defaults.update(overrides)
    return InstanciaRecurso(**defaults)


class TestProjectOcupacaoSemanal:
    def test_semana_em_segmento_atividade_e_prod(self):
        instancia = _instancia(
            segmentos_atividade=[
                SegmentoAtividade(
                    activity_id="eap-1", semana_inicio="2026-W01", semana_fim="2026-W02", machine_weeks=2
                )
            ],
        )
        ocupacao = project_ocupacao_semanal(instancia)
        assert ocupacao["2026-W01"] == "prod"
        assert ocupacao["2026-W02"] == "prod"

    def test_semana_em_segmento_idle_e_idle(self):
        instancia = _instancia(
            segmentos_atividade=[
                SegmentoAtividade(
                    activity_id="eap-1", semana_inicio="2026-W01", semana_fim="2026-W01", machine_weeks=1
                )
            ],
            segmentos_idle=[
                SegmentoAtividade(
                    activity_id="__idle__", semana_inicio="2026-W02", semana_fim="2026-W02", machine_weeks=1
                )
            ],
        )
        ocupacao = project_ocupacao_semanal(instancia)
        assert ocupacao["2026-W02"] == "idle"

    def test_semana_fora_de_qualquer_segmento_e_off(self):
        instancia = _instancia(
            segmentos_atividade=[
                SegmentoAtividade(
                    activity_id="eap-1", semana_inicio="2026-W01", semana_fim="2026-W01", machine_weeks=1
                )
            ],
        )
        ocupacao = project_ocupacao_semanal(instancia)
        # span do contrato é W01-W04; só W01 tem segmento — W02/W03/W04 residuais
        assert ocupacao["2026-W02"] == "off"
        assert ocupacao["2026-W03"] == "off"
        assert ocupacao["2026-W04"] == "off"

    def test_instancia_nunca_utilizada_e_toda_off(self):
        instancia = _instancia()  # sem segmentos_atividade nem segmentos_idle
        ocupacao = project_ocupacao_semanal(instancia)
        assert ocupacao == {
            "2026-W01": "off",
            "2026-W02": "off",
            "2026-W03": "off",
            "2026-W04": "off",
        }

    def test_prod_tem_precedencia_sobre_idle_em_sobreposicao_defensiva(self):
        # Não deveria ocorrer por construção (_build_instancia_slot nunca sobrepõe os
        # dois), mas a função deve ser defensiva: prod sempre vence.
        instancia = _instancia(
            segmentos_atividade=[
                SegmentoAtividade(
                    activity_id="eap-1", semana_inicio="2026-W01", semana_fim="2026-W01", machine_weeks=1
                )
            ],
            segmentos_idle=[
                SegmentoAtividade(
                    activity_id="__idle__", semana_inicio="2026-W01", semana_fim="2026-W01", machine_weeks=1
                )
            ],
        )
        ocupacao = project_ocupacao_semanal(instancia)
        assert ocupacao["2026-W01"] == "prod"

    def test_sem_span_de_contrato_retorna_vazio(self):
        instancia = _instancia(semana_entrada="", semana_saida="")
        assert project_ocupacao_semanal(instancia) == {}


class TestProjectOcupacaoContratoSemanal:
    def test_agrega_prod_idle_off_por_semana_entre_instancias(self):
        contrato = _contrato()
        inst1 = _instancia(
            numero=1,
            segmentos_atividade=[
                SegmentoAtividade(
                    activity_id="eap-1", semana_inicio="2026-W01", semana_fim="2026-W02", machine_weeks=2
                )
            ],
        )
        inst2 = _instancia(
            numero=2,
            segmentos_idle=[
                SegmentoAtividade(
                    activity_id="__idle__", semana_inicio="2026-W01", semana_fim="2026-W01", machine_weeks=1
                )
            ],
        )
        agregado = project_ocupacao_contrato_semanal(contrato, [inst1, inst2])
        assert agregado["2026-W01"] == {"prod": 1, "idle": 1, "off": 0}
        assert agregado["2026-W02"] == {"prod": 1, "idle": 0, "off": 1}
        assert agregado["2026-W03"] == {"prod": 0, "idle": 0, "off": 2}
        assert agregado["2026-W04"] == {"prod": 0, "idle": 0, "off": 2}

    def test_ignora_instancias_de_outro_contrato(self):
        contrato = _contrato()
        inst_outro = _instancia(numero=1, contrato_id="contrato-outro")
        agregado = project_ocupacao_contrato_semanal(contrato, [inst_outro])
        assert agregado == {}

    def test_total_por_semana_igual_quantidade_contratada(self):
        contrato = _contrato(quantidade_contratada=2)
        instancias = [_instancia(numero=1), _instancia(numero=2)]
        agregado = project_ocupacao_contrato_semanal(contrato, instancias)
        for semana, bucket in agregado.items():
            assert sum(bucket.values()) == contrato.quantidade_contratada, semana
