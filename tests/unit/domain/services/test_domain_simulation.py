"""Tests for concilium.domain.services.simulation — targets 80%+ coverage."""

from math import ceil

import pytest

from concilium.domain.services.simulation import (
    ResultadoSimulacao,
    SimuladorEngenharia,
    _sim_calc_equipamentos,
    _sim_calc_funcoes,
    _sim_calc_materiais,
)

# ---------------------------------------------------------------------------
# Helpers / fixtures
# ---------------------------------------------------------------------------


def make_catalogo(
    cpus=None,
    insumos=None,
    producoes=None,
):
    """Build a minimal catalog dict suitable for SimuladorEngenharia."""
    return {
        "cpus": cpus or [],
        "insumos": insumos or [],
        "produtividades": producoes or [],
    }


def make_cpu(codigo="CPU-001", producao_id_ref=None, unidade="m3", composicao_itens=None):
    return {
        "codigo": codigo,
        "unidade": unidade,
        "producao_id_ref": producao_id_ref,
        "composicao_itens": composicao_itens or [],
    }


def make_producao(pid="PROD-001", valor_horario=10.0, equipe=None):
    p = {"id": pid, "valor_horario": valor_horario}
    if equipe is not None:
        p["composicao_padrao_equipe"] = equipe
    return p


def make_insumo(codigo, preco_unitario=100.0, unidade="h", atributos_especificos=None):
    i = {"codigo": codigo, "preco_unitario": preco_unitario, "unidade": unidade}
    if atributos_especificos is not None:
        i["atributos_especificos"] = atributos_especificos
    return i


# ---------------------------------------------------------------------------
# SimuladorEngenharia.__init__
# ---------------------------------------------------------------------------


class TestSimuladorInit:
    def test_empty_catalog_creates_empty_dicts(self):
        sim = SimuladorEngenharia(make_catalogo())
        assert sim.cpus == {}
        assert sim.insumos == {}
        assert sim.producoes == {}

    def test_cpus_indexed_by_codigo(self):
        cpu = make_cpu("CPU-A")
        sim = SimuladorEngenharia(make_catalogo(cpus=[cpu]))
        assert "CPU-A" in sim.cpus
        assert sim.cpus["CPU-A"] is cpu

    def test_insumos_indexed_by_codigo(self):
        ins = make_insumo("INS-A", preco_unitario=50.0)
        sim = SimuladorEngenharia(make_catalogo(insumos=[ins]))
        assert "INS-A" in sim.insumos

    def test_producoes_indexed_by_id(self):
        prod = make_producao("PROD-X", valor_horario=5.5)
        sim = SimuladorEngenharia(make_catalogo(producoes=[prod]))
        assert sim.producoes["PROD-X"] == 5.5

    def test_producoes_key_producoes_fallback(self):
        """Catalog may use 'producoes' instead of 'produtividades'."""
        prod = make_producao("PROD-Z", valor_horario=3.0)
        catalogo = {"cpus": [], "insumos": [], "producoes": [prod]}
        sim = SimuladorEngenharia(catalogo)
        assert sim.producoes["PROD-Z"] == 3.0

    def test_producao_without_id_ignored(self):
        """Entries without an 'id' field should be skipped."""
        prod_no_id = {"valor_horario": 9.0}
        sim = SimuladorEngenharia(make_catalogo(producoes=[prod_no_id]))
        assert sim.producoes == {}


# ---------------------------------------------------------------------------
# SimuladorEngenharia._calcular_dias_trabalhados
# ---------------------------------------------------------------------------


