"""Tests for application/skills/graph_exporter.py."""

from __future__ import annotations

from unittest.mock import MagicMock


def _make_registry(n=3):
    """Build a mock registry with n skills and simple dependencies."""
    from concilium.application.skills.registry import SkillRegistry

    registry = MagicMock(spec=SkillRegistry)
    skills = {}
    for i in range(1, n + 1):
        sid = f"{i:02d}-skill-{i}"
        skill_mock = MagicMock()
        skill_mock.validations = [f"VAL-{i:02d}-A", f"VAL-{i:02d}-B", f"VAL-{i:02d}-C"]
        skill_mock.depends_on_skills = [f"{(i - 1):02d}-skill-{i - 1}"] if i > 1 else []
        skill_mock.version = "1.0"
        skill_mock.descricao = f"Skill {i}"
        skill_mock.produces_section = f"section-{i}"
        skills[sid] = skill_mock
    registry.skills = skills
    registry.get_skill.side_effect = lambda sid: skills.get(sid)
    return registry


class TestSkillGraphExporter:
    def test_node_id_converts_hyphens(self):
        from concilium.application.skills.graph_exporter import SkillGraphExporter

        assert SkillGraphExporter._node_id("01-escopo-e-eap") == "01_escopo_e_eap"

    def test_to_mermaid_basic(self):
        from concilium.application.skills.graph_exporter import SkillGraphExporter

        registry = _make_registry(2)
        exporter = SkillGraphExporter(registry=registry)
        result = exporter.to_mermaid()
        assert result.startswith("graph TD")
        assert "01_skill_1" in result
        assert "02_skill_2" in result
        # Edge: skill 2 depends on skill 1
        assert "-->" in result

    def test_to_mermaid_show_validations(self):
        from concilium.application.skills.graph_exporter import SkillGraphExporter

        registry = _make_registry(1)
        exporter = SkillGraphExporter(registry=registry)
        result = exporter.to_mermaid(show_validations=True)
        assert "VAL-01-A" in result
        assert "..." in result  # truncated at 2 + ellipsis

    def test_to_mermaid_group_by_phase(self):
        from concilium.application.skills.graph_exporter import SkillGraphExporter

        # Use default registry which has real skill IDs matching PHASE_MAP
        exporter = SkillGraphExporter()
        result = exporter.to_mermaid(group_by_phase=True)
        assert "graph TD" in result
        assert "subgraph" in result

    def test_to_json_structure(self):
        from concilium.application.skills.graph_exporter import SkillGraphExporter

        registry = _make_registry(2)
        exporter = SkillGraphExporter(registry=registry)
        result = exporter.to_json()
        assert "nodes" in result
        assert "edges" in result
        assert result["total_skills"] == 2
        assert result["total_dependencies"] == 1
        assert result["edges"][0]["type"] == "depends_on"

    def test_to_dot_basic(self):
        from concilium.application.skills.graph_exporter import SkillGraphExporter

        registry = _make_registry(2)
        exporter = SkillGraphExporter(registry=registry)
        result = exporter.to_dot()
        assert result.startswith("digraph SkillPipeline {")
        assert "rankdir=TB" in result
        assert "}" in result

    def test_to_dot_edges(self):
        from concilium.application.skills.graph_exporter import SkillGraphExporter

        registry = _make_registry(2)
        exporter = SkillGraphExporter(registry=registry)
        result = exporter.to_dot()
        assert "->" in result

    def test_to_json_edges_loop_dep_not_in_registry_and_duplicate(self):
        """Branches 133->132 (dep ausente do registry) e 135->132 (edge duplicado)
        pulam o corpo do if e voltam direto ao topo do loop interno."""
        from concilium.application.skills.graph_exporter import SkillGraphExporter

        registry = _make_registry(3)
        registry.skills["03-skill-3"].depends_on_skills = [
            "01-skill-1",
            "missing-skill-not-in-registry",
            "01-skill-1",  # duplicado → edge já processado
        ]
        exporter = SkillGraphExporter(registry=registry)
        result = exporter.to_json()
        # Apenas 1 edge único de 03 (para 01) + 1 default de 02->01... na verdade
        # skill-2 depende de skill-1 (default de _make_registry); total = 2.
        assert result["total_dependencies"] == 2

    def test_to_dot_edges_loop_dep_not_in_registry_and_duplicate(self):
        """Branches 177->176, 179->176: mesmo caso para to_dot()."""
        from concilium.application.skills.graph_exporter import SkillGraphExporter

        registry = _make_registry(3)
        registry.skills["03-skill-3"].depends_on_skills = [
            "01-skill-1",
            "missing-skill-not-in-registry",
            "01-skill-1",
        ]
        exporter = SkillGraphExporter(registry=registry)
        result = exporter.to_dot()
        assert '"01-skill-1" -> "03-skill-3"' in result
        assert "missing-skill-not-in-registry" not in result

    def test_default_registry_loads(self):
        from concilium.application.skills.graph_exporter import SkillGraphExporter

        exporter = SkillGraphExporter()
        result = exporter.to_mermaid()
        assert "graph TD" in result

    def test_build_skill_label_without_validations(self):
        from concilium.application.skills.graph_exporter import _build_skill_label

        skill = MagicMock()
        skill.validations = []
        assert _build_skill_label("01-skill", skill, show_validations=True) == "01-skill"

    def test_build_skill_label_truncated(self):
        from concilium.application.skills.graph_exporter import _build_skill_label

        skill = MagicMock()
        skill.validations = ["VAL-A", "VAL-B", "VAL-C"]
        result = _build_skill_label("01-skill", skill, show_validations=True)
        assert "VAL-A, VAL-B..." in result

    def test_append_dep_edges_skips_missing_dep(self):
        from concilium.application.skills.graph_exporter import _append_dep_edges

        registry = MagicMock()
        skill = MagicMock()
        skill.depends_on_skills = ["99-missing"]
        registry.skills = {"01-a": skill}
        registry.get_skill.return_value = skill
        lines: list = []
        _append_dep_edges(lines, registry, lambda x: x)
        assert len(lines) == 0  # dep not in registry → no edge

    def test_append_dep_edges_skips_duplicate_edge(self):
        """Branch 39->36: edge já processado (dep duplicado) pula o append e volta ao topo do loop."""
        from concilium.application.skills.graph_exporter import _append_dep_edges

        registry = MagicMock()
        skill_a = MagicMock()
        skill_a.depends_on_skills = []
        skill_b = MagicMock()
        # dep_id repetido duas vezes → segunda ocorrência é duplicata do edge já adicionado
        skill_b.depends_on_skills = ["01-a", "01-a"]
        registry.skills = {"01-a": skill_a, "02-b": skill_b}
        registry.get_skill.side_effect = lambda sid: registry.skills.get(sid)
        lines: list = []
        _append_dep_edges(lines, registry, lambda x: x)
        assert len(lines) == 1  # apenas 1 edge único, apesar do dep duplicado

    def test_group_skills_by_phase(self):
        from concilium.application.skills.graph_exporter import _group_skills_by_phase

        registry = MagicMock()
        registry.skills = {"01-escopo-e-eap": MagicMock()}
        result = _group_skills_by_phase(registry)
        assert isinstance(result, dict)

    def test_group_skills_by_phase_unknown_phase(self):
        """Line 25: skill with phase not in PHASE_MAP gets its own key."""
        from concilium.application.skills.graph_exporter import _group_skills_by_phase

        registry = MagicMock()
        # "99-unknown" will not match any known phase prefix → classify_phase returns
        # something not in PHASE_MAP, triggering the `if phase not in phases_dict` branch.
        registry.skills = {"99-unknown-xyz": MagicMock()}
        result = _group_skills_by_phase(registry)
        assert isinstance(result, dict)
        # All known phases present
        from concilium.application.skills.phase_classifier import PHASE_MAP

        for p in PHASE_MAP:
            assert p in result


