"""Tests for infrastructure/storage/benchmark_store.py."""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import MagicMock

import pytest


def _make_meta(bid="bench-1", versao=1, imutavel=False):
    from concilium.domain.benchmark.models import BenchmarkMetadata
    return BenchmarkMetadata(
        benchmark_id=bid,
        nome="Test",
        origem="manual",
        tags=["t1"],
        criado_em=datetime(2026, 1, 1, tzinfo=timezone.utc),
        versao=versao,
        imutavel=imutavel,
    )


def _make_exec(bid="bench-1", status="SUCESSO"):
    from concilium.domain.benchmark.models import BenchmarkExecution
    return BenchmarkExecution(
        execution_id="exec-1",
        benchmark_id=bid,
        versao=1,
        projeto_id="proj-1",
        status=status,
        executado_em=datetime(2026, 1, 2, tzinfo=timezone.utc),
        discrepancia_sumario={"decision": status},
    )


def _make_store(tmp_path):
    from concilium.infrastructure.storage.benchmark_store import FileSystemBenchmarkStore
    return FileSystemBenchmarkStore(root=tmp_path)


class TestFromPath:
    def test_creates_store(self, tmp_path):
        store = _make_store(tmp_path)
        assert store is not None

    def test_from_root_kwarg(self, tmp_path):
        from concilium.infrastructure.storage.benchmark_store import FileSystemBenchmarkStore
        store = FileSystemBenchmarkStore(root=tmp_path)
        assert store.root == tmp_path

    def test_no_storage_no_root_raises(self):
        from concilium.infrastructure.storage.benchmark_store import FileSystemBenchmarkStore
        with pytest.raises(TypeError, match="storage"):
            FileSystemBenchmarkStore()


class TestSaveAndGetMetadata:
    def test_save_and_get_metadata(self, tmp_path):
        store = _make_store(tmp_path)
        meta = _make_meta()
        store.save_metadata(meta)
        loaded = store.get_metadata("bench-1")
        assert loaded is not None
        assert loaded.benchmark_id == "bench-1"
        assert loaded.versao == 1

    def test_get_metadata_missing_returns_none(self, tmp_path):
        store = _make_store(tmp_path)
        assert store.get_metadata("nonexistent") is None

    def test_get_metadata_picks_latest_version(self, tmp_path):
        store = _make_store(tmp_path)
        store.save_metadata(_make_meta(versao=1))
        store.save_metadata(_make_meta(versao=2))
        store.save_metadata(_make_meta(versao=3))
        loaded = store.get_metadata("bench-1")
        assert loaded.versao == 3

    def test_get_metadata_by_version(self, tmp_path):
        store = _make_store(tmp_path)
        store.save_metadata(_make_meta(versao=1))
        store.save_metadata(_make_meta(versao=2))
        loaded = store.get_metadata_by_version("bench-1", 1)
        assert loaded.versao == 1

    def test_get_metadata_by_version_missing(self, tmp_path):
        store = _make_store(tmp_path)
        assert store.get_metadata_by_version("bench-1", 99) is None

    def test_save_immutable_raises_on_overwrite(self, tmp_path):
        store = _make_store(tmp_path)
        meta = _make_meta(imutavel=True)
        store.save_metadata(meta)
        # Trying to save again with imutavel=True should raise
        with pytest.raises(PermissionError):
            store.save_metadata(_make_meta(imutavel=True))


class TestListAll:
    def test_list_all_empty(self, tmp_path):
        store = _make_store(tmp_path)
        assert store.list_all() == []

    def test_list_all_multiple_benchmarks(self, tmp_path):
        store = _make_store(tmp_path)
        store.save_metadata(_make_meta("bench-1", versao=1))
        store.save_metadata(_make_meta("bench-2", versao=1))
        result = store.list_all()
        ids = {m.benchmark_id for m in result}
        assert "bench-1" in ids
        assert "bench-2" in ids

    def test_list_all_returns_latest_per_benchmark(self, tmp_path):
        store = _make_store(tmp_path)
        store.save_metadata(_make_meta("bench-1", versao=1))
        store.save_metadata(_make_meta("bench-1", versao=2))
        result = store.list_all()
        bench1_entries = [m for m in result if m.benchmark_id == "bench-1"]
        assert len(bench1_entries) == 1
        assert bench1_entries[0].versao == 2


