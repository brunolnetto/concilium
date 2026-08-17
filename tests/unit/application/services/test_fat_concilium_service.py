"""Fat coverage tests for ConciliumService.

Goal: exercise as many lines as possible by mocking ConciliumDependencies at the
boundary so that the real service method logic runs.

Each test covers one complete execution path (happy path or specific error path).
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from concilium.application.services.concilium_service import (
    ConciliumService,
)

# ─── helpers ──────────────────────────────────────────────────────────────────


def _make_svc(config_root: Path | None = None):
    """Return (service, deps_mock). config_root wires the input_builder stub."""
    deps = MagicMock()
    if config_root is not None:
        deps.input_builder._config_root = config_root
    else:
        deps.input_builder._config_root = Path("/nonexistent_fake_root_abc123")
    # ADR-149: resolve_cpu chama get_cpu_contexto — default "sem contexto" para não poluir
    # asserts de igualdade exata nos testes que não exercitam esse caminho especificamente.
    deps.override_service.get_cpu_contexto.return_value = None
    svc = ConciliumService(dependencies=deps)
    return svc, deps


def _make_project_mock(meta: dict | None = None, current_version: str = "v1") -> MagicMock:
    p = MagicMock()
    p.meta = meta or {}
    p.current_version.return_value = current_version
    return p


# ─── list_catalogs ────────────────────────────────────────────────────────────


class TestListCatalogs:
    def test_returns_sorted_catalog_ids(self, tmp_path):
        cats = tmp_path / "catalogos"
        (cats / "mendeslobo").mkdir(parents=True)
        (cats / "alpha").mkdir(parents=True)
        # hidden dir should be excluded
        (cats / ".hidden").mkdir(parents=True)
        svc, _ = _make_svc(tmp_path)
        result = svc.list_catalogs()
        assert result == [{"id": "alpha"}, {"id": "mendeslobo"}]

    def test_returns_empty_when_catalogos_dir_missing(self, tmp_path):
        svc, _ = _make_svc(tmp_path)
        assert svc.list_catalogs() == []

    def test_excludes_files_returns_only_dirs(self, tmp_path):
        cats = tmp_path / "catalogos"
        cats.mkdir()
        (cats / "real-cat").mkdir()
        (cats / "README.txt").write_text("ignore me")
        svc, _ = _make_svc(tmp_path)
        result = svc.list_catalogs()
        assert result == [{"id": "real-cat"}]


# ─── get_catalog ─────────────────────────────────────────────────────────────


class TestGetCatalog:
    def test_returns_catalog_stats(self, tmp_path):
        svc, _ = _make_svc(tmp_path)
        fake_cat = {
            "cpus": [1, 2, 3],
            "insumos": [1],
            "producoes": [1, 2],
        }
        with patch("concilium.application.services.concilium_service._catalog.Runtime") as MockRT:
            MockRT.return_value.load_catalogo.return_value = fake_cat
            result = svc.get_catalog("test-cat")

        assert result == {
            "id": "test-cat",
            "n_cpus": 3,
            "n_insumos": 1,
            "n_producoes": 2,
        }
        MockRT.assert_called_once_with(tmp_path)

    def test_empty_catalog(self, tmp_path):
        svc, _ = _make_svc(tmp_path)
        with patch("concilium.application.services.concilium_service._catalog.Runtime") as MockRT:
            MockRT.return_value.load_catalogo.return_value = {}
            result = svc.get_catalog("empty")

        assert result["n_cpus"] == 0
        assert result["n_insumos"] == 0
        assert result["n_producoes"] == 0


# ─── list_catalog_cpus ───────────────────────────────────────────────────────


class TestListCatalogCpus:
    def _svc_with_cpus(self, cpus: list[dict]):
        svc, _ = _make_svc()
        svc._get_enriched_cpus = MagicMock(return_value=cpus)
        return svc

    def test_returns_all_cpus_no_filter(self):
        cpus = [
            {"codigo": "CPU-A", "descricao": "Alpha"},
            {"codigo": "CPU-B", "descricao": "Beta"},
        ]
        svc = self._svc_with_cpus(cpus)
        result = svc.list_catalog_cpus("cat1")
        assert result["total"] == 2
        assert result["catalog_id"] == "cat1"
        assert len(result["items"]) == 2

    def test_filters_by_query_codigo(self):
        cpus = [
            {"codigo": "CPU-ALPHA", "descricao": "Escavacao"},
            {"codigo": "CPU-BETA", "descricao": "Transporte"},
        ]
        svc = self._svc_with_cpus(cpus)
        result = svc.list_catalog_cpus("cat1", q="alpha")
        assert result["total"] == 1
        assert result["items"][0]["codigo"] == "CPU-ALPHA"

    def test_filters_by_query_descricao(self):
        cpus = [
            {"codigo": "CPU-A", "descricao": "Escavacao mecanica"},
            {"codigo": "CPU-B", "descricao": "Transporte rodoviario"},
        ]
        svc = self._svc_with_cpus(cpus)
        result = svc.list_catalog_cpus("cat1", q="escavacao")
        assert result["total"] == 1

    def test_limit_applied(self):
        cpus = [{"codigo": f"CPU-{i}", "descricao": f"desc {i}"} for i in range(10)]
        svc = self._svc_with_cpus(cpus)
        result = svc.list_catalog_cpus("cat1", limit=3)
        assert len(result["items"]) == 3
        assert result["total"] == 10

    def test_query_is_case_insensitive(self):
        cpus = [{"codigo": "CPU-TERRA", "descricao": "Terraplenagem"}]
        svc = self._svc_with_cpus(cpus)
        result = svc.list_catalog_cpus("cat1", q="TERRA")
        assert result["total"] == 1


# ─── get_catalog_cpu ─────────────────────────────────────────────────────────


class TestGetCatalogCpu:
    def test_found_returns_dict(self):
        cpu = {"codigo": "CPU-XYZ", "descricao": "Test"}
        svc, _ = _make_svc()
        svc._get_enriched_cpus = MagicMock(return_value=[cpu])
        result = svc.get_catalog_cpu("cat1", "CPU-XYZ")
        assert result == cpu

    def test_not_found_returns_none(self):
        svc, _ = _make_svc()
        svc._get_enriched_cpus = MagicMock(return_value=[{"codigo": "CPU-OTHER", "descricao": "Other"}])
        result = svc.get_catalog_cpu("cat1", "CPU-MISSING")
        assert result is None

    def test_empty_enriched_returns_none(self):
        svc, _ = _make_svc()
        svc._get_enriched_cpus = MagicMock(return_value=[])
        assert svc.get_catalog_cpu("cat1", "CPU-ANY") is None


# ─── list_catalog_insumos ────────────────────────────────────────────────────


class TestListCatalogInsumos:
    def _svc_with_insumos(self, insumos: list[dict], tmp_path: Path):
        svc, _ = _make_svc(tmp_path)
        fake_cat = {"insumos": insumos}
        return svc, fake_cat

    def test_returns_all_insumos_no_filter(self, tmp_path):
        insumos = [
            {"codigo": "INS-A", "descricao": "Cimento"},
            {"codigo": "INS-B", "descricao": "Areia"},
        ]
        svc, fake_cat = self._svc_with_insumos(insumos, tmp_path)
        with patch("concilium.application.services.concilium_service._catalog.Runtime") as MockRT:
            MockRT.return_value.load_catalogo.return_value = fake_cat
            result = svc.list_catalog_insumos("cat1")
        assert result["total"] == 2
        assert result["catalog_id"] == "cat1"

    def test_filters_insumos_by_query(self, tmp_path):
        insumos = [
            {"codigo": "INS-CIM", "descricao": "Cimento Portland"},
            {"codigo": "INS-ARC", "descricao": "Areia grossa"},
        ]
        svc, fake_cat = self._svc_with_insumos(insumos, tmp_path)
        with patch("concilium.application.services.concilium_service._catalog.Runtime") as MockRT:
            MockRT.return_value.load_catalogo.return_value = fake_cat
            result = svc.list_catalog_insumos("cat1", q="cimento")
        assert result["total"] == 1
        assert result["items"][0]["codigo"] == "INS-CIM"

    def test_limit_applied_to_insumos(self, tmp_path):
        insumos = [{"codigo": f"INS-{i}", "descricao": f"desc {i}"} for i in range(10)]
        svc, fake_cat = self._svc_with_insumos(insumos, tmp_path)
        with patch("concilium.application.services.concilium_service._catalog.Runtime") as MockRT:
            MockRT.return_value.load_catalogo.return_value = fake_cat
            result = svc.list_catalog_insumos("cat1", limit=4)
        assert len(result["items"]) == 4
        assert result["total"] == 10

    def test_empty_catalog_insumos(self, tmp_path):
        svc, fake_cat = self._svc_with_insumos([], tmp_path)
        with patch("concilium.application.services.concilium_service._catalog.Runtime") as MockRT:
            MockRT.return_value.load_catalogo.return_value = fake_cat
            result = svc.list_catalog_insumos("cat1")
        assert result["total"] == 0
        assert result["items"] == []


# ─── search_catalog ───────────────────────────────────────────────────────────


class TestSearchCatalog:
    def test_with_specific_catalog_id(self):
        svc, _ = _make_svc()
        cpus = [{"codigo": "CPU-ESCO", "descricao": "Escavacao"}]
        svc._get_enriched_cpus = MagicMock(return_value=cpus)
        result = svc.search_catalog("escavacao", catalog_id="cat1")
        assert result["q"] == "escavacao"
        assert result["total"] == 1
        assert result["items"][0]["_catalog_id"] == "cat1"

    def test_without_catalog_id_searches_all(self, tmp_path):
        cats = tmp_path / "catalogos"
        (cats / "cat-a").mkdir(parents=True)
        (cats / "cat-b").mkdir(parents=True)
        svc, _ = _make_svc(tmp_path)
        cpus_a = [{"codigo": "CPU-A1", "descricao": "Alpha Escavacao"}]
        cpus_b = [{"codigo": "CPU-B1", "descricao": "Beta Transporte"}]

        def _enriched(catalog_id):
            return cpus_a if catalog_id == "cat-a" else cpus_b

        svc._get_enriched_cpus = MagicMock(side_effect=_enriched)
        result = svc.search_catalog("escavacao")
        assert result["total"] == 1
        assert result["items"][0]["codigo"] == "CPU-A1"

    def test_stops_when_limit_reached(self, tmp_path):
        cats = tmp_path / "catalogos"
        for i in range(5):
            (cats / f"cat-{i}").mkdir(parents=True)
        svc, _ = _make_svc(tmp_path)
        # Each catalog has 5 matching CPUs
        svc._get_enriched_cpus = MagicMock(
            return_value=[{"codigo": f"CPU-{i}", "descricao": "match"} for i in range(5)]
        )
        result = svc.search_catalog("match", limit=7)
        assert len(result["items"]) == 7

    def test_continues_after_catalog_error(self, tmp_path):
        cats = tmp_path / "catalogos"
        (cats / "good-cat").mkdir(parents=True)
        (cats / "bad-cat").mkdir(parents=True)
        svc, _ = _make_svc(tmp_path)

        def _enriched(catalog_id):
            if catalog_id == "bad-cat":
                raise RuntimeError("broken!")
            return [{"codigo": "CPU-OK", "descricao": "Good result"}]

        svc._get_enriched_cpus = MagicMock(side_effect=_enriched)
        result = svc.search_catalog("good")
        assert result["total"] == 1


# ─── audit_catalog_reasonability ─────────────────────────────────────────────


class TestAuditCatalogReasonability:
    def test_calls_build_reasonability_artifact(self, tmp_path):
        svc, _ = _make_svc(tmp_path)
        fake_cat = {
            "cpus": [{"codigo": "CPU-A"}],
            "produtividades": [{"id": "PROD-1"}],
            "producoes": [],
        }
        with (
            patch("concilium.application.services.concilium_service._catalog.Runtime") as MockRT,
            patch(
                "concilium.application.services.concilium_service._catalog.build_catalog_reasonability_artifact"
            ) as mock_build,
        ):
            MockRT.return_value.load_catalogo.return_value = fake_cat
            mock_build.return_value = {"catalog_id": "cat1", "issues": []}
            result = svc.audit_catalog_reasonability("cat1")

        mock_build.assert_called_once()
        call_args = mock_build.call_args
        assert call_args[0][0] == "cat1"  # catalog_id
        # cpus list passed
        assert call_args[0][1] == [{"codigo": "CPU-A"}]
        assert result == {"catalog_id": "cat1", "issues": []}

    def test_merges_produtividades_and_producoes(self, tmp_path):
        svc, _ = _make_svc(tmp_path)
        fake_cat = {
            "cpus": [],
            "produtividades": [{"id": "PROD-1", "producao_horaria": 10}],
            "producoes": [{"id": "PROD-2", "producao_horaria": 20}],
        }
        with (
            patch("concilium.application.services.concilium_service._catalog.Runtime") as MockRT,
            patch(
                "concilium.application.services.concilium_service._catalog.build_catalog_reasonability_artifact"
            ) as mock_build,
        ):
            MockRT.return_value.load_catalogo.return_value = fake_cat
            mock_build.return_value = {}
            svc.audit_catalog_reasonability("cat1")

        _, _, producoes_arg = mock_build.call_args[0]
        assert len(producoes_arg) == 2


# ─── _enrich_cpus_with_producao (static) ─────────────────────────────────────


class TestEnrichCpusWithProducaoStatic:
    def test_no_cpus_returns_empty(self):
        cat = {"cpus": [], "producoes": []}
        result = ConciliumService._enrich_cpus_with_producao(cat)
        assert result == []

    def test_enriches_matching_producao_id_ref(self):
        cat = {
            "cpus": [{"codigo": "CPU-A", "producao_id_ref": "PROD-1"}],
            "producoes": [{"id": "PROD-1", "producao_horaria": 42.5, "equipe": {"op": 1}}],
        }
        result = ConciliumService._enrich_cpus_with_producao(cat)
        assert result[0]["producao_horaria"] == 42.5
        assert result[0]["equipe"] == {"op": 1}

    def test_skips_non_dict_cpus(self):
        cat = {"cpus": ["not-a-dict", {"codigo": "CPU-A"}], "producoes": []}
        result = ConciliumService._enrich_cpus_with_producao(cat)
        assert len(result) == 1
        assert result[0]["codigo"] == "CPU-A"

    def test_produtividades_takes_precedence_over_producoes(self):
        cat = {
            "cpus": [{"codigo": "CPU-A", "producao_id_ref": "PROD-1"}],
            "produtividades": [{"id": "PROD-1", "producao_horaria": 100.0}],
            "producoes": [{"id": "PROD-1", "producao_horaria": 999.0}],
        }
        result = ConciliumService._enrich_cpus_with_producao(cat)
        # _enrich_cpus_with_producao uses produtividades OR producoes (first found)
        assert result[0]["producao_horaria"] == 100.0

    def test_cpu_without_ref_unchanged(self):
        cat = {
            "cpus": [{"codigo": "CPU-A"}],
            "producoes": [{"id": "PROD-1", "producao_horaria": 5.0}],
        }
        result = ConciliumService._enrich_cpus_with_producao(cat)
        assert "producao_horaria" not in result[0]


# ─── extend_cpu ───────────────────────────────────────────────────────────────


class TestExtendCpu:
    def test_delegates_to_override_service(self):
        svc, deps = _make_svc()
        svc.extend_cpu("proj-1", "CPU-X", {"composicao_itens": []}, actor="user1", motivo="fix")
        deps.override_service.extend_cpu.assert_called_once_with(
            "proj-1", "CPU-X", {"composicao_itens": []}, actor="user1", motivo="fix"
        )


# ─── get_project_catalog_overrides ────────────────────────────────────────────


class TestGetProjectCatalogOverrides:
    def test_returns_overlay_dict(self):
        svc, deps = _make_svc()
        project = _make_project_mock()
        project.read_json.return_value = {"CPU-A": {"factor": 1.2}}
        deps.repository.get_project.return_value = project
        result = svc.get_project_catalog_overrides("proj-1")
        assert result == {"CPU-A": {"factor": 1.2}}
        project.read_json.assert_called_once_with("overrides/cpus_overlay.json", {})

    def test_returns_empty_when_overlay_is_not_dict(self):
        svc, deps = _make_svc()
        project = _make_project_mock()
        project.read_json.return_value = ["not", "a", "dict"]
        deps.repository.get_project.return_value = project
        result = svc.get_project_catalog_overrides("proj-1")
        assert result == {}


# ─── resolve_cpu ─────────────────────────────────────────────────────────────


class TestResolveCpu:
    def test_returns_merged_when_both_candidate_and_master(self):
        svc, deps = _make_svc()
        candidate = {"codigo": "CPU-X", "project_factor": 2}
        master = {"codigo": "CPU-X", "composicao_itens": [{"insumo": "areia"}]}
        deps.override_service.resolve_cpu.return_value = candidate
        project = _make_project_mock(meta={"catalogo_base": "cat1"})
        deps.repository.get_project.return_value = project
        svc.get_catalog_cpu = MagicMock(return_value=master)
        result = svc.resolve_cpu("proj-1", "CPU-X")
        # merged: master fields + candidate fields override
        assert result["composicao_itens"] == [{"insumo": "areia"}]
        assert result["project_factor"] == 2

    def test_returns_master_when_no_candidate(self):
        svc, deps = _make_svc()
        master = {"codigo": "CPU-X", "descricao": "Master only"}
        deps.override_service.resolve_cpu.return_value = None
        project = _make_project_mock(meta={"catalogo_base": "cat1"})
        deps.repository.get_project.return_value = project
        svc.get_catalog_cpu = MagicMock(return_value=master)
        result = svc.resolve_cpu("proj-1", "CPU-X")
        assert result == master

    def test_returns_none_when_neither_found(self):
        svc, deps = _make_svc()
        deps.override_service.resolve_cpu.return_value = None
        project = _make_project_mock(meta={})
        deps.repository.get_project.return_value = project
        svc.get_catalog_cpu = MagicMock(return_value=None)
        result = svc.resolve_cpu("proj-1", "CPU-MISSING")
        assert result is None

    def test_enriches_candidate_when_no_master(self):
        svc, deps = _make_svc()
        candidate = {"codigo": "CPU-X", "producao_id_ref": "PROD-1"}
        deps.override_service.resolve_cpu.return_value = candidate
        project = _make_project_mock(meta={})
        deps.repository.get_project.return_value = project
        svc.get_catalog_cpu = MagicMock(return_value=None)
        svc._enrich_cpu_from_producao = MagicMock(return_value={**candidate, "producao_horaria": 55.0})
        result = svc.resolve_cpu("proj-1", "CPU-X")
        assert result["producao_horaria"] == 55.0
        svc._enrich_cpu_from_producao.assert_called_once()

    def test_skips_catalog_on_exception_tries_next(self):
        svc, deps = _make_svc()
        master = {"codigo": "CPU-X", "descricao": "Found in second cat"}
        deps.override_service.resolve_cpu.return_value = None
        project = _make_project_mock(meta={"catalogo_base": "cat1", "contexto_id": "cat2"})
        deps.repository.get_project.return_value = project
        # No contexto_version → _resolve_project_catalog_id returns contexto_id directly (versions=[])
        deps.project_service.list_contexto_versions.return_value = []
        call_count = [0]

        def _get_cpu(cat_id, cpu_id):
            call_count[0] += 1
            if cat_id == "cat1":
                raise RuntimeError("cat1 broken")
            return master

        svc.get_catalog_cpu = MagicMock(side_effect=_get_cpu)
        result = svc.resolve_cpu("proj-1", "CPU-X")
        assert result == master


class TestResolveCpuContextoProjeto:
    """ADR-149: contexto_projeto é sempre complementar, anexado independente da fonte resolvida."""

    def test_attaches_contexto_when_present_master_only(self):
        svc, deps = _make_svc()
        master = {"codigo": "CPU-X", "descricao": "Master only"}
        deps.override_service.resolve_cpu.return_value = None
        deps.override_service.get_cpu_contexto.return_value = "Solo argiloso nesta obra."
        project = _make_project_mock(meta={"catalogo_base": "cat1"})
        deps.repository.get_project.return_value = project
        svc.get_catalog_cpu = MagicMock(return_value=master)
        result = svc.resolve_cpu("proj-1", "CPU-X")
        assert result["descricao"] == "Master only"
        assert result["contexto_projeto"] == "Solo argiloso nesta obra."

    def test_attaches_contexto_when_present_candidate_and_master(self):
        svc, deps = _make_svc()
        candidate = {"codigo": "CPU-X", "project_factor": 2}
        master = {"codigo": "CPU-X", "composicao_itens": [{"insumo": "areia"}]}
        deps.override_service.resolve_cpu.return_value = candidate
        deps.override_service.get_cpu_contexto.return_value = "Acesso restrito por chuva."
        project = _make_project_mock(meta={"catalogo_base": "cat1"})
        deps.repository.get_project.return_value = project
        svc.get_catalog_cpu = MagicMock(return_value=master)
        result = svc.resolve_cpu("proj-1", "CPU-X")
        assert result["contexto_projeto"] == "Acesso restrito por chuva."
        # Complementar: descrição/composição herdadas do catálogo continuam presentes.
        assert result["composicao_itens"] == [{"insumo": "areia"}]

    def test_no_contexto_key_when_absent(self):
        svc, deps = _make_svc()
        master = {"codigo": "CPU-X", "descricao": "Master only"}
        deps.override_service.resolve_cpu.return_value = None
        deps.override_service.get_cpu_contexto.return_value = None
        project = _make_project_mock(meta={"catalogo_base": "cat1"})
        deps.repository.get_project.return_value = project
        svc.get_catalog_cpu = MagicMock(return_value=master)
        result = svc.resolve_cpu("proj-1", "CPU-X")
        assert "contexto_projeto" not in result

    def test_no_contexto_attached_when_cpu_not_found(self):
        svc, deps = _make_svc()
        deps.override_service.resolve_cpu.return_value = None
        deps.override_service.get_cpu_contexto.return_value = "não deveria aparecer"
        project = _make_project_mock(meta={})
        deps.repository.get_project.return_value = project
        svc.get_catalog_cpu = MagicMock(return_value=None)
        result = svc.resolve_cpu("proj-1", "CPU-MISSING")
        assert result is None

    def test_set_cpu_contexto_delegates(self):
        svc, deps = _make_svc()
        svc.set_cpu_contexto("proj-1", "CPU-X", "texto", actor="eng-1")
        deps.override_service.set_cpu_contexto.assert_called_once_with("proj-1", "CPU-X", "texto", actor="eng-1")

    def test_get_cpu_contexto_delegates(self):
        svc, deps = _make_svc()
        deps.override_service.get_cpu_contexto.return_value = "texto salvo"
        assert svc.get_cpu_contexto("proj-1", "CPU-X") == "texto salvo"

    def test_list_cpu_contextos_delegates(self):
        svc, deps = _make_svc()
        deps.override_service.list_cpu_contextos.return_value = {"CPU-X": "texto"}
        assert svc.list_cpu_contextos("proj-1") == {"CPU-X": "texto"}


# ─── _candidate_catalog_ids ───────────────────────────────────────────────────


class TestCandidateCatalogIds:
    def test_returns_catalogo_base_when_set(self):
        svc, deps = _make_svc()
        project = _make_project_mock(meta={"catalogo_base": "base-cat"})
        deps.project_service.list_contexto_versions.return_value = []
        result = svc._candidate_catalog_ids(project)
        assert "base-cat" in result

    def test_deduplicates_ids(self):
        svc, deps = _make_svc()
        # catalogo_base == contexto_id == same value → deduped
        project = _make_project_mock(meta={"catalogo_base": "cat-X", "contexto_id": "cat-X"})
        deps.project_service.list_contexto_versions.return_value = []
        result = svc._candidate_catalog_ids(project)
        assert result.count("cat-X") == 1

    def test_empty_meta_returns_empty_list(self):
        svc, deps = _make_svc()
        project = _make_project_mock(meta={})
        deps.project_service.list_contexto_versions.return_value = []
        result = svc._candidate_catalog_ids(project)
        assert result == []

    def test_includes_contexto_id(self):
        svc, deps = _make_svc()
        project = _make_project_mock(meta={"contexto_id": "ctx-cat"})
        deps.project_service.list_contexto_versions.return_value = []
        result = svc._candidate_catalog_ids(project)
        assert "ctx-cat" in result


# ─── _enrich_cpu_from_producao ───────────────────────────────────────────────


class TestEnrichCpuFromProducao:
    def test_returns_unchanged_when_already_has_both_fields(self):
        svc, _ = _make_svc()
        project = _make_project_mock(meta={})
        cpu = {"codigo": "CPU-A", "equipe": {"op": 1}, "producao_horaria": 10.0}
        result = svc._enrich_cpu_from_producao(project, cpu)
        assert result is cpu  # no copy needed, returned as-is

    def test_returns_unchanged_when_no_prod_id_ref(self):
        svc, _ = _make_svc()
        project = _make_project_mock(meta={})
        cpu = {"codigo": "CPU-A"}
        result = svc._enrich_cpu_from_producao(project, cpu)
        assert result == cpu

    def test_injects_producao_horaria_from_prod(self):
        svc, deps = _make_svc()
        project = _make_project_mock(meta={"catalogo_base": "cat1"})
        deps.project_service.list_contexto_versions.return_value = []
        cpu = {"codigo": "CPU-A", "producao_id_ref": "PROD-1"}
        svc._get_catalog_producao = MagicMock(return_value={"id": "PROD-1", "producao_horaria": 88.0})
        result = svc._enrich_cpu_from_producao(project, cpu)
        assert result["producao_horaria"] == 88.0

    def test_injects_equipe_dict(self):
        svc, deps = _make_svc()
        project = _make_project_mock(meta={"catalogo_base": "cat1"})
        deps.project_service.list_contexto_versions.return_value = []
        cpu = {"codigo": "CPU-A", "producao_id_ref": "PROD-1"}
        prod = {"id": "PROD-1", "producao_horaria": 5.0, "equipe": {"op": 2, "ajudante": 1}}
        svc._get_catalog_producao = MagicMock(return_value=prod)
        result = svc._enrich_cpu_from_producao(project, cpu)
        assert result["equipe"] == {"op": 2, "ajudante": 1}

    def test_uses_composicao_padrao_equipe_fallback(self):
        svc, deps = _make_svc()
        project = _make_project_mock(meta={"catalogo_base": "cat1"})
        deps.project_service.list_contexto_versions.return_value = []
        cpu = {"codigo": "CPU-A", "producao_id_ref": "PROD-1"}
        prod = {
            "id": "PROD-1",
            "producao_horaria": 5.0,
            "equipe": "not-a-dict",  # non-dict triggers fallback
            "composicao_padrao_equipe": {"op": 1},
        }
        svc._get_catalog_producao = MagicMock(return_value=prod)
        result = svc._enrich_cpu_from_producao(project, cpu)
        assert result["equipe"] == {"op": 1}

    def test_no_prod_found_in_any_catalog(self):
        svc, deps = _make_svc()
        project = _make_project_mock(meta={"catalogo_base": "cat1"})
        deps.project_service.list_contexto_versions.return_value = []
        cpu = {"codigo": "CPU-A", "producao_id_ref": "PROD-MISSING"}
        svc._get_catalog_producao = MagicMock(return_value=None)
        result = svc._enrich_cpu_from_producao(project, cpu)
        assert "producao_horaria" not in result

    def test_producao_horaria_already_set_skips_overwrite(self):
        """Covers the false branch of
        `if cpu.get("producao_horaria") is None and ...`: when the CPU
        already carries a producao_horaria, it must not be overwritten, but
        the equipe-filling branch below must still run."""
        svc, deps = _make_svc()
        project = _make_project_mock(meta={"catalogo_base": "cat1"})
        deps.project_service.list_contexto_versions.return_value = []
        cpu = {"codigo": "CPU-A", "producao_id_ref": "PROD-1", "producao_horaria": 42.0}
        prod = {"id": "PROD-1", "producao_horaria": 88.0, "equipe": {"op": 2}}
        svc._get_catalog_producao = MagicMock(return_value=prod)
        result = svc._enrich_cpu_from_producao(project, cpu)
        assert result["producao_horaria"] == 42.0  # unchanged
        assert result["equipe"] == {"op": 2}

    def test_equipe_already_set_skips_fill_but_still_checks_break(self):
        """Covers the false branch of `if not cpu.get("equipe")`: when the
        CPU already has an equipe dict, the fill step is skipped but the
        loop must still evaluate the break condition afterwards."""
        svc, deps = _make_svc()
        project = _make_project_mock(meta={"catalogo_base": "cat1"})
        deps.project_service.list_contexto_versions.return_value = []
        cpu = {
            "codigo": "CPU-A",
            "producao_id_ref": "PROD-1",
            "equipe": {"existing": True},
        }
        prod = {"id": "PROD-1", "producao_horaria": 88.0, "equipe": {"op": 2}}
        svc._get_catalog_producao = MagicMock(return_value=prod)
        result = svc._enrich_cpu_from_producao(project, cpu)
        assert result["equipe"] == {"existing": True}  # unchanged
        assert result["producao_horaria"] == 88.0


# ─── _get_catalog_producao ────────────────────────────────────────────────────


class TestGetCatalogProducao:
    def test_finds_prod_in_produtividades(self, tmp_path):
        svc, _ = _make_svc(tmp_path)
        fake_cat = {
            "produtividades": [{"id": "PROD-1", "producao_horaria": 10}],
            "producoes": [],
        }
        with patch("concilium.application.services.concilium_service._cpu_resolution.Runtime") as MockRT:
            MockRT.return_value.load_catalogo.return_value = fake_cat
            result = svc._get_catalog_producao("cat1", "PROD-1")
        assert result["id"] == "PROD-1"

    def test_finds_prod_in_producoes_fallback(self, tmp_path):
        svc, _ = _make_svc(tmp_path)
        fake_cat = {
            "produtividades": [],
            "producoes": [{"id": "PROD-2", "producao_horaria": 20}],
        }
        with patch("concilium.application.services.concilium_service._cpu_resolution.Runtime") as MockRT:
            MockRT.return_value.load_catalogo.return_value = fake_cat
            result = svc._get_catalog_producao("cat1", "PROD-2")
        assert result["id"] == "PROD-2"

    def test_returns_none_when_not_found(self, tmp_path):
        svc, _ = _make_svc(tmp_path)
        fake_cat = {"produtividades": [], "producoes": []}
        with patch("concilium.application.services.concilium_service._cpu_resolution.Runtime") as MockRT:
            MockRT.return_value.load_catalogo.return_value = fake_cat
            result = svc._get_catalog_producao("cat1", "PROD-MISSING")
        assert result is None

    def test_skips_non_list_key_then_scans_multiple_rows(self, tmp_path):
        """Covers: (1) the `if not isinstance(rows, list): continue` branch
        when "produtividades" is not a list, and (2) the for-loop iterating
        past a non-matching row before finding the match in "producoes"."""
        svc, _ = _make_svc(tmp_path)
        fake_cat = {
            "produtividades": "not-a-list",
            "producoes": [
                {"id": "OTHER", "producao_horaria": 1},
                {"id": "PROD-3", "producao_horaria": 30},
            ],
        }
        with patch("concilium.application.services.concilium_service._cpu_resolution.Runtime") as MockRT:
            MockRT.return_value.load_catalogo.return_value = fake_cat
            result = svc._get_catalog_producao("cat1", "PROD-3")
        assert result["id"] == "PROD-3"


# ─── _resolve_project_catalog_id ─────────────────────────────────────────────


class TestResolveProjectCatalogId:
    def test_returns_none_when_no_contexto_id(self):
        svc, _ = _make_svc()
        project = _make_project_mock(meta={})
        result = svc._resolve_project_catalog_id(project)
        assert result is None

    def test_returns_contexto_id_when_no_versions(self):
        svc, deps = _make_svc()
        project = _make_project_mock(meta={"contexto_id": "ctx-1"})
        deps.project_service.list_contexto_versions.return_value = []
        result = svc._resolve_project_catalog_id(project)
        assert result == "ctx-1"

    def test_returns_latest_version_catalog_id(self):
        svc, deps = _make_svc()
        project = _make_project_mock(meta={"contexto_id": "ctx-1"})
        versions = [
            {"version": "1", "catalogo_id": "cat-old"},
            {"version": "2", "catalogo_id": "cat-new"},
        ]
        deps.project_service.list_contexto_versions.return_value = versions
        result = svc._resolve_project_catalog_id(project)
        assert result == "cat-new"

    def test_selects_specific_version_when_set(self):
        svc, deps = _make_svc()
        project = _make_project_mock(meta={"contexto_id": "ctx-1", "contexto_version": "1"})
        versions = [
            {"version": "1", "catalogo_id": "cat-v1"},
            {"version": "2", "catalogo_id": "cat-v2"},
        ]
        deps.project_service.list_contexto_versions.return_value = versions
        result = svc._resolve_project_catalog_id(project)
        assert result == "cat-v1"

    def test_handles_list_contexto_versions_exception(self):
        svc, deps = _make_svc()
        project = _make_project_mock(meta={"contexto_id": "ctx-1"})
        deps.project_service.list_contexto_versions.side_effect = RuntimeError("not available")
        result = svc._resolve_project_catalog_id(project)
        assert result == "ctx-1"

    def test_returns_contexto_id_when_selected_has_empty_catalog(self):
        svc, deps = _make_svc()
        project = _make_project_mock(meta={"contexto_id": "ctx-1"})
        versions = [{"version": "1", "catalogo_id": ""}]
        deps.project_service.list_contexto_versions.return_value = versions
        result = svc._resolve_project_catalog_id(project)
        # empty catalog_id → falls back to contexto_id
        assert result == "ctx-1"


# ─── list_benchmarks ─────────────────────────────────────────────────────────


class TestListBenchmarks:
    def test_returns_empty_when_root_missing(self, tmp_path):
        svc, deps = _make_svc()
        deps.benchmarks_root = tmp_path / "nonexistent"
        result = svc.list_benchmarks()
        assert result == []

    def test_returns_slugs_for_valid_benchmark_dirs(self, tmp_path):
        benchmarks_root = tmp_path / "benchmarks"
        slug_dir = benchmarks_root / "agis"
        slug_dir.mkdir(parents=True)
        # A reference candidate file that discover_benchmark_slugs checks for
        (slug_dir / "referencia.json").write_text("{}")
        svc, deps = _make_svc()
        deps.benchmarks_root = benchmarks_root
        result = svc.list_benchmarks()
        assert "AGIS" in result


# ─── project delegation methods ───────────────────────────────────────────────


class TestProjectDelegation:
    def test_list_projects_delegates(self):
        svc, deps = _make_svc()
        deps.project_service.list_projects.return_value = [{"id": "p1"}]
        assert svc.list_projects() == [{"id": "p1"}]

    def test_get_project_delegates(self):
        svc, deps = _make_svc()
        deps.project_service.get_project.return_value = {"id": "p1"}
        assert svc.get_project("p1") == {"id": "p1"}
        deps.project_service.get_project.assert_called_once_with("p1")

    def test_delete_project_delegates(self):
        svc, deps = _make_svc()
        deps.project_service.delete_project.return_value = {"deleted": True}
        result = svc.delete_project("p1", actor="admin")
        assert result == {"deleted": True}
        deps.project_service.delete_project.assert_called_once_with("p1", actor="admin")

    def test_create_project_delegates_prepared_inputs(self):
        svc, deps = _make_svc()
        prepared = MagicMock()
        prepared.inputs_escopo = {"area": 100}
        prepared.skill_inputs = {"skill-01": {}}
        prepared.benchmark_slug = "agis"
        prepared.benchmark_reference = None
        prepared.contexto_version = "v2"
        prepared.perfil_id = "perf-1"
        prepared.perfil_version = "1"
        deps.input_builder.prepare.return_value = prepared
        deps.project_service.create_project.return_value = {"id": "new-proj"}
        req = {"nome": "Test Proj"}
        result = svc.create_project(req, actor="user1")
        assert result == {"id": "new-proj"}
        deps.input_builder.prepare.assert_called_once_with(req)

    def test_get_eap_delegates(self):
        svc, deps = _make_svc()
        deps.project_service.get_eap.return_value = {"eap": []}
        assert svc.get_eap("p1") == {"eap": []}

    def test_upsert_eap_delegates(self):
        svc, deps = _make_svc()
        deps.project_service.upsert_eap.return_value = {"ok": True}
        result = svc.upsert_eap("p1", [{"id": "eap-1"}], actor="u1")
        deps.project_service.upsert_eap.assert_called_once_with("p1", [{"id": "eap-1"}], actor="u1")
        assert result == {"ok": True}

    def test_patch_project_config_delegates(self):
        svc, deps = _make_svc()
        deps.project_service.patch_project_config.return_value = {"patched": True}
        result = svc.patch_project_config("p1", {"key": "val"}, actor="u1")
        deps.project_service.patch_project_config.assert_called_once_with("p1", {"key": "val"}, actor="u1")
        assert result == {"patched": True}


# ─── run_project / start_run_project ─────────────────────────────────────────


class TestRunProjectDelegation:
    def test_run_project_delegates(self):
        svc, deps = _make_svc()
        deps.pipeline_service.run_project.return_value = {"run_id": "r1"}
        result = svc.run_project(
            "p1",
            base_version=None,
            fork_version=False,
            skill_inputs_override={},
            use_saved_overrides=True,
            use_mobilizacao_policy=False,
            use_strict_catalog_baseline=False,
            actor="user1",
        )
        assert result == {"run_id": "r1"}

    def test_start_run_project_delegates(self):
        svc, deps = _make_svc()
        deps.pipeline_service.start_run_project.return_value = {"job_id": "j1"}
        result = svc.start_run_project(
            "p1",
            base_version="v1",
            fork_version=True,
            skill_inputs_override={},
            use_saved_overrides=False,
            use_mobilizacao_policy=True,
            use_strict_catalog_baseline=True,
        )
        assert result == {"job_id": "j1"}

    def test_list_runs_delegates(self):
        svc, deps = _make_svc()
        deps.pipeline_service.list_runs.return_value = [{"id": "r1"}]
        assert svc.list_runs("p1") == [{"id": "r1"}]

    def test_get_run_delegates(self):
        svc, deps = _make_svc()
        deps.pipeline_service.get_run.return_value = {"id": "r1", "version": "v2"}
        assert svc.get_run("p1", "r1") == {"id": "r1", "version": "v2"}


# ─── resolve_run_base_version ────────────────────────────────────────────────


class TestResolveRunBaseVersion:
    def test_returns_version_string(self):
        svc, deps = _make_svc()
        deps.pipeline_service.get_run.return_value = {"id": "r1", "version": "v3"}
        assert svc.resolve_run_base_version("p1", "r1") == "v3"

    def test_raises_when_no_version(self):
        svc, deps = _make_svc()
        deps.pipeline_service.get_run.return_value = {"id": "r1"}
        with pytest.raises(ValueError, match="ainda não possui versão"):
            svc.resolve_run_base_version("p1", "r1")


# ─── versioning delegation ───────────────────────────────────────────────────


class TestVersioningDelegation:
    def test_list_versions(self):
        svc, deps = _make_svc()
        deps.project_service.list_versions.return_value = ["v1", "v2"]
        assert svc.list_versions("p1") == ["v1", "v2"]

    def test_delete_version(self):
        svc, deps = _make_svc()
        deps.project_service.delete_version.return_value = {"deleted": "v1"}
        result = svc.delete_version("p1", "v1", actor="u1")
        deps.project_service.delete_version.assert_called_once_with("p1", "v1", actor="u1")
        assert result == {"deleted": "v1"}

    def test_compare_versions(self):
        svc, deps = _make_svc()
        deps.project_service.compare_versions.return_value = {"diff": {}}
        svc.compare_versions("p1", "v1", "v2")
        deps.project_service.compare_versions.assert_called_once_with("p1", "v1", "v2")

    def test_fork_version(self):
        svc, deps = _make_svc()
        deps.project_service.fork_version.return_value = {"version": "v2"}
        svc.fork_version("p1", "v1", actor="u2")
        deps.project_service.fork_version.assert_called_once_with("p1", "v1", actor="u2")


# ─── audit / overrides ───────────────────────────────────────────────────────


class TestAuditAndOverrides:
    def test_list_audit_delegates(self):
        svc, deps = _make_svc()
        project = _make_project_mock()
        deps.repository.get_project.return_value = project
        deps.audit_service.list.return_value = [{"entry": 1}]
        result = svc.list_audit("p1", limit=50)
        deps.audit_service.list.assert_called_once_with(project, limit=50)
        assert result == [{"entry": 1}]

    def test_list_overrides_delegates(self):
        svc, deps = _make_svc()
        deps.override_service.list_overrides.return_value = {"skill-01": {}}
        assert svc.list_overrides("p1") == {"skill-01": {}}

    def test_upsert_override_delegates(self):
        svc, deps = _make_svc()
        deps.override_service.upsert_override.return_value = {"ok": True}
        svc.upsert_override("p1", "skill-01", {"k": "v"}, actor="u1")
        deps.override_service.upsert_override.assert_called_once_with("p1", "skill-01", {"k": "v"}, actor="u1")

    def test_delete_override_delegates(self):
        svc, deps = _make_svc()
        deps.override_service.delete_override.return_value = {"deleted": True}
        svc.delete_override("p1", "skill-01", actor="u1")
        deps.override_service.delete_override.assert_called_once_with("p1", "skill-01", actor="u1")


# ─── perfil methods ───────────────────────────────────────────────────────────


class TestPerfis:
    def test_list_perfis(self):
        svc, deps = _make_svc()
        deps.project_service.list_perfis.return_value = [{"id": "perf-1"}]
        assert svc.list_perfis() == [{"id": "perf-1"}]

    def test_list_perfil_versions(self):
        svc, deps = _make_svc()
        deps.project_service.list_perfil_versions.return_value = [{"version": "1"}]
        assert svc.list_perfil_versions("perf-1") == [{"version": "1"}]

    def test_create_perfil_version_delegates(self):
        svc, deps = _make_svc()
        deps.project_service.create_perfil_version.return_value = {"version": "2"}
        result = svc.create_perfil_version("perf-1", {"field": "val"}, "test motivo", "author1", make_current=True)
        deps.project_service.create_perfil_version.assert_called_once_with(
            "perf-1", {"field": "val"}, "test motivo", "author1", make_current=True
        )
        assert result == {"version": "2"}

    def test_compare_perfil_versions(self):
        svc, deps = _make_svc()
        deps.project_service.compare_perfil_versions.return_value = {"diff": {}}
        svc.compare_perfil_versions("perf-1", "v1", "v2")
        deps.project_service.compare_perfil_versions.assert_called_once_with("perf-1", "v1", "v2")


# ─── contexto methods ─────────────────────────────────────────────────────────


class TestContextos:
    def test_list_contextos(self):
        svc, deps = _make_svc()
        deps.project_service.list_contextos.return_value = [{"id": "ctx-1"}]
        assert svc.list_contextos() == [{"id": "ctx-1"}]

    def test_list_contexto_versions(self):
        svc, deps = _make_svc()
        deps.project_service.list_contexto_versions.return_value = [{"version": "1"}]
        assert svc.list_contexto_versions("ctx-1") == [{"version": "1"}]

    def test_create_contexto_version_delegates(self):
        svc, deps = _make_svc()
        deps.project_service.create_contexto_version.return_value = {"version": "3"}
        result = svc.create_contexto_version(
            "ctx-1", {"catalogo_id": "cat-new"}, "atualiza catalogo", "sys", make_current=False
        )
        deps.project_service.create_contexto_version.assert_called_once_with(
            "ctx-1", {"catalogo_id": "cat-new"}, "atualiza catalogo", "sys", make_current=False
        )
        assert result == {"version": "3"}

    def test_compare_contexto_versions(self):
        svc, deps = _make_svc()
        deps.project_service.compare_contexto_versions.return_value = {"diff": {}}
        svc.compare_contexto_versions("ctx-1", "v1", "v2")
        deps.project_service.compare_contexto_versions.assert_called_once_with("ctx-1", "v1", "v2")


# ─── temas methods ────────────────────────────────────────────────────────────


class TestTemas:
    def test_list_temas(self):
        svc, deps = _make_svc()
        deps.project_service.list_temas.return_value = [{"id": "tema-1"}]
        assert svc.list_temas() == [{"id": "tema-1"}]

    def test_list_tema_versions(self):
        svc, deps = _make_svc()
        deps.project_service.list_tema_versions.return_value = [{"version": "1"}]
        assert svc.list_tema_versions("tema-1") == [{"version": "1"}]

    def test_create_tema_version(self):
        svc, deps = _make_svc()
        deps.project_service.create_tema_version.return_value = {"version": "2"}
        svc.create_tema_version("tema-1", {"k": "v"}, "motivo", "author1", make_current=None)
        deps.project_service.create_tema_version.assert_called_once_with(
            "tema-1", {"k": "v"}, "motivo", "author1", make_current=None
        )

    def test_compare_tema_versions(self):
        svc, deps = _make_svc()
        deps.project_service.compare_tema_versions.return_value = {}
        svc.compare_tema_versions("tema-1", "v1", "v2")
        deps.project_service.compare_tema_versions.assert_called_once_with("tema-1", "v1", "v2")


# ─── jurisdicoes methods ─────────────────────────────────────────────────────


class TestJurisdicoes:
    def test_list_jurisdicoes(self):
        svc, deps = _make_svc()
        deps.project_service.list_jurisdicoes.return_value = [{"id": "jur-1"}]
        assert svc.list_jurisdicoes() == [{"id": "jur-1"}]

    def test_list_jurisdicao_versions(self):
        svc, deps = _make_svc()
        deps.project_service.list_jurisdicao_versions.return_value = [{"version": "1"}]
        assert svc.list_jurisdicao_versions("jur-1") == [{"version": "1"}]

    def test_create_jurisdicao_version(self):
        svc, deps = _make_svc()
        deps.project_service.create_jurisdicao_version.return_value = {"version": "2"}
        svc.create_jurisdicao_version("jur-1", {"k": "v"}, "motivo")
        deps.project_service.create_jurisdicao_version.assert_called_once_with(
            "jur-1", {"k": "v"}, "motivo", "system", make_current=None
        )

    def test_compare_jurisdicao_versions(self):
        svc, deps = _make_svc()
        deps.project_service.compare_jurisdicao_versions.return_value = {}
        svc.compare_jurisdicao_versions("jur-1", "v1", "v2")
        deps.project_service.compare_jurisdicao_versions.assert_called_once_with("jur-1", "v1", "v2")


# ─── artifacts ───────────────────────────────────────────────────────────────


class TestArtifacts:
    def test_list_artifacts_delegates(self):
        svc, deps = _make_svc()
        deps.project_service.list_artifacts.return_value = {"artifacts": []}
        svc.list_artifacts("p1", "v1")
        deps.project_service.list_artifacts.assert_called_once_with("p1", "v1")

    def test_get_artifact_bytes_delegates(self):
        svc, deps = _make_svc()
        deps.project_service.get_artifact_bytes.return_value = (b"data", "application/json")
        result = svc.get_artifact_bytes("p1", "v1", "report", "report.json")
        assert result == (b"data", "application/json")

    def test_get_benchmark_reference_delegates(self):
        svc, deps = _make_svc()
        deps.project_service.get_benchmark_reference.return_value = {"slug": "agis"}
        result = svc.get_benchmark_reference("p1")
        assert result == {"slug": "agis"}


# ─── get_diagnostico_pe ───────────────────────────────────────────────────────


class TestGetDiagnosticoPe:
    def test_returns_none_when_no_canonical(self):
        svc, deps = _make_svc()
        deps.project_service.get_last_canonical.return_value = None
        result = svc.get_diagnostico_pe("p1")
        assert result == {"diagnostico_pe": None, "backtracking_pe": None}

    def test_returns_dict_when_canonical_has_no_diag(self):
        svc, deps = _make_svc()
        canonical = MagicMock()
        canonical.diagnostico_pe = None
        canonical.backtracking_pe = None
        deps.project_service.get_last_canonical.return_value = canonical
        # Simulate no project in repository (triggers fallback path)
        deps.repository.get_project.side_effect = Exception("not found")
        result = svc.get_diagnostico_pe("p1")
        assert result["diagnostico_pe"] is None
        assert result["backtracking_pe"] is None

    def test_returns_serialized_diag(self):
        svc, deps = _make_svc()
        diag = MagicMock()
        diag.to_dict.return_value = {"status": "ok"}
        back = MagicMock()
        back.to_dict.return_value = {"steps": []}
        canonical = MagicMock()
        canonical.diagnostico_pe = diag
        canonical.backtracking_pe = back
        deps.project_service.get_last_canonical.return_value = canonical
        deps.repository.get_project.side_effect = Exception("not found")
        result = svc.get_diagnostico_pe("p1")
        assert result["diagnostico_pe"] == {"status": "ok"}
        assert result["backtracking_pe"] == {"steps": []}


# ─── mobilizacao methods ──────────────────────────────────────────────────────


class TestMobilizacaoDelegation:
    def test_get_mobilizacao_policies_delegates(self):
        svc, deps = _make_svc()
        deps.override_service.get_mobilizacao_policies.return_value = {"items": []}
        svc.get_mobilizacao_policies("p1")
        deps.override_service.get_mobilizacao_policies.assert_called_once_with("p1")

    def test_upsert_mobilizacao_policy_delegates(self):
        svc, deps = _make_svc()
        svc.upsert_mobilizacao_policy("p1", "item-1", {"policy": "x"}, actor="u1")
        deps.override_service.upsert_mobilizacao_policy.assert_called_once_with(
            "p1", "item-1", {"policy": "x"}, actor="u1"
        )

    def test_delete_mobilizacao_policy_delegates(self):
        svc, deps = _make_svc()
        svc.delete_mobilizacao_policy("p1", "item-1", actor="u1")
        deps.override_service.delete_mobilizacao_policy.assert_called_once_with("p1", "item-1", actor="u1")


# ─── deliverables ─────────────────────────────────────────────────────────────


class TestDeliverables:
    def test_get_deliverables_config_delegates(self):
        svc, deps = _make_svc()
        deps.override_service.get_deliverables_config.return_value = {"items": []}
        svc.get_deliverables_config("p1")
        deps.override_service.get_deliverables_config.assert_called_once_with("p1")

    def test_put_deliverables_config_delegates(self):
        svc, deps = _make_svc()
        deps.override_service.put_deliverables_config.return_value = {"ok": True}
        svc.put_deliverables_config("p1", {"items": []}, actor="u1")
        deps.override_service.put_deliverables_config.assert_called_once_with("p1", {"items": []}, actor="u1")


# ─── _load_canonical_for_version ────────────────────────────────────────────


class TestLoadCanonicalForVersion:
    def test_loads_from_repository_when_available(self):
        svc, deps = _make_svc()
        canonical = MagicMock()
        project = _make_project_mock(current_version="v5")
        project.load_canonical.return_value = canonical
        deps.repository.get_project.return_value = project
        result_canonical, result_version = svc._load_canonical_for_version("p1", "v2")
        assert result_canonical is canonical
        assert result_version == "v2"

    def test_returns_current_version_when_version_is_none(self):
        svc, deps = _make_svc()
        canonical = MagicMock()
        project = _make_project_mock(current_version="v5")
        project.load_canonical.return_value = canonical
        deps.repository.get_project.return_value = project
        result_canonical, result_version = svc._load_canonical_for_version("p1", None)
        assert result_version == "v5"

    def test_falls_back_to_project_service_when_repo_fails(self):
        svc, deps = _make_svc()
        canonical = MagicMock()
        deps.repository.get_project.side_effect = Exception("repo error")
        deps.project_service.get_last_canonical.return_value = canonical
        result_canonical, result_version = svc._load_canonical_for_version("p1", None)
        assert result_canonical is canonical

    def test_returns_none_when_all_fail(self):
        svc, deps = _make_svc()
        deps.repository.get_project.side_effect = Exception("repo error")
        deps.project_service.get_last_canonical.side_effect = Exception("ps error")
        result_canonical, result_version = svc._load_canonical_for_version("p1", None)
        assert result_canonical is None

    def test_repo_fails_with_explicit_version_skips_project_service_fallback(self):
        """Covers the false branch of `if version is None`: when a specific
        version is requested and the repository lookup fails, the legacy
        project_service fallback must not even be attempted."""
        svc, deps = _make_svc()
        deps.repository.get_project.side_effect = Exception("repo error")
        result_canonical, result_version = svc._load_canonical_for_version("p1", "v2")
        assert result_canonical is None
        assert result_version == "v2"
        deps.project_service.get_last_canonical.assert_not_called()

    def test_repo_fails_and_no_project_service_returns_none(self):
        """Covers the false branch of
        `if project_service is not None and hasattr(..., "get_last_canonical")`:
        when there's no usable project_service, the fallback is skipped."""
        svc, deps = _make_svc()
        deps.repository.get_project.side_effect = Exception("repo error")
        deps.project_service = None
        result_canonical, result_version = svc._load_canonical_for_version("p1", None)
        assert result_canonical is None
        assert result_version is None


