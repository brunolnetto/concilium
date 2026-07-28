"""Testes ADR-162 Fase 3 (D4) — permanência/custo de 1 frente robustos a rampa.

Cobre `_sum_1frente_cost`/`_calc_custo_cron` e `_resolve_permanencia_e_custo_total_ajustados`
(skill 05, `_dimensionamento_itens.py`/`_dimensionamento_orquestracao.py`):

  - a versão anterior (ADR-091) dividia o agregado multi-frente (`team_weeks`/`custo_total`)
    por um único `num_equipes_paralelas` constante — exato só quando o número de frentes é
    constante em todas as semanas ativas (`team_weeks/max_n == ativos`)
  - com rampa (num_equipes variando semana a semana), essa divisão SEMPRE subestima ou empata
    com a permanência real (`team_weeks/max_n <= ativos`, nunca `>`, pela definição de `max_n`)
  - a correção soma a taxa semanal de 1 frente de referência semana a semana
    (`_sum_1frente_cost`), sem depender de nenhum `num_equipes_paralelas` — robusta a
    qualquer forma de rampa (mobilização parcial, lesão climática, etc.)
  - verificado numericamente contra o benchmark AGIS: agrega ~+6,55% no custo_direto
    (`test_cost_decomposition_adr104.py::test_agis_custo_direto_matches_reference`),
    puxado majoritariamente por eap-1_6 (team_weeks=72, ativos=25, max_n=4 —
    72/4=18 semanas estimadas vs. 25 reais, ~28% de subestimação antes da correção)
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from concilium.domain.constants import SEMANAS_POR_MES

_MANIFESTS = Path(__file__).resolve().parents[4] / "src" / "concilium" / "application" / "skills" / "manifests"


def _load_mod(skill_dir: str, mod_name: str):
    key = f"_adr162_d4_test_{skill_dir}_{mod_name}"
    if key in sys.modules:
        return sys.modules[key]
    path = _MANIFESTS / skill_dir / f"{mod_name}.py"
    if not path.exists():
        path = _MANIFESTS / skill_dir / mod_name / "__init__.py"
    spec = importlib.util.spec_from_file_location(key, path)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[key] = mod
    spec.loader.exec_module(mod)
    return mod


def _h05():
    return _load_mod("05-equipes-e-alocacao", "_skill_helpers")


def _make_cron(seq: list[int], assigned_resources: dict | None = None):
    periodos = {}
    for i, n in enumerate(seq):
        d = MagicMock()
        d.num_equipes = n
        d.eficiencia = 1.0
        periodos[f"2026-W{i + 1:02d}"] = d
    cron = MagicMock()
    cron.distribuicao_semanal = periodos
    cron.assigned_resources = assigned_resources or {}
    return cron


class TestSum1FrenteCost:
    """`_sum_1frente_cost`: taxa semanal de 1 frente somada só nas semanas ativas,
    sem multiplicar por num_equipes — nunca depende de quantas frentes rodaram em paralelo."""

    def test_semanas_inativas_nao_contam(self):
        h = _h05()
        cron = _make_cron([0, 0, 0])
        custo = h._sum_1frente_cost(list(cron.distribuicao_semanal.values()), fixo_sem_comb=1000.0, comb_nominal=0.0)
        assert custo == 0.0

    def test_indiferente_ao_numero_de_frentes_por_semana(self):
        """A mesma taxa semanal é somada uma vez por semana ativa — 1 frente ou 6, o
        custo de referência de UMA frente por semana é o mesmo."""
        h = _h05()
        periodos_1 = list(_make_cron([1, 1, 1]).distribuicao_semanal.values())
        periodos_6 = list(_make_cron([6, 6, 6]).distribuicao_semanal.values())
        custo_1 = h._sum_1frente_cost(periodos_1, fixo_sem_comb=1000.0, comb_nominal=200.0)
        custo_6 = h._sum_1frente_cost(periodos_6, fixo_sem_comb=1000.0, comb_nominal=200.0)
        assert custo_1 == custo_6 == pytest.approx(3 * 1200.0)

    def test_rampa_soma_so_semanas_ativas_independente_do_pico(self):
        """Rampa 1→3→1: 7 semanas ativas, custo de 1 frente = taxa_semanal × 7 —
        não é afetado pelo pico de 3 frentes em nenhuma semana."""
        h = _h05()
        periodos = list(_make_cron([1, 1, 3, 3, 3, 1, 1]).distribuicao_semanal.values())
        custo = h._sum_1frente_cost(periodos, fixo_sem_comb=3450.87, comb_nominal=229.99)
        assert custo == pytest.approx(7 * (3450.87 + 229.99), rel=1e-6)


class TestResolvePermanenciaECustoTotalAjustados:
    """`_resolve_permanencia_e_custo_total_ajustados`: permanência = ativos/SEMANAS_POR_MES
    (contagem de semanas, não ponderada por num_equipes) — corrige o viés de subestimação
    da versão anterior (ADR-091) quando o número de frentes varia."""

    def test_sem_rampa_bate_com_permanencia_meses(self):
        """N constante (3 equipes, 5 semanas ativas) — nenhuma rampa, resultado exato."""
        h = _h05()
        cron = _make_cron([3, 3, 3, 3, 3])
        _custo_total, ativos, _comb_ef, _fixo_mensal, _team_weeks, custo_ocioso, custo_1frente = h._calc_custo_cron(
            cron, custo_mo=6000.0, custo_eq=3000.0, custo_comb=900.0
        )
        permanencia, custo_total_final = h._resolve_permanencia_e_custo_total_ajustados(
            ativos, custo_1frente, custo_mat=0.0, custo_ocioso=custo_ocioso, custo_mob_desmob=0.0
        )
        assert permanencia == pytest.approx(round(5 / SEMANAS_POR_MES, 4))

    def test_rampa_nao_subestima_permanencia(self):
        """Rampa 1→3→1 ao longo de 7 semanas ativas: permanência deve refletir as 7
        semanas reais (~1,61 meses), não `team_weeks/max_n` (13/3≈4,33 semanas, ~0,9966
        meses) — o viés de subestimação da versão anterior (ADR-091) que esta fase corrige."""
        h = _h05()
        cron = _make_cron([1, 1, 3, 3, 3, 1, 1])
        _custo_total, ativos, _comb_ef, _fixo_mensal, _team_weeks, custo_ocioso, custo_1frente = h._calc_custo_cron(
            cron, custo_mo=10000.0, custo_eq=5000.0, custo_comb=1000.0
        )
        permanencia, _custo_total_final = h._resolve_permanencia_e_custo_total_ajustados(
            ativos, custo_1frente, custo_mat=0.0, custo_ocioso=custo_ocioso, custo_mob_desmob=0.0
        )
        permanencia_antiga_subestimada = round((13 / 3) / SEMANAS_POR_MES, 4)
        assert permanencia == pytest.approx(round(7 / SEMANAS_POR_MES, 4))
        assert permanencia > permanencia_antiga_subestimada
        assert permanencia_antiga_subestimada == pytest.approx(0.9966, abs=1e-3)

    def test_custo_mat_ocioso_mob_desmob_somados_ao_custo_1frente(self):
        h = _h05()
        cron = _make_cron([2, 2, 2])
        _custo_total, ativos, _comb_ef, _fixo_mensal, _team_weeks, custo_ocioso, custo_1frente = h._calc_custo_cron(
            cron, custo_mo=6000.0, custo_eq=3000.0, custo_comb=0.0
        )
        _permanencia, custo_total_final = h._resolve_permanencia_e_custo_total_ajustados(
            ativos, custo_1frente, custo_mat=500.0, custo_ocioso=100.0, custo_mob_desmob=200.0
        )
        permanencia_esperada = round(ativos / SEMANAS_POR_MES, 4)
        esperado = round(custo_1frente + 500.0 * permanencia_esperada + 100.0 + 200.0, 2)
        assert custo_total_final == pytest.approx(esperado)


class TestCalcCustoCronRetornaCusto1Frente:
    def test_custo_1frente_menor_ou_igual_ao_agregado_quando_ha_multiplas_frentes(self):
        """Com >1 frente em alguma semana, o custo de 1 frente (não multiplicado) é
        estritamente menor que o agregado multi-frente (`custo_total`)."""
        h = _h05()
        cron = _make_cron([3, 3, 3])
        custo_total, _ativos, _comb_ef, _fixo_mensal, _team_weeks, _custo_ocioso, custo_1frente = h._calc_custo_cron(
            cron, custo_mo=6000.0, custo_eq=3000.0, custo_comb=900.0
        )
        assert custo_1frente < custo_total
        assert custo_1frente == pytest.approx(custo_total / 3)

    def test_custo_1frente_igual_ao_agregado_quando_uma_frente_por_semana(self):
        h = _h05()
        cron = _make_cron([1, 1, 1])
        custo_total, _ativos, _comb_ef, _fixo_mensal, _team_weeks, _custo_ocioso, custo_1frente = h._calc_custo_cron(
            cron, custo_mo=6000.0, custo_eq=3000.0, custo_comb=900.0
        )
        assert custo_1frente == pytest.approx(custo_total)
