"""ADR-148: eta_jornada = (horas_dia - horas_improdutivas_dia) / horas_dia.

Cobre:
  - _build_dist_cell: fator_jornada entra em praticabilidade (η_p), lado a lado de
    fator_clima/fator_calendario, e é exposto em DistribuicaoSemanal.fator_jornada.
  - _compute_productive_weeks (ADR-072): eta_jornada ENTRA na duração produtiva
    (ao contrário de clima/calendário, que ficam fora por ADR-082-cons).
  - Não-regressão: eta_jornada=1.0 (default de teste) reproduz exatamente o
    comportamento pré-ADR-148.
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from types import ModuleType

_ROOT = Path(__file__).parent.parent.parent.parent.parent / "src/concilium/application/skills/manifests"


def _load(mod_name: str, rel_path: str) -> ModuleType:
    spec = importlib.util.spec_from_file_location(mod_name, _ROOT / rel_path)
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    sys.modules[mod_name] = mod
    spec.loader.exec_module(mod)  # type: ignore[union-attr]
    return mod


from concilium.application.skills import run_cronograma as _run_cronograma  # noqa: E402

assert _run_cronograma
_cron = sys.modules["_concilium_skillpkg_04_cronograma.skill"]


class TestBuildDistCellFatorJornada:
    def test_default_fator_jornada_e_1_sem_regressao(self):
        cell = _cron._build_dist_cell(
            producao_semanal_base=100.0,
            num_eq=2,
            n_max=2,
            fator_clima=1.0,
            fator_calendario=1.0,
            quantitativo=10_000.0,
            qtd_acumulada=0.0,
        )
        assert cell.fator_jornada == 1.0
        assert cell.qtd_executada == 200.0

    def test_fator_jornada_reduz_praticabilidade_e_producao(self):
        cell = _cron._build_dist_cell(
            producao_semanal_base=100.0,
            num_eq=2,
            n_max=2,
            fator_clima=1.0,
            fator_calendario=1.0,
            quantitativo=10_000.0,
            qtd_acumulada=0.0,
            fator_jornada=0.9375,
        )
        assert cell.fator_jornada == 0.9375
        assert cell.eta_p == 0.9375
        assert cell.qtd_executada == 100.0 * 2 * 0.9375
        assert cell.fator_total == cell.eta_s * cell.eta_p * cell.eta_w

    def test_fator_jornada_multiplica_com_clima_e_calendario(self):
        cell = _cron._build_dist_cell(
            producao_semanal_base=100.0,
            num_eq=2,
            n_max=2,
            fator_clima=0.8,
            fator_calendario=0.9,
            quantitativo=10_000.0,
            qtd_acumulada=0.0,
            fator_jornada=0.9375,
        )
        assert cell.eta_p == round(0.8 * 0.9 * 0.9375, 4)


class TestComputeProductiveWeeksEtaJornada:
    """ADR-072/ADR-148: eta_jornada entra na duração; clima/calendário não (ADR-082-cons)."""

    def _make_canonical(self, eap_items, eta_jornada=1.0):
        from types import SimpleNamespace

        regime = SimpleNamespace(horas_dia=8, dias_semana=5, eta_jornada=eta_jornada)
        projeto = SimpleNamespace(regime_trabalho=regime)
        return SimpleNamespace(projeto=projeto, eap=eap_items)

    def _eap_item(self, quantitativo=80.0):
        from types import SimpleNamespace

        return SimpleNamespace(item_id="ITEM-A", quantitativo=quantitativo, cpu_id="CPU-A")

    def test_eta_jornada_1_reproduz_formula_original(self):
        canonical = self._make_canonical([self._eap_item(quantitativo=80.0)], eta_jornada=1.0)
        cpu = {"codigo": "CPU-A", "producao_id_ref": "PROD-A"}
        prod_lookup = {"PROD-A": {"producao_horaria": 2.0}}
        result = _cron._compute_productive_weeks("ITEM-A", 1, canonical, {"CPU-A": cpu}, prod_lookup, [])
        # P=2.0, horas=8, dias=5, eta_jornada=1.0, n=1 → prod_per_week=80 → ceil(80/80)=1
        assert result == 1

    def test_eta_jornada_reduzido_aumenta_duracao(self):
        canonical = self._make_canonical([self._eap_item(quantitativo=80.0)], eta_jornada=0.9375)
        cpu = {"codigo": "CPU-A", "producao_id_ref": "PROD-A"}
        prod_lookup = {"PROD-A": {"producao_horaria": 2.0}}
        result = _cron._compute_productive_weeks("ITEM-A", 1, canonical, {"CPU-A": cpu}, prod_lookup, [])
        # prod_per_week = 2.0*8*5*0.9375 = 75 → ceil(80/75) = 2
        assert result == 2
