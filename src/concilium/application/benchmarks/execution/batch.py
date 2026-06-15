from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from ..input_derivation import normalize_referencia_weeks
from ..report.report_builder import BenchmarkReportBuilder
from ..report.report_printer import BenchmarkReportPrinter
from .runner import BenchmarkRunner
from ..spec.spec_loader import ProjectSpec, load_spec_from_dict


def _reference_candidates(benchmark_dir: Path) -> tuple[Path, ...]:
    return (
        benchmark_dir / "referencia.json",
        benchmark_dir / "artifacts" / "inputs" / "referencia.json",
        benchmark_dir / "artifacts" / "referencia.json",
    )


def find_benchmark_reference(benchmarks_root: Path, slug: str) -> Path | None:
    bench_dir = benchmarks_root / slug.upper()
    for candidate in _reference_candidates(bench_dir):
        if candidate.exists():
            return candidate
    return None


def discover_benchmark_slugs(benchmarks_root: Path) -> list[str]:
    if not benchmarks_root.exists() or not benchmarks_root.is_dir():
        return []

    slugs: list[str] = []
    for benchmark_dir in sorted(benchmarks_root.iterdir()):
        if not benchmark_dir.is_dir():
            continue
        if any(candidate.exists() for candidate in _reference_candidates(benchmark_dir)):
            slugs.append(benchmark_dir.name.upper())
    return slugs


def _fmt_delta(v) -> str:
    return f"{v:+.2f}%" if v is not None else "N/A"


def _resolve_status(report: dict) -> str:
    s = report.get("status_final")
    if s:
        return s
    qg = report.get("quality_gates")
    return (qg or {}).get("decision") or "OK"


def _build_summary_row(report: dict) -> dict:
    confronto = report.get("confronto", {})
    deltas = confronto.get("deltas", {})
    status_final = _resolve_status(report)
    skills_log = report.get("skills_log", [])
    has_error = False
    for skill in skills_log:
        if skill.get("status") in ("ERRO", "EXCEPTION"):
            has_error = True
            break
    status_str = f"{status_final}/AVISO" if has_error else status_final
    slug = report.get("slug") or report.get("projeto") or "-"
    return {
        "Projeto": slug,
        "Status": status_str,
        "Delta Direto %": _fmt_delta(deltas.get("custo_direto", {}).get("percentual")),
        "Delta Indireto %": _fmt_delta(deltas.get("custo_indireto", {}).get("percentual")),
        "Delta Total %": _fmt_delta(deltas.get("custo_total", {}).get("percentual")),
        "Delta Venda %": _fmt_delta(deltas.get("preco_venda", {}).get("percentual")),
    }


@dataclass(slots=True)
class BenchmarkBatchRunner:
    benchmarks_root: Path
    config_root: Path
    projects_root: Path

    def discover_specs(self) -> list[ProjectSpec]:
        specs: list[ProjectSpec] = []
        if not self.benchmarks_root.exists() or not self.benchmarks_root.is_dir():
            return specs

        for benchmark_dir in sorted(self.benchmarks_root.iterdir()):
            if not benchmark_dir.is_dir():
                continue

            ref_path = None
            for candidate in _reference_candidates(benchmark_dir):
                if candidate.exists():
                    ref_path = candidate
                    break

            if ref_path is None:
                continue

            ref_data = json.loads(ref_path.read_text(encoding="utf-8"))
            normalize_referencia_weeks(ref_data)  # em memoria, sem I/O
            specs.append(load_spec_from_dict(ref_data, ref_path))
        return specs

    def run_all(self, *, reset: bool = True, quiet: bool = False) -> list[dict[str, Any]]:
        runner = BenchmarkRunner(
            config_root=self.config_root,
            projects_root=self.projects_root,
            report_builder=BenchmarkReportBuilder(),
            report_printer=BenchmarkReportPrinter(),
        )

        specs = self.discover_specs()
        reports: list[dict[str, Any]] = []

        for idx, spec in enumerate(specs, 1):
            if not quiet:
                print(f"\n{'=' * 60}")
                print(f"  EXECUTANDO BENCHMARK: {spec.slug}")
                print(f"{'=' * 60}")
            else:
                print(f"[{idx}/{len(specs)}] {spec.slug}...", end=" ", flush=True)

            report = runner.run(spec, reset=reset)
            reports.append(report)

            if quiet:
                status = _resolve_status(report)
                print(f"{status}")

        return reports

    def build_summary(self, reports: list[dict[str, Any]]) -> list[dict[str, str]]:
        summary: list[dict[str, str]] = []
        for report in reports:
            summary.append(_build_summary_row(report))
        return summary
