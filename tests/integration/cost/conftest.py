"""Fixtures para testes de integração de custo (ADR-104).

Performance:
- golden_benchmark: ~15s (projeto sintético GOLDEN, 3 itens)
- agis_benchmark: ~62s (projeto real AGIS, ~100+ itens) — use apenas se realmente necessário
"""

import pytest


@pytest.fixture(scope="session")
def golden_benchmark(config_root):
    """Fixture que retorna o canonical model do benchmark GOLDEN (sintético, rápido).

    Executa o pipeline do GOLDEN (projeto sintético mínimo com 3 itens EAP)
    via BenchmarkFacade. Ideal para testes que precisam validar invariantes
    estruturais sem necessidade de dados reais complexos.

    Tempo: ~15s (vs ~62s para AGIS)
    """
    from concilium.application.benchmarks.execution.facade import BenchmarkFacade
    from concilium.infrastructure.storage.store_factory import build_local_project_repository

    root = config_root.parent
    facade = BenchmarkFacade.from_root(root)

    # Executar benchmark GOLDEN (projeto sintético)
    facade.run_single("GOLDEN", reset=True)

    # Carregar canonical model
    repo = build_local_project_repository(facade.projects_root)
    try:
        store = repo.get_project("GOLDEN")
    except FileNotFoundError:
        raise FileNotFoundError(
            f"GOLDEN project not found under {facade.projects_root} after benchmark run"
        ) from None
    canonical = store.load_canonical()
    return BenchmarkWrapper(canonical)


class BenchmarkWrapper:
    """Wrapper para acessar dados do benchmark nos testes."""

    def __init__(self, canonical_model):
        self.canonical = canonical_model