class TestCalcularDiasTrabalhados:
    @pytest.fixture
    def sim(self):
        return SimuladorEngenharia(make_catalogo())

    def test_7x0_returns_periodo_inteiro(self, sim):
        assert sim._calcular_dias_trabalhados(28, "7x0") == 28

    def test_continuo_returns_periodo_inteiro(self, sim):
        assert sim._calcular_dias_trabalhados(14, "continuo") == 14

    def test_6x1_equals_ceil_6_over_7(self, sim):
        periodo = 28
        expected = ceil(periodo / 7 * 6)
        assert sim._calcular_dias_trabalhados(periodo, "6x1") == expected

    def test_5x2_equals_ceil_5_over_7(self, sim):
        periodo = 35
        expected = ceil(periodo / 7 * 5)
        assert sim._calcular_dias_trabalhados(periodo, "5x2") == expected

    def test_unknown_regime_returns_periodo(self, sim):
        """Unrecognised regime should fall through to returning periodo_dias."""
        assert sim._calcular_dias_trabalhados(10, "4x3") == 10

    def test_6x1_non_multiple_of_7(self, sim):
        periodo = 10  # 1 full week + 3 days
        expected = ceil(10 / 7 * 6)
        assert sim._calcular_dias_trabalhados(periodo, "6x1") == expected

    def test_5x2_non_multiple_of_7(self, sim):
        periodo = 10
        expected = ceil(10 / 7 * 5)
        assert sim._calcular_dias_trabalhados(periodo, "5x2") == expected


# ---------------------------------------------------------------------------
# simular_cpu — basic validation
# ---------------------------------------------------------------------------


class TestSimularCpuValidation:
    def test_missing_cpu_raises_value_error(self):
        sim = SimuladorEngenharia(make_catalogo())
        with pytest.raises(ValueError, match="CPU-MISSING"):
            sim.simular_cpu("CPU-MISSING", 30, "7x0", 8.0)

    def test_returns_resultado_simulacao_instance(self):
        cpu = make_cpu("CPU-001")
        sim = SimuladorEngenharia(make_catalogo(cpus=[cpu]))
        result = sim.simular_cpu("CPU-001", 7, "7x0", 8.0)
        assert isinstance(result, ResultadoSimulacao)

    def test_cpu_id_preserved_in_result(self):
        cpu = make_cpu("CPU-001")
        sim = SimuladorEngenharia(make_catalogo(cpus=[cpu]))
        result = sim.simular_cpu("CPU-001", 7, "7x0", 8.0)
        assert result.cpu_id == "CPU-001"

    def test_unidade_from_cpu(self):
        cpu = make_cpu("CPU-X", unidade="m2")
        sim = SimuladorEngenharia(make_catalogo(cpus=[cpu]))
        result = sim.simular_cpu("CPU-X", 7, "7x0", 8.0)
        assert result.unidade == "m2"


# ---------------------------------------------------------------------------
# simular_cpu — regime variants
# ---------------------------------------------------------------------------


class TestSimularCpuRegimes:
    """Verify dias_trabalhados for each supported regime."""

    @pytest.fixture
    def sim_basic(self):
        cpu = make_cpu("CPU-001")
        return SimuladorEngenharia(make_catalogo(cpus=[cpu]))

    def test_7x0_dias(self, sim_basic):
        r = sim_basic.simular_cpu("CPU-001", 28, "7x0", 8.0)
        assert r.dias_trabalhados == 28

    def test_continuo_dias(self, sim_basic):
        r = sim_basic.simular_cpu("CPU-001", 28, "continuo", 8.0)
        assert r.dias_trabalhados == 28

    def test_6x1_dias(self, sim_basic):
        r = sim_basic.simular_cpu("CPU-001", 28, "6x1", 8.0)
        assert r.dias_trabalhados == ceil(28 / 7 * 6)

    def test_5x2_dias(self, sim_basic):
        r = sim_basic.simular_cpu("CPU-001", 28, "5x2", 8.0)
        assert r.dias_trabalhados == ceil(28 / 7 * 5)

    def test_horas_totais_consistent_with_dias(self, sim_basic):
        """producao_total = 0 when no producao_id_ref, but horas implicitly tested."""
        r = sim_basic.simular_cpu("CPU-001", 7, "5x2", 10.0)
        assert r.dias_trabalhados == ceil(7 / 7 * 5)


# ---------------------------------------------------------------------------
# simular_cpu — producao_total
# ---------------------------------------------------------------------------


