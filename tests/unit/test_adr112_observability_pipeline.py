"""TDD para ADR-112 — Pipeline Assíncrona de Observabilidade: Arquitetura Medalhão.

Cobre:
  F1 · BronzeWriter: escrita append-only em blob storage
  F1 · BronzeLogHandler: handler Python logging → Bronze
  F2 · CheckpointStore: leitura/escrita/deleção de checkpoints
  F3 · SilverNormalizer: normalização de records + classificação de fallback_type
  F4 · ObservabilityWorker: fast-forward, idempotência, full-reload
  F5 · GoldAggregator: SLIs, fallback_rate, alertas_ativos via DuckDB
  F6 · CLI commands: run, status, report
"""

from __future__ import annotations

import json
import logging

import pytest

# ─────────────────────────────────────────────────────────────────────────────
# Fixture: LocalBlobStorage isolada por teste
# ─────────────────────────────────────────────────────────────────────────────


@pytest.fixture
def storage(tmp_path):
    from concilium.infrastructure.adapters.blob_storage.local import LocalBlobStorage

    return LocalBlobStorage(tmp_path)


# ─────────────────────────────────────────────────────────────────────────────
# F1-A: BronzeWriter
# ─────────────────────────────────────────────────────────────────────────────


class TestBronzeWriter:
    """Escrita append-only de batches NDJSON no Bronze."""

    def test_write_batch_creates_ndjson_blob(self, storage):
        from concilium.infrastructure.observability.bronze_writer import BronzeWriter

        writer = BronzeWriter(storage, signal_type="logs")
        records = [{"severity": "WARNING", "message": "teste"}]
        path = writer.write_batch(records, date="2026-06-18")
        content = storage.ler_blob(path).decode("utf-8")
        assert json.loads(content.splitlines()[0])["message"] == "teste"

    def test_write_batch_path_partitioned_by_date(self, storage):
        from concilium.infrastructure.observability.bronze_writer import BronzeWriter

        writer = BronzeWriter(storage, signal_type="traces")
        path = writer.write_batch([{"span_id": "abc"}], date="2026-06-18")
        assert path.startswith("observability/bronze/traces/2026-06-18/")
        assert path.endswith(".ndjson")

    def test_write_batch_append_only_each_call_creates_new_file(self, storage):
        from concilium.infrastructure.observability.bronze_writer import BronzeWriter

        writer = BronzeWriter(storage, signal_type="logs")
        path1 = writer.write_batch([{"msg": "a"}], date="2026-06-18")
        path2 = writer.write_batch([{"msg": "b"}], date="2026-06-18")
        assert path1 != path2, "Cada write deve criar um arquivo distinto (append-only)"

    def test_write_batch_multiple_records_as_ndjson(self, storage):
        from concilium.infrastructure.observability.bronze_writer import BronzeWriter

        writer = BronzeWriter(storage, signal_type="logs")
        records = [{"id": 1}, {"id": 2}, {"id": 3}]
        path = writer.write_batch(records, date="2026-06-18")
        lines = storage.ler_blob(path).decode("utf-8").strip().splitlines()
        assert len(lines) == 3
        assert json.loads(lines[2])["id"] == 3

    def test_write_batch_uses_today_when_date_omitted(self, storage):
        import datetime

        from concilium.infrastructure.observability.bronze_writer import BronzeWriter

        writer = BronzeWriter(storage, signal_type="logs")
        path = writer.write_batch([{"x": 1}])
        today = datetime.date.today().isoformat()
        assert today in path


# ─────────────────────────────────────────────────────────────────────────────
# F1-B: BronzeLogHandler
# ─────────────────────────────────────────────────────────────────────────────


