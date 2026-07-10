"""ADR-085: Custo Instancial Composicional Temporal.

Testa:
  A. Modelo: campos novos em InstanciaRecurso / CustoParticionadoItem / RecursoContrato
  B. Helper composicional: custo ativo (todos) + idle (MO integral + EQ reduzida) + demob
  C. Decomposição da taxa unitária por componente em _build_contratos_recurso
  D. Custo instancial substitui fórmula monolítica + mob tardia + desmob efetiva
  E. Invariante categorial: Σ custo_inst_cat == custo_total_particionado
  F. Retrocompatibilidade: sem c_idle → fórmula monolítica preservada
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest


def _load_helpers_a():
    """Carrega o módulo _skill_helpers (dir com hífen → importlib)."""
    here = Path(__file__).resolve().parents[2]
    path = (
        here
        / "src"
        / "concilium"
        / "application"
        / "skills"
        / "manifests"
        / "05-equipes-e-alocacao"
        / "_skill_helpers"
        / "__init__.py"
    )
    spec = importlib.util.spec_from_file_location("skill05_helpers_a_test", path)
    mod = importlib.util.module_from_spec(spec)
    sys.modules["skill05_helpers_a_test"] = mod
    spec.loader.exec_module(mod)
    return mod


calcular_custo_instancia_composicional = _load_helpers_a().calcular_custo_instancia_composicional

# ─────────────────────────────────────────────────────────────────────────────
# A. Novos campos de modelo
# ─────────────────────────────────────────────────────────────────────────────


class TestNovosCamposModelo085:
    def test_instancia_tem_campos_composicionais(self):
        from concilium.domain.models.canonical import InstanciaRecurso

        inst = InstanciaRecurso(
            instancia_id="X-01",
            contrato_id="c",
            tipo_id="X",
            numero=1,
            semana_entrada="2026-W01",
            semana_saida="2026-W10",
        )
        for campo in (
            "semana_mobilizacao",
            "semana_desmobilizacao",
            "semanas_off",
            "custo_ativo_mo",
            "custo_ativo_eq",
            "custo_ativo_comb",
            "custo_ativo_mat",
            "custo_idle_mo",
            "custo_idle_eq",
            "custo_demob_instancia",
            "custo_instancia_total",
        ):
            assert hasattr(inst, campo)
        assert inst.custo_instancia_total == 0.0
        assert inst.semana_mobilizacao == ""

    def test_particao_tem_campos_categoriais(self):
        from concilium.domain.models.canonical import CustoParticionadoItem

        p = CustoParticionadoItem(item_id="a")
        for campo in ("custo_inst_mo", "custo_inst_eq", "custo_inst_comb", "custo_inst_mat"):
            assert hasattr(p, campo)

    def test_contrato_tem_taxas_por_componente(self):
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
        )
        for campo in (
            "custo_unit_semanal_mo",
            "custo_unit_semanal_eq",
            "custo_unit_semanal_comb",
            "custo_unit_semanal_mat",
            "rho_idle_eq",
        ):
            assert hasattr(rc, campo)
        assert rc.rho_idle_eq == 1.0


# ─────────────────────────────────────────────────────────────────────────────
# B. Helper composicional
# ─────────────────────────────────────────────────────────────────────────────


class TestHelperComposicional:
    def test_ativo_cobra_todos_componentes(self):
        cc = calcular_custo_instancia_composicional(
            prod_weeks=10,
            idle_weeks=0,
            c_mo=1000.0,
            c_eq=400.0,
            c_comb=200.0,
            c_mat=100.0,
            c_idle_eq=80.0,
        )
        # 10 × (1000+400+200+100) = 17000
        assert cc["total"] == pytest.approx(17000.0)
        assert cc["ativo_mo"] == pytest.approx(10000.0)
        assert cc["idle_mo"] == 0.0

    def test_idle_mantem_mo_integral_e_reduz_eq(self):
        cc = calcular_custo_instancia_composicional(
            prod_weeks=0,
            idle_weeks=5,
            c_mo=1000.0,
            c_eq=400.0,
            c_comb=200.0,
            c_mat=100.0,
            c_idle_eq=80.0,  # 20% de c_eq
        )
        # idle: MO integral (5×1000) + EQ reduzida (5×80); comb/mat zero
        assert cc["idle_mo"] == pytest.approx(5000.0)
        assert cc["idle_eq"] == pytest.approx(400.0)
        assert cc["total"] == pytest.approx(5400.0)

    def test_combustivel_e_material_zerados_no_idle(self):
        cc = calcular_custo_instancia_composicional(
            prod_weeks=0,
            idle_weeks=8,
            c_mo=0.0,
            c_eq=0.0,
            c_comb=500.0,
            c_mat=300.0,
            c_idle_eq=0.0,
        )
        assert cc["total"] == 0.0  # sem operação → comb/mat não incorrem

    def test_demob_efetivo_somado(self):
        cc = calcular_custo_instancia_composicional(
            prod_weeks=6,
            idle_weeks=0,
            c_mo=1000.0,
            c_eq=400.0,
            c_comb=0.0,
            c_mat=0.0,
            c_idle_eq=80.0,
            c_demob_efetivo=2500.0,
        )
        # 6×1400 + 2500 = 10900
        assert cc["total"] == pytest.approx(10900.0)
        assert cc["demob"] == pytest.approx(2500.0)

    def test_mob_efetivo_somado(self):
        """ADR-136 F3: mobilização é custo de evento de entrada, somado ao total."""
        cc = calcular_custo_instancia_composicional(
            prod_weeks=6,
            idle_weeks=0,
            c_mo=1000.0,
            c_eq=400.0,
            c_comb=0.0,
            c_mat=0.0,
            c_idle_eq=80.0,
            c_mob_efetivo=1800.0,
        )
        # 6×1400 + 1800 = 10200
        assert cc["total"] == pytest.approx(10200.0)
        assert cc["mob"] == pytest.approx(1800.0)

    def test_mob_e_demob_efetivos_somados_juntos(self):
        """ADR-136 F3: mob e demob são termos independentes, ambos somados ao total."""
        cc = calcular_custo_instancia_composicional(
            prod_weeks=6,
            idle_weeks=0,
            c_mo=1000.0,
            c_eq=400.0,
            c_comb=0.0,
            c_mat=0.0,
            c_idle_eq=80.0,
            c_mob_efetivo=1800.0,
            c_demob_efetivo=2500.0,
        )
        # 6×1400 + 1800 + 2500 = 12700
        assert cc["total"] == pytest.approx(12700.0)
        assert cc["mob"] == pytest.approx(1800.0)
        assert cc["demob"] == pytest.approx(2500.0)

    def test_mob_default_zero_retrocompat(self):
        """Sem c_mob_efetivo (retrocompat), total permanece sem termo de mobilização."""
        cc = calcular_custo_instancia_composicional(
            prod_weeks=6,
            idle_weeks=0,
            c_mo=1000.0,
            c_eq=400.0,
            c_comb=0.0,
            c_mat=0.0,
            c_idle_eq=80.0,
        )
        assert cc["mob"] == 0.0
        assert cc["total"] == pytest.approx(6 * 1400.0)

    def test_idle_mais_barato_que_ativo_quando_eq_reduzida(self):
        ativo = calcular_custo_instancia_composicional(
            prod_weeks=1,
            idle_weeks=0,
            c_mo=1000.0,
            c_eq=400.0,
            c_comb=200.0,
            c_mat=100.0,
            c_idle_eq=80.0,
        )
        idle = calcular_custo_instancia_composicional(
            prod_weeks=0,
            idle_weeks=1,
            c_mo=1000.0,
            c_eq=400.0,
            c_comb=200.0,
            c_mat=100.0,
            c_idle_eq=80.0,
        )
        assert idle["total"] < ativo["total"]
        # diferença = c_eq economizado em EQ + comb + mat = (400-80)+200+100 = 620
        assert ativo["total"] - idle["total"] == pytest.approx(620.0)


# ─────────────────────────────────────────────────────────────────────────────
# C/D/E/F. Pipeline integrado: _build_contratos_recurso + _build_instancias + reconciliação
# ─────────────────────────────────────────────────────────────────────────────


class TestComputeInstanciaLifecycleMobDemob:
    """ADR-136 F3: _compute_instancia_lifecycle deixa de hardcodar custo de mob/demob em 0.0.

    Reproduz diretamente o bug documentado no ADR-136: o campo `custo_mob_instancia`
    nunca era populado, e `custo_demob_instancia` era sempre gravado como 0.0 mesmo
    quando a desmobilização antecipada era efetivamente aplicada.
    """

    def _contrato(self, semana_fim="S010"):
        from types import SimpleNamespace

        return SimpleNamespace(semana_fim=semana_fim)

    def test_mobilizacao_sempre_computada_para_instancia_usada(self):
        mod = _load_helpers_a()
        instance_week_map = {1: {"S003": "eap-A", "S004": "eap-A"}}
        mobilizacao_por_instancia: dict = {}
        result = mod._compute_instancia_lifecycle(
            i=1,
            instance_week_map=instance_week_map,
            contrato=self._contrato(),
            contract_start_idx=1,
            contract_end_idx=10,
            apply_idle_gaps=True,
            c_mo=1000.0,
            c_eq=400.0,
            c_comb=200.0,
            c_mat=100.0,
            c_idle_unit=80.0,
            c_mob_unit=1800.0,
            c_demob_unit=2500.0,
            prod_w=2,
            mobilizacao_por_instancia=mobilizacao_por_instancia,
        )
        (
            sm_mob,
            sm_demob,
            _semanas_off,
            _ca_mo,
            _ca_eq,
            _ca_comb,
            _ca_mat,
            _ci_mo,
            _ci_eq,
            c_mob_i,
            c_demob_i,
            desmob_aplicada,
            custo_inst_total,
            _idle_segs,
        ) = result
        # Instância foi de fato usada (mobilizada) — custo de mobilização é sempre incorrido.
        assert c_mob_i == pytest.approx(1800.0)
        # Trailing standby (S005..S010) supera o custo de demob → desmob antecipada efetiva.
        assert desmob_aplicada is True
        assert c_demob_i == pytest.approx(2500.0)
        assert sm_mob == "S003"
        assert sm_demob == "S004"
        # 2 semanas ativas × (1000+400+200+100) + mob + demob = 3400 + 1800 + 2500
        assert custo_inst_total == pytest.approx(3400.0 + 1800.0 + 2500.0)

    def test_demob_zero_quando_nao_ha_desmob_antecipada(self):
        """Instância ativa até o fim do contrato: sem trailing standby, sem desmob efetiva."""
        mod = _load_helpers_a()
        instance_week_map = {1: {f"S{n:03d}": "eap-A" for n in range(1, 11)}}
        result = mod._compute_instancia_lifecycle(
            i=1,
            instance_week_map=instance_week_map,
            contrato=self._contrato(semana_fim="S010"),
            contract_start_idx=1,
            contract_end_idx=10,
            apply_idle_gaps=True,
            c_mo=1000.0,
            c_eq=400.0,
            c_comb=200.0,
            c_mat=100.0,
            c_idle_unit=80.0,
            c_mob_unit=1800.0,
            c_demob_unit=2500.0,
            prod_w=10,
            mobilizacao_por_instancia={},
        )
        c_mob_i, c_demob_i, desmob_aplicada = result[9], result[10], result[11]
        # Mobilização ainda ocorre (instância foi usada)...
        assert c_mob_i == pytest.approx(1800.0)
        # ...mas sem trailing standby não há desmob antecipada — custo embutido no contrato.
        assert desmob_aplicada is False
        assert c_demob_i == 0.0

    def test_instancia_nao_utilizada_sem_mob_nem_demob(self):
        """Slot nunca ativado (apply_idle_gaps=False ou sem atividades) permanece zerado."""
        mod = _load_helpers_a()
        result = mod._compute_instancia_lifecycle(
            i=1,
            instance_week_map={1: {}},
            contrato=self._contrato(),
            contract_start_idx=1,
            contract_end_idx=10,
            apply_idle_gaps=True,
            c_mo=1000.0,
            c_eq=400.0,
            c_comb=200.0,
            c_mat=100.0,
            c_idle_unit=80.0,
            c_mob_unit=1800.0,
            c_demob_unit=2500.0,
            prod_w=0,
            mobilizacao_por_instancia={},
        )
        c_mob_i, c_demob_i = result[9], result[10]
        assert c_mob_i == 0.0
        assert c_demob_i == 0.0


def _mk_sched(item_id, weeks):
    """ScheduledActivityCanonical com distribuicao_semanal (1 equipe nas semanas dadas)."""
    from concilium.domain.models.canonical import (
        DistribuicaoSemanal,
        ScheduledActivityCanonical,
    )

    dist = {
        w: DistribuicaoSemanal(
            num_equipes=1,
            qtd_executada=10.0,
            qtd_acumulada=10.0,
            pct=1.0,
            eficiencia=1.0,
            fator_clima=1.0,
            fator_calendario=1.0,
        )
        for w in weeks
    }
    return ScheduledActivityCanonical(
        activity_id=item_id,
        start_week=0,
        end_week=len(weeks),
        duration_weeks=len(weeks),
        distribuicao_semanal=dist,
    )


def _mk_equipe(item_id, mo, eq, comb, mat, custo_total):
    from concilium.domain.models.canonical import EquipeDireta

    return EquipeDireta(
        equipe_id=f"eq-{item_id}",
        item_id=item_id,
        cpu_id="CPU-X",
        custo_mao_obra_mensal=mo,
        custo_equipamentos_mensal=eq,
        custo_combustivel_total_mensal=comb,
        custo_material_mensal=mat,
        custo_fixo_mensal=mo + eq + mat,
        custo_total=custo_total,
    )


class TestPipelineComposicional:
    """Dois itens do mesmo tipo, um tardio, com resource_costs (c_idle > 0)."""

    def _run(self, with_idle: bool, weeks_b=None, mo=8000.0, remob=(5000.0, 2500.0)):
        mod = _load_helpers_a()
        # eap-A: semanas S001..S010 (cedo) | eap-B: tardio (gap longo por padrão)
        weeks_a = [f"S{n:03d}" for n in range(1, 11)]
        if weeks_b is None:
            weeks_b = [f"S{n:03d}" for n in range(20, 26)]
        # custo_total calibrado para custo_unit_semanal=13000 (= soma componentes) por mw
        base = mo + 3000.0 + 1500.0 + 500.0
        equipes = [
            _mk_equipe("eap-A", mo, 3000.0, 1500.0, 500.0, base * 10),
            _mk_equipe("eap-B", mo, 3000.0, 1500.0, 500.0, base * 6),
        ]
        sched_lookup = {"eap-A": _mk_sched("eap-A", weeks_a), "eap-B": _mk_sched("eap-B", weeks_b)}
        resource_costs = (
            {
                "ESC": {
                    "custo_mob_unit": remob[0],
                    "custo_demob_unit": remob[1],
                    "custo_idle_semanal_unit": 2000.0,
                    "unidade_faturamento": "dia_cal",
                }
            }
            if with_idle
            else {}
        )
        rcpsp_spec = {
            "resource_pool": {"ESC": 1},
            "activities": [
                {"item_id": "eap-A", "required_resources": {"ESC": 1}},
                {"item_id": "eap-B", "required_resources": {"ESC": 1}},
            ],
            "resource_costs": resource_costs,
        }
        validacoes = []
        contratos, atribuicao, cadeias = mod._build_contratos_recurso(equipes, rcpsp_spec, sched_lookup, validacoes)
        for eq in equipes:
            if eq.item_id in atribuicao:
                eq.custo_total_autonomo = eq.custo_total
                eq.custo_total = atribuicao[eq.item_id][0]
        instancias, _comp, _res = mod._build_instancias_recurso(contratos, rcpsp_spec, sched_lookup, validacoes)
        if instancias:
            mod._aplicar_custo_instancial(contratos, instancias, equipes, validacoes)
        return mod, contratos, equipes, instancias, validacoes

    def test_taxas_por_componente_somam_unitaria(self):
        _mod, contratos, _eq, _inst, _val = self._run(with_idle=True)
        c = contratos[0]
        soma = c.custo_unit_semanal_mo + c.custo_unit_semanal_eq + c.custo_unit_semanal_comb + c.custo_unit_semanal_mat
        assert soma == pytest.approx(c.custo_unit_semanal, rel=1e-3)

    def test_mobilizacao_tardia_preenchida(self):
        _mod, contratos, _eq, _inst, _val = self._run(with_idle=True)
        c = contratos[0]
        # instância única (pool=1); mobilizada na primeira semana ativa global S001
        assert c.mobilizacao_por_instancia
        assert c.mobilizacao_por_instancia.get(1) == "S001"

    def test_custo_instancial_menor_que_monolitico(self):
        """Com c_idle e gaps, o custo composicional < monolítico (peak×unit×span)."""
        _mod, contratos, _eq, instancias, _val = self._run(with_idle=True)
        c = contratos[0]
        # monolítico seria quantidade × custo_unit × semanas_contrato (span S001..S025 = 25)
        monolitico = c.quantidade_contratada * c.custo_unit_semanal * 25
        assert c.custo_total_contrato < monolitico
        # e o contrato = Σ custo_instancia_total
        soma_inst = sum(i.custo_instancia_total for i in instancias)
        assert c.custo_total_contrato == pytest.approx(soma_inst, abs=1.0)

    def test_invariante_categorial_soma(self):
        """ADR-085 D4: Σ custo_inst_cat == custo_total_particionado por item."""
        _mod, contratos, _eq, _inst, _val = self._run(with_idle=True)
        for c in contratos:
            for part in c.particao_por_item:
                soma = part.custo_inst_mo + part.custo_inst_eq + part.custo_inst_comb + part.custo_inst_mat
                assert soma == pytest.approx(part.custo_total_particionado, abs=0.05)

    def test_invariante_particao_soma_contrato(self):
        """Σ custo_total_particionado == custo_total_contrato (ADR-071 D3 preservado)."""
        _mod, contratos, _eq, _inst, _val = self._run(with_idle=True)
        for c in contratos:
            soma = sum(p.custo_total_particionado for p in c.particao_por_item)
            assert soma == pytest.approx(c.custo_total_contrato, abs=1.0)

    def test_retrocompat_sem_idle_mantem_monolitico(self):
        """Sem resource_costs (c_idle=0), o custo permanece monolítico (ADR-071)."""
        _mod, contratos, _eq, instancias, _val = self._run(with_idle=False)
        c = contratos[0]
        monolitico = c.quantidade_contratada * c.custo_unit_semanal * c.semanas_contrato
        assert c.custo_total_contrato == pytest.approx(monolitico, abs=1.0)
        # instâncias não recebem custo composicional
        assert all(i.custo_instancia_total == 0.0 for i in instancias)

    def test_c_pool_menor_que_total_quando_ha_mobilizacao(self):
        """ADR-136 F6: C_pool ≤ total deixa de ser uma tautologia (mob/demob=0 sempre).

        Antes da correção, custo_mob_instancia/custo_demob_instancia eram sempre
        0.0 no pipeline real do pool — a validação C_pool ≤ total (ADR-125 D4)
        era sempre trivialmente verdadeira. Com valores reais, C_pool (produtivo +
        ocioso, sem mob/demob) é estritamente menor que o total (que os inclui)
        sempre que há mobilização/desmobilização efetiva.
        """
        _mod, _contratos, _eq, instancias, _val = self._run(with_idle=True)
        inst = instancias[0]
        c_pool_instancia = (
            inst.custo_ativo_mo
            + inst.custo_ativo_eq
            + inst.custo_ativo_comb
            + inst.custo_ativo_mat
            + inst.custo_idle_mo
            + inst.custo_idle_eq
        )
        assert inst.custo_mob_instancia > 0.0  # instância foi mobilizada — não é vácuo
        assert c_pool_instancia < inst.custo_instancia_total
        assert c_pool_instancia == pytest.approx(
            inst.custo_instancia_total - inst.custo_mob_instancia - inst.custo_demob_instancia
        )

    def test_gap_longo_vira_off_nao_faturado(self):
        """Gap (9 sem) > gap_max → recurso desmobilizado: semanas OFF, não faturadas.

        Sem ociosidade faturada, o custo instancial = soma das semanas produtivas
        + o custo de mobilização (ADR-136 F3: sempre incorrido para uma instância
        de fato utilizada) — o baseline "autônomo" do fixture não modela
        mobilização, então a diferença é exatamente 1 mobilização (remob[0]).
        """
        _mod, contratos, equipes, instancias, _val = self._run(with_idle=True)
        inst = instancias[0]
        assert inst.semanas_off > 0  # gap longo classificado como off
        assert inst.custo_idle_mo == 0.0 and inst.custo_idle_eq == 0.0
        assert inst.custo_mob_instancia == pytest.approx(5000.0)  # remob[0] default
        n4 = sum(eq.custo_total for eq in equipes)
        n4_autonomo = sum(eq.custo_total_autonomo for eq in equipes)
        assert n4 == pytest.approx(n4_autonomo + inst.custo_mob_instancia, abs=1.0)

    def test_gap_curto_economico_vira_idle_faturado(self):
        """Gap curto + MO barata + remob caro → ponte ociosa econômica: idle faturado.

        idle_week_cost = MO(200) + EQ_idle(2000) = 2200; gap=2 → 4400 ≤ remob(20000+10000)=30000
        → IDLE: MO integral + EQ reduzida cobrados.
        """
        weeks_b_curto = [f"S{n:03d}" for n in range(13, 19)]  # gap S011,S012 = 2 sem
        _mod, _contratos, equipes, instancias, _val = self._run(
            with_idle=True, weeks_b=weeks_b_curto, mo=200.0, remob=(20000.0, 10000.0)
        )
        inst = instancias[0]
        assert inst.custo_idle_mo > 0.0  # MO integral durante o gap curto (CLT)
        assert inst.custo_idle_eq > 0.0  # EQ a taxa reduzida durante o gap curto
        assert inst.semanas_off == 0  # nada off interno: gap foi mantido idle

    def test_gap_curto_mo_pesada_vira_off(self):
        """Gap curto mas MO pesada → liberar é mais barato que manter idle: OFF.

        idle_week_cost = MO(8000)+EQ_idle(2000)=10000; gap=2 → 20000 > remob(5000+2500)=7500
        → OFF: recurso liberado, gap não faturado.
        """
        weeks_b_curto = [f"S{n:03d}" for n in range(13, 19)]  # gap = 2 sem
        _mod, _contratos, equipes, instancias, _val = self._run(
            with_idle=True, weeks_b=weeks_b_curto, mo=8000.0, remob=(5000.0, 2500.0)
        )
        inst = instancias[0]
        assert inst.custo_idle_mo == 0.0  # MO-pesada → recurso liberado, não ocioso
        assert inst.semanas_off > 0
        assert inst.custo_mob_instancia == pytest.approx(5000.0)  # remob[0] (ADR-136 F3)
        n4 = sum(eq.custo_total for eq in equipes)
        n4_autonomo = sum(eq.custo_total_autonomo for eq in equipes)
        assert n4 == pytest.approx(n4_autonomo + inst.custo_mob_instancia, abs=1.0)
