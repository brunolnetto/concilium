"""ADR-128 F6 — Testes unitários para os modelos canônicos de contabilização de consumíveis.

Cobre:
- TestDisponibilidadeConsumivelCanonicalModel — validação do modelo Pydantic
- TestRecursoConsumivelCanonicalModel         — validação do modelo Pydantic
- TestResumoEstoqueConsumivelModel            — validação do modelo Pydantic + defaults
- TestCanonicalModelCampos                    — CanonicalModel aceita os novos campos, default vazio
"""

from __future__ import annotations

from concilium.domain.models.canonical import (
    CanonicalModel,
    DisponibilidadeConsumivelCanonical,
    RecursoConsumivelCanonical,
    ResumoEstoqueConsumivel,
)


class TestDisponibilidadeConsumivelCanonicalModel:
    def test_defaults_sao_irrestrito(self):
        d = DisponibilidadeConsumivelCanonical()
        assert d.capacidade_armazenamento is None
        assert d.estoque_inicial == 0.0
        assert d.taxa_reabastecimento_max is None
        assert d.lead_time_reabastecimento_dias is None

    def test_aceita_todos_os_campos(self):
        d = DisponibilidadeConsumivelCanonical(
            capacidade_armazenamento=15000.0,
            estoque_inicial=5000.0,
            taxa_reabastecimento_max=3000.0,
            lead_time_reabastecimento_dias=2.0,
        )
        assert d.capacidade_armazenamento == 15000.0
        assert d.estoque_inicial == 5000.0
        assert d.taxa_reabastecimento_max == 3000.0
        assert d.lead_time_reabastecimento_dias == 2.0

    def test_extra_ignorado(self):
        d = DisponibilidadeConsumivelCanonical.model_validate({"estoque_inicial": 1.0, "campo_futuro": "x"})
        assert d.estoque_inicial == 1.0


class TestRecursoConsumivelCanonicalModel:
    def test_construcao_minima(self):
        r = RecursoConsumivelCanonical(
            resource_id="MA-DIESEL-S10", disponibilidade=DisponibilidadeConsumivelCanonical()
        )
        assert r.resource_id == "MA-DIESEL-S10"
        assert r.consumo_por_semana == {}
        assert r.producao_por_semana == {}

    def test_construcao_com_fluxos(self):
        r = RecursoConsumivelCanonical(
            resource_id="MA-SOLO-3CAT",
            disponibilidade=DisponibilidadeConsumivelCanonical(estoque_inicial=0.0),
            consumo_por_semana={"aterro": 8000.0},
            producao_por_semana={"corte": 4000.0},
        )
        assert r.consumo_por_semana == {"aterro": 8000.0}
        assert r.producao_por_semana == {"corte": 4000.0}

    def test_disponibilidade_aceita_dict_cru_via_model_validate(self):
        r = RecursoConsumivelCanonical.model_validate(
            {"resource_id": "MA-DIESEL-S10", "disponibilidade": {"estoque_inicial": 100.0}}
        )
        assert isinstance(r.disponibilidade, DisponibilidadeConsumivelCanonical)
        assert r.disponibilidade.estoque_inicial == 100.0


class TestResumoEstoqueConsumivelModel:
    def test_construcao_minima_status_default_ok(self):
        r = ResumoEstoqueConsumivel(
            resource_id="MA-DIESEL-S10",
            estoque_inicial=0.0,
            estoque_medio=50.0,
            estoque_minimo=10.0,
            estoque_final=20.0,
        )
        assert r.status_estoque == "OK"
        assert r.overflow_total == 0.0
        assert r.delay_total_semanas == 0
        assert r.n_atividades_atrasadas == 0

    def test_status_critico_explicito(self):
        r = ResumoEstoqueConsumivel(
            resource_id="MA-DIESEL-S10",
            estoque_inicial=0.0,
            estoque_medio=-5.0,
            estoque_minimo=-25.0,
            estoque_final=-10.0,
            status_estoque="CRITICO",
        )
        assert r.status_estoque == "CRITICO"
        assert r.estoque_minimo < 0

    def test_status_aviso_explicito_com_delay(self):
        r = ResumoEstoqueConsumivel(
            resource_id="MA-DIESEL-S10",
            estoque_inicial=0.0,
            estoque_medio=20.0,
            estoque_minimo=0.0,
            estoque_final=30.0,
            delay_total_semanas=3,
            n_atividades_atrasadas=1,
            status_estoque="AVISO",
        )
        assert r.status_estoque == "AVISO"
        assert r.delay_total_semanas == 3


class TestCanonicalModelCampos:
    def test_default_vazio(self):
        c = CanonicalModel.model_construct()
        assert c.recursos_consumiveis == []
        assert c.resumo_estoque_consumiveis == []

    def test_aceita_listas_povoadas(self):
        c = CanonicalModel.model_construct(
            recursos_consumiveis=[
                RecursoConsumivelCanonical(
                    resource_id="MA-DIESEL-S10", disponibilidade=DisponibilidadeConsumivelCanonical()
                )
            ],
            resumo_estoque_consumiveis=[
                ResumoEstoqueConsumivel(
                    resource_id="MA-DIESEL-S10",
                    estoque_inicial=0.0,
                    estoque_medio=1.0,
                    estoque_minimo=1.0,
                    estoque_final=1.0,
                )
            ],
        )
        assert len(c.recursos_consumiveis) == 1
        assert len(c.resumo_estoque_consumiveis) == 1
