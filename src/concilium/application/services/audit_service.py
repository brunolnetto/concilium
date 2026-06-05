from __future__ import annotations

import json
from datetime import UTC, datetime
from typing import Any

from .project_files import DEFAULT_PROJECT_FILES, ProjectFiles
from .project_repository import ProjectHandle


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
    ) -> None:
        entry = {
            "timestamp": datetime.now(UTC).isoformat(),
            "actor": actor,
            "action": action,
            "payload": payload or {},
            "result": result or {},
            "status": "ERRO" if error else "OK",
            "error": error,
        }
        project.append_jsonl(self._files.audit_log, entry)

    def list(self, project: ProjectHandle, limit: int = 200) -> list[dict[str, Any]]:
        rows: list[dict[str, Any]] = []
        for line in project.read_lines(self._files.audit_log):
            try:
                rows.append(json.loads(line))
            except Exception:
                continue
        return rows[-limit:][::-1]