class TestSimularCpuProducao:
    def test_producao_total_equals_prod_h_times_horas(self):
        prod = make_producao("PROD-A", valor_horario=5.0)
        cpu = make_cpu("CPU-A", producao_id_ref="PROD-A")
        sim = SimuladorEngenharia(make_catalogo(cpus=[cpu], producoes=[prod]))
        periodo = 7
        horas_dia = 8.0
        r = sim.simular_cpu("CPU-A", periodo, "7x0", horas_dia)
        expected = 5.0 * periodo * horas_dia
        assert r.producao_total == pytest.approx(expected, abs=0.01)

    def test_no_producao_id_ref_yields_zero_producao(self):
        cpu = make_cpu("CPU-B")  # no producao_id_ref
        sim = SimuladorEngenharia(make_catalogo(cpus=[cpu]))
        r = sim.simular_cpu("CPU-B", 7, "7x0", 8.0)
        assert r.producao_total == 0.0

    def test_producao_id_ref_not_in_catalog_yields_zero(self):
        cpu = make_cpu("CPU-C", producao_id_ref="GHOST-PROD")
        sim = SimuladorEngenharia(make_catalogo(cpus=[cpu]))
        r = sim.simular_cpu("CPU-C", 7, "7x0", 8.0)
        assert r.producao_total == 0.0


# ---------------------------------------------------------------------------
# simular_cpu — no producao_id_ref → zero labor costs
# ---------------------------------------------------------------------------


class TestSimularCpuNoProdRef:
    def test_no_prod_ref_yields_zero_labor_costs(self):
        cpu = make_cpu("CPU-Z")
        sim = SimuladorEngenharia(make_catalogo(cpus=[cpu]))
        r = sim.simular_cpu("CPU-Z", 14, "7x0", 8.0)
        assert r.custo_mao_obra_base == 0.0
        assert r.custo_mao_obra_encargos == 0.0
        assert r.custo_equipamento_capital == 0.0
        assert r.custo_equipamento_manutencao == 0.0
        assert r.custo_diesel_total == 0.0

    def test_no_prod_ref_yields_zero_total(self):
        cpu = make_cpu("CPU-Z")
        sim = SimuladorEngenharia(make_catalogo(cpus=[cpu]))
        r = sim.simular_cpu("CPU-Z", 14, "7x0", 8.0)
        assert r.total_direto == 0.0


# ---------------------------------------------------------------------------
# simular_cpu — contratacao CLT vs PJ
# ---------------------------------------------------------------------------


class TestSimularCpuEncargos:
    """FATOR_ENCARGOS CLT=0.77, PJ=0.06."""

    def _make_sim_with_funcao(self):
        """A CPU with one funcao paying 100/h."""
        ins = make_insumo("FUNC-A", preco_unitario=100.0, unidade="h")
        equipe = {"funcoes": [{"funcao_id": "FUNC-A", "num_pessoas": 1}], "equipamentos": []}
        prod = make_producao("PROD-A", valor_horario=1.0, equipe=equipe)
        cpu = make_cpu("CPU-A", producao_id_ref="PROD-A")
        cat = make_catalogo(cpus=[cpu], insumos=[ins], producoes=[prod])
        return SimuladorEngenharia(cat)

    def test_clt_encargos(self):
        sim = self._make_sim_with_funcao()
        r = sim.simular_cpu("CPU-A", 7, "7x0", 8.0, contratacao="clt")
        horas = 7 * 8.0
        base = 1 * 100.0 * horas
        expected_encargos = base * 0.77
        assert r.custo_mao_obra_base == pytest.approx(base, abs=0.01)
        assert r.custo_mao_obra_encargos == pytest.approx(expected_encargos, abs=0.01)

    def test_pj_encargos(self):
        sim = self._make_sim_with_funcao()
        r = sim.simular_cpu("CPU-A", 7, "7x0", 8.0, contratacao="pj")
        horas = 7 * 8.0
        base = 1 * 100.0 * horas
        expected_encargos = base * 0.06
        assert r.custo_mao_obra_encargos == pytest.approx(expected_encargos, abs=0.01)

    def test_clt_encargos_greater_than_pj(self):
        sim = self._make_sim_with_funcao()
        r_clt = sim.simular_cpu("CPU-A", 7, "7x0", 8.0, contratacao="clt")
        r_pj = sim.simular_cpu("CPU-A", 7, "7x0", 8.0, contratacao="pj")
        assert r_clt.custo_mao_obra_encargos > r_pj.custo_mao_obra_encargos

    def test_default_contratacao_is_clt(self):
        sim = self._make_sim_with_funcao()
        r_default = sim.simular_cpu("CPU-A", 7, "7x0", 8.0)
        r_clt = sim.simular_cpu("CPU-A", 7, "7x0", 8.0, contratacao="clt")
        assert r_default.custo_mao_obra_encargos == r_clt.custo_mao_obra_encargos


# ---------------------------------------------------------------------------
# simular_cpu — total_direto is sum of all components
# ---------------------------------------------------------------------------


class TestSimularCpuTotalDireto:
    def test_total_direto_equals_sum_of_components(self):
        ins_func = make_insumo("FUNC-A", preco_unitario=50.0, unidade="h")
        ins_mat = make_insumo("MAT-A", preco_unitario=10.0, unidade="m3")
        equipe = {"funcoes": [{"funcao_id": "FUNC-A", "num_pessoas": 2}], "equipamentos": []}
        prod = make_producao("PROD-A", valor_horario=2.0, equipe=equipe)
        cpu = make_cpu(
            "CPU-A",
            producao_id_ref="PROD-A",
            composicao_itens=[{"insumo_id": "MAT-A", "coeficiente": 0.5}],
        )
        sim = SimuladorEngenharia(make_catalogo(cpus=[cpu], insumos=[ins_func, ins_mat], producoes=[prod]))
        r = sim.simular_cpu("CPU-A", 7, "7x0", 8.0)
        computed_total = round(
            r.custo_material
            + r.custo_mao_obra_base
            + r.custo_mao_obra_encargos
            + r.custo_equipamento_capital
            + r.custo_equipamento_manutencao
            + r.custo_diesel_total,
            2,
        )
        assert r.total_direto == pytest.approx(computed_total, abs=0.01)

    def test_total_direto_zero_when_no_costs(self):
        cpu = make_cpu("CPU-Z")
        sim = SimuladorEngenharia(make_catalogo(cpus=[cpu]))
        r = sim.simular_cpu("CPU-Z", 7, "7x0", 8.0)
        assert r.total_direto == 0.0


# ---------------------------------------------------------------------------
# _sim_calc_funcoes — unit tests
# ---------------------------------------------------------------------------


