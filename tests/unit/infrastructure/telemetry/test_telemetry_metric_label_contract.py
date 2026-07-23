"""Testes do contrato de labels de métricas (ADR-146, gap 2 do ERD Gold).

O contrato: chaves canônicas de label ("skill", "tool", "project.id", "status")
são as ÚNICAS que a Silver promove a colunas de primeira classe. Os valores são
exatamente o que a instrumentação já emitia — nenhum rename, nenhuma série
existente quebra; a única mudança de comportamento é record_tool_call ganhar
project.id (que _with_tracing já extraía para o span e descartava na métrica).

silver_normalizer permanece um módulo puro (sem imports do concilium) — o teste
de conformidade no final solda os dois lados sem acoplá-los em runtime.
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import concilium.infrastructure.telemetry as tel


class TestCanonicalLabelConstants:
    def test_constants_have_exact_production_values(self):
        """Os valores são os já emitidos em produção — mudá-los quebraria séries existentes."""
        assert tel.METRIC_LABEL_SKILL == "skill"
        assert tel.METRIC_LABEL_TOOL == "tool"
        assert tel.METRIC_LABEL_PROJECT == "project.id"
        assert tel.METRIC_LABEL_STATUS == "status"


class TestRecordToolCallProjectId:
    def _fake_counter(self):
        c = MagicMock()
        c.add = MagicMock()
        return c

    def test_without_project_id_emits_exactly_tool_and_status(self):
        """Sem project_id, o label dict é idêntico ao de antes — nem chave com None."""
        fake_counter = self._fake_counter()
        original = tel._tool_calls_counter
        try:
            tel._tool_calls_counter = fake_counter
            with patch.object(tel, "_OTEL_AVAILABLE", True):
                tel.record_tool_call("listar_projetos", "OK")
            fake_counter.add.assert_called_once_with(1, {"tool": "listar_projetos", "status": "OK"})
        finally:
            tel._tool_calls_counter = original

    def test_with_project_id_adds_canonical_project_label(self):
        fake_counter = self._fake_counter()
        original = tel._tool_calls_counter
        try:
            tel._tool_calls_counter = fake_counter
            with patch.object(tel, "_OTEL_AVAILABLE", True):
                tel.record_tool_call("executar_pipeline", "OK", project_id="AGIS")
            fake_counter.add.assert_called_once_with(
                1, {"tool": "executar_pipeline", "status": "OK", "project.id": "AGIS"}
            )
        finally:
            tel._tool_calls_counter = original

    def test_non_str_project_id_is_coerced(self):
        """kwargs.get("project_id") pode não ser str — o label deve ser sempre str."""
        fake_counter = self._fake_counter()
        original = tel._tool_calls_counter
        try:
            tel._tool_calls_counter = fake_counter
            with patch.object(tel, "_OTEL_AVAILABLE", True):
                tel.record_tool_call("t", "OK", project_id=123)
            labels = fake_counter.add.call_args.args[1]
            assert labels["project.id"] == "123"
        finally:
            tel._tool_calls_counter = original


class TestWithTracingForwardsProjectId:
    def _traced(self, fn):
        fake_span = MagicMock()
        fake_span.__enter__ = MagicMock(return_value=fake_span)
        fake_span.__exit__ = MagicMock(return_value=False)
        fake_tracer = MagicMock()
        fake_tracer.start_as_current_span.return_value = fake_span
        return fake_tracer

    def test_ok_path_forwards_project_id_to_metric(self):
        def my_tool(project_id=None):
            return 42

        with (
            patch.object(tel, "_OTEL_AVAILABLE", True),
            patch.object(tel, "get_tracer", return_value=self._traced(my_tool)),
            patch.object(tel, "record_tool_call") as mock_record,
        ):
            wrapped = tel._with_tracing(my_tool)
            wrapped(project_id="AGIS")

        mock_record.assert_called_once_with("my_tool", "OK", project_id="AGIS")

    def test_error_path_forwards_project_id_to_metric(self):
        import pytest

        def broken_tool(**kwargs):
            raise ValueError("falhou")

        with (
            patch.object(tel, "_OTEL_AVAILABLE", True),
            patch.object(tel, "get_tracer", return_value=self._traced(broken_tool)),
            patch.object(tel, "record_tool_call") as mock_record,
        ):
            wrapped = tel._with_tracing(broken_tool)
            with pytest.raises(ValueError, match="falhou"):
                wrapped(project_id="AGIS")

        mock_record.assert_called_once_with("broken_tool", "ERROR", project_id="AGIS")

    def test_no_project_id_forwards_none(self):
        def simple_tool():
            return "ok"

        with (
            patch.object(tel, "_OTEL_AVAILABLE", True),
            patch.object(tel, "get_tracer", return_value=self._traced(simple_tool)),
            patch.object(tel, "record_tool_call") as mock_record,
        ):
            wrapped = tel._with_tracing(simple_tool)
            wrapped()

        mock_record.assert_called_once_with("simple_tool", "OK", project_id=None)


class TestContractConformanceWithSilver:
    """Solda write-side (telemetry) e read-side (silver_normalizer) sem acoplá-los:
    labels emitidas com as constantes canônicas DEVEM ser promovidas pela projeção."""

    def test_silver_promotes_exactly_the_canonical_keys(self):
        from concilium.infrastructure.observability.silver_normalizer import normalize_metric_record

        record = {
            "metric_name": "concilium.mcp.tool.calls",
            "ts": "2026-07-21T10:00:00.000000Z",
            "value": 1.0,
            "labels": {
                tel.METRIC_LABEL_SKILL: "05",
                tel.METRIC_LABEL_TOOL: "executar_pipeline",
                tel.METRIC_LABEL_PROJECT: "AGIS",
                tel.METRIC_LABEL_STATUS: "OK",
            },
            "service": "concilium",
        }

        result = normalize_metric_record(record)

        assert result["skill_id"] == "05"
        assert result["tool_name"] == "executar_pipeline"
        assert result["project_id"] == "AGIS"
