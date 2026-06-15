"""Tests for SkillRegistry and SkillMetadata to boost coverage of registry.py."""

import textwrap
from pathlib import Path

import pytest

from concilium.application.skills.registry import SkillMetadata, SkillRegistry


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_skill_toml(tmp_path: Path, folder: str, content: str) -> Path:
    """Create a skill.toml inside a subdirectory of tmp_path."""
    skill_dir = tmp_path / folder
    skill_dir.mkdir(parents=True, exist_ok=True)
    toml_file = skill_dir / "skill.toml"
    toml_file.write_text(content, encoding="utf-8")
    return toml_file


MINIMAL_TOML = textwrap.dedent("""\
    [skill]
    id = "{skill_id}"
    version = "1.0.0"
    descricao = "Test skill"
""")

FULL_TOML = textwrap.dedent("""\
    [skill]
    id = "{skill_id}"
    version = "2.0.0"
    descricao = "Full skill"
    gate = true

    [depends_on]
    skills = ["{dep_id}"]
    canonical_sections = ["section_a"]

    [produces]
    canonical_section = "section_b"
    validations = ["VAL-X-01"]

    [inputs]
    required = ["input_a"]
    optional = ["input_b"]
""")


@pytest.fixture(autouse=True)
def reset_singleton():
    """Reset SkillRegistry singleton before every test."""
    SkillRegistry._instance = None
    yield
    SkillRegistry._instance = None


# ---------------------------------------------------------------------------
# SkillMetadata unit tests
# ---------------------------------------------------------------------------


class TestSkillMetadataHash:
    def _make(self, skill_id: str) -> SkillMetadata:
        return SkillMetadata(
            id=skill_id,
            version="1.0.0",
            descricao="desc",
            is_gate=False,
            depends_on_skills=[],
            canonical_sections_required=[],
            produces_section="",
            validations=[],
            inputs_required=[],
            inputs_optional=[],
        )

    def test_hash_is_based_on_id(self):
        m = self._make("skill-01")
        assert hash(m) == hash("skill-01")

    def test_equal_ids_same_hash(self):
        a = self._make("skill-01")
        b = self._make("skill-01")
        assert hash(a) == hash(b)

    def test_different_ids_different_hash(self):
        a = self._make("skill-01")
        b = self._make("skill-02")
        assert hash(a) != hash(b)

    def test_usable_in_set(self):
        a = self._make("skill-01")
        b = self._make("skill-01")
        s = {a, b}
        assert len(s) == 1

    def test_usable_as_dict_key(self):
        m = self._make("skill-01")
        d = {m: "value"}
        assert d[m] == "value"


class TestSkillMetadataEq:
    def _make(self, skill_id: str) -> SkillMetadata:
        return SkillMetadata(
            id=skill_id,
            version="1.0.0",
            descricao="desc",
            is_gate=False,
            depends_on_skills=[],
            canonical_sections_required=[],
            produces_section="",
            validations=[],
            inputs_required=[],
            inputs_optional=[],
        )

    def test_equal_same_id(self):
        a = self._make("skill-01")
        b = self._make("skill-01")
        assert a == b

    def test_not_equal_different_id(self):
        a = self._make("skill-01")
        b = self._make("skill-02")
        assert a != b

    def test_not_equal_to_string(self):
        a = self._make("skill-01")
        assert a != "skill-01"

    def test_not_equal_to_none(self):
        a = self._make("skill-01")
        assert a != None  # noqa: E711

    def test_not_equal_to_int(self):
        a = self._make("skill-01")
        assert a != 42


# ---------------------------------------------------------------------------
# SkillRegistry singleton tests
# ---------------------------------------------------------------------------


class TestSkillRegistrySingleton:
    def test_same_instance_returned_twice(self, tmp_path):
        r1 = SkillRegistry(manifests_dir=tmp_path)
        r2 = SkillRegistry(manifests_dir=tmp_path)
        assert r1 is r2

    def test_second_call_ignores_new_manifests_dir(self, tmp_path):
        """Once initialized, a different manifests_dir is silently ignored."""
        _make_skill_toml(tmp_path, "01-alpha", MINIMAL_TOML.format(skill_id="skill-alpha"))
        r1 = SkillRegistry(manifests_dir=tmp_path)

        other_dir = tmp_path / "other"
        other_dir.mkdir()
        _make_skill_toml(other_dir, "99-beta", MINIMAL_TOML.format(skill_id="skill-beta"))

        r2 = SkillRegistry(manifests_dir=other_dir)
        assert r1 is r2
        # Only skills from the first dir are loaded
        assert "skill-alpha" in r2.skills
        assert "skill-beta" not in r2.skills

    def test_reset_allows_reinit(self, tmp_path):
        _make_skill_toml(tmp_path, "01-alpha", MINIMAL_TOML.format(skill_id="skill-alpha"))
        r1 = SkillRegistry(manifests_dir=tmp_path)
        assert r1.get_skill("skill-alpha") is not None

        SkillRegistry._instance = None
        other = tmp_path / "other"
        other.mkdir()
        r2 = SkillRegistry(manifests_dir=other)
        assert r2 is not r1
        assert r2.get_skill("skill-alpha") is None


