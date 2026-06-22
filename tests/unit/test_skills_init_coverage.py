"""Tests targeting missing lines in concilium/application/skills/__init__.py.

Covers:
- _skill_pkg_name / _skill_mod_name helpers
- _ensure_skill_package (already-registered path)
- _load_skill_module (missing file, error cleanup, cached path)
- _SkillProxy.__getattr__ (lazy load + alias replacement)
- _load (stale module path)
- _discover_manifest_index / _discover_manifest_meta (no-dir, error paths)
- load_skill_stage
- list_compat_aliases
- _LazySkillsDict (contains, iter, len, getitem, values, items, get)
- module __getattr__ (SkillResult, run_*, missing → AttributeError)
"""

from __future__ import annotations

import sys
import types
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest


# ---------------------------------------------------------------------------
# Private name helpers
# ---------------------------------------------------------------------------


class TestSkillNameHelpers:
    def test_skill_pkg_name_replaces_dash(self):
        from concilium.application.skills import _skill_pkg_name

        assert _skill_pkg_name("01-escopo-e-eap") == "_concilium_skillpkg_01_escopo_e_eap"

    def test_skill_mod_name_contains_skill_suffix(self):
        from concilium.application.skills import _skill_mod_name

        mod = _skill_mod_name("01-escopo-e-eap")
        assert mod.endswith(".skill")
        assert "_concilium_skillpkg_01_escopo_e_eap" in mod

    def test_get_compat_alias_format(self):
        from concilium.application.skills import _get_compat_alias

        alias = _get_compat_alias("01-escopo-e-eap")
        assert alias == "concilium.application.skills.escopo_e_eap"

    def test_get_compat_alias_simple(self):
        from concilium.application.skills import _get_compat_alias

        alias = _get_compat_alias("02-cronograma")
        assert alias == "concilium.application.skills.cronograma"


# ---------------------------------------------------------------------------
# _ensure_skill_package — already-registered fast-path
# ---------------------------------------------------------------------------


class TestEnsureSkillPackage:
    def test_returns_existing_pkg_name_if_already_registered(self, tmp_path):
        from concilium.application.skills import _ensure_skill_package, _skill_pkg_name

        skill_id = "_test_ensure_already_registered"
        pkg_name = _skill_pkg_name(skill_id)
        # Pre-register a fake package
        fake_pkg = types.ModuleType(pkg_name)
        sys.modules[pkg_name] = fake_pkg
        try:
            result = _ensure_skill_package(skill_id, tmp_path)
            assert result == pkg_name
            # Must NOT have replaced the pre-existing module
            assert sys.modules[pkg_name] is fake_pkg
        finally:
            sys.modules.pop(pkg_name, None)

    def test_registers_new_package_when_absent(self, tmp_path):
        from concilium.application.skills import _ensure_skill_package, _skill_pkg_name

        skill_id = "_test_ensure_new_pkg"
        pkg_name = _skill_pkg_name(skill_id)
        sys.modules.pop(pkg_name, None)
        try:
            result = _ensure_skill_package(skill_id, tmp_path)
            assert result == pkg_name
            assert pkg_name in sys.modules
        finally:
            sys.modules.pop(pkg_name, None)


# ---------------------------------------------------------------------------
# _load_skill_module — error paths
# ---------------------------------------------------------------------------


