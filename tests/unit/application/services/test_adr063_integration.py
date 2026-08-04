"""ADR-063 §F6: Integration test — 'project' type with 3 items and linear predecessão.

Validates the full create → upsert_eap → status_eap → strategy dispatch chain.
"""

from __future__ import annotations

import pytest

from concilium.application.pipeline_strategy import ProjectStrategy, get_pipeline_strategy
from concilium.application.services.project.audit_service import AuditService
from concilium.application.services.project.project_service import ProjectService
from concilium.infrastructure.storage.store_factory import build_project_repository


@pytest.fixture
def repo(tmp_path):
    root = tmp_path / "projetos"
    root.mkdir()
    return build_project_repository(root)


@pytest.fixture
def svc(repo):
    return ProjectService(repo, AuditService())


# ─── F6 DoD: project com 3 itens e predecessão linear ────────────────────────


class TestProjectTypeIntegration:
    def test_new_project_has_tipo_project_and_rascunho(self, repo):
        """Project without benchmark → tipo_projeto=project, status_eap=RASCUNHO."""
        project = repo.create_project("Proj Teste", "mendeslobo")
        project.update_meta(tipo_projeto="project", status_eap="RASCUNHO")

        assert project.tipo_projeto == "project"
        assert project.status_eap == "RASCUNHO"

    def test_hot_project_backward_compat(self, repo):
        """Legacy projects with only project_kind field still resolve correctly."""
        project = repo.create_project("Proj Legacy", "mendeslobo")
        project.update_meta(project_kind="hot_project")
        # status_eap absent → defaults to ATIVO
        assert project.tipo_projeto == "hot_project"
        assert project.status_eap == "ATIVO"

    def test_upsert_eap_linear_chain_becomes_rascunho_pronto(self, svc, repo):
        """3 items with A→B→C predecessão → upsert resolves status RASCUNHO_PRONTO."""
        project = repo.create_project("Construção Linear", "mendeslobo")
        project.new_version()
        project.update_meta(tipo_projeto="project", status_eap="RASCUNHO")
        pid = project.meta["id"]

        eap_items = [
            {
                "item_id": "A",
                "ordem": 1,
                "descricao": "Terraplenagem",
                "cpu_id": "ESCO-1CAT",
                "unidade": "m³",
                "quantitativo": 1000.0,
                "predecessores": [],
            },
            {
                "item_id": "B",
                "ordem": 2,
                "descricao": "Compactação",
                "cpu_id": "COMPACT-ATERRO",
                "unidade": "m³",
                "quantitativo": 1000.0,
                "predecessores": ["A"],
            },
            {
                "item_id": "C",
                "ordem": 3,
                "descricao": "Regularização",
                "cpu_id": "REGULARIZACAO",
                "unidade": "m²",
                "quantitativo": 500.0,
                "predecessores": ["B"],
            },
        ]

        result = svc.upsert_eap(pid, eap_items, actor="test")

        assert result["status_eap"] == "RASCUNHO_PRONTO"
        assert result["count"] == 3

        # Verify persisted
        stored = svc.get_eap(pid)
        assert stored["status_eap"] == "RASCUNHO_PRONTO"
        assert len(stored["items"]) == 3
        # Check predecessão preserved
        item_b = next(it for it in stored["items"] if it["item_id"] == "B")
        assert item_b["predecessores"] == ["A"]

    def test_upsert_eap_missing_cpu_stays_rascunho(self, svc, repo):
        """Items without cpu_id → status stays RASCUNHO."""
        project = repo.create_project("Proj Incompleto", "mendeslobo")
        project.new_version()
        project.update_meta(tipo_projeto="project", status_eap="RASCUNHO")
        pid = project.meta["id"]

        eap_items = [
            {
                "item_id": "X",
                "ordem": 1,
                "descricao": "Sem CPU",
                "cpu_id": "",
                "unidade": "m³",
                "quantitativo": 100.0,
                "predecessores": [],
            },
        ]
        result = svc.upsert_eap(pid, eap_items, actor="test")
        assert result["status_eap"] == "RASCUNHO"

    def test_upsert_eap_rejects_cycle(self, svc, repo):
        """Cyclic predecessão → raises ValueError."""
        project = repo.create_project("Proj Ciclo", "mendeslobo")
        project.new_version()
        project.update_meta(tipo_projeto="project", status_eap="RASCUNHO")
        pid = project.meta["id"]

        cyclic_eap = [
            {
                "item_id": "A",
                "ordem": 1,
                "cpu_id": "CPU-A",
                "descricao": "A",
                "unidade": "m³",
                "quantitativo": 1.0,
                "predecessores": ["B"],
            },
            {
                "item_id": "B",
                "ordem": 2,
                "cpu_id": "CPU-B",
                "descricao": "B",
                "unidade": "m³",
                "quantitativo": 1.0,
                "predecessores": ["A"],
            },
        ]
        with pytest.raises(ValueError):
            svc.upsert_eap(pid, cyclic_eap, actor="test")

    def test_upsert_eap_rejected_for_hot_project(self, svc, repo):
        """upsert_eap raises ValueError for hot_project type."""
        project = repo.create_project("Proj HOT", "mendeslobo")
        project.new_version()
        project.update_meta(tipo_projeto="hot_project", status_eap="ATIVO")
        pid = project.meta["id"]

        with pytest.raises(ValueError, match="hot_project"):
            svc.upsert_eap(pid, [], actor="test")

    def test_strategy_blocks_pipeline_when_rascunho(self, repo):
        """ProjectStrategy.validate_preconditions raises when status_eap=RASCUNHO."""
        project = repo.create_project("Proj Bloqueado", "mendeslobo")
        project.update_meta(tipo_projeto="project", status_eap="RASCUNHO")

        strategy = get_pipeline_strategy(project)
        assert isinstance(strategy, ProjectStrategy)

        with pytest.raises(ValueError, match="RASCUNHO_PRONTO"):
            strategy.validate_preconditions(project)

    def test_strategy_allows_pipeline_after_eap_ready(self, repo):
        """ProjectStrategy passes when status_eap=RASCUNHO_PRONTO."""
        project = repo.create_project("Proj Pronto", "mendeslobo")
        project.update_meta(tipo_projeto="project", status_eap="RASCUNHO_PRONTO")

        strategy = get_pipeline_strategy(project)
        strategy.validate_preconditions(project)  # must not raise
