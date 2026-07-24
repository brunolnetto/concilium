"""Tests for OverrideService to boost coverage."""

from __future__ import annotations

from unittest.mock import MagicMock


def _make_svc():
    from concilium.application.services.project.override_service import OverrideService

    repo = MagicMock()
    audit = MagicMock()
    svc = OverrideService(repository=repo, audit_service=audit)
    return svc, repo, audit


def _make_project(data_map: dict | None = None):
    proj = MagicMock()
    proj.read_json.side_effect = lambda path, default=None: (data_map or {}).get(
        path, default if default is not None else {}
    )
    proj.write_json = MagicMock()
    return proj


class TestExtendCpu:
    def test_calls_project_extend_cpu_and_logs(self):
        svc, repo, audit = _make_svc()
        proj = _make_project()
        repo.get_project.return_value = proj
        svc.extend_cpu("proj-1", "CPU-1", {"descricao": "x"}, actor="user", motivo="test")
        proj.extend_cpu.assert_called_once_with("CPU-1", {"descricao": "x"}, actor="user", motivo="test")
        audit.log.assert_called_once()

    def test_resolve_cpu_delegates(self):
        svc, repo, _ = _make_svc()
        proj = _make_project()
        proj.resolve_cpu.return_value = {"codigo": "CPU-1"}
        repo.get_project.return_value = proj
        result = svc.resolve_cpu("proj-1", "CPU-1")
        assert result == {"codigo": "CPU-1"}


class TestCpuContexto:
    """ADR-148: contexto de projeto complementar à descrição de CPU (texto livre, sem aprovação)."""

    def test_set_cpu_contexto_writes_and_logs(self):
        svc, repo, audit = _make_svc()
        proj = _make_project()
        repo.get_project.return_value = proj
        svc.set_cpu_contexto("proj-1", "CPU-1", "Solo argiloso, acesso restrito.", actor="eng-1")
        proj.write_json.assert_called_once_with(
            "overrides/cpus_contexto.json", {"CPU-1": "Solo argiloso, acesso restrito."}
        )
        audit.log.assert_called_once()

    def test_set_cpu_contexto_preserves_other_entries(self):
        svc, repo, _ = _make_svc()
        proj = _make_project({"overrides/cpus_contexto.json": {"CPU-EXISTING": "já anotado"}})
        repo.get_project.return_value = proj
        svc.set_cpu_contexto("proj-1", "CPU-1", "novo contexto")
        written = proj.write_json.call_args.args[1]
        assert written == {"CPU-EXISTING": "já anotado", "CPU-1": "novo contexto"}

    def test_set_cpu_contexto_empty_string_removes_entry(self):
        svc, repo, _ = _make_svc()
        proj = _make_project({"overrides/cpus_contexto.json": {"CPU-1": "antigo"}})
        repo.get_project.return_value = proj
        svc.set_cpu_contexto("proj-1", "CPU-1", "")
        written = proj.write_json.call_args.args[1]
        assert "CPU-1" not in written

    def test_get_cpu_contexto_returns_stored_value(self):
        svc, repo, _ = _make_svc()
        proj = _make_project({"overrides/cpus_contexto.json": {"CPU-1": "contexto salvo"}})
        repo.get_project.return_value = proj
        assert svc.get_cpu_contexto("proj-1", "CPU-1") == "contexto salvo"

    def test_get_cpu_contexto_returns_none_when_absent(self):
        svc, repo, _ = _make_svc()
        proj = _make_project()
        repo.get_project.return_value = proj
        assert svc.get_cpu_contexto("proj-1", "CPU-1") is None

    def test_list_cpu_contextos_returns_full_dict(self):
        svc, repo, _ = _make_svc()
        stored = {"CPU-1": "a", "CPU-2": "b"}
        proj = _make_project({"overrides/cpus_contexto.json": stored})
        repo.get_project.return_value = proj
        assert svc.list_cpu_contextos("proj-1") == stored

    def test_list_cpu_contextos_empty_when_missing(self):
        svc, repo, _ = _make_svc()
        proj = _make_project()
        repo.get_project.return_value = proj
        assert svc.list_cpu_contextos("proj-1") == {}