class TestLoadSkillModule:
    def test_raises_import_error_when_skill_py_missing(self, tmp_path):
        from concilium.application.skills import _load_skill_module
        import concilium.application.skills as skills_pkg

        fake_manifests = tmp_path / "manifests"
        fake_manifests.mkdir()

        original_manifests = skills_pkg._MANIFESTS
        skills_pkg._MANIFESTS = fake_manifests
        try:
            with pytest.raises(ImportError, match="skill.py"):
                _load_skill_module("nonexistent-skill")
        finally:
            skills_pkg._MANIFESTS = original_manifests

    def test_cleans_up_sys_modules_on_exec_error(self, tmp_path):
        from concilium.application.skills import _load_skill_module, _skill_mod_name
        import concilium.application.skills as skills_pkg

        fake_manifests = tmp_path / "manifests"
        skill_dir = fake_manifests / "bad-skill"
        skill_dir.mkdir(parents=True)
        skill_py = skill_dir / "skill.py"
        skill_py.write_text("raise RuntimeError('intentional error')", encoding="utf-8")

        original_manifests = skills_pkg._MANIFESTS
        skills_pkg._MANIFESTS = fake_manifests
        mod_name = _skill_mod_name("bad-skill")
        sys.modules.pop(mod_name, None)
        try:
            with pytest.raises(RuntimeError, match="intentional error"):
                _load_skill_module("bad-skill")
            # Module must have been removed from sys.modules after error
            assert mod_name not in sys.modules
        finally:
            skills_pkg._MANIFESTS = original_manifests
            sys.modules.pop(mod_name, None)

    def test_cached_module_returned_without_re_exec(self, tmp_path):
        from concilium.application.skills import _load_skill_module, _skill_mod_name
        import concilium.application.skills as skills_pkg

        fake_manifests = tmp_path / "manifests"
        skill_dir = fake_manifests / "cached-skill"
        skill_dir.mkdir(parents=True)
        (skill_dir / "skill.py").write_text("X = 42", encoding="utf-8")

        original_manifests = skills_pkg._MANIFESTS
        skills_pkg._MANIFESTS = fake_manifests
        mod_name = _skill_mod_name("cached-skill")
        sys.modules.pop(mod_name, None)
        try:
            mod1 = _load_skill_module("cached-skill")
            mod2 = _load_skill_module("cached-skill")
            assert mod1 is mod2
        finally:
            skills_pkg._MANIFESTS = original_manifests
            sys.modules.pop(mod_name, None)
            sys.modules.pop(skills_pkg._skill_pkg_name("cached-skill"), None)


# ---------------------------------------------------------------------------
# _SkillProxy — lazy load via __getattr__
# ---------------------------------------------------------------------------


class TestSkillProxy:
    def test_proxy_getattr_loads_module(self, tmp_path):
        from concilium.application.skills import _SkillProxy, _skill_mod_name
        import concilium.application.skills as skills_pkg

        fake_manifests = tmp_path / "manifests"
        skill_dir = fake_manifests / "proxy-skill"
        skill_dir.mkdir(parents=True)
        (skill_dir / "skill.py").write_text("RUN_PROXY = 'ok'", encoding="utf-8")

        original_manifests = skills_pkg._MANIFESTS
        skills_pkg._MANIFESTS = fake_manifests
        mod_name = _skill_mod_name("proxy-skill")
        sys.modules.pop(mod_name, None)
        try:
            proxy = _SkillProxy("proxy-skill")
            val = proxy.RUN_PROXY
            assert val == "ok"
            # After first access, sys.modules[alias] should be the real module
            alias = proxy.__name__
            assert sys.modules.get(alias) is sys.modules.get(mod_name)
        finally:
            skills_pkg._MANIFESTS = original_manifests
            sys.modules.pop(mod_name, None)
            sys.modules.pop(skills_pkg._skill_pkg_name("proxy-skill"), None)

    def test_proxy_getattr_cached(self, tmp_path):
        """Second access to proxy reuses the already-loaded module."""
        from concilium.application.skills import _SkillProxy, _skill_mod_name
        import concilium.application.skills as skills_pkg

        fake_manifests = tmp_path / "manifests"
        skill_dir = fake_manifests / "proxy2-skill"
        skill_dir.mkdir(parents=True)
        (skill_dir / "skill.py").write_text("VAL = 99", encoding="utf-8")

        original_manifests = skills_pkg._MANIFESTS
        skills_pkg._MANIFESTS = fake_manifests
        mod_name = _skill_mod_name("proxy2-skill")
        sys.modules.pop(mod_name, None)
        try:
            proxy = _SkillProxy("proxy2-skill")
            _ = proxy.VAL
            # Module is now in sys.modules; second call should not re-load
            val2 = proxy.VAL
            assert val2 == 99
        finally:
            skills_pkg._MANIFESTS = original_manifests
            sys.modules.pop(mod_name, None)
            sys.modules.pop(skills_pkg._skill_pkg_name("proxy2-skill"), None)


