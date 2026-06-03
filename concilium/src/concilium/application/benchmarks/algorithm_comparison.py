"""ADR-075: Multi-algorithm scheduling comparison runner.

Development utility — wraps the pipeline and runs it once per scheduling
algorithm to compare their impact on deliverables (makespan, cost, quality).

The pipeline itself is always single-algorithm (selected by
``select_scheduling_algorithm()`` or overridden via inputs).  This module
sits *outside* the pipeline and drives it N times with different algorithm
overrides, then consolidates the results into a side-by-side report.

Typical usage::

    from pathlib import Path
    from concilium.application.benchmarks.algorithm_comparison import (
        AlgorithmComparisonRunner,
    )
    from concilium.application.benchmarks import load_spec_from_json

    spec = load_spec_from_json(Path("benchmarks/data/my_project/spec.json"))
    runner = AlgorithmComparisonRunner(
        config_root=Path("config"),
        projects_root=Path("projects"),
    )
    report = runner.compare(spec)
    print(report.summary_table())
"""

from __future__ import annotations

import importlib
import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


# ─────────────────────────────────────────────────────────────────────────────
# Result types
# ─────────────────────────────────────────────────────────────────────────────


@dataclass
class AlgorithmComparisonEntry:
    """Metrics extracted from a single pipeline run with one algorithm."""

    algorithm: str
    version: str | None = None
    # Scheduling metrics (from Cronograma — skill-04)
    makespan_weeks: int | None = None
    quality_score: float | None = None
    is_feasible: bool = False
    was_relaxed: bool = False
    # Financial metrics (from ConsolidadoFinanceiro — skill-08, if available)
    cost_total: float | None = None
    # Perpetuation metrics (from RelatorioPerpetacao — skill-05, if available)
    mob_cost: float | None = None
    # Error message when the pipeline failed for this algorithm
    error: str | None = None


@dataclass
class AlgorithmComparisonReport:
    """Consolidated results from running the same project with multiple algorithms."""

    project_name: str
    algorithms_tried: list[str]
    entries: list[AlgorithmComparisonEntry] = field(default_factory=list)

    # ── convenience properties ─────────────────────────────────────────────

    @property
    def best_by_quality(self) -> AlgorithmComparisonEntry | None:
        """Return the feasible entry with the highest quality_score."""
        feasible = [
            e for e in self.entries if e.is_feasible and e.quality_score is not None
        ]
        return max(feasible, key=lambda e: e.quality_score, default=None)  # type: ignore[arg-type]

    @property
    def best_by_makespan(self) -> AlgorithmComparisonEntry | None:
        """Return the feasible entry with the shortest makespan."""
        feasible = [
            e for e in self.entries if e.is_feasible and e.makespan_weeks is not None
        ]
        return min(feasible, key=lambda e: e.makespan_weeks, default=None)  # type: ignore[arg-type]

    # ── reporting ──────────────────────────────────────────────────────────

    def summary_table(self) -> str:
        """Return a plain-text comparison table."""
        col_w = 14
        header = (
            f"{'Algorithm':<{col_w}}"
            f"{'Makespan':>{col_w}}"
            f"{'Quality':>{col_w}}"
            f"{'Cost Total':>{col_w}}"
            f"{'Mob Cost':>{col_w}}"
            f"  {'Status'}"
        )
        sep = "-" * len(header)
        rows = [header, sep]

        best = self.best_by_quality
        for e in self.entries:
            if e.error:
                status = f"ERROR: {e.error[:40]}"
                row = (
                    f"{e.algorithm:<{col_w}}"
                    f"{'—':>{col_w}}"
                    f"{'—':>{col_w}}"
                    f"{'—':>{col_w}}"
                    f"{'—':>{col_w}}"
                    f"  {status}"
                )
            else:
                marker = " ◀ best" if e is best else ""
                relaxed = " (relaxed)" if e.was_relaxed else ""
                makespan = f"{e.makespan_weeks}w" if e.makespan_weeks is not None else "—"
                quality = f"{e.quality_score:.4f}" if e.quality_score is not None else "—"
                cost = f"R${e.cost_total:,.0f}" if e.cost_total is not None else "—"
                mob = f"R${e.mob_cost:,.0f}" if e.mob_cost is not None else "—"
                row = (
                    f"{e.algorithm:<{col_w}}"
                    f"{makespan:>{col_w}}"
                    f"{quality:>{col_w}}"
                    f"{cost:>{col_w}}"
                    f"{mob:>{col_w}}"
                    f"  {'OK' + relaxed + marker}"
                )
            rows.append(row)

        rows.append(sep)
        rows.append(f"Project: {self.project_name}")
        return "\n".join(rows)

    def to_dict(self) -> dict[str, Any]:
        """Serialisable dict for JSON export."""
        return {
            "project_name": self.project_name,
            "algorithms_tried": self.algorithms_tried,
            "best_by_quality": self.best_by_quality.algorithm if self.best_by_quality else None,
            "best_by_makespan": self.best_by_makespan.algorithm if self.best_by_makespan else None,
            "entries": [
                {
                    "algorithm": e.algorithm,
                    "version": e.version,
                    "makespan_weeks": e.makespan_weeks,
                    "quality_score": e.quality_score,
                    "is_feasible": e.is_feasible,
                    "was_relaxed": e.was_relaxed,
                    "cost_total": e.cost_total,
                    "mob_cost": e.mob_cost,
                    "error": e.error,
                }
                for e in self.entries
            ],
        }