class TestLogExecution:
    def test_log_and_get_history(self, tmp_path):
        store = _make_store(tmp_path)
        exec_ = _make_exec()
        store.log_execution(exec_)
        history = store.get_execution_history("bench-1")
        assert len(history) == 1
        assert history[0].execution_id == "exec-1"

    def test_multiple_executions(self, tmp_path):
        from concilium.domain.benchmark.models import BenchmarkExecution
        store = _make_store(tmp_path)
        for i in range(3):
            store.log_execution(
                BenchmarkExecution(
                    execution_id=f"exec-{i}",
                    benchmark_id="bench-1",
                    versao=1,
                    projeto_id="proj-1",
                    status="SUCESSO",
                    executado_em=datetime(2026, 1, i + 1, tzinfo=timezone.utc),
                )
            )
        history = store.get_execution_history("bench-1", limit=50)
        assert len(history) == 3

    def test_history_filters_by_benchmark_id(self, tmp_path):
        store = _make_store(tmp_path)
        store.log_execution(_make_exec("bench-1"))
        store.log_execution(_make_exec("bench-2"))
        history = store.get_execution_history("bench-1")
        assert all(e.benchmark_id == "bench-1" for e in history)

    def test_history_empty_when_no_log(self, tmp_path):
        store = _make_store(tmp_path)
        assert store.get_execution_history("bench-1") == []

    def test_history_limit(self, tmp_path):
        from concilium.domain.benchmark.models import BenchmarkExecution
        store = _make_store(tmp_path)
        for i in range(10):
            store.log_execution(
                BenchmarkExecution(
                    execution_id=f"exec-{i}",
                    benchmark_id="bench-1",
                    versao=1,
                    projeto_id="proj-1",
                    status="SUCESSO",
                    executado_em=datetime(2026, 1, 1, tzinfo=timezone.utc),
                )
            )
        history = store.get_execution_history("bench-1", limit=5)
        assert len(history) == 5


class TestCreateNewVersion:
    def test_create_new_version(self, tmp_path):
        store = _make_store(tmp_path)
        store.save_metadata(_make_meta(versao=1))
        new = store.create_new_version("bench-1", {"nome": "Updated"})
        assert new.versao == 2
        assert new.nome == "Updated"
        assert not new.imutavel

    def test_create_new_version_missing_raises(self, tmp_path):
        store = _make_store(tmp_path)
        with pytest.raises(ValueError, match="não existe"):
            store.create_new_version("nonexistent", {})


class TestUpdateMetadata:
    def test_update_metadata(self, tmp_path):
        store = _make_store(tmp_path)
        store.save_metadata(_make_meta(versao=1))
        store.update_metadata("bench-1", {"nome": "Renamed"})
        loaded = store.get_metadata("bench-1")
        assert loaded.nome == "Renamed"

    def test_update_metadata_missing_raises(self, tmp_path):
        store = _make_store(tmp_path)
        with pytest.raises(ValueError):
            store.update_metadata("nonexistent", {})

    def test_update_metadata_immutable_raises(self, tmp_path):
        from concilium.infrastructure.storage.benchmark_store import FileSystemBenchmarkStore
        store = _make_store(tmp_path)
        # Save a mutable version first
        meta = _make_meta(imutavel=False)
        store.save_metadata(meta)
        # Overwrite the JSON on disk to set imutavel=True
        meta_dir = tmp_path / "metadata"
        meta_file = meta_dir / "bench-1-v1.json"
        d = json.loads(meta_file.read_text())
        d["imutavel"] = True
        meta_file.write_text(json.dumps(d))
        with pytest.raises(PermissionError):
            store.update_metadata("bench-1", {"nome": "fail"})


class TestSerialisation:
    def test_to_dict_and_from_dict_roundtrip(self):
        from concilium.infrastructure.storage.benchmark_store import FileSystemBenchmarkStore
        meta = _make_meta()
        d = FileSystemBenchmarkStore._to_dict(meta)
        assert d["benchmark_id"] == "bench-1"
        restored = FileSystemBenchmarkStore._from_dict(d)
        assert restored.benchmark_id == meta.benchmark_id
        assert restored.versao == meta.versao

    def test_exec_to_dict_and_from_dict_roundtrip(self):
        from concilium.infrastructure.storage.benchmark_store import FileSystemBenchmarkStore
        exec_ = _make_exec()
        d = FileSystemBenchmarkStore._exec_to_dict(exec_)
        assert d["execution_id"] == "exec-1"
        restored = FileSystemBenchmarkStore._exec_from_dict(d)
        assert restored.execution_id == exec_.execution_id
        assert restored.discrepancia_sumario == exec_.discrepancia_sumario
