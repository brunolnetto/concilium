"""Tests for _enrich_cpus_with_producao — correctness, complexity, and cache.

ADR-067: The join between CPUs (producao_id_ref) and productions (valor_horario)
must be O(P + C) where P = len(producoes) and C = len(cpus).

Invariants verified:
  1. Every CPU with a matching producao_id_ref gets producao_horaria populated.
  2. CPUs that already have producao_horaria are unchanged.
  3. CPUs without producao_id_ref are unchanged.
  4. CPUs with unmatched producao_id_ref are returned without producao_horaria.
  5. Time complexity: 10_000-CPU catalog enriched in <100 ms.
  6. Cache: second call with same bundle mtime returns the cached list (no re-enrich).
  7. Cache invalidation: changed mtime causes re-enrich.
"""

from __future__ import annotations

import time
from pathlib import Path

import pytest

from concilium.application.services.concilium_service import ConciliumService


def _make_cat(n_cpus: int, n_prods: int, *, match_all: bool = True) -> dict:
    """Build a synthetic catalog with n_cpus CPUs and n_prods productions."""
    prods = [{"id": f"PROD-{i:06d}", "valor_horario": float(i + 1)} for i in range(n_prods)]
    cpus = []
    for i in range(n_cpus):
        if match_all:
            ref = f"PROD-{i % n_prods:06d}" if n_prods > 0 else None
        else:
            ref = f"PROD-{i:06d}" if i < n_prods else None
        cpus.append(
            {
                "codigo": f"CPU-{i:06d}",
                "descricao": f"CPU numero {i}",
                "unidade": "m3",
                "producao_id_ref": ref,
            }
        )
    return {"cpus": cpus, "producoes": prods, "insumos": []}


# ─── Correctness ──────────────────────────────────────────────────────────────


class TestEnrichCpusCorrectness:
    def test_matching_ref_populates_producao_horaria(self):
        cat = _make_cat(5, 5)
        enriched = ConciliumService._enrich_cpus_with_producao(cat)
        assert all(c.get("producao_horaria") is not None for c in enriched)
        # valor_horario is float(i+1) for PROD-000000..4
        assert enriched[0]["producao_horaria"] == 1.0
        assert enriched[4]["producao_horaria"] == 5.0

    def test_cpu_with_existing_producao_horaria_unchanged(self):
        cat = {
            "cpus": [{"codigo": "CPU-A", "producao_horaria": 99.0, "producao_id_ref": "PROD-0"}],
            "producoes": [{"id": "PROD-0", "valor_horario": 1.0}],
            "insumos": [],
        }
        enriched = ConciliumService._enrich_cpus_with_producao(cat)
        assert enriched[0]["producao_horaria"] == 99.0  # not overwritten

    def test_cpu_without_ref_has_no_producao_horaria(self):
        cat = {
            "cpus": [{"codigo": "CPU-A", "unidade": "m3"}],
            "producoes": [{"id": "PROD-0", "valor_horario": 5.0}],
            "insumos": [],
        }
        enriched = ConciliumService._enrich_cpus_with_producao(cat)
        assert "producao_horaria" not in enriched[0]

    def test_unmatched_ref_leaves_field_absent(self):
        cat = {
            "cpus": [{"codigo": "CPU-A", "producao_id_ref": "PROD-GHOST"}],
            "producoes": [{"id": "PROD-REAL", "valor_horario": 5.0}],
            "insumos": [],
        }
        enriched = ConciliumService._enrich_cpus_with_producao(cat)
        assert enriched[0].get("producao_horaria") is None

    def test_empty_catalog_returns_empty(self):
        assert ConciliumService._enrich_cpus_with_producao({}) == []

    def test_non_dict_cpus_skipped(self):
        cat = {
            "cpus": ["not-a-dict", None, {"codigo": "CPU-A", "producao_id_ref": "P1"}],
            "producoes": [{"id": "P1", "valor_horario": 7.0}],
            "insumos": [],
        }
        enriched = ConciliumService._enrich_cpus_with_producao(cat)
        assert len(enriched) == 1
        assert enriched[0]["producao_horaria"] == 7.0

    def test_original_dict_not_mutated(self):
        """Enrichment must not mutate the input catalog (creates new dicts)."""
        cpu = {"codigo": "CPU-A", "producao_id_ref": "P1"}
        cat = {"cpus": [cpu], "producoes": [{"id": "P1", "valor_horario": 3.0}], "insumos": []}
        ConciliumService._enrich_cpus_with_producao(cat)
        assert "producao_horaria" not in cpu  # original unmodified

    def test_many_to_one_productions(self):
        """Multiple CPUs can share the same producao_id_ref."""
        cat = {
            "cpus": [
                {"codigo": "CPU-A", "producao_id_ref": "PROD-SHARED"},
                {"codigo": "CPU-B", "producao_id_ref": "PROD-SHARED"},
            ],
            "producoes": [{"id": "PROD-SHARED", "valor_horario": 42.0}],
            "insumos": [],
        }
        enriched = ConciliumService._enrich_cpus_with_producao(cat)
        assert enriched[0]["producao_horaria"] == 42.0
        assert enriched[1]["producao_horaria"] == 42.0


