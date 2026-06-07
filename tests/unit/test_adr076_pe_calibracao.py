"""Testes ADR-076 — Calibração de PU e diagnóstico quantitativo de frentes.

Cobre as Opções C e D implementadas em skill-08 (_build_pe_for_equipe):
  - frentes_equivalentes_necessarias (custo_total_autonomo / venda_sem_bdi)
  - gap_pool_overhead (custo_operacional_real − custo_total_autonomo)
  - status_frentes threshold (OK ≤ 1.25, AVISO ≤ 1.5, CRITICO > 1.5)
  - pu_catalogo_unitario, pu_calibrado_unitario, ajuste_minimo_pct
  - gap_praticabilidade_abs, gap_pool_abs
  - VAL-FRENTES-NECESSARIAS-ALTA emitido acima do threshold
"""

from __future__ import annotations

# Importação direta do helper — sem carregar a skill completa.
import importlib.util
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest

_helpers_path = (
    Path(__file__).resolve().parent.parent.parent
    / "src"
    / "concilium"
    / "application"
    / "skills"
    / "manifests"
    / "08-consolidacao-financeira"
    / "_skill_helpers_a.py"
)
_spec = importlib.util.spec_from_file_location("skill08_helpers_a", _helpers_path)
_mod = importlib.util.module_from_spec(_spec)  # type: ignore[arg-type]
_spec.loader.exec_module(_mod)  # type: ignore[union-attr]

_build_pe_for_equipe = _mod._build_pe_for_equipe
_validate_frentes_necessarias = _mod._validate_frentes_necessarias
_bpe_process_equipe = _mod._bpe_process_equipe


# ── fixtures / helpers ──────────────────────────────────────────────────────


class _FakeSubtotalCat:
    def __init__(self, total: float):
        self.total = total


class _FakeSubtotal:
    def __init__(self, sem_bdi: float, com_bdi: float):
        self.sem_bdi = _FakeSubtotalCat(sem_bdi)
        self.com_bdi = _FakeSubtotalCat(com_bdi)


class _FakePlan:
    def __init__(self, item_id: str, qty: float, sem_bdi: float, com_bdi: float):
        self.item_id = item_id
        self.quantitativo = qty
        self.subtotal = _FakeSubtotal(sem_bdi, com_bdi)


def _make_equipe(
    item_id: str = "eap-01",
    custo_fixo_mensal: float = 100_000.0,
    permanencia_meses: float = 5.0,
    permanencia_efetiva_meses: float = 6.0,
    custo_total: float = 700_000.0,  # custo_operacional_real (inclui pool)
    custo_total_autonomo: float = 600_000.0,
) -> Any:
    return SimpleNamespace(
        item_id=item_id,
        custo_fixo_mensal=custo_fixo_mensal,
        permanencia_meses=permanencia_meses,
        permanencia_efetiva_meses=permanencia_efetiva_meses,
        custo_total=custo_total,
        custo_total_autonomo=custo_total_autonomo,
    )


def _make_plan(
    item_id: str = "eap-01",
    qty: float = 1000.0,
    pu_sem_bdi: float = 500.0,  # PU × Q = 500 000 sem BDI
    bdi_factor: float = 0.15,
) -> _FakePlan:
    sem_bdi_total = pu_sem_bdi * qty
    com_bdi_total = sem_bdi_total * (1.0 + bdi_factor)
    return _FakePlan(item_id, qty, sem_bdi_total, com_bdi_total)


# ── Unit tests ──────────────────────────────────────────────────────────────


