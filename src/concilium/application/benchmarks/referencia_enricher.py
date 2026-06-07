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

    # Build section headers from extracted items
    sections: dict[str, Any] = {}

    for item in eap_items:
        section_id = item["item_id"].split(".")[0]
        if section_id not in sections:
            sections[section_id] = {
                "item_id": section_id,
                "ordem": int(section_id),
                "cpu_id": f"CPU-SECTION-{section_id}",
                "descricao": f"Seção {section_id}",
                "unidade": "",
                "quantitativo": 0.0,
                "predecessores": [] if section_id == "1" else [{
                    "item_id": str(int(section_id) - 1),
                    "tipo": "FS",
                    "lag": 0,
                    "completion_threshold_pct": 1.0
                }],
            }

    # Build complete EAP with sections and items
    eap = list(sections.values())
    eap.sort(key=lambda x: x["ordem"])

    # Insert items after their section headers
    final_eap = []
    for item in eap_items:
        section_id = item["item_id"].split(".")[0]

        # Add section header if not yet added
        section = next((s for s in eap if s["item_id"] == section_id), None)
        if section and section not in final_eap:
            final_eap.append(section)

        # Ensure CPU is set (use inference if needed)
        if item["cpu_id"] == "CPU-UNKNOWN":
            section_num = int(section_id)
            item_num = int(item["item_id"].split(".")[1])
            item["cpu_id"] = _infer_cpu_from_section(section_id, item_num)

        final_eap.append(item)

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
