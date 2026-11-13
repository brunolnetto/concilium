"""Report what each CPU of a catalog still lacks for a P23 certificate.

Uses the pipeline's own predicates (V5 calibration, P18 consumption, C^cat);
never edits the catalog. The Markdown report is the data request.

Usage:
    uv run python scripts/catalog/audit_certification_readiness.py --catalog mendeslobo \\
        --out docs/engineering/catalog_readiness/mendeslobo.md
"""

from __future__ import annotations

import argparse
from pathlib import Path

from concilium.application.catalog.certification_readiness import audit_catalog, render_markdown
from concilium.application.runtime import Runtime

REPO_ROOT = Path(__file__).resolve().parents[2]


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--catalog", required=True, help="catalog id under config/catalogos")
    parser.add_argument("--out", type=Path, help="write the Markdown report here (default: stdout)")
    args = parser.parse_args(argv)
    catalog = Runtime(REPO_ROOT / "config").load_catalogo(args.catalog)
    report = render_markdown(args.catalog, audit_catalog(catalog))
    if args.out:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(report, encoding="utf-8")
    else:
        print(report)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
