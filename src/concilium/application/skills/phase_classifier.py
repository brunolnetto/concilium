"""Phase classification for skills — organizes skills into logical groups."""

from collections import defaultdict

from concilium.application.skills import MANIFEST_META

# Preserve canonical display order
_PHASE_ORDER = ["Definição", "Planejamento", "Consolidação", "Análise", "Decisão", "Saída"]

# Build PHASE_MAP dynamically from TOML manifests
_phase_index: dict[str, list[str]] = defaultdict(list)
for _sid, _meta in MANIFEST_META.items():
    _phase_index[_meta.get("phase", "Sem Classificação")].append(_sid)

# Map of phase name to list of skill IDs in that phase
PHASE_MAP: dict[str, list[str]] = {p: _phase_index[p] for p in _PHASE_ORDER if p in _phase_index}
# Include any extra phases not in canonical order
for _p, _skills in _phase_index.items():
    if _p not in PHASE_MAP:
        PHASE_MAP[_p] = _skills

# Reverse mapping: skill_id -> phase (derived from MANIFEST_META directly)
_MANIFEST_META_BY_PHASE: dict[str, str] = {
    sid: meta.get("phase", "Sem Classificação") for sid, meta in MANIFEST_META.items()
}


def classify_phase(skill_id: str) -> str:
    """Classify which phase a skill belongs to.

    Args:
        skill_id: The skill ID (e.g., "04-cronograma")

    Returns:
        Phase name (e.g., "Planejamento"), or "Sem Classificação" if unknown
    """
    return _MANIFEST_META_BY_PHASE.get(skill_id, "Sem Classificação")


def get_phase_skills(phase: str) -> list[str]:
    """Get all skills in a given phase.

    Args:
        phase: Phase name

    Returns:
        List of skill IDs in that phase, or empty list if phase not found
    """
    return PHASE_MAP.get(phase, [])


def get_all_phases() -> list[str]:
    """Get all defined phases in order."""
    return list(PHASE_MAP.keys())


# ── Canonical pipeline execution order (single source of truth) ───────────────
# Derived from PHASE_MAP so that any new skill added to a phase is automatically
# included in auto-advance without touching pipeline.py (DRY / ADR-026 §D6).
# NEP-041 F3: skills com status="dormante" são excluídas do pipeline automático
# (permanecem em SKILLS, invocáveis explicitamente).
_DORMANTES: set[str] = {sid for sid, meta in MANIFEST_META.items() if meta.get("status") == "dormante"}
CANONICAL_SKILL_ORDER: list[str] = [
    skill_id for phase in PHASE_MAP.values() for skill_id in phase if skill_id not in _DORMANTES
]