class TestSimCalcFuncoes:
    def test_empty_equipe(self):
        base, enc = _sim_calc_funcoes({}, {}, 56.0, 0.77)
        assert base == 0.0
        assert enc == 0.0

    def test_funcao_unidade_hora(self):
        equipe = {"funcoes": [{"funcao_id": "F1", "num_pessoas": 2}]}
        insumos = {"F1": {"preco_unitario": 100.0, "unidade": "h"}}
        base, enc = _sim_calc_funcoes(equipe, insumos, 10.0, 0.77)
        # base = 2 * 100 * 10 = 2000
        assert base == pytest.approx(2000.0)
        assert enc == pytest.approx(2000.0 * 0.77)

    def test_funcao_unidade_mes_divides_by_208(self):
        equipe = {"funcoes": [{"funcao_id": "F1", "num_pessoas": 1}]}
        insumos = {"F1": {"preco_unitario": 2080.0, "unidade": "mes"}}
        base, enc = _sim_calc_funcoes(equipe, insumos, 10.0, 0.06)
        # preco_base = 2080 / 208 = 10.0
        # base = 1 * 10.0 * 10.0 = 100.0
        assert base == pytest.approx(100.0)
        assert enc == pytest.approx(100.0 * 0.06)

    def test_funcao_missing_insumo_uses_zero(self):
        equipe = {"funcoes": [{"funcao_id": "GHOST", "num_pessoas": 3}]}
        base, enc = _sim_calc_funcoes(equipe, {}, 8.0, 0.77)
        assert base == 0.0
        assert enc == 0.0

    def test_multiple_funcoes_accumulated(self):
        equipe = {
            "funcoes": [
                {"funcao_id": "F1", "num_pessoas": 1},
                {"funcao_id": "F2", "num_pessoas": 2},
            ]
        }
        insumos = {
            "F1": {"preco_unitario": 10.0, "unidade": "h"},
            "F2": {"preco_unitario": 20.0, "unidade": "h"},
        }
        base, enc = _sim_calc_funcoes(equipe, insumos, 5.0, 0.77)
        # F1: 1 * 10 * 5 = 50; F2: 2 * 20 * 5 = 200; total = 250
        assert base == pytest.approx(250.0)
        assert enc == pytest.approx(250.0 * 0.77)

    def test_fator_pj_applied_correctly(self):
        equipe = {"funcoes": [{"funcao_id": "F1", "num_pessoas": 1}]}
        insumos = {"F1": {"preco_unitario": 100.0, "unidade": "h"}}
        base_clt, enc_clt = _sim_calc_funcoes(equipe, insumos, 8.0, 0.77)
        base_pj, enc_pj = _sim_calc_funcoes(equipe, insumos, 8.0, 0.06)
        assert base_clt == base_pj  # base is the same
        assert enc_clt != enc_pj
        assert enc_pj == pytest.approx(base_pj * 0.06)


# ---------------------------------------------------------------------------
# _sim_calc_equipamentos — unit tests
# ---------------------------------------------------------------------------


class TestSimCalcEquipamentos:
    def test_empty_equipe(self):
        eq_cap, eq_manut, diesel, mo, mo_enc = _sim_calc_equipamentos({}, {}, 10.0, 0.77)
        assert eq_cap == 0.0
        assert eq_manut == 0.0
        assert diesel == 0.0

    def test_fallback_split_no_decomp(self):
        """Without decomposicao_equip, uses 0.7/0.1/0.2 split."""
        equipe = {"equipamentos": [{"equip_id": "EQ-A", "num_unidades": 1}]}
        insumos = {"EQ-A": {"preco_unitario": 100.0}}
        horas = 10.0
        eq_cap, eq_manut, diesel, mo, mo_enc = _sim_calc_equipamentos(equipe, insumos, horas, 0.77)
        contribuicao = 1 * 100.0 * horas  # = 1000
        assert mo == pytest.approx(contribuicao * 0.7)
        assert eq_manut == pytest.approx(contribuicao * 0.1)
        assert diesel == pytest.approx(contribuicao * 0.2)
        assert eq_cap == 0.0  # no capital in fallback
        assert mo_enc == pytest.approx(contribuicao * 0.7 * 0.77)

    def test_with_decomposicao(self):
        """With decomposicao_equip, costs are split proportionally."""
        decomp = {
            "custo_hora_total": 100.0,
            "custo_diesel_h": 20.0,
            "custo_material_h": 10.0,
            "custo_capital_h": 30.0,
            "custo_mao_obra_h": 40.0,
        }
        equipe = {"equipamentos": [{"equip_id": "EQ-B", "num_unidades": 2}]}
        insumos = {
            "EQ-B": {
                "preco_unitario": 100.0,
                "atributos_especificos": {"decomposicao_equip": decomp},
            }
        }
        horas = 5.0
        contribuicao = 2 * 100.0 * horas  # = 1000
        eq_cap, eq_manut, diesel, mo, mo_enc = _sim_calc_equipamentos(equipe, insumos, horas, 0.77)
        assert diesel == pytest.approx(contribuicao * 20 / 100)
        assert eq_manut == pytest.approx(contribuicao * 10 / 100)
        assert eq_cap == pytest.approx(contribuicao * 30 / 100)
        assert mo == pytest.approx(contribuicao * 40 / 100)
        assert mo_enc == pytest.approx(contribuicao * 40 / 100 * 0.77)

    def test_missing_insumo_uses_zero_price(self):
        equipe = {"equipamentos": [{"equip_id": "GHOST", "num_unidades": 1}]}
        eq_cap, eq_manut, diesel, mo, mo_enc = _sim_calc_equipamentos(equipe, {}, 10.0, 0.77)
        assert mo == 0.0
        assert diesel == 0.0

    def test_atributos_especificos_none_uses_fallback(self):
        """atributos_especificos=None should not blow up — should use fallback."""
        equipe = {"equipamentos": [{"equip_id": "EQ-C", "num_unidades": 1}]}
        insumos = {"EQ-C": {"preco_unitario": 200.0, "atributos_especificos": None}}
        eq_cap, eq_manut, diesel, mo, mo_enc = _sim_calc_equipamentos(equipe, insumos, 4.0, 0.06)
        contribuicao = 1 * 200.0 * 4.0  # = 800
        assert mo == pytest.approx(contribuicao * 0.7)
        assert diesel == pytest.approx(contribuicao * 0.2)

    def test_decomp_custo_hora_total_zero_uses_preco_fallback(self):
        """When custo_hora_total == 0 in decomp, falls back to 1.0 denominator guard."""
        decomp = {
            "custo_hora_total": 0,  # triggers `or 1.0`
            "custo_diesel_h": 5.0,
            "custo_material_h": 0,
            "custo_capital_h": 0,
            "custo_mao_obra_h": 0,
        }
        equipe = {"equipamentos": [{"equip_id": "EQ-D", "num_unidades": 1}]}
        insumos = {
            "EQ-D": {
                "preco_unitario": 10.0,
                "atributos_especificos": {"decomposicao_equip": decomp},
            }
        }
        # Should not raise ZeroDivisionError
        eq_cap, eq_manut, diesel, mo, mo_enc = _sim_calc_equipamentos(equipe, insumos, 2.0, 0.77)
        # contribuicao = 1 * 10 * 2 = 20; total_h = 1.0 (guard); diesel = 20 * 5/1 = 100
        assert diesel == pytest.approx(100.0)


