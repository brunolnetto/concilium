"""Fixtures para testes de integração de benchmark.

Performance:
- golden_rfi_artifacts: ~15s (GOLDEN com intent='rfi', session-scoped)
- golden_rfp_artifacts: ~15s (GOLDEN com intent='rfp', session-scoped)
- Ambas evitam re-executar benchmarks dentro do mesmo teste
"""

from pathlib import Path

import pytest


@pytest.fixture(scope="session")
def golden_rfi_artifacts(config_root) -> Path:
    """Fixture session-scoped que executa GOLDEN com intent='rfi' UMA VEZ.

    Retorna caminho dos artifacts para validação nos testes.
    Tempo: ~15s (reutilizado por todos os testes na sessão)
    """
    from concilium.application.benchmarks.execution.facade import BenchmarkFacade

    root = config_root.parent
    facade = BenchmarkFacade.from_root(root)
    facade.run_single("GOLDEN", reset=True, procurement_intent="rfi")
    return root / "benchmarks" / "projetos" / "GOLDEN" / "artifacts"


@pytest.fixture(scope="session")
def golden_rfp_artifacts(config_root) -> Path:
    """Fixture session-scoped que executa GOLDEN com intent='rfp' UMA VEZ.

    Retorna caminho dos artifacts para validação nos testes.
    Tempo: ~15s (reutilizado por todos os testes na sessão)
    """
    from concilium.application.benchmarks.execution.facade import BenchmarkFacade

    root = config_root.parent
    facade = BenchmarkFacade.from_root(root)
    facade.run_single("GOLDEN", reset=True, procurement_intent="rfp")
    return root / "benchmarks" / "projetos" / "GOLDEN" / "artifacts"
