"""Coverage sweep 2 — medium missing-line files (8-25 lines)."""

from __future__ import annotations

import json
from datetime import UTC, date, datetime
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from concilium.application.runtime import Runtime
from concilium.domain.models.canonical import (
    CanonicalModel,
    Coordenadas,
    Meta,
    Projeto,
    RegimeTrabalho,
)


def _make_meta():
    return Meta(gerado_em=datetime.now(UTC), contexto_id="test")

def _make_proj(data_inicio="2026-06-01", data_termino="2026-07-31"):
    return Projeto(
        id="p1",
        nome="proj",
        tipo_obra="terraplenagem",
        localizacao="x",
        coordenadas=Coordenadas(lat=-3.0, lng=-38.0),
        regime_trabalho=RegimeTrabalho(dias_semana=5, horas_dia=8),
        data_inicio=date(2026, 6, 1),
        data_termino=date(2026, 7, 31),
        snapshot_catalogo_id="s",
        snapshot_perfil_id="s",
    )

def _minimal_canonical(**kw):
    return CanonicalModel(meta=_make_meta(), projeto=_make_proj(), **kw)

def _load_skill_module(skill_id: str) -> object:
    import concilium.application.skills as _skills_pkg

    return _skills_pkg._load_skill_module(skill_id)


# ─── application/runtime/__init__ ────────────────────────────────────────────


class TestRuntimeInit:
    def test_runtime_imports(self):
        from concilium.application.runtime import Runtime

        assert Runtime is not None

    def test_runtime_error_importable(self):
        from concilium.application.runtime import RuntimeError as ConciliumRuntimeError

        assert issubclass(ConciliumRuntimeError, Exception)

    def test_runtime_instantiation(self, tmp_path):
        from concilium.application.runtime import Runtime

        rt = Runtime(tmp_path)
        assert rt is not None
        assert rt.config_root == tmp_path


# ══ runtime.py ════════════════════════════════════════════════════════════════