class TestGetSkillNoneBranches:
    """Cover the `if not skill: continue` guards (lines 35, 74, 86, 92, 112, 130, 166, 174)."""

    def _registry_with_none_skill(self):
        """Registry where get_skill always returns None."""
        registry = MagicMock()
        registry.skills = {"01-skill-a": MagicMock()}
        registry.get_skill.return_value = None  # every call returns None
        return registry

    def test_to_mermaid_skips_none_skill(self):
        """Line 74: `if not skill: continue` in to_mermaid flat loop."""
        from concilium.application.skills.graph_exporter import SkillGraphExporter

        exporter = SkillGraphExporter(registry=self._registry_with_none_skill())
        result = exporter.to_mermaid()
        # No node definitions rendered but no crash
        assert result.startswith("graph TD")

    def test_to_mermaid_phases_skips_none_skill_in_phase(self):
        """Line 92: `if not skill: continue` inside phase subgraph loop."""
        from concilium.application.skills.graph_exporter import SkillGraphExporter

        registry = MagicMock()
        # Use a skill that maps to a known phase so the phase loop runs

        real_skill_id = "01-escopo-e-eap"
        registry.skills = {real_skill_id: MagicMock()}
        registry.get_skill.return_value = None  # returns None → triggers continue on line 92
        exporter = SkillGraphExporter(registry=registry)
        result = exporter.to_mermaid(group_by_phase=True)
        assert "graph TD" in result

    def test_append_dep_edges_get_skill_none(self):
        """Line 35: `if not skill: continue` in _append_dep_edges."""
        from concilium.application.skills.graph_exporter import _append_dep_edges

        registry = MagicMock()
        registry.skills = {"01-a": MagicMock()}
        registry.get_skill.return_value = None
        lines: list = []
        _append_dep_edges(lines, registry, lambda x: x)
        assert lines == []  # no edges added, no crash

    def test_to_json_skips_none_skill_in_nodes_loop(self):
        """Line 112: `if not skill: continue` in to_json nodes loop."""
        from concilium.application.skills.graph_exporter import SkillGraphExporter

        exporter = SkillGraphExporter(registry=self._registry_with_none_skill())
        result = exporter.to_json()
        assert result["total_skills"] == 0
        assert result["nodes"] == []

    def test_to_json_skips_none_skill_in_edges_loop(self):
        """Line 130: `if not skill: continue` in to_json edges loop.

        First call (nodes loop) also returns None but we need the edges loop to fire.
        Use side_effect so the first call returns a valid skill (node recorded),
        the second call (edges loop) returns None.
        """
        from concilium.application.skills.graph_exporter import SkillGraphExporter

        real_skill = MagicMock()
        real_skill.version = "1.0"
        real_skill.descricao = "Test"
        real_skill.produces_section = "sec"
        real_skill.validations = []
        real_skill.depends_on_skills = []

        registry = MagicMock()
        registry.skills = {"01-skill-a": real_skill}
        # First call (sorted loop for nodes) → real; second call (edges loop) → None
        registry.get_skill.side_effect = [real_skill, None]
        exporter = SkillGraphExporter(registry=registry)
        result = exporter.to_json()
        assert result["total_skills"] == 1
        assert result["total_dependencies"] == 0

    def test_to_dot_skips_none_skill_in_nodes(self):
        """Line 166: `if not skill: continue` in to_dot nodes loop."""
        from concilium.application.skills.graph_exporter import SkillGraphExporter

        exporter = SkillGraphExporter(registry=self._registry_with_none_skill())
        result = exporter.to_dot()
        assert result.startswith("digraph SkillPipeline {")
        # No node lines added (other than header), no crash

    def test_to_dot_skips_none_skill_in_edges(self):
        """Line 174: `if not skill: continue` in to_dot edges loop."""
        from concilium.application.skills.graph_exporter import SkillGraphExporter

        real_skill = MagicMock()
        real_skill.depends_on_skills = []

        registry = MagicMock()
        registry.skills = {"01-skill-a": real_skill}
        # First call (nodes loop) → real skill; second call (edges loop) → None
        registry.get_skill.side_effect = [real_skill, None]
        exporter = SkillGraphExporter(registry=registry)
        result = exporter.to_dot()
        assert "digraph SkillPipeline {" in result

    def test_to_mermaid_with_phases_skips_empty_phase(self):
        """Line 86: `if not phases_dict.get(phase): continue` skips empty phase."""
        from concilium.application.skills.graph_exporter import SkillGraphExporter

        # Registry with no skills → all phases are empty → every phase is skipped
        registry = MagicMock()
        registry.skills = {}
        registry.get_skill.return_value = None
        exporter = SkillGraphExporter(registry=registry)
        result = exporter.to_mermaid(group_by_phase=True)
        # No subgraphs in output since all phases empty
        assert "subgraph" not in result
        assert result.startswith("graph TD")
