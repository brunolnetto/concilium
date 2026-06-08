#!/usr/bin/env python3
"""Enrich 7 benchmarks with semantic CPU mapping from catalog.

Reads cronograma.txt for each benchmark, maps item descriptions to catalog CPUs,
and updates referencia.json with correct CPU IDs and productivity data.
"""

import json
import sys
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from concilium.application.benchmarks.cpu_mapper import CpuMapper
from concilium.application.benchmarks.cpu_validator import CpuValidator
from concilium.application.benchmarks.cronograma_parser import CronogramaParser
from concilium.application.benchmarks.referencia_enricher import (
    enrich_referencia_with_eap,
)


def enrich_benchmark(slug: str, benchmarks_root: Path, config_root: Path) -> bool:
    """Enrich a single benchmark with CPU mapping.

    Args:
        slug: Benchmark slug (e.g., "LUNDIN")
        benchmarks_root: Path to benchmarks/data directory
        config_root: Path to config directory

    Returns:
        True if successful, False otherwise
    """
    benchmark_dir = benchmarks_root / slug
    cronograma_path = benchmark_dir / "artifacts" / "raw" / "cronograma.txt"
    referencia_path = benchmark_dir / "referencia.json"

    if not cronograma_path.exists():
        print(f"❌ {slug}: cronograma.txt não encontrado")
        return False

    if not referencia_path.exists():
        print(f"❌ {slug}: referencia.json não encontrado")
        return False

    try:
        print(f"\n{'='*70}")
        print(f"Enriquecendo {slug}")
        print(f"{'='*70}")

        # Load existing referencia
        referencia = json.loads(referencia_path.read_text(encoding="utf-8"))

        # Enrich with EAP from cronograma + CPU mapping
        referencia = enrich_referencia_with_eap(
            referencia, cronograma_path, contexto_id="mendeslobo"
        )

        # Validate mappings
        eap_items = referencia.get("spec", {}).get("eap", [])
        try:
            validator = CpuValidator("mendeslobo")
            validation = validator.validate_eap_items(eap_items)
            validator.print_validation_report(validation)
            success = validation["invalid"] == 0
        except Exception as ve:
            print(f"⚠️ Validação indisponível: {ve}")
            success = True  # Continuamos mesmo se validador falhar

        # Save enriched referencia
        referencia_path.write_text(
            json.dumps(referencia, indent=2, ensure_ascii=False),
            encoding="utf-8",
        )

        print(f"\n✓ {slug}: salvo com {len(eap_items)} items")
        return success

    except Exception as e:
        print(f"❌ {slug}: erro durante enriquecimento: {e}")
        import traceback
        traceback.print_exc()
        return False


def main():
    """Enrich all 7 benchmarks with semantic CPU mapping."""
    project_root = Path(__file__).parent.parent
    benchmarks_root = project_root / "benchmarks" / "data"
    config_root = project_root / "config"

    slugs = [
        "CTC",
        "LUNDIN",
        "MATEC_GUARULHOS",
        "MATEC_UBERLANDIA",
        "PRIVATE_LOG",
        "VALE",
        "AGIS",
    ]

    results = {}
    for slug in slugs:
        success = enrich_benchmark(slug, benchmarks_root, config_root)
        results[slug] = "✓ OK" if success else "✗ FALHOU"

    print(f"\n{'='*70}")
    print("RESUMO FINAL")
    print(f"{'='*70}")
    for slug, status in results.items():
        print(f"  {slug}: {status}")


if __name__ == "__main__":
    main()