class TestBronzeLogHandler:
    """Handler Python logging → Bronze."""

    @pytest.fixture(autouse=True)
    def isolate(self):
        root = logging.getLogger()
        original = root.handlers[:]
        yield
        for h in root.handlers[:]:
            root.removeHandler(h)
        for h in original:
            root.addHandler(h)

    def test_handler_writes_log_record_to_bronze(self, storage, tmp_path):
        from concilium.infrastructure.observability.bronze_writer import BronzeLogHandler, BronzeWriter

        writer = BronzeWriter(storage, signal_type="logs")
        handler = BronzeLogHandler(writer)
        logger = logging.getLogger("test.bronze")
        logger.addHandler(handler)
        logger.setLevel(logging.WARNING)
        logger.warning("BDI sem taxa para 'mao_obra'")
        handler.flush()
        blobs = storage.listar_blobs("observability/bronze/logs/")
        assert len(blobs) >= 1

    def test_handler_includes_message_in_record(self, storage):
        from concilium.infrastructure.observability.bronze_writer import BronzeLogHandler, BronzeWriter

        writer = BronzeWriter(storage, signal_type="logs")
        handler = BronzeLogHandler(writer)
        logger = logging.getLogger("test.bronze.msg")
        logger.addHandler(handler)
        logger.setLevel(logging.WARNING)
        logger.warning("Função SV-P0046-D sem preco_unitario")
        handler.flush()
        blobs = sorted(storage.listar_blobs("observability/bronze/logs/"))
        content = storage.ler_blob(blobs[-1]).decode("utf-8")
        record = json.loads(content.strip().splitlines()[0])
        assert "preco_unitario" in record["message"]

    def test_handler_captures_user_id_from_auth_context(self, storage):
        """BronzeLogHandler deve propagar user_id/request_id da contextvar de auth (ADR-121 D6)."""
        from concilium.infrastructure.middleware.auth_context import current_request_id, current_user_id
        from concilium.infrastructure.observability.bronze_writer import BronzeLogHandler, BronzeWriter

        writer = BronzeWriter(storage, signal_type="logs")
        handler = BronzeLogHandler(writer)
        logger = logging.getLogger("test.bronze.user")
        logger.addHandler(handler)
        logger.setLevel(logging.WARNING)

        t_user = current_user_id.set("user-42")
        t_req = current_request_id.set("req-abc-123")
        try:
            logger.warning("BDI sem taxa para 'mao_obra'")
        finally:
            current_user_id.reset(t_user)
            current_request_id.reset(t_req)
        handler.flush()

        blobs = sorted(storage.listar_blobs("observability/bronze/logs/"))
        content = storage.ler_blob(blobs[-1]).decode("utf-8")
        record = json.loads(content.strip().splitlines()[0])
        assert record["user_id"] == "user-42"
        assert record["request_id"] == "req-abc-123"

    def test_handler_user_id_empty_outside_request_context(self, storage):
        """Fora de uma request (CLI, testes), user_id/request_id ficam vazios, não ausentes."""
        from concilium.infrastructure.observability.bronze_writer import BronzeLogHandler, BronzeWriter

        writer = BronzeWriter(storage, signal_type="logs")
        handler = BronzeLogHandler(writer)
        logger = logging.getLogger("test.bronze.no_context")
        logger.addHandler(handler)
        logger.setLevel(logging.WARNING)
        logger.warning("log sem request associada")
        handler.flush()

        blobs = sorted(storage.listar_blobs("observability/bronze/logs/"))
        content = storage.ler_blob(blobs[-1]).decode("utf-8")
        record = json.loads(content.strip().splitlines()[0])
        assert record["user_id"] == ""
        assert record["request_id"] == ""


# ─────────────────────────────────────────────────────────────────────────────
# F2: CheckpointStore
# ─────────────────────────────────────────────────────────────────────────────


class TestCheckpointStore:
    """Leitura/escrita/deleção de checkpoints JSON."""

    def test_load_returns_none_when_checkpoint_not_exists(self, storage):
        from concilium.infrastructure.observability.checkpoint_store import CheckpointStore

        store = CheckpointStore(storage)
        assert store.load("logs") is None

    def test_save_and_load_roundtrip(self, storage):
        from concilium.infrastructure.observability.checkpoint_store import Checkpoint, CheckpointStore

        store = CheckpointStore(storage)
        cp = Checkpoint(
            signal_type="logs",
            last_processed_path="observability/bronze/logs/2026-06-18/batch-abc.ndjson",
            last_processed_ts="2026-06-18T14:00:00Z",
            records_processed=42,
        )
        store.save(cp)
        loaded = store.load("logs")
        assert loaded is not None
        assert loaded.last_processed_path == cp.last_processed_path
        assert loaded.records_processed == 42

    def test_checkpoint_fields_required(self, storage):
        from concilium.infrastructure.observability.checkpoint_store import Checkpoint, CheckpointStore

        store = CheckpointStore(storage)
        cp = Checkpoint(signal_type="traces", last_processed_path="p", last_processed_ts="t", records_processed=0)
        store.save(cp)
        loaded = store.load("traces")
        assert hasattr(loaded, "signal_type")
        assert hasattr(loaded, "last_processed_path")
        assert hasattr(loaded, "last_processed_ts")
        assert hasattr(loaded, "records_processed")

    def test_delete_makes_load_return_none(self, storage):
        from concilium.infrastructure.observability.checkpoint_store import Checkpoint, CheckpointStore

        store = CheckpointStore(storage)
        store.save(Checkpoint("logs", "p", "t", 10))
        store.delete("logs")
        assert store.load("logs") is None

    def test_save_overwrites_existing_checkpoint(self, storage):
        from concilium.infrastructure.observability.checkpoint_store import Checkpoint, CheckpointStore

        store = CheckpointStore(storage)
        store.save(Checkpoint("logs", "path-A", "ts-A", 100))
        store.save(Checkpoint("logs", "path-B", "ts-B", 200))
        loaded = store.load("logs")
        assert loaded.last_processed_path == "path-B"
        assert loaded.records_processed == 200

    def test_independent_checkpoints_per_signal_type(self, storage):
        from concilium.infrastructure.observability.checkpoint_store import Checkpoint, CheckpointStore

        store = CheckpointStore(storage)
        store.save(Checkpoint("logs", "logs-path", "ts", 10))
        store.save(Checkpoint("traces", "traces-path", "ts", 20))
        assert store.load("logs").last_processed_path == "logs-path"
        assert store.load("traces").last_processed_path == "traces-path"

    def test_delete_swallows_storage_error(self):
        """delete() silently ignores exceptions from gravar_blob."""
        from unittest.mock import MagicMock

        from concilium.infrastructure.observability.checkpoint_store import CheckpointStore

        failing_storage = MagicMock()
        failing_storage.gravar_blob.side_effect = RuntimeError("storage unavailable")
        store = CheckpointStore(failing_storage)
        # Must not raise
        store.delete("logs")

    def test_load_all_returns_all_saved_checkpoints(self, storage):
        from concilium.infrastructure.observability.checkpoint_store import Checkpoint, CheckpointStore

        store = CheckpointStore(storage)
        store.save(Checkpoint("logs", "logs-path", "ts1", 10))
        store.save(Checkpoint("traces", "traces-path", "ts2", 20))
        checkpoints = store.load_all()
        signal_types = {cp.signal_type for cp in checkpoints}
        assert "logs" in signal_types
        assert "traces" in signal_types
        assert len(checkpoints) == 2

    def test_load_all_returns_empty_when_no_checkpoints(self, storage):
        from concilium.infrastructure.observability.checkpoint_store import CheckpointStore

        store = CheckpointStore(storage)
        assert store.load_all() == []

    def test_load_all_skips_deleted_checkpoints(self, storage):
        """load_all() ignores empty blobs (deleted checkpoints)."""
        from concilium.infrastructure.observability.checkpoint_store import Checkpoint, CheckpointStore

        store = CheckpointStore(storage)
        store.save(Checkpoint("logs", "path", "ts", 5))
        store.save(Checkpoint("traces", "path2", "ts2", 7))
        store.delete("logs")  # overwrites with empty bytes
        result = store.load_all()
        signal_types = {cp.signal_type for cp in result}
        assert "logs" not in signal_types
        assert "traces" in signal_types

    def test_load_all_skips_malformed_blobs(self, storage):
        """load_all() silently skips blobs with invalid JSON."""
        from concilium.infrastructure.observability.checkpoint_store import Checkpoint, CheckpointStore

        store = CheckpointStore(storage)
        store.save(Checkpoint("logs", "path", "ts", 3))
        # Write a corrupt blob at the same prefix location
        storage.gravar_blob("observability/checkpoints/corrupt.json", b"not-valid-json{{{")
        result = store.load_all()
        signal_types = {cp.signal_type for cp in result}
        assert "logs" in signal_types
        # corrupt blob is silently skipped — no crash


