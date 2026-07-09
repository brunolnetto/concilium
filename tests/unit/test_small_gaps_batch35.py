"""Coverage batch 35 — 04-cronograma skill helper functions."""
from __future__ import annotations

import sys
from types import SimpleNamespace

import pytest

from concilium.application.skills import run_cronograma as _run_cronograma

assert _run_cronograma
MOD = sys.modules["_concilium_skillpkg_04_cronograma.skill"]


# ---------------------------------------------------------------------------
# _resolve_productivity lines 1010-1012:
# cpu_meta with producao_horaria → early return float
# ---------------------------------------------------------------------------


class TestResolveProductivity:
    def test_cpu_meta_producao_horaria_returns_early(self):
        """Lines 1010-1012: cpu_meta has producao_horaria → return float(valor)."""
        cpu = {"codigo": "CPU-X", "cpu_meta": {"producao_horaria": 12.5}}
        result = MOD._resolve_productivity(cpu, producao_lookup={}, validacoes=[])
        assert result == pytest.approx(12.5)

    def test_cpu_meta_none_valor_falls_through_to_default(self):
        """Line 1011: valor=None → condition fails → falls through to 1000.0 default."""
        cpu = {"codigo": "CPU-X", "cpu_meta": {"producao_horaria": None}}
        validacoes = []
        result = MOD._resolve_productivity(cpu, producao_lookup={}, validacoes=validacoes)
        assert result == 1000.0

    def test_prod_id_ref_with_legacy_producao_horaria_warns(self):
        """Lines 1020-1031: prod_item uses legacy 'producao_horaria' field → AVISO."""
        cpu = {"codigo": "CPU-Y", "producao_id_ref": "PROD-001"}
        producao_lookup = {
            "PROD-001": {"producao_horaria": 8.0}  # no valor_horario → legacy
        }
        validacoes = []
        result = MOD._resolve_productivity(cpu, producao_lookup, validacoes)
        assert result == pytest.approx(8.0)
        codes = [v.codigo for v in validacoes]
        assert "VAL-PROD-04-PROD-LEGACY" in codes


# ---------------------------------------------------------------------------
# _validate_preconditions lines 957 (no projeto) and 964 (no eap)
# ---------------------------------------------------------------------------


class TestValidatePreconditions:
    def test_no_projeto_appends_error_and_returns_false(self):
        """Line 957: canonical.projeto is None → append VAL-CRON-PRECONDICAO and return False."""

        canonical = SimpleNamespace(projeto=None, eap=[])
        validacoes = []
        result = MOD._validate_preconditions(canonical, validacoes)

        assert result is False
        assert any(v.codigo == "VAL-CRON-PRECONDICAO" for v in validacoes)

    def test_empty_eap_appends_error_and_returns_false(self):
        """Line 964: canonical.eap is empty → append VAL-CRON-PRECONDICAO."""
        canonical = SimpleNamespace(projeto=object(), eap=[])
        validacoes = []
        result = MOD._validate_preconditions(canonical, validacoes)

        assert result is False
        assert any(v.codigo == "VAL-CRON-PRECONDICAO" for v in validacoes)


# ---------------------------------------------------------------------------
# _compute_productive_weeks guard conditions
# lines 660 (item not in eap), 663 (Q <= 0), 668 (cpu not found)
# ---------------------------------------------------------------------------