# ---------------------------------------------------------------------------
# _load — stale/partial module recovery path
# ---------------------------------------------------------------------------


class TestLoadFunction:
    def test_load_recovers_from_stale_module_without_attr(self, tmp_path):
        from concilium.application.skills import _load, _skill_mod_name
        import concilium.application.skills as skills_pkg

        fake_manifests = tmp_path / "manifests"
        skill_dir = fake_manifests / "stale-skill"
        skill_dir.mkdir(parents=True)
        (skill_dir / "skill.py").write_text("def run_stale_skill(): return 'fresh'", encoding="utf-8")

        original_manifests = skills_pkg._MANIFESTS
        skills_pkg._MANIFESTS = fake_manifests
        mod_name = _skill_mod_name("stale-skill")

        # Insert a stale module that lacks the function
        stale = types.ModuleType(mod_name)
        sys.modules[mod_name] = stale
        try:
            fn = _load("stale-skill", "run_stale_skill")
            assert callable(fn)
            assert fn() == "fresh"
        finally:
            skills_pkg._MANIFESTS = original_manifests
            sys.modules.pop(mod_name, None)
            sys.modules.pop(skills_pkg._skill_pkg_name("stale-skill"), None)


# ---------------------------------------------------------------------------
# _discover_manifest_index / _discover_manifest_meta — edge cases
# ---------------------------------------------------------------------------


class TestDiscoverManifestIndex:
    def test_returns_empty_when_manifests_dir_missing(self, tmp_path):
        from concilium.application.skills import _discover_manifest_index
        import concilium.application.skills as skills_pkg

        original = skills_pkg._MANIFESTS
        skills_pkg._MANIFESTS = tmp_path / "nonexistent"
        try:
            result = _discover_manifest_index()
            assert result == {}
        finally:
            skills_pkg._MANIFESTS = original

    def test_raises_on_malformed_toml(self, tmp_path):
        from concilium.application.skills import _discover_manifest_index
        import concilium.application.skills as skills_pkg

        manifests = tmp_path / "manifests"
        skill_dir = manifests / "bad-toml-skill"
        skill_dir.mkdir(parents=True)
        (skill_dir / "skill.toml").write_text("not valid toml ][", encoding="utf-8")
        (skill_dir / "skill.py").write_text("pass", encoding="utf-8")

        original = skills_pkg._MANIFESTS
        skills_pkg._MANIFESTS = manifests
        try:
            with pytest.raises(RuntimeError, match="Erro lendo manifesto"):
                _discover_manifest_index()
        finally:
            skills_pkg._MANIFESTS = original

    def test_raises_when_skill_py_absent(self, tmp_path):
        from concilium.application.skills import _discover_manifest_index
        import concilium.application.skills as skills_pkg

        manifests = tmp_path / "manifests"
        skill_dir = manifests / "nopy-skill"
        skill_dir.mkdir(parents=True)
        toml_content = '[skill]\nid = "nopy-skill"\n'
        (skill_dir / "skill.toml").write_text(toml_content, encoding="utf-8")
        # NO skill.py

        original = skills_pkg._MANIFESTS
        skills_pkg._MANIFESTS = manifests
        try:
            with pytest.raises(RuntimeError):
                _discover_manifest_index()
        finally:
            skills_pkg._MANIFESTS = original

    def test_skips_non_directory_entries(self, tmp_path):
        from concilium.application.skills import _discover_manifest_index
        import concilium.application.skills as skills_pkg

        manifests = tmp_path / "manifests"
        manifests.mkdir()
        (manifests / "afile.toml").write_text("just a file", encoding="utf-8")
        # No subdirectories -> must return empty without error

        original = skills_pkg._MANIFESTS
        skills_pkg._MANIFESTS = manifests
        try:
            result = _discover_manifest_index()
            assert result == {}
        finally:
            skills_pkg._MANIFESTS = original


