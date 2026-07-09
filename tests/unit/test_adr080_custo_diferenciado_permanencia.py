"""ADR-080: Custo Diferenciado de Permanência — Mobilização Tardia por Instância,
Taxa Ociosa por Componente e Desmobilização Antecipada Efetiva.

Testa:
  A. InstanciaRecurso.desmob_antecipada_aplicada campo presente
  B. RecursoContrato.mobilizacao_por_instancia campo presente
  C. Custo do contrato com idle rate diferenciado (c_idle < c_unit para standby)
  D. Desmob antecipada efetiva reduz custo_total_contrato
  E. Mobilização tardia: instâncias contratadas apenas da primeira semana ativa
  F. Compatibilidade retroativa: sem resource_costs → comportamento do ADR-079
"""

from __future__ import annotations

import sys

import pytest

from concilium.application.skills import run_equipes_e_alocacao as _trigger_skill05_load

assert _trigger_skill05_load
_skill05_helpers = sys.modules["_concilium_skillpkg_05_equipes_e_alocacao._skill_helpers"]

# ─────────────────────────────────────────────────────────────────────────────
# A. Novos campos de modelo
# ─────────────────────────────────────────────────────────────────────────────


class TestNovosCamposModelo:
    def _inst(self, **kwargs):
        from concilium.domain.models.canonical import InstanciaRecurso

        defaults = dict(
            instancia_id="ATERRO-04",
            contrato_id="contrato-aterro",
            tipo_id="ATERRO",
            numero=4,
            semana_entrada="2026-W23",
            semana_saida="2027-W21",
        )
        return InstanciaRecurso(**{**defaults, **kwargs})

    def test_instancia_recurso_tem_desmob_antecipada_aplicada(self):
        inst = self._inst(
            semanas_ativas=6,
            semanas_standby=43,
            taxa_utilizacao_pct=12.2,
            custo_standby=322500.0,
            atividades_cobertas=["eap-1_10"],
        )
        assert hasattr(inst, "desmob_antecipada_aplicada")
        assert inst.desmob_antecipada_aplicada is False

    def test_instancia_recurso_desmob_aplicada_pode_ser_true(self):
        inst = self._inst(
            semanas_ativas=37,
            semanas_standby=11,
            taxa_utilizacao_pct=77.1,
            custo_standby=132000.0,
            atividades_cobertas=["eap-1_5", "eap-1_6"],
            desmob_antecipada_aplicada=True,
        )
        assert inst.desmob_antecipada_aplicada is True

    def test_recurso_contrato_tem_mobilizacao_por_instancia(self):
        from concilium.domain.models.canonical import RecursoContrato

        rc = RecursoContrato(
            contrato_id="contrato-aterro",
            tipo_id="ATERRO",
            quantidade_contratada=4,
            semana_inicio="2026-W23",
            semana_fim="2027-W21",
            semanas_contrato=49,
            custo_unit_semanal=150000.0,
            custo_total_contrato=29400000.0,
            items_cobertos=["eap-1_7", "eap-1_8", "eap-1_10"],
        )
        # Campo mobilizacao_por_instancia deve existir com default {}
        assert hasattr(rc, "mobilizacao_por_instancia")
        assert isinstance(rc.mobilizacao_por_instancia, dict)

    def test_recurso_contrato_mobilizacao_por_instancia_preenchido(self):
        from concilium.domain.models.canonical import RecursoContrato

        rc = RecursoContrato(
            contrato_id="contrato-aterro",
            tipo_id="ATERRO",
            quantidade_contratada=4,
            semana_inicio="2026-W23",
            semana_fim="2027-W21",
            semanas_contrato=49,
            custo_unit_semanal=150000.0,
            custo_total_contrato=29400000.0,
            items_cobertos=["eap-1_7"],
            mobilizacao_por_instancia={
                1: "2026-W23",  # ATERRO-01: contrato desde o início
                2: "2026-W23",
                3: "2026-W23",
                4: "2027-W07",  # ATERRO-04: mobilização tardia (semana 36)
            },
        )
        assert rc.mobilizacao_por_instancia[4] == "2027-W07"


# ─────────────────────────────────────────────────────────────────────────────
# B. Cálculo de custo com idle rate diferenciado
# ─────────────────────────────────────────────────────────────────────────────


