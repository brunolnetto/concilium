"""Tests for _pii_sweep — direito de ser esquecido (LGPD Art. 18), Fase 3.

Varredura de client_id em audit trails de projeto (audit_log.jsonl, meta.json)
e de catálogo (arquivos de versão), trocando por um alias opaco.
"""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from concilium.application.services.project._ownership_helpers import (
    create_ownership_transfer_pending,
)
from concilium.application.services.project._pii_sweep import (
    _replace_value,
    sweep_all_projects,
    sweep_catalog_version_files,
    sweep_project,
)
from concilium.application.services.project.audit_service import (
    AuditService,
    OwnershipTransferAction,
    VersionAction,
)
from concilium.infrastructure.storage.file_project_repository import FileProjectRepository


@pytest.fixture
def repo(tmp_path):
    return FileProjectRepository(tmp_path / "projetos")


@pytest.fixture
def audit():
    return AuditService()


def _make_project(repo, owner_id="joao.silva"):
    project = repo.create_project("Projeto Teste", "mendeslobo")
    project.update_meta(owner_id=owner_id, owner_assigned_at=datetime.now(UTC).isoformat())
    return project


# ---------------------------------------------------------------------------
# _replace_value — substituição recursiva genérica
# ---------------------------------------------------------------------------


class TestReplaceValue:
    def test_replaces_matching_top_level_string(self):
        result, n = _replace_value({"actor": "carla", "action": "run"}, "carla", "alias-1")
        assert result == {"actor": "alias-1", "action": "run"}
        assert n == 1

    def test_replaces_nested_dict_values(self):
        obj = {"ownership_action": {"actor_id": "carla", "owner_anterior": "carla", "owner_proposto_ou_novo": "maria"}}
        result, n = _replace_value(obj, "carla", "alias-1")
        assert result == {
            "ownership_action": {"actor_id": "alias-1", "owner_anterior": "alias-1", "owner_proposto_ou_novo": "maria"}
        }
        assert n == 2

    def test_replaces_inside_lists(self):
        result, n = _replace_value({"history": ["carla", "maria", "carla"]}, "carla", "alias-1")
        assert result == {"history": ["alias-1", "maria", "alias-1"]}
        assert n == 2

    def test_no_match_returns_unchanged_and_zero(self):
        obj = {"actor": "maria", "n": 3, "flag": True, "nested": {"x": None}}
        result, n = _replace_value(obj, "carla", "alias-1")
        assert result == obj
        assert n == 0

    def test_non_string_values_never_match(self):
        # "carla" nunca é igual a valores não-string (int/bool/None) — sem falso positivo.
        result, n = _replace_value({"a": 1, "b": True, "c": None}, "carla", "alias-1")
        assert result == {"a": 1, "b": True, "c": None}
        assert n == 0


# ---------------------------------------------------------------------------
# sweep_project — audit_log.jsonl
# ---------------------------------------------------------------------------