class TestDiscoverManifestMeta:
    def test_returns_empty_when_manifests_dir_missing(self, tmp_path):
        from concilium.application.skills import _discover_manifest_meta
        import concilium.application.skills as skills_pkg

        original = skills_pkg._MANIFESTS
        skills_pkg._MANIFESTS = tmp_path / "nonexistent"
        try:
            result = _discover_manifest_meta()
            assert result == {}
        finally:
            skills_pkg._MANIFESTS = original

    def test_meta_includes_phase_gate_status_tier(self, tmp_path):
        from concilium.application.skills import _discover_manifest_meta
        import concilium.application.skills as skills_pkg

        manifests = tmp_path / "manifests"
        skill_dir = manifests / "meta-skill"
        skill_dir.mkdir(parents=True)
        toml_content = (
            "[skill]\n"
            'id = "meta-skill"\n'
            'phase = "Fase Teste"\n'
            "gate = true\n"
            'status = "ativo"\n'
            'tier = "oltp"\n'
        )
        (skill_dir / "skill.toml").write_text(toml_content, encoding="utf-8")
        (skill_dir / "skill.py").write_text("pass", encoding="utf-8")

        original = skills_pkg._MANIFESTS
        skills_pkg._MANIFESTS = manifests
        try:
            meta = _discover_manifest_meta()
            assert "meta-skill" in meta
            entry = meta["meta-skill"]
            assert entry["phase"] == "Fase Teste"
            assert entry["gate"] is True
            assert entry["status"] == "ativo"
            assert entry["tier"] == "oltp"
        finally:
            skills_pkg._MANIFESTS = original

    def test_meta_defaults_when_fields_absent(self, tmp_path):
        from concilium.application.skills import _discover_manifest_meta
        import concilium.application.skills as skills_pkg

        manifests = tmp_path / "manifests"
        skill_dir = manifests / "minimal-skill"
        skill_dir.mkdir(parents=True)
        (skill_dir / "skill.toml").write_text("[skill]\n", encoding="utf-8")
        (skill_dir / "skill.py").write_text("pass", encoding="utf-8")

        original = skills_pkg._MANIFESTS
        skills_pkg._MANIFESTS = manifests
        try:
            meta = _discover_manifest_meta()
            # skill_id falls back to dir name
            assert "minimal-skill" in meta
            entry = meta["minimal-skill"]
            assert entry["phase"] == "Sem Classificação"
            assert entry["gate"] is False
            assert entry["tier"] == "olap"
        finally:
            skills_pkg._MANIFESTS = original

    def test_raises_on_malformed_toml(self, tmp_path):
        from concilium.application.skills import _discover_manifest_meta
        import concilium.application.skills as skills_pkg

        manifests = tmp_path / "manifests"
        skill_dir = manifests / "bad-skill"
        skill_dir.mkdir(parents=True)
        (skill_dir / "skill.toml").write_text("not valid ][", encoding="utf-8")

        original = skills_pkg._MANIFESTS
        skills_pkg._MANIFESTS = manifests
        try:
            with pytest.raises(RuntimeError, match="Erro lendo manifesto"):
                _discover_manifest_meta()
        finally:
            skills_pkg._MANIFESTS = original


# ---------------------------------------------------------------------------
# load_skill_stage
# ---------------------------------------------------------------------------


