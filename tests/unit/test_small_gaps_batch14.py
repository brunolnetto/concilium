"""Coverage batch 14 — report_markdown_sections, granular, _assessor small gaps."""

from __future__ import annotations

import importlib.util
import tempfile
from pathlib import Path


def _load_assessor():
    """Load _assessor.py from hyphenated directory via importlib."""
    path = (
        Path(__file__).parents[2]
        / "src/concilium/application/skills/manifests/11-replanejamento-e-cenarios/_skill_helpers/_assessor.py"
    )
    spec = importlib.util.spec_from_file_location("skill11._assessor", path)
    mod = importlib.util.module_from_spec(spec)  # type: ignore[arg-type]
    spec.loader.exec_module(mod)  # type: ignore[union-attr]
    return mod


# ---------------------------------------------------------------------------
# report_markdown_sections.py lines 122, 142: early returns for empty inputs
# ---------------------------------------------------------------------------


class TestRenderResultadoEmptyInput:
    def test_render_resultado_empty_dict_returns_empty_list(self):
        """Line 122: resultado={} → not resultado → return []."""
        from concilium.application.runtime.deliverables.reports.report_markdown_sections import render_resultado

        assert render_resultado({}) == []

    def test_render_resultado_non_dict_returns_empty_list(self):
        """Line 122: resultado is not a dict → return []."""
        from concilium.application.runtime.deliverables.reports.report_markdown_sections import render_resultado

        assert render_resultado("not a dict") == []  # type: ignore[arg-type]

    def test_render_resultado_none_returns_empty_list(self):
        """Line 122: resultado=None is not a dict → return []."""
        from concilium.application.runtime.deliverables.reports.report_markdown_sections import render_resultado

        assert render_resultado(None) == []  # type: ignore[arg-type]


class TestRenderPlanejamentoTableEmptyInput:
    def test_render_planejamento_table_empty_list_returns_empty(self):
        """Line 142: plan=[] → not plan → return []."""
        from concilium.application.runtime.deliverables.reports.report_markdown_sections import (
            render_planejamento_table,
        )

        assert render_planejamento_table([]) == []

    def test_render_planejamento_table_non_list_returns_empty(self):
        """Line 142: plan is not a list → return []."""
        from concilium.application.runtime.deliverables.reports.report_markdown_sections import (
            render_planejamento_table,
        )

        assert render_planejamento_table("oops") == []  # type: ignore[arg-type]


# ---------------------------------------------------------------------------
# granular.py lines 20-22: _load_json except block for invalid JSON
# ---------------------------------------------------------------------------


class TestGranularLoadJsonInvalidJson:
    def test_load_json_returns_empty_dict_on_invalid_json(self):
        """Lines 20-22: file exists but has invalid JSON → except → return {}."""
        from concilium.application.benchmarks.comparison.granular import _load_json

        with tempfile.NamedTemporaryFile(mode="wb", suffix=".json", delete=False) as f:
            tmppath = Path(f.name)
            f.write(b"{not: valid json}")

        try:
            result = _load_json(tmppath)
        finally:
            tmppath.unlink()

        assert result == {}

    def test_load_json_returns_empty_dict_on_unicode_error(self):
        """Lines 20-22: file with bad bytes → UnicodeDecodeError → return {}."""
        from concilium.application.benchmarks.comparison.granular import _load_json

        with tempfile.NamedTemporaryFile(mode="wb", suffix=".json", delete=False) as f:
            tmppath = Path(f.name)
            f.write(b"\xff\xfe invalid utf-8 \xab\xcd")

        try:
            result = _load_json(tmppath)
        finally:
            tmppath.unlink()

        assert result == {}


# ---------------------------------------------------------------------------
# _assessor.py line 84: _get_a_plus_atividades falls through to ccr.get()
# ---------------------------------------------------------------------------


class TestGetAPlusAtividades:
    def test_dict_ccr_uses_get_method(self):
        """Line 84: ccr is a dict → getattr(ccr, 'atividades', None) returns None
        (dicts don't have .atividades attr) → falls through to ccr.get('atividades', [])."""
        mod = _load_assessor()
        result = mod._get_a_plus_atividades({"atividades": []})
        assert result == []

    def test_dict_ccr_with_a_plus_items(self):
        """Line 84: dict ccr with classe A+ items → returned via .get() path."""
        mod = _load_assessor()
        item_a_plus = {"atividade_id": "ESCAV-01", "class": "A+"}
        item_other = {"atividade_id": "ESCAV-02", "class": "B"}
        result = mod._get_a_plus_atividades({"atividades": [item_a_plus, item_other]})
        assert len(result) == 1
        assert result[0]["atividade_id"] == "ESCAV-01"


# ---------------------------------------------------------------------------
# _assessor.py lines 199-206: VAL-REPLAN-01 AVISO when no sugestoes
# _assessor.py lines 219-226: VAL-REPLAN-02 ERRO when checkpoints invalid
# ---------------------------------------------------------------------------


class TestBuildValidacoesReplan:
    def test_val_replan_01_aviso_when_no_sugestoes(self):
        """Lines 199-206: sugestoes=[] → VAL-REPLAN-01 AVISO appended."""
        _build_validacoes_replan = _load_assessor()._build_validacoes_replan
        validacoes = _build_validacoes_replan(
            sugestoes=[],
            delta_necessario=0.1,
            sugestao_prioritaria=None,
            status_gatilho="VERMELHO",
        )
        codes = {v.codigo: v.status for v in validacoes}
        assert codes.get("VAL-REPLAN-01") == "AVISO"

    def test_val_replan_02_erro_when_invalid_checkpoint(self):
        """Lines 219-226: sugestao has invalid checkpoint_skill → VAL-REPLAN-02 ERRO."""
        from concilium.domain.models.canonical import ReplanSugestao

        _build_validacoes_replan = _load_assessor()._build_validacoes_replan
        sugestao = ReplanSugestao(
            id="REPLAN-999",
            tipo="CRONOGRAMA",
            checkpoint_skill="99-invalid-checkpoint",
            parametros_sugeridos={},
            delta_margem_estimado=0.05,
            confianca="BAIXA",
            justificativa="Sugestão de teste com checkpoint inválido.",
        )
        validacoes = _build_validacoes_replan(
            sugestoes=[sugestao],
            delta_necessario=0.1,
            sugestao_prioritaria="REPLAN-999",
            status_gatilho="VERMELHO",
        )
        codes = {v.codigo: v.status for v in validacoes}
        assert codes.get("VAL-REPLAN-02") == "ERRO"

    def test_val_replan_02_ok_when_valid_checkpoint(self):
        """Line 228: all checkpoints valid → VAL-REPLAN-02 OK."""
        from concilium.domain.models.canonical import ReplanSugestao

        _build_validacoes_replan = _load_assessor()._build_validacoes_replan
        sugestao = ReplanSugestao(
            id="REPLAN-001",
            tipo="CRONOGRAMA",
            checkpoint_skill="04-cronograma",
            parametros_sugeridos={},
            delta_margem_estimado=0.05,
            confianca="MEDIA",
            justificativa="Sugestão válida.",
        )
        validacoes = _build_validacoes_replan(
            sugestoes=[sugestao],
            delta_necessario=0.1,
            sugestao_prioritaria="REPLAN-001",
            status_gatilho="AMARELO",
        )
        codes = {v.codigo: v.status for v in validacoes}
        assert codes.get("VAL-REPLAN-02") == "OK"