# ─── get_cubo_analitico ───────────────────────────────────────────────────────


class TestGetCuboAnalitico:
    def test_returns_none_when_no_canonical(self):
        svc, deps = _make_svc()
        deps.repository.get_project.side_effect = Exception("not found")
        deps.project_service.get_last_canonical.return_value = None
        result = svc.get_cubo_analitico("p1")
        assert result["cubo_analitico"] is None

    def test_returns_cubo_from_canonical(self):
        svc, deps = _make_svc()
        cubo = MagicMock()
        cubo.to_dict.return_value = {"rows": []}
        canonical = MagicMock()
        canonical.cubo_analitico = cubo
        project = _make_project_mock()
        project.load_canonical.return_value = canonical
        deps.repository.get_project.return_value = project
        result = svc.get_cubo_analitico("p1", version="v1")
        assert result["cubo_analitico"] == {"rows": []}

    def test_builds_cubo_when_canonical_has_none(self):
        """Lines 622-624: CuboAnaliticoBuilder is invoked when canonical.cubo_analitico is None."""
        svc, deps = _make_svc()
        canonical = MagicMock()
        canonical.cubo_analitico = None  # force builder path
        project = _make_project_mock()
        project.load_canonical.return_value = canonical
        deps.repository.get_project.return_value = project
        from unittest.mock import patch

        mock_cubo = MagicMock()
        mock_cubo.to_dict.return_value = {"built": True}
        with patch(
            "concilium.domain.services.analytics.cubo_analitico_builder.CuboAnaliticoBuilder.build",
            return_value=mock_cubo,
        ):
            result = svc.get_cubo_analitico("p1")
        assert result["cubo_analitico"] is not None


# ─── get_cubo_projection_contract (static) ───────────────────────────────────


class TestGetCuboProjectionContract:
    def test_has_expected_faces(self):
        contract = ConciliumService.get_cubo_projection_contract()
        faces = set(contract["faces"])
        assert "tempo_natureza" in faces
        assert "abc_curva" in faces
        assert "s_curve_custo" in faces
        assert "recursos_ativos_tempo" in faces

    def test_granularidades_present(self):
        contract = ConciliumService.get_cubo_projection_contract()
        assert "mes" in contract["granularidades"]
        assert "semana" in contract["granularidades"]

    def test_abc_defaults_present(self):
        contract = ConciliumService.get_cubo_projection_contract()
        assert contract["abc_defaults"]["threshold_a"] == 0.80
        assert contract["abc_defaults"]["threshold_b"] == 0.95


# ─── get_cubo_pool_projection_contract (static) ───────────────────────────────


class TestGetCuboPoolProjectionContract:
    def test_returns_dict(self):
        with patch(
            "concilium.application.services.concilium_service.cubo_pool_projection_contract",
            return_value={"faces": {}},
            create=True,
        ):
            # patch the import inside the method
            with patch(
                "concilium.application.services.analytics.cubo_pool_projection.cubo_pool_projection_contract",
                return_value={"faces": {}},
                create=True,
            ):
                pass
        # Call through real import path
        result = ConciliumService.get_cubo_pool_projection_contract()
        assert isinstance(result, dict)


