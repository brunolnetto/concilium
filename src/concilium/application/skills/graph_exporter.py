"""Skill graph exporter — generates Mermaid diagrams and other formats."""

from typing import Any

from concilium.application.skills.phase_classifier import PHASE_MAP, classify_phase
from concilium.application.skills.registry import SkillRegistry


def _build_skill_label(skill_id: str, skill, show_validations: bool) -> str:
    if show_validations and skill.validations:
        val_str = ", ".join(skill.validations[:2])
        if len(skill.validations) > 2:
            val_str += "..."
        return f"{skill_id}<br/>({val_str})"
    return skill_id


def _group_skills_by_phase(registry) -> dict:
    phases_dict: dict = {}
    for phase in PHASE_MAP.keys():
        phases_dict[phase] = []
    for skill_id in registry.skills.keys():
        phase = classify_phase(skill_id)
        if phase not in phases_dict:
            phases_dict[phase] = []
        phases_dict[phase].append(skill_id)
    return phases_dict


def _append_dep_edges(lines: list, registry, node_id_fn, indent: str = "    ") -> None:
    edges_added: set = set()
    for skill_id in registry.skills.keys():
        skill = registry.get_skill(skill_id)
        if not skill:
            continue
        for dep_id in skill.depends_on_skills:
            if dep_id in registry.skills:
                edge = (node_id_fn(dep_id), node_id_fn(skill_id))
                if edge not in edges_added:
                    lines.append(f"{indent}{edge[0]} --> {edge[1]}")
                    edges_added.add(edge)


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
        if group_by_phase:
            return self._to_mermaid_with_phases(show_validations)

        lines: list[str] = ["graph TD"]
        for skill_id in sorted(self.registry.skills.keys()):
            skill = self.registry.get_skill(skill_id)
            if not skill:
                continue
            label = _build_skill_label(skill_id, skill, show_validations)
            lines.append(f'    {self._node_id(skill_id)}["{label}"]')
        _append_dep_edges(lines, self.registry, self._node_id, "    ")
        return "\n".join(lines)

    def _to_mermaid_with_phases(self, show_validations: bool = False) -> str:
        """Generate Mermaid with phase grouping (subgraphs)."""
        lines: list[str] = ["graph TD"]
        phases_dict = _group_skills_by_phase(self.registry)
        for phase in PHASE_MAP.keys():
            if not phases_dict.get(phase):
                continue
            phase_id = self._node_id(phase)
            lines.append(f'    subgraph {phase_id}["{phase}"]')
            for skill_id in sorted(phases_dict[phase]):
                skill = self.registry.get_skill(skill_id)
                if not skill:
                    continue
                label = _build_skill_label(skill_id, skill, show_validations)
                lines.append(f'        {self._node_id(skill_id)}["{label}"]')
            lines.append("    end")
        _append_dep_edges(lines, self.registry, self._node_id, "    ")
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