class TestBuildPeForEquipeNewFields:
    """Novos campos ADR-076 calculados corretamente."""

    def test_gap_pool_overhead_isolado(self):
        """gap_pool_overhead = custo_total − custo_total_autonomo."""
        eq = _make_equipe(custo_total=700_000, custo_total_autonomo=600_000)
        pe = _build_pe_for_equipe(eq, {"eap-01": 575_000})
        assert pe is not None
        assert pe.gap_pool_overhead == pytest.approx(100_000.0, abs=1)

    def test_gap_pool_zero_sem_pool(self):
        """Sem pool (custo_total_autonomo == custo_total), gap_pool_overhead = 0."""
        eq = _make_equipe(custo_total=600_000, custo_total_autonomo=600_000)
        pe = _build_pe_for_equipe(eq, {"eap-01": 575_000})
        assert pe is not None
        assert pe.gap_pool_overhead == pytest.approx(0.0, abs=1)

    def test_frentes_necessarias_computado_com_planejamento(self):
        """frentes_equivalentes_necessarias = custo_total_autonomo / venda_sem_bdi."""
        eq = _make_equipe(custo_total_autonomo=600_000)
        # venda_sem_bdi = 500 * 1000 = 500_000
        plan = _make_plan(qty=1000.0, pu_sem_bdi=500.0)
        pe = _build_pe_for_equipe(eq, {"eap-01": 575_000}, {"eap-01": plan})
        assert pe is not None
        expected = 600_000 / 500_000  # 1.20
        assert pe.frentes_equivalentes_necessarias == pytest.approx(expected, abs=0.001)

    def test_frentes_necessarias_sem_planejamento_retorna_1(self):
        """Sem planejamento_por_item, frentes_equivalentes_necessarias = 1.0 (default)."""
        eq = _make_equipe(custo_total_autonomo=600_000)
        pe = _build_pe_for_equipe(eq, {"eap-01": 575_000}, None)
        assert pe is not None
        assert pe.frentes_equivalentes_necessarias == pytest.approx(1.0, abs=0.001)

    def test_pu_catalogo_unitario(self):
        """pu_catalogo_unitario = venda_sem_bdi / Q."""
        eq = _make_equipe(custo_total_autonomo=600_000)
        plan = _make_plan(qty=1000.0, pu_sem_bdi=500.0)  # total sem_bdi = 500_000
        pe = _build_pe_for_equipe(eq, {"eap-01": 575_000}, {"eap-01": plan})
        assert pe is not None
        assert pe.pu_catalogo_unitario == pytest.approx(500.0, abs=0.01)

    def test_pu_calibrado_maior_que_catalogo_quando_autonomo_supera(self):
        """pu_calibrado > pu_catalogo quando custo_autonomo/Q > PU_catalogo."""
        eq = _make_equipe(custo_total_autonomo=600_000)
        # PU_catalogo = 500_000 / 1000 = 500. custo_aut/Q = 600_000/1000 = 600. → calibrado = 600
        plan = _make_plan(qty=1000.0, pu_sem_bdi=500.0)
        pe = _build_pe_for_equipe(eq, {"eap-01": 575_000}, {"eap-01": plan})
        assert pe is not None
        assert pe.pu_calibrado_unitario == pytest.approx(600.0, abs=0.01)
        assert pe.ajuste_minimo_pct == pytest.approx(20.0, abs=0.1)  # +20%

    def test_pu_calibrado_igual_catalogo_quando_autonomo_menor(self):
        """pu_calibrado = pu_catalogo quando custo_autonomo/Q ≤ PU_catalogo."""
        eq = _make_equipe(custo_total_autonomo=400_000)
        # custo_aut/Q = 400. PU_cat = 500. → calibrado = 500 (catálogo já suficiente)
        plan = _make_plan(qty=1000.0, pu_sem_bdi=500.0)
        pe = _build_pe_for_equipe(eq, {"eap-01": 575_000}, {"eap-01": plan})
        assert pe is not None
        assert pe.pu_calibrado_unitario == pytest.approx(500.0, abs=0.01)
        assert pe.ajuste_minimo_pct == pytest.approx(0.0, abs=0.01)

    def test_gap_praticabilidade_abs_zero_quando_custo_proporcional_a_N(self):
        """gap_praticabilidade_abs ≈ 0 quando custo_autonomo == fixo × perm_efetiva (puramente proporcional a N).

        Contexto ADR-076 (fix):
          custo_base_catalogo = fixo × perm_nominal = 100k × 5 = 500k (1 equipe)
          N = perm_efetiva / perm_nominal = 6/5 = 1.2
          custo_base_N = custo_base × N = 500k × 1.2 = 600k
          gap_praticabilidade = custo_autonomo − custo_base_N = 600k − 600k = 0

        O gap de escala (N=1.2) já está em gap_escala_abs.
        gap_praticabilidade só captura RESIDUAL além da escala pura.
        """
        eq = _make_equipe(
            custo_fixo_mensal=100_000,
            permanencia_meses=5.0,
            permanencia_efetiva_meses=6.0,
            custo_total=700_000,
            custo_total_autonomo=600_000,  # = fixo × perm_efetiva = 100k×6 → residual=0
        )
        plan = _make_plan(qty=1000.0, pu_sem_bdi=500.0)
        pe = _build_pe_for_equipe(eq, {"eap-01": 575_000}, {"eap-01": plan})
        assert pe is not None
        assert pe.gap_praticabilidade_abs == pytest.approx(0.0, abs=1)

    def test_gap_praticabilidade_abs_positivo_quando_ha_desvio_real(self):
        """gap_praticabilidade_abs > 0 quando ha lesao climatica real no schedule.

        Formula ADR-083: gap_praticabilidade = custo_total_autonomo × (1 − fator_clima_v).
        Requer sched_por_item com fator_clima_v < 1 para capturar a perda.
          Schedule: 10 semanas × 1 equipe, 9 com fc=1.0 + 1 com fc=0.0
          fator_clima_v = 9/10 = 0.90 (exato)
          custo_autonomo = 650k → gap = 650k × 0.1 = 65k
        """
        eq = _make_equipe(
            custo_fixo_mensal=100_000,
            permanencia_meses=5.0,
            permanencia_efetiva_meses=6.0,
            custo_total=750_000,
            custo_total_autonomo=650_000,
        )
        plan = _make_plan(qty=1000.0, pu_sem_bdi=500.0)
        # 10 semanas, 9 boas (fc=1.0) + 1 com lesao total (fc=0.0) → fv=0.90 exato
        sched = _FakeSched(
            "eap-01",
            [
                _FakeDistSem(1, 1.0),
                _FakeDistSem(1, 1.0),
                _FakeDistSem(1, 1.0),
                _FakeDistSem(1, 1.0),
                _FakeDistSem(1, 1.0),
                _FakeDistSem(1, 1.0),
                _FakeDistSem(1, 1.0),
                _FakeDistSem(1, 1.0),
                _FakeDistSem(1, 1.0),
                _FakeDistSem(1, 0.0),  # 1 semana com lesao total
            ],
        )
        pe = _build_pe_for_equipe(eq, {"eap-01": 575_000}, {"eap-01": plan}, sched_por_item={"eap-01": sched})
        assert pe is not None
        # fv = 0.9 → gap = 650_000 × 0.1 = 65_000
        assert pe.gap_praticabilidade_abs == pytest.approx(65_000.0, abs=10)

    def test_decomposicao_custo_total_identidade(self):
        """custo_base + gap_escala + gap_praticabilidade + gap_pool == custo_total.

        Identidade fundamental do memorial de cálculo ADR-076/083:
        cada R$ de custo_total deve ser rastreável a uma fonte legítima.

        Com ADR-083: gap_praticabilidade = custo_total_aut × (1 - fv).
        Para a identidade valer: custo_base_N = custo_total_aut × fv.
          - fv = 0.8 (exato), custo_total_aut = 1_250_000 (pois 1_250k × 0.8 = 1_000k = fixo×perm_ef)
          - gap_praticab = 1_250k × 0.2 = 250k
          - gap_pool = 200k → custo_total = 1_450k
          - Identidade: 500k + 500k + 250k + 200k = 1_450k ✓
        """
        fixo = 100_000.0
        perm_nom = 5.0
        perm_ef = 10.0  # N=2 equipes
        custo_total_aut = 1_250_000.0  # custo_total_aut × fv = 1_250k × 0.8 = 1_000k = fixo×perm_ef
        custo_total = 1_450_000.0  # custo_total_aut + gap_pool = 1_250k + 200k

        eq = _make_equipe(
            custo_fixo_mensal=fixo,
            permanencia_meses=perm_nom,
            permanencia_efetiva_meses=perm_ef,
            custo_total=custo_total,
            custo_total_autonomo=custo_total_aut,
        )
        plan = _make_plan(qty=1000.0, pu_sem_bdi=500.0)
        # fv = 0.8 exato: 5 semanas × 2 equipes, 4 × fc=1.0 + 1 × fc=0.0
        # team_weeks = 10, active_weeks = 5, n_equipes_ef = 2.0, fv = 8/10 = 0.8
        sched = _FakeSched(
            "eap-01",
            [
                _FakeDistSem(2, 1.0),
                _FakeDistSem(2, 1.0),
                _FakeDistSem(2, 1.0),
                _FakeDistSem(2, 1.0),
                _FakeDistSem(2, 0.0),
            ],
        )
        pe = _build_pe_for_equipe(eq, {"eap-01": 575_000}, {"eap-01": plan}, sched_por_item={"eap-01": sched})
        assert pe is not None

        custo_base = fixo * perm_nom  # 500k
        N = perm_ef / perm_nom  # 2.0
        gap_escala = custo_base * (N - 1.0)  # 500k
        fv = 0.8
        gap_praticab = custo_total_aut * (1.0 - fv)  # 1_250k × 0.2 = 250k
        gap_pool = custo_total - custo_total_aut  # 200k

        # identidade: 500k + 500k + 250k + 200k = 1_450k = custo_total
        assert abs(custo_base + gap_escala + gap_praticab + gap_pool - custo_total) < 1.0

        # verificar campos PE
        assert pe.gap_escala_abs == pytest.approx(gap_escala, abs=1)
        assert pe.gap_praticabilidade_abs == pytest.approx(gap_praticab, abs=10)
        assert pe.gap_pool_overhead == pytest.approx(gap_pool, abs=1)

    def test_gap_pool_abs_alias(self):
        """gap_pool_abs é o mesmo valor que gap_pool_overhead."""
        eq = _make_equipe(custo_total=700_000, custo_total_autonomo=600_000)
        plan = _make_plan()
        pe = _build_pe_for_equipe(eq, {"eap-01": 575_000}, {"eap-01": plan})
        assert pe is not None
        assert pe.gap_pool_abs == pe.gap_pool_overhead

    def test_campos_legados_nao_regridem(self):
        """Campos originais (custo_fixo_equipe, delta, frentes_equivalentes) não regridem."""
        # custo_fixo_mensal=100k × perm_efetiva=6 = 600k
        eq = _make_equipe(
            custo_fixo_mensal=100_000,
            permanencia_efetiva_meses=6.0,
            custo_total=700_000,
            custo_total_autonomo=600_000,
        )
        pe = _build_pe_for_equipe(eq, {"eap-01": 575_000})
        assert pe is not None
        assert pe.custo_fixo_equipe == pytest.approx(600_000.0, abs=1)
        assert pe.custo_venda_cpu == pytest.approx(575_000.0, abs=1)
        assert pe.delta == pytest.approx(-25_000.0, abs=1)
        assert pe.status_validacao == "ERRO"
        assert pe.frentes_equivalentes == pytest.approx(700_000 / 600_000, abs=0.01)


class TestStatusFrentesThreshold:
    """Classificação de status_frentes pelo threshold ADR-076."""

    def _pe_with_frentes_nec(self, frentes_nec: float):
        """Cria PE com frentes_equivalentes_necessarias controlado via custo_total_autonomo."""
        eq = _make_equipe(custo_total_autonomo=frentes_nec * 500_000)
        plan = _make_plan(qty=1000.0, pu_sem_bdi=500.0)  # venda_sem_bdi = 500_000
        pe = _build_pe_for_equipe(eq, {"eap-01": 575_000}, {"eap-01": plan})
        assert pe is not None
        return pe

    def test_status_ok_abaixo_threshold(self):
        pe = self._pe_with_frentes_nec(1.10)
        assert pe.status_frentes == "OK"

    def test_status_ok_exato_limite(self):
        pe = self._pe_with_frentes_nec(1.25)
        assert pe.status_frentes == "OK"

    def test_status_aviso_entre_limites(self):
        pe = self._pe_with_frentes_nec(1.35)
        assert pe.status_frentes == "AVISO"

    def test_status_aviso_exato_limite_superior(self):
        pe = self._pe_with_frentes_nec(1.50)
        assert pe.status_frentes == "AVISO"

    def test_status_critico_acima_limite(self):
        pe = self._pe_with_frentes_nec(1.80)
        assert pe.status_frentes == "CRITICO"


