"""ProjectSpec e utilitários de semanas ISO."""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import date, timedelta
from pathlib import Path

logger = logging.getLogger(__name__)


@dataclass
class ProjectSpec:
    """Especificacao completa de um projeto para benchmark."""

    nome: str
    slug: str
    contexto_id: str = "mendeslobo"
    contexto_version: str | None = None  # ADR-062: version resolved at load time
    perfil_id: str | None = None  # ADR-062: from versioned context
    perfil_version: str | None = None  # ADR-062: version resolved at load time
    referencia_path: Path | None = None
    inputs_escopo: dict = field(default_factory=dict)
    inputs_01A: dict = field(default_factory=dict)
    inputs_cronograma: dict = field(default_factory=dict)
    inputs_indiretos: dict = field(default_factory=dict)
    extra_inputs: dict = field(default_factory=dict)


def iso_weeks(start: str, end: str) -> list[str]:
    """Gera lista de chaves ISO-week entre duas datas."""

    current = date.fromisoformat(start)
    end_date = date.fromisoformat(end)
    seen: dict[str, None] = {}
    while current <= end_date:
        iso = current.isocalendar()
        seen[f"{iso.year}-W{iso.week:02d}"] = None
        current += timedelta(weeks=1)
    return list(seen.keys())


