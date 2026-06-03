#!/usr/bin/env python3
"""ADR-066 §F7: Migra cpus_override.json → cpus_overlay.json para projetos existentes.

Execução:
    python3 scripts/migrate_overlays.py [--projetos-dir projetos/]
"""

from __future__ import annotations

import json
import sys
from pathlib import Path


def migrate_project(proj_dir: Path) -> dict:
    """Migra um projeto: cria cpus_overlay.json a partir de cpus_override.json."""
    overrides_dir = proj_dir / "overrides"
    legacy = overrides_dir / "cpus_override.json"
    new_overlay = overrides_dir / "cpus_overlay.json"

    if not legacy.exists():
        return {"project": proj_dir.name, "status": "skip", "reason": "no cpus_override.json"}

    if new_overlay.exists():
        return {"project": proj_dir.name, "status": "skip", "reason": "cpus_overlay.json already exists"}

    try:
        data = json.loads(legacy.read_text(encoding="utf-8"))
        new_overlay.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
        return {"project": proj_dir.name, "status": "migrated", "items": len(data)}
    except Exception as e:
        return {"project": proj_dir.name, "status": "error", "error": str(e)}


def main() -> None:
    import argparse

    parser = argparse.ArgumentParser(description="Migra overlays de projetos (ADR-066)")
    parser.add_argument("--projetos-dir", default="projetos", help="Diretório raiz dos projetos")
    parser.add_argument("--dry-run", action="store_true", help="Apenas lista, não migra")
    args = parser.parse_args()

    projetos_root = Path(args.projetos_dir)
    if not projetos_root.exists():
        print(f"Diretório não encontrado: {projetos_root}", file=sys.stderr)
        sys.exit(1)

    results = []
    for proj_dir in sorted(projetos_root.iterdir()):
        if not proj_dir.is_dir():
            continue
        if args.dry_run:
            legacy = proj_dir / "overrides" / "cpus_override.json"
            results.append({"project": proj_dir.name, "would_migrate": legacy.exists()})
        else:
            results.append(migrate_project(proj_dir))

    migrated = sum(1 for r in results if r.get("status") == "migrated")
    skipped = sum(1 for r in results if r.get("status") == "skip")
    errors = sum(1 for r in results if r.get("status") == "error")

    for r in results:
        status = r.get("status", "?")
        print(f"  [{status:8}]  {r['project']}"
              + (f"  ({r.get('items', 0)} items)" if status == "migrated" else "")
              + (f"  → {r.get('reason', '')}" if status == "skip" else "")
              + (f"  ERROR: {r.get('error', '')}" if status == "error" else ""))

    if not args.dry_run:
        print(f"\n  Migrados: {migrated}  |  Ignorados: {skipped}  |  Erros: {errors}")


if __name__ == "__main__":
    main()
