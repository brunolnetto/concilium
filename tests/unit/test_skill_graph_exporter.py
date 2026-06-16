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
        skill_mock.depends_on_skills = [f"{(i-1):02d}-skill-{i-1}"] if i > 1 else []
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

    def test_group_skills_by_phase(self):
        from concilium.application.skills.graph_exporter import _group_skills_by_phase
        registry = MagicMock()
        registry.skills = {"01-escopo-e-eap": MagicMock()}
        result = _group_skills_by_phase(registry)
        assert isinstance(result, dict)