# ---------------------------------------------------------------------------
# SkillRegistry._load_all_skills — missing manifests_dir
# ---------------------------------------------------------------------------


class TestLoadAllSkillsMissingDir:
    def test_nonexistent_dir_returns_empty(self, tmp_path):
        missing = tmp_path / "nonexistent"
        registry = SkillRegistry(manifests_dir=missing)
        assert registry.skills == {}

    def test_get_all_skills_returns_empty_dict(self, tmp_path):
        missing = tmp_path / "nonexistent"
        registry = SkillRegistry(manifests_dir=missing)
        assert registry.get_all_skills() == {}


# ---------------------------------------------------------------------------
# SkillRegistry._load_all_skills — malformed TOML raises RuntimeError
# ---------------------------------------------------------------------------


class TestMalformedToml:
    def test_invalid_toml_raises_runtime_error(self, tmp_path):
        skill_dir = tmp_path / "bad-skill"
        skill_dir.mkdir()
        (skill_dir / "skill.toml").write_text("this is not valid toml ===", encoding="utf-8")
        with pytest.raises(RuntimeError, match="Error loading skill"):
            SkillRegistry(manifests_dir=tmp_path)

    def test_error_message_contains_path(self, tmp_path):
        skill_dir = tmp_path / "bad-skill"
        skill_dir.mkdir()
        toml_path = skill_dir / "skill.toml"
        toml_path.write_text("[unclosed\n", encoding="utf-8")
        with pytest.raises(RuntimeError) as exc_info:
            SkillRegistry(manifests_dir=tmp_path)
        assert str(toml_path) in str(exc_info.value)


# ---------------------------------------------------------------------------
# SkillRegistry._parse_toml — missing [skill].id returns None (skill not loaded)
# ---------------------------------------------------------------------------


class TestParseTomlMissingId:
    def test_skill_without_id_is_skipped(self, tmp_path):
        no_id_toml = textwrap.dedent("""\
            [skill]
            version = "1.0.0"
            descricao = "No id here"
        """)
        _make_skill_toml(tmp_path, "01-noid", no_id_toml)
        registry = SkillRegistry(manifests_dir=tmp_path)
        assert registry.skills == {}

    def test_empty_id_is_skipped(self, tmp_path):
        empty_id_toml = textwrap.dedent("""\
            [skill]
            id = ""
            version = "1.0.0"
        """)
        _make_skill_toml(tmp_path, "01-emptyid", empty_id_toml)
        registry = SkillRegistry(manifests_dir=tmp_path)
        assert registry.skills == {}


# ---------------------------------------------------------------------------
# SkillRegistry._load_all_skills — directories without skill.toml are skipped
# ---------------------------------------------------------------------------


class TestLoadSkillsSkipsNonToml:
    def test_dir_without_toml_is_ignored(self, tmp_path):
        empty_dir = tmp_path / "01-empty"
        empty_dir.mkdir()
        registry = SkillRegistry(manifests_dir=tmp_path)
        assert registry.skills == {}

    def test_file_at_top_level_is_ignored(self, tmp_path):
        # A file (not a directory) at the manifests level is not a valid skill dir
        (tmp_path / "not-a-dir.toml").write_text("[skill]\nid='x'\n", encoding="utf-8")
        registry = SkillRegistry(manifests_dir=tmp_path)
        assert registry.skills == {}


# ---------------------------------------------------------------------------
# SkillRegistry.get_skill — hit and miss
# ---------------------------------------------------------------------------


class TestGetSkill:
    def test_get_skill_hit(self, tmp_path):
        _make_skill_toml(tmp_path, "01-alpha", MINIMAL_TOML.format(skill_id="skill-alpha"))
        registry = SkillRegistry(manifests_dir=tmp_path)
        skill = registry.get_skill("skill-alpha")
        assert skill is not None
        assert skill.id == "skill-alpha"

    def test_get_skill_miss_returns_none(self, tmp_path):
        _make_skill_toml(tmp_path, "01-alpha", MINIMAL_TOML.format(skill_id="skill-alpha"))
        registry = SkillRegistry(manifests_dir=tmp_path)
        assert registry.get_skill("nonexistent") is None

    def test_get_skill_from_empty_registry(self, tmp_path):
        missing = tmp_path / "missing"
        registry = SkillRegistry(manifests_dir=missing)
        assert registry.get_skill("anything") is None


