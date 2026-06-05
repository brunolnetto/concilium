"""ADR-082-cons / NEP-035: consistência da base de cálculo (produtividade × custo).

Cobre:
  - _build_dist_cell: η_s (alocação), η_p (praticabilidade), η_w (gestão), q_max, perda_fisica
  - fator_total = η_s · η_p · η_w  (identidade verificável)
  - VAL-PROD-VS-PU: divergência de produtividade engine ↔ catálogo isolada do clima
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from types import ModuleType

_ROOT = Path(__file__).parent.parent.parent / "src/concilium/application/skills/manifests"


def _load(mod_name: str, rel_path: str) -> ModuleType:
    spec = importlib.util.spec_from_file_location(mod_name, _ROOT / rel_path)
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    sys.modules[mod_name] = mod
    spec.loader.exec_module(mod)  # type: ignore[union-attr]
    return mod


_cron = _load("_cron_skill_082", "04-cronograma/skill.py")
_cons = _load("_cons_helpers_082", "08-consolidacao-financeira/_skill_helpers_a.py")


# ── _build_dist_cell: eficiencia = utilização; fator_total = p_j × m_ij ──────


class TestBuildDistCell:
    def test_semana_pico_todos_os_eta_1(self):
        # n_j = n_max, clima=1, calend=1, sem fechamento → η_s=η_p=η_w=1
        cell = _cron._build_dist_cell(
            producao_semanal_base=100.0, num_eq=2, n_max=2,
            fator_clima=1.0, fator_calendario=1.0,
            quantitativo=10_000.0, qtd_acumulada=0.0,
        )
        assert cell.eta_s == 1.0
        assert cell.eta_p == 1.0
        assert cell.eta_w == 1.0
        assert abs(cell.fator_total - 1.0) < 1e-6
        assert cell.qtd_executada == 200.0  # 100 × 1 × 2
        assert cell.q_max_celula == 200.0
        assert cell.perda_fisica == 0.0

    def test_subalocacao_captura_eta_s(self):
        # n_j=1, n_max=2 → η_s=0.5; clima=1, calend=1
        cell = _cron._build_dist_cell(
            producao_semanal_base=100.0, num_eq=1, n_max=2,
            fator_clima=1.0, fator_calendario=1.0,
            quantitativo=10_000.0, qtd_acumulada=0.0,
        )
        assert abs(cell.eta_s - 0.5) < 1e-6
        assert cell.eta_p == 1.0
        assert cell.eta_w == 1.0
        assert abs(cell.fator_total - 0.5) < 1e-6
        assert cell.qtd_executada == 100.0  # 100 × 0.5
        assert cell.q_max_celula == 200.0   # referência = pico n_max=2
        assert abs(cell.perda_fisica - 100.0) < 1e-4  # q_max(200) - q_executada(100)

    def test_praticabilidade_captura_eta_p(self):
        # n_j=2, n_max=2, clima=0.8, calend=0.9 → η_p=0.72
        cell = _cron._build_dist_cell(
            producao_semanal_base=100.0, num_eq=2, n_max=2,
            fator_clima=0.8, fator_calendario=0.9,
            quantitativo=10_000.0, qtd_acumulada=0.0,
        )
        assert abs(cell.eta_s - 1.0) < 1e-6
        assert abs(cell.eta_p - 0.72) < 1e-6
        assert cell.eta_w == 1.0
        assert abs(cell.fator_total - 0.72) < 1e-6
        assert abs(cell.qtd_executada - 144.0) < 1e-4

    def test_fechamento_parcial_captura_eta_w(self):
        # n_j=2, n_max=2, clima=0.9, calend=0.8 → capacidade=144; remanescente=50 → η_w<1
        cell = _cron._build_dist_cell(
            producao_semanal_base=100.0, num_eq=2, n_max=2,
            fator_clima=0.9, fator_calendario=0.8,
            quantitativo=10_000.0, qtd_acumulada=9_950.0,
        )
        assert cell.qtd_executada == 50.0
        assert cell.eta_s == 1.0
        assert abs(cell.eta_p - 0.72) < 1e-6
        assert 0.0 < cell.eta_w < 1.0  # fechamento parcial
        # identidade: fator_total = η_s × η_p × η_w
        assert abs(cell.fator_total - cell.eta_s * cell.eta_p * cell.eta_w) < 1e-4

    def test_identidade_fator_total_eta_produto(self):
        # fator_total deve ser sempre η_s × η_p × η_w (identidade fundamental)
        for n_eq, n_max, clima, calend in [
            (1, 2, 0.8, 0.9), (2, 2, 1.0, 1.0), (1, 3, 0.6, 0.7),
        ]:
            cell = _cron._build_dist_cell(
                100.0, n_eq, n_max, clima, calend, 10_000.0, 0.0,
            )
            assert abs(cell.fator_total - cell.eta_s * cell.eta_p * cell.eta_w) < 1e-4, (
                f"identidade falhou para n_eq={n_eq}, n_max={n_max}, clima={clima}, calend={calend}"
            )

    def test_eficiencia_e_eta_w(self):
        # eficiencia (m_ij) deve ser igual a eta_w
        cell = _cron._build_dist_cell(100.0, 1, 2, 0.9, 0.8, 10_000.0, 0.0)
        assert abs(cell.eficiencia - cell.eta_w) < 1e-6

    def test_q_max_referencia_n_max(self):
        # q_max_celula = base × n_max (independente de n_j)
        cell = _cron._build_dist_cell(100.0, 1, 4, 0.8, 0.8, 10_000.0, 0.0)
        assert abs(cell.q_max_celula - 400.0) < 1e-4  # 100 × 4

    def test_eficiencia_nao_e_clima(self):
        # garante que eficiencia (utilização) != clima×calendário (conflação corrigida)
        cell = _cron._build_dist_cell(100.0, 2, 2, 0.5, 0.5, 10_000.0, 0.0)
        assert cell.eficiencia == 1.0   # η_w = 1 (sem fechamento parcial)
        assert abs(cell.fator_total - 0.25) < 1e-6  # = η_s(1) × η_p(0.25) × η_w(1)


# ── VAL-PROD-VS-PU: resíduo = fe_nec × fator_clima_medio ─────────────────────


def _pe(item_id: str, fe_nec: float, clima: float):
    from concilium.domain.models.canonical import PontoEquilibrio

    return PontoEquilibrio(
        item_id=item_id,
        custo_fixo_equipe=1000.0,
        custo_venda_cpu=1000.0,
        delta=0.0,
        delta_pct=0.0,
        status_validacao="OK",
        frentes_equivalentes_necessarias=fe_nec,
        fator_clima_medio=clima,
        pu_catalogo_unitario=10.0,
        pu_calibrado_unitario=10.0 * fe_nec,
    )


class TestValProdVsPU:
    def test_flag_quando_residuo_acima_de_1(self):
        # fe_nec=1.29, clima=1.00 → resíduo 1.29 (puro mismatch de P, sem clima)
        val = []
        _cons._validate_prod_vs_pu(_pe("eap-1_5", 1.29, 1.00), val)
        assert len(val) == 1
        assert val[0].codigo == "VAL-PROD-VS-PU"
        assert "P_engine > P_catálogo" in val[0].mensagem

    def test_flag_quando_residuo_abaixo_de_1(self):
        # fe_nec=0.84, clima=0.87 → resíduo 0.73 (engine mais barato)
        val = []
        _cons._validate_prod_vs_pu(_pe("eap-1_8", 0.84, 0.87), val)
        assert len(val) == 1
        assert "P_engine < P_catálogo" in val[0].mensagem

    def test_silencioso_quando_gap_e_puro_clima(self):
        # fe_nec ≈ 1/clima → resíduo ≈ 1 → consistente, sem flag
        val = []
        _cons._validate_prod_vs_pu(_pe("eap-x", 1.05, 0.95), val)  # 1.05×0.95 = 0.9975
        assert val == []