class TestOverrides:
    def test_list_overrides_returns_data(self):
        svc, repo, _ = _make_svc()
        from concilium.application.services.project.project_files import DEFAULT_PROJECT_FILES

        proj = _make_project({DEFAULT_PROJECT_FILES.overrides: {"skill-01": {"key": "val"}}})
        repo.get_project.return_value = proj
        result = svc.list_overrides("proj-1")
        assert result.get("skill-01") == {"key": "val"}

    def test_upsert_override_merges_and_logs(self):
        svc, repo, audit = _make_svc()
        from concilium.application.services.project.project_files import DEFAULT_PROJECT_FILES

        existing = {"skill-01": {"a": 1}}
        proj = _make_project({DEFAULT_PROJECT_FILES.overrides: existing})
        repo.get_project.return_value = proj
        result = svc.upsert_override("proj-1", "skill-01", {"b": 2}, actor="user")
        assert result["skill-01"]["a"] == 1
        assert result["skill-01"]["b"] == 2
        proj.write_json.assert_called_once()
        audit.log.assert_called_once()

    def test_upsert_override_creates_new_skill(self):
        svc, repo, audit = _make_svc()
        from concilium.application.services.project.project_files import DEFAULT_PROJECT_FILES

        proj = _make_project({DEFAULT_PROJECT_FILES.overrides: {}})
        repo.get_project.return_value = proj
        result = svc.upsert_override("proj-1", "skill-02", {"x": 9})
        assert "skill-02" in result

    def test_delete_override_removes_skill(self):
        svc, repo, audit = _make_svc()
        from concilium.application.services.project.project_files import DEFAULT_PROJECT_FILES

        existing = {"skill-01": {"a": 1}, "skill-02": {"b": 2}}
        proj = _make_project({DEFAULT_PROJECT_FILES.overrides: existing})
        repo.get_project.return_value = proj
        result = svc.delete_override("proj-1", "skill-01")
        assert "skill-01" not in result
        audit.log.assert_called_once()

    def test_delete_override_missing_skill_no_error(self):
        svc, repo, _ = _make_svc()
        from concilium.application.services.project.project_files import DEFAULT_PROJECT_FILES

        proj = _make_project({DEFAULT_PROJECT_FILES.overrides: {}})
        repo.get_project.return_value = proj
        result = svc.delete_override("proj-1", "nonexistent")
        assert result == {}


class TestMobilizacaoPolicies:
    def test_get_policies_returns_stored(self):
        svc, repo, _ = _make_svc()
        from concilium.application.services.project.project_files import DEFAULT_PROJECT_FILES

        data = {"item-1": {"n_inicial": 1}}
        proj = _make_project({DEFAULT_PROJECT_FILES.mobilizacao_policies: data})
        repo.get_project.return_value = proj
        result = svc.get_mobilizacao_policies("proj-1")
        assert result == data

    def test_upsert_policy_writes_and_logs(self):
        svc, repo, audit = _make_svc()
        from concilium.application.services.project.project_files import DEFAULT_PROJECT_FILES

        proj = _make_project({DEFAULT_PROJECT_FILES.mobilizacao_policies: {}})
        repo.get_project.return_value = proj
        svc.upsert_mobilizacao_policy("proj-1", "item-1", {"n_inicial": 2})
        proj.write_json.assert_called_once()
        audit.log.assert_called_once()

    def test_delete_policy_removes_item(self):
        svc, repo, audit = _make_svc()
        from concilium.application.services.project.project_files import DEFAULT_PROJECT_FILES

        data = {"item-1": {"n_inicial": 1}, "item-2": {"n_inicial": 2}}
        proj = _make_project({DEFAULT_PROJECT_FILES.mobilizacao_policies: data})
        repo.get_project.return_value = proj
        svc.delete_mobilizacao_policy("proj-1", "item-1")
        # Check write was called with item-1 removed
        written = proj.write_json.call_args[0][1]
        assert "item-1" not in written
        assert "item-2" in written
        audit.log.assert_called_once()

    def test_delete_policy_missing_no_error(self):
        svc, repo, _ = _make_svc()
        from concilium.application.services.project.project_files import DEFAULT_PROJECT_FILES

        proj = _make_project({DEFAULT_PROJECT_FILES.mobilizacao_policies: {}})
        repo.get_project.return_value = proj
        svc.delete_mobilizacao_policy("proj-1", "nonexistent")  # no error


class TestDeliverablesConfig:
    def test_get_deliverables_config_returns_stored(self):
        svc, repo, _ = _make_svc()
        from concilium.application.services.project.project_files import DEFAULT_PROJECT_FILES

        stored = {"key1": True}
        proj = _make_project({DEFAULT_PROJECT_FILES.deliverables_config: stored})
        repo.get_project.return_value = proj
        result = svc.get_deliverables_config("proj-1")
        assert result == stored

    def test_get_deliverables_config_returns_default_when_empty(self):
        svc, repo, _ = _make_svc()
        from concilium.application.services.project.project_files import DEFAULT_DELIVERABLES, DEFAULT_PROJECT_FILES

        proj = _make_project({DEFAULT_PROJECT_FILES.deliverables_config: {}})
        repo.get_project.return_value = proj
        result = svc.get_deliverables_config("proj-1")
        assert result == dict(DEFAULT_DELIVERABLES)

    def test_put_deliverables_config_writes_and_logs(self):
        svc, repo, audit = _make_svc()
        proj = _make_project()
        repo.get_project.return_value = proj
        config = {"report": True, "excel": False}
        result = svc.put_deliverables_config("proj-1", config, actor="admin")
        assert result == config
        proj.write_json.assert_called_once()
        audit.log.assert_called_once()