class TestIdleRateDiferenciado:
    """O custo do contrato usa c_idle para standby e c_unit para ativo."""

    def test_custo_sem_standby_usa_taxa_plena(self):
        """Quando não há standby, custo = c_unit × active_weeks × n_units."""
        calcular_custo_contrato_por_instancia = _skill05_helpers.calcular_custo_contrato_por_instancia

        # Instância com 10 semanas ativas, 0 standby
        custo = calcular_custo_contrato_por_instancia(
            active_weeks=10,
            standby_weeks=0,
            custo_unit_semanal=10000.0,
            custo_idle_semanal=0.0,
            custo_mob=5000.0,
            custo_demob=2500.0,
        )
        # custo = 10000 × 10 + 5000 + 2500 = 107500
        assert custo == pytest.approx(107500.0)

    def test_custo_com_standby_usa_idle_quando_disponivel(self):
        """Standby cobrado a c_idle (menor) quando disponível."""
        calcular_custo_contrato_por_instancia = _skill05_helpers.calcular_custo_contrato_por_instancia

        custo = calcular_custo_contrato_por_instancia(
            active_weeks=10,
            standby_weeks=5,
            custo_unit_semanal=10000.0,
            custo_idle_semanal=2000.0,  # 20% da taxa ativa
            custo_mob=5000.0,
            custo_demob=2500.0,
        )
        # custo = 10000×10 + 2000×5 + 5000 + 2500 = 117500
        assert custo == pytest.approx(117500.0)

    def test_custo_standby_sem_idle_usa_taxa_plena(self):
        """Fallback: quando c_idle=0, standby usa c_unit (comportamento legado)."""
        calcular_custo_contrato_por_instancia = _skill05_helpers.calcular_custo_contrato_por_instancia

        custo_idle = calcular_custo_contrato_por_instancia(
            active_weeks=10,
            standby_weeks=5,
            custo_unit_semanal=10000.0,
            custo_idle_semanal=0.0,  # sem custo_idle definido
            custo_mob=5000.0,
            custo_demob=2500.0,
        )
        custo_pleno = calcular_custo_contrato_por_instancia(
            active_weeks=10,
            standby_weeks=5,
            custo_unit_semanal=10000.0,
            custo_idle_semanal=10000.0,  # igual à taxa plena
            custo_mob=5000.0,
            custo_demob=2500.0,
        )
        # Fallback (c_idle=0) deve dar mesmo resultado que c_idle=c_unit
        assert custo_idle == pytest.approx(custo_pleno)

    def test_c_idle_menor_que_c_unit_reduz_custo_total(self):
        """Usar c_idle < c_unit reduz o custo comparado ao modelo legado (c_unit para tudo)."""
        calcular_custo_contrato_por_instancia = _skill05_helpers.calcular_custo_contrato_por_instancia

        custo_novo = calcular_custo_contrato_por_instancia(
            active_weeks=35,
            standby_weeks=14,
            custo_unit_semanal=150000.0,
            custo_idle_semanal=30000.0,  # 20% da taxa ativa
            custo_mob=50000.0,
            custo_demob=25000.0,
        )
        custo_legado = calcular_custo_contrato_por_instancia(
            active_weeks=35,
            standby_weeks=14,
            custo_unit_semanal=150000.0,
            custo_idle_semanal=150000.0,  # usa taxa plena para standby (legado)
            custo_mob=50000.0,
            custo_demob=25000.0,
        )
        assert custo_novo < custo_legado


# ─────────────────────────────────────────────────────────────────────────────
# C. Desmobilização antecipada efetiva reduz custo
# ─────────────────────────────────────────────────────────────────────────────


class TestDesmobEfetivaReduzCusto:
    def test_desmob_elimina_trailing_standby(self):
        """Com early demob, trailing standby é substituído por custo de desmob."""
        calcular_custo_contrato_por_instancia = _skill05_helpers.calcular_custo_contrato_por_instancia

        # Sem early demob: 35 ativas + 43 trailing standby
        custo_sem_desmob = calcular_custo_contrato_por_instancia(
            active_weeks=6,
            standby_weeks=43,  # ATERRO-04 no AGIS
            custo_unit_semanal=150000.0,
            custo_idle_semanal=7500.0,
            custo_mob=50000.0,
            custo_demob=0.0,  # sem desmob explícita
        )

        # Com early demob: 6 ativas, 0 trailing standby, + c_demob
        custo_com_desmob = calcular_custo_contrato_por_instancia(
            active_weeks=6,
            standby_weeks=0,  # trailing eliminado
            custo_unit_semanal=150000.0,
            custo_idle_semanal=7500.0,
            custo_mob=50000.0,
            custo_demob=25000.0,  # paga desmob ao liberar cedo
        )

        # Com desmob antecipada deve ser mais barato
        assert custo_com_desmob < custo_sem_desmob

    def test_desmob_so_vale_quando_economia_positiva(self):
        """A economia líquida de early demob = c_idle×trailing - c_demob > 0."""
        c_idle = 7500.0
        c_demob = 25000.0
        trailing_weeks = 43
        economia = c_idle * trailing_weeks - c_demob
        assert economia > 0  # 322500 - 25000 = 297500 > 0

    def test_desmob_nao_aplicada_quando_economia_negativa(self):
        """Se trailing_weeks pequeno, early demob pode custar mais que manter idle."""
        c_idle = 7500.0
        c_demob = 25000.0
        trailing_weeks = 2  # só 2 semanas = R$15k economia, mas c_demob = R$25k
        economia = c_idle * trailing_weeks - c_demob
        assert economia < 0  # não vale a pena


