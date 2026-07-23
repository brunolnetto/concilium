"""Coverage sweep — files with few missing lines (1-30 lines missing)."""

from __future__ import annotations

from unittest.mock import MagicMock

# ─── application/services/audit_service.py ───────────────────────────────────


class TestAuditService:
    def test_log_writes_entry(self):
        from concilium.application.services.project.audit_service import AuditService

        svc = AuditService()
        project = MagicMock()
        svc.log(project, action="run_skill", actor="eng", payload={"skill": "01"}, result={"ok": True})
        project.append_jsonl.assert_called_once()
        entry = project.append_jsonl.call_args[0][1]
        assert entry["action"] == "run_skill"
        assert entry["status"] == "OK"
        assert entry["actor"] == "eng"

    def test_log_with_error(self):
        from concilium.application.services.project.audit_service import AuditService

        svc = AuditService()
        project = MagicMock()
        svc.log(project, action="run", actor="sys", error="something failed")
        entry = project.append_jsonl.call_args[0][1]
        assert entry["status"] == "ERRO"
        assert entry["error"] == "something failed"

    def test_list_returns_entries(self):
        from concilium.application.services.project.audit_service import AuditService

        svc = AuditService()
        project = MagicMock()
        project.read_lines.return_value = [
            '{"action": "run", "actor": "eng", "timestamp": "2026-01-01"}',
            "invalid json line",
            '{"action": "save", "actor": "sys", "timestamp": "2026-01-02"}',
        ]
        result = svc.list(project)
        assert len(result) == 2
        assert result[0]["action"] == "save"  # reversed

    def test_list_respects_limit(self):
        from concilium.application.services.project.audit_service import AuditService

        svc = AuditService()
        project = MagicMock()
        project.read_lines.return_value = [f'{{"action": "a{i}", "actor": "e"}}' for i in range(10)]
        result = svc.list(project, limit=3)
        assert len(result) == 3



