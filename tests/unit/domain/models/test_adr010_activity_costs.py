"""Tests for ADR-010: Activity Cost Breakdown Models."""

from __future__ import annotations

from concilium.domain.models.canonical import (
    AtividadeCustoCompleto,
    AtividadeInsumo,
    CustoIndiretoAtividade,
    IndiretoAlocacao,
    InsumoComponenteAtividade,
    MobilizacaoAtividade,
)


class TestInsumoComponenteAtividade:
    def test_create(self):
        comp = InsumoComponenteAtividade(nome="MÃO DE OBRA", custo_total=9800.0)
        assert comp.custo_total == 9800.0

    def test_create_with_items(self):
        comp = InsumoComponenteAtividade(
            nome="EQUIPAMENTOS",
            itens=[{"equip": "Escavadeira 350", "custo": 4300.0}],
            custo_total=4300.0,
        )
        assert len(comp.itens) == 1


class TestAtividadeInsumo:
    def test_custo_total_direto(self):
        ins = AtividadeInsumo(
            categoria="Escavação",
            mao_de_obra=InsumoComponenteAtividade(nome="MO", custo_total=9800.0),
            equipamentos=InsumoComponenteAtividade(nome="EQ", custo_total=4300.0),
            material=InsumoComponenteAtividade(nome="MAT", custo_total=1500.0),
        )
        assert ins.custo_total_direto == 9800.0 + 4300.0 + 1500.0

    def test_custo_total_direto_partial(self):
        ins = AtividadeInsumo(
            categoria="Escavação",
            mao_de_obra=InsumoComponenteAtividade(nome="MO", custo_total=9800.0),
        )
        assert ins.custo_total_direto == 9800.0

    def test_no_components_zero(self):
        ins = AtividadeInsumo(categoria="Vazio")
        assert ins.custo_total_direto == 0.0


class TestIndiretoAlocacao:
    def test_estrategia_duracao(self):
        aloc = IndiretoAlocacao(estrategia="duracao", semanas_atividade=4, semanas_projeto=24)
        assert aloc.estrategia == "duracao"
        assert aloc.semanas_atividade == 4

    def test_estrategia_fator_explicito(self):
        aloc = IndiretoAlocacao(
            estrategia="fator_explicito",
            fator_top=0.10,
            fator_adm=0.25,
            fator_lab=0.30,
            fator_qsms=0.20,
        )
        assert aloc.fator_top + aloc.fator_adm + aloc.fator_lab + aloc.fator_qsms <= 1.0

    def test_estrategia_esforco_mo(self):
        aloc = IndiretoAlocacao(estrategia="esforco_mo", percentual_horas_mo=0.15)
        assert aloc.percentual_horas_mo == 0.15


class TestMobilizacaoAtividade:
    def test_custo_total(self):
        mob = MobilizacaoAtividade(
            atividade_id="ACT-01",
            fase="setup",
            mao_de_obra=InsumoComponenteAtividade(nome="MO", custo_total=3000.0),
            equipamentos=InsumoComponenteAtividade(nome="EQ", custo_total=2000.0),
            material=InsumoComponenteAtividade(nome="MAT", custo_total=1000.0),
        )
        assert mob.custo_total == 6000.0

    def test_alocacao_semana_inicio(self):
        mob = MobilizacaoAtividade(
            atividade_id="ACT-01",
            fase="setup",
            material=InsumoComponenteAtividade(nome="MAT", custo_total=6000.0),
            alocacao="semana_inicio",
        )
        result = mob.alocacao_por_semana(semana_inicio=2, semana_fim=6)
        assert result == {2: 6000.0}

    def test_alocacao_ambas_split(self):
        mob = MobilizacaoAtividade(
            atividade_id="ACT-01",
            fase="both",
            material=InsumoComponenteAtividade(nome="MAT", custo_total=6000.0),
            alocacao="ambas",
        )
        result = mob.alocacao_por_semana(semana_inicio=0, semana_fim=10)
        assert result[0] == 3000.0
        assert result[10] == 3000.0

    def test_alocacao_semana_fim(self):
        mob = MobilizacaoAtividade(
            atividade_id="ACT-01",
            fase="teardown",
            material=InsumoComponenteAtividade(nome="MAT", custo_total=4000.0),
            alocacao="semana_fim",
        )
        result = mob.alocacao_por_semana(semana_inicio=2, semana_fim=8)
        assert result == {8: 4000.0}


class TestCustoIndiretoAtividade:
    def test_custo_total_indireto_sums_all_categories(self):
        custo = CustoIndiretoAtividade(
            atividade_id="ACT-01",
            alocacao=IndiretoAlocacao(estrategia="duracao", semanas_atividade=4, semanas_projeto=24),
            custo_top_atribuido=100.0,
            custo_adm_atribuido=200.0,
            custo_lab_atribuido=50.0,
            custo_qsms_atribuido=25.0,
        )
        assert custo.custo_total_indireto == 375.0

    def test_custo_total_indireto_defaults_to_zero(self):
        custo = CustoIndiretoAtividade(
            atividade_id="ACT-01",
            alocacao=IndiretoAlocacao(estrategia="duracao", semanas_atividade=4, semanas_projeto=24),
        )
        assert custo.custo_total_indireto == 0.0


class TestAtividadeCustoCompleto:
    def test_duracao_semanas(self):
        act = AtividadeCustoCompleto(atividade_id="A", semana_inicio=2, semana_fim=6)
        assert act.duracao_semanas == 5

    def test_custo_direto_total(self):
        act = AtividadeCustoCompleto(
            atividade_id="A",
            semana_inicio=0,
            semana_fim=3,
            custos_diretos=[
                AtividadeInsumo(
                    categoria="Esc",
                    mao_de_obra=InsumoComponenteAtividade(nome="MO", custo_total=9800.0),
                    equipamentos=InsumoComponenteAtividade(nome="EQ", custo_total=4300.0),
                )
            ],
        )
        assert act.custo_direto_total == 9800.0 + 4300.0

    def test_custo_total_atividade(self):
        act = AtividadeCustoCompleto(
            atividade_id="A",
            semana_inicio=0,
            semana_fim=3,
            custos_diretos=[
                AtividadeInsumo(
                    categoria="Esc",
                    mao_de_obra=InsumoComponenteAtividade(nome="MO", custo_total=15600.0),
                )
            ],
            custo_indireto_atribuido=5000.0,
            mobilizacao=MobilizacaoAtividade(
                atividade_id="A",
                fase="setup",
                material=InsumoComponenteAtividade(nome="MAT", custo_total=6000.0),
            ),
        )
        assert act.custo_total_atividade == 15600.0 + 5000.0 + 6000.0
