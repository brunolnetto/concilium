"""TDD ADR-112 F7 (scheduler periódico) + F8 (cross-domain Gold ⋈ canonical)."""

from __future__ import annotations

import datetime

import pytest


@pytest.fixture
def storage(tmp_path):
    from concilium.infrastructure.adapters.blob_storage.local import LocalBlobStorage

    return LocalBlobStorage(tmp_path)


def _seed_silver_logs(storage, records):
    from concilium.infrastructure.observability.pipeline import ObservabilityWorker
    from concilium.infrastructure.observability.silver_normalizer import normalize_log_record

    worker = ObservabilityWorker(storage)
    worker._upsert_silver("logs", [normalize_log_record(r) for r in records], "2026-06-19")


# ─────────────────────────────────────────────────────────────────────────────
# F8 — Cross-domain: fallback_rate por projeto ⋈ canonical resultado
# ─────────────────────────────────────────────────────────────────────────────


class TestCrossDomainBuilder:
    """build_cross_domain junta fallback por projeto com custo/margem do canonical."""

    def test_empty_when_no_logs(self, storage):
        from concilium.infrastructure.observability.cross_domain import CrossDomainBuilder

        builder = CrossDomainBuilder(storage, canonical_provider=lambda pid: None)
        assert builder.build() == []

    def test_joins_fallback_rate_with_canonical(self, storage):
        from concilium.infrastructure.observability.cross_domain import CrossDomainBuilder

        _seed_silver_logs(
            storage,
            [
                {
                    "ts": "2026-06-19T10:00:00Z",
                    "severity": "WARNING",
                    "logger": "concilium.skills.06",
                    "message": "BDI sem taxa para 'mao_obra'",
                    "trace_id": "",
                    "span_id": "s1",
                    "service": "c",
                    "project_id": "AGIS",
                },
                {
                    "ts": "2026-06-19T10:00:01Z",
                    "severity": "INFO",
                    "logger": "concilium.skills.06",
                    "message": "ok",
                    "trace_id": "",
                    "span_id": "s2",
                    "service": "c",
                    "project_id": "AGIS",
                },
            ],
        )
        canonicals = {"AGIS": {"custo_direto": 16_500_000.0, "margem_pct": 0.14}}
        builder = CrossDomainBuilder(storage, canonical_provider=lambda pid: canonicals.get(pid))
        rows = builder.build()
        assert len(rows) == 1
        row = rows[0]
        assert row["project_id"] == "AGIS"
        assert row["custo_direto"] == 16_500_000.0
        assert row["margem_pct"] == 0.14
        assert 0.0 <= row["fallback_rate"] <= 1.0
        assert row["n_fallbacks"] == 1
        assert row["n_total"] == 2

    def test_handles_missing_canonical_gracefully(self, storage):
        from concilium.infrastructure.observability.cross_domain import CrossDomainBuilder

        _seed_silver_logs(
            storage,
            [
                {
                    "ts": "2026-06-19T10:00:00Z",
                    "severity": "WARNING",
                    "logger": "concilium.skills.06",
                    "message": "BDI sem taxa",
                    "trace_id": "",
                    "span_id": "s3",
                    "service": "c",
                    "project_id": "XYZ",
                },
            ],
        )
        builder = CrossDomainBuilder(storage, canonical_provider=lambda pid: None)
        rows = builder.build()
        assert len(rows) == 1
        assert rows[0]["project_id"] == "XYZ"
        assert rows[0]["custo_direto"] is None
        assert rows[0]["margem_pct"] is None

    def test_logs_without_project_id_grouped_as_unknown(self, storage):
        from concilium.infrastructure.observability.cross_domain import CrossDomainBuilder

        _seed_silver_logs(
            storage,
            [
                {
                    "ts": "2026-06-19T10:00:00Z",
                    "severity": "WARNING",
                    "logger": "concilium.skills.06",
                    "message": "BDI sem taxa",
                    "trace_id": "",
                    "span_id": "s4",
                    "service": "c",
                },
            ],
        )
        builder = CrossDomainBuilder(storage, canonical_provider=lambda pid: None)
        rows = builder.build()
        assert any(r["project_id"] in ("unknown", "") for r in rows)

    def test_write_persists_cross_domain_json(self, storage):
        from concilium.infrastructure.observability.cross_domain import CrossDomainBuilder

        _seed_silver_logs(
            storage,
            [
                {
                    "ts": "2026-06-19T10:00:00Z",
                    "severity": "WARNING",
                    "logger": "concilium.skills.06",
                    "message": "BDI sem taxa",
                    "trace_id": "",
                    "span_id": "s5",
                    "service": "c",
                    "project_id": "AGIS",
                },
            ],
        )
        builder = CrossDomainBuilder(storage, canonical_provider=lambda pid: {"custo_direto": 1.0, "margem_pct": 0.1})
        path = builder.write()
        assert path == "observability/gold/cross_domain.json"
        assert storage.blob_existe(path)