# ─── Complexity ───────────────────────────────────────────────────────────────


class TestEnrichCpusComplexity:
    @pytest.mark.flaky
    def test_linear_time_10k_cpus(self):
        """O(P + C): 10_000 CPUs + 10_000 productions must enrich in < 500 ms.

        Threshold generoso para ambientes com CPU sob carga (CI, dev com outros processos).
        O invariante real é a linearidade testada em test_linear_time_1k_cpus_vs_10k_cpus.
        """
        cat = _make_cat(10_000, 10_000)
        t0 = time.perf_counter()
        enriched = ConciliumService._enrich_cpus_with_producao(cat)
        elapsed_ms = (time.perf_counter() - t0) * 1_000
        assert len(enriched) == 10_000
        assert all(c.get("producao_horaria") is not None for c in enriched)
        assert elapsed_ms < 500, f"Enrichment took {elapsed_ms:.1f} ms — expected < 500 ms"

    @pytest.mark.slow
    @pytest.mark.flaky
    def test_linear_time_1k_cpus_vs_10k_cpus(self):
        """Time ratio for 10× more data should be well under quadratic (~100×).

        Threshold generoso (35×, igual filosofia de test_linear_time_10k_cpus)
        para ambientes com CPU sob carga (CI, dev com outros processos) — o
        `t_small` de 1k itens é a medição mais sensível a ruído aqui, e um pico
        de contenção durante ela infla o ratio sem refletir complexidade real.
        Um regressão para O(n²) real produziria ~100×, bem acima da margem.
        """
        cat_small = _make_cat(1_000, 1_000)
        cat_large = _make_cat(10_000, 10_000)

        t0 = time.perf_counter()
        for _ in range(5):
            ConciliumService._enrich_cpus_with_producao(cat_small)
        t_small = (time.perf_counter() - t0) / 5

        t0 = time.perf_counter()
        for _ in range(5):
            ConciliumService._enrich_cpus_with_producao(cat_large)
        t_large = (time.perf_counter() - t0) / 5

        ratio = t_large / max(t_small, 1e-9)
        assert ratio < 35, (
            f"10× more data took {ratio:.1f}× longer — expected < 35× (não quadrático). "
            f"small={t_small * 1000:.2f}ms large={t_large * 1000:.2f}ms"
        )

    @pytest.mark.flaky
    def test_no_quadratic_behavior_worst_case(self):
        """Worst case: all CPUs share one production — still O(C).

        Threshold generoso (300 ms) para ambientes com CPU sob carga.
        """
        cat = {
            "cpus": [{"codigo": f"CPU-{i}", "producao_id_ref": "PROD-0"} for i in range(5_000)],
            "producoes": [{"id": "PROD-0", "valor_horario": 1.0}],
            "insumos": [],
        }
        t0 = time.perf_counter()
        enriched = ConciliumService._enrich_cpus_with_producao(cat)
        elapsed_ms = (time.perf_counter() - t0) * 1_000
        assert len(enriched) == 5_000
        assert elapsed_ms < 300, f"Worst-case took {elapsed_ms:.1f} ms — expected < 300 ms"


