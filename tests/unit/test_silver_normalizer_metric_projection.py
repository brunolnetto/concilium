"""Testes da projeção dimensional em normalize_metric_record (ADR-146, gap 2 do ERD Gold).

As chaves canônicas ("skill", "tool", "project.id", "status") são promovidas a
colunas de primeira classe (skill_id/tool_name/project_id/status) — o que torna
DIM_SKILL/DIM_TOOL/DIM_PROJECT/DIM_STATUS alcançáveis a partir de
FACT_METRIC_DATAPOINT sem parsear `labels`. Funciona retroativamente: essas
chaves são o que a instrumentação sempre emitiu. "status" foi promovida junto
com o relatório build_tool_usage_diario (ADR-147) — METRIC_LABEL_STATUS já
existia desde a ADR-146, mas ficava sem projeção correspondente até então.
"""

from __future__ import annotations

from concilium.infrastructure.observability.silver_normalizer import normalize_metric_record


def _bronze_metric(labels=None):
    return {
        "metric_name": "concilium.pipeline.skill.duration_ms",
        "ts": "2026-07-21T10:00:00.000000Z",
        "value": 120.0,
        "labels": labels or {},
        "service": "concilium",
    }


class TestMetricDimensionalProjection:
    def test_promotes_skill_tool_project_and_status_from_canonical_keys(self):
        result = normalize_metric_record(
            _bronze_metric(labels={"skill": "05", "tool": "executar_pipeline", "project.id": "AGIS", "status": "OK"})
        )

        assert result["skill_id"] == "05"
        assert result["tool_name"] == "executar_pipeline"
        assert result["project_id"] == "AGIS"
        assert result["status"] == "OK"

    def test_absent_labels_project_to_none(self):
        result = normalize_metric_record(_bronze_metric(labels={"route": "/auth/token"}))

        assert result["skill_id"] is None
        assert result["tool_name"] is None
        assert result["project_id"] is None
        assert result["status"] is None

    def test_labels_dict_preserved_intact_with_promoted_and_extra_keys(self):
        """A promoção é aditiva — `labels` continua íntegro para fidelidade/debug."""
        labels = {"skill": "05", "status": "OK", "pipeline.mode": "olap"}

        result = normalize_metric_record(_bronze_metric(labels=labels))

        assert result["labels"] == labels

    def test_none_labels_value_is_safe(self):
        """Bronze com labels=None explícito (não missing) não pode quebrar a projeção."""
        record = _bronze_metric()
        record["labels"] = None

        result = normalize_metric_record(record)

        assert result["skill_id"] is None
        assert result["tool_name"] is None
        assert result["project_id"] is None
        assert result["status"] is None