# ---------------------------------------------------------------------------
# SkillRegistry.get_all_skills
# ---------------------------------------------------------------------------


class TestGetAllSkills:
    def test_returns_all_loaded_skills(self, tmp_path):
        _make_skill_toml(tmp_path, "01-alpha", MINIMAL_TOML.format(skill_id="skill-alpha"))
        _make_skill_toml(tmp_path, "02-beta", MINIMAL_TOML.format(skill_id="skill-beta"))
        registry = SkillRegistry(manifests_dir=tmp_path)
        all_skills = registry.get_all_skills()
        assert set(all_skills.keys()) == {"skill-alpha", "skill-beta"}

    def test_returns_same_dict_reference(self, tmp_path):
        _make_skill_toml(tmp_path, "01-alpha", MINIMAL_TOML.format(skill_id="skill-alpha"))
        registry = SkillRegistry(manifests_dir=tmp_path)
        assert registry.get_all_skills() is registry.skills

    def test_full_toml_fields_parsed_correctly(self, tmp_path):
        content = FULL_TOML.format(skill_id="skill-full", dep_id="skill-dep")
        _make_skill_toml(tmp_path, "01-full", content)
        registry = SkillRegistry(manifests_dir=tmp_path)
        skill = registry.get_skill("skill-full")
        assert skill is not None
        assert skill.version == "2.0.0"
        assert skill.descricao == "Full skill"
        assert skill.is_gate is True
        assert skill.depends_on_skills == ["skill-dep"]
        assert skill.canonical_sections_required == ["section_a"]
        assert skill.produces_section == "section_b"
        assert skill.validations == ["VAL-X-01"]
        assert skill.inputs_required == ["input_a"]
        assert skill.inputs_optional == ["input_b"]


# ---------------------------------------------------------------------------
# SkillRegistry.get_dependencies_for
# ---------------------------------------------------------------------------


class TestGetDependenciesFor:
    def _setup_chain(self, tmp_path: Path) -> SkillRegistry:
        """Create skills: skill-a (no deps), skill-b (depends on skill-a)."""
        _make_skill_toml(tmp_path, "01-a", MINIMAL_TOML.format(skill_id="skill-a"))
        content_b = textwrap.dedent("""\
            [skill]
            id = "skill-b"
            version = "1.0.0"
            descricao = "B depends on A"

            [depends_on]
            skills = ["skill-a"]
        """)
        _make_skill_toml(tmp_path, "02-b", content_b)
        return SkillRegistry(manifests_dir=tmp_path)

    def test_skill_with_dependency(self, tmp_path):
        registry = self._setup_chain(tmp_path)
        deps = registry.get_dependencies_for("skill-b")
        assert deps == ["skill-a"]

    def test_skill_with_no_dependencies(self, tmp_path):
        registry = self._setup_chain(tmp_path)
        deps = registry.get_dependencies_for("skill-a")
        assert deps == []

    def test_absent_skill_returns_empty_list(self, tmp_path):
        registry = self._setup_chain(tmp_path)
        deps = registry.get_dependencies_for("nonexistent")
        assert deps == []


# ---------------------------------------------------------------------------
# SkillRegistry.get_dependents_of
# ---------------------------------------------------------------------------


class TestGetDependentsOf:
    def _setup_chain(self, tmp_path: Path) -> SkillRegistry:
        _make_skill_toml(tmp_path, "01-a", MINIMAL_TOML.format(skill_id="skill-a"))
        content_b = textwrap.dedent("""\
            [skill]
            id = "skill-b"
            version = "1.0.0"
            descricao = "B depends on A"

            [depends_on]
            skills = ["skill-a"]
        """)
        _make_skill_toml(tmp_path, "02-b", content_b)
        content_c = textwrap.dedent("""\
            [skill]
            id = "skill-c"
            version = "1.0.0"
            descricao = "C also depends on A"

            [depends_on]
            skills = ["skill-a"]
        """)
        _make_skill_toml(tmp_path, "03-c", content_c)
        return SkillRegistry(manifests_dir=tmp_path)

    def test_skill_with_two_dependents(self, tmp_path):
        registry = self._setup_chain(tmp_path)
        dependents = registry.get_dependents_of("skill-a")
        assert set(dependents) == {"skill-b", "skill-c"}

    def test_leaf_skill_has_no_dependents(self, tmp_path):
        registry = self._setup_chain(tmp_path)
        dependents = registry.get_dependents_of("skill-b")
        assert dependents == []

    def test_absent_skill_returns_empty_list(self, tmp_path):
        registry = self._setup_chain(tmp_path)
        assert registry.get_dependents_of("nonexistent") == []

    def test_empty_registry_returns_empty_list(self, tmp_path):
        missing = tmp_path / "missing"
        registry = SkillRegistry(manifests_dir=missing)
        assert registry.get_dependents_of("skill-a") == []