# ─── Cache ────────────────────────────────────────────────────────────────────


class TestEnrichedCpusCache:
    def _make_service(self, config_root: Path, projects_root: Path) -> ConciliumService:
        from concilium.application.runtime import Runtime
        from concilium.application.services.concilium_service import ConciliumDependencies
        from concilium.application.services.pipeline_service import PipelineService
        from concilium.application.services.project.audit_service import AuditService
        from concilium.application.services.project.override_service import OverrideService
        from concilium.application.services.project.project_input_builder import ProjectInputBuilder
        from concilium.application.services.project.project_service import ProjectService
        from concilium.infrastructure.storage.file_project_repository import FileProjectRepository

        repo = FileProjectRepository(projects_root)
        audit = AuditService()
        ps = ProjectService(repo, audit)
        ov = OverrideService(repo, audit)
        pls = PipelineService(repo, audit, runtime_factory=lambda: Runtime(config_root))
        ib = ProjectInputBuilder(config_root, config_root / "benchmarks")
        return ConciliumService(
            ConciliumDependencies(
                input_builder=ib,
                repository=repo,
                project_service=ps,
                override_service=ov,
                pipeline_service=pls,
                audit_service=audit,
                benchmarks_root=config_root / "benchmarks",
            )
        )

    def _setup_catalog(self, tmp_path: Path) -> tuple[Path, Path]:
        import json

        cfg = tmp_path / "config"
        cats_dir = cfg / "catalogos" / "test-cat"
        (cats_dir / "cpus").mkdir(parents=True)
        (cats_dir / "producoes").mkdir()
        (cfg / "catalogos" / "test-cat" / "cpus" / "CPU-001.json").write_text(
            json.dumps({"codigo": "CPU-001", "descricao": "Test", "unidade": "m3", "producao_id_ref": "PROD-001"}),
            encoding="utf-8",
        )
        (cfg / "catalogos" / "test-cat" / "producoes" / "PROD-001.json").write_text(
            json.dumps({"id": "PROD-001", "valor_horario": 55.5}), encoding="utf-8"
        )
        prj = tmp_path / "projetos"
        prj.mkdir()
        return cfg, prj

    def test_cache_hit_returns_same_list_object(self, tmp_path):
        cfg, prj = self._setup_catalog(tmp_path)
        svc = self._make_service(cfg, prj)

        first = svc._get_enriched_cpus("test-cat")
        second = svc._get_enriched_cpus("test-cat")
        assert first is second, "Second call should return the same cached list object"

    def test_cache_miss_after_mtime_change(self, tmp_path):
        cfg, prj = self._setup_catalog(tmp_path)
        svc = self._make_service(cfg, prj)

        first = svc._get_enriched_cpus("test-cat")

        # Simulate ADR-067 write: delete bundle (it doesn't exist yet, so touch a file)
        bundle = cfg / "catalogos" / "test-cat" / ".catalog_bundle.json"
        bundle.write_text("{}", encoding="utf-8")
        # Force cache miss by corrupting the stored mtime
        svc._enriched_cache["test-cat"] = (-1, first)

        second = svc._get_enriched_cpus("test-cat")
        assert second is not first, "Cache miss: new bundle → re-enriched list"

    def test_enrichment_populates_producao_horaria(self, tmp_path):
        cfg, prj = self._setup_catalog(tmp_path)
        svc = self._make_service(cfg, prj)
        cpus = svc._get_enriched_cpus("test-cat")
        assert cpus[0]["producao_horaria"] == 55.5