class TestRuntimeEdgeCases:
    def test_load_referencia_success(self, tmp_path):
        """load_referencia success path (line 58)."""
        from concilium.application.runtime import Runtime

        refs_dir = tmp_path / "referencias"
        refs_dir.mkdir()
        (refs_dir / "test.json").write_text(json.dumps({"tabela": "SICRO"}), encoding="utf-8")
        r = Runtime(tmp_path)
        result = r.load_referencia("test")
        assert result == {"tabela": "SICRO"}

    def test_load_catalogo_dict_no_matching_key(self, tmp_path):
        """cpus.json is a dict without 'cpus' key → data.get(key, []) (line 79)."""
        from concilium.application.runtime import Runtime

        cat_dir = tmp_path / "catalogos" / "mycat"
        cat_dir.mkdir(parents=True)
        # Dict without 'cpus' key → falls into else branch
        (cat_dir / "cpus.json").write_text(json.dumps({"other_key": "val"}), encoding="utf-8")
        r = Runtime(tmp_path)
        cat = r.load_catalogo("mycat")
        assert cat["cpus"] == []

    def test_load_insumos_bad_json(self, tmp_path):
        """Bad JSON in insumos file → except Exception: continue (lines 97-98)."""
        from concilium.application.runtime import Runtime

        cat_dir = tmp_path / "catalogos" / "mycat"
        (cat_dir / "insumos").mkdir(parents=True)
        (cat_dir / "insumos" / "mao_obra.json").write_text("NOT JSON!!!", encoding="utf-8")
        r = Runtime(tmp_path)
        insumos = r._load_insumos(cat_dir)
        assert insumos == []

    def test_load_insumos_dict_with_insumos_key(self, tmp_path):
        """Insumos file is a dict with 'insumos' key → extend (line 101)."""
        from concilium.application.runtime import Runtime

        cat_dir = tmp_path / "catalogos" / "mycat"
        (cat_dir / "insumos").mkdir(parents=True)
        data = {"insumos": [{"codigo": "MAO-01", "tipo": "MAO_OBRA", "descricao": "test", "preco_unitario": 10}]}
        (cat_dir / "insumos" / "mao_obra.json").write_text(json.dumps(data), encoding="utf-8")
        r = Runtime(tmp_path)
        insumos = r._load_insumos(cat_dir)
        assert len(insumos) == 1
        assert insumos[0]["codigo"] == "MAO-01"

    def test_check_manifest_deps_blank_line_skipped(self, tmp_path):
        """Blank lines in invocations log are skipped (line 136)."""
        from concilium.application.runtime import Runtime
        from concilium.infrastructure.storage.project import ProjectStore

        r = Runtime(tmp_path / "config")
        projetos = tmp_path / "projetos"
        projetos.mkdir()
        project = ProjectStore.init(projetos, "test-proj", "test")
        v = project.new_version()
        log_path = project.version_path(v) / project.INVOCATIONS_LOG
        log_path.parent.mkdir(parents=True, exist_ok=True)
        # Write log with blank lines and valid entries
        log_path.write_text(
            '{"skill": "02-produtividade-climatica", "status": "OK"}\n'
            "\n"  # blank line — triggers continue at line 136
            "   \n"  # whitespace-only line
            '{"skill": "01-escopo-e-eap", "status": "OK"}\n',
            encoding="utf-8",
        )
        # Patch load_manifest to return deps so we exercise the log parsing
        with patch.object(r, "load_manifest", return_value={"depends_on": {"skills": ["02-produtividade-climatica"]}}):
            deps = r.check_manifest_deps("04-cronograma", project, v)
        # 02-produtividade-climatica is in the log as OK → no missing deps
        assert "02-produtividade-climatica" not in deps

    def test_run_skill_raises_for_missing_deps(self, tmp_path):
        """run_skill raises RuntimeError when check_manifest_deps returns missing (line 185)."""
        from concilium.application.runtime import Runtime
        from concilium.application.runtime import RuntimeError as ConciliumRE
        from concilium.infrastructure.storage.project import ProjectStore

        # Use test config_root from actual config dir
        config_root = Path(__file__).parents[5] / "config"
        r = Runtime(config_root)
        projetos = tmp_path / "projetos"
        projetos.mkdir()
        project = ProjectStore.init(projetos, "test-missing-deps", "test")
        v = project.new_version()
        # Patch check_manifest_deps to simulate missing deps
        with patch.object(r, "check_manifest_deps", return_value=["02-produtividade-climatica"]):
            with pytest.raises(ConciliumRE, match="requer execução prévia"):
                r.run_skill("04-cronograma", project, v)

    def test_plan_with_decisions_calls_adjust_schedule(self):
        """plan_with_decisions calls adjust_schedule (lines 333-335)."""
        from concilium.application.runtime import Runtime
        from concilium.domain.models.project.decision_variables import DecisionVariables

        config_root = Path(__file__).parents[5] / "config"
        r = Runtime(config_root)
        canonical = _minimal_canonical()
        dv = DecisionVariables()
        perfil = {"categorias_indireto": []}
        # adjust_schedule is imported locally inside plan_with_decisions;
        # patch it at its source module
        with patch(
            "concilium.application.optimizer.loop.adjust_schedule", return_value=(canonical, True, [])
        ) as mock_adj:
            r.plan_with_decisions(canonical, dv, perfil=perfil)
        mock_adj.assert_called_once()






# runtime.py: RuntimeError re-raise (line 278)
# ────────────────────────────────────────────────────────────────


class TestRuntimeErrorHandling:
    """Test RuntimeError re-raising in runtime."""

    def test_runtime_error_reraise(self, tmp_path):
        """RuntimeError should be re-raised, not wrapped."""
        from concilium.application.runtime import RuntimeError as ConciliumRuntimeError

        runtime = Runtime(tmp_path)

        # Create required directories
        (tmp_path / "contextos").mkdir()
        (tmp_path / "jurisdicoes").mkdir()
        (tmp_path / "perfis").mkdir()
        (tmp_path / "referencias").mkdir()
        (tmp_path / "catalogos").mkdir()

        # Try to load non-existent items to trigger RuntimeError path
        with pytest.raises(ConciliumRuntimeError):
            runtime.load_contexto("nonexistent")


# ────────────────────────────────────────────────────────────────



# runtime/__init__.py line 178:
# Runtime._meta_is_gate returns gate flag from MANIFEST_META
# ---------------------------------------------------------------------------