# ─── simulate_calendario_operacional ─────────────────────────────────────────


class TestSimulateCalendarioOperacional:
    def test_applies_overrides(self):
        svc, deps = _make_svc()
        base = {
            "version": "v1",
            "semanas": [
                {"semana_iso": "2024-W01", "fator_clima": 0.9, "fator_calendario": 0.8},
                {"semana_iso": "2024-W02", "fator_clima": 1.0, "fator_calendario": 1.0},
            ],
        }
        svc.get_calendario_operacional = MagicMock(return_value=base)
        payload = {"fator_calendario_semanal": {"2024-W01": 0.5}}
        result = svc.simulate_calendario_operacional("p1", payload, version="v1")
        assert result["version"] == "v1"
        # W01: fator_cal=0.5 (override), fator_clima=0.9 → fator_total=0.45
        w01 = next(r for r in result["simulado"] if r["semana_iso"] == "2024-W01")
        assert abs(w01["fator_total"] - 0.45) < 0.001
        # W02: no override, fator_cal=1.0, fator_clima=1.0 → fator_total=1.0
        w02 = next(r for r in result["simulado"] if r["semana_iso"] == "2024-W02")
        assert abs(w02["fator_total"] - 1.0) < 0.001

    def test_empty_payload(self):
        svc, deps = _make_svc()
        base = {
            "version": "v1",
            "semanas": [{"semana_iso": "2024-W01", "fator_clima": 1.0, "fator_calendario": 0.7}],
        }
        svc.get_calendario_operacional = MagicMock(return_value=base)
        result = svc.simulate_calendario_operacional("p1", {})
        assert len(result["simulado"]) == 1


