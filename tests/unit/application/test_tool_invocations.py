"""Testes de ADR-119 — Gestão Multi-Ator de Projetos.

Cobre:
  F1: ROLE_ALLOWED_INTENTS + check_intent_allowed
  F2: VersionMeta estendido (criado_por, role_criador, procurement_intent, forked_from)
  F5: VersionAction dataclass
"""

from __future__ import annotations

import json
import pytest


# ── F1: ROLE_ALLOWED_INTENTS ──────────────────────────────────────────────────


class TestRoleAllowedIntents:
    def test_operator_allows_only_rfi(self):
        from concilium.infrastructure.auth.permission_guard import ROLE_ALLOWED_INTENTS
        assert "rfi" in ROLE_ALLOWED_INTENTS["operator"]
        assert "rfp" not in ROLE_ALLOWED_INTENTS["operator"]

    def test_engineer_allows_rfi_and_rfp(self):
        from concilium.infrastructure.auth.permission_guard import ROLE_ALLOWED_INTENTS
        assert "rfi" in ROLE_ALLOWED_INTENTS["engineer"]
        assert "rfp" in ROLE_ALLOWED_INTENTS["engineer"]

    def test_admin_allows_rfi_and_rfp(self):
        from concilium.infrastructure.auth.permission_guard import ROLE_ALLOWED_INTENTS
        assert ROLE_ALLOWED_INTENTS["admin"] == frozenset({"rfi", "rfp"})

    def test_service_ci_allows_only_rfi(self):
        from concilium.infrastructure.auth.permission_guard import ROLE_ALLOWED_INTENTS
        assert ROLE_ALLOWED_INTENTS["service-ci"] == frozenset({"rfi"})

    def test_viewer_and_auditor_allow_nothing(self):
        from concilium.infrastructure.auth.permission_guard import ROLE_ALLOWED_INTENTS
        assert ROLE_ALLOWED_INTENTS["viewer"] == frozenset()
        assert ROLE_ALLOWED_INTENTS["auditor"] == frozenset()


class TestCheckIntentAllowed:
    def test_no_auth_always_passes(self, monkeypatch):
        from concilium.infrastructure.auth.permission_guard import check_intent_allowed
        monkeypatch.setattr("concilium.infrastructure.auth.permission_guard._auth_enabled", lambda: False)
        check_intent_allowed("rfp", ["operator"])  # would fail with auth

    def test_none_intent_always_passes(self, monkeypatch):
        from concilium.infrastructure.auth.permission_guard import check_intent_allowed
        monkeypatch.setattr("concilium.infrastructure.auth.permission_guard._auth_enabled", lambda: True)
        check_intent_allowed(None, ["viewer"])  # no intent = no check

    def test_operator_rfp_raises(self, monkeypatch):
        from concilium.infrastructure.auth.permission_guard import check_intent_allowed
        monkeypatch.setattr("concilium.infrastructure.auth.permission_guard._auth_enabled", lambda: True)
        with pytest.raises(PermissionError, match="rfp"):
            check_intent_allowed("rfp", ["operator"])

    def test_operator_rfi_passes(self, monkeypatch):
        from concilium.infrastructure.auth.permission_guard import check_intent_allowed
        monkeypatch.setattr("concilium.infrastructure.auth.permission_guard._auth_enabled", lambda: True)
        check_intent_allowed("rfi", ["operator"])  # should not raise

    def test_engineer_rfp_passes(self, monkeypatch):
        from concilium.infrastructure.auth.permission_guard import check_intent_allowed
        monkeypatch.setattr("concilium.infrastructure.auth.permission_guard._auth_enabled", lambda: True)
        check_intent_allowed("rfp", ["engineer"])  # should not raise

    def test_service_ci_rfp_raises(self, monkeypatch):
        from concilium.infrastructure.auth.permission_guard import check_intent_allowed
        monkeypatch.setattr("concilium.infrastructure.auth.permission_guard._auth_enabled", lambda: True)
        with pytest.raises(PermissionError):
            check_intent_allowed("rfp", ["service-ci"])

    def test_error_message_suggests_correct_role(self, monkeypatch):
        from concilium.infrastructure.auth.permission_guard import check_intent_allowed
        monkeypatch.setattr("concilium.infrastructure.auth.permission_guard._auth_enabled", lambda: True)
        with pytest.raises(PermissionError) as exc_info:
            check_intent_allowed("rfp", ["operator"])
        assert "rfp" in str(exc_info.value)
        assert "operator" in str(exc_info.value).lower()


# ── F2: VersionMeta estendido ─────────────────────────────────────────────────