# ─────────────────────────────────────────────────────────────────────────────
# F3: SilverNormalizer
# ─────────────────────────────────────────────────────────────────────────────


class TestSilverNormalizer:
    """Normalização Bronze → Silver e classificação de fallback_type."""

    def test_normalize_log_record_mandatory_fields(self):
        from concilium.infrastructure.observability.silver_normalizer import normalize_log_record

        raw = {
            "ts": "2026-06-18T10:00:00Z",
            "severity": "WARNING",
            "logger": "concilium.domain.services.simulation",
            "message": "Função X sem preco_unitario",
            "trace_id": "abc123",
            "span_id": "def456",
            "service": "concilium",
        }
        norm = normalize_log_record(raw)
        for field in ("event_id", "trace_id", "span_id", "ts", "severity", "logger", "message", "service"):
            assert field in norm, f"Campo ausente: {field}"

    def test_normalize_log_record_extracts_skill_id_from_logger(self):
        from concilium.infrastructure.observability.silver_normalizer import normalize_log_record

        raw = {
            "logger": "concilium.skills.manifests.05-equipes-e-alocacao.skill",
            "message": "x",
            "ts": "",
            "severity": "",
            "trace_id": "",
            "span_id": "",
            "service": "",
        }
        norm = normalize_log_record(raw)
        assert norm["skill_id"] == "05"

    def test_normalize_log_record_skill_id_none_for_non_skill_logger(self):
        from concilium.infrastructure.observability.silver_normalizer import normalize_log_record

        raw = {
            "logger": "concilium.domain.services.simulation",
            "message": "x",
            "ts": "",
            "severity": "",
            "trace_id": "",
            "span_id": "",
            "service": "",
        }
        norm = normalize_log_record(raw)
        assert norm["skill_id"] is None

    # Classificação de fallback_type (ADR-110 patterns)

    def test_classify_preco_unitario_fallback(self):
        from concilium.infrastructure.observability.silver_normalizer import classify_fallback_type

        assert classify_fallback_type("Função SV-P0046-D sem preco_unitario no catálogo") == "preco_unitario"

    def test_classify_bdi_ausente_fallback(self):
        from concilium.infrastructure.observability.silver_normalizer import classify_fallback_type

        assert classify_fallback_type("BDI sem taxa para 'mao_obra' — markup zero") == "bdi_ausente"

    def test_classify_cpu_fallback(self):
        from concilium.infrastructure.observability.silver_normalizer import classify_fallback_type

        assert classify_fallback_type("Falha ao resolver CPU P0046 no catálogo mendeslobo") == "cpu_fallback"

    def test_classify_producao_horaria_fallback(self):
        from concilium.infrastructure.observability.silver_normalizer import classify_fallback_type

        assert classify_fallback_type("Produção horária não encontrada para cpu_id=X") == "producao_horaria"

    def test_classify_contexto_fallback(self):
        from concilium.infrastructure.observability.silver_normalizer import classify_fallback_type

        assert classify_fallback_type("Falha ao resolver contexto mendeslobo") == "contexto_fallback"

    def test_classify_none_for_unrecognized_message(self):
        from concilium.infrastructure.observability.silver_normalizer import classify_fallback_type

        assert classify_fallback_type("Pipeline executado com sucesso") is None

    def test_normalize_assigns_fallback_type_to_log(self):
        from concilium.infrastructure.observability.silver_normalizer import normalize_log_record

        raw = {
            "message": "BDI sem taxa para 'equipamentos'",
            "logger": "concilium.skills.06",
            "ts": "",
            "severity": "WARNING",
            "trace_id": "",
            "span_id": "",
            "service": "",
        }
        norm = normalize_log_record(raw)
        assert norm["fallback_type"] == "bdi_ausente"

    def test_normalize_fallback_type_none_for_clean_log(self):
        from concilium.infrastructure.observability.silver_normalizer import normalize_log_record

        raw = {
            "message": "Benchmark concluído com sucesso",
            "logger": "concilium.runner",
            "ts": "",
            "severity": "INFO",
            "trace_id": "",
            "span_id": "",
            "service": "",
        }
        norm = normalize_log_record(raw)
        assert norm["fallback_type"] is None

    def test_event_id_stable_for_same_record(self):
        """event_id deve ser determinístico para o mesmo record (dedup por re-processamento)."""
        from concilium.infrastructure.observability.silver_normalizer import normalize_log_record

        raw = {
            "trace_id": "abc",
            "span_id": "def",
            "ts": "2026-06-18T10:00:00Z",
            "severity": "WARNING",
            "logger": "x",
            "message": "y",
            "service": "concilium",
        }
        n1 = normalize_log_record(raw)
        n2 = normalize_log_record(raw)
        assert n1["event_id"] == n2["event_id"]

    def test_normalize_log_record_propagates_user_id(self):
        """user_id/request_id capturados no Bronze devem sobreviver à normalização Silver (ADR-121 D6)."""
        from concilium.infrastructure.observability.silver_normalizer import normalize_log_record

        raw = {
            "ts": "2026-06-18T10:00:00Z",
            "severity": "WARNING",
            "logger": "x",
            "message": "y",
            "trace_id": "",
            "span_id": "",
            "service": "concilium",
            "user_id": "user-42",
            "request_id": "req-abc-123",
        }
        norm = normalize_log_record(raw)
        assert norm["user_id"] == "user-42"
        assert norm["request_id"] == "req-abc-123"

    def test_normalize_log_record_user_id_none_when_absent(self):
        """Records Bronze antigos (sem user_id) não devem quebrar a normalização."""
        from concilium.infrastructure.observability.silver_normalizer import normalize_log_record

        raw = {
            "ts": "",
            "severity": "",
            "logger": "x",
            "message": "y",
            "trace_id": "",
            "span_id": "",
            "service": "",
        }
        norm = normalize_log_record(raw)
        assert norm["user_id"] is None
        assert norm["request_id"] is None


