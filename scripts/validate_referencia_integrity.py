#!/usr/bin/env python3
"""Validate referencia.json files for structural integrity and completeness."""

import json
from pathlib import Path
from typing import Any, Dict, List, Tuple

def load_catalog(project_root: Path) -> Dict[str, Any]:
    """Load the catalog for CPU validation."""
    cat_path = project_root / "config/catalogos/mendeslobo/.catalog_bundle.json"
    if cat_path.exists():
        return json.loads(cat_path.read_text())
    return {}

def validate_meta(meta: Dict) -> List[str]:
    """Validate meta section."""
    errors = []
    required_fields = ['projeto', 'data_inicio', 'data_termino', 'regime_trabalho']

    for field in required_fields:
        if field not in meta or not meta[field]:
            errors.append(f"meta.{field}: missing or empty")

    return errors

def validate_eap_items(eap: List[Dict], catalog: Dict) -> List[str]:
    """Validate EAP items."""
    errors = []
    cpus = {cpu["codigo"]: cpu for cpu in catalog.get("cpus", [])}
    seen_ids = set()

    for i, item in enumerate(eap):
        prefix = f"eap[{i}]"

        # Check required fields
        if "item_id" not in item:
            errors.append(f"{prefix}: missing item_id")
            continue

        item_id = item["item_id"]
        if item_id in seen_ids:
            errors.append(f"{prefix}: duplicate item_id '{item_id}'")
        seen_ids.add(item_id)

        # Validate item_id format
        if not isinstance(item_id, str) or not item_id.strip():
            errors.append(f"{prefix}: item_id must be non-empty string")

        # Check CPU exists in catalog
        if "cpu_id" not in item:
            errors.append(f"{prefix} ({item_id}): missing cpu_id")
        elif item["cpu_id"] not in cpus:
            errors.append(f"{prefix} ({item_id}): cpu_id '{item['cpu_id']}' not in catalog")

        # Check required fields
        required = ["descricao", "unidade", "quantitativo"]
        for field in required:
            if field not in item:
                errors.append(f"{prefix} ({item_id}): missing {field}")

        # Validate quantitativo > 0
        if "quantitativo" in item:
            try:
                q = float(item["quantitativo"])
                if q <= 0:
                    errors.append(f"{prefix} ({item_id}): quantitativo must be > 0, got {q}")
            except (ValueError, TypeError):
                errors.append(f"{prefix} ({item_id}): quantitativo must be a number")

        # Validate predecessores structure
        if "predecessores" not in item:
            errors.append(f"{prefix} ({item_id}): missing predecessores (should be [])")
        elif not isinstance(item["predecessores"], list):
            errors.append(f"{prefix} ({item_id}): predecessores must be a list")
        else:
            for j, pred in enumerate(item["predecessores"]):
                if not isinstance(pred, dict):
                    errors.append(f"{prefix} ({item_id}).predecessores[{j}]: must be dict")
                    continue

                pred_prefix = f"{prefix} ({item_id}).predecessores[{j}]"
                required_pred = ["item_id", "tipo", "lag", "completion_threshold_pct"]
                for field in required_pred:
                    if field not in pred:
                        errors.append(f"{pred_prefix}: missing {field}")

    return errors

def validate_bdi(bdi: Dict) -> List[str]:
    """Validate BDI section (should match AGIS structure)."""
    errors = []
    required_categories = ["mao_obra", "material", "servicos", "diesel", "indireto"]
    required_components = ["ac", "df", "r", "cr", "ir"]

    for category in required_categories:
        if category not in bdi:
            errors.append(f"bdi.{category}: missing")
        elif not isinstance(bdi[category], dict):
            errors.append(f"bdi.{category}: must be dict, got {type(bdi[category]).__name__}")
        else:
            for component in required_components:
                if component not in bdi[category]:
                    errors.append(f"bdi.{category}.{component}: missing")

    return errors

