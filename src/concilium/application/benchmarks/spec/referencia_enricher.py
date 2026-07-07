"""Enrich referencia.json files with complete spec including EAP and cronograma.

Takes existing referencia.json with just cost data and enriches it with
full project specification including EAP items, CPUs, predecessores, etc.

Uses semantic CPU mapping to match cronograma items to actual catalog CPUs.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

from ..cronograma_parser import CronogramaParser
from ..validation.cpu_mapper import CpuMapper

logger = logging.getLogger(__name__)


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


def _parse_produtividade_line(line: str) -> tuple[str, float] | None:
    """Parse a single produtividade.txt line into (item_id, produtividade) or None if skippable."""
    line = line.strip()
    if not line:
        return None

    parts = [p.strip() for p in line.split("\t")]
    if len(parts) < 4:
        return None

    item_id = parts[0]
    if not item_id or not item_id[0].isdigit():
        return None

    try:
        prod_str = parts[3].replace(".", "").replace(",", ".")
        return item_id, float(prod_str)
    except (ValueError, IndexError):
        logger.debug("Linha ignorada ao enriquecer EAP (item %s): valor de produtividade inválido", item_id)
        return None


def _parse_produtividade_map(produtividade_path: Path) -> dict[str, float]:
    produtividade_map: dict[str, float] = {}
    try:
        with open(produtividade_path, encoding="utf-8") as f:
            lines = f.readlines()

        for line in lines[4:]:  # Skip header rows
            parsed = _parse_produtividade_line(line)
            if parsed is not None:
                item_id, prod = parsed
                produtividade_map[item_id] = prod
    except Exception as e:
        logger.warning("Falha ao ler arquivo de produtividade para enriquecimento de EAP: %s", e, exc_info=True)
    return produtividade_map


def _apply_produtividade_to_items(eap_items: list[dict], produtividade_map: dict[str, float]) -> None:
    for item in eap_items:
        if item.get("item_id") in produtividade_map:
            prod = produtividade_map[item["item_id"]]
            # Store productivity in CPU metadata for later use by skill-04
            if "cpu_meta" not in item:
                item["cpu_meta"] = {}
            item["cpu_meta"]["producao_horaria"] = prod


def _enrich_eap_with_produtividade(eap_items: list[dict], produtividade_path: Path) -> None:
    """Enrich EAP items with productivity data from produtividade.txt.

    Updates CPU to include productivity information when available.
    """
    if not produtividade_path.exists():
        return

    produtividade_map = _parse_produtividade_map(produtividade_path)
    _apply_produtividade_to_items(eap_items, produtividade_map)


def _ensure_referencia_meta_defaults(
    referencia: dict[str, Any], cronograma_path: Path, project_meta: dict[str, Any] | None
) -> None:
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


def _build_cpu_mapper(contexto_id: str) -> CpuMapper | None:
    """Load CPU mapper for semantic matching, returning None on failure."""
    try:
        return CpuMapper(contexto_id)
    except Exception as e:
        print(f"Warning: CPU mapper initialization failed: {e}")
        return None


def _resolve_item_cpu_id(item: dict, cpu_mapper: CpuMapper | None) -> None:
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


def _apply_producao_horaria_fallback(item: dict) -> None:
    # Store productivity data from cronograma if available
    if "cpu_meta" not in item:
        item["cpu_meta"] = {}
    if "producao_horaria" not in item.get("cpu_meta", {}):
        # Extract from EAP item if available
        if "producao_horaria" in item and item["producao_horaria"] > 0:
            item["cpu_meta"]["producao_horaria"] = item["producao_horaria"]


def _build_final_eap(eap_items: list[dict], cpu_mapper: CpuMapper | None) -> list[dict]:
    # Build complete EAP with just leaf items (no section headers)
    # Section headers would have quantitativo=0 which violates EapItem constraints
    final_eap = []
    ordem = 1

    for item in eap_items:
        _resolve_item_cpu_id(item, cpu_mapper)
        _apply_producao_horaria_fallback(item)

        # Update ordem to be sequential
        item["ordem"] = ordem
        final_eap.append(item)
        ordem += 1

    return final_eap


def _log_cpu_mapping_stats(cpu_mapper: CpuMapper | None) -> None:
    if not cpu_mapper:
        return
    stats = cpu_mapper.get_mapping_stats()
    if stats["total_items_processed"] > 0:
        print(
            f"CPU mapping: {stats['successfully_mapped']}/{stats['total_items_processed']} items mapped "
            f"({stats['success_rate']:.1f}% success rate)"
        )


def _build_cronograma_from_eap(final_eap: list[dict]) -> list[dict]:
    # Build cronograma in spec format (list of items with scheduling data)
    return [
        {
            "item_id": item["item_id"],
            "producao_diaria": item.get("producao_diaria", 0.0),
            "semanas": {},  # Could be enriched with actual week data from cronograma
        }
        for item in final_eap
        if "." in item["item_id"]  # Only leaf items, not section headers
    ]


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
    _ensure_referencia_meta_defaults(referencia, cronograma_path, project_meta)

    # Parse cronograma to get EAP items
    parser = CronogramaParser()
    eap_items = parser.parse_file(cronograma_path)

    if not eap_items:
        print(f"Warning: No EAP items extracted from {cronograma_path}")
        return referencia

    # Enrich EAP items with productivity data if available
    produtividade_path = cronograma_path.parent / "produtividade.txt"
    _enrich_eap_with_produtividade(eap_items, produtividade_path)

    cpu_mapper = _build_cpu_mapper(contexto_id)

    final_eap = _build_final_eap(eap_items, cpu_mapper)

    # Log mapping statistics if mapper was used
    _log_cpu_mapping_stats(cpu_mapper)

    cronograma = _build_cronograma_from_eap(final_eap)

    # Update spec
    referencia["spec"]["eap"] = final_eap
    referencia["spec"]["cronograma"] = cronograma
    referencia["spec"]["rcpsp_spec"] = referencia["spec"].get("rcpsp_spec", {})

    return referencia


def _extract_item_id_from_line_parts(parts: list[str]) -> str | None:
    """Validate the first part of a cpus.txt line as an item_id (e.g. "2.1", "3").

    May raise ValueError if a segment is non-numeric — propagated to the caller.
    """
    if not parts:
        return None

    # Check if first part looks like an item_id (e.g., "2.1", "3", "1.2")
    potential_id = parts[0]
    if not (potential_id[0].isdigit()):
        return None

    # Validate format: either "N" or "N.M"
    id_parts = potential_id.split(".")
    if len(id_parts) > 2:
        return None
    for part in id_parts:
        int(part)  # Validate each part is numeric

    return potential_id


def _extract_descricao_from_parts(parts: list[str], item_id: str) -> str:
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
    return descricao


def _infer_predecessores_from_hierarchy(item_id: str, seen_ids: set[str]) -> list[dict[str, Any]]:
    # Infer predecessores based on hierarchy
    predecessores: list[dict[str, Any]] = []
    if "." in item_id:
        item_num = int(item_id.split(".")[1])
        if item_num > 1:
            prev_id = f"{item_id.split('.')[0]}.{item_num - 1}"
            if prev_id in seen_ids:
                predecessores.append(
                    {
                        "item_id": prev_id,
                        "tipo": "FS",
                        "lag": 0,
                        "completion_threshold_pct": 1.0,
                    }
                )
    return predecessores


def _build_eap_item_from_cpus_line(line: str, seen_ids: set[str], ordem: int) -> dict[str, Any] | None:
    """Parse a single cpus.txt line into an EAP item, or None if it should be skipped.

    May raise ValueError/IndexError — propagated to the caller.
    """
    # Look for item_id pattern: single or double digit followed by optional decimal
    # Format: "CÓDIGO" in column 1, item_id in next columns
    parts = [p.strip() for p in line.split("\t") if p.strip()]

    item_id = _extract_item_id_from_line_parts(parts)
    if item_id is None:
        return None

    # Skip section headers (single digit items without subitems seen yet)
    # For now, include all items - they'll be filtered later if needed
    if item_id in seen_ids:
        return None
    seen_ids.add(item_id)

    descricao = _extract_descricao_from_parts(parts, item_id)

    # Create basic EAP item with reasonable defaults
    predecessores = _infer_predecessores_from_hierarchy(item_id, seen_ids)
    return {
        "item_id": item_id,
        "ordem": ordem,
        "cpu_id": "CPU-UNKNOWN",  # Will be mapped later
        "descricao": descricao,
        "unidade": "un",  # Generic default
        "quantitativo": 1.0,  # Minimal default
        "predecessores": predecessores,
    }


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
        for _line_no, line in enumerate(lines):
            line = line.strip()
            try:
                eap_item = _build_eap_item_from_cpus_line(line, seen_ids, ordem)
            except (ValueError, IndexError):
                continue

            if eap_item is None:
                continue

            eap_items.append(eap_item)
            ordem += 1

    except Exception as e:
        print(f"Warning: Failed to parse {cpus_path}: {e}")

    return eap_items


def _try_enrich_via_cronograma(
    referencia: dict, cronograma_path: Path, referencia_path: Path, benchmark_dir: Path
) -> bool:
    """Attempt to enrich referencia from cronograma.txt (primary source)."""
    try:
        referencia = enrich_referencia_with_eap(referencia, cronograma_path)
        referencia_path.write_text(json.dumps(referencia, indent=2, ensure_ascii=False), encoding="utf-8")
        print(f"✓ Enriched {benchmark_dir.name} with {len(referencia['spec']['eap'])} EAP items (cronograma)")
        return True
    except Exception as e:
        print(f"⚠ cronograma.txt parsing failed: {e}")
        return False


def _ensure_cpus_meta_defaults(referencia: dict, benchmark_dir: Path) -> None:
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


def _apply_cpus_eap_to_referencia(referencia: dict, eap_items: list[dict]) -> None:
    # Build spec with EAP
    if "spec" not in referencia:
        referencia["spec"] = {}

    referencia["spec"]["eap"] = eap_items
    referencia["spec"]["cronograma"] = [
        {"item_id": item["item_id"], "producao_diaria": 0.0, "semanas": {}} for item in eap_items
    ]
    referencia["spec"]["rcpsp_spec"] = {}


def _try_enrich_via_cpus(referencia: dict, cpus_path: Path, referencia_path: Path, benchmark_dir: Path) -> bool:
    """Attempt to enrich referencia from cpus.txt (fallback source)."""
    try:
        eap_items = _extract_eap_from_cpus_txt(cpus_path)
        if eap_items:
            _ensure_cpus_meta_defaults(referencia, benchmark_dir)
            _apply_cpus_eap_to_referencia(referencia, eap_items)

            referencia_path.write_text(json.dumps(referencia, indent=2, ensure_ascii=False), encoding="utf-8")
            print(f"✓ Enriched {benchmark_dir.name} with {len(eap_items)} EAP items (cpus.txt)")
            return True

    except Exception as e:
        print(f"⚠ cpus.txt extraction failed: {e}")

    return False


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
        if _try_enrich_via_cronograma(referencia, cronograma_path, referencia_path, benchmark_dir):
            return True

    # Fallback to cpus.txt if cronograma unavailable
    if cpus_path.exists():
        if _try_enrich_via_cpus(referencia, cpus_path, referencia_path, benchmark_dir):
            return True

    print(f"❌ No EAP source found (cronograma.txt or cpus.txt): {benchmark_dir.name}")
    return False