# ─────────────────────────────────────────────────────────────────────────────
# D. Mobilização tardia — instâncias contratadas da primeira semana ativa
# ─────────────────────────────────────────────────────────────────────────────


class TestMobilizacaoTardia:
    def test_instancia_tardia_tem_menos_semanas_de_contrato(self):
        """Uma instância mobilizada na semana 36 (não na 1) tem contrato menor."""
        calcular_custo_contrato_por_instancia = _skill05_helpers.calcular_custo_contrato_por_instancia

        # ATERRO-04 no AGIS iter-3: mobilizada semana 36, dura até semana 41 (6 semanas)
        custo_tardio = calcular_custo_contrato_por_instancia(
            active_weeks=6,
            standby_weeks=0,  # sem standby com mobilização tardia
            custo_unit_semanal=150000.0,
            custo_idle_semanal=7500.0,
            custo_mob=50000.0,
            custo_demob=25000.0,
        )
        # ATERRO-04 no baseline: mobilizada semana 1, 6 ativas + 43 standby
        custo_desde_inicio = calcular_custo_contrato_por_instancia(
            active_weeks=6,
            standby_weeks=43,
            custo_unit_semanal=150000.0,
            custo_idle_semanal=7500.0,
            custo_mob=50000.0,
            custo_demob=0.0,
        )
        assert custo_tardio < custo_desde_inicio

    def test_reducao_custo_mob_tardia_agis_aterro04(self):
        """Economia estimada com mob tardia de ATERRO-04: ~R$297k (43 semanas × R$7500 - R$25k demob)."""
        calcular_custo_contrato_por_instancia = _skill05_helpers.calcular_custo_contrato_por_instancia

        custo_baseline = calcular_custo_contrato_por_instancia(
            active_weeks=6,
            standby_weeks=43,
            custo_unit_semanal=150000.0,
            custo_idle_semanal=7500.0,
            custo_mob=50000.0,
            custo_demob=0.0,
        )
        custo_otimizado = calcular_custo_contrato_por_instancia(
            active_weeks=6,
            standby_weeks=0,
            custo_unit_semanal=150000.0,
            custo_idle_semanal=7500.0,
            custo_mob=50000.0,
            custo_demob=25000.0,
        )
        economia = custo_baseline - custo_otimizado
        # 43 × 7500 - 25000 = 322500 - 25000 = 297500
        assert economia == pytest.approx(297500.0)


# ─────────────────────────────────────────────────────────────────────────────
# E. Compatibilidade retroativa
# ─────────────────────────────────────────────────────────────────────────────


class TestCompatibilidadeRetroativa080:
    def test_sem_c_idle_comportamento_identico_ao_anterior(self):
        """Sem c_idle, custo = c_unit × (active + standby) + mob + demob."""
        calcular_custo_contrato_por_instancia = _skill05_helpers.calcular_custo_contrato_por_instancia

        custo = calcular_custo_contrato_por_instancia(
            active_weeks=10,
            standby_weeks=5,
            custo_unit_semanal=10000.0,
            custo_idle_semanal=0.0,  # legado: sem idle separado
            custo_mob=0.0,
            custo_demob=0.0,
        )
        # Legado: 10000 × (10 + 5) = 150000
        assert custo == pytest.approx(150000.0)

    def test_campo_desmob_aplicada_default_false(self):
        from concilium.domain.models.canonical import InstanciaRecurso

        inst = InstanciaRecurso(
            instancia_id="X-01",
            contrato_id="c",
            tipo_id="X",
            numero=1,
            semana_entrada="2026-W01",
            semana_saida="2026-W10",
        )
        assert inst.desmob_antecipada_aplicada is False

    def test_campo_mobilizacao_contrato_default_vazio(self):
        from concilium.domain.models.canonical import RecursoContrato

        rc = RecursoContrato(
            contrato_id="c",
            tipo_id="X",
            quantidade_contratada=1,
            semana_inicio="2026-W01",
            semana_fim="2026-W10",
            semanas_contrato=10,
            custo_unit_semanal=1000.0,
            custo_total_contrato=10000.0,
            items_cobertos=[],
        )
        assert rc.mobilizacao_por_instancia == {}