class TestValidacaoFrentesNecessarias:
    """VAL-FRENTES-NECESSARIAS-ALTA: emissão e severidade."""

    def _build_pe_and_validate(self, frentes_nec: float) -> tuple:
        eq = _make_equipe(custo_total_autonomo=frentes_nec * 500_000)
        plan = _make_plan(qty=1000.0, pu_sem_bdi=500.0)
        pe = _build_pe_for_equipe(eq, {"eap-01": 575_000}, {"eap-01": plan})
        assert pe is not None
        validacoes: list = []
        _validate_frentes_necessarias(pe, validacoes)
        return pe, validacoes

    def test_nao_emite_quando_ok(self):
        _, validacoes = self._build_pe_and_validate(1.10)
        assert not any(v.codigo == "VAL-FRENTES-NECESSARIAS-ALTA" for v in validacoes)

    def test_emite_aviso_entre_1_25_e_1_5(self):
        _, validacoes = self._build_pe_and_validate(1.35)
        match = [v for v in validacoes if v.codigo == "VAL-FRENTES-NECESSARIAS-ALTA"]
        assert match, "Deve emitir VAL-FRENTES-NECESSARIAS-ALTA"
        assert match[0].status == "AVISO"

    def test_emite_erro_acima_1_5(self):
        _, validacoes = self._build_pe_and_validate(1.80)
        match = [v for v in validacoes if v.codigo == "VAL-FRENTES-NECESSARIAS-ALTA"]
        assert match, "Deve emitir VAL-FRENTES-NECESSARIAS-ALTA"
        assert match[0].status == "ERRO"

    def test_mensagem_contem_ajuste_pct(self):
        # frentes_nec = 1.40 → pu_calibrado = 700, pu_cat = 500 → ajuste = +40%
        _, validacoes = self._build_pe_and_validate(1.40)
        match = [v for v in validacoes if v.codigo == "VAL-FRENTES-NECESSARIAS-ALTA"]
        assert match
        assert "%" in match[0].mensagem

    def test_bpe_process_equipe_chama_validate_frentes(self):
        """_bpe_process_equipe integra a nova validação."""
        eq = _make_equipe(custo_total_autonomo=1.8 * 500_000)
        plan = _make_plan(qty=1000.0, pu_sem_bdi=500.0)
        validacoes: list = []
        venda_por_item = {"eap-01": 575_000}
        plan_por_item = {"eap-01": plan}
        pe = _bpe_process_equipe(eq, venda_por_item, validacoes, plan_por_item)
        assert pe is not None
        assert any(v.codigo == "VAL-FRENTES-NECESSARIAS-ALTA" for v in validacoes)


