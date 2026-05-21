from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .input_derivation import normalize_referencia_weeks
from .report_builder import BenchmarkReportBuilder
from .report_printer import BenchmarkReportPrinter
from .runner import BenchmarkRunner
from .spec_loader import ProjectSpec, load_spec_from_dict


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


@dataclass
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

    def run_all(self, *, reset: bool = True) -> list[dict[str, Any]]:
        runner = BenchmarkRunner(
            config_root=self.config_root,
            projects_root=self.projects_root,
            report_builder=BenchmarkReportBuilder(),
            report_printer=BenchmarkReportPrinter(),
        )

        reports: list[dict[str, Any]] = []
        for spec in self.discover_specs():
            print(f"\n{'=' * 60}")
            print(f"  EXECUTANDO BENCHMARK: {spec.slug}")
            print(f"{'=' * 60}")
            reports.append(runner.run(spec, reset=reset))
        return reports

    def build_summary(self, reports: list[dict[str, Any]]) -> list[dict[str, str]]:
        summary: list[dict[str, str]] = []
        for report in reports:
            confronto = report.get("confronto", {})
            deltas = confronto.get("deltas", {})
            status_final = report.get("status_final") or (report.get("quality_gates") or {}).get("decision") or "OK"
            cd_delta = deltas.get("custo_direto", {}).get("percentual")
            ci_delta = deltas.get("custo_indireto", {}).get("percentual")
            ct_delta = deltas.get("custo_total", {}).get("percentual")
            pv_delta = deltas.get("preco_venda", {}).get("percentual")
            skills_log = report.get("skills_log", [])
            has_error = any(skill.get("status") in ("ERRO", "EXCEPTION") for skill in skills_log)
            summary.append(
                {
                    "Projeto": report.get("slug") or report.get("projeto") or "-",
                    "Status": f"{status_final}/AVISO" if has_error else status_final,
                    "Delta Direto %": f"{cd_delta:+.2f}%" if cd_delta is not None else "N/A",
                    "Delta Indireto %": f"{ci_delta:+.2f}%" if ci_delta is not None else "N/A",
                    "Delta Total %": f"{ct_delta:+.2f}%" if ct_delta is not None else "N/A",
                    "Delta Venda %": f"{pv_delta:+.2f}%" if pv_delta is not None else "N/A",
                }
            )
        return summary
