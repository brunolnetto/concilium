from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from concilium.application.benchmarks import BenchmarkFacade
from concilium.application.benchmarks.analysis import (
    build_stage_discrepancy_summary,
    generate_diffs_for_benchmark,
    run_audit,
    validate_pipeline_integrity,
)


def main() -> int:
    slug = "AGIS"
    facade = BenchmarkFacade.from_root(ROOT)
    report = facade.run_single(slug, reset=True)

    bench_dir = ROOT / "benchmarks" / "data" / slug
    audit_dir = bench_dir / "audit"
    audit_dir.mkdir(parents=True, exist_ok=True)

    (audit_dir / "benchmark_report.json").write_text(
        json.dumps(report, indent=2, ensure_ascii=False, default=str),
        encoding="utf-8",
    )

    six = run_audit(slug, root=ROOT)
    (audit_dir / "audit_six_questions.json").write_text(
        json.dumps(six, indent=2, ensure_ascii=False, default=str),
        encoding="utf-8",
    )

    diffs = generate_diffs_for_benchmark(slug, root=ROOT)
    (audit_dir / "stage_diffs.json").write_text(
        json.dumps(diffs or {"slug": slug, "status": "indisponivel"}, indent=2, ensure_ascii=False, default=str),
        encoding="utf-8",
    )

    pipe = validate_pipeline_integrity(slug, root=ROOT)
    (audit_dir / "pipeline_integrity.json").write_text(
        json.dumps(pipe, indent=2, ensure_ascii=False, default=str),
        encoding="utf-8",
    )

    summary_all = build_stage_discrepancy_summary(root=ROOT)
    agis_row = next((row for row in summary_all.get("benchmarks", []) if str(row.get("slug", "")).upper() == slug), None)
    (audit_dir / "stage_discrepancy_summary_agis.json").write_text(
        json.dumps({"meta": summary_all.get("meta", {}), "agis": agis_row}, indent=2, ensure_ascii=False, default=str),
        encoding="utf-8",
    )

    print("AGIS benchmark executado e artefatos gerados em:", audit_dir)
    print("status_final:", report.get("status_final"))
    print("quality_gates:", (report.get("quality_gates") or {}).get("decision"))
    print("arquivos:", sorted([p.name for p in audit_dir.glob("*.json")]))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