class TestLoadSkillStage:
    def test_load_stage_from_file(self, tmp_path):
        from concilium.application.skills import load_skill_stage
        import concilium.application.skills as skills_pkg

        fake_manifests = tmp_path / "manifests"
        skill_dir = fake_manifests / "sk-stage"
        skill_dir.mkdir(parents=True)
        (skill_dir / "_helper.py").write_text("def run_helper(): return 'stage_ok'", encoding="utf-8")

        original = skills_pkg._MANIFESTS
        skills_pkg._MANIFESTS = fake_manifests
        try:
            fn = load_skill_stage("sk-stage", "_helper", "run_helper")
            assert callable(fn)
            assert fn() == "stage_ok"
        finally:
            skills_pkg._MANIFESTS = original
            # cleanup synthetic module
            sys.modules.pop("stage_sk_stage__helper", None)

    def test_load_stage_from_subdir(self, tmp_path):
        from concilium.application.skills import load_skill_stage
        import concilium.application.skills as skills_pkg

        fake_manifests = tmp_path / "manifests"
        skill_dir = fake_manifests / "sk-subdir"
        stage_dir = skill_dir / "_substage"
        stage_dir.mkdir(parents=True)
        (stage_dir / "skill.py").write_text("def run_sub(): return 'subdir_ok'", encoding="utf-8")

        original = skills_pkg._MANIFESTS
        skills_pkg._MANIFESTS = fake_manifests
        try:
            fn = load_skill_stage("sk-subdir", "_substage", "run_sub")
            assert callable(fn)
            assert fn() == "subdir_ok"
        finally:
            skills_pkg._MANIFESTS = original


# ---------------------------------------------------------------------------
# list_compat_aliases
# ---------------------------------------------------------------------------


class TestListCompatAliases:
    def test_returns_dict(self):
        from concilium.application.skills import list_compat_aliases

        aliases = list_compat_aliases()
        assert isinstance(aliases, dict)

    def test_values_end_with_skill(self):
        from concilium.application.skills import list_compat_aliases

        aliases = list_compat_aliases()
        for alias, mod_name in aliases.items():
            assert alias.startswith("concilium.application.skills.")
            assert mod_name.endswith(".skill")


# ---------------------------------------------------------------------------
# _LazySkillsDict
# ---------------------------------------------------------------------------


