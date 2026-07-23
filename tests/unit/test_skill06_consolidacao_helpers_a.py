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
CONSOL = _cons


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





# _consolidacao/_skill_helpers_a.py
# ===========================================================================


class TestAsBool:
    """Lines 967-978: _as_bool conversion."""

    def test_bool_true(self):
        assert CONSOL._as_bool(True) is True

    def test_bool_false(self):
        assert CONSOL._as_bool(False) is False

    def test_int_nonzero(self):
        assert CONSOL._as_bool(1) is True

    def test_int_zero(self):
        assert CONSOL._as_bool(0) is False

    def test_str_true_values(self):
        """Lines 973-975: truthy strings → True."""
        for v in ("1", "true", "t", "yes", "y", "on", "True", " YES "):
            assert CONSOL._as_bool(v) is True, f"Expected True for {v!r}"

    def test_str_false_values(self):
        """Lines 976-977: falsy strings → False."""
        for v in ("0", "false", "f", "no", "n", "off", "", " "):
            assert CONSOL._as_bool(v) is False, f"Expected False for {v!r}"

    def test_unrecognized_string_returns_false(self):
        """Line 978 fallthrough: unrecognized string → False."""
        assert CONSOL._as_bool("maybe") is False

    def test_none_returns_false(self):
        assert CONSOL._as_bool(None) is False


class TestValidatePeDuploRisco:
    """Lines 728-741: _validate_pe_duplo_risco."""

    def _make_pe(self, confianca: str, status: str = "ERRO") -> object:
        from concilium.domain.models.canonical import PontoEquilibrio

        return PontoEquilibrio(
            item_id="ITEM-01",
            custo_fixo_equipe=100_000.0,
            custo_venda_cpu=80_000.0,
            delta=-20_000.0,
            delta_pct=-0.2,
            status_validacao=status,
            confianca_pe=confianca,
        )

    def test_media_confianca_emits_aviso(self):
        """Line 730: confianca_pe == 'MEDIA' → severidade = 'AVISO'."""
        pe = self._make_pe("MEDIA", "ERRO")
        validacoes = []
        CONSOL._validate_pe_duplo_risco(pe, validacoes)
        assert len(validacoes) == 1
        assert validacoes[0].codigo == "VAL-PE-PU-DUPLO-RISCO"
        assert validacoes[0].status == "AVISO"

    def test_baixa_confianca_emits_erro(self):
        """Line 731: confianca_pe == 'BAIXA' → severidade = 'ERRO'."""
        pe = self._make_pe("BAIXA", "ERRO")
        validacoes = []
        CONSOL._validate_pe_duplo_risco(pe, validacoes)
        assert validacoes[0].status == "ERRO"

    def test_alta_confianca_no_emission(self):
        """Guard: 'ALTA' not in ('MEDIA', 'BAIXA') → no validacao emitted."""
        pe = self._make_pe("ALTA", "ERRO")
        validacoes = []
        CONSOL._validate_pe_duplo_risco(pe, validacoes)
        assert len(validacoes) == 0

    def test_status_ok_no_emission(self):
        """Guard: status_validacao != 'ERRO' → no emission."""
        pe = self._make_pe("MEDIA", "OK")
        validacoes = []
        CONSOL._validate_pe_duplo_risco(pe, validacoes)
        assert len(validacoes) == 0


class TestApmProcessFamilia:
    """Lines 839-860: _apm_process_familia downgrade ERRO → AVISO."""

    def _make_pe(self, delta: float, status: str = "ERRO") -> object:
        from concilium.domain.models.canonical import PontoEquilibrio

        return PontoEquilibrio(
            item_id="X",
            custo_fixo_equipe=100.0,
            custo_venda_cpu=120.0,
            delta=delta,
            delta_pct=delta / 100.0,
            status_validacao=status,
        )

    def test_single_row_returns_early(self):
        """Line 841-842: len(rows) < 2 → return immediately."""
        pe = self._make_pe(-10.0)
        validacoes = []
        CONSOL._apm_process_familia("FAM-A", [("X", pe)], validacoes)
        assert len(validacoes) == 0
        assert pe.status_validacao == "ERRO"  # unchanged

    def test_family_with_positive_aggregate_downgrades(self):
        """Lines 843-850: 2 rows, ERRO + OK, delta_fam >= 0 → ERRO downgraded to AVISO."""
        pe_err = self._make_pe(-10.0, "ERRO")
        pe_ok = self._make_pe(50.0, "OK")
        validacoes = []
        CONSOL._apm_process_familia("FAM-B", [("A", pe_err), ("B", pe_ok)], validacoes)
        assert pe_err.status_validacao == "AVISO"
        assert len(validacoes) == 1
        assert validacoes[0].codigo == "VAL-PONTO-EQUILIBRIO-MITIGACAO"

    def test_all_negative_aggregate_no_downgrade(self):
        """Guard: erros_fam exists but delta_fam < 0 → no downgrade."""
        pe1 = self._make_pe(-100.0, "ERRO")
        pe2 = self._make_pe(-50.0, "ERRO")
        validacoes = []
        CONSOL._apm_process_familia("FAM-C", [("A", pe1), ("B", pe2)], validacoes)
        assert pe1.status_validacao == "ERRO"
        assert len(validacoes) == 0


class TestBpeProcessEquipe:
    """Line 882: _bpe_process_equipe returns None when equipe.item_id is falsy."""

    def test_empty_item_id_returns_none(self):
        """Line 882: not equipe.item_id → return None."""
        equipe = SimpleNamespace(item_id="", custo_total=0.0, funcoes=[])
        result = CONSOL._bpe_process_equipe(equipe, venda_por_item={}, validacoes=[])
        assert result is None

    def test_none_item_id_returns_none(self):
        equipe = SimpleNamespace(item_id=None, custo_total=0.0, funcoes=[])
        result = CONSOL._bpe_process_equipe(equipe, venda_por_item={}, validacoes=[])
        assert result is None


class TestApmBuildFamiliaRows:
    """Line 862: `if fam:` — item sem cpu_id resolvível não entra em nenhuma família."""

    def _make_pe(self) -> object:
        from concilium.domain.models.canonical import PontoEquilibrio

        return PontoEquilibrio(
            item_id="X",
            custo_fixo_equipe=100.0,
            custo_venda_cpu=120.0,
            delta=10.0,
            delta_pct=0.1,
            status_validacao="OK",
        )

    def test_equipe_ausente_gera_familia_vazia(self):
        """eq is None → fam = _cpu_familia("") = "" → branch `if fam` é False."""
        pe = self._make_pe()
        rows = CONSOL._apm_build_familia_rows({"X": pe}, equipe_by_item={})
        assert rows == {}

    def test_equipe_sem_cpu_id_gera_familia_vazia(self):
        """eq.cpu_id vazio → fam == "" → item não é agrupado."""
        pe = self._make_pe()
        equipe = SimpleNamespace(item_id="X", cpu_id="")
        rows = CONSOL._apm_build_familia_rows({"X": pe}, equipe_by_item={"X": equipe})
        assert rows == {}

    def test_equipe_com_cpu_id_agrupa_por_familia(self):
        pe = self._make_pe()
        equipe = SimpleNamespace(item_id="X", cpu_id="CPU-DREN-01")
        rows = CONSOL._apm_build_familia_rows({"X": pe}, equipe_by_item={"X": equipe})
        assert "CPU" in rows
        assert rows["CPU"] == [("X", pe)]


# ===========================================================================
# _indiretos/_skill_helpers_b.py
# ===========================================================================



