from __future__ import annotations

import argparse
import json
from pathlib import Path


def _find_report_for_slug(slug_dir: Path) -> Path | None:
    candidates = [
        slug_dir / "outputs" / "benchmark_report.json",
        slug_dir / "artifacts" / "outputs" / "benchmark_report.json",
        slug_dir / "audit" / "benchmark_report.json",
        slug_dir / "artifacts" / "audit" / "benchmark_report.json",
    ]
    for path in candidates:
        if path.exists():
            return path
    return None


def main() -> int:
    parser = argparse.ArgumentParser(description="Export benchmark_report snapshots by slug.")
    parser.add_argument("--source", default="benchmarks/data", help="Source benchmark data directory")
    parser.add_argument("--dest", required=True, help="Destination directory for copied snapshots")
    args = parser.parse_args()

    source = Path(args.source).resolve()
    dest = Path(args.dest).resolve()
    dest.mkdir(parents=True, exist_ok=True)

    exported = 0
    missing: list[str] = []
    for slug_dir in sorted(p for p in source.iterdir() if p.is_dir()):
        report = _find_report_for_slug(slug_dir)
        if report is None:
            missing.append(slug_dir.name)
            continue

        payload = json.loads(report.read_text(encoding="utf-8-sig"))
        out_file = dest / f"{slug_dir.name}.benchmark_report.json"
        out_file.write_text(json.dumps(payload, indent=2, ensure_ascii=False, default=str), encoding="utf-8")
        exported += 1

    summary = {
        "source": str(source),
        "dest": str(dest),
        "exported": exported,
        "missing": missing,
    }
    (dest / "_export_summary.json").write_text(
        json.dumps(summary, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )
    print(json.dumps(summary, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
