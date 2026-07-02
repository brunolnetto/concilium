"""Tests for service-layer modules to boost coverage."""

from __future__ import annotations

from datetime import datetime
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

# ─── BenchmarkDiffService ───────────────────────────────────────────────────


class TestBenchmarkDiffService:
    def _make_exec(self, exec_id, benchmark_id, versao, discrepancia=None):
        return SimpleNamespace(
            execution_id=exec_id,
            benchmark_id=benchmark_id,
            versao=versao,
            discrepancia_sumario=discrepancia or {},
        )

    def test_compare_happy_path(self):
        from concilium.application.benchmarks.diff_service import BenchmarkDiffService

        svc = BenchmarkDiffService()
        e1 = self._make_exec("e1", "BENCH", 1)
        e2 = self._make_exec(
            "e2",
            "BENCH",
            2,
            {"delta_custo_direto": 5.0, "delta_cronograma": 2, "delta_margem_lucro": -1.5, "itens_impactados": 3},
        )
        result = svc.compare(e1, e2)
        assert result.delta_custo_direto_percentual == 5.0
        assert result.delta_cronograma_semanas == 2
        assert result.delta_margem_lucro_percentual == -1.5
        assert result.itens_impactados == 3
        assert result.benchmark_id == "BENCH"
        assert result.comparado_em is not None

    def test_compare_different_benchmark_raises(self):
        from concilium.application.benchmarks.diff_service import BenchmarkDiffService

        svc = BenchmarkDiffService()
        e1 = self._make_exec("e1", "A", 1)
        e2 = self._make_exec("e2", "B", 2)
        with pytest.raises(ValueError, match="diferentes"):
            svc.compare(e1, e2)

    def test_compare_zero_deltas(self):
        from concilium.application.benchmarks.diff_service import BenchmarkDiffService

        svc = BenchmarkDiffService()
        e1 = self._make_exec("e1", "B", 1)
        e2 = self._make_exec("e2", "B", 2)
        result = svc.compare(e1, e2)
        assert result.delta_custo_direto_percentual == 0.0
        assert "sem mudança" in result.interpretacao.lower() or len(result.interpretacao) > 0

    def test_to_dict(self):
        from concilium.application.benchmarks.diff_service import BenchmarkDiffResult

        r = BenchmarkDiffResult(
            execution_1_id="e1",
            execution_2_id="e2",
            benchmark_id="B",
            versao_1=1,
            versao_2=2,
            delta_custo_direto_percentual=3.0,
            delta_cronograma_semanas=1,
            delta_margem_lucro_percentual=-0.5,
            itens_impactados=2,
            interpretacao="test",
            comparado_em=datetime(2026, 1, 1),
        )
        d = r.to_dict()
        assert d["benchmark_id"] == "B"
        assert d["delta_custo_direto_percentual"] == 3.0
        assert d["comparado_em"] is not None

    def test_to_dict_no_comparado_em(self):
        from concilium.application.benchmarks.diff_service import BenchmarkDiffResult

        r = BenchmarkDiffResult(
            execution_1_id="e1",
            execution_2_id="e2",
            benchmark_id="B",
            versao_1=1,
            versao_2=2,
            delta_custo_direto_percentual=0.0,
            delta_cronograma_semanas=0,
            delta_margem_lucro_percentual=0.0,
        )
        assert r.to_dict()["comparado_em"] is None


# ─── OverrideService ────────────────────────────────────────────────────────


class TestOverrideService:
    def _make_svc(self):
        from concilium.application.services.project.override_service import OverrideService

        repo = MagicMock()
        audit = MagicMock()
        return OverrideService(repo, audit), repo, audit

    def test_extend_cpu_calls_project_and_audit(self):
        svc, repo, audit = self._make_svc()
        mock_proj = MagicMock()
        repo.get_project.return_value = mock_proj
        svc.extend_cpu("proj-1", "cpu-1", {"field": "val"}, actor="eng")
        mock_proj.extend_cpu.assert_called_once_with("cpu-1", {"field": "val"}, actor="eng", motivo="")
        audit.log.assert_called_once()

    def test_resolve_cpu_delegates(self):
        svc, repo, audit = self._make_svc()
        mock_proj = MagicMock()
        mock_proj.resolve_cpu.return_value = {"id": "cpu-1"}
        repo.get_project.return_value = mock_proj
        result = svc.resolve_cpu("proj-1", "cpu-1")
        assert result == {"id": "cpu-1"}

    def test_list_overrides(self):
        svc, repo, audit = self._make_svc()
        mock_proj = MagicMock()
        mock_proj.read_json.return_value = {"skill-01": {"x": 1}}
        repo.get_project.return_value = mock_proj
        result = svc.list_overrides("proj-1")
        assert "skill-01" in result

    def test_upsert_override_merges(self):
        svc, repo, audit = self._make_svc()
        mock_proj = MagicMock()
        mock_proj.read_json.return_value = {"skill-01": {"existing": True}}
        repo.get_project.return_value = mock_proj
        svc.upsert_override("proj-1", "skill-01", {"new_key": "val"}, actor="eng")
        mock_proj.write_json.assert_called_once()
        audit.log.assert_called_once()

    def test_delete_override(self):
        svc, repo, audit = self._make_svc()
        mock_proj = MagicMock()
        mock_proj.read_json.return_value = {"skill-01": {}, "skill-02": {}}
        repo.get_project.return_value = mock_proj
        svc.delete_override("proj-1", "skill-01")
        written = mock_proj.write_json.call_args[0][1]
        assert "skill-01" not in written
        assert "skill-02" in written

    def test_list_overrides_empty(self):
        svc, repo, audit = self._make_svc()
        mock_proj = MagicMock()
        mock_proj.read_json.return_value = {}
        repo.get_project.return_value = mock_proj
        result = svc.list_overrides("proj-1")
        assert result == {}


