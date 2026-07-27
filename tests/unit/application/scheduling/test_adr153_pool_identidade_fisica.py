"""ADR-153 F1 — Identidade Física de Recurso: Anotação Declarativa de Segmento: TDD.

Cobre:
  - `SegmentoAtividade.identidade_fisica_id`: campo opcional, default None (regressão zero).
  - `atribuir_identidade_fisica_segmentos`: enriquece segmentos_atividade a partir de uma
    declaração externa {(instancia_id, semana_inicio): identidade_fisica_id}, sem tocar
    o solver, a atribuição de slots (ADR-077) ou a cadeia de custo.

Escrito antes da implementação (red phase). Puramente aditivo — nenhuma mudança em
_build_instancias_recurso/_assign_instances/CP-SAT.
"""

from __future__ import annotations

from concilium.application.scheduling.pool_identidade_fisica import (
    atribuir_identidade_fisica_segmentos,
)
from concilium.domain.models.canonical import InstanciaRecurso, SegmentoAtividade


def _instancia(numero: int = 1, **overrides) -> InstanciaRecurso:
    defaults = dict(
        instancia_id=f"ESC-3CAT-{numero:02d}",
        contrato_id="contrato-esc-3cat",
        tipo_id="ESC-3CAT",
        numero=numero,
        semana_entrada="2026-W01",
        semana_saida="2026-W04",
    )
    defaults.update(overrides)
    return InstanciaRecurso(**defaults)


class TestSegmentoAtividadeIdentidadeFisicaDefault:
    def test_default_e_none(self):
        seg = SegmentoAtividade(activity_id="eap-1", semana_inicio="2026-W01", semana_fim="2026-W01")
        assert seg.identidade_fisica_id is None


class TestAtribuirIdentidadeFisicaSegmentos:
    def test_aplica_rotulo_ao_segmento_correspondente(self):
        instancia = _instancia(
            segmentos_atividade=[
                SegmentoAtividade(activity_id="eap-1", semana_inicio="2026-W01", semana_fim="2026-W02"),
            ]
        )
        resultado = atribuir_identidade_fisica_segmentos(
            [instancia], {("ESC-3CAT-01", "2026-W01"): "PLACA-1234"}
        )
        assert resultado[0].segmentos_atividade[0].identidade_fisica_id == "PLACA-1234"

    def test_segmento_sem_atribuicao_mantem_none(self):
        instancia = _instancia(
            segmentos_atividade=[
                SegmentoAtividade(activity_id="eap-1", semana_inicio="2026-W01", semana_fim="2026-W02"),
            ]
        )
        resultado = atribuir_identidade_fisica_segmentos([instancia], {})
        assert resultado[0].segmentos_atividade[0].identidade_fisica_id is None

    def test_chave_sem_correspondencia_e_ignorada_silenciosamente(self):
        instancia = _instancia(
            segmentos_atividade=[
                SegmentoAtividade(activity_id="eap-1", semana_inicio="2026-W01", semana_fim="2026-W02"),
            ]
        )
        resultado = atribuir_identidade_fisica_segmentos(
            [instancia], {("ESC-3CAT-99", "2026-W01"): "PLACA-9999"}
        )
        assert resultado[0].segmentos_atividade[0].identidade_fisica_id is None

    def test_nao_muta_instancias_originais(self):
        instancia = _instancia(
            segmentos_atividade=[
                SegmentoAtividade(activity_id="eap-1", semana_inicio="2026-W01", semana_fim="2026-W02"),
            ]
        )
        atribuir_identidade_fisica_segmentos([instancia], {("ESC-3CAT-01", "2026-W01"): "PLACA-1234"})
        assert instancia.segmentos_atividade[0].identidade_fisica_id is None

    def test_multiplos_segmentos_recebem_rotulos_independentes(self):
        instancia = _instancia(
            segmentos_atividade=[
                SegmentoAtividade(activity_id="eap-1", semana_inicio="2026-W01", semana_fim="2026-W01"),
                SegmentoAtividade(activity_id="eap-2", semana_inicio="2026-W03", semana_fim="2026-W04"),
            ]
        )
        resultado = atribuir_identidade_fisica_segmentos(
            [instancia],
            {
                ("ESC-3CAT-01", "2026-W01"): "PLACA-1234",
                ("ESC-3CAT-01", "2026-W03"): "PLACA-5678",
            },
        )
        segs = resultado[0].segmentos_atividade
        assert segs[0].identidade_fisica_id == "PLACA-1234"
        assert segs[1].identidade_fisica_id == "PLACA-5678"

    def test_multiplas_instancias_resolvidas_independentemente(self):
        inst1 = _instancia(
            numero=1,
            segmentos_atividade=[
                SegmentoAtividade(activity_id="eap-1", semana_inicio="2026-W01", semana_fim="2026-W01"),
            ],
        )
        inst2 = _instancia(
            numero=2,
            segmentos_atividade=[
                SegmentoAtividade(activity_id="eap-1", semana_inicio="2026-W01", semana_fim="2026-W01"),
            ],
        )
        resultado = atribuir_identidade_fisica_segmentos(
            [inst1, inst2], {("ESC-3CAT-02", "2026-W01"): "PLACA-5678"}
        )
        assert resultado[0].segmentos_atividade[0].identidade_fisica_id is None
        assert resultado[1].segmentos_atividade[0].identidade_fisica_id == "PLACA-5678"
