"""Tests for small-gap files: benchmark repository port, week_sequence, config mixin,
permission_guard, rate_limit, jwt_auth, replan MCP tool."""

from __future__ import annotations

import json

import pytest

# ─── application/runtime/mixins/config.py ─────────────────────────────────────


class TestConfigMixin:
    def _make(self, tmp_path):
        from concilium.application.runtime.mixins.config import ConfigMixin

        return ConfigMixin(config_root=tmp_path)

    def test_load_tema_default_when_missing(self, tmp_path):
        cm = self._make(tmp_path)
        tema = cm.load_tema()  # no tema dir → falls back to TEMA_DEFAULT
        assert tema is not None

    def test_load_tema_cached(self, tmp_path):
        cm = self._make(tmp_path)
        t1 = cm.load_tema()
        t2 = cm.load_tema()
        assert t1 is t2

    def test_load_tema_invalid_json_returns_default(self, tmp_path):
        tema_dir = tmp_path / "temas" / "custom"
        tema_dir.mkdir(parents=True)
        (tema_dir / "tema.json").write_text("NOT JSON")
        cm = self._make(tmp_path)
        tema = cm.load_tema("custom")
        from concilium.domain.models.catalog.tema import TEMA_DEFAULT

        assert tema is TEMA_DEFAULT

    def test_load_contexto_missing_raises(self, tmp_path):
        from concilium.application.runtime.exceptions import RuntimeDomainError

        cm = self._make(tmp_path)
        with pytest.raises(RuntimeDomainError):
            cm.load_contexto("nonexistent")

    def test_load_jurisdicao_with_parent(self, tmp_path):
        jur_dir = tmp_path / "jurisdicoes"
        jur_dir.mkdir()
        (jur_dir / "parent.json").write_text('{"name": "Parent", "base": 1}')
        (jur_dir / "child.json").write_text('{"parent_id": "parent", "base": 2}')
        cm = self._make(tmp_path)
        result = cm.load_jurisdicao("child")
        assert result["base"] == 2  # child overrides parent

    def test_load_calendario_operacional_merges_all_levels(self, tmp_path):
        cal_dir = tmp_path / "calendarios"
        (cal_dir).mkdir()
        global_cal = {"eventos": [{"id": "E1", "tipo": "feriado"}]}
        (cal_dir / "global.json").write_text(json.dumps(global_cal))
        jur_dir = cal_dir / "jurisdicao"
        jur_dir.mkdir()
        (jur_dir / "jur-1.json").write_text('{"eventos": [{"id": "E2", "tipo": "regional"}]}')
        proj_dir = cal_dir / "projeto"
        proj_dir.mkdir()
        (proj_dir / "proj-1.json").write_text('{"eventos": [{"id": "E1", "tipo": "override"}]}')
        cm = self._make(tmp_path)
        cal = cm.load_calendario_operacional(jurisdicao_id="jur-1", project_id="proj-1")
        event_ids = {e["id"] for e in cal["eventos"]}
        assert "E1" in event_ids  # global (overridden by project)
        assert "E2" in event_ids  # jurisdicao

    def test_load_calendario_operacional_malformed_json_ignored(self, tmp_path):
        # global.json with invalid JSON content must be swallowed by the
        # `_load_optional` except-branch and treated as if it had no events.
        cal_dir = tmp_path / "calendarios"
        cal_dir.mkdir()
        (cal_dir / "global.json").write_text("{not valid json", encoding="utf-8")
        cm = self._make(tmp_path)
        cal = cm.load_calendario_operacional()
        assert cal["eventos"] == []

    def test_load_calendario_cached(self, tmp_path):
        cm = self._make(tmp_path)
        c1 = cm.load_calendario_operacional()
        c2 = cm.load_calendario_operacional()
        assert c1 is c2

    def test_deep_merge(self, tmp_path):
        cm = self._make(tmp_path)
        result = cm._deep_merge({"a": 1, "b": {"c": 2}}, {"b": {"d": 3}, "e": 5})
        assert result["a"] == 1
        assert result["b"]["c"] == 2
        assert result["b"]["d"] == 3
        assert result["e"] == 5



