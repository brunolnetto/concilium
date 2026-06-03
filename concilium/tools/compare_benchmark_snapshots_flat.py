from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any


VOLATILE_TOP_LEVEL_KEYS = {"versao", "skills_log"}


def _load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _normalize(report: dict[str, Any]) -> dict[str, Any]:
    out = {k: v for k, v in report.items() if k not in VOLATILE_TOP_LEVEL_KEYS}
    return out


def _slug_from_name(path: Path) -> str:
    return path.name.replace(".benchmark_report.json", "")


def _index_reports(folder: Path) -> dict[str, Path]:
    return {_slug_from_name(p): p for p in sorted(folder.glob("*.benchmark_report.json"))}


def main() -> int:
    parser = argparse.ArgumentParser(description="Compare per-project benchmark_report snapshots.")
    parser.add_argument("--legacy", required=True, help="Folder with legacy snapshots")
    parser.add_argument("--v2", required=True, help="Folder with v2 snapshots")
    parser.add_argument("--out", required=True, help="Output json report path")
    args = parser.parse_args()

    legacy_dir = Path(args.legacy).resolve()
    v2_dir = Path(args.v2).resolve()
    out_path = Path(args.out).resolve()
    out_path.parent.mkdir(parents=True, exist_ok=True)

    legacy = _index_reports(legacy_dir)
    v2 = _index_reports(v2_dir)
    all_slugs = sorted(set(legacy) | set(v2))

    missing_legacy = [s for s in all_slugs if s not in legacy]
    missing_v2 = [s for s in all_slugs if s not in v2]

    diffs: list[dict[str, Any]] = []
    for slug in all_slugs:
        lpath = legacy.get(slug)
        vpath = v2.get(slug)
        if lpath is None or vpath is None:
            continue

        lnorm = _normalize(_load_json(lpath))
        vnorm = _normalize(_load_json(vpath))
        if lnorm != vnorm:
            diffs.append(
                {
                    "slug": slug,
                    "legacy_file": str(lpath),
                    "v2_file": str(vpath),
                    "legacy_status_final": lnorm.get("status_final"),
                    "v2_status_final": vnorm.get("status_final"),
                    "legacy_quality_gates": lnorm.get("quality_gates"),
                    "v2_quality_gates": vnorm.get("quality_gates"),
                }
            )

    report = {
        "legacy_dir": str(legacy_dir),
        "v2_dir": str(v2_dir),
        "legacy_count": len(legacy),
        "v2_count": len(v2),
        "missing_in_legacy": missing_legacy,
        "missing_in_v2": missing_v2,
        "diff_count": len(diffs),
        "diffs": diffs,
    }

    out_path.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
    print(json.dumps({k: report[k] for k in ("legacy_count", "v2_count", "diff_count")}, ensure_ascii=False))

    return 0 if report["diff_count"] == 0 and not missing_legacy and not missing_v2 else 1


if __name__ == "__main__":
    raise SystemExit(main())