# ─────────────────────────────────────────────────────────────────────────────
# F4: ObservabilityWorker
# ─────────────────────────────────────────────────────────────────────────────


def _seed_bronze(storage, signal_type: str, date: str, records: list[dict]) -> str:
    """Helper: grava um batch Bronze na storage."""
    from concilium.infrastructure.observability.bronze_writer import BronzeWriter

    writer = BronzeWriter(storage, signal_type=signal_type)
    return writer.write_batch(records, date=date)


class TestObservabilityWorker:
    """Worker Bronze → Silver: fast-forward, idempotência, full-reload."""

    def test_run_processes_bronze_blobs(self, storage):
        from concilium.infrastructure.observability.pipeline import ObservabilityWorker

        _seed_bronze(
            storage,
            "logs",
            "2026-06-18",
            [
                {
                    "ts": "2026-06-18T10:00:00Z",
                    "severity": "WARNING",
                    "logger": "concilium.test",
                    "message": "BDI sem taxa",
                    "trace_id": "",
                    "span_id": "s1",
                    "service": "concilium",
                },
            ],
        )
        worker = ObservabilityWorker(storage)
        result = worker.run(signal_type="logs")
        assert result["blobs_processed"] == 1
        assert result["records_processed"] == 1

    def test_run_creates_checkpoint_after_processing(self, storage):
        from concilium.infrastructure.observability.checkpoint_store import CheckpointStore
        from concilium.infrastructure.observability.pipeline import ObservabilityWorker

        _seed_bronze(
            storage,
            "logs",
            "2026-06-18",
            [
                {
                    "ts": "t",
                    "severity": "W",
                    "logger": "l",
                    "message": "m",
                    "trace_id": "",
                    "span_id": "s2",
                    "service": "c",
                }
            ],
        )
        worker = ObservabilityWorker(storage)
        worker.run(signal_type="logs")
        checkpoint = CheckpointStore(storage).load("logs")
        assert checkpoint is not None
        assert checkpoint.records_processed == 1

    def test_fast_forward_second_run_processes_zero_blobs(self, storage):
        from concilium.infrastructure.observability.pipeline import ObservabilityWorker

        _seed_bronze(
            storage,
            "logs",
            "2026-06-18",
            [
                {
                    "ts": "t",
                    "severity": "W",
                    "logger": "l",
                    "message": "m",
                    "trace_id": "",
                    "span_id": "s3",
                    "service": "c",
                }
            ],
        )
        worker = ObservabilityWorker(storage)
        worker.run(signal_type="logs")
        result2 = worker.run(signal_type="logs")
        assert result2["blobs_processed"] == 0, "Segunda execução sem novos blobs deve processar 0"

    def test_fast_forward_processes_only_new_blobs(self, storage):
        from concilium.infrastructure.observability.pipeline import ObservabilityWorker

        worker = ObservabilityWorker(storage)
        _seed_bronze(
            storage,
            "logs",
            "2026-06-18",
            [
                {
                    "ts": "t",
                    "severity": "W",
                    "logger": "l",
                    "message": "m",
                    "trace_id": "",
                    "span_id": "s4",
                    "service": "c",
                }
            ],
        )
        worker.run(signal_type="logs")
        # Adiciona novo blob em data POSTERIOR — garante ordenação lexicográfica maior
        _seed_bronze(
            storage,
            "logs",
            "2026-06-19",
            [
                {
                    "ts": "t",
                    "severity": "W",
                    "logger": "l",
                    "message": "m2",
                    "trace_id": "",
                    "span_id": "s5",
                    "service": "c",
                }
            ],
        )
        result = worker.run(signal_type="logs")
        assert result["blobs_processed"] == 1
        assert result["records_processed"] == 1

    def test_full_reload_resets_checkpoint_and_reprocesses(self, storage):
        from concilium.infrastructure.observability.pipeline import ObservabilityWorker

        _seed_bronze(
            storage,
            "logs",
            "2026-06-18",
            [
                {
                    "ts": "t",
                    "severity": "W",
                    "logger": "l",
                    "message": "m",
                    "trace_id": "",
                    "span_id": "s6",
                    "service": "c",
                }
            ],
        )
        worker = ObservabilityWorker(storage)
        worker.run(signal_type="logs")
        result = worker.run(signal_type="logs", full_reload=True)
        assert result["blobs_processed"] == 1, "full_reload deve reprocessar todos os blobs"

    def test_idempotent_upsert_no_duplicate_silver_records(self, storage):
        """Processar o mesmo blob duas vezes (full_reload) não duplica Silver."""
        from concilium.infrastructure.observability.pipeline import ObservabilityWorker

        _seed_bronze(
            storage,
            "logs",
            "2026-06-18",
            [
                {
                    "ts": "t",
                    "severity": "W",
                    "logger": "l",
                    "message": "m",
                    "trace_id": "",
                    "span_id": "same-id",
                    "service": "c",
                }
            ],
        )
        worker = ObservabilityWorker(storage)
        worker.run(signal_type="logs")
        worker.run(signal_type="logs", full_reload=True)
        # Silver deve ter apenas 1 record com span_id="same-id"
        silver_records = worker.read_silver(signal_type="logs")
        deduped = {r["event_id"] for r in silver_records}
        assert len(deduped) == len(silver_records), "Nenhum event_id duplicado no Silver"

    def test_run_returns_zero_when_no_bronze_data(self, storage):
        from concilium.infrastructure.observability.pipeline import ObservabilityWorker

        worker = ObservabilityWorker(storage)
        result = worker.run(signal_type="logs")
        assert result["blobs_processed"] == 0
        assert result["records_processed"] == 0