class TestVersionMetaExtension:
    def test_new_version_stores_criado_por(self, tmp_path):
        from concilium.infrastructure.storage.project import ProjectStore
        store = ProjectStore.init(tmp_path, "TestProj", "test")
        store.new_version(criado_por="joao.silva", role_criador="operator", procurement_intent="rfi")
        v = store.current_version()
        meta = store.get_version_meta(v)
        assert meta["criado_por"] == "joao.silva"
        assert meta["role_criador"] == "operator"
        assert meta["procurement_intent"] == "rfi"

    def test_new_version_stores_forked_from(self, tmp_path):
        from concilium.infrastructure.storage.project import ProjectStore
        store = ProjectStore.init(tmp_path, "TestProj", "test")
        store.new_version()  # v1
        store.new_version(forked_from="v1", criado_por="maria.santos", procurement_intent="rfp")
        v2 = store.current_version()
        meta = store.get_version_meta(v2)
        assert meta["forked_from"] == "v1"
        assert meta["criado_por"] == "maria.santos"
        assert meta["procurement_intent"] == "rfp"

    def test_missing_version_returns_empty_dict(self, tmp_path):
        from concilium.infrastructure.storage.project import ProjectStore
        store = ProjectStore.init(tmp_path, "TestProj", "test")
        assert store.get_version_meta("v99") == {}

    def test_version_history_persists_across_instances(self, tmp_path):
        from concilium.infrastructure.storage.project import ProjectStore
        store = ProjectStore.init(tmp_path, "TestProj", "test")
        store.new_version(criado_por="actor-x", procurement_intent="rfi")
        # re-open
        store2 = ProjectStore(store.root)
        v = store2.current_version()
        assert store2.get_version_meta(v)["criado_por"] == "actor-x"

    def test_none_fields_stored_gracefully(self, tmp_path):
        from concilium.infrastructure.storage.project import ProjectStore
        store = ProjectStore.init(tmp_path, "TestProj", "test")
        store.new_version()  # all None
        meta = store.get_version_meta(store.current_version())
        assert meta.get("criado_por") is None
        assert meta.get("procurement_intent") is None


# ── F5: VersionAction ─────────────────────────────────────────────────────────


class TestVersionAction:
    def test_version_action_fields(self):
        from concilium.application.services.project.audit_service import VersionAction
        va = VersionAction(
            action="fork",
            version_afetada="v2",
            actor_id="joao.silva",
            actor_role="operator",
            intent="rfi",
            detalhes={"forked_from": "v1"},
        )
        assert va.action == "fork"
        assert va.version_afetada == "v2"
        assert va.actor_id == "joao.silva"
        assert va.intent == "rfi"

    def test_version_action_to_dict(self):
        from concilium.application.services.project.audit_service import VersionAction
        va = VersionAction(action="approve", version_afetada="v1", actor_id="admin")
        d = va.to_dict()
        assert d["action"] == "approve"
        assert d["version_afetada"] == "v1"
        assert "ts" in d

    def test_audit_service_log_version_action(self, tmp_path):
        from concilium.application.services.project.audit_service import AuditService, VersionAction
        from concilium.infrastructure.storage.file_project_repository import FileProjectRepository
        repo = FileProjectRepository(tmp_path)
        handle = repo.create_project("TestProj", "test")
        svc = AuditService()
        va = VersionAction(action="approve", version_afetada="v1", actor_id="engineer-x")
        svc.log_version_action(handle, va)
        entries = svc.list(handle)
        assert len(entries) >= 1
        last = entries[0]
        assert last["action"] == "approve"
        assert last["version_action"]["actor_id"] == "engineer-x"


# ── F3: Fork com rastreamento ─────────────────────────────────────────────────


class TestForkVersionTracking:
    def _make_service_and_project(self, tmp_path):
        from concilium.application.services.project.audit_service import AuditService
        from concilium.application.services.project.project_files import DEFAULT_PROJECT_FILES
        from concilium.application.services.project.project_service import ProjectService
        from concilium.infrastructure.storage.file_project_repository import FileProjectRepository
        repo = FileProjectRepository(tmp_path)
        handle = repo.create_project("TestProj", "test")
        svc = ProjectService(repo, AuditService(), DEFAULT_PROJECT_FILES)
        return svc, handle

    def test_fork_stores_forked_from(self, tmp_path):
        from concilium.infrastructure.storage.project import ProjectStore
        svc, handle = self._make_service_and_project(tmp_path)
        project_id = handle.meta.get("id")
        # Create initial version with authorship
        store = ProjectStore(handle.root)
        store.new_version(criado_por="joao", procurement_intent="rfi")

        result = svc.fork_version(project_id, "v1", actor="maria")

        store2 = ProjectStore(handle.root)
        v2_meta = store2.get_version_meta(result["forked_version"])
        assert v2_meta["forked_from"] == "v1"

    def test_fork_inherits_intent(self, tmp_path):
        from concilium.infrastructure.storage.project import ProjectStore
        svc, handle = self._make_service_and_project(tmp_path)
        project_id = handle.meta.get("id")
        store = ProjectStore(handle.root)
        store.new_version(criado_por="joao", procurement_intent="rfp")

        result = svc.fork_version(project_id, "v1", actor="maria")

        store2 = ProjectStore(handle.root)
        v2_meta = store2.get_version_meta(result["forked_version"])
        assert v2_meta["procurement_intent"] == "rfp"
