"""Fixtures para testes de integração ADR-104."""

import pytest


@pytest.fixture(scope="session")
def agis_benchmark(config_root):
    """Fixture que retorna o canonical model do benchmark AGIS após execução completa.

    Executa o pipeline completo do AGIS via BenchmarkFacade e retorna um wrapper
    com o canonical model com todos os dados processados.
    """
    from concilium.application.benchmarks.execution.facade import BenchmarkFacade

    # Criar facade a partir do config_root
    # BenchmarkFacade descobre benchmarks_root e projects_root automaticamente
    root = config_root.parent
    facade = BenchmarkFacade.from_root(root)

    # Executar benchmark AGIS
    # Se já foi executado, reset=False reutiliza resultado em cache
    facade.run_single("AGIS", reset=False)

    # Carregar canonical model do store
    # ProjectStore descobre o projeto pelo ID no meta.json do diretório AGIS
    agis_store_root = facade.projects_root / "AGIS"
    if not agis_store_root.exists():
        raise FileNotFoundError(f"AGIS project not found at {agis_store_root} after benchmark run")

    from concilium.infrastructure.storage.project import ProjectStore

    store = ProjectStore(root=agis_store_root)
    canonical = store.load_canonical()
    return BenchmarkWrapper(canonical)


class BenchmarkWrapper:
    """Wrapper para acessar dados do benchmark AGIS nos testes."""

    def __init__(self, canonical_model):
        self.canonical = canonical_model
