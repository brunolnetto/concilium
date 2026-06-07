"""Enrich referencia.json files with complete spec including EAP and cronograma.

Takes existing referencia.json with just cost data and enriches it with
full project specification including EAP items, CPUs, predecessores, etc.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .cronograma_parser import CronogramaParser


def _infer_cpu_from_section(section_id: str, item_num: int) -> str:
    """Generate CPU code from section and item number."""
    section_names = {
        "1": "MOB",  # Mobilização
        "2": "SUPP",  # Supressão
        "3": "LIMP",  # Limpeza
        "4": "ESCA",  # Escavação
        "5": "EQUIP",  # Equipamento
    }
    section_name = section_names.get(section_id, f"SEC{section_id}")
    return f"CPU-{section_name}-{item_num:03d}"


def enrich_referencia_with_eap(
    referencia: dict[str, Any],
    cronograma_path: Path,
    project_meta: dict[str, Any] | None = None
) -> dict[str, Any]:
    """Enrich referencia with EAP structure from cronograma.txt.

    Args:
        referencia: Existing referencia dict (may have minimal spec)
        cronograma_path: Path to cronograma.txt file
        project_meta: Optional project metadata to override/merge

    Returns:
        Enriched referencia dict with complete spec.eap and spec.cronograma
    """
    # Ensure meta exists
    if "meta" not in referencia:
        referencia["meta"] = {}

    # Provide sensible defaults for required fields
    if not referencia["meta"].get("data_inicio"):
        referencia["meta"]["data_inicio"] = "2026-01-01"
    if not referencia["meta"].get("data_termino"):
        referencia["meta"]["data_termino"] = "2027-12-31"
    if not referencia["meta"].get("projeto"):
        referencia["meta"]["projeto"] = cronograma_path.parent.parent.parent.name
    if not referencia["meta"].get("localizacao"):
        referencia["meta"]["localizacao"] = "Brasil"
    if not referencia["meta"].get("regime_trabalho"):
        referencia["meta"]["regime_trabalho"] = {"horas_dia": 8, "dias_semana": 6}
    if not referencia["meta"].get("mode"):
        referencia["meta"]["mode"] = "benchmark_config"

    # Merge project metadata
    if project_meta:
        referencia["meta"].update(project_meta)

    # Ensure spec exists
    if "spec" not in referencia:
        referencia["spec"] = {}

    # Parse cronograma to get EAP items
    parser = CronogramaParser()
    eap_items = parser.parse_file(cronograma_path)

    if not eap_items:
        print(f"Warning: No EAP items extracted from {cronograma_path}")
        return referencia

    # Build complete EAP with just leaf items (no section headers)
    # Section headers would have quantitativo=0 which violates EapItem constraints
    final_eap = []
    ordem = 1

    for item in eap_items:
        # Ensure CPU is set (use inference if needed)
        if item["cpu_id"] == "CPU-UNKNOWN":
            section_id = item["item_id"].split(".")[0]
            item_num = int(item["item_id"].split(".")[1])
            item["cpu_id"] = _infer_cpu_from_section(section_id, item_num)

        # Update ordem to be sequential
        item["ordem"] = ordem
        final_eap.append(item)
        ordem += 1

    # Build cronograma in spec format (list of items with scheduling data)
    cronograma = [
        {
            "item_id": item["item_id"],
            "producao_diaria": item.get("producao_diaria", 0.0),
            "semanas": {}  # Could be enriched with actual week data from cronograma
        }
        for item in final_eap
        if "." in item["item_id"]  # Only leaf items, not section headers
    ]

    # Update spec
    referencia["spec"]["eap"] = final_eap
    referencia["spec"]["cronograma"] = cronograma
    referencia["spec"]["rcpsp_spec"] = referencia["spec"].get("rcpsp_spec", {})

    return referencia


def enrich_benchmark_referencia(benchmark_dir: Path) -> bool:
    """Enrich a benchmark's referencia.json with EAP from cronograma.txt.

    Args:
        benchmark_dir: Path to benchmark directory (e.g., benchmarks/data/MARA_ROSA)

    Returns:
        True if successful, False if cronograma.txt not found or parse failed
    """
    referencia_path = benchmark_dir / "referencia.json"
    cronograma_path = benchmark_dir / "artifacts" / "raw" / "cronograma.txt"

    if not cronograma_path.exists():
        print(f"❌ cronograma.txt not found: {cronograma_path}")
        return False

    if not referencia_path.exists():
        print(f"❌ referencia.json not found: {referencia_path}")
        return False

    # Load existing referencia
    referencia = json.loads(referencia_path.read_text(encoding="utf-8"))

    # Enrich with EAP
    try:
        referencia = enrich_referencia_with_eap(referencia, cronograma_path)
        referencia_path.write_text(
            json.dumps(referencia, indent=2, ensure_ascii=False),
            encoding="utf-8"
        )
        print(f"✓ Enriched {benchmark_dir.name} with {len(referencia['spec']['eap'])} EAP items")
        return True
    except Exception as e:
        print(f"❌ Error enriching {benchmark_dir.name}: {e}")
        return False
