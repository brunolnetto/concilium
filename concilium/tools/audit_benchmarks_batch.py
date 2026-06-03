from __future__ import annotations

import json
import sys
from datetime import UTC, datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from concilium.application.benchmarks.analysis import (
    build_stage_discrepancy_summary,
    generate_diffs_for_benchmark,
    run_audit,
    validate_pipeline_integrity,
)
from concilium.application.benchmarks.batch import discover_benchmark_slugs


def _write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False, default=str), encoding="utf-8")


def main() -> int:
    bench_root = ROOT / "benchmarks" / "data"
    slugs = discover_benchmark_slugs(bench_root)
    if not slugs:
        print("Nenhum benchmark com referencia encontrado em benchmarks/data.")
        return 1

    rows: list[dict] = []
    for slug in slugs:
        data_dir = bench_root / slug
        audit_dir = data_dir / "audit"
        audit_dir.mkdir(parents=True, exist_ok=True)

        try:
            six = run_audit(slug, root=ROOT)
        except Exception as exc:
            six = {
                "slug": slug,
                "status": "indisponivel",
                "motivo": str(exc),
                "resumo": {"passa": 0, "falha": 0, "na": 0, "total": 0},
            }
        _write_json(audit_dir / "audit_six_questions.json", six)

        try:
            pipe = validate_pipeline_integrity(slug, root=ROOT)
        except Exception as exc:
            pipe = {"slug": slug, "status": "indisponivel", "motivo": str(exc)}
        _write_json(audit_dir / "pipeline_integrity.json", pipe)

        try:
            diffs = generate_diffs_for_benchmark(slug, root=ROOT)
        except Exception as exc:
            diffs = {"slug": slug, "status": "indisponivel", "motivo": str(exc)}
        _write_json(audit_dir / "stage_diffs.json", diffs or {"slug": slug, "status": "indisponivel"})

        resumo = six.get("resumo") or {}
        rows.append(
            {
                "slug": slug,
                "q_passa": int(resumo.get("passa") or 0),
                "q_falha": int(resumo.get("falha") or 0),
                "q_na": int(resumo.get("na") or 0),
            }
        )
        print(f"[OK] {slug}: auditorias atualizadas")

    global_summary = build_stage_discrepancy_summary(root=ROOT)
    _write_json(bench_root / "_batch_audit_summary.json", {
        "meta": {
            "gerado_em": datetime.now(UTC).isoformat(),
            "total_slugs": len(slugs),
        },
        "rows": rows,
        "stage_summary_meta": global_summary.get("meta") or {},
    })

    print(f"[OK] Auditoria em lote concluida para {len(slugs)} slugs.")
    print(f"[OK] Resumo: {bench_root / '_batch_audit_summary.json'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