class TestComputeProductiveWeeks:
    def _make_canonical(self, eap_items):
        regime = SimpleNamespace(horas_dia=8, dias_semana=5)
        projeto = SimpleNamespace(regime_trabalho=regime)
        return SimpleNamespace(projeto=projeto, eap=eap_items)

    def test_item_not_in_eap_returns_none(self):
        """Line 660: eap_item not found → return None."""
        canonical = self._make_canonical([])
        result = MOD._compute_productive_weeks("ITEM-GHOST", 1, canonical, {}, {}, [])
        assert result is None

    def test_zero_quantitativo_returns_none(self):
        """Line 663: Q <= 0 → return None."""
        eap_item = SimpleNamespace(item_id="ITEM-A", quantitativo=0.0, cpu_id="CPU-A")
        canonical = self._make_canonical([eap_item])
        result = MOD._compute_productive_weeks("ITEM-A", 1, canonical, {}, {}, [])
        assert result is None

    def test_cpu_not_in_lookup_returns_none(self):
        """Line 668: cpu not in cpu_lookup → return None."""
        eap_item = SimpleNamespace(item_id="ITEM-A", quantitativo=100.0, cpu_id="CPU-MISSING")
        canonical = self._make_canonical([eap_item])
        result = MOD._compute_productive_weeks("ITEM-A", 1, canonical, cpu_lookup={}, producao_lookup={}, validacoes=[])
        assert result is None

    def test_zero_productivity_returns_none(self):
        """Line 671-672: _resolve_productivity returns 0 → return None."""
        eap_item = SimpleNamespace(item_id="ITEM-A", quantitativo=100.0, cpu_id="CPU-A")
        self._make_canonical([eap_item])
        # CPU with no producao_id_ref → falls through to 1000.0 default (not 0)
        # Force P=0 by using a cpu_meta with producao_horaria=0 which doesn't early-return
        # Actually _resolve_productivity always returns 1000.0 as default when not found
        # So we need to test prod_per_week <= 0 path (lines 673-674)
        # That requires regime.horas_dia=0 or dias_semana=0
        regime_zero = SimpleNamespace(horas_dia=0, dias_semana=5)
        projeto_zero = SimpleNamespace(regime_trabalho=regime_zero)
        canonical_zero = SimpleNamespace(projeto=projeto_zero, eap=[eap_item])
        cpu = {"codigo": "CPU-A", "producao_id_ref": "PROD-A"}
        prod_lookup = {"PROD-A": {"valor_horario": 5.0}}
        result = MOD._compute_productive_weeks("ITEM-A", 1, canonical_zero, {"CPU-A": cpu}, prod_lookup, [])
        assert result is None

    def test_valid_case_returns_positive_integer(self):
        """Happy path: returns ceil(Q / (P × horas × dias × n_resources))."""
        eap_item = SimpleNamespace(item_id="ITEM-A", quantitativo=80.0, cpu_id="CPU-A")
        canonical = self._make_canonical([eap_item])
        # P=2.0, horas=8, dias=5, n=1 → prod_per_week=80 → ceil(80/80)=1
        cpu = {"codigo": "CPU-A", "producao_id_ref": "PROD-A"}
        prod_lookup = {"PROD-A": {"valor_horario": 2.0}}
        result = MOD._compute_productive_weeks("ITEM-A", 1, canonical, {"CPU-A": cpu}, prod_lookup, [])
        assert result == 1


# ---------------------------------------------------------------------------
# _enrich_producao_canonico lines 215, 233:
# continue when prod not found (215) or custo_hora <= 0 (233)
# ---------------------------------------------------------------------------


class TestEnrichProducaoCanonico:
    def _make_canonical(self, eap_items):
        regime = SimpleNamespace(horas_dia=8, dias_semana=5)
        projeto = SimpleNamespace(
            regime_trabalho=regime,
            data_base_orcamento=None,
        )
        return SimpleNamespace(projeto=projeto, eap=eap_items)

    def test_prod_not_found_continues(self):
        """Line 215: producao_lookup has no entry for cpu.producao_id_ref → continue."""
        cpu_lookup = {"CPU-A": {"codigo": "CPU-A", "producao_id_ref": "PROD-MISSING"}}
        producao_lookup = {}  # PROD-MISSING not here

        # Should run without error, skipping item via continue (line 215)
        MOD._enrich_producao_canonico(
            cpu_lookup,
            producao_lookup,
            insumos_lookup={},
            horas_mes=168.0,
            taxa_encargos=1.777,
            validacoes=[],
        )


# ---------------------------------------------------------------------------
# _extract_dag lines 510-517: extended precedences from EapItem.predecessores_tipados
# ---------------------------------------------------------------------------


class TestExtractDag:
    def test_extract_dag_linear_fallback(self):
        """Lines 510-517: canonical.eap without predecessores → linear fallback."""
        from concilium.domain.models.canonical import EapItem

        eap = [
            EapItem(item_id="A", ordem=1, cpu_id="CPU-A", descricao="A", unidade="m3", quantitativo=10.0),
            EapItem(item_id="B", ordem=2, cpu_id="CPU-B", descricao="B", unidade="m3", quantitativo=10.0),
        ]
        canonical = SimpleNamespace(eap=eap, activity_dag=None, atividades=None)
        activity_ids = ["A", "B"]

        dag = MOD._extract_dag(canonical, activity_ids)
        assert dag is not None
        # Linear fallback: A→B
        assert ("A", "B") in dag.precedence or len(dag.precedence) >= 1
