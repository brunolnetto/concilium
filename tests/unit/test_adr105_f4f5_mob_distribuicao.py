"""ADR-105 F4/F5 — Distribuição de fases MOB: mobilizacao / operacao / desmobilizacao.

TDD: testes para _distribuir_mob_fases() em _indiretos/_skill_helpers_b.py.

Invariantes:
  - mob_total = soma dos custo_fixo_total de fase="mobilizacao"
  - operacao é distribuído proporcionalmente ao longo de todas as semanas
  - demob está na última semana (semana duracao_semanas - 1)
  - total_distribuido ≈ total_original (conservação de custo)
  - Backward compat: item sem campo ``fase`` é ignorado (não gera erro)
"""

from __future__ import annotations

import pytest


def _import():
    """Importa _distribuir_mob_fases do helper de indiretos."""
    import importlib.util
    import sys
    from pathlib import Path

    here = Path(__file__).resolve().parent.parent.parent
    p = (
        here
        / "src"
        / "concilium"
        / "application"
        / "skills"
        / "manifests"
        / "06-resultado-financeiro"
        / "_indiretos"
        / "_skill_helpers_b"
        / "__init__.py"
    )
    spec = importlib.util.spec_from_file_location("skill_helpers_b", p, submodule_search_locations=[str(p.parent)])
    mod = importlib.util.module_from_spec(spec)  # type: ignore[arg-type]
    sys.modules["skill_helpers_b"] = mod
    spec.loader.exec_module(mod)  # type: ignore[union-attr]
    return mod._distribuir_mob_fases


# Fixture padrão do ADR-105 §2.1 (MATEC_GUARULHOS)
_ITEMS_PADRAO = [
    {
        "tipo": "MOB",
        "fase": "mobilizacao",
        "driver": "projeto",
        "custo_fixo_total": 2_044_560.87,
    },
    {
        "tipo": "MOB",
        "fase": "operacao",
        "driver": "mensal",
        "custo_fixo_mensal": 50_000.00,
    },
    {
        "tipo": "MOB",
        "fase": "desmobilizacao",
        "driver": "projeto",
        "custo_fixo_total": 408_912.17,
    },
]


# ---------------------------------------------------------------------------
# Valores retornados — mob, operacao, demob
# ---------------------------------------------------------------------------


class TestTotaisRetornados:
    def test_total_mob_soma_itens_mobilizacao(self):
        fn = _import()
        result = fn(_ITEMS_PADRAO, duracao_semanas=52)
        assert result["total_mob"] == pytest.approx(2_044_560.87, abs=0.05)

    def test_total_demob_soma_itens_desmobilizacao(self):
        fn = _import()
        result = fn(_ITEMS_PADRAO, duracao_semanas=52)
        assert result["total_demob"] == pytest.approx(408_912.17, abs=0.05)

    def test_total_operacao_custo_mensal_vezes_duracao(self):
        """total_operacao = custo_fixo_mensal × (duracao_semanas / SEMANAS_POR_MES)."""
        from concilium.domain.constants import SEMANAS_POR_MES

        fn = _import()
        duracao_semanas = 52
        custo_mensal = 50_000.0
        esperado = custo_mensal * (duracao_semanas / SEMANAS_POR_MES)
        result = fn(_ITEMS_PADRAO, duracao_semanas=duracao_semanas)
        assert result["total_operacao"] == pytest.approx(esperado, rel=0.005)

    def test_chaves_resultado_presentes(self):
        fn = _import()
        result = fn(_ITEMS_PADRAO, duracao_semanas=20)
        assert "total_mob" in result
        assert "total_operacao" in result
        assert "total_demob" in result
        assert "semanal" in result


# ---------------------------------------------------------------------------
# Distribuição semanal: mobilizacao na semana 0
# ---------------------------------------------------------------------------


class TestSemana0Mobilizacao:
    def test_mob_alocado_na_semana_0(self):
        fn = _import()
        items = [
            {"tipo": "MOB", "fase": "mobilizacao", "driver": "projeto", "custo_fixo_total": 1_000_000.0},
        ]
        result = fn(items, duracao_semanas=10)
        assert result["semanal"][0] == pytest.approx(1_000_000.0, abs=0.05)

    def test_mob_zero_em_outras_semanas(self):
        fn = _import()
        items = [
            {"tipo": "MOB", "fase": "mobilizacao", "driver": "projeto", "custo_fixo_total": 1_000_000.0},
        ]
        result = fn(items, duracao_semanas=10)
        for s in range(1, 10):
            assert result["semanal"][s] == pytest.approx(0.0, abs=0.01)


# ---------------------------------------------------------------------------
# Distribuição semanal: operacao distribuída proporcionalmente
# ---------------------------------------------------------------------------