class TestLazySkillsDict:
    def _make_dict(self):
        from concilium.application.skills import _LazySkillsDict

        index = {"aa-one": "run_one", "aa-two": "run_two"}
        d = _LazySkillsDict(index)
        return d, index

    def test_contains_true(self):
        d, _ = self._make_dict()
        assert "aa-one" in d

    def test_contains_false(self):
        d, _ = self._make_dict()
        assert "missing" not in d

    def test_iter_yields_all_ids(self):
        d, index = self._make_dict()
        assert set(d) == set(index)

    def test_len(self):
        d, index = self._make_dict()
        assert len(d) == len(index)

    def test_keys(self):
        d, index = self._make_dict()
        assert set(d.keys()) == set(index.keys())

    def test_getitem_missing_raises_key_error(self):
        d, _ = self._make_dict()
        with pytest.raises(KeyError):
            _ = d["not-there"]

    def test_get_missing_returns_default(self):
        d, _ = self._make_dict()
        assert d.get("not-there") is None
        assert d.get("not-there", "fallback") == "fallback"

    def test_get_existing_calls_getitem(self, tmp_path):
        """get() on an existing key should load and return the function."""
        from concilium.application.skills import _LazySkillsDict
        import concilium.application.skills as skills_pkg

        fake_manifests = tmp_path / "manifests"
        skill_dir = fake_manifests / "lazy-get-skill"
        skill_dir.mkdir(parents=True)
        (skill_dir / "skill.py").write_text("def run_lazy_get_skill(): return 42", encoding="utf-8")

        original = skills_pkg._MANIFESTS
        skills_pkg._MANIFESTS = fake_manifests
        try:
            d = _LazySkillsDict({"lazy-get-skill": "run_lazy_get_skill"})
            fn = d.get("lazy-get-skill")
            assert callable(fn)
        finally:
            skills_pkg._MANIFESTS = original
            from concilium.application.skills import _skill_mod_name, _skill_pkg_name
            sys.modules.pop(_skill_mod_name("lazy-get-skill"), None)
            sys.modules.pop(_skill_pkg_name("lazy-get-skill"), None)

    def test_values_forces_all_loads(self, tmp_path):
        from concilium.application.skills import _LazySkillsDict
        import concilium.application.skills as skills_pkg

        fake_manifests = tmp_path / "manifests"
        for sid, fname in [("lz-v-skill1", "run_lz_v_skill1"), ("lz-v-skill2", "run_lz_v_skill2")]:
            sd = fake_manifests / sid
            sd.mkdir(parents=True)
            (sd / "skill.py").write_text(f"def {fname}(): pass", encoding="utf-8")

        original = skills_pkg._MANIFESTS
        skills_pkg._MANIFESTS = fake_manifests
        try:
            d = _LazySkillsDict({"lz-v-skill1": "run_lz_v_skill1", "lz-v-skill2": "run_lz_v_skill2"})
            vals = list(d.values())
            assert len(vals) == 2
            assert all(callable(v) for v in vals)
        finally:
            skills_pkg._MANIFESTS = original
            from concilium.application.skills import _skill_mod_name, _skill_pkg_name
            for sid in ["lz-v-skill1", "lz-v-skill2"]:
                sys.modules.pop(_skill_mod_name(sid), None)
                sys.modules.pop(_skill_pkg_name(sid), None)

    def test_items_yields_id_fn_pairs(self, tmp_path):
        from concilium.application.skills import _LazySkillsDict
        import concilium.application.skills as skills_pkg

        fake_manifests = tmp_path / "manifests"
        skill_dir = fake_manifests / "items-skill"
        skill_dir.mkdir(parents=True)
        (skill_dir / "skill.py").write_text("def run_items_skill(): pass", encoding="utf-8")

        original = skills_pkg._MANIFESTS
        skills_pkg._MANIFESTS = fake_manifests
        try:
            d = _LazySkillsDict({"items-skill": "run_items_skill"})
            pairs = list(d.items())
            assert len(pairs) == 1
            sid, fn = pairs[0]
            assert sid == "items-skill"
            assert callable(fn)
        finally:
            skills_pkg._MANIFESTS = original
            from concilium.application.skills import _skill_mod_name, _skill_pkg_name
            sys.modules.pop(_skill_mod_name("items-skill"), None)
            sys.modules.pop(_skill_pkg_name("items-skill"), None)


# ---------------------------------------------------------------------------
# Module __getattr__
# ---------------------------------------------------------------------------


class TestModuleGetattr:
    def test_get_skill_result_class(self):
        import concilium.application.skills as skills_pkg

        SkillResult = skills_pkg.__getattr__("SkillResult")
        assert SkillResult is not None
        assert callable(SkillResult)

    def test_get_run_function_valid(self):
        """__getattr__ for a known run_ prefix resolves via MANIFEST_INDEX."""
        import concilium.application.skills as skills_pkg

        # Get the first run_* from the index
        if not skills_pkg._MANIFEST_INDEX:
            pytest.skip("No manifests available")
        first_id, first_fn = next(iter(skills_pkg._MANIFEST_INDEX.items()))
        fn = skills_pkg.__getattr__(first_fn)
        assert callable(fn)

    def test_get_unknown_attribute_raises(self):
        import concilium.application.skills as skills_pkg

        with pytest.raises(AttributeError, match="no attribute"):
            skills_pkg.__getattr__("totally_nonexistent_attr_xyz")

    def test_get_run_nonexistent_raises(self):
        """A run_ prefix that doesn't match any skill also raises AttributeError."""
        import concilium.application.skills as skills_pkg

        with pytest.raises(AttributeError):
            skills_pkg.__getattr__("run_nonexistent_skill_xyz")
