from __future__ import annotations

import argparse
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any


SNAPSHOT_REL = Path("artifacts") / "outputs" / "benchmark_report.json"


@dataclass
class ProjectDiff:
    slug: str
    differs: bool
    reason: str | None = None


def _load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def _normalize_report(report: dict[str, Any]) -> dict[str, Any]:
    # version/id fields are expected to differ across independent runs.
    out = dict(report)
    out.pop("versao", None)
    return out


def compare_snapshots(legacy_root: Path, v2_root: Path) -> tuple[list[ProjectDiff], int]:
    diffs: list[ProjectDiff] = []
    compared = 0

    legacy_slugs = sorted(p.name for p in legacy_root.iterdir() if p.is_dir())
    v2_set = {p.name for p in v2_root.iterdir() if p.is_dir()}

    for slug in legacy_slugs:
        legacy_report = legacy_root / slug / SNAPSHOT_REL
        v2_report = v2_root / slug / SNAPSHOT_REL

        if slug not in v2_set:
            diffs.append(ProjectDiff(slug=slug, differs=True, reason="missing_in_v2"))
            continue
        if not legacy_report.exists() or not v2_report.exists():
            diffs.append(ProjectDiff(slug=slug, differs=True, reason="missing_snapshot"))
            continue

        compared += 1
        legacy_data = _normalize_report(_load_json(legacy_report))
        v2_data = _normalize_report(_load_json(v2_report))

        if legacy_data != v2_data:
            diffs.append(ProjectDiff(slug=slug, differs=True, reason="content_diff"))
        else:
            diffs.append(ProjectDiff(slug=slug, differs=False))

    return diffs, compared


def main() -> int:
    parser = argparse.ArgumentParser(description="Compare per-project benchmark_report snapshots between legacy and v2 runs.")
    parser.add_argument("--legacy-root", required=True, help="Root folder containing legacy snapshots by project slug")
    parser.add_argument("--v2-root", required=True, help="Root folder containing v2 snapshots by project slug")
    parser.add_argument("--output", default="artifacts/audit/benchmark_snapshot_parity.json", help="Output json report path")
    args = parser.parse_args()

    legacy_root = Path(args.legacy_root)
    v2_root = Path(args.v2_root)
    output_path = Path(args.output)

    diffs, compared = compare_snapshots(legacy_root, v2_root)
    diff_count = sum(1 for d in diffs if d.differs)

    payload = {
        "legacy_root": str(legacy_root),
        "v2_root": str(v2_root),
        "projects_compared": compared,
        "diff_count": diff_count,
        "rows": [d.__dict__ for d in diffs],
    }

    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")

    print(f"projects_compared={compared}")
    print(f"diff_count={diff_count}")
    print(f"report={output_path}")
    return 0 if diff_count == 0 else 2


if __name__ == "__main__":
    raise SystemExit(main())