class TestSweepAuditLog:
    def test_anonymizes_actor_in_generic_audit_entries(self, repo, audit):
        project = _make_project(repo)
        audit.log(project, action="upsert_override", actor="carla", payload={"skill_id": "x"})
        audit.log(project, action="upsert_override", actor="maria", payload={"skill_id": "y"})

        stats = sweep_project(project, "carla", "alias-1")

        assert stats["audit_log_entries"] == 1
        entries = audit.list(project)
        actors = {e["actor"] for e in entries}
        assert actors == {"alias-1", "maria"}

    def test_anonymizes_version_action_actor_id(self, repo, audit):
        project = _make_project(repo)
        va = VersionAction(action="approve", version_afetada="v1", actor_id="carla")
        audit.log_version_action(project, va)

        stats = sweep_project(project, "carla", "alias-1")

        assert stats["audit_log_entries"] == 1
        entry = audit.list(project)[0]
        assert entry["version_action"]["actor_id"] == "alias-1"

    def test_anonymizes_ownership_action_all_three_fields(self, repo, audit):
        project = _make_project(repo)
        oa = OwnershipTransferAction(
            action="transfer_forced",
            project_id="p1",
            actor_id="carla",
            owner_anterior="carla",
            owner_proposto_ou_novo="carla",
        )
        audit.log_ownership_transfer_action(project, oa)

        stats = sweep_project(project, "carla", "alias-1")

        assert stats["audit_log_entries"] == 1
        entry = audit.list(project)[0]
        oa_out = entry["ownership_action"]
        assert oa_out["actor_id"] == "alias-1"
        assert oa_out["owner_anterior"] == "alias-1"
        assert oa_out["owner_proposto_ou_novo"] == "alias-1"

    def test_no_matching_entries_leaves_file_untouched(self, repo, audit):
        project = _make_project(repo)
        audit.log(project, action="upsert_override", actor="maria")

        stats = sweep_project(project, "carla", "alias-1")

        assert stats["audit_log_entries"] == 0
        assert audit.list(project)[0]["actor"] == "maria"

    def test_no_audit_log_file_returns_zero(self, repo):
        project = _make_project(repo)
        stats = sweep_project(project, "carla", "alias-1")
        assert stats["audit_log_entries"] == 0

    def test_malformed_line_preserved_others_still_anonymized(self, repo, audit):
        project = _make_project(repo)
        audit.log(project, action="upsert_override", actor="carla")
        # injeta uma linha ilegível diretamente no arquivo
        from concilium.application.services.project.project_files import DEFAULT_PROJECT_FILES

        lines = project.read_lines(DEFAULT_PROJECT_FILES.audit_log)
        project.write_lines(DEFAULT_PROJECT_FILES.audit_log, [*lines, "NOT_JSON"])

        stats = sweep_project(project, "carla", "alias-1")

        assert stats["audit_log_entries"] == 1
        raw_lines = project.read_lines(DEFAULT_PROJECT_FILES.audit_log)
        assert "NOT_JSON" in raw_lines


# ---------------------------------------------------------------------------
# sweep_project — meta.json
# ---------------------------------------------------------------------------


class TestSweepMeta:
    def test_anonymizes_owner_id(self, repo):
        project = _make_project(repo, owner_id="carla")

        stats = sweep_project(project, "carla", "alias-1")

        assert stats["meta_fields"] >= 1
        reloaded = repo.get_project(project.meta["id"])
        assert reloaded.meta["owner_id"] == "alias-1"

    def test_owner_id_not_matching_is_untouched(self, repo):
        project = _make_project(repo, owner_id="maria")

        sweep_project(project, "carla", "alias-1")

        reloaded = repo.get_project(project.meta["id"])
        assert reloaded.meta["owner_id"] == "maria"

    def test_anonymizes_version_history_criado_por(self, repo):
        project = _make_project(repo, owner_id="maria")
        project.new_version(criado_por="carla", role_criador="engineer")

        stats = sweep_project(project, "carla", "alias-1")

        assert stats["meta_fields"] >= 1
        reloaded = repo.get_project(project.meta["id"])
        vh = reloaded.meta["version_history"]
        entry = next(iter(vh.values()))
        assert entry["criado_por"] == "alias-1"
        assert entry["role_criador"] == "engineer"  # role não é PII, preservado

    def test_anonymizes_ownership_transfer_pending(self, repo, audit):
        project = _make_project(repo, owner_id="carla")
        create_ownership_transfer_pending(project, owner_proposto="carla", actor="carla", audit=audit)

        stats = sweep_project(project, "carla", "alias-1")

        assert stats["meta_fields"] >= 1
        reloaded = repo.get_project(project.meta["id"])
        pending = reloaded.meta["ownership_transfer_pending"]
        assert pending["owner_atual"] == "alias-1"
        assert pending["owner_proposto"] == "alias-1"

    def test_legacy_project_without_owner_id_untouched(self, repo):
        project = repo.create_project("Legado", "mendeslobo")
        stats = sweep_project(project, "carla", "alias-1")
        assert stats["meta_fields"] == 0


# ---------------------------------------------------------------------------
# sweep_all_projects
# ---------------------------------------------------------------------------


