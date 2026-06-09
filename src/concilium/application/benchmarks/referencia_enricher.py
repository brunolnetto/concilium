"""Enrich referencia.json files with complete spec including EAP and cronograma.

Takes existing referencia.json with just cost data and enriches it with
full project specification including EAP items, CPUs, predecessores, etc.

Uses semantic CPU mapping to match cronograma items to actual catalog CPUs.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .cpu_mapper import CpuMapper
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


def _enrich_eap_with_produtividade(eap_items: list[dict], produtividade_path: Path) -> None:
    """Enrich EAP items with productivity data from produtividade.txt.

    Updates CPU to include productivity information when available.
    """
    if not produtividade_path.exists():
        return

    produtividade_map = {}
    try:
        with open(produtividade_path, encoding="utf-8") as f:
            lines = f.readlines()

        for line in lines[4:]:  # Skip header rows
            line = line.strip()
            if not line:
                continue

            parts = [p.strip() for p in line.split("\t")]
            if len(parts) < 4:
                continue

            item_id = parts[0]
            if not item_id or not item_id[0].isdigit():
                continue

            try:
                prod_str = parts[3].replace(".", "").replace(",", ".")
                produtividade_map[item_id] = float(prod_str)
            except (ValueError, IndexError):
                pass
    except Exception:
        pass

    # Enrich items with productivity info
    for item in eap_items:
        if item.get("item_id") in produtividade_map:
            prod = produtividade_map[item["item_id"]]
            # Store productivity in CPU metadata for later use by skill-04
            if "cpu_meta" not in item:
                item["cpu_meta"] = {}
            item["cpu_meta"]["producao_horaria"] = prod


def enrich_referencia_with_eap(
    referencia: dict[str, Any],
    cronograma_path: Path,
    project_meta: dict[str, Any] | None = None,
    contexto_id: str = "mendeslobo",
) -> dict[str, Any]:
    """Enrich referencia with EAP structure from cronograma.txt.

    Args:
        referencia: Existing referencia dict (may have minimal spec)
        cronograma_path: Path to cronograma.txt file
        project_meta: Optional project metadata to override/merge
        contexto_id: Catalog context for semantic CPU mapping (default: mendeslobo)

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

    # Enrich EAP items with productivity data if available
    produtividade_path = cronograma_path.parent / "produtividade.txt"
    _enrich_eap_with_produtividade(eap_items, produtividade_path)

    # Load CPU mapper for semantic matching
    try:
        cpu_mapper = CpuMapper(contexto_id)
    except Exception as e:
        print(f"Warning: CPU mapper initialization failed: {e}")
        cpu_mapper = None

    # Build complete EAP with just leaf items (no section headers)
    # Section headers would have quantitativo=0 which violates EapItem constraints
    final_eap = []
    ordem = 1

    for item in eap_items:
        # Try to map to actual catalog CPU using semantic search
        if cpu_mapper and item["cpu_id"] == "CPU-UNKNOWN":
            mapped_cpu = cpu_mapper.map_item_to_cpu(item["item_id"], item["descricao"])
            if mapped_cpu:
                item["cpu_id"] = mapped_cpu
            else:
                # Fallback to section-based inference
                section_id = item["item_id"].split(".")[0]
                item_num = int(item["item_id"].split(".")[1])
                item["cpu_id"] = _infer_cpu_from_section(section_id, item_num)
        elif not cpu_mapper:
            # No mapper available, use fallback inference
            section_id = item["item_id"].split(".")[0]
            item_num = int(item["item_id"].split(".")[1])
            item["cpu_id"] = _infer_cpu_from_section(section_id, item_num)

        # Store productivity data from cronograma if available
        if "cpu_meta" not in item:
            item["cpu_meta"] = {}
        if "producao_horaria" not in item.get("cpu_meta", {}):
            # Extract from EAP item if available
            if "producao_horaria" in item and item["producao_horaria"] > 0:
                item["cpu_meta"]["producao_horaria"] = item["producao_horaria"]

        # Update ordem to be sequential
        item["ordem"] = ordem
        final_eap.append(item)
        ordem += 1

    # Log mapping statistics if mapper was used
    if cpu_mapper:
        stats = cpu_mapper.get_mapping_stats()
        if stats["total_items_processed"] > 0:
            print(
                f"CPU mapping: {stats['successfully_mapped']}/{stats['total_items_processed']} items mapped "
                f"({stats['success_rate']:.1f}% success rate)"
            )

    # Build cronograma in spec format (list of items with scheduling data)
    cronograma = [
        {
            "item_id": item["item_id"],
            "producao_diaria": item.get("producao_diaria", 0.0),
            "semanas": {},  # Could be enriched with actual week data from cronograma
        }
        for item in final_eap
        if "." in item["item_id"]  # Only leaf items, not section headers
    ]

    # Update spec
    referencia["spec"]["eap"] = final_eap
    referencia["spec"]["cronograma"] = cronograma
    referencia["spec"]["rcpsp_spec"] = referencia["spec"].get("rcpsp_spec", {})

    return referencia