# ─────────────────────────────────────────────────────────────────────────────
# F5: GoldAggregator
# ─────────────────────────────────────────────────────────────────────────────


def _seed_silver_traces(worker, records: list[dict]) -> None:
    """Helper: injeta records diretamente no Silver de traces."""
    from concilium.infrastructure.observability.silver_normalizer import normalize_span_record

    normalized = [normalize_span_record(r) for r in records]
    worker._upsert_silver("traces", normalized)


def _seed_silver_logs(worker, records: list[dict]) -> None:
    """Helper: injeta records normalizados diretamente no Silver de logs."""
    from concilium.infrastructure.observability.silver_normalizer import normalize_log_record

    normalized = [normalize_log_record(r) for r in records]
    worker._upsert_silver("logs", normalized)


class TestGoldAggregator:
    """Agregações Silver → Gold via DuckDB."""

    def test_sli_diario_computed_from_traces(self, storage):
        from concilium.infrastructure.observability.gold_aggregator import GoldAggregator
        from concilium.infrastructure.observability.pipeline import ObservabilityWorker

        worker = ObservabilityWorker(storage)
        _seed_silver_traces(
            worker,
            [
                {
                    "span_id": "a",
                    "trace_id": "t1",
                    "parent_span_id": None,
                    "service": "concilium",
                    "operation": "concilium.skill.05",
                    "start_ts": "2026-06-18T10:00:00Z",
                    "end_ts": "2026-06-18T10:00:02Z",
                    "duration_ms": 2000,
                    "status": "OK",
                    "project_id": "AGIS",
                    "skill_id": "05",
                },
                {
                    "span_id": "b",
                    "trace_id": "t2",
                    "parent_span_id": None,
                    "service": "concilium",
                    "operation": "concilium.skill.05",
                    "start_ts": "2026-06-18T10:01:00Z",
                    "end_ts": "2026-06-18T10:01:05Z",
                    "duration_ms": 5000,
                    "status": "OK",
                    "project_id": "AGIS",
                    "skill_id": "05",
                },
            ],
        )
        agg = GoldAggregator(storage)
        sli = agg.build_sli_diario()
        assert len(sli) >= 1
        row = next(r for r in sli if r["skill_id"] == "05")
        assert "p50_ms" in row
        assert "p95_ms" in row
        assert "p99_ms" in row

    def test_fallback_rate_computed_from_logs(self, storage):
        from concilium.infrastructure.observability.gold_aggregator import GoldAggregator
        from concilium.infrastructure.observability.pipeline import ObservabilityWorker

        worker = ObservabilityWorker(storage)
        _seed_silver_logs(
            worker,
            [
                {
                    "ts": "2026-06-18T10:00:00Z",
                    "severity": "WARNING",
                    "logger": "concilium.skills.06",
                    "message": "BDI sem taxa para 'mao_obra'",
                    "trace_id": "",
                    "span_id": "x1",
                    "service": "c",
                },
                {
                    "ts": "2026-06-18T10:00:01Z",
                    "severity": "INFO",
                    "logger": "concilium.skills.06",
                    "message": "skill concluída",
                    "trace_id": "",
                    "span_id": "x2",
                    "service": "c",
                },
                {
                    "ts": "2026-06-18T10:00:02Z",
                    "severity": "INFO",
                    "logger": "concilium.skills.06",
                    "message": "skill concluída",
                    "trace_id": "",
                    "span_id": "x3",
                    "service": "c",
                },
            ],
        )
        agg = GoldAggregator(storage)
        rates = agg.build_fallback_rate_por_skill()
        assert len(rates) >= 1
        row = next(r for r in rates if r.get("skill_id") == "06")
        assert "fallback_rate" in row
        assert 0.0 <= row["fallback_rate"] <= 1.0

    def test_alertas_ativos_triggered_when_p99_over_threshold(self, storage):
        from concilium.infrastructure.observability.gold_aggregator import GoldAggregator
        from concilium.infrastructure.observability.pipeline import ObservabilityWorker

        worker = ObservabilityWorker(storage)
        # skill com p99 > 30s
        _seed_silver_traces(
            worker,
            [
                {
                    "span_id": f"s{i}",
                    "trace_id": f"t{i}",
                    "parent_span_id": None,
                    "service": "c",
                    "operation": "concilium.skill.04",
                    "start_ts": "2026-06-18T10:00:00Z",
                    "end_ts": "2026-06-18T10:01:00Z",
                    "duration_ms": 40000 + i,
                    "status": "OK",
                    "project_id": "AGIS",
                    "skill_id": "04",
                }
                for i in range(5)
            ],
        )
        agg = GoldAggregator(storage)
        alertas = agg.build_alertas_ativos()
        tipos = {a["tipo"] for a in alertas}
        assert "p99_alto" in tipos

    def test_no_alertas_when_nominal(self, storage):
        from concilium.infrastructure.observability.gold_aggregator import GoldAggregator
        from concilium.infrastructure.observability.pipeline import ObservabilityWorker

        worker = ObservabilityWorker(storage)
        _seed_silver_traces(
            worker,
            [
                {
                    "span_id": "ok1",
                    "trace_id": "t1",
                    "parent_span_id": None,
                    "service": "c",
                    "operation": "concilium.skill.03",
                    "start_ts": "2026-06-18T10:00:00Z",
                    "end_ts": "2026-06-18T10:00:01Z",
                    "duration_ms": 800,
                    "status": "OK",
                    "project_id": "AGIS",
                    "skill_id": "03",
                }
            ],
        )
        agg = GoldAggregator(storage)
        alertas = agg.build_alertas_ativos()
        p99_alertas = [a for a in alertas if a["tipo"] == "p99_alto"]
        assert len(p99_alertas) == 0

    def test_alertas_triggered_by_high_fallback_rate(self, storage):
        from concilium.infrastructure.observability.gold_aggregator import GoldAggregator
        from concilium.infrastructure.observability.pipeline import ObservabilityWorker

        worker = ObservabilityWorker(storage)
        # 6 fallbacks em 10 logs → 60% > 5%
        logs = []
        for i in range(6):
            logs.append(
                {
                    "ts": f"2026-06-18T10:00:0{i}Z",
                    "severity": "WARNING",
                    "logger": "concilium.skills.manifests.06-resultado-financeiro.skill",
                    "message": "BDI sem taxa",
                    "trace_id": "",
                    "span_id": f"f{i}",
                    "service": "c",
                }
            )
        for i in range(4):
            logs.append(
                {
                    "ts": f"2026-06-18T10:01:0{i}Z",
                    "severity": "INFO",
                    "logger": "concilium.skills.manifests.06-resultado-financeiro.skill",
                    "message": "concluído",
                    "trace_id": "",
                    "span_id": f"ok{i}",
                    "service": "c",
                }
            )
        _seed_silver_logs(worker, logs)
        agg = GoldAggregator(storage)
        alertas = agg.build_alertas_ativos()
        tipos = {a["tipo"] for a in alertas}
        assert "fallback_alto" in tipos


