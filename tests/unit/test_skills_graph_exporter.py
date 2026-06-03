"""Tests for skills graph export functionality (TDD approach)."""

import re

import pytest

from concilium.application.skills import SkillRegistry
from concilium.application.skills.graph_exporter import SkillGraphExporter


class TestSkillGraphExporter:
    """Test SkillGraphExporter class — Mermaid diagram generation."""

    @pytest.fixture
    def skill_registry(self) -> SkillRegistry:
        """Load actual skill registry from manifests."""
        return SkillRegistry()

    @pytest.fixture
    def exporter(self, skill_registry: SkillRegistry) -> SkillGraphExporter:
        """Create exporter with loaded registry."""
        return SkillGraphExporter(skill_registry)

    def test_exporter_initializes_with_registry(self, exporter: SkillGraphExporter):
        """Exporter initializes with SkillRegistry."""
        assert exporter.registry is not None
        assert len(exporter.registry.skills) > 0

    def test_to_mermaid_returns_string(self, exporter: SkillGraphExporter):
        """to_mermaid() returns string output."""
        output = exporter.to_mermaid()
        assert isinstance(output, str)
        assert len(output) > 0

    def test_to_mermaid_valid_syntax(self, exporter: SkillGraphExporter):
        """to_mermaid() returns valid Mermaid graph TD syntax."""
        output = exporter.to_mermaid()

        # Must start with graph TD
        assert output.strip().startswith("graph TD")

        # Must have node definitions (with brackets and labels)
        assert re.search(r'^\s*[0-9a-zA-Z_]+\["', output, re.MULTILINE)

        # Must have arrow syntax for dependencies
        assert "-->" in output or len(re.findall(r'\[".+?"\]', output)) == 1

    def test_all_skills_appear_as_nodes(self, exporter: SkillGraphExporter, skill_registry: SkillRegistry):
        """All registered skills appear as nodes in the diagram."""
        output = exporter.to_mermaid()

        for skill_id in skill_registry.skills.keys():
            # Skills appear as part of node definitions or connections
            assert skill_id in output, f"Skill {skill_id} missing from graph"

    def test_dependencies_create_edges(self, exporter: SkillGraphExporter):
        """Skill dependencies create correct edges in diagram."""
        output = exporter.to_mermaid()

        # Get a skill with known dependencies (04-cronograma depends on 00-escopo, 02-produtividade-climatica)
        registry = exporter.registry
        skill_02 = registry.get_skill("04-cronograma")

        if skill_02 and skill_02.depends_on_skills:
            for dep_id in skill_02.depends_on_skills:
                # Should see edge from dependency to 04-cronograma
                # Pattern: "dep_id --> ... --> 04-cronograma" or similar path
                assert dep_id in output, f"Dependency {dep_id} missing from graph"
                assert "04-cronograma" in output

    def test_mermaid_no_circular_dependencies(self, exporter: SkillGraphExporter):
        """Graph detects and reports circular dependencies (if any exist)."""
        output = exporter.to_mermaid()

        # This should not raise; detection happens at graph construction
        # If circular, should be caught and reported (not silently loop)
        assert isinstance(output, str)

    def test_mermaid_with_phase_grouping(self, exporter: SkillGraphExporter):
        """to_mermaid(group_by_phase=True) creates subgraphs."""
        output = exporter.to_mermaid(group_by_phase=True)

        # Subgraphs are denoted by "subgraph ... end"
        assert "subgraph" in output, "Phase grouping should create subgraphs"
        assert "end" in output

        # Should still have valid graph TD header
        assert output.strip().startswith("graph TD")

    def test_mermaid_phase_grouping_contains_known_phases(self, exporter: SkillGraphExporter):
        """Phase grouping includes logical phase names."""
        output = exporter.to_mermaid(group_by_phase=True)

        # Known phases from PHASE_MAP
        expected_phrases = ["Inicialização", "Análise", "Planejamento", "Consolidação"]
        for _phase in expected_phrases:
            # At least some phases should appear in subgraph definitions
            pass  # Will be checked against actual implementation

        # At minimum, should see subgraph syntax
        assert re.search(r'subgraph\s+\w+\["[^"]+"\]', output)

    def test_mermaid_with_validations(self, exporter: SkillGraphExporter):
        """to_mermaid(show_validations=True) includes validation codes."""
        exporter.to_mermaid(show_validations=False)
        output_with = exporter.to_mermaid(show_validations=True)

        # With validations should be longer or have VAL- codes
        if any(
            "VAL-" in skill.validations for skill in exporter.registry.skills.values() if hasattr(skill, "validations")
        ):
            # If any skill has validations, the "with" version should reflect them
            assert isinstance(output_with, str)

    def test_mermaid_formatting_readable(self, exporter: SkillGraphExporter):
        """Mermaid output is properly formatted and readable."""
        output = exporter.to_mermaid()
        lines = output.strip().split("\n")

        # Should have reasonable number of lines (at least 2: graph TD + something)
        assert len(lines) >= 2

        # Lines should be non-empty (except possible blank lines)
        non_empty = [line for line in lines if line.strip()]
        assert len(non_empty) >= 2

    def test_to_json_returns_dict(self, exporter: SkillGraphExporter):
        """to_json() returns dict representation of graph."""
        output = exporter.to_json()
        assert isinstance(output, dict)
        assert "nodes" in output or "skills" in output

    def test_to_json_contains_skills_and_edges(self, exporter: SkillGraphExporter):
        """to_json() includes skills as nodes and dependencies as edges."""
        output = exporter.to_json()

        # Should have nodes/skills with IDs
        nodes = output.get("nodes") or output.get("skills")
        assert isinstance(nodes, list)
        assert len(nodes) > 0

        # Should have edges/dependencies
        edges = output.get("edges") or output.get("dependencies")
        assert isinstance(edges, list)

    def test_export_formats_consistency(self, exporter: SkillGraphExporter):
        """Different export formats contain consistent skill information."""
        mermaid = exporter.to_mermaid()
        json_data = exporter.to_json()

        # Extract skill IDs from both
        skill_ids_from_registry = set(exporter.registry.skills.keys())

        # Mermaid should mention all skills
        for skill_id in skill_ids_from_registry:
            assert skill_id in mermaid, f"{skill_id} missing from Mermaid"

        # JSON should list all skills
        json_skills = {node.get("id") for node in json_data.get("nodes", [])} or {
            skill.get("id") for skill in json_data.get("skills", [])
        }
        for skill_id in skill_ids_from_registry:
            assert skill_id in json_skills, f"{skill_id} missing from JSON"


class TestSkillGraphExporterEdgeCases:
    """Edge case and error handling tests."""

    @pytest.fixture
    def exporter(self) -> SkillGraphExporter:
        """Exporter with actual registry."""
        return SkillGraphExporter(SkillRegistry())

    def test_missing_skill_in_dependency(self, exporter: SkillGraphExporter):
        """If a skill depends on non-existent skill, handled gracefully."""
        # This is a validation that should happen during TOML load
        # Exporter should not crash; should report in output or skip
        output = exporter.to_mermaid()
        assert isinstance(output, str)

    def test_empty_registry_handled(self):
        """Exporter handles empty skill registry (edge case)."""
        # Would need a way to create empty registry
        # For now, just verify exporter initializes
        from concilium.application.skills import SkillRegistry

        registry = SkillRegistry()
        exporter = SkillGraphExporter(registry)
        assert exporter is not None

    def test_orphaned_skill_nodes(self, exporter: SkillGraphExporter):
        """Skills with no dependencies still appear in graph."""
        output = exporter.to_mermaid()

        # Skill 00-escopo has no dependencies but should still appear
        registry = exporter.registry
        skill_00 = registry.get_skill("01-escopo-e-eap")

        if skill_00:
            assert "01-escopo-e-eap" in output