# ─── get_cubo_analitico_projection validation ────────────────────────────────


class TestGetCuboAnaliticoProjectionValidation:
    def _make_projection_svc(self):
        svc, deps = _make_svc()
        # Make _load_canonical_for_version return None to short-circuit
        svc._load_canonical_for_version = MagicMock(return_value=(None, None))
        return svc

    def test_invalid_face_raises(self):
        svc = self._make_projection_svc()
        with pytest.raises(ValueError, match="Face de projeção não suportada"):
            svc.get_cubo_analitico_projection("p1", face="invalid_face")

    def test_invalid_granularidade_raises(self):
        svc = self._make_projection_svc()
        svc._load_canonical_for_version = MagicMock(return_value=(None, None))
        # Has to pass face validation first
        # With None canonical it returns early before validation, so give a real canonical
        canonical = MagicMock()
        cubo = MagicMock()
        cubo.slice.return_value = cubo
        cubo.total_preco_venda = 0
        cubo.total_custo_direto = 0
        cubo.total_overhead = 0
        cubo.total_margem = 0
        cubo.total_tributos = 0
        cubo.total_consumo_diesel_L = 0
        canonical.cubo_analitico = cubo
        svc._load_canonical_for_version = MagicMock(return_value=(canonical, "v1"))
        with pytest.raises(ValueError, match="Granularidade inválida"):
            svc.get_cubo_analitico_projection("p1", face="tempo_natureza", granularidade="decada")

    def test_returns_empty_rows_when_no_canonical(self):
        svc = self._make_projection_svc()
        result = svc.get_cubo_analitico_projection("p1", face="tempo_natureza")
        assert result["rows"] == []
        assert result["face"] == "tempo_natureza"


