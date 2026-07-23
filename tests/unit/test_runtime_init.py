"""Coverage sweep 2 — medium missing-line files (8-25 lines)."""

from __future__ import annotations

import json
from datetime import UTC, date, datetime
from pathlib import Path
from unittest.mock import patch

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
        config_root = Path(__file__).parents[3] / "config"
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

        config_root = Path(__file__).parents[3] / "config"
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