# ---------------------------------------------------------------------------
# _sim_calc_materiais — unit tests
# ---------------------------------------------------------------------------


class TestSimCalcMateriais:
    def test_empty_composicao(self):
        cpu = {"composicao_itens": []}
        assert _sim_calc_materiais(cpu, {}, 100.0) == 0.0

    def test_single_item_accumulation(self):
        cpu = {"composicao_itens": [{"insumo_id": "MAT-A", "coeficiente": 2.0}]}
        insumos = {"MAT-A": {"preco_unitario": 5.0}}
        producao_total = 100.0
        result = _sim_calc_materiais(cpu, insumos, producao_total)
        assert result == pytest.approx(2.0 * 100.0 * 5.0)

    def test_multiple_items_accumulated(self):
        cpu = {
            "composicao_itens": [
                {"insumo_id": "MAT-A", "coeficiente": 1.0},
                {"insumo_id": "MAT-B", "coeficiente": 0.5},
            ]
        }
        insumos = {
            "MAT-A": {"preco_unitario": 10.0},
            "MAT-B": {"preco_unitario": 4.0},
        }
        result = _sim_calc_materiais(cpu, insumos, 50.0)
        # MAT-A: 1 * 50 * 10 = 500; MAT-B: 0.5 * 50 * 4 = 100; total = 600
        assert result == pytest.approx(600.0)

    def test_missing_insumo_uses_zero_price(self):
        cpu = {"composicao_itens": [{"insumo_id": "GHOST", "coeficiente": 3.0}]}
        result = _sim_calc_materiais(cpu, {}, 100.0)
        assert result == 0.0

    def test_zero_producao_yields_zero_cost(self):
        cpu = {"composicao_itens": [{"insumo_id": "MAT-A", "coeficiente": 2.0}]}
        insumos = {"MAT-A": {"preco_unitario": 100.0}}
        assert _sim_calc_materiais(cpu, insumos, 0.0) == 0.0

    def test_no_composicao_itens_key(self):
        cpu = {}  # no composicao_itens key at all
        assert _sim_calc_materiais(cpu, {}, 100.0) == 0.0