def _extract_eap_from_cpus_txt(cpus_path: Path) -> list[dict[str, Any]]:
    """Extract EAP structure from cpus.txt when cronograma is unavailable.

    Parses itemized CPU descriptions to build basic EAP with hierarchical structure.
    """
    eap_items = []
    ordem = 1

    try:
        with open(cpus_path, encoding="utf-8") as f:
            lines = f.readlines()

        seen_ids: set[str] = set()
        for line_no, line in enumerate(lines):
            line = line.strip()

            # Look for item_id pattern: single or double digit followed by optional decimal
            # Format: "CÓDIGO" in column 1, item_id in next columns
            parts = [p.strip() for p in line.split("\t") if p.strip()]

            if not parts:
                continue

            # Check if first part looks like an item_id (e.g., "2.1", "3", "1.2")
            potential_id = parts[0]
            if not (potential_id[0].isdigit()):
                continue

            # Try to parse as item_id
            try:
                # Validate format: either "N" or "N.M"
                id_parts = potential_id.split(".")
                if len(id_parts) > 2:
                    continue
                for part in id_parts:
                    int(part)  # Validate each part is numeric

                item_id = potential_id

                # Skip section headers (single digit items without subitems seen yet)
                # For now, include all items - they'll be filtered later if needed
                if item_id in seen_ids:
                    continue
                seen_ids.add(item_id)

                # Description is typically the next non-empty part after CODE/DATE/UNIT headers
                descricao = ""
                if len(parts) > 1:
                    # Skip date-like patterns and look for actual description
                    for part in parts[1:]:
                        if not any(c in part for c in "0123456789/,-"):  # Skip dates
                            descricao = part
                            break

                # If still no description, use generic one
                if not descricao:
                    descricao = f"Item {item_id}"

                # Create basic EAP item with reasonable defaults
                eap_item = {
                    "item_id": item_id,
                    "ordem": ordem,
                    "cpu_id": "CPU-UNKNOWN",  # Will be mapped later
                    "descricao": descricao,
                    "unidade": "un",  # Generic default
                    "quantitativo": 1.0,  # Minimal default
                    "predecessores": [],
                }

                # Infer predecessores based on hierarchy
                if "." in item_id:
                    item_num = int(item_id.split(".")[1])
                    if item_num > 1:
                        prev_id = f"{item_id.split('.')[0]}.{item_num - 1}"
                        if prev_id in seen_ids:
                            eap_item["predecessores"].append(
                                {
                                    "item_id": prev_id,
                                    "tipo": "FS",
                                    "lag": 0,
                                    "completion_threshold_pct": 1.0,
                                }
                            )

                eap_items.append(eap_item)
                ordem += 1

            except (ValueError, IndexError):
                continue

    except Exception as e:
        print(f"Warning: Failed to parse {cpus_path}: {e}")

    return eap_items


def enrich_benchmark_referencia(benchmark_dir: Path) -> bool:
    """Enrich a benchmark's referencia.json with EAP from cronograma.txt or cpus.txt.

    Args:
        benchmark_dir: Path to benchmark directory (e.g., benchmarks/data/MARA_ROSA)

    Returns:
        True if successful, False if no EAP source found
    """
    referencia_path = benchmark_dir / "referencia.json"
    cronograma_path = benchmark_dir / "artifacts" / "raw" / "cronograma.txt"
    cpus_path = benchmark_dir / "artifacts" / "raw" / "cpus.txt"

    if not referencia_path.exists():
        print(f"❌ referencia.json not found: {referencia_path}")
        return False

    # Load existing referencia
    referencia = json.loads(referencia_path.read_text(encoding="utf-8"))

    # Try cronograma.txt first (primary source)
    if cronograma_path.exists() and cronograma_path.stat().st_size > 0:
        try:
            referencia = enrich_referencia_with_eap(referencia, cronograma_path)
            referencia_path.write_text(json.dumps(referencia, indent=2, ensure_ascii=False), encoding="utf-8")
            print(f"✓ Enriched {benchmark_dir.name} with {len(referencia['spec']['eap'])} EAP items (cronograma)")
            return True
        except Exception as e:
            print(f"⚠ cronograma.txt parsing failed: {e}")

    # Fallback to cpus.txt if cronograma unavailable
    if cpus_path.exists():
        try:
            eap_items = _extract_eap_from_cpus_txt(cpus_path)
            if eap_items:
                # Ensure meta exists
                if "meta" not in referencia:
                    referencia["meta"] = {}
                if not referencia["meta"].get("data_inicio"):
                    referencia["meta"]["data_inicio"] = "2026-01-01"
                if not referencia["meta"].get("data_termino"):
                    referencia["meta"]["data_termino"] = "2027-12-31"
                if not referencia["meta"].get("projeto"):
                    referencia["meta"]["projeto"] = benchmark_dir.name
                if not referencia["meta"].get("localizacao"):
                    referencia["meta"]["localizacao"] = "Brasil"
                if not referencia["meta"].get("regime_trabalho"):
                    referencia["meta"]["regime_trabalho"] = {"horas_dia": 8, "dias_semana": 6}

                # Build spec with EAP
                if "spec" not in referencia:
                    referencia["spec"] = {}

                referencia["spec"]["eap"] = eap_items
                referencia["spec"]["cronograma"] = [
                    {"item_id": item["item_id"], "producao_diaria": 0.0, "semanas": {}} for item in eap_items
                ]
                referencia["spec"]["rcpsp_spec"] = {}

                referencia_path.write_text(json.dumps(referencia, indent=2, ensure_ascii=False), encoding="utf-8")
                print(f"✓ Enriched {benchmark_dir.name} with {len(eap_items)} EAP items (cpus.txt)")
                return True

        except Exception as e:
            print(f"⚠ cpus.txt extraction failed: {e}")

    print(f"❌ No EAP source found (cronograma.txt or cpus.txt): {benchmark_dir.name}")
    return False
