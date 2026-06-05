"""Persistência append-only de ResolutionDecision — ADR-002.

Armazena como JSONL (consistente com invocations.log existente).
Nunca sobrescreve. Nunca deleta.

Regra de falha: resolve() deve FALHAR se persist() falhar.
Não existe "best effort logging".
"""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Any

from concilium.application.resolution.models import ResolutionDecision


def _default_json(obj: Any) -> Any:
    if isinstance(obj, datetime):
        return obj.isoformat()
    if hasattr(obj, "__dataclass_fields__"):
        import dataclasses

        return dataclasses.asdict(obj)
    raise TypeError(f"Object of type {type(obj).__name__} is not JSON serializable")


class ResolutionDecisionStore:
    """Persistência append-only de ResolutionDecision.

    Cada linha do arquivo JSONL é uma ResolutionDecision serializada.
    Operações suportadas: persist (append), load (query).

    Regra: API resolve_and_persist() deve FALHAR se persist() falhar.
    """

    def __init__(self, store_path: Path) -> None:
        self._path = store_path
        self._path.parent.mkdir(parents=True, exist_ok=True)

    def persist(self, decision: ResolutionDecision) -> None:
        """Persiste uma decisão. Falha explicitamente se não conseguir.

        Raises:
            IOError: se não conseguir escrever no arquivo.
        """
        line = json.dumps(
            decision.model_dump(mode="json"),
            ensure_ascii=False,
            default=_default_json,
        )
        with self._path.open("a", encoding="utf-8") as f:
            f.write(line + "\n")

    def load_all(self) -> list[ResolutionDecision]:
        """Carrega todas as decisões do store."""
        if not self._path.exists():
            return []
        decisions: list[ResolutionDecision] = []
        with self._path.open("r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    data = json.loads(line)
                    decisions.append(ResolutionDecision.model_validate(data))
                except Exception:
                    pass  # linhas corrompidas não quebram o carregamento
        return decisions

    def load_for_scope_item(self, scope_item_id: str) -> list[ResolutionDecision]:
        """Retorna todas as decisões para um scope_item, em ordem cronológica."""
        return [d for d in self.load_all() if d.scope_item_id == scope_item_id]

    def load_recent_for_activity_type(self, activity_type: str, limit: int = 50) -> list[ResolutionDecision]:
        """Decisões recentes por activity_type — para historical_prior."""
        matching = [d for d in self.load_all() if d.intent_snapshot.activity_type == activity_type]
        # Ordenar por created_at desc, retornar limit mais recentes
        matching.sort(key=lambda d: d.created_at, reverse=True)
        return matching[:limit]

    def load_for_project(self, project_id: str) -> list[ResolutionDecision]:
        """Todas as decisões que contêm project_id no scope_item_id."""
        return [d for d in self.load_all() if project_id in d.scope_item_id]

    def count(self) -> int:
        """Número total de decisões persistidas."""
        return len(self.load_all())


__all__ = ["ResolutionDecisionStore"]