# ─── get_calendario_operacional (lines 536–568) ───────────────────────────────


class TestGetCalendarioOperacional:
    def test_returns_empty_semanas_when_no_canonical(self):
        svc, deps = _make_svc()
        deps.repository.get_project.side_effect = Exception("not found")
        deps.project_service.get_last_canonical.return_value = None
        result = svc.get_calendario_operacional("p1")
        assert result["semanas"] == []

    def test_returns_semanas_with_climate_factors_from_cronograma(self):
        """Lines 544-568: semanas enriched with fator_clima/fator_total from cronograma."""
        from types import SimpleNamespace

        svc, deps = _make_svc()

        dist = SimpleNamespace(fator_clima=0.9, fator_total=0.85, eficiencia=1.0)
        sa = MagicMock()
        sa.distribuicao_semanal = {"2026-W01": dist}

        cron = MagicMock()
        cron.scheduled_activities = [sa]

        cal_row = MagicMock()
        cal_row.model_dump.return_value = {"semana_iso": "2026-W01", "dias_uteis_base": 5}

        canonical = MagicMock()
        canonical.calendario_operacional = [cal_row]
        canonical.cronograma = cron

        project = _make_project_mock()
        project.load_canonical.return_value = canonical
        deps.repository.get_project.return_value = project

        result = svc.get_calendario_operacional("p1")
        assert len(result["semanas"]) == 1
        row = result["semanas"][0]
        assert row["fator_clima"] == pytest.approx(0.9, rel=1e-3)
        assert row["fator_total"] == pytest.approx(0.85, rel=1e-3)

    def test_returns_semanas_without_cronograma(self):
        """Lines 557-566: rows processed without cronograma factor enrichment."""
        svc, deps = _make_svc()

        cal_row = MagicMock()
        cal_row.model_dump.return_value = {"semana_iso": "2026-W02", "dias_uteis_base": 3}

        canonical = MagicMock()
        canonical.calendario_operacional = [cal_row]
        canonical.cronograma = None

        project = _make_project_mock()
        project.load_canonical.return_value = canonical
        deps.repository.get_project.return_value = project

        result = svc.get_calendario_operacional("p1")
        assert len(result["semanas"]) == 1
        assert result["semanas"][0]["fator_clima"] == pytest.approx(1.0)