# ── helpers para testes de lesão ──────────────────────────────────────────────


class _FakeDistSem:
    """Simula DistribuicaoSemanal com fator_clima, fator_calendario."""

    def __init__(self, num_equipes: int = 2, fator_clima: float = 1.0, fator_calendario: float = 1.0):
        self.num_equipes = num_equipes
        self.fator_clima = fator_clima
        self.fator_calendario = fator_calendario
        self.fator_total = fator_clima * fator_calendario


class _FakeSched:
    """Simula ScheduledActivityCanonical com distribuicao_semanal."""

    def __init__(self, activity_id: str, semanas: list[_FakeDistSem]):
        self.activity_id = activity_id
        self.distribuicao_semanal = {f"2026-W{i + 1:02d}": s for i, s in enumerate(semanas)}


# ── Testes de Lesão de Produtividade (ADR-076 Justificativa) ─────────────────


class TestLesaoFromSched:
    """_lesao_from_sched extrai corretamente os fatores de DistribuicaoSemanal."""

    _lesao_from_sched = staticmethod(_mod._lesao_from_sched)

    def test_sem_clima_retorna_fator_1(self):
        sched = _FakeSched("eap-01", [_FakeDistSem(2, 1.0), _FakeDistSem(2, 1.0)])
        result = self._lesao_from_sched(sched)
        assert result["fator_clima"] == pytest.approx(1.0, abs=0.001)
        assert result["semanas_lesadas_clima"] == 0

    def test_fator_clima_ponderado(self):
        # 2 semanas: num_equipes=2 com fc=0.9 e num_equipes=2 com fc=1.0 → media=0.95
        sched = _FakeSched("eap-01", [_FakeDistSem(2, 0.9), _FakeDistSem(2, 1.0)])
        result = self._lesao_from_sched(sched)
        assert result["fator_clima"] == pytest.approx(0.95, abs=0.001)

    def test_semanas_lesadas_contagem(self):
        semanas = [_FakeDistSem(1, 0.85), _FakeDistSem(1, 0.90), _FakeDistSem(1, 1.0)]
        sched = _FakeSched("eap-01", semanas)
        result = self._lesao_from_sched(sched)
        # fator_clima < 0.90 → 1 semana (0.85 sim, 0.90 não, por ser ≥ 0.90)
        assert result["semanas_lesadas_clima"] == 1

    def test_active_weeks_e_team_weeks(self):
        # 3 semanas: num_equipes=[3, 3, 3]
        sched = _FakeSched("eap-01", [_FakeDistSem(3), _FakeDistSem(3), _FakeDistSem(3)])
        result = self._lesao_from_sched(sched)
        assert result["active_weeks"] == 3
        assert result["team_weeks"] == 9  # 3 × 3

    def test_sem_distribuicao_retorna_vazio(self):
        sched = _FakeSched("eap-01", [])
        result = self._lesao_from_sched(sched)
        assert result == {}


