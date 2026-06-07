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
    1. Items within same section (e.g., 2.1, 2.2, 2.3) depend on previous item
    2. First item of section depends on section header (e.g., 2.1 depends on 2)
    3. First item overall (section header) has no dependencies

    Returns list of predecessor dicts with keys: item_id, tipo, lag, completion_threshold_pct
    """
    parts = item_id.split(".")

    # Section header (e.g., "2") - no predecessors
    if len(parts) == 1:
        return []

    section = parts[0]
    item_num = int(parts[1]) if len(parts) > 1 else 1

    predecessores = []

    # If first item in section, depend on section header
    if item_num == 1:
        predecessores.append({
            "item_id": section,
            "tipo": "FS",
            "lag": 0,
            "completion_threshold_pct": 0.0  # Can start when section starts
        })
    else:
        # Depend on previous item in same section
        prev_item_id = f"{section}.{item_num - 1}"
        predecessores.append({
            "item_id": prev_item_id,
            "tipo": "FS",
            "lag": 0,
            "completion_threshold_pct": 1.0  # Must finish before this can start
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

        # Convert to EAP format with inferred predecessores
        eap_items = []
        ordem = 1

        for item in items:
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