# ─────────────────────────────────────────────────────────────────────────────
# F6: CLI commands
# ─────────────────────────────────────────────────────────────────────────────


class TestObservabilityCLI:
    """CLI commands: run, status, report."""

    def test_cli_run_calls_worker_run(self, monkeypatch, tmp_path):
        from typer.testing import CliRunner

        from concilium.presentation.cli.commands_observability import observability_app

        called = {}

        def fake_run(self, signal_type="logs", full_reload=False, since=None):
            called["signal_type"] = signal_type
            called["full_reload"] = full_reload
            return {"blobs_processed": 2, "records_processed": 10}

        from concilium.infrastructure.observability import pipeline as pipeline_mod

        monkeypatch.setattr(pipeline_mod.ObservabilityWorker, "run", fake_run)
        monkeypatch.setenv("CONCILIUM__CONFIG_ROOT", str(tmp_path))
        runner = CliRunner()
        runner.invoke(observability_app, ["run"])
        assert called.get("signal_type") is not None

    def test_cli_run_full_reload_flag(self, monkeypatch, tmp_path):
        from typer.testing import CliRunner

        from concilium.presentation.cli.commands_observability import observability_app

        called = {}

        def fake_run(self, signal_type="logs", full_reload=False, since=None):
            called["full_reload"] = full_reload
            return {"blobs_processed": 0, "records_processed": 0}

        from concilium.infrastructure.observability import pipeline as pipeline_mod

        monkeypatch.setattr(pipeline_mod.ObservabilityWorker, "run", fake_run)
        monkeypatch.setenv("CONCILIUM__CONFIG_ROOT", str(tmp_path))
        runner = CliRunner()
        runner.invoke(observability_app, ["run", "--full-reload"])
        assert called.get("full_reload") is True

    def test_cli_status_shows_checkpoints(self, monkeypatch, tmp_path, storage):
        from typer.testing import CliRunner

        from concilium.infrastructure.observability.checkpoint_store import Checkpoint, CheckpointStore
        from concilium.presentation.cli.commands_observability import observability_app

        CheckpointStore(storage).save(Checkpoint("logs", "path/abc.ndjson", "2026-06-18T10:00:00Z", 42))
        # Patch storage creation to return our fixture storage
        from concilium.infrastructure.observability import pipeline as pipeline_mod

        monkeypatch.setattr(pipeline_mod, "_make_storage", lambda: storage)
        monkeypatch.setenv("CONCILIUM__CONFIG_ROOT", str(tmp_path))
        runner = CliRunner()
        result = runner.invoke(observability_app, ["status"])
        assert result.exit_code == 0
        assert "logs" in result.output