# ─── get_cubo_pool_projection with real canonical (lines 649–673) ────────────


class TestGetCuboPoolProjectionWithCanonical:
    def test_returns_projection_when_canonical_exists(self):
        """Lines 649-673: projection result returned when canonical is not None."""
        from unittest.mock import patch

        svc, deps = _make_svc()
        canonical = MagicMock()
        project = _make_project_mock()
        project.load_canonical.return_value = canonical
        deps.repository.get_project.return_value = project

        mock_proj = {"face": "instancia_ciclo_vida", "rows": [], "version": "v1"}
        with patch(
            "concilium.application.services.analytics.cubo_pool_projection.resolve_cubo_pool_projection",
            return_value=mock_proj,
        ):
            result = svc.get_cubo_pool_projection("p1", face="instancia_ciclo_vida")
        assert result["face"] == "instancia_ciclo_vida"


# ─── get_cubo_estoque_consumivel_projection with real canonical (ADR-128 F6) ──


class TestGetCuboEstoqueConsumivelProjectionWithCanonical:
    def test_returns_projection_when_canonical_exists(self):
        from unittest.mock import patch

        svc, deps = _make_svc()
        canonical = MagicMock()
        project = _make_project_mock()
        project.load_canonical.return_value = canonical
        deps.repository.get_project.return_value = project

        mock_proj = {"face": "resumo_por_recurso", "rows": [], "version": "v1"}
        with patch(
            "concilium.application.services.analytics.cubo_estoque_consumivel_projection."
            "resolve_cubo_estoque_consumivel_projection",
            return_value=mock_proj,
        ):
            result = svc.get_cubo_estoque_consumivel_projection("p1", face="resumo_por_recurso")
        assert result["face"] == "resumo_por_recurso"

    def test_returns_empty_projection_when_canonical_none(self):
        svc, deps = _make_svc()
        project = _make_project_mock()
        project.load_canonical.return_value = None
        deps.repository.get_project.return_value = project

        result = svc.get_cubo_estoque_consumivel_projection("p1")
        assert result["rows"] == []
        assert result["invariantes_ok"] is True