class TestOperacaoDistribuida:
    def test_operacao_distribuida_igualmente(self):
        """Custo mensal distribuído proporcionalmente — cada semana ≈ custo_total/n."""
        from concilium.domain.constants import SEMANAS_POR_MES

        fn = _import()
        custo_mensal = 50_000.0
        duracao_semanas = 12

        items = [
            {"tipo": "MOB", "fase": "operacao", "driver": "mensal", "custo_fixo_mensal": custo_mensal},
        ]
        result = fn(items, duracao_semanas=duracao_semanas)

        custo_total_op = custo_mensal * (duracao_semanas / SEMANAS_POR_MES)
        custo_por_semana = custo_total_op / duracao_semanas

        # Cada semana (exceto a última) deve receber ≈ custo_por_semana
        for s in range(duracao_semanas - 1):
            assert result["semanal"][s] == pytest.approx(custo_por_semana, rel=0.01)

    def test_operacao_soma_igual_ao_total(self):
        """Conservação: soma das semanas == total_operacao."""
        fn = _import()
        custo_mensal = 75_000.0
        duracao_semanas = 20

        items = [
            {"tipo": "MOB", "fase": "operacao", "driver": "mensal", "custo_fixo_mensal": custo_mensal},
        ]
        result = fn(items, duracao_semanas=duracao_semanas)

        soma_semanas = sum(result["semanal"].values())
        assert soma_semanas == pytest.approx(result["total_operacao"], rel=0.001)

    def test_operacao_positiva_em_todas_semanas(self):
        fn = _import()
        items = [
            {"tipo": "MOB", "fase": "operacao", "driver": "mensal", "custo_fixo_mensal": 10_000.0},
        ]
        result = fn(items, duracao_semanas=8)
        for s in range(8):
            assert result["semanal"][s] > 0.0


# ---------------------------------------------------------------------------
# Distribuição semanal: desmobilizacao na última semana
# ---------------------------------------------------------------------------


class TestUltimaSemana:
    def test_demob_alocado_na_ultima_semana(self):
        fn = _import()
        n_semanas = 10
        items = [
            {
                "tipo": "MOB",
                "fase": "desmobilizacao",
                "driver": "projeto",
                "custo_fixo_total": 500_000.0,
            },
        ]
        result = fn(items, duracao_semanas=n_semanas)
        assert result["semanal"][n_semanas - 1] == pytest.approx(500_000.0, abs=0.05)

    def test_demob_zero_em_outras_semanas(self):
        fn = _import()
        n_semanas = 10
        items = [
            {
                "tipo": "MOB",
                "fase": "desmobilizacao",
                "driver": "projeto",
                "custo_fixo_total": 500_000.0,
            },
        ]
        result = fn(items, duracao_semanas=n_semanas)
        for s in range(n_semanas - 1):
            assert result["semanal"][s] == pytest.approx(0.0, abs=0.01)


# ---------------------------------------------------------------------------
# Conservação: total_distribuido ≈ total_original
# ---------------------------------------------------------------------------


class TestConservacao:
    def test_soma_total_distribuida_igual_total_original(self):
        """total_mob + total_operacao + total_demob == sum(semanal.values())."""
        fn = _import()
        result = fn(_ITEMS_PADRAO, duracao_semanas=52)

        total_original = result["total_mob"] + result["total_operacao"] + result["total_demob"]
        total_distribuido = sum(result["semanal"].values())

        assert abs(total_distribuido - total_original) / total_original < 0.001

    def test_semanal_tem_duracao_semanas_entradas(self):
        """semanal deve ter exatamente duracao_semanas entradas."""
        fn = _import()
        n = 20
        result = fn(_ITEMS_PADRAO, duracao_semanas=n)
        assert len(result["semanal"]) == n

    def test_todas_semanas_indexadas_de_0_a_n_menos_1(self):
        fn = _import()
        n = 15
        result = fn(_ITEMS_PADRAO, duracao_semanas=n)
        assert set(result["semanal"].keys()) == set(range(n))


# ---------------------------------------------------------------------------
# Backward compat: item sem campo ``fase``
# ---------------------------------------------------------------------------