# ─────────────────────────────────────────────────────────────────────────────
# Missing branch coverage
# ─────────────────────────────────────────────────────────────────────────────


class TestReadNdjsonInvalidLine:
    """Line 65-66: json.JSONDecodeError em linha inválida é ignorada com warning."""

    def test_invalid_line_skipped_returns_valid_records(self, storage, caplog):
        from concilium.infrastructure.observability.pipeline import ObservabilityWorker

        worker = ObservabilityWorker(storage)
        # Write an NDJSON blob with one valid + one invalid line
        path = "bronze/logs/2026-06-30/test.ndjson"
        content = '{"event_id": "e1", "msg": "ok"}\nnot-valid-json\n'
        storage.gravar_blob(path, content.encode())

        with caplog.at_level(logging.WARNING):
            records = worker._read_ndjson(path)

        assert len(records) == 1
        assert records[0]["event_id"] == "e1"
        assert any("inválida" in r.message for r in caplog.records)


class TestReadSilverExceptionSwallowed:
    """Lines 114-115: exceção durante ler_blob é silenciada em read_silver."""

    def test_exception_in_ler_blob_returns_partial(self, storage):
        from unittest.mock import patch

        from concilium.infrastructure.observability.pipeline import ObservabilityWorker

        worker = ObservabilityWorker(storage)
        # Save one valid blob and simulate failure on a second
        path1 = "silver/logs/2026-06-30/records.ndjson"
        storage.gravar_blob(path1, b'{"event_id":"e1"}\n')

        original_listar = storage.listar_blobs
        original_ler = storage.ler_blob

        def patched_ler(path):
            if "records.ndjson" in path and "broken" in path:
                raise OSError("network error")
            return original_ler(path)

        def patched_listar(prefix):
            if "silver/logs" in prefix:
                return [path1, "silver/logs/2026-06-30/broken.ndjson"]
            return original_listar(prefix)

        with patch.object(storage, "listar_blobs", patched_listar):
            with patch.object(storage, "ler_blob", patched_ler):
                records = worker.read_silver("logs")

        # Partial results from the valid blob
        assert any(r.get("event_id") == "e1" for r in records)


class TestRunSinceFilter:
    """Line 147: elif since: filtra blobs pelo fragmento de data."""

    def test_since_filters_blobs_by_date_fragment(self, storage):
        from concilium.infrastructure.observability.bronze_writer import BronzeWriter
        from concilium.infrastructure.observability.pipeline import ObservabilityWorker

        # Write blobs on two different dates
        writer = BronzeWriter(storage, signal_type="logs")
        writer.write_batch([{"event_id": "old", "ts": "2026-06-01T00:00:00Z"}], date="2026-06-01")
        writer.write_batch([{"event_id": "new", "ts": "2026-06-30T00:00:00Z"}], date="2026-06-30")

        worker = ObservabilityWorker(storage)
        # since="2026-06-30" should only pick up the newer blob
        result = worker.run(signal_type="logs", since="2026-06-30")
        assert result["blobs_processed"] == 1
        assert result["records_processed"] == 1


