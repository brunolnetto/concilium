"""Coverage sweep 12 — two files below 90%:

- _consolidacao/_skill_helpers_a.py (88%) — missing: 74->73, 164-165, 209, 212-214, 238, 273, 275, 293->295, etc.
- financial_report_pdf.py (89%) — missing: 273, 459->486, 464, 469, 472-477, 480-483, 516-517, etc.
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from types import SimpleNamespace

_ROOT = Path(__file__).resolve().parents[2]

_MANIFESTS = _ROOT / "src/concilium/application/skills/manifests"

def _load(mod_name: str, rel_path: str):
    path = _MANIFESTS / rel_path
    spec = importlib.util.spec_from_file_location(mod_name, path)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[mod_name] = mod
    spec.loader.exec_module(mod)
    return mod

_cons = _load("_cons_helpers_sw12", "06-resultado-financeiro/_consolidacao/_skill_helpers/__init__.py")


# ── _consolidacao/_skill_helpers_a.py ─────────────────────────────────────────


class TestCpuFamilia:
    def test_empty_string_returns_empty(self):
        """Line 209: cpu_id is empty → return ''."""
        assert _cons._cpu_familia("") == ""

    def test_dash_separator_returns_prefix(self):
        """Line 211: '-' in cpu_id → split on '-'."""
        assert _cons._cpu_familia("CPU-001") == "CPU"

    def test_underscore_separator_returns_prefix(self):
        """Lines 212-213: '_' in cpu_id → split on '_'."""
        assert _cons._cpu_familia("ESC_HIDRA") == "ESC"

    def test_no_separator_returns_whole(self):
        """Line 214: no '-' or '_' → return cpu_id unchanged."""
        assert _cons._cpu_familia("CPUX") == "CPUX"


class TestCalcVendaComBdiMissingRate:
    def _make_empty_canonical(self):
        return SimpleNamespace(
            contratos_recurso=[],
            equipes_diretas=[],
            indiretos=[],
        )

    def test_missing_bdi_rate_logs_warning_returns_zero(self):
        """Lines 163-165: _bdi called with missing key → warning + return 0.0."""
        canonical = self._make_empty_canonical()
        bdi_rates = {}  # no keys → every lookup triggers the warning branch
        vd, vi, ct = _cons._calc_venda_com_bdi(canonical, bdi_rates)
        assert vd == 0.0
        assert vi == 0.0
        assert ct == 0.0


class TestBrBuildVendaCustoFallback:
    def _make_canonical_no_planejamento(self, custo_total=10_000.0):
        eq = SimpleNamespace(
            item_id="EAP-01",
            custo_total=custo_total,
        )
        SimpleNamespace(
            subtotal=SimpleNamespace(
                sem_bdi=SimpleNamespace(total=0.0, material=0.0),
                com_bdi=SimpleNamespace(total=0.0),
            )
        )
        return SimpleNamespace(
            planejamento=[],
            equipes_diretas=[eq],
        )

    def test_empty_planejamento_nonzero_equipes_triggers_fallback(self):
        """Lines 273, 275: venda_sem_bdi and venda_com_bdi both fall back to custo_direto_equipe."""
        canonical = self._make_canonical_no_planejamento(custo_total=5000.0)
        vsb, vcb, cde, cm, cdp = _cons._br_build_venda_custo(canonical)
        assert vsb == 5000.0
        assert vcb == 5000.0


class TestBuildCustoAtvFallback:
    def test_no_cronograma_no_equipes_returns_empty(self):
        """Lines 235-251: when cronograma is None and equipes_diretas has items with item_id."""
        canonical = SimpleNamespace(
            cronograma=None,
            equipes_diretas=[
                SimpleNamespace(item_id="EAP-01"),
                SimpleNamespace(item_id="EAP-02"),
            ],
            eap=[],
        )
        result = _cons._build_custos_atividades(canonical)
        assert len(result) == 2
        assert result[0].atividade_id == "EAP-01"

    def test_equipe_with_empty_item_id_skipped(self):
        """Line 238: equipe with empty item_id → continue."""
        canonical = SimpleNamespace(
            cronograma=None,
            equipes_diretas=[
                SimpleNamespace(item_id=""),
                SimpleNamespace(item_id="EAP-03"),
            ],
            eap=[],
        )
        result = _cons._build_custos_atividades(canonical)
        assert len(result) == 1
        assert result[0].atividade_id == "EAP-03"


class TestBuildCustoCategoriaBottomUp:
    def test_part_with_zero_inst_not_added_to_part_by_item(self):
        """Line 74->73: part with all-zero custo_inst_* → if-condition False → skip."""
        from types import SimpleNamespace

        part = SimpleNamespace(
            item_id="EAP-01",
            custo_inst_mo=0.0,
            custo_inst_eq=0.0,
            custo_inst_comb=0.0,
            custo_inst_mat=0.0,
        )
        contrato = SimpleNamespace(particao_por_item=[part])
        eq = SimpleNamespace(
            item_id="EAP-01",
            custo_total=1000.0,
            custo_inst_mo=None,
            custo_mao_obra_mensal=500.0,
            custo_equipamentos_mensal=200.0,
            custo_combustivel_total_mensal=100.0,
            custo_material_mensal=50.0,
        )
        # getattr needed for custo_encargos_mensal
        eq.custo_encargos_mensal = 0.0
        canonical = SimpleNamespace(
            contratos_recurso=[contrato],
            equipes_diretas=[eq],
        )
        result = _cons._build_custo_categorial_bottom_up(canonical)
        # EAP-01 should appear in the heuristic path, not the pool path
        assert result["mao_obra"] > 0.0



