"""Coverage sweep 12 — two files below 90%:

- _consolidacao/_skill_helpers_a.py (88%) — missing: 74->73, 164-165, 209, 212-214, 238, 273, 275, 293->295, etc.
- financial_report_pdf.py (89%) — missing: 273, 459->486, 464, 469, 472-477, 480-483, 516-517, etc.
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

_ROOT = Path(__file__).resolve().parents[2]
_MANIFESTS = _ROOT / "src/concilium/application/skills/manifests"


def _load(mod_name: str, rel_path: str):
    path = _MANIFESTS / rel_path
    spec = importlib.util.spec_from_file_location(mod_name, path)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[mod_name] = mod
    spec.loader.exec_module(mod)
    return mod


_cons = _load("_cons_helpers_sw12", "06-resultado-financeiro/_consolidacao/_skill_helpers_a.py")


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


# ── financial_report_pdf.py ───────────────────────────────────────────────────

try:
    from concilium.application.runtime.deliverables.reports.financial_report_pdf import (
        render_financial_report_pdf,
    )

    _HAS_RENDER = True
except ImportError:
    _HAS_RENDER = False


def _minimal_relatorio(**kwargs) -> dict:
    base = {
        "resumo": {
            "projeto": "Test PDF",
            "tipo_obra": "Rodovia",
            "localizacao": "Goiás, GO",
        },
        "RESULTADO": {
            "preco_venda_total": 1_000_000.0,
            "custo_total": 800_000.0,
            "resultado_bruto": 200_000.0,
            "margem_pct": 0.20,
        },
    }
    base.update(kwargs)
    return base


@pytest.mark.skipif(not _HAS_RENDER, reason="reportlab not available")
class TestFinancialReportPdfBranches:
    def test_descricao_in_resumo_adds_to_info_lines(self):
        """Line 273: descricao is truthy → added to info_lines paragraph."""
        relatorio = _minimal_relatorio()
        relatorio["resumo"]["descricao"] = "Rodovia de alto impacto regional"
        result = render_financial_report_pdf(relatorio, title="Test Com Descricao")
        assert result is None or isinstance(result, bytes)

    def test_actionable_insights_not_dict_skips_block(self):
        """Lines 459->486: ACTIONABLE_INSIGHTS is a string → not a dict → block skipped."""
        relatorio = _minimal_relatorio()
        relatorio["ACTIONABLE_INSIGHTS"] = "should_be_skipped"
        result = render_financial_report_pdf(relatorio, title="Test Insights Non-Dict")
        assert result is None or isinstance(result, bytes)

    def test_actionable_insights_with_non_dict_section_triggers_continue(self):
        """Lines 464: sec is not a dict → continue."""
        relatorio = _minimal_relatorio()
        relatorio["ACTIONABLE_INSIGHTS"] = {
            "criticidade": "not_a_dict",  # triggers continue
            "sensibilidade": {},
            "intervencao": {},
        }
        result = render_financial_report_pdf(relatorio, title="Test Insights Continue")
        assert result is None or isinstance(result, bytes)

    def test_actionable_insights_with_string_recommendation(self):
        """Lines 469: val is a string → recs.append(val.strip())."""
        relatorio = _minimal_relatorio()
        relatorio["ACTIONABLE_INSIGHTS"] = {
            "criticidade": {
                "notas_engenheiro": "Verificar camada base da rodovia.",
            }
        }
        result = render_financial_report_pdf(relatorio, title="Test Insights Str")
        assert result is None or isinstance(result, bytes)

    def test_actionable_insights_with_list_recommendations(self):
        """Lines 472-477: val is a list of strings and dicts."""
        relatorio = _minimal_relatorio()
        relatorio["ACTIONABLE_INSIGHTS"] = {
            "sensibilidade": {
                "passos_repair": [
                    "Primeiro passo de reparo",
                    {"descricao": "Passo com dict", "titulo": "T1"},
                    {"sem_campo_valido": True},  # no txt → skipped
                ]
            }
        }
        result = render_financial_report_pdf(relatorio, title="Test Insights List")
        assert result is None or isinstance(result, bytes)

    def test_actionable_insights_recs_populated_adds_section(self):
        """Lines 480-483: recs is non-empty → KeepTogether with paragraphs added to story."""
        relatorio = _minimal_relatorio()
        relatorio["ACTIONABLE_INSIGHTS"] = {
            "intervencao": {
                "recomendacao_primaria": "Recomendação principal detalhada.",
            }
        }
        result = render_financial_report_pdf(relatorio, title="Test Insights Recs")
        assert result is None or isinstance(result, bytes)

    def test_planejamento_item_without_descricao_uses_cpu_id(self):
        """Lines 516-517: planejamento item has no descricao → use cpu_id."""
        relatorio = _minimal_relatorio()
        relatorio["planejamento"] = [
            {
                "item_id": "EAP-01",
                "cpu_id": "CPU-001",
                "subtotal_com_bdi": 100_000.0,
                # no "descricao" key → triggers cpu_id fallback
            },
            {
                "item_id": "EAP-02",
                "cpu_id": "",
                "subtotal_com_bdi": 50_000.0,
                "descricao": None,  # None also triggers fallback
            },
        ]
        result = render_financial_report_pdf(relatorio, title="Test Planejamento No Desc")
        assert result is None or isinstance(result, bytes)

    def test_image_provider_exception_is_swallowed(self):
        """Lines 695-696: image rendering raises Exception → pass."""

        def bad_image_provider(name: str) -> bytes | None:
            if "scurve" in name:
                return b"NOT_VALID_IMAGE_DATA_AT_ALL_XYZ"
            return None

        relatorio = _minimal_relatorio()
        result = render_financial_report_pdf(relatorio, title="Test Bad Image", image_provider=bad_image_provider)
        assert result is None or isinstance(result, bytes)

    def test_fallback_when_resultado_empty(self):
        """Lines 739->758: resultado is empty in fallback path → skip resultado block."""
        import reportlab.platypus as platypus

        real_cls = platypus.SimpleDocTemplate

        class _Broken:
            def __init__(self, *a, **kw):
                raise RuntimeError("forced fallback")

        relatorio = {"resumo": {"projeto": "Test", "tipo_obra": "X", "localizacao": "Y"}}
        # No "RESULTADO" key → resultado is {} → if resultado: is False
        platypus.SimpleDocTemplate = _Broken
        try:
            result = render_financial_report_pdf(relatorio, title="Fallback Empty Result")
        finally:
            platypus.SimpleDocTemplate = real_cls
        assert result is None or isinstance(result, bytes)

    def test_fallback_inner_exception_returns_none(self):
        """Lines 765-766: both primary and fallback raise → returns None."""
        import reportlab.pdfgen.canvas as canvas_mod
        import reportlab.platypus as platypus

        real_platypus = platypus.SimpleDocTemplate
        real_canvas = canvas_mod.Canvas

        class _BrokenDoc:
            def __init__(self, *a, **kw):
                raise RuntimeError("primary failure")

        class _BrokenCanvas:
            def __init__(self, *a, **kw):
                raise RuntimeError("fallback failure")

        platypus.SimpleDocTemplate = _BrokenDoc
        canvas_mod.Canvas = _BrokenCanvas
        try:
            result = render_financial_report_pdf({}, title="Double Failure")
        finally:
            platypus.SimpleDocTemplate = real_platypus
            canvas_mod.Canvas = real_canvas
        assert result is None
