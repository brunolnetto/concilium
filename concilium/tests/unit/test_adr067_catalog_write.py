"""Tests for ADR-067 — Master Catalog Write API.

Covers:
  - upsert_catalog_cpu creates file
  - upsert_catalog_cpu invalidates bundle cache
  - upsert_catalog_cpu appends to audit log
  - upsert_catalog_cpu preserves previous snapshot in audit
  - validation rejects missing required fields
  - validation rejects cpu_id mismatch
  - validation rejects empty motivo
"""

from __future__ import annotations

import json

import pytest

from concilium.application.services.audit_service import AuditService
from concilium.application.services.concilium_service import (
    ConciliumDependencies,
    ConciliumService,
)
from concilium.application.services.override_service import OverrideService
from concilium.application.services.pipeline_service import PipelineService
from concilium.application.services.project_input_builder import ProjectInputBuilder
from concilium.application.services.project_service import ProjectService
from concilium.infrastructure.storage.file_project_repository import FileProjectRepository


@pytest.fixture
def catalog_env(tmp_path):
    """Creates a minimal config_root with a test catalog."""
    config_root = tmp_path / "config"
    cats_dir = config_root / "catalogos" / "test-cat" / "cpus"
    cats_dir.mkdir(parents=True)
    projects_root = tmp_path / "projetos"
    projects_root.mkdir()
    return config_root, cats_dir, projects_root


@pytest.fixture
def service(catalog_env):
    config_root, _cats_dir, projects_root = catalog_env

    repo = FileProjectRepository(projects_root)
    audit = AuditService()
    ps = ProjectService(repo, audit)
    os_ = OverrideService(repo, audit)

    from concilium.application.runtime import Runtime

    pls = PipelineService(repo, audit, runtime_factory=lambda: Runtime(config_root))
    ib = ProjectInputBuilder(config_root, config_root / "benchmarks" / "data")

    svc = ConciliumService(
        ConciliumDependencies(
            input_builder=ib,
            repository=repo,
            project_service=ps,
            override_service=os_,
            pipeline_service=pls,
            audit_service=audit,
            benchmarks_root=config_root / "benchmarks" / "data",
        )
    )
    return svc


_VALID_CPU = {
    "codigo": "CPU-TEST-001",
    "descricao": "CPU de teste para ADR-067",
    "unidade": "m³",
    "categoria": "TERRAPLENAGEM",
    "composicao_itens": [],
}


class TestUpsertCatalogCpu:
    def test_creates_file(self, service, catalog_env):
        config_root, cats_dir, _ = catalog_env
        service.upsert_catalog_cpu("test-cat", "CPU-TEST-001", _VALID_CPU, actor="user", motivo="initial")
        cpu_file = cats_dir / "CPU-TEST-001.json"
        assert cpu_file.exists()
        saved = json.loads(cpu_file.read_text(encoding="utf-8"))
        assert saved["codigo"] == "CPU-TEST-001"
        assert saved["descricao"] == "CPU de teste para ADR-067"

    def test_invalidates_bundle_cache(self, service, catalog_env):
        config_root, cats_dir, _ = catalog_env
        # Create a fake bundle cache
        bundle = cats_dir.parent / ".catalog_bundle.json"
        bundle.write_text("{}", encoding="utf-8")
        assert bundle.exists()

        service.upsert_catalog_cpu("test-cat", "CPU-TEST-001", _VALID_CPU, actor="user", motivo="bust cache")
        assert not bundle.exists(), "Bundle cache should be deleted after write"

    def test_writes_audit_entry(self, service, catalog_env):
        config_root, cats_dir, _ = catalog_env
        service.upsert_catalog_cpu("test-cat", "CPU-TEST-001", _VALID_CPU, actor="alice", motivo="test audit")

        audit = cats_dir.parent / ".catalog_audit.jsonl"
        assert audit.exists()
        entry = json.loads(audit.read_text(encoding="utf-8").strip().splitlines()[-1])
        assert entry["event"] == "upsert_cpu"
        assert entry["cpu_id"] == "CPU-TEST-001"
        assert entry["actor"] == "alice"
        assert entry["motivo"] == "test audit"

    def test_preserves_previous_in_audit(self, service, catalog_env):
        config_root, cats_dir, _ = catalog_env
        # Write initial state
        service.upsert_catalog_cpu("test-cat", "CPU-TEST-001", _VALID_CPU, actor="u1", motivo="initial")
        # Overwrite
        updated = {**_VALID_CPU, "descricao": "CPU atualizada"}
        service.upsert_catalog_cpu("test-cat", "CPU-TEST-001", updated, actor="u2", motivo="update")

        audit = cats_dir.parent / ".catalog_audit.jsonl"
        lines = audit.read_text(encoding="utf-8").strip().splitlines()
        assert len(lines) == 2
        second = json.loads(lines[1])
        assert second["previous_snapshot"]["descricao"] == "CPU de teste para ADR-067"

    def test_returns_result_with_timestamp(self, service, catalog_env):
        result = service.upsert_catalog_cpu("test-cat", "CPU-TEST-001", _VALID_CPU, motivo="ok")
        assert result["catalog_id"] == "test-cat"
        assert result["cpu_id"] == "CPU-TEST-001"
        assert "saved_at" in result
        assert result["bundle_invalidated"] is True

    # ── Validation ────────────────────────────────────────────────────────────

    def test_rejects_missing_codigo(self, service, catalog_env):
        bad = {**_VALID_CPU, "codigo": ""}
        with pytest.raises(ValueError, match="codigo"):
            service.upsert_catalog_cpu("test-cat", "CPU-TEST-001", bad, motivo="x")

    def test_rejects_codigo_mismatch(self, service, catalog_env):
        bad = {**_VALID_CPU, "codigo": "CPU-OTHER"}
        with pytest.raises(ValueError, match="coincid"):
            service.upsert_catalog_cpu("test-cat", "CPU-TEST-001", bad, motivo="x")

    def test_rejects_missing_descricao(self, service, catalog_env):
        bad = {**_VALID_CPU, "descricao": ""}
        with pytest.raises(ValueError, match="descricao"):
            service.upsert_catalog_cpu("test-cat", "CPU-TEST-001", bad, motivo="x")

    def test_rejects_missing_unidade(self, service, catalog_env):
        bad = {**_VALID_CPU, "unidade": ""}
        with pytest.raises(ValueError, match="unidade"):
            service.upsert_catalog_cpu("test-cat", "CPU-TEST-001", bad, motivo="x")

    def test_rejects_empty_motivo(self, service, catalog_env):
        with pytest.raises(ValueError, match="motivo"):
            service.upsert_catalog_cpu("test-cat", "CPU-TEST-001", _VALID_CPU, motivo="")

    def test_rejects_invalid_composicao_type(self, service, catalog_env):
        bad = {**_VALID_CPU, "composicao_itens": "not-a-list"}
        with pytest.raises(ValueError, match="lista"):
            service.upsert_catalog_cpu("test-cat", "CPU-TEST-001", bad, motivo="x")

    def test_rejects_nonexistent_catalog(self, service, catalog_env):
        cpu_nonexist = {**_VALID_CPU, "codigo": "CPU-TEST-001"}
        with pytest.raises(FileNotFoundError, match="nonexistent"):
            service.upsert_catalog_cpu("nonexistent", "CPU-TEST-001", cpu_nonexist, motivo="x")
