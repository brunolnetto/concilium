from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from typing import Any, Literal

from .project_files import DEFAULT_PROJECT_FILES, ProjectFiles
from .project_repository import ProjectHandle


@dataclass
class VersionAction:
    """ADR-119 D5: entrada de auditoria cross-ator para ações sobre versões."""

    action: Literal["run_pipeline", "fork", "approve", "reject", "compare"]
    version_afetada: str
    ts: str = field(default_factory=lambda: datetime.now(UTC).isoformat())
    actor_id: str = "system"
    actor_role: str | None = None
    intent: str | None = None
    detalhes: dict = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class AuditService:
    def __init__(self, files: ProjectFiles = DEFAULT_PROJECT_FILES):
        self._files = files

    def log(
        self,
        project: ProjectHandle,
        action: str,
        actor: str,
        payload: dict[str, Any] | None = None,
        result: dict[str, Any] | None = None,
        error: str | None = None,
        version_action: VersionAction | None = None,
    ) -> None:
        entry: dict[str, Any] = {
            "timestamp": datetime.now(UTC).isoformat(),
            "actor": actor,
            "action": action,
            "payload": payload or {},
            "result": result or {},
            "status": "ERRO" if error else "OK",
            "error": error,
        }
        # ADR-119 D5: inclui VersionAction quando presente
        if version_action is not None:
            entry["version_action"] = version_action.to_dict()
        project.append_jsonl(self._files.audit_log, entry)

    def log_version_action(self, project: ProjectHandle, va: VersionAction) -> None:
        """ADR-119 D5: registra VersionAction diretamente no audit trail."""
        self.log(project, action=va.action, actor=va.actor_id, version_action=va)

    def list(self, project: ProjectHandle, limit: int = 200) -> list[dict[str, Any]]:
        rows: list[dict[str, Any]] = []
        for line in project.read_lines(self._files.audit_log):
            try:
                rows.append(json.loads(line))
            except Exception:
                continue
        return rows[-limit:][::-1]