class TestRuntimeMetaIsGate:
    def _make_runtime(self, tmp_path):
        from concilium.application.runtime import Runtime

        return Runtime(config_root=tmp_path)

    def test_meta_is_gate_returns_false_for_unknown_skill(self, tmp_path):
        """Line 178: MANIFEST_META.get unknown → {} → .get("gate", False) → False."""
        rt = self._make_runtime(tmp_path)
        result = rt._meta_is_gate("99-nonexistent-skill")
        assert result is False

    def test_meta_is_gate_returns_false_for_non_gate_skill(self, tmp_path):
        """Line 178: known skill with gate=False → False."""
        rt = self._make_runtime(tmp_path)
        # "05-equipes-e-alocacao" has gate=False in MANIFEST_META
        result = rt._meta_is_gate("05-equipes-e-alocacao")
        assert result is False

    def test_meta_is_gate_returns_true_for_gate_skill(self, tmp_path):
        """Line 178: known skill with gate=True → True."""
        rt = self._make_runtime(tmp_path)
        result = rt._meta_is_gate("01-escopo-e-eap")
        assert result is True



# execution.py line 106:
# run_skill_on_plano when canonical_in is None and skill != "01-escopo-e-eap"
# → raises RuntimeDomainError
# ---------------------------------------------------------------------------


class TestRunSkillOnPlanoNoCanonical:
    def test_raises_runtime_domain_error_when_no_canonical(self):
        """Line 106: canonical_in is None and skill_id != '01-escopo-e-eap' → RuntimeDomainError."""
        from types import SimpleNamespace
        from unittest.mock import MagicMock

        import pytest

        from concilium.application.runtime.exceptions import RuntimeDomainError
        from concilium.application.runtime.mixins.execution import ExecutionMixin

        class FakeRuntime(ExecutionMixin):
            def get_skill_contract(self, skill_id):
                return MagicMock(signature=[])

        runtime = FakeRuntime()
        plano_store = SimpleNamespace(
            load_canonical=lambda: None,
            plano_id="plano-001",
            escopo_store=SimpleNamespace(meta={}),
        )

        with pytest.raises(RuntimeDomainError, match="estado inicial"):
            runtime.run_skill_on_plano(
                "02-produtividade-climatica",
                MagicMock(),
                plano_store,
            )


class TestRunSkillOnPlanoShouldSaveFalse:
    def test_00_escopo_with_errors_skips_save_canonical(self):
        """Branch 153->156: skill_id=='00-escopo' com erros e sem gate/dv override
        → should_save permanece False → save_canonical NÃO é chamado."""
        from types import SimpleNamespace
        from unittest.mock import MagicMock, patch

        from concilium.application.runtime.mixins.execution import ExecutionMixin
        from concilium.application.skills.base import SkillResult
        from concilium.domain.models.canonical import ValidacaoItem

        canonical = MagicMock()
        canonical.pipeline_blocked_from = []
        val_erro = ValidacaoItem(codigo="ERR-001", status="ERRO", campo=None, mensagem="erro")
        fake_result = SkillResult(canonical, [val_erro])

        class FakeRuntime(ExecutionMixin):
            def get_skill_contract(self, skill_id):
                return MagicMock(signature=[])

            def _load_context(self, escopo_meta, project):
                return MagicMock(), {}, {}

            def _apply_runtime_defaults(self, skill_id, project, contexto, base_inputs):
                return dict(base_inputs)

            def _build_skill_kwargs(self, contract, **kwargs):
                return {}

            def _build_log_entry(self, *args, **kwargs):
                return {}

            def _process_side_effects(self, *args, **kwargs):
                pass

        runtime = FakeRuntime()
        plano_store = SimpleNamespace(
            load_canonical=lambda: canonical,
            plano_id="plano-001",
            escopo_store=SimpleNamespace(meta={"escopo_id": "e1", "contexto_id": "ctx"}),
            save_canonical=MagicMock(),
            log_invocation=MagicMock(),
            read_premissas_por_skill=MagicMock(return_value={}),
            write_premissas_efetivas=MagicMock(),
        )
        project = SimpleNamespace(meta={"id": "proj-1"})

        with (
            patch("concilium.application.runtime.mixins.execution.SKILLS", {"00-escopo": MagicMock()}),
            patch(
                "concilium.application.runtime.mixins.execution._execute_skill",
                return_value=fake_result,
            ),
        ):
            runtime.run_skill_on_plano("00-escopo", project, plano_store)

        plano_store.save_canonical.assert_not_called()


