"""Gold Aggregator — ADR-112 F5.

Agrega Silver → Gold usando DuckDB in-process.
Lê Silver diretamente do BlobStorage (mesmo storage usado pelo ObservabilityWorker).
"""

from __future__ import annotations

import json
import logging
from typing import Any

from concilium.domain.repositories.blob_storage_port import BlobStoragePort

from .cubo_logs import CuboLogs
from .cubo_metricas import CuboMetricas
from .cubo_spans import CuboSpans
from .pipeline import read_silver_records

_TOOL_CALLS_METRIC = "concilium.mcp.tool.calls"

logger = logging.getLogger(__name__)

_P99_THRESHOLD_MS = 30_000  # 30 s
_FALLBACK_RATE_THRESHOLD = 0.05  # 5 %


class GoldAggregator:
    """Gera tabelas Gold (SLIs, fallback rates, alertas) a partir dos cubos (ADR-147)."""

    def __init__(self, storage: BlobStoragePort):
        self._storage = storage

    # ── Leitura Silver ──────────────────────────────────────────────────────

    def _read_silver(self, signal_type: str) -> list[dict[str, Any]]:
        """Lê todos os records Silver do tipo de sinal, deduplicados entre arquivos."""
        return read_silver_records(self._storage, signal_type)

    # ── Tabelas Gold ────────────────────────────────────────────────────────

    def build_sli_diario(self) -> list[dict[str, Any]]:
        """p50/p95/p99 de duration_ms por (date, skill_id) a partir do Silver traces."""
        cubo = CuboSpans.from_silver(self._read_silver("traces"))
        return cubo.query(
            group_by=["date", "skill_id"],
            aggs={
                "p50_ms": "PERCENTILE_CONT(0.50) WITHIN GROUP (ORDER BY duration_ms)",
                "p95_ms": "PERCENTILE_CONT(0.95) WITHIN GROUP (ORDER BY duration_ms)",
                "p99_ms": "PERCENTILE_CONT(0.99) WITHIN GROUP (ORDER BY duration_ms)",
                "n_spans": "COUNT(*)",
            },
            where="skill_id IS NOT NULL",
            order_by="date, skill_id",
        )

    def build_fallback_rate_por_skill(self) -> list[dict[str, Any]]:
        """Taxa de fallbacks por (date, skill_id) a partir do Silver logs."""
        cubo = CuboLogs.from_silver(self._read_silver("logs"))
        rows = cubo.query(
            group_by=["date", "COALESCE(skill_id, 'unknown') AS skill_id"],
            aggs={
                "n_fallbacks": "COUNT(*) FILTER (WHERE fallback_type IS NOT NULL)",
                "n_total": "COUNT(*)",
                "fallback_rate": (
                    "ROUND(CAST(COUNT(*) FILTER (WHERE fallback_type IS NOT NULL) AS DOUBLE)"
                    " / NULLIF(COUNT(*), 0), 4)"
                ),
            },
            order_by="fallback_rate DESC NULLS LAST",
        )
        for r in rows:
            r["fallback_rate"] = float(r["fallback_rate"] or 0.0)
        return rows

    def build_tool_usage_diario(self) -> list[dict[str, Any]]:
        """Uso diário de tools MCP por status, a partir de concilium.mcp.tool.calls (Silver metrics).

        ADR-147 D7: primeiro relatório Gold consumindo CuboMetricas — decidido como
        uso/erro de tools por ser o caso de uso mais direto habilitado pela projeção
        skill_id/tool_name/project_id/status de ADR-146/147.

        `n` soma `value`, não conta linhas: concilium.mcp.tool.calls é um Counter —
        cada data point já é a soma acumulada de um intervalo de coleta (pode
        cobrir várias chamadas com os mesmos labels), não uma chamada individual.
        """
        cubo = CuboMetricas.from_silver(self._read_silver("metrics"))
        return cubo.query(
            group_by=["date", "tool_name", "status"],
            aggs={"n": "SUM(value)"},
            where=f"metric_name = '{_TOOL_CALLS_METRIC}'",
            order_by="date, tool_name, status",
        )

    def build_alertas_ativos(self) -> list[dict[str, Any]]:
        """Alertas quando p99 > 30 s ou fallback_rate > 5 %."""
        alertas: list[dict[str, Any]] = []

        for row in self.build_sli_diario():
            if (row.get("p99_ms") or 0) > _P99_THRESHOLD_MS:
                alertas.append(
                    {
                        "tipo": "p99_alto",
                        "skill_id": row["skill_id"],
                        "date": row["date"],
                        "p99_ms": row["p99_ms"],
                        "threshold_ms": _P99_THRESHOLD_MS,
                    }
                )

        for row in self.build_fallback_rate_por_skill():
            if (row.get("fallback_rate") or 0.0) > _FALLBACK_RATE_THRESHOLD:
                alertas.append(
                    {
                        "tipo": "fallback_alto",
                        "skill_id": row["skill_id"],
                        "date": row["date"],
                        "fallback_rate": row["fallback_rate"],
                        "threshold": _FALLBACK_RATE_THRESHOLD,
                    }
                )

        return alertas

    def write_gold(self) -> dict[str, str]:
        """Persiste tabelas Gold no BlobStorage como JSON. Retorna paths gravados."""
        paths: dict[str, str] = {}
        for name, data in [
            ("sli_diario", self.build_sli_diario()),
            ("fallback_rate_por_skill", self.build_fallback_rate_por_skill()),
            ("alertas_ativos", self.build_alertas_ativos()),
            ("tool_usage_diario", self.build_tool_usage_diario()),
        ]:
            path = f"observability/gold/{name}.json"
            self._storage.gravar_blob(path, json.dumps(data, ensure_ascii=False, indent=2).encode("utf-8"))
            paths[name] = path
        return paths