class TestLesaoFieldsInPE:
    """Campos de lesão aparecem corretamente no PontoEquilibrio."""

    def _make_sched(
        self, n_equipes: int = 2, semanas: int = 7, fator_clima: float = 1.0, semanas_lesadas: int = 0
    ) -> _FakeSched:
        dists = []
        for i in range(semanas):
            fc = 0.80 if i < semanas_lesadas else fator_clima
            dists.append(_FakeDistSem(n_equipes, fc))
        return _FakeSched("eap-01", dists)

    def test_n_equipes_efetivo_correto(self):
        """n_equipes_efetivo = team_weeks / active_weeks."""
        sched = self._make_sched(n_equipes=3, semanas=10)
        eq = _make_equipe()
        pe = _build_pe_for_equipe(eq, {"eap-01": 575_000}, sched_por_item={"eap-01": sched})
        assert pe is not None
        assert pe.n_equipes_efetivo == pytest.approx(3.0, abs=0.01)
        assert pe.semanas_ativas == 10

    def test_fator_clima_medio_calculado(self):
        """fator_clima_medio é a média ponderada por equipe×semana."""
        sched = self._make_sched(n_equipes=2, semanas=4, fator_clima=0.85, semanas_lesadas=4)
        eq = _make_equipe()
        pe = _build_pe_for_equipe(eq, {"eap-01": 575_000}, sched_por_item={"eap-01": sched})
        assert pe is not None
        # Todas as 4 semanas com fator < 0.90
        assert pe.fator_clima_medio == pytest.approx(0.80, abs=0.01)
        assert pe.semanas_lesadas_clima == 4

    def test_gap_escala_abs_dois_equipes(self):
        """gap_escala_abs = custo_base_catalogo × (N−1) para N=2."""
        # perm_nominal = 5m, custo_fixo_mensal = 100k → base = 500k
        # N = 2 → gap_escala = 500k × 1 = 500k
        sched = self._make_sched(n_equipes=2, semanas=7)
        eq = _make_equipe(
            custo_fixo_mensal=100_000,
            permanencia_meses=5.0,
            permanencia_efetiva_meses=7.0,  # ~2 teams × 3.5 weeks
        )
        pe = _build_pe_for_equipe(eq, {"eap-01": 575_000}, sched_por_item={"eap-01": sched})
        assert pe is not None
        expected_gap = 100_000 * 5.0 * (2.0 - 1.0)  # base × (N−1)
        assert pe.gap_escala_abs == pytest.approx(expected_gap, abs=100)

    def test_sem_sched_lesao_defaults(self):
        """Sem sched_por_item, campos de lesão ficam em defaults seguros."""
        eq = _make_equipe()
        pe = _build_pe_for_equipe(eq, {"eap-01": 575_000})
        assert pe is not None
        # defaults: n_equipes_efetivo derivado de perm_efetiva/perm_nominal
        assert pe.fator_clima_medio == pytest.approx(1.0, abs=0.001)
        assert pe.semanas_lesadas_clima == 0

    def test_diagnostico_lesao_menciona_clima_significativo(self):
        """diagnostico_lesao cita lesão climática quando semanas_lesadas > 0 e fc < 1."""
        sched = self._make_sched(n_equipes=1, semanas=10, semanas_lesadas=4, fator_clima=1.0)
        eq = _make_equipe(custo_total=600_000, custo_total_autonomo=600_000)
        pe = _build_pe_for_equipe(eq, {"eap-01": 575_000}, sched_por_item={"eap-01": sched})
        assert pe is not None
        # 4 semanas com fc=0.80 → lesão climática deve aparecer no diagnóstico
        assert pe.diagnostico_lesao is not None
        assert "sem." in pe.diagnostico_lesao.lower() or "lesao" in pe.diagnostico_lesao.lower()

    def test_diagnostico_lesao_menciona_escala(self):
        """diagnostico_lesao cita escala de equipes quando N>1."""
        sched = self._make_sched(n_equipes=4, semanas=12, fator_clima=1.0)
        eq = _make_equipe(custo_total=600_000, custo_total_autonomo=600_000)
        pe = _build_pe_for_equipe(eq, {"eap-01": 575_000}, sched_por_item={"eap-01": sched})
        assert pe is not None
        assert pe.diagnostico_lesao is not None
        assert "equipes" in pe.diagnostico_lesao.lower() or "escala" in pe.diagnostico_lesao.lower()