class TestSweepAllProjects:
    def test_aggregates_across_multiple_projects(self, repo, audit):
        p1 = _make_project(repo, owner_id="carla")
        p2 = _make_project(repo, owner_id="maria")
        audit.log(p1, action="x", actor="carla")
        audit.log(p2, action="y", actor="maria")

        totals = sweep_all_projects(repo, "carla", "alias-1")

        assert totals["projects_scanned"] == 2
        assert totals["projects_affected"] == 1
        assert totals["audit_log_entries"] == 1
        assert totals["meta_fields"] >= 1

    def test_no_projects_returns_zeroed_totals(self, repo):
        totals = sweep_all_projects(repo, "carla", "alias-1")
        assert totals == {
            "projects_scanned": 0,
            "projects_affected": 0,
            "audit_log_entries": 0,
            "meta_fields": 0,
        }

    def test_no_client_id_anywhere_affects_zero_projects(self, repo):
        _make_project(repo, owner_id="maria")
        totals = sweep_all_projects(repo, "carla", "alias-1")
        assert totals["projects_scanned"] == 1
        assert totals["projects_affected"] == 0


# ---------------------------------------------------------------------------
# sweep_catalog_version_files
# ---------------------------------------------------------------------------


class TestSweepCatalogVersionFiles:
    def test_anonymizes_created_by_in_context_version_file(self, tmp_path):
        vfile = tmp_path / "contextos" / "mendeslobo" / "versions" / "v1.json"
        vfile.parent.mkdir(parents=True)
        vfile.write_text('{"created_by": "carla", "motivo": "reajuste"}', encoding="utf-8")

        affected = sweep_catalog_version_files(tmp_path, "carla", "alias-1")

        assert affected == 1
        import json

        data = json.loads(vfile.read_text(encoding="utf-8"))
        assert data["created_by"] == "alias-1"
        assert data["motivo"] == "reajuste"

    def test_anonymizes_rejeitado_por_in_rascunho_file(self, tmp_path):
        """Rascunhos rejeitados (ADR-120) usam o mesmo path — coberto pela mesma varredura

        genérica sem precisar hardcodar o nome do campo `_rejeitado_por`."""
        vfile = tmp_path / "contextos" / "mendeslobo" / "versions" / "v5.json"
        vfile.parent.mkdir(parents=True)
        vfile.write_text('{"created_by": "maria", "_rejeitado_por": "carla"}', encoding="utf-8")

        affected = sweep_catalog_version_files(tmp_path, "carla", "alias-1")

        assert affected == 1
        import json

        data = json.loads(vfile.read_text(encoding="utf-8"))
        assert data["created_by"] == "maria"
        assert data["_rejeitado_por"] == "alias-1"

    def test_covers_perfis_temas_jurisdicoes_via_same_glob(self, tmp_path):
        for subdir in ("contextos", "perfis", "temas", "jurisdicoes"):
            vfile = tmp_path / subdir / "e1" / "versions" / "v1.json"
            vfile.parent.mkdir(parents=True)
            vfile.write_text('{"created_by": "carla"}', encoding="utf-8")

        affected = sweep_catalog_version_files(tmp_path, "carla", "alias-1")

        assert affected == 4

    def test_no_match_leaves_files_untouched(self, tmp_path):
        vfile = tmp_path / "contextos" / "mendeslobo" / "versions" / "v1.json"
        vfile.parent.mkdir(parents=True)
        original = '{"created_by": "maria"}'
        vfile.write_text(original, encoding="utf-8")

        affected = sweep_catalog_version_files(tmp_path, "carla", "alias-1")

        assert affected == 0
        assert vfile.read_text(encoding="utf-8") == original

    def test_malformed_json_file_skipped_without_crashing(self, tmp_path):
        good = tmp_path / "contextos" / "a" / "versions" / "v1.json"
        good.parent.mkdir(parents=True)
        good.write_text('{"created_by": "carla"}', encoding="utf-8")
        bad = tmp_path / "contextos" / "b" / "versions" / "v1.json"
        bad.parent.mkdir(parents=True)
        bad.write_text("NOT VALID JSON", encoding="utf-8")

        affected = sweep_catalog_version_files(tmp_path, "carla", "alias-1")

        assert affected == 1  # só o bom foi contado; o malformado não travou a varredura

    def test_no_versions_directories_returns_zero(self, tmp_path):
        assert sweep_catalog_version_files(tmp_path, "carla", "alias-1") == 0