class TestRunSkillOnPlanoStalenessWiring:
    """issue #121: run_skill_on_plano de fato congela premissas e detecta staleness
    ponta a ponta (PlanoStore/EscopoStore reais em disco, não mockados)."""

    def _make_stores(self, tmp_path):
        from concilium.domain.models.canonical import CanonicalModel
        from concilium.infrastructure.storage.escopo_store import EscopoStore

        escopo_root = tmp_path / "escopos" / "esc-1"
        escopo_root.mkdir(parents=True)
        (escopo_root / "escopo.json").write_text('{"escopo_id": "esc-1", "jurisdicao_id": "sp"}', encoding="utf-8")
        es = EscopoStore(root=escopo_root)
        plano_store = es.plan("plan-1")
        plano_store.root.mkdir(parents=True)

        canonical = CanonicalModel.model_validate(
            {
                "meta": {"gerado_em": "2026-01-01T00:00:00Z", "contexto_id": "ctx-test"},
                "projeto": {
                    "id": "proj-test",
                    "nome": "Test Project",
                    "tipo_obra": "terraplenagem",
                    "localizacao": "SP",
                    "coordenadas": {"lat": -23.5, "lng": -46.6},
                    "regime_trabalho": {"dias_semana": 6, "horas_dia": 8},
                    "data_inicio": "2026-01-01",
                    "data_termino": "2026-12-31",
                    "snapshot_catalogo_id": "cat-v1",
                    "snapshot_perfil_id": "perf-v1",
                },
            }
        )
        (plano_store.root / plano_store.CANONICAL_FILE).write_text(
            canonical.model_dump_json(indent=2), encoding="utf-8"
        )
        return es, plano_store, canonical

    def _make_fake_runtime(self, depends_on_skills):
        from types import SimpleNamespace
        from unittest.mock import MagicMock

        from concilium.application.runtime.mixins.execution import ExecutionMixin

        class FakeRuntime(ExecutionMixin):
            def get_skill_contract(self, skill_id):
                return SimpleNamespace(depends_on_skills=depends_on_skills.get(skill_id, []))

            def _load_context(self, escopo_meta, project):
                return MagicMock(), {}, {}

            def _apply_runtime_defaults(self, skill_id, project, contexto, base_inputs):
                return dict(base_inputs)

            def _build_skill_kwargs(self, contract, **kwargs):
                return {}

            def _build_log_entry(self, *args, **kwargs):
                return {}

            def _process_side_effects(self, *args, **kwargs):
                pass

        return FakeRuntime()

    def test_dependencia_com_escopo_alterado_emite_stale_upstream(self, tmp_path):
        from unittest.mock import MagicMock, patch

        from concilium.application.skills.base import SkillResult
        from concilium.domain.models.canonical import ValidacaoItem

        es, plano_store, canonical = self._make_stores(tmp_path)
        runtime = self._make_fake_runtime({"06-resultado-financeiro": ["04-cronograma"]})
        project = MagicMock()
        project.meta = {"id": "proj-1"}

        with (
            patch("concilium.application.runtime.mixins.execution.SKILLS", {"04-cronograma": MagicMock()}),
            patch(
                "concilium.application.runtime.mixins.execution._execute_skill",
                return_value=SkillResult(canonical, [ValidacaoItem(codigo="OK-01", status="OK", mensagem="ok")]),
            ),
        ):
            runtime.run_skill_on_plano("04-cronograma", project, plano_store)

        # Premissas de "04-cronograma" congeladas com jurisdicao_id="sp".
        por_skill = plano_store.read_premissas_por_skill()
        assert "04-cronograma" in por_skill

        # Escopo muda de jurisdição sem reexecutar a cadeia inteira.
        es.update_meta(jurisdicao_id="rj")

        with (
            patch("concilium.application.runtime.mixins.execution.SKILLS", {"06-resultado-financeiro": MagicMock()}),
            patch(
                "concilium.application.runtime.mixins.execution._execute_skill",
                return_value=SkillResult(canonical, []),
            ),
        ):
            result = runtime.run_skill_on_plano("06-resultado-financeiro", project, plano_store)

        codigos = [v.codigo for v in result.validacoes]
        assert "VAL-STALE-UPSTREAM" in codigos
        assert result.has_errors is False

    def test_sem_mudanca_de_escopo_nao_emite_stale_upstream(self, tmp_path):
        from unittest.mock import MagicMock, patch

        from concilium.application.skills.base import SkillResult
        from concilium.domain.models.canonical import ValidacaoItem

        _es, plano_store, canonical = self._make_stores(tmp_path)
        runtime = self._make_fake_runtime({"06-resultado-financeiro": ["04-cronograma"]})
        project = MagicMock()
        project.meta = {"id": "proj-1"}

        with (
            patch("concilium.application.runtime.mixins.execution.SKILLS", {"04-cronograma": MagicMock()}),
            patch(
                "concilium.application.runtime.mixins.execution._execute_skill",
                return_value=SkillResult(canonical, [ValidacaoItem(codigo="OK-01", status="OK", mensagem="ok")]),
            ),
        ):
            runtime.run_skill_on_plano("04-cronograma", project, plano_store)

        with (
            patch("concilium.application.runtime.mixins.execution.SKILLS", {"06-resultado-financeiro": MagicMock()}),
            patch(
                "concilium.application.runtime.mixins.execution._execute_skill",
                return_value=SkillResult(canonical, []),
            ),
        ):
            result = runtime.run_skill_on_plano("06-resultado-financeiro", project, plano_store)

        assert "VAL-STALE-UPSTREAM" not in [v.codigo for v in result.validacoes]