class TestSchedulerLastRunValueError:
    """Lines 215-216: _last_run retorna None quando last_processed_ts é inválido."""

    def test_corrupt_ts_returns_none(self, storage):
        from concilium.infrastructure.observability.checkpoint_store import Checkpoint, CheckpointStore
        from concilium.infrastructure.observability.pipeline import ObservabilityScheduler

        CheckpointStore(storage).save(
            Checkpoint(
                signal_type="__sched_silver__",
                last_processed_path="",
                last_processed_ts="not-a-datetime",
                records_processed=0,
            )
        )
        scheduler = ObservabilityScheduler(storage)
        result = scheduler._last_run("__sched_silver__")
        assert result is None


class TestSchedulerRunCycleDefaultNow:
    """Line 242: run_cycle usa datetime.now quando now não é passado."""

    def test_run_cycle_without_now_succeeds(self, storage):
        from concilium.infrastructure.observability.pipeline import ObservabilityScheduler

        scheduler = ObservabilityScheduler(storage, silver_interval_min=0, gold_interval_min=9999)
        result = scheduler.run_cycle()  # no now= argument
        assert "silver_ran" in result


class TestSchedulerSilverException:
    """Lines 253-254: exceção em worker.run é capturada e logada."""

    def test_silver_worker_exception_logged(self, storage, caplog):
        from unittest.mock import patch

        from concilium.infrastructure.observability.pipeline import ObservabilityScheduler

        scheduler = ObservabilityScheduler(storage, silver_interval_min=0, gold_interval_min=9999)

        import datetime

        def boom(self, signal_type="logs", full_reload=False, since=None):
            raise RuntimeError("silver exploded")

        from concilium.infrastructure.observability import pipeline as pm

        with patch.object(pm.ObservabilityWorker, "run", boom):
            with caplog.at_level(logging.WARNING):
                result = scheduler.run_cycle(now=datetime.datetime(2026, 6, 30, 12, 0, tzinfo=datetime.UTC))

        assert result["silver_ran"] is True  # mark ran even on partial failure
        assert any("Silver" in r.message for r in caplog.records)


class TestSchedulerGoldException:
    """Lines 267-268: exceção no GoldAggregator é capturada e logada."""

    def test_gold_aggregator_exception_logged(self, storage, caplog):
        from unittest.mock import patch

        from concilium.infrastructure.observability.pipeline import ObservabilityScheduler

        scheduler = ObservabilityScheduler(storage, silver_interval_min=9999, gold_interval_min=0)

        import datetime

        with patch(
            "concilium.infrastructure.observability.gold_aggregator.GoldAggregator.write_gold",
            side_effect=RuntimeError("gold failed"),
        ):
            with caplog.at_level(logging.WARNING):
                scheduler.run_cycle(now=datetime.datetime(2026, 6, 30, 12, 0, tzinfo=datetime.UTC))

        assert any("Gold" in r.message for r in caplog.records)


class TestSchedulerCrossDomainException:
    """Lines 284-286: exceção em CrossDomain é capturada; result['cross_domain_ran']=False."""

    def test_cross_domain_failure_sets_flag_false(self, storage, caplog):
        from unittest.mock import MagicMock, patch

        from concilium.infrastructure.observability.pipeline import ObservabilityScheduler

        scheduler = ObservabilityScheduler(storage, silver_interval_min=9999, gold_interval_min=0)

        import datetime

        mock_cfg = MagicMock()
        mock_cfg.projects_root = "/fake/projects"

        # GoldAggregator succeeds; CrossDomain import fails
        with patch("concilium.infrastructure.observability.gold_aggregator.GoldAggregator.write_gold"):
            with patch("concilium.infrastructure.settings.get_storage", return_value=mock_cfg):
                with patch(
                    "concilium.infrastructure.observability.cross_domain.default_canonical_provider",
                    side_effect=RuntimeError("cross domain boom"),
                ):
                    with caplog.at_level(logging.WARNING):
                        result = scheduler.run_cycle(now=datetime.datetime(2026, 6, 30, 12, 0, tzinfo=datetime.UTC))

        assert result.get("cross_domain_ran") is False
        assert any("CrossDomain" in r.message for r in caplog.records)


class TestSchedulerCrossDomainNoProjectsRoot:
    """Branch 280→288: projects_root falsy (no projects_root and no root
    configured) → CrossDomain block is skipped entirely, no exception, no flag."""

    def test_no_projects_root_skips_cross_domain(self, storage):
        from unittest.mock import MagicMock, patch

        from concilium.infrastructure.observability.pipeline import ObservabilityScheduler

        scheduler = ObservabilityScheduler(storage, silver_interval_min=9999, gold_interval_min=0)

        import datetime

        mock_cfg = MagicMock()
        mock_cfg.projects_root = None
        mock_cfg.root = None

        with patch("concilium.infrastructure.observability.gold_aggregator.GoldAggregator.write_gold"):
            with patch("concilium.infrastructure.settings.get_storage", return_value=mock_cfg):
                result = scheduler.run_cycle(now=datetime.datetime(2026, 6, 30, 12, 0, tzinfo=datetime.UTC))

        assert "cross_domain_ran" not in result