# ─── ProjectInputBuilder ────────────────────────────────────────────────────


class TestProjectInputBuilder:
    def _make_builder(self, tmp_path):
        from concilium.application.services.project.project_input_builder import ProjectInputBuilder

        return ProjectInputBuilder(config_root=tmp_path / "config", benchmarks_root=tmp_path / "benchmarks")

    def test_prepare_without_benchmark_builds_inputs(self, tmp_path):
        builder = self._make_builder(tmp_path)
        req = MagicMock()
        req.benchmark_slug = None
        req.referencia_path = None
        req.nome = "Projeto Teste"
        req.tipo_obra = "terraplenagem"
        req.localizacao = "Fortaleza, CE"
        req.coordenadas_lat = -3.7
        req.coordenadas_lng = -38.5
        req.dias_semana = 6
        req.horas_dia = 8
        req.data_inicio = "2026-01-01"
        req.data_termino = "2026-12-31"
        req.eap = []
        req.cronograma = None
        req.inputs_indiretos = None
        req.contexto_id = "mendeslobo"
        req.coordenadas = None
        result = builder.prepare(req)
        assert result.inputs_escopo["nome"] == "Projeto Teste"
        assert result.benchmark_slug is None

    def test_prepare_with_benchmark_slug_not_found_raises(self, tmp_path):
        builder = self._make_builder(tmp_path)
        req = MagicMock()
        req.benchmark_slug = "MISSING"
        req.referencia_path = None
        with patch(
            "concilium.application.services.project.project_input_builder.find_benchmark_reference", return_value=None
        ):
            with pytest.raises(FileNotFoundError):
                builder.prepare(req)

    def test_prepare_with_referencia_path_not_found_raises(self, tmp_path):
        builder = self._make_builder(tmp_path)
        req = MagicMock()
        req.benchmark_slug = None
        req.referencia_path = str(tmp_path / "nonexistent.json")
        with pytest.raises(FileNotFoundError):
            builder.prepare(req)

    def test_prepare_with_valid_referencia_path(self, tmp_path):
        import json

        ref_data = {
            "slug": "TEST",
            "contexto_id": "mendeslobo",
            "meta": {"nome": "Test", "tipo_obra": "terraplenagem"},
            "spec": {"eap": [], "cronograma": []},
        }
        ref_path = tmp_path / "referencia.json"
        ref_path.write_text(json.dumps(ref_data), encoding="utf-8")
        builder = self._make_builder(tmp_path)
        req = MagicMock()
        req.benchmark_slug = None
        req.referencia_path = str(ref_path)
        mock_spec = MagicMock()
        mock_spec.slug = "TEST"
        mock_spec.contexto_id = "mendeslobo"
        mock_spec.contexto_version = "v1"
        mock_spec.perfil_id = None
        mock_spec.perfil_version = None
        mock_spec.inputs_escopo = {"tipo_obra": "terraplenagem"}
        mock_spec.inputs_cronograma = None
        mock_spec.inputs_indiretos = None
        mock_spec.extra_inputs = {}
        with patch(
            "concilium.application.services.project.project_input_builder.BenchmarkSpecLoader"
        ) as mock_loader_cls:
            mock_loader = MagicMock()
            mock_loader.load.return_value = mock_spec
            mock_loader_cls.return_value = mock_loader
            result = builder.prepare(req)
        assert result.benchmark_slug == "TEST"
        assert result.contexto_version == "v1"

    def test_build_skill_inputs_from_spec_with_inputs_cronograma(self, tmp_path):
        """Line 82: spec.inputs_cronograma populated → adds '04-cronograma' key."""
        import json

        from concilium.application.services.project.project_input_builder import ProjectInputBuilder

        ref_data = {"slug": "TEST4", "contexto_id": "mendeslobo"}
        ref_path = tmp_path / "referencia.json"
        ref_path.write_text(json.dumps(ref_data), encoding="utf-8")
        builder = ProjectInputBuilder(config_root=tmp_path / "config", benchmarks_root=tmp_path / "benchmarks")
        req = MagicMock()
        req.benchmark_slug = None
        req.referencia_path = str(ref_path)
        mock_spec = MagicMock()
        mock_spec.slug = "TEST4"
        mock_spec.contexto_id = "mendeslobo"
        mock_spec.contexto_version = "v1"
        mock_spec.perfil_id = None
        mock_spec.perfil_version = None
        mock_spec.inputs_escopo = {"tipo_obra": "terraplenagem"}
        mock_spec.inputs_01A = None
        mock_spec.inputs_cronograma = {"precedence": []}  # non-empty → line 82
        mock_spec.inputs_indiretos = None
        mock_spec.extra_inputs = {}
        with patch("concilium.application.services.project.project_input_builder.BenchmarkSpecLoader") as mock_cls:
            mock_loader = MagicMock()
            mock_loader.load.return_value = mock_spec
            mock_cls.return_value = mock_loader
            result = builder.prepare(req)
        assert "04-cronograma" in result.skill_inputs

    def test_build_skill_inputs_from_spec_with_inputs_01A(self, tmp_path):
        """Line 80: spec.inputs_01A populated → adds '03-catalogo-de-recursos' key."""
        import json

        from concilium.application.services.project.project_input_builder import ProjectInputBuilder

        ref_data = {"slug": "TEST2", "contexto_id": "mendeslobo"}
        ref_path = tmp_path / "referencia.json"
        ref_path.write_text(json.dumps(ref_data), encoding="utf-8")
        builder = ProjectInputBuilder(config_root=tmp_path / "config", benchmarks_root=tmp_path / "benchmarks")
        req = MagicMock()
        req.benchmark_slug = None
        req.referencia_path = str(ref_path)
        mock_spec = MagicMock()
        mock_spec.slug = "TEST2"
        mock_spec.contexto_id = "mendeslobo"
        mock_spec.contexto_version = "v1"
        mock_spec.perfil_id = None
        mock_spec.perfil_version = None
        mock_spec.inputs_escopo = {"tipo_obra": "terraplenagem"}
        mock_spec.inputs_01A = {"cpu_ids": ["CPU-001"]}  # non-empty → line 82
        mock_spec.inputs_cronograma = None
        mock_spec.inputs_indiretos = None
        mock_spec.extra_inputs = {}
        with patch("concilium.application.services.project.project_input_builder.BenchmarkSpecLoader") as mock_cls:
            mock_loader = MagicMock()
            mock_loader.load.return_value = mock_spec
            mock_cls.return_value = mock_loader
            result = builder.prepare(req)
        assert "03-catalogo-de-recursos" in result.skill_inputs

    def test_build_skill_inputs_from_spec_with_inputs_indiretos(self, tmp_path):
        """Line 86: spec.inputs_indiretos populated → merges into '06-resultado-financeiro'."""
        import json

        from concilium.application.services.project.project_input_builder import ProjectInputBuilder

        ref_data = {"slug": "TEST3", "contexto_id": "mendeslobo"}
        ref_path = tmp_path / "referencia.json"
        ref_path.write_text(json.dumps(ref_data), encoding="utf-8")
        builder = ProjectInputBuilder(config_root=tmp_path / "config", benchmarks_root=tmp_path / "benchmarks")
        req = MagicMock()
        req.benchmark_slug = None
        req.referencia_path = str(ref_path)
        mock_spec = MagicMock()
        mock_spec.slug = "TEST3"
        mock_spec.contexto_id = "mendeslobo"
        mock_spec.contexto_version = "v1"
        mock_spec.perfil_id = None
        mock_spec.perfil_version = None
        mock_spec.inputs_escopo = {"tipo_obra": "terraplenagem"}
        mock_spec.inputs_01A = None
        mock_spec.inputs_cronograma = None
        mock_spec.inputs_indiretos = {"bdi_pct": 25.0}  # non-empty → line 86
        mock_spec.extra_inputs = {}
        with patch("concilium.application.services.project.project_input_builder.BenchmarkSpecLoader") as mock_cls:
            mock_loader = MagicMock()
            mock_loader.load.return_value = mock_spec
            mock_cls.return_value = mock_loader
            result = builder.prepare(req)
        assert "06-resultado-financeiro" in result.skill_inputs
        assert result.skill_inputs["06-resultado-financeiro"]["bdi_pct"] == 25.0