# ---------------------------------------------------------------------------
# Integration: simular_cpu with materials
# ---------------------------------------------------------------------------


class TestSimularCpuMateriais:
    def test_custo_material_computed(self):
        prod = make_producao("PROD-A", valor_horario=1.0)
        ins_mat = make_insumo("MAT-A", preco_unitario=3.0)
        cpu = make_cpu(
            "CPU-A",
            producao_id_ref="PROD-A",
            composicao_itens=[{"insumo_id": "MAT-A", "coeficiente": 2.0}],
        )
        sim = SimuladorEngenharia(make_catalogo(cpus=[cpu], insumos=[ins_mat], producoes=[prod]))
        r = sim.simular_cpu("CPU-A", 7, "7x0", 8.0)
        # producao_total = 1 * 7 * 8 = 56; mat = 2 * 56 * 3 = 336
        assert r.custo_material == pytest.approx(336.0, abs=0.01)

    def test_custo_material_scales_with_producao(self):
        prod = make_producao("PROD-B", valor_horario=2.0)
        ins_mat = make_insumo("MAT-A", preco_unitario=1.0)
        cpu = make_cpu(
            "CPU-B",
            producao_id_ref="PROD-B",
            composicao_itens=[{"insumo_id": "MAT-A", "coeficiente": 1.0}],
        )
        sim = SimuladorEngenharia(make_catalogo(cpus=[cpu], insumos=[ins_mat], producoes=[prod]))
        r1 = sim.simular_cpu("CPU-B", 7, "7x0", 8.0)
        r2 = sim.simular_cpu("CPU-B", 14, "7x0", 8.0)
        assert r2.custo_material == pytest.approx(r1.custo_material * 2, abs=0.01)


# ---------------------------------------------------------------------------
# Integration: simular_cpu with full equipe (funcoes + equipamentos)
# ---------------------------------------------------------------------------


class TestSimularCpuFullEquipe:
    def _make_full_sim(self):
        ins_func = make_insumo("FUNC-A", preco_unitario=100.0, unidade="h")
        ins_equip = make_insumo(
            "EQ-A",
            preco_unitario=200.0,
            atributos_especificos={
                "decomposicao_equip": {
                    "custo_hora_total": 200.0,
                    "custo_diesel_h": 40.0,
                    "custo_material_h": 20.0,
                    "custo_capital_h": 60.0,
                    "custo_mao_obra_h": 80.0,
                }
            },
        )
        equipe = {
            "funcoes": [{"funcao_id": "FUNC-A", "num_pessoas": 1}],
            "equipamentos": [{"equip_id": "EQ-A", "num_unidades": 1}],
        }
        prod = make_producao("PROD-A", valor_horario=5.0, equipe=equipe)
        cpu = make_cpu("CPU-A", producao_id_ref="PROD-A")
        cat = make_catalogo(cpus=[cpu], insumos=[ins_func, ins_equip], producoes=[prod])
        return SimuladorEngenharia(cat)

    def test_full_equipe_total_direto_is_consistent(self):
        sim = self._make_full_sim()
        r = sim.simular_cpu("CPU-A", 7, "7x0", 8.0)
        computed = round(
            r.custo_material
            + r.custo_mao_obra_base
            + r.custo_mao_obra_encargos
            + r.custo_equipamento_capital
            + r.custo_equipamento_manutencao
            + r.custo_diesel_total,
            2,
        )
        assert r.total_direto == pytest.approx(computed, abs=0.01)

    def test_full_equipe_equipment_capital_nonzero(self):
        sim = self._make_full_sim()
        r = sim.simular_cpu("CPU-A", 7, "7x0", 8.0)
        assert r.custo_equipamento_capital > 0

    def test_full_equipe_diesel_nonzero(self):
        sim = self._make_full_sim()
        r = sim.simular_cpu("CPU-A", 7, "7x0", 8.0)
        assert r.custo_diesel_total > 0