# ─── application/runtime/__init__.py (30 missing) ─────────────────────────────


class TestRuntimeInit2:
    def test_runtime_importable(self):
        from concilium.application.runtime import Runtime

        assert Runtime is not None

    def test_runtime_init(self, tmp_path):
        from concilium.application.runtime import Runtime

        rt = Runtime(config_root=tmp_path)
        assert rt is not None

    def test_runtime_has_run_pipeline(self, tmp_path):
        from concilium.application.runtime import Runtime

        rt = Runtime(config_root=tmp_path)
        assert hasattr(rt, "run_pipeline")




# ─── application/runtime/__init__.py extended tests ────────────────────────────


class TestRuntimeRunPipeline:
    """Test run_pipeline which covers lines 112-148."""

    def test_run_pipeline_no_active_version_raises(self, tmp_path):
        from concilium.application.runtime import Runtime, RuntimeDomainError

        rt = Runtime(config_root=tmp_path)
        store = MagicMock()
        store.current_version.return_value = None
        with pytest.raises(RuntimeDomainError, match="versão"):
            rt.run_pipeline(store)

    def test_run_pipeline_with_version(self, tmp_path):
        from concilium.application.runtime import Runtime

        rt = Runtime(config_root=tmp_path)
        store = MagicMock()
        store.current_version.return_value = "v1"
        store.load_canonical.return_value = None
        store.meta = {"contexto_id": "ctx-1", "id": "proj-1"}
        store.root = MagicMock()
        store.root.name = "proj-dir"

        # Mock out _providers_factory to avoid loading real catalogs
        with patch.object(
            rt,
            "_providers_factory",
            return_value={
                "canonical_in": None,
                "inputs": {},
                "catalogo": {},
                "catalog_session": None,
                "perfil": {},
                "contexto": MagicMock(),
                "project": store,
                "version": "v1",
                "runtime": rt,
            },
        ):
            with patch("concilium.application.runtime.SkillExecutor") as mock_executor_cls:
                executor = MagicMock()
                executor.run_pipeline.return_value = (None, [])
                mock_executor_cls.return_value = executor
                result = rt.run_pipeline(store, skill_sequence=["01-escopo-e-eap"])
        assert isinstance(result, list)

    def test_run_pipeline_with_existing_canonical_skips_bootstrap(self, tmp_path):
        """load_canonical() já não-None -> skip_bootstrap=True -> 01-escopo-e-eap removido."""
        from concilium.application.runtime import Runtime

        rt = Runtime(config_root=tmp_path)
        store = MagicMock()
        store.current_version.return_value = "v1"
        store.load_canonical.return_value = MagicMock()  # canônico já existe
        store.meta = {"contexto_id": "ctx-1", "id": "proj-1"}
        store.root = MagicMock()
        store.root.name = "proj-dir"

        with patch.object(
            rt,
            "_providers_factory",
            return_value={
                "canonical_in": None,
                "inputs": {},
                "catalogo": {},
                "catalog_session": None,
                "perfil": {},
                "contexto": MagicMock(),
                "project": store,
                "version": "v1",
                "runtime": rt,
            },
        ):
            with patch("concilium.application.runtime.SkillExecutor") as mock_executor_cls:
                executor = MagicMock()
                executor.run_pipeline.return_value = (None, [])
                mock_executor_cls.return_value = executor
                rt.run_pipeline(store, skill_sequence=["01-escopo-e-eap", "02-cronograma"])

        active_skills_arg = mock_executor_cls.call_args[0][0]
        assert "01-escopo-e-eap" not in active_skills_arg

