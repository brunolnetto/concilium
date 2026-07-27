"""ADR-160 D3 — gerar_timeline_real_instancias: TDD.

Compõe ADR-152 (project_ocupacao_semanal) + ADR-154/155 (roster real,
transiente) + ADR-156/157 (substituição segura, usada só como taxa "sombra") +
ADR-158 (custo real por instância). Retorna None quando o roster não cobre a
composição — nunca mistura número real parcial com calibrado. Nada é
persistido: o RecursoContrato original nunca é mutado nem salvo.

Escrito antes da implementação (red phase).
"""

from __future__ import annotations

from datetime import date

from concilium.application.scheduling.cubo_pool_real import gerar_timeline_real_instancias
from concilium.domain.models.canonical import (
    InstanciaRecurso,
    MembroEquipeReal,
    RecursoContrato,
    SegmentoAtividade,
)


def _contrato(**overrides) -> RecursoContrato:
    defaults = dict(
        contrato_id="contrato-esc-3cat",
        tipo_id="ESC-3CAT",
        quantidade_contratada=1,
        semana_inicio="2026-W01",
        semana_fim="2026-W04",
        semanas_contrato=4,
        custo_unit_semanal=1000.0,
        custo_total_contrato=4000.0,
        custo_unit_semanal_mo=600.0,
        custo_unit_semanal_eq=300.0,
        composicao_funcoes_mo={"MO-OPER-ESCAV": 1},
    )
    defaults.update(overrides)
    return RecursoContrato(**defaults)


def _instancia(numero: int = 1, **overrides) -> InstanciaRecurso:
    defaults = dict(
        instancia_id=f"ESC-3CAT-{numero:02d}",
        contrato_id="contrato-esc-3cat",
        tipo_id="ESC-3CAT",
        numero=numero,
        semana_entrada="2026-W01",
        semana_saida="2026-W04",
        segmentos_atividade=[
            SegmentoAtividade(activity_id="eap-1", semana_inicio="2026-W01", semana_fim="2026-W04")
        ],
    )
    defaults.update(overrides)
    return InstanciaRecurso(**defaults)


def _membro(**overrides) -> MembroEquipeReal:
    defaults = dict(
        individuo_id="joao-001",
        funcao_id="MO-OPER-ESCAV",
        salario_base_mensal=3000.0,
        categoria_sindical="horista",
        data_admissao=date(2026, 1, 1),
    )
    defaults.update(overrides)
    return MembroEquipeReal(**defaults)


class TestGerarTimelineRealInstancias:
    def test_retorna_none_quando_roster_mo_nao_cobre(self):
        contrato = _contrato(composicao_funcoes_mo={"MO-OPER-ESCAV": 2})  # precisa de 2
        instancia = _instancia()
        membro = _membro()  # só 1
        resultado = gerar_timeline_real_instancias(contrato, [instancia], [membro], [])
        assert resultado is None

    def test_retorna_timeline_quando_cobertura_e_suficiente(self):
        contrato = _contrato()
        instancia = _instancia()
        membro = _membro()
        resultado = gerar_timeline_real_instancias(contrato, [instancia], [membro], [])
        assert resultado is not None
        assert "ESC-3CAT-01" in resultado
        assert all(v >= 0 for v in resultado["ESC-3CAT-01"].values())

    def test_nao_muta_contrato_original(self):
        contrato = _contrato()
        instancia = _instancia()
        membro = _membro()
        gerar_timeline_real_instancias(contrato, [instancia], [membro], [])
        assert contrato.custo_unit_semanal_mo == 600.0

    def test_apenas_instancias_do_contrato_sao_incluidas(self):
        contrato = _contrato()
        inst_deste = _instancia(numero=1)
        inst_de_outro = _instancia(numero=2, contrato_id="outro-contrato")
        membro = _membro()
        resultado = gerar_timeline_real_instancias(contrato, [inst_deste, inst_de_outro], [membro], [])
        assert resultado is not None
        assert set(resultado.keys()) == {"ESC-3CAT-01"}

    def test_composicao_vazia_usa_taxa_calibrada_sem_falhar(self):
        # Sem composicao_funcoes_mo/eq declaradas, não há o que cobrir — segue
        # com a taxa calibrada do contrato em vez de None.
        contrato = _contrato(composicao_funcoes_mo={})
        instancia = _instancia()
        resultado = gerar_timeline_real_instancias(contrato, [instancia], [], [])
        assert resultado is not None
