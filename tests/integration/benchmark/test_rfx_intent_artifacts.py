from __future__ import annotations

from pathlib import Path

import pytest

from concilium.application.skills.phase_classifier import get_pipeline_profile_for_intent


def _artifact_files(artifacts_root: Path) -> set[str]:
    if not artifacts_root.exists():
        return set()
    return {p.name for p in artifacts_root.rglob("*") if p.is_file()}


@pytest.mark.slow
def test_intent_artifacts_match_profile_deliverables(golden_rfi_artifacts, golden_rfp_artifacts):
    """Cada intent RFX deve materializar ao menos os entregáveis previstos no perfil.

    Usa projeto GOLDEN (ADR-114) — sintético mínimo (3 itens EAP) para validar
    invariantes do sistema sem acoplamento a dados de cliente reais.

    Performance:
    - Antes: ~28.65s (re-executava GOLDEN 2× dentro do teste)
    - Depois: ~15s (usa fixtures session-scoped que executam UMA VEZ)
    """
    # Validar entregáveis para RFI
    profile_rfi = get_pipeline_profile_for_intent("rfi")
    files_rfi = _artifact_files(golden_rfi_artifacts)
    for deliverable in profile_rfi.deliverables:
        assert deliverable in files_rfi, f"Entregável '{deliverable}' ausente para intent='rfi'"

    # Validar entregáveis para RFP
    profile_rfp = get_pipeline_profile_for_intent("rfp")
    files_rfp = _artifact_files(golden_rfp_artifacts)
    for deliverable in profile_rfp.deliverables:
        assert deliverable in files_rfp, f"Entregável '{deliverable}' ausente para intent='rfp'"