# ─────────────────────────────────────────────────────────────────────────────
# F7 — ObservabilityScheduler: ciclo time-gated (Bronze→Silver 15min, Silver→Gold 1h)
# ─────────────────────────────────────────────────────────────────────────────


def _seed_bronze(storage, signal_type, records, date="2026-06-19"):
    from concilium.infrastructure.observability.bronze_writer import BronzeWriter

    BronzeWriter(storage, signal_type).write_batch(records, date=date)


class TestObservabilityScheduler:
    """run_cycle(now) executa Bronze→Silver e Silver→Gold conforme cadência."""

    def _now(self, **kw):
        base = datetime.datetime(2026, 6, 19, 12, 0, 0, tzinfo=datetime.UTC)
        return base + datetime.timedelta(**kw)

    def test_first_cycle_runs_both_stages(self, storage):
        from concilium.infrastructure.observability.pipeline import ObservabilityScheduler

        _seed_bronze(
            storage,
            "logs",
            [
                {
                    "ts": "2026-06-19T10:00:00Z",
                    "severity": "WARNING",
                    "logger": "l",
                    "message": "BDI sem taxa",
                    "trace_id": "",
                    "span_id": "x1",
                    "service": "c",
                }
            ],
        )
        sched = ObservabilityScheduler(storage)
        result = sched.run_cycle(now=self._now())
        assert result["silver_ran"] is True
        assert result["gold_ran"] is True

    def test_second_cycle_within_15min_skips_silver(self, storage):
        from concilium.infrastructure.observability.pipeline import ObservabilityScheduler

        _seed_bronze(
            storage,
            "logs",
            [
                {
                    "ts": "t",
                    "severity": "W",
                    "logger": "l",
                    "message": "m",
                    "trace_id": "",
                    "span_id": "x2",
                    "service": "c",
                }
            ],
        )
        sched = ObservabilityScheduler(storage)
        sched.run_cycle(now=self._now())
        result2 = sched.run_cycle(now=self._now(minutes=5))
        assert result2["silver_ran"] is False, "Silver não deve rodar < 15min após o último"

    def test_silver_runs_again_after_15min(self, storage):
        from concilium.infrastructure.observability.pipeline import ObservabilityScheduler

        _seed_bronze(
            storage,
            "logs",
            [
                {
                    "ts": "t",
                    "severity": "W",
                    "logger": "l",
                    "message": "m",
                    "trace_id": "",
                    "span_id": "x3",
                    "service": "c",
                }
            ],
        )
        sched = ObservabilityScheduler(storage)
        sched.run_cycle(now=self._now())
        result2 = sched.run_cycle(now=self._now(minutes=16))
        assert result2["silver_ran"] is True

    def test_gold_skips_within_1h(self, storage):
        from concilium.infrastructure.observability.pipeline import ObservabilityScheduler

        _seed_bronze(
            storage,
            "logs",
            [
                {
                    "ts": "t",
                    "severity": "W",
                    "logger": "l",
                    "message": "m",
                    "trace_id": "",
                    "span_id": "x4",
                    "service": "c",
                }
            ],
        )
        sched = ObservabilityScheduler(storage)
        sched.run_cycle(now=self._now())
        result2 = sched.run_cycle(now=self._now(minutes=20))  # silver sim, gold não
        assert result2["silver_ran"] is True
        assert result2["gold_ran"] is False

    def test_gold_runs_again_after_1h(self, storage):
        from concilium.infrastructure.observability.pipeline import ObservabilityScheduler

        _seed_bronze(
            storage,
            "logs",
            [
                {
                    "ts": "t",
                    "severity": "W",
                    "logger": "l",
                    "message": "m",
                    "trace_id": "",
                    "span_id": "x5",
                    "service": "c",
                }
            ],
        )
        sched = ObservabilityScheduler(storage)
        sched.run_cycle(now=self._now())
        result2 = sched.run_cycle(now=self._now(hours=1, minutes=1))
        assert result2["gold_ran"] is True

    def test_custom_intervals(self, storage):
        from concilium.infrastructure.observability.pipeline import ObservabilityScheduler

        sched = ObservabilityScheduler(storage, silver_interval_min=5, gold_interval_min=30)
        assert sched.silver_interval_min == 5
        assert sched.gold_interval_min == 30