def validate_indiretos(indiretos: List[Dict]) -> List[str]:
    """Validate indiretos section."""
    errors = []

    if not isinstance(indiretos, list):
        return [f"indiretos: must be list, got {type(indiretos).__name__}"]

    valid_tipos = {"ADM", "TOP", "LAB", "QSMS", "MOB"}
    seen_tipos = set()

    for i, item in enumerate(indiretos):
        if not isinstance(item, dict):
            errors.append(f"indiretos[{i}]: must be dict")
            continue

        tipo = item.get("tipo")
        if tipo in valid_tipos:
            if tipo in seen_tipos:
                errors.append(f"indiretos[{i}]: duplicate tipo '{tipo}'")
            seen_tipos.add(tipo)

    return errors

def validate_resultado(resultado: Dict) -> List[str]:
    """Validate resultado.benchmark_confronto_referencia section."""
    errors = []

    if "benchmark_confronto_referencia" not in resultado:
        return ["resultado.benchmark_confronto_referencia: missing"]

    bcr = resultado["benchmark_confronto_referencia"]
    required_fields = ["custo_direto", "custo_indireto", "custo_total", "preco_venda"]

    for field in required_fields:
        if field not in bcr:
            errors.append(f"resultado.benchmark_confronto_referencia.{field}: missing")

    return errors

def validate_referencia(slug: str, ref_path: Path, catalog: Dict) -> Dict[str, Any]:
    """Validate a complete referencia.json file."""
    result = {
        "slug": slug,
        "path": str(ref_path),
        "valid": True,
        "errors": [],
        "warnings": []
    }

    if not ref_path.exists():
        result["valid"] = False
        result["errors"].append("File does not exist")
        return result

    try:
        ref = json.loads(ref_path.read_text())
    except json.JSONDecodeError as e:
        result["valid"] = False
        result["errors"].append(f"Invalid JSON: {e}")
        return result

    # Validate main structure
    if "meta" not in ref:
        result["errors"].append("Missing 'meta' section")
    else:
        errors = validate_meta(ref["meta"])
        result["errors"].extend(errors)

    if "spec" not in ref:
        result["errors"].append("Missing 'spec' section")
        result["valid"] = False
        return result

    spec = ref["spec"]

    # Validate EAP
    if "eap" not in spec:
        result["errors"].append("spec.eap: missing")
    else:
        errors = validate_eap_items(spec["eap"], catalog)
        result["errors"].extend(errors)

    # Validate BDI
    if "bdi" not in spec:
        result["errors"].append("spec.bdi: missing")
    else:
        errors = validate_bdi(spec["bdi"])
        result["errors"].extend(errors)

    # Validate indiretos
    if "indiretos" not in spec:
        result["warnings"].append("spec.indiretos: missing (optional if no indirect costs)")
    else:
        errors = validate_indiretos(spec["indiretos"])
        result["errors"].extend(errors)

    # Validate resultado (if present)
    if "resultado" in ref:
        errors = validate_resultado(ref.get("resultado", {}))
        result["warnings"].extend(errors)

    result["valid"] = len(result["errors"]) == 0
    return result

def main():
    project_root = Path(__file__).resolve().parent.parent
    benchmarks_root = project_root / "benchmarks" / "data"
    catalog = load_catalog(project_root)

    print("\n" + "=" * 90)
    print("VALIDATING REFERENCIA.JSON STRUCTURAL INTEGRITY")
    print("=" * 90)

    # Find all referencia.json files
    ref_files = sorted(benchmarks_root.glob("*/referencia.json"))

    all_results = []
    valid_count = 0

    for ref_path in ref_files:
        slug = ref_path.parent.name
        result = validate_referencia(slug, ref_path, catalog)
        all_results.append(result)

        if result["valid"]:
            valid_count += 1
            status = "✓"
        else:
            status = "✗"

        print(f"\n{status} {slug:25} ({len(result['errors'])} errors, {len(result['warnings'])} warnings)")

        for error in result["errors"][:3]:  # Show first 3 errors
            print(f"    ERROR: {error}")

        for warning in result["warnings"][:2]:  # Show first 2 warnings
            print(f"    WARN: {warning}")

        if len(result["errors"]) > 3:
            print(f"    ... and {len(result['errors']) - 3} more errors")

    print("\n" + "=" * 90)
    print(f"SUMMARY: {valid_count}/{len(all_results)} files valid")
    print("=" * 90 + "\n")

    return all_results

if __name__ == "__main__":
    main()