class TestBackwardCompat:
    def test_item_sem_fase_nao_gera_erro(self):
        """Item legado sem campo ``fase`` não causa exceção — é ignorado."""
        fn = _import()
        items_legado = [
            {"categoria": "MOB", "driver": "projeto", "custo_fixo_total": 819_636.54},
        ]
        result = fn(items_legado, duracao_semanas=20)
        assert result["total_mob"] == pytest.approx(0.0, abs=0.01)
        assert result["total_demob"] == pytest.approx(0.0, abs=0.01)
        assert result["total_operacao"] == pytest.approx(0.0, abs=0.01)

    def test_itens_mistos_fases_e_legado(self):
        """Mix de itens com e sem fase: apenas os com fase são processados."""
        fn = _import()
        items = [
            # Legado (sem fase)
            {"categoria": "MOB", "driver": "projeto", "custo_fixo_total": 100_000.0},
            # Com fase
            {"tipo": "MOB", "fase": "mobilizacao", "driver": "projeto", "custo_fixo_total": 200_000.0},
        ]
        result = fn(items, duracao_semanas=10)
        # Apenas o item com fase é contado
        assert result["total_mob"] == pytest.approx(200_000.0, abs=0.05)

    def test_lista_vazia_retorna_zeros(self):
        fn = _import()
        result = fn([], duracao_semanas=10)
        assert result["total_mob"] == pytest.approx(0.0)
        assert result["total_operacao"] == pytest.approx(0.0)
        assert result["total_demob"] == pytest.approx(0.0)
        assert sum(result["semanal"].values()) == pytest.approx(0.0)

    def test_fase_com_driver_nao_reconhecido_e_ignorado(self):
        """Item com `fase` presente mas nenhuma combinação fase/driver bate em
        nenhum dos ramos (ex.: desmobilizacao com driver != 'projeto') —
        o loop simplesmente segue para o próximo item sem alterar totais."""
        fn = _import()
        items = [
            {"tipo": "MOB", "fase": "desmobilizacao", "driver": "mensal", "custo_fixo_total": 50_000.0},
            {"tipo": "MOB", "fase": "mobilizacao", "driver": "projeto", "custo_fixo_total": 200_000.0},
        ]
        result = fn(items, duracao_semanas=10)
        assert result["total_demob"] == pytest.approx(0.0)
        assert result["total_mob"] == pytest.approx(200_000.0, abs=0.05)


# ---------------------------------------------------------------------------
# Múltiplos itens por fase
# ---------------------------------------------------------------------------


class TestMultiplosItensPorFase:
    def test_dois_itens_mobilizacao_somam(self):
        """Dois itens de mobilização devem ser somados."""
        fn = _import()
        items = [
            {"tipo": "MOB", "fase": "mobilizacao", "driver": "projeto", "custo_fixo_total": 300_000.0},
            {"tipo": "MOB", "fase": "mobilizacao", "driver": "projeto", "custo_fixo_total": 150_000.0},
        ]
        result = fn(items, duracao_semanas=10)
        assert result["total_mob"] == pytest.approx(450_000.0, abs=0.05)
        assert result["semanal"][0] == pytest.approx(450_000.0, abs=0.05)

    def test_conservacao_tres_fases_completo(self):
        """Conservação com itens MATEC_GUARULHOS (ADR-105 §7.1)."""
        from concilium.domain.constants import SEMANAS_POR_MES

        fn = _import()
        custo_mensal = 75_000.0
        duracao_semanas = 108  # 27 meses × 4 semanas ≈ 108

        items = [
            {"tipo": "MOB", "fase": "mobilizacao", "driver": "projeto", "custo_fixo_total": 2_044_560.87},
            {"tipo": "MOB", "fase": "operacao", "driver": "mensal", "custo_fixo_mensal": custo_mensal},
            {"tipo": "MOB", "fase": "desmobilizacao", "driver": "projeto", "custo_fixo_total": 408_912.17},
        ]
        result = fn(items, duracao_semanas=duracao_semanas)

        total_esperado = 2_044_560.87 + custo_mensal * (duracao_semanas / SEMANAS_POR_MES) + 408_912.17
        soma = sum(result["semanal"].values())
        assert abs(soma - total_esperado) / total_esperado < 0.001

    def test_duracao_semanas_zero_skips_semanal_assignment_for_all_fases(self):
        """Edge case duracao_semanas=0: totals are still accumulated (totais não
        dependem de duracao_semanas > 0), but the `if duracao_semanas > 0` guards
        in each fase branch prevent writing into the (empty) `semanal` dict."""
        fn = _import()
        items = [
            {"tipo": "MOB", "fase": "mobilizacao", "driver": "projeto", "custo_fixo_total": 1000.0},
            {"tipo": "MOB", "fase": "operacao", "driver": "mensal", "custo_fixo_mensal": 500.0},
            {"tipo": "MOB", "fase": "desmobilizacao", "driver": "projeto", "custo_fixo_total": 300.0},
        ]
        result = fn(items, duracao_semanas=0)

        assert result["total_mob"] == 1000.0
        assert result["total_demob"] == 300.0
        assert result["semanal"] == {}
