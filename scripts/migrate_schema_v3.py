#!/usr/bin/env python3
"""Migrate referencia.json from v2 to v3 minimalista schema.

v3 optimizations:
1. Remove spec.eap.item.{ordem, descricao, unidade} - infer from catalog
2. Remove spec.eap.item.producao_diaria - compute from cronograma
3. Remove spec.rcpsp_spec - infer mobilization/demobilization from timeline
4. Clarify meta.localizacao structure
5. Clean up redundant bdi_lucro_impostos placement
"""

import json
from pathlib import Path
from typing import Any, Dict


def migrate_to_v3(ref: Dict[str, Any], slug: str) -> Dict[str, Any]:
    """Migrate a referencia.json from v2 to v3 schema."""

    # ─────────────────────────────────────────────────────────────────────────
    # 1. Optimize meta.localizacao
    # ─────────────────────────────────────────────────────────────────────────
    meta = ref.get("meta", {})
    localizacao = meta.get("localizacao")

    if isinstance(localizacao, str) and localizacao:
        # Keep structured for now, upgrade to (lat,lng) or endereco in future
        meta["localizacao"] = {
            "tipo": "endereco_descritivo",
            "valor": localizacao
        }

    # ─────────────────────────────────────────────────────────────────────────
    # 2. Optimize spec.eap: Remove redundant fields
    # ─────────────────────────────────────────────────────────────────────────
    spec = ref.get("spec", {})
    eap = spec.get("eap", [])

    # Remove ordem (redundant with predecessores DAG)
    # Remove descricao, unidade (inferrable from catalog cpu_id)
    # Remove producao_diaria (computed from cronograma)
    # Keep: item_id, cpu_id, quantitativo, predecessores

    for item in eap:
        # Document what's being removed
        removed_fields = []

        if "ordem" in item:
            del item["ordem"]
            removed_fields.append("ordem")

        if "descricao" in item:
            del item["descricao"]
            removed_fields.append("descricao")

        if "unidade" in item:
            del item["unidade"]
            removed_fields.append("unidade")

        if "producao_diaria" in item:
            del item["producao_diaria"]
            removed_fields.append("producao_diaria")

        # Keep only primitives: item_id, cpu_id, quantitativo, predecessores
        # Also keep cpu_meta if present (optional enrichment from catalog)

    # ─────────────────────────────────────────────────────────────────────────
    # 3. Optimize cronograma: Remove producao_diaria (compute on-demand)
    # ─────────────────────────────────────────────────────────────────────────
    cronograma = spec.get("cronograma", [])

    for item in cronograma:
        if "producao_diaria" in item:
            del item["producao_diaria"]

    # ─────────────────────────────────────────────────────────────────────────
    # 4. Remove spec.rcpsp_spec (will infer from timeline + indiretos.MOB)
    # ─────────────────────────────────────────────────────────────────────────
    if "rcpsp_spec" in spec:
        del spec["rcpsp_spec"]

    # ─────────────────────────────────────────────────────────────────────────
    # 5. Clarify bdi_lucro_impostos placement
    # ─────────────────────────────────────────────────────────────────────────
    bdi = spec.get("bdi", {})

    # Move bdi_lucro_impostos from bdi to resultado if present
    bdi_lucro = None
    if "bdi_lucro_impostos" in bdi:
        bdi_lucro = bdi.pop("bdi_lucro_impostos")

    # Also check in resultado
    resultado = ref.get("resultado", {})
    if bdi_lucro and "bdi_lucro_impostos" not in resultado:
        resultado["bdi_lucro_impostos"] = bdi_lucro

    # ─────────────────────────────────────────────────────────────────────────
    # 6. Remove spec.cenarios (not used, defer for future)
    # ─────────────────────────────────────────────────────────────────────────
    if "cenarios" in spec:
        del spec["cenarios"]

    # ─────────────────────────────────────────────────────────────────────────
    # 7. Add schema version marker
    # ─────────────────────────────────────────────────────────────────────────
    ref["_schema_version"] = "v3"
    ref["_schema_upgraded_from"] = "v2"

    return ref


def main():
    project_root = Path(__file__).resolve().parent.parent
    benchmarks_root = project_root / "benchmarks" / "data"

    print("\n" + "="*80)
    print("MIGRATING BENCHMARKS TO SCHEMA V3")
    print("="*80)

    # Start with AGIS as proof-of-concept
    slugs = ["AGIS"]

    for slug in slugs:
        ref_path = benchmarks_root / slug / "referencia.json"
        if not ref_path.exists():
            print(f"  ? {slug:25} referencia.json not found")
            continue

        ref = json.load(open(ref_path, encoding="utf-8"))

        # Get original size
        original_size = len(json.dumps(ref, ensure_ascii=False))

        # Migrate to v3
        ref_v3 = migrate_to_v3(ref, slug)

        # Get new size
        new_size = len(json.dumps(ref_v3, ensure_ascii=False))
        reduction = 100 * (original_size - new_size) / original_size

        # Save
        ref_path.write_text(json.dumps(ref_v3, indent=2, ensure_ascii=False), encoding="utf-8")

        print(f"  ✓ {slug:25} migrated to v3")
        print(f"    Size: {original_size:6d} → {new_size:6d} bytes ({reduction:.1f}% reduction)")

    print("\n" + "="*80)
    print("Migration complete. Validate with: run_benchmarks.py")
    print("="*80 + "\n")


if __name__ == "__main__":
    main()
