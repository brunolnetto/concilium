"""Parser for cronograma.txt files to extract EAP structure.

Transforms cronograma.txt (TSV schedule data) into spec.eap format with:
- item_id: extracted from item column (e.g., "2.1", "2.2")
- descricao: service/activity description
- unidade: unit of measurement (un, m3, m², etc.)
- quantitativo: total quantity for the project
- cpu_id: inferred from description via cpus.txt mapping
- predecessores: inferred from scheduling structure and chronological order
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

import csv


@dataclass
class CronogramaItem:
    """Single cronograma item extracted from cronograma.txt."""

    item_id: str
    descricao: str
    unidade: str
    quantitativo: float
    producao_diaria: float = 0.0


def _parse_valor(s: str) -> float:
    """Parse Portuguese number format (1.234,56 → 1234.56)."""
    if not s:
        return 0.0
    s = s.strip()
    if s == "-":
        return 0.0
    # Convert 1.234,56 → 1234.56
    s = s.replace(".", "").replace(",", ".")
    try:
        return float(s)
    except ValueError:
        return 0.0


def _load_produtividade_map(produtividade_path: Path) -> dict[str, float]:
    """Load productivity values from produtividade.txt.

    Format: TSV with columns: ITEM, SERVIÇO, UNID, PRODUÇÃO HORARIA / EQUIPE
    Returns dict mapping item_id -> producao_horaria
    """
    produtividade = {}

    if not produtividade_path.exists():
        return produtividade

    try:
        with open(produtividade_path, encoding="utf-8") as f:
            lines = f.readlines()

        for line_no, line in enumerate(lines[4:], start=4):  # Skip header
            line = line.strip()
            if not line:
                continue

            parts = [p.strip() for p in line.split('\t')]
            if len(parts) < 4:
                continue

            item_id = parts[0]
            if not item_id or not item_id[0].isdigit():
                continue

            # Produção horária is 4th column (index 3)
            try:
                prod_str = parts[3].replace('.', '').replace(',', '.')
                produtividade[item_id] = float(prod_str)
            except (ValueError, IndexError):
                pass

    except Exception:
        pass

    return produtividade


def _find_cpu_for_item(descricao: str, cpus_map: dict[str, str]) -> str | None:
    """Infer CPU from item description using cpus_map.

    Tries to match keywords in description against known CPU descriptions.
    """
    descricao_lower = descricao.lower()

    for cpu_id, cpu_desc in cpus_map.items():
        cpu_desc_lower = cpu_desc.lower()
        # Try exact substring match
        if cpu_desc_lower in descricao_lower or descricao_lower in cpu_desc_lower:
            return cpu_id
        # Try keyword matching (first N words)
        cpu_words = cpu_desc_lower.split()[:3]
        if all(w in descricao_lower for w in cpu_words if w):
            return cpu_id

    return None


def _infer_predecessores(
    items: list[CronogramaItem],
    item_id: str,
    secao_map: dict[str, str]
) -> list[dict[str, Any]]:
    """Infer predecessores from item structure and order.

    Rules:
    1. Items within same section (e.g., 2.1, 2.2, 2.3) depend on previous existing item in same section
    2. If no previous item in section, depend on last item of previous section
    3. Very first item (1.1) has no dependencies
    4. Handles gaps in numbering (e.g., 1.1 → 1.3 without 1.2)

    Section headers are not included as predecessors since they're excluded from EAP.

    Returns list of predecessor dicts with keys: item_id, tipo, lag, completion_threshold_pct
    """
    parts = item_id.split(".")

    # Section header (e.g., "2") - no predecessors (but shouldn't be included in EAP anyway)
    if len(parts) == 1:
        return []

    section = int(parts[0])
    item_num = int(parts[1]) if len(parts) > 1 else 1

    predecessores = []
    item_ids_in_section = set()

    # Build set of all item_ids that actually exist in this section
    for i in items:
        i_parts = i.item_id.split(".")
        if len(i_parts) == 2 and int(i_parts[0]) == section:
            try:
                item_ids_in_section.add(int(i_parts[1]))
            except ValueError:
                pass

    # If first item in section, depend on last item of previous section (if exists)
    if item_num == 1:
        if section > 1:
            # Previous section exists - find its last item
            prev_section_str = str(section - 1)
            last_prev_item = None
            max_prev_num = 0
            for i in items:
                if i.item_id.startswith(prev_section_str + "."):
                    try:
                        prev_num = int(i.item_id.split(".")[1])
                        if prev_num > max_prev_num:
                            max_prev_num = prev_num
                            last_prev_item = i.item_id
                    except (ValueError, IndexError):
                        pass

            if last_prev_item:
                predecessores.append({
                    "item_id": last_prev_item,
                    "tipo": "FS",
                    "lag": 0,
                    "completion_threshold_pct": 1.0  # Must finish before this can start
                })
        # else: section == 1, first item overall, no predecessors
    else:
        # Find previous existing item in same section (may not be item_num - 1 due to gaps)
        prev_found = None
        for num in range(item_num - 1, 0, -1):
            if num in item_ids_in_section:
                prev_found = f"{section}.{num}"
                break

        if prev_found:
            predecessores.append({
                "item_id": prev_found,
                "tipo": "FS",
                "lag": 0,
                "completion_threshold_pct": 1.0  # Must finish before this can start
            })
        else:
            # No previous item in section, depend on last item of previous section
            if section > 1:
                prev_section_str = str(section - 1)
                last_prev_item = None
                max_prev_num = 0
                for i in items:
                    if i.item_id.startswith(prev_section_str + "."):
                        try:
                            prev_num = int(i.item_id.split(".")[1])
                            if prev_num > max_prev_num:
                                max_prev_num = prev_num
                                last_prev_item = i.item_id
                        except (ValueError, IndexError):
                            pass

                if last_prev_item:
                    predecessores.append({
                        "item_id": last_prev_item,
                        "tipo": "FS",
                        "lag": 0,
                        "completion_threshold_pct": 1.0
                    })

    return predecessores


class CronogramaParser:
    """Parse cronograma.txt files to extract EAP structure."""

    def __init__(self, cpus_map: dict[str, str] | None = None):
        """Initialize parser with optional CPU mapping.

        Args:
            cpus_map: Dict mapping cpu_id → cpu_description for inference
        """
        self.cpus_map = cpus_map or {}

    def parse_file(self, path: Path) -> list[dict[str, Any]]:
        """Parse cronograma.txt and return list of EAP items."""
        with open(path, encoding="utf-8") as f:
            lines = f.readlines()

        return self.parse_lines(lines)

    def parse_lines(self, lines: list[str]) -> list[dict[str, Any]]:
        """Parse cronograma.txt lines and return list of EAP items."""
        items: list[CronogramaItem] = []
        secao_map: dict[str, str] = {}  # section_id → description

        # Skip header rows (line 0 is header, lines 1-3 are sub-headers)
        for line_no, line in enumerate(lines[4:], start=4):
            if not line.strip():
                continue

            parts = line.split('\t')
            if len(parts) < 3:
                continue

            item_id = parts[0].strip()
            descricao = parts[1].strip()

            if not item_id:
                continue

            # Parse item_id structure
            id_parts = item_id.split(".")

            # Section header (e.g., "2", "3", "4")
            if len(id_parts) == 1 and item_id[0].isdigit():
                secao_map[item_id] = descricao
                continue  # Section headers are aggregates, skip detailed parsing

            # Sub-item (e.g., "2.1", "2.2")
            if len(id_parts) == 2 and item_id[0].isdigit():
                unidade = parts[2].strip() if len(parts) > 2 else ""

                # Quantity is in column 3 (4th column)
                quantitativo_str = parts[3].strip() if len(parts) > 3 else "0"
                quantitativo = _parse_valor(quantitativo_str)

                # Produção diária is in column 5 (6th column)
                producao_str = parts[5].strip() if len(parts) > 5 else "0"
                producao_diaria = _parse_valor(producao_str)

                if quantitativo > 0:
                    items.append(CronogramaItem(
                        item_id=item_id,
                        descricao=descricao,
                        unidade=unidade,
                        quantitativo=quantitativo,
                        producao_diaria=producao_diaria,
                    ))

        # Deduplicate items by item_id (keep first occurrence)
        seen_ids: set[str] = set()
        unique_items = []
        for item in items:
            if item.item_id not in seen_ids:
                unique_items.append(item)
                seen_ids.add(item.item_id)

        # Convert to EAP format with inferred predecessores
        eap_items = []
        ordem = 1

        for item in unique_items:
            cpu_id = _find_cpu_for_item(item.descricao, self.cpus_map) or "CPU-UNKNOWN"
            predecessores = _infer_predecessores(items, item.item_id, secao_map)

            eap_item = {
                "item_id": item.item_id,
                "ordem": ordem,
                "cpu_id": cpu_id,
                "descricao": item.descricao,
                "unidade": item.unidade,
                "quantitativo": item.quantitativo,
                "predecessores": predecessores,
            }
            eap_items.append(eap_item)
            ordem += 1

        return eap_items

    @staticmethod
    def load_cpus_map(cpus_path: Path) -> dict[str, str]:
        """Load CPU mapping from cpus.txt.

        Expected format: TSV with columns: CODIGO, DESCRICAO
        """
        cpus_map = {}

        if not cpus_path.exists():
            return cpus_map

        with open(cpus_path, encoding="utf-8") as f:
            reader = csv.reader(f, delimiter='\t')
            next(reader, None)  # Skip header

            for row in reader:
                if len(row) >= 2:
                    codigo = row[0].strip()
                    descricao = row[1].strip()
                    if codigo and descricao:
                        cpus_map[codigo] = descricao

        return cpus_map
