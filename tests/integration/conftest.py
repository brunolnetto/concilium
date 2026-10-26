"""Fixtures compartilhadas para TODOS os testes de integração.

Consolidação de fixtures benchmarks em um único local para garantir:
1. Session-scoped fixtures são realmente compartilhadas entre subdirs (benchmark/, cost/, cli/)
2. Sem duplicação: GOLDEN é executado UMA VEZ (não duas vezes em conftest diferentes)
3. Performance: ~15s GOLDEN (compartilhado) + ~60-100s AGIS (sob demanda)

Histórico de problema:
- Antes: golden_benchmark (cost/conftest.py) + golden_artifacts (benchmark/conftest.py)
  executavam GOLDEN separadamente → duplicação de setup
- Depois: Consolidado aqui → única execução compartilhada por todos os testes
"""

from pathlib import Path

import pytest

# ── Benchmark Fixtures (Shared across integration tests) ─────────────────────


@pytest.fixture(scope="session")
def golden_artifacts(config_root, tmp_path_factory) -> dict[str, Path]:
    """Fixture session-scoped que executa GOLDEN com ambos os intents (RFI + RFP).

    RFI e RFP usam modos diferentes de pipeline:
    - RFI: OLTP mode (skills 01-06) → benchmark_report.json apenas
    - RFP: OLAP mode (skills 01-11) → benchmark_report.json + relatorio.pdf + resultado_planejamento.xlsx

    Ambas execuções com reset=True para garantir cada modo executa completamente.
    
    Entregáveis:
    - RFI: audit/benchmark_report.json
    - RFP: audit/benchmark_report.json + outputs/reports/relatorio.pdf + outputs/resultado_planejamento.xlsx

    Tempo: ~55-65s (RFI ~15-20s + RFP ~35-45s sequencial)
    Compartilhado: session-scoped, inicializado UMA VEZ para toda a sessão de testes
    """
    from concilium.application.benchmarks.execution.facade import BenchmarkFacade

    root = config_root.parent
    # RFI/RFP have independent output roots: the former must not be silently
    # overwritten by the latter's reset=True run. Neither may overwrite the
    # GOLDEN benchmark used by other integration fixtures.
    artifacts: dict[str, Path] = {}
    for intent in ("rfi", "rfp"):
        facade = BenchmarkFacade.from_root(root)
        facade.projects_root = tmp_path_factory.mktemp(f"golden_{intent}_projects")
        facade.run_single("GOLDEN", reset=True, procurement_intent=intent)
        artifacts[intent] = facade.projects_root / "GOLDEN" / "artifacts"
    return artifacts


@pytest.fixture(scope="session")
def golden_benchmark(config_root, tmp_path_factory):
    """Fixture que retorna o canonical model do benchmark GOLDEN (sintético, rápido).

    Executa o pipeline do GOLDEN (projeto sintético mínimo com 3 itens EAP)
    via BenchmarkFacade. Ideal para testes que precisam validar invariantes
    estruturais sem necessidade de dados reais complexos.

    Tempo: ~15s (vs ~60-100s para AGIS)
    Compartilhado: session-scoped, reutilizado por múltiplos testes
    """
    from concilium.application.benchmarks.execution.facade import BenchmarkFacade
    from concilium.infrastructure.storage.store_factory import build_local_project_repository

    root = config_root.parent
    facade = BenchmarkFacade.from_root(root)
    # Isolate canonical and report from RFI/RFP artifact fixtures, and from
    # other pytest sessions/xdist workers executing reset=True.
    facade.projects_root = tmp_path_factory.mktemp("golden_benchmark_projects")

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
    """Wrapper para acessar dados do benchmark AGIS nos testes."""

    def __init__(self, canonical_model):
        self.canonical = canonical_model