class TestFase4LeverGapPool:
    """ADR-084 Fase 4 — Lever fechar_gap_pool exibe predecessor_critico_id e overlap_semanas."""

    def _make_particao(
        self,
        overhead_ocioso: float = 80_000.0,
        economia_mob: float = 20_000.0,
        predecessor_critico_id: str | None = None,
        overlap_semanas: float = 0.0,
    ) -> Any:
        return SimpleNamespace(
            overhead_ocioso=overhead_ocioso,
            economia_mob=economia_mob,
            predecessor_critico_id=predecessor_critico_id,
            overlap_semanas=overlap_semanas,
        )

    def _lever_pool(self, pe: Any):
        """Extrai lever fechar_gap_pool ou None."""
        if pe is None:
            return None
        for lv in pe.levers_equilibrio or []:
            if lv.id == "fechar_gap_pool":
                return lv
        return None

    def test_lever_pool_exibe_predecessor_critico(self):
        """Lever inclui predecessor_critico_id na lista de restricoes quando definido."""
        particao = self._make_particao(predecessor_critico_id="eap-02", overlap_semanas=0.0)
        eq = _make_equipe(custo_total=700_000, custo_total_autonomo=600_000)
        pe = _build_pe_for_equipe(eq, {"eap-01": 575_000}, None, None, {"eap-01": particao})
        lv = self._lever_pool(pe)
        assert lv is not None
        assert any("eap-02" in r for r in lv.restricoes), (
            f"predecessor_critico_id 'eap-02' not found in lever restricoes: {lv.restricoes}"
        )

    def test_lever_pool_exibe_overlap_semanas(self):
        """Lever inclui overlap_semanas na lista de restricoes quando > 0."""
        particao = self._make_particao(overlap_semanas=3.5)
        eq = _make_equipe(custo_total=700_000, custo_total_autonomo=600_000)
        pe = _build_pe_for_equipe(eq, {"eap-01": 575_000}, None, None, {"eap-01": particao})
        lv = self._lever_pool(pe)
        assert lv is not None
        assert any("3.5" in r or "sobreposicao" in r.lower() for r in lv.restricoes), (
            f"overlap_semanas=3.5 not reflected in lever restricoes: {lv.restricoes}"
        )

    def test_lever_pool_omitido_quando_gap_nao_positivo(self):
        """Lever fechar_gap_pool não aparece quando gap_pool_abs <= 0 (pool vantajoso)."""
        eq = _make_equipe(custo_total=600_000, custo_total_autonomo=700_000)
        pe = _build_pe_for_equipe(eq, {"eap-01": 700_000})
        lv = self._lever_pool(pe)
        assert lv is None, "Lever não deve existir quando pool é vantajoso (gap_pool_overhead <= 0)"

    def test_lever_pool_sem_predecessor_nao_adiciona_campo(self):
        """Sem predecessor_critico_id definido, lever não tem entrada de predecessor."""
        particao = self._make_particao(predecessor_critico_id=None, overlap_semanas=0.0)
        eq = _make_equipe(custo_total=700_000, custo_total_autonomo=600_000)
        pe = _build_pe_for_equipe(eq, {"eap-01": 575_000}, None, None, {"eap-01": particao})
        lv = self._lever_pool(pe)
        assert lv is not None
        assert not any("predecessor" in r.lower() for r in lv.restricoes), (
            f"Lever should not contain predecessor when None: {lv.restricoes}"
        )

    def test_lever_pool_p_fracionario_overlap_longo(self):
        """Com p < 1 (sobreposição longa, ex.: 8 semanas), lever exibe overlap_semanas corretamente."""
        # Simula atividade com sobreposição de 8 semanas (p ≈ 0.75 de 10 semanas totais)
        particao = self._make_particao(
            predecessor_critico_id="eap-00",
            overlap_semanas=8.0,
        )
        eq = _make_equipe(custo_total=750_000, custo_total_autonomo=600_000)
        pe = _build_pe_for_equipe(eq, {"eap-01": 600_000}, None, None, {"eap-01": particao})
        lv = self._lever_pool(pe)
        assert lv is not None
        assert any("8.0" in r for r in lv.restricoes), (
            f"overlap_semanas=8.0 not found in lever restricoes: {lv.restricoes}"
        )
        assert any("eap-00" in r for r in lv.restricoes), (
            f"predecessor 'eap-00' not found in lever restricoes: {lv.restricoes}"
        )

    def test_lever_pool_multiplos_predecessores_mostra_critico(self):
        """Lever exibe apenas o predecessor_critico_id (não lista todos os predecessores)."""
        # Cenário: a3 tem predecessores a1 e a2, mas a1 é o crítico (maior sobreposição)
        particao = self._make_particao(
            predecessor_critico_id="a1",
            overlap_semanas=4.0,
        )
        eq = _make_equipe(custo_total=700_000, custo_total_autonomo=500_000)
        pe = _build_pe_for_equipe(eq, {"eap-01": 600_000}, None, None, {"eap-01": particao})
        lv = self._lever_pool(pe)
        assert lv is not None
        restricoes_text = " ".join(lv.restricoes)
        assert "a1" in restricoes_text, f"Critical predecessor 'a1' not in restricoes: {lv.restricoes}"