# ─── get_cubo_estoque_consumivel_projection_contract (static, ADR-128 F6) ─────


class TestGetCuboEstoqueConsumivelProjectionContract:
    def test_returns_dict(self):
        result = ConciliumService.get_cubo_estoque_consumivel_projection_contract()
        assert isinstance(result, dict)
        assert "faces" in result


# ─── simulate/validate mobilizacao_policy (lines 936, 939) ───────────────────


class TestMobilizacaoPolicyDelegates:
    def test_simulate_mobilizacao_policy_delegates(self):
        """Line 936: delegates to _cs_simulate_mobilizacao_policy."""
        from unittest.mock import patch

        svc, _ = _make_svc()
        with patch(
            "concilium.application.services.concilium_service._mobilizacao_deliverables._cs_simulate_mobilizacao_policy",
            return_value={"ok": True},
        ) as mock_fn:
            result = svc.simulate_mobilizacao_policy("p1", {"items": []})
        mock_fn.assert_called_once()
        assert result == {"ok": True}

    def test_validate_mobilizacao_policies_delegates(self):
        """Line 939: delegates to _cs_validate_mobilizacao_policies."""
        from unittest.mock import patch

        svc, _ = _make_svc()
        with patch(
            "concilium.application.services.concilium_service._mobilizacao_deliverables._cs_validate_mobilizacao_policies",
            return_value=[],
        ) as mock_fn:
            result = svc.validate_mobilizacao_policies("p1")
        mock_fn.assert_called_once()
        assert result == []
