from __future__ import annotations

from pathlib import Path

import pytest

from concilium.application.benchmarks.execution.facade import BenchmarkFacade
from concilium.application.skills.phase_classifier import get_pipeline_profile_for_intent


def _artifact_files(artifacts_root: Path) -> set[str]:
    if not artifacts_root.exists():
        return set()
    return {p.name for p in artifacts_root.rglob("*") if p.is_file()}


@pytest.mark.slow
def test_intent_artifacts_match_profile_deliverables(config_root):
    """Cada intent RFX deve materializar ao menos os entregáveis previstos no perfil.

    Pesado: roda o pipeline completo do AGIS 3× (rfi/rfp/rfq) com reset.
    """
    root = config_root.parent
    facade = BenchmarkFacade.from_root(root)

    # AGIS é benchmark estável no repositório e já usado em outros testes de integração.
    for intent in ("rfi", "rfp", "rfq"):
        report = facade.run_single("AGIS", reset=True, procurement_intent=intent)
        assert report is not None

        profile = get_pipeline_profile_for_intent(intent)
        artifacts_root = root / "benchmarks" / "projetos" / "AGIS" / "artifacts"
        files = _artifact_files(artifacts_root)

        # Alguns entregáveis podem ser opcionais em dados sintéticos/seed;
        # validamos o contrato mínimo presente no perfil e no disco.
        for deliverable in profile.deliverables:
            assert deliverable in files, f"Entregável '{deliverable}' ausente para intent='{intent}'"