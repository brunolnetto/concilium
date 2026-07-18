"""Gold Aggregator — ADR-112 F5.

Agrega Silver → Gold usando DuckDB in-process.
Lê Silver diretamente do BlobStorage (mesmo storage usado pelo ObservabilityWorker).
"""

from __future__ import annotations

import json
import logging
from typing import Any

from concilium.domain.repositories.blob_storage_port import BlobStoragePort

from .silver_normalizer import dedupe_records

logger = logging.getLogger(__name__)

_SILVER_PREFIX = "observability/silver"
_P99_THRESHOLD_MS = 30_000  # 30 s
_FALLBACK_RATE_THRESHOLD = 0.05  # 5 %


class GoldAggregator:
    """Gera tabelas Gold (SLIs, fallback rates, alertas) via DuckDB sobre o Silver."""

    def __init__(self, storage: BlobStoragePort):
        self._storage = storage

    # ── Leitura Silver ──────────────────────────────────────────────────────

    def _read_silver(self, signal_type: str) -> list[dict[str, Any]]:
        """Lê todos os records Silver do tipo de sinal, deduplicados entre arquivos.

        Dedup é necessário pelo mesmo motivo de ObservabilityWorker.read_silver():
        um dia pode ter sido reprocessado com particionamento diferente do original,
        deixando o mesmo event_id em mais de um arquivo — sem dedup, Gold conta em dobro.
        """
        blobs = sorted(self._storage.listar_blobs(f"{_SILVER_PREFIX}/{signal_type}/"))
        records: list[dict[str, Any]] = []
        for path in blobs:
            try:
                raw = self._storage.ler_blob(path)
                for line in raw.decode("utf-8").splitlines():
                    if line.strip():
                        records.append(json.loads(line))
            except Exception:
                pass
        return dedupe_records(records)

    # ── Tabelas Gold ────────────────────────────────────────────────────────

    def build_sli_diario(self) -> list[dict[str, Any]]:
        """p50/p95/p99 de duration_ms por (date, skill_id) a partir do Silver traces."""
        import duckdb

        traces = self._read_silver("traces")
        if not traces:
            return []

        con = duckdb.connect(":memory:")
        con.execute("""
            CREATE TABLE traces (
                span_id TEXT, skill_id TEXT, duration_ms INTEGER, start_ts TEXT
            )
        """)
        con.executemany(
            "INSERT INTO traces VALUES (?, ?, ?, ?)",
            [
                (t.get("span_id", ""), t.get("skill_id"), int(t.get("duration_ms", 0)), t.get("start_ts", ""))
                for t in traces
                if t.get("skill_id")
            ],
        )
        rows = con.execute("""
            SELECT
                SUBSTR(start_ts, 1, 10)                                          AS date,
                skill_id,
                PERCENTILE_CONT(0.50) WITHIN GROUP (ORDER BY duration_ms)       AS p50_ms,
                PERCENTILE_CONT(0.95) WITHIN GROUP (ORDER BY duration_ms)       AS p95_ms,
                PERCENTILE_CONT(0.99) WITHIN GROUP (ORDER BY duration_ms)       AS p99_ms,
                COUNT(*)                                                          AS n_spans
            FROM traces
            WHERE skill_id IS NOT NULL
            GROUP BY 1, 2
            ORDER BY 1, 2
        """).fetchall()
        return [
            {"date": r[0], "skill_id": r[1], "p50_ms": r[2], "p95_ms": r[3], "p99_ms": r[4], "n_spans": r[5]}
            for r in rows
        ]

    def build_fallback_rate_por_skill(self) -> list[dict[str, Any]]:
        """Taxa de fallbacks por (date, skill_id) a partir do Silver logs."""
        import duckdb

        logs = self._read_silver("logs")
        if not logs:
            return []

        con = duckdb.connect(":memory:")
        con.execute("""
            CREATE TABLE logs (
                event_id TEXT, skill_id TEXT, fallback_type TEXT, ts TEXT
            )
        """)
        con.executemany(
            "INSERT INTO logs VALUES (?, ?, ?, ?)",
            [(ln.get("event_id", ""), ln.get("skill_id"), ln.get("fallback_type"), ln.get("ts", "")) for ln in logs],
        )
        rows = con.execute("""
            SELECT
                SUBSTR(ts, 1, 10)                                                 AS date,
                COALESCE(skill_id, 'unknown')                                     AS skill_id,
                COUNT(*) FILTER (WHERE fallback_type IS NOT NULL)                 AS n_fallbacks,
                COUNT(*)                                                           AS n_total,
                ROUND(
                    CAST(COUNT(*) FILTER (WHERE fallback_type IS NOT NULL) AS DOUBLE)
                    / NULLIF(COUNT(*), 0),
                    4
                )                                                                  AS fallback_rate
            FROM logs
            GROUP BY 1, 2
            ORDER BY fallback_rate DESC NULLS LAST
        """).fetchall()
        return [
            {
                "date": r[0],
                "skill_id": r[1],
                "n_fallbacks": r[2],
                "n_total": r[3],
                "fallback_rate": float(r[4] or 0.0),
            }
            for r in rows
        ]

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
        ]:
            path = f"observability/gold/{name}.json"
            self._storage.gravar_blob(path, json.dumps(data, ensure_ascii=False, indent=2).encode("utf-8"))
            paths[name] = path
        return paths
