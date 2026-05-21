"""Tests for ADR-066 — Catalog Overlay Model (Single Source of Truth).

Covers:
  F1: CatalogResolver — 3-layer resolution (master > jurisdiction > project)
  F2: set_overlay() — creates cpus_overlay.json + audit trail
  F4: resolved_catalog.json — compact catalog per run
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from concilium.application.services.catalog_resolver import (
    CatalogResolutionTrace,
    CatalogResolver,
    _deep_merge,
)

# ─── _deep_merge helper ───────────────────────────────────────────────────────

class TestDeepMerge:
    def test_scalar_override(self):
        result = _deep_merge({"a": 1, "b": 2}, {"b": 99})
        assert result == {"a": 1, "b": 99}

    def test_nested_dict_merge(self):
        base = {"a": {"x": 1, "y": 2}}
        overlay = {"a": {"y": 99, "z": 3}}
        result = _deep_merge(base, overlay)
        assert result["a"] == {"x": 1, "y": 99, "z": 3}

    def test_new_key_added(self):
        result = _deep_merge({"a": 1}, {"b": 2})
        assert result == {"a": 1, "b": 2}

    def test_does_not_mutate_base(self):
        base = {"a": 1}
        _deep_merge(base, {"a": 2})
        assert base["a"] == 1


# ─── CatalogResolutionTrace ───────────────────────────────────────────────────

class TestCatalogResolutionTrace:
    def test_record_and_to_dict(self):
        trace = CatalogResolutionTrace()
        trace.record("CPU-A", "master")
        trace.record("CPU-B", "project")
        d = trace.to_dict()
        assert d["CPU-A"] == "master"
        assert d["CPU-B"] == "project"


# ─── CatalogResolver.apply_overlays ──────────────────────────────────────────

class _FakeProject:
    def __init__(self, project_root: Path):
        self._root = project_root
        self._meta: dict = {"id": "fake-project", "catalogo_base": "mendeslobo"}

    @property
    def root(self) -> Path:
        return self._root

    @property
    def meta(self) -> dict:
        return self._meta

    def read_json(self, relative_path: str, default):
        path = self._root / relative_path
        if not path.exists():
            return default
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            return default


class TestCatalogResolverApplyOverlays:
    @pytest.fixture
    def setup(self, tmp_path):
        """Setup: config_root with minimal structure + project with overlay."""
        config_root = tmp_path / "config"
        config_root.mkdir()

        proj_root = tmp_path / "projetos" / "test-proj"
        proj_root.mkdir(parents=True)
        (proj_root / "overrides").mkdir()

        project = _FakeProject(proj_root)
        resolver = CatalogResolver(config_root)

        master = {
            "cpus": [
                {"codigo": "CPU-A", "descricao": "Original A", "producao_horaria": 10.0},
                {"codigo": "CPU-B", "descricao": "Original B", "producao_horaria": 20.0},
            ],
            "insumos": [
                {"id": "INS-001", "preco_unitario": 100.0},
            ],
            "producoes": [],
        }
        return config_root, proj_root, project, resolver, master

    def test_no_overlays_returns_master(self, setup):
        _, _, project, resolver, master = setup
        resolved, trace = resolver.apply_overlays(master, project)
        assert len(resolved["cpus"]) == 2
        assert trace.to_dict().get("CPU-A") == "master"
        assert trace.to_dict().get("CPU-B") == "master"

    def test_project_overlay_overrides_master(self, setup):
        config_root, proj_root, project, resolver, master = setup
        overlay_file = proj_root / "overrides" / "cpus_overlay.json"
        overlay_file.write_text(json.dumps({
            "CPU-A": {"descricao": "Customizado A", "producao_horaria": 999.0}
        }), encoding="utf-8")

        resolved, trace = resolver.apply_overlays(master, project)
        cpu_a = next(c for c in resolved["cpus"] if c["codigo"] == "CPU-A")
        assert cpu_a["producao_horaria"] == 999.0
        assert cpu_a["descricao"] == "Customizado A"
        assert trace.to_dict().get("CPU-A") == "project"
        assert trace.to_dict().get("CPU-B") == "master"

    def test_project_only_cpu_added(self, setup):
        config_root, proj_root, project, resolver, master = setup
        overlay_file = proj_root / "overrides" / "cpus_overlay.json"
        overlay_file.write_text(json.dumps({
            "CPU-NEW": {"codigo": "CPU-NEW", "descricao": "Nova CPU do projeto"}
        }), encoding="utf-8")

        resolved, trace = resolver.apply_overlays(master, project)
        ids = [c["codigo"] for c in resolved["cpus"]]
        assert "CPU-NEW" in ids
        assert trace.to_dict().get("CPU-NEW") == "project"

    def test_jurisdiction_overlay_applied(self, setup):
        config_root, proj_root, project, resolver, master = setup

        # Create jurisdiction overlay
        jur_dir = config_root / "jurisdicoes" / "BR-CE"
        jur_dir.mkdir(parents=True)
        (jur_dir / "overlay.json").write_text(json.dumps({
            "cpus": {"CPU-B": {"producao_horaria": 777.0}}
        }), encoding="utf-8")

        resolved, trace = resolver.apply_overlays(master, project, "BR-CE")
        cpu_b = next(c for c in resolved["cpus"] if c["codigo"] == "CPU-B")
        assert cpu_b["producao_horaria"] == 777.0
        assert trace.to_dict().get("CPU-B") == "jurisdiction"

    def test_project_beats_jurisdiction(self, setup):
        config_root, proj_root, project, resolver, master = setup

        jur_dir = config_root / "jurisdicoes" / "BR-CE"
        jur_dir.mkdir(parents=True)
        (jur_dir / "overlay.json").write_text(json.dumps({
            "cpus": {"CPU-A": {"producao_horaria": 50.0}}
        }), encoding="utf-8")

        (proj_root / "overrides" / "cpus_overlay.json").write_text(json.dumps({
            "CPU-A": {"producao_horaria": 100.0}
        }), encoding="utf-8")

        resolved, trace = resolver.apply_overlays(master, project, "BR-CE")
        cpu_a = next(c for c in resolved["cpus"] if c["codigo"] == "CPU-A")
        assert cpu_a["producao_horaria"] == 100.0
        assert trace.to_dict().get("CPU-A") == "project"

    def test_build_resolved_catalog_filters_to_eap(self, setup):
        config_root, proj_root, project, resolver, master = setup
        resolved, _trace = resolver.build_resolved_catalog(
            master, project, None, eap_cpu_ids={"CPU-A"}
        )
        assert len(resolved["cpus"]) == 1
        assert resolved["cpus"][0]["codigo"] == "CPU-A"

    def test_build_resolved_catalog_no_filter(self, setup):
        config_root, proj_root, project, resolver, master = setup
        resolved, _trace = resolver.build_resolved_catalog(
            master, project, None, eap_cpu_ids=None
        )
        assert len(resolved["cpus"]) == 2

    def test_missing_overlay_returns_master(self, setup):
        """No overlay file → all items from master."""
        config_root, proj_root, project, resolver, master = setup
        # No overlay files at all
        resolved, trace = resolver.apply_overlays(master, project)
        cpu_a = next(c for c in resolved["cpus"] if c["codigo"] == "CPU-A")
        assert cpu_a["producao_horaria"] == 10.0  # master value unchanged
        assert trace.to_dict().get("CPU-A") == "master"


# ─── F2: set_overlay via FileProjectHandle ────────────────────────────────────

class TestSetOverlay:
    def test_set_overlay_creates_file(self, tmp_path):
        from concilium.infrastructure.storage.file_project_repository import FileProjectHandle
        from concilium.infrastructure.storage.project import ProjectStore

        proj_root = tmp_path / "proj"
        proj_root.mkdir()
        (proj_root / "overrides").mkdir()
        (proj_root / "overrides" / "cpus_override.json").write_text("{}", encoding="utf-8")

        import json as _j
        (proj_root / "meta.json").write_text(_j.dumps({"id": "x", "nome": "X", "contexto_id": "c"}), encoding="utf-8")

        store = ProjectStore(proj_root)
        handle = FileProjectHandle(store)
        handle.set_overlay("cpu", "CPU-TEST", {"producao_horaria": 55.0}, actor="test", motivo="unit test")

        overlay_file = proj_root / "overrides" / "cpus_overlay.json"
        assert overlay_file.exists()
        data = _j.loads(overlay_file.read_text())
        assert "CPU-TEST" in data
        assert data["CPU-TEST"]["producao_horaria"] == 55.0

    def test_set_overlay_writes_audit(self, tmp_path):
        import json as _j

        from concilium.infrastructure.storage.file_project_repository import FileProjectHandle
        from concilium.infrastructure.storage.project import ProjectStore
        proj_root = tmp_path / "proj"
        proj_root.mkdir()
        (proj_root / "overrides").mkdir()
        (proj_root / "overrides" / "cpus_override.json").write_text("{}", encoding="utf-8")
        (proj_root / "meta.json").write_text(_j.dumps({"id": "x", "nome": "X", "contexto_id": "c"}), encoding="utf-8")

        store = ProjectStore(proj_root)
        handle = FileProjectHandle(store)
        handle.set_overlay("cpu", "CPU-X", {"preco": 100}, actor="u1", motivo="Ajuste")

        audit = proj_root / "overrides" / "overlay_audit.jsonl"
        assert audit.exists()
        lines = [ln for ln in audit.read_text().splitlines() if ln.strip()]
        assert len(lines) == 1
        entry = _j.loads(lines[0])
        assert entry["item_id"] == "CPU-X"
        assert entry["actor"] == "u1"
        assert entry["motivo"] == "Ajuste"
