"""Skill graph exporter — generates Mermaid diagrams and other formats."""

from typing import Any

from concilium.application.skills.phase_classifier import PHASE_MAP, classify_phase
from concilium.application.skills.registry import SkillRegistry


class SkillGraphExporter:
    """Exports skill dependency graph in various formats."""

    def __init__(self, registry: SkillRegistry | None = None):
        """Initialize exporter with skill registry."""
        if registry is None:
            registry = SkillRegistry()
        self.registry = registry

    def to_mermaid(
        self,
        group_by_phase: bool = False,
        show_validations: bool = False,
    ) -> str:
        """Generate Mermaid graph TD diagram of skill dependencies.

        Args:
            group_by_phase: If True, organize skills into subgraphs by phase
            show_validations: If True, include VAL-* codes in node labels

        Returns:
            Valid Mermaid graph TD definition as string
        """
        lines: list[str] = ["graph TD"]

        if group_by_phase:
            return self._to_mermaid_with_phases(show_validations)

        # Flat graph: define all nodes first
        for skill_id in sorted(self.registry.skills.keys()):
            skill = self.registry.get_skill(skill_id)
            if not skill:
                continue

            # Node label with optional validations
            label = skill_id
            if show_validations and skill.validations:
                val_str = ", ".join(skill.validations[:2])  # Limit to 2 for readability
                if len(skill.validations) > 2:
                    val_str += "..."
                label = f"{skill_id}<br/>({val_str})"

            lines.append(f'    {self._node_id(skill_id)}["{label}"]')

        # Add edges for dependencies
        edges_added: set[tuple[str, str]] = set()
        for skill_id in self.registry.skills.keys():
            skill = self.registry.get_skill(skill_id)
            if not skill:
                continue

            for dep_id in skill.depends_on_skills:
                if dep_id in self.registry.skills:
                    edge = (self._node_id(dep_id), self._node_id(skill_id))
                    if edge not in edges_added:
                        lines.append(f"    {edge[0]} --> {edge[1]}")
                        edges_added.add(edge)

        return "\n".join(lines)

    def _to_mermaid_with_phases(self, show_validations: bool = False) -> str:
        """Generate Mermaid with phase grouping (subgraphs)."""
        lines: list[str] = ["graph TD"]

        # Group skills by phase
        phases_dict: dict[str, list[str]] = {}
        for phase in PHASE_MAP.keys():
            phases_dict[phase] = []

        for skill_id in self.registry.skills.keys():
            phase = classify_phase(skill_id)
            if phase not in phases_dict:
                phases_dict[phase] = []
            phases_dict[phase].append(skill_id)

        # Create subgraphs for each phase
        phase_node_ids: dict[str, str] = {}
        for phase in PHASE_MAP.keys():
            if not phases_dict.get(phase):
                continue

            phase_id = self._node_id(phase)
            phase_node_ids[phase] = phase_id
            lines.append(f'    subgraph {phase_id}["{phase}"]')

            for skill_id in sorted(phases_dict[phase]):
                skill = self.registry.get_skill(skill_id)
                if not skill:
                    continue

                label = skill_id
                if show_validations and skill.validations:
                    val_str = ", ".join(skill.validations[:2])
                    if len(skill.validations) > 2:
                        val_str += "..."
                    label = f"{skill_id}<br/>({val_str})"

                lines.append(f'        {self._node_id(skill_id)}["{label}"]')

            lines.append("    end")

        # Add edges for dependencies (outside subgraphs)
        edges_added: set[tuple[str, str]] = set()
        for skill_id in self.registry.skills.keys():
            skill = self.registry.get_skill(skill_id)
            if not skill:
                continue

            for dep_id in skill.depends_on_skills:
                if dep_id in self.registry.skills:
                    edge = (self._node_id(dep_id), self._node_id(skill_id))
                    if edge not in edges_added:
                        lines.append(f"    {edge[0]} --> {edge[1]}")
                        edges_added.add(edge)

        return "\n".join(lines)

    def to_json(self) -> dict[str, Any]:
        """Generate JSON representation of skill graph.

        Returns:
            Dict with 'nodes' (skills) and 'edges' (dependencies)
        """
        nodes: list[dict[str, Any]] = []
        edges: list[dict[str, Any]] = []

        # Create nodes
        for skill_id in sorted(self.registry.skills.keys()):
            skill = self.registry.get_skill(skill_id)
            if not skill:
                continue

            nodes.append(
                {
                    "id": skill_id,
                    "version": skill.version,
                    "descricao": skill.descricao,
                    "produces": skill.produces_section,
                    "validations": skill.validations,
                    "phase": classify_phase(skill_id),
                }
            )

        # Create edges
        edges_added: set[tuple[str, str]] = set()
        for skill_id in self.registry.skills.keys():
            skill = self.registry.get_skill(skill_id)
            if not skill:
                continue

            for dep_id in skill.depends_on_skills:
                if dep_id in self.registry.skills:
                    edge_tuple = (dep_id, skill_id)
                    if edge_tuple not in edges_added:
                        edges.append(
                            {
                                "from": dep_id,
                                "to": skill_id,
                                "type": "depends_on",
                            }
                        )
                        edges_added.add(edge_tuple)

        return {
            "nodes": nodes,
            "edges": edges,
            "total_skills": len(nodes),
            "total_dependencies": len(edges),
        }

    def to_dot(self) -> str:
        """Generate GraphViz DOT format (future extension).

        Returns:
            Valid DOT format for use with Graphviz
        """
        lines: list[str] = ["digraph SkillPipeline {"]
        lines.append("    rankdir=TB;")
        lines.append("    node [shape=box, style=filled, fillcolor=lightblue];")

        # Add nodes
        for skill_id in sorted(self.registry.skills.keys()):
            skill = self.registry.get_skill(skill_id)
            if not skill:
                continue
            lines.append(f'    "{skill_id}" [label="{skill_id}"];')

        # Add edges
        edges_added: set[tuple[str, str]] = set()
        for skill_id in self.registry.skills.keys():
            skill = self.registry.get_skill(skill_id)
            if not skill:
                continue

            for dep_id in skill.depends_on_skills:
                if dep_id in self.registry.skills:
                    edge = (dep_id, skill_id)
                    if edge not in edges_added:
                        lines.append(f'    "{dep_id}" -> "{skill_id}";')
                        edges_added.add(edge)

        lines.append("}")
        return "\n".join(lines)

    @staticmethod
    def _node_id(skill_id: str) -> str:
        """Convert skill ID to valid Mermaid node ID (alphanumeric + underscore)."""
        # Replace hyphens with underscores
        return skill_id.replace("-", "_")
