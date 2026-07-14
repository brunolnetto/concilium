"""Phase classification for skills — organizes skills into logical groups.

ADR-113: skills são classificadas em dois tiers de execução:
  OLTP (01-06): resultado de planejamento em < 30s
  OLAP (07-11): análise analítica e artefatos (pesado, opcional)
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from enum import StrEnum

from concilium.application.skills import MANIFEST_META

# ── Tiers de execução (ADR-113) ───────────────────────────────────────────────


class PipelineMode(StrEnum):
    """Modo de execução do pipeline de skills.

    OLTP  — skills 01-06: resultado de planejamento em tempo real (< 30s)
    LIGHT — skills 01-06 + relatorio: planejamento com relatório básico (30-90s)
    OLAP  — skills 01-11: pipeline completo com análise e artefatos (2-5min)
    """

    OLTP = "oltp"  # planejamento: 01-06
    LIGHT = "light"  # planejamento + relatório: 01-06 + 10-relatorio
    OLAP = "olap"  # completo: 01-11


class ProcurementIntent(StrEnum):
    """Intenção de procurement no fluxo RFX."""

    RFI = "rfi"
    RFP = "rfp"


@dataclass(frozen=True)
class PipelineProfile:
    """Perfil de execução orientado por linguagem de negócio (RFX)."""

    intent: ProcurementIntent
    mode: PipelineMode
    path_name: str
    skill_sequence: list[str]
    deliverables: list[str]


def get_skills_for_mode(mode: PipelineMode) -> list[str]:
    """Retorna lista de skill IDs para o modo especificado.

    Usa MANIFEST_META (skill.toml) como fonte de verdade — funciona
    tanto com IDs atuais quanto após a renumeração F4.
    """
    oltp_ids = sorted(sid for sid, meta in MANIFEST_META.items() if meta.get("tier") == "oltp")
    olap_ids = sorted(sid for sid, meta in MANIFEST_META.items() if meta.get("tier") == "olap")

    if mode == PipelineMode.OLTP:
        return oltp_ids
    if mode == PipelineMode.OLAP:
        return oltp_ids + olap_ids
    if mode == PipelineMode.LIGHT:
        # LIGHT = OLTP + apenas o skill de relatório-e-artefatos (saída direta)
        relatorio = [sid for sid in olap_ids if "relatorio" in sid]
        return oltp_ids + relatorio
    return oltp_ids + olap_ids  # fallback seguro  # pragma: no cover


def get_pipeline_profile_for_intent(intent: ProcurementIntent | str) -> PipelineProfile:
    """Resolve perfil RFX em termos de nós/caminho/entregáveis da pipeline.

    Esta função institucionaliza a linguagem ubiqua de procurement no core da
    orquestração (e não nas tools):

    - RFI: precificação de catálogo (PU x Q), sem trilha analítica pesada.
    - RFP: comparação técnico-econômica completa com cronograma e análise.
      O RFP aprovado segue diretamente para aprovação do cliente.
    """
    if isinstance(intent, ProcurementIntent):
        resolved = intent
    else:
        try:
            resolved = ProcurementIntent(str(intent).strip().lower())
        except Exception:
            resolved = ProcurementIntent.RFI

    if resolved == ProcurementIntent.RFP:
        return PipelineProfile(
            intent=resolved,
            mode=PipelineMode.OLAP,
            path_name="RFP_TECNICO_ECONOMICO",
            skill_sequence=get_skills_for_mode(PipelineMode.OLAP),
            deliverables=[
                "benchmark_report.json",
                "relatorio.pdf",
                "resultado_planejamento.xlsx",
            ],
        )

    return PipelineProfile(
        intent=ProcurementIntent.RFI,
        mode=PipelineMode.OLTP,
        path_name="RFI_EXPLORACAO_CATALOGO",
        skill_sequence=get_skills_for_mode(PipelineMode.OLTP),
        deliverables=["benchmark_report.json"],
    )


def normalize_procurement_intent(intent: ProcurementIntent | str | None) -> ProcurementIntent:
    """Normaliza intenção de procurement para enum tipado (fallback=RFI)."""
    if isinstance(intent, ProcurementIntent):
        return intent
    try:
        return ProcurementIntent(str(intent or "").strip().lower())
    except Exception:
        return ProcurementIntent.RFI


def is_campaign_allowed_for_intent(intent: ProcurementIntent | str | None) -> bool:
    """Campanha GO é permitida apenas para RFP."""
    normalized = normalize_procurement_intent(intent)
    return normalized == ProcurementIntent.RFP


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

# ── Alias map ADR-113 F3: IDs legados → novos após renumeração ─────────────────
# Permite que callers com IDs antigos continuem funcionando durante F4 (renaming).
# Remover após todos os callers atualizados.
SKILL_ID_ALIASES: dict[str, str] = {
    # legado → novo (após renumeração F4)
    "10-relatorio-e-artefatos": "10-relatorio-e-artefatos",
    "07-diagnostico-criticidade": "07-diagnostico-criticidade",
    "11-replanejamento-e-cenarios": "11-replanejamento-e-cenarios",
}

# Mapeamento inverso (novo → legado), para referência
SKILL_ID_CANONICAL: dict[str, str] = {v: k for k, v in SKILL_ID_ALIASES.items()}


def resolve_skill_id(skill_id: str) -> str:
    """Resolve um skill ID potencialmente legado para o ID canônico atual.

    Durante a transição F3→F4:
    - Se o diretório antigo ainda existe: retorna o ID antigo (sem mudança)
    - Após F4 (renaming): SKILL_ID_ALIASES aponta para os novos IDs
    """
    return SKILL_ID_ALIASES.get(skill_id, skill_id)


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