# ─────────────────────────────────────────────────────────────────────────────
# Runner
# ─────────────────────────────────────────────────────────────────────────────

#: Default algorithms compared when *algorithms* is omitted.
DEFAULT_COMPARISON_ALGORITHMS: list[str] = ["CP-SAT", "LNS", "MINSLK"]


class AlgorithmComparisonRunner:
    """Run the benchmark pipeline once per scheduling algorithm and compare.

    Args:
        config_root:    Path to the Concilium config directory (passed to Runtime).
        projects_root:  Root directory for project stores.
    """

    def __init__(self, config_root: Path, projects_root: Path) -> None:
        self.config_root = config_root
        self.projects_root = projects_root

    # ── public API ─────────────────────────────────────────────────────────

    def compare(
        self,
        spec: Any,
        algorithms: list[str] | None = None,
        *,
        reset: bool = False,
        save_json: Path | None = None,
    ) -> AlgorithmComparisonReport:
        """Run the pipeline with each algorithm and return a comparison report.

        Args:
            spec:        ``ProjectSpec`` loaded via ``load_spec_from_json``.
            algorithms:  Algorithms to compare.  Defaults to
                         ``["CP-SAT", "LNS", "MINSLK"]``.
            reset:       If True, delete any existing project store before
                         running (useful to guarantee a clean slate).
            save_json:   If provided, write the report dict to this path as
                         JSON after all runs complete.
        """
        algos = algorithms if algorithms is not None else DEFAULT_COMPARISON_ALGORITHMS
        report = AlgorithmComparisonReport(
            project_name=spec.nome,
            algorithms_tried=algos,
        )

        from concilium.application.runtime import Runtime

        runtime = Runtime(self.config_root)
        store = self._find_or_create(spec, reset=reset)
        ref_data = self._load_referencia(spec)
        inference_pack = self._derive_inference_pack(ref_data)

        for algo in algos:
            print(f"\n  [CMP] Running algorithm: {algo}")
            version = store.new_version()
            base_inputs = self._prepare_inputs(spec, ref_data, inference_pack)

            # Inject algorithm override for skill-04 (the pipeline stays single-algo).
            cron_inputs = base_inputs.setdefault("04-cronograma", {})
            cron_inputs["algorithm"] = algo

            try:
                runtime.run_pipeline(store, base_inputs)
                canonical = store.load_canonical(version)
                entry = self._extract_entry(algo, version, canonical)
            except Exception as exc:
                entry = AlgorithmComparisonEntry(
                    algorithm=algo,
                    version=version,
                    error=f"{type(exc).__name__}: {exc}",
                )

            report.entries.append(entry)
            _print_entry(entry)

        print("\n" + report.summary_table())

        if save_json is not None:
            save_json.parent.mkdir(parents=True, exist_ok=True)
            save_json.write_text(
                json.dumps(report.to_dict(), indent=2, default=str, ensure_ascii=False),
                encoding="utf-8",
            )
            print(f"\n  [SAVE] Comparison report → {save_json}")

        return report

    # ── internals ──────────────────────────────────────────────────────────

    def _find_or_create(self, spec: Any, *, reset: bool) -> Any:
        import shutil

        from concilium.infrastructure.storage.project import ProjectStore

        if self.projects_root.exists():
            for project_dir in self.projects_root.iterdir():
                meta_path = project_dir / "meta.json"
                if not project_dir.is_dir() or not meta_path.exists():
                    continue
                meta = json.loads(meta_path.read_text(encoding="utf-8"))
                if meta.get("nome") == spec.nome:
                    if reset:
                        print(f"  [DEL] Removing existing project: {project_dir.name}")
                        shutil.rmtree(project_dir, ignore_errors=True)
                        break
                    print(f"  [OK]  Found existing project: {project_dir.name}")
                    return ProjectStore(project_dir)

        print(f"  [NEW] Creating '{spec.nome}'...")
        self.projects_root.mkdir(parents=True, exist_ok=True)
        return ProjectStore.init(self.projects_root, spec.nome, spec.contexto_id)

    def _load_referencia(self, spec: Any) -> dict[str, Any] | None:
        if spec.referencia_path and spec.referencia_path.exists():
            return json.loads(spec.referencia_path.read_text(encoding="utf-8"))
        return None

    def _derive_inference_pack(self, ref_data: dict[str, Any] | None) -> Any:
        mod = importlib.import_module("concilium.application.benchmarks.inference")
        svc_cls = getattr(mod, "BenchmarkInferenceService")
        return svc_cls.derive(ref_data)

    def _prepare_inputs(
        self, spec: Any, ref: dict[str, Any] | None, inference_pack: Any
    ) -> dict[str, dict]:
        """Mirror BenchmarkRunner._prepare_inputs — builds skill_inputs from spec."""
        mod = importlib.import_module("concilium.application.benchmarks.inference")
        svc_cls = getattr(mod, "BenchmarkInferenceService")

        skill_inputs: dict[str, dict] = {}
        if spec.inputs_escopo:
            if "contexto_id" not in spec.inputs_escopo:
                spec.inputs_escopo["contexto_id"] = spec.contexto_id
            skill_inputs["01-escopo-e-eap"] = spec.inputs_escopo
            skill_inputs["00-escopo"] = spec.inputs_escopo
        if getattr(spec, "inputs_01A", None):
            skill_inputs["03-catalogo-de-recursos"] = spec.inputs_01A
        if getattr(spec, "inputs_cronograma", None):
            skill_inputs["04-cronograma"] = dict(spec.inputs_cronograma)
        if getattr(spec, "inputs_indiretos", None):
            skill_inputs["07-custos-indiretos"] = spec.inputs_indiretos
        skill_inputs.update(getattr(spec, "extra_inputs", {}))
        skill_inputs = svc_cls.apply_to_skill_inputs(skill_inputs, inference_pack)
        return skill_inputs

    @staticmethod
    def _extract_entry(
        algo: str, version: str, canonical: Any | None
    ) -> AlgorithmComparisonEntry:
        entry = AlgorithmComparisonEntry(algorithm=algo, version=version)

        if canonical is None:
            entry.error = "canonical not found"
            return entry

        # ── Scheduling metrics (skill-04) — canonical.cronograma ──────────
        cron = getattr(canonical, "cronograma", None)
        if cron is not None:
            entry.makespan_weeks = getattr(cron, "makespan_weeks", None)
            entry.quality_score = getattr(cron, "quality_score", None)
            entry.is_feasible = bool(getattr(cron, "is_feasible", False))
            entry.was_relaxed = bool(getattr(cron, "was_relaxed", False))

        # ── Financial metrics (skill-08) — canonical.resultado.custo.total ─
        resultado = getattr(canonical, "resultado", None)
        if resultado is not None:
            custo = getattr(resultado, "custo", None)
            if custo is not None:
                total = getattr(custo, "total", None)
                entry.cost_total = float(total) if total is not None else None

        # ── Perpetuation/mob metrics (skill-05) — contratos_recurso ────────
        # custo_mob_desmob_contrato = n_cadeias × (mob + demob) × pool_size
        contratos = getattr(canonical, "contratos_recurso", None) or []
        if contratos:
            mob_total = sum(
                getattr(c, "custo_mob_desmob_contrato", 0.0) for c in contratos
            )
            if mob_total > 0:
                entry.mob_cost = mob_total

        return entry


# ─────────────────────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────────────────────


def _print_entry(entry: AlgorithmComparisonEntry) -> None:
    if entry.error:
        print(f"  [FAIL] {entry.algorithm}: {entry.error}")
    else:
        parts = [f"makespan={entry.makespan_weeks}w", f"quality={entry.quality_score:.4f}"]
        if entry.cost_total is not None:
            parts.append(f"cost=R${entry.cost_total:,.0f}")
        if entry.mob_cost is not None:
            parts.append(f"mob=R${entry.mob_cost:,.0f}")
        if entry.was_relaxed:
            parts.append("relaxed")
        print(f"  [OK]   {entry.algorithm}: {', '.join(parts)}")
