#!/usr/bin/env python3
import json
from pathlib import Path

ROOT = Path("config/catalogos")
CATALOGS = ["mendeslobo", "mendeslobo_backup_ids", "samples"]


def candidates_for_cpu_code(code: str) -> list[str]:
    # Ordered by most likely naming patterns.
    parts = code.split("-")
    cands: list[str] = [f"{code}-PROD-001"]

    if code.startswith("CPU-"):
        cands.append(f"{code[4:]}-PROD-001")

    if len(parts) >= 3:
        # Remove domain prefixes such as CPU-TERRA-, CPU-DREN-, CPU-PAVIM-, CPU-SANEA-, CPU-DIVER-, CPU-OBRAS-
        cands.append(f"{'-'.join(parts[2:])}-PROD-001")

    if len(parts) >= 2:
        cands.append(f"{'-'.join(parts[1:])}-PROD-001")

    # Unique preserving order
    seen = set()
    out = []
    for c in cands:
        if c not in seen:
            seen.add(c)
            out.append(c)
    return out


def load_json(path: Path):
    return json.loads(path.read_text(encoding="utf-8-sig"))


def save_json(path: Path, data):
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def reconcile_catalog(cat: str) -> tuple[int, int, int]:
    base = ROOT / cat
    cpus_dir = base / "cpus"
    prods_dir = base / "produtividades"
    cpus_file = base / "cpus.json"

    prod_ids = {p.stem for p in prods_dir.glob("*.json")} if prods_dir.exists() else set()
    fixed = 0
    unresolved = 0
    total = 0

    def reconcile_cpu(cpu: dict) -> bool:
        nonlocal fixed, unresolved, total
        total += 1
        code = cpu.get("codigo")
        if not code:
            unresolved += 1
            return False
        ref = cpu.get("producao_id_ref")
        if ref in prod_ids:
            return False

        for cand in candidates_for_cpu_code(code):
            if cand in prod_ids:
                cpu["producao_id_ref"] = cand
                fixed += 1
                return True

        unresolved += 1
        return False

    changed = False
    if cpus_file.exists():
        data = load_json(cpus_file)
        for cpu in data.get("cpus", []):
            changed = reconcile_cpu(cpu) or changed
        if changed:
            save_json(cpus_file, data)
    elif cpus_dir.exists():
        for cf in cpus_dir.glob("*.json"):
            cpu = load_json(cf)
            was = reconcile_cpu(cpu)
            if was:
                save_json(cf, cpu)

    return total, fixed, unresolved


def main():
    grand_total = grand_fixed = grand_unresolved = 0
    for cat in CATALOGS:
        if not (ROOT / cat).exists():
            continue
        total, fixed, unresolved = reconcile_catalog(cat)
        grand_total += total
        grand_fixed += fixed
        grand_unresolved += unresolved
        print(f"{cat}: total={total} fixed={fixed} unresolved={unresolved}")

    print(f"TOTAL: total={grand_total} fixed={grand_fixed} unresolved={grand_unresolved}")


if __name__ == "__main__":
    main()
