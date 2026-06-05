"""Skill registry — loads and manages skill metadata from TOML manifests."""

import tomllib
from dataclasses import dataclass
from pathlib import Path
from typing import Any


@dataclass
class SkillMetadata:
    """Metadata extracted from skill.toml."""

    id: str
    version: str
    descricao: str
    is_gate: bool
    depends_on_skills: list[str]
    canonical_sections_required: list[str]
    produces_section: str
    validations: list[str]
    inputs_required: list[str]
    inputs_optional: list[str]

    def __hash__(self) -> int:
        return hash(self.id)

    def __eq__(self, other: Any) -> bool:
        if isinstance(other, SkillMetadata):
            return self.id == other.id
        return False


class SkillRegistry:
    """Loads and manages skill metadata from manifests."""

    _instance: "SkillRegistry | None" = None

    def __new__(cls, manifests_dir: Path | None = None) -> "SkillRegistry":
        """Singleton pattern: return cached instance on subsequent calls."""
        if cls._instance is None:
            instance = super().__new__(cls)
            instance._initialized = False  # type: ignore[has-type]
            cls._instance = instance
        return cls._instance

    def __init__(self, manifests_dir: Path | None = None):
        """Initialize registry by loading all skill.toml files (once)."""
        if self._initialized:  # type: ignore[has-type]
            return

        if manifests_dir is None:
            manifests_dir = Path(__file__).parent / "manifests"

        self.manifests_dir = manifests_dir
        self.skills: dict[str, SkillMetadata] = {}
        self._load_all_skills()
        self._initialized = True

    def _load_all_skills(self) -> None:
        """Discover and load all skills from manifests directory."""
        if not self.manifests_dir.exists():
            return

        for manifest_dir in sorted(self.manifests_dir.iterdir()):
            if not manifest_dir.is_dir():
                continue

            toml_path = manifest_dir / "skill.toml"
            if not toml_path.exists():
                continue

            try:
                with open(toml_path, "rb") as f:
                    config = tomllib.load(f)
                metadata = self._parse_toml(config, toml_path)
                if metadata:
                    self.skills[metadata.id] = metadata
            except Exception as e:
                raise RuntimeError(f"Error loading skill from {toml_path}: {e}") from e

    def _parse_toml(self, config: dict[str, Any], toml_path: Path) -> SkillMetadata | None:
        """Parse TOML config into SkillMetadata."""
        skill_section = config.get("skill", {})
        depends_section = config.get("depends_on", {})
        produces_section = config.get("produces", {})
        inputs_section = config.get("inputs", {})

        skill_id = skill_section.get("id")
        if not skill_id:
            return None

        return SkillMetadata(
            id=skill_id,
            version=skill_section.get("version", "1.0.0"),
            descricao=skill_section.get("descricao", ""),
            is_gate=skill_section.get("gate", False),
            depends_on_skills=depends_section.get("skills", []),
            canonical_sections_required=depends_section.get("canonical_sections", []),
            produces_section=produces_section.get("canonical_section", ""),
            validations=produces_section.get("validations", []),
            inputs_required=inputs_section.get("required", []),
            inputs_optional=inputs_section.get("optional", []),
        )

    def get_skill(self, skill_id: str) -> SkillMetadata | None:
        """Get metadata for a specific skill."""
        return self.skills.get(skill_id)

    def get_all_skills(self) -> dict[str, SkillMetadata]:
        """Get all loaded skills."""
        return self.skills

    def get_dependencies_for(self, skill_id: str) -> list[str]:
        """Get list of skills that the given skill depends on."""
        skill = self.get_skill(skill_id)
        return skill.depends_on_skills if skill else []

    def get_dependents_of(self, skill_id: str) -> list[str]:
        """Get list of skills that depend on the given skill."""
        dependents = []
        for skill in self.skills.values():
            if skill_id in skill.depends_on_skills:
                dependents.append(skill.id)
        return dependents

    def get_topological_order(self) -> list[str]:
        """Return skills in topological order (dependencies first)."""
        visited: set[str] = set()
        order: list[str] = []

        def visit(skill_id: str) -> None:
            if skill_id in visited:
                return
            visited.add(skill_id)

            skill = self.get_skill(skill_id)
            if skill:
                for dep_id in skill.depends_on_skills:
                    if dep_id in self.skills:
                        visit(dep_id)

            order.append(skill_id)

        for skill_id in sorted(self.skills.keys()):
            visit(skill_id)

        return order