# ---------------------------------------------------------------------------
# SkillRegistry.get_topological_order
# ---------------------------------------------------------------------------


class TestGetTopologicalOrder:
    def test_linear_chain_deps_come_first(self, tmp_path):
        """A → B → C; topological order must place A before B before C."""
        _make_skill_toml(tmp_path, "01-a", MINIMAL_TOML.format(skill_id="skill-a"))
        content_b = textwrap.dedent("""\
            [skill]
            id = "skill-b"

            [depends_on]
            skills = ["skill-a"]
        """)
        _make_skill_toml(tmp_path, "02-b", content_b)
        content_c = textwrap.dedent("""\
            [skill]
            id = "skill-c"

            [depends_on]
            skills = ["skill-b"]
        """)
        _make_skill_toml(tmp_path, "03-c", content_c)

        registry = SkillRegistry(manifests_dir=tmp_path)
        order = registry.get_topological_order()

        assert order.index("skill-a") < order.index("skill-b")
        assert order.index("skill-b") < order.index("skill-c")

    def test_independent_skills_all_present(self, tmp_path):
        """Three independent skills — all appear in the order, no particular ordering required."""
        _make_skill_toml(tmp_path, "01-x", MINIMAL_TOML.format(skill_id="skill-x"))
        _make_skill_toml(tmp_path, "02-y", MINIMAL_TOML.format(skill_id="skill-y"))
        _make_skill_toml(tmp_path, "03-z", MINIMAL_TOML.format(skill_id="skill-z"))

        registry = SkillRegistry(manifests_dir=tmp_path)
        order = registry.get_topological_order()

        assert set(order) == {"skill-x", "skill-y", "skill-z"}

    def test_empty_registry_returns_empty_list(self, tmp_path):
        missing = tmp_path / "missing"
        registry = SkillRegistry(manifests_dir=missing)
        assert registry.get_topological_order() == []

    def test_single_skill_returns_list_with_one_element(self, tmp_path):
        _make_skill_toml(tmp_path, "01-solo", MINIMAL_TOML.format(skill_id="skill-solo"))
        registry = SkillRegistry(manifests_dir=tmp_path)
        order = registry.get_topological_order()
        assert order == ["skill-solo"]

    def test_external_dependency_not_in_registry_is_still_visited(self, tmp_path):
        """If a skill depends on an ID not in the registry, topological order still works."""
        content = textwrap.dedent("""\
            [skill]
            id = "skill-d"

            [depends_on]
            skills = ["external-skill-not-loaded"]
        """)
        _make_skill_toml(tmp_path, "01-d", content)
        registry = SkillRegistry(manifests_dir=tmp_path)
        order = registry.get_topological_order()
        # skill-d should be present; external dep is not in registry so not added
        assert "skill-d" in order
        assert "external-skill-not-loaded" not in order

    def test_no_duplicates_in_topological_order(self, tmp_path):
        """Each skill id appears exactly once even in diamond deps."""
        _make_skill_toml(tmp_path, "01-a", MINIMAL_TOML.format(skill_id="skill-a"))
        content_b = textwrap.dedent("""\
            [skill]
            id = "skill-b"
            [depends_on]
            skills = ["skill-a"]
        """)
        content_c = textwrap.dedent("""\
            [skill]
            id = "skill-c"
            [depends_on]
            skills = ["skill-a"]
        """)
        content_d = textwrap.dedent("""\
            [skill]
            id = "skill-d"
            [depends_on]
            skills = ["skill-b", "skill-c"]
        """)
        _make_skill_toml(tmp_path, "02-b", content_b)
        _make_skill_toml(tmp_path, "03-c", content_c)
        _make_skill_toml(tmp_path, "04-d", content_d)

        registry = SkillRegistry(manifests_dir=tmp_path)
        order = registry.get_topological_order()

        assert len(order) == len(set(order)), "Duplicate entries found in topological order"
        assert order.index("skill-a") < order.index("skill-b")
        assert order.index("skill-a") < order.index("skill-c")
        assert order.index("skill-b") < order.index("skill-d")
        assert order.index("skill-c") < order.index("skill-d")
