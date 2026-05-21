"""Scenario Engine — Fase 2A.

Gera e executa múltiplas variações de um projeto para análise comparativa.

Conceitos:
    ScenarioConfig   — parâmetros de uma variação (deltas percentuais por dimensão)
    ScenarioResult   — resultado canônico + métricas resumidas
    ScenarioRunner   — orquestra execução sequencial de N cenários via Runtime

Uso programático:
    runner = ScenarioRunner(runtime, project)
    results = runner.run_variations(base_inputs, n=5)
    matrix = runner.compare(results)

CLI:
    concilium scenario run --project p --variations 5
    concilium scenario compare --project p
"""

from .config import ScenarioConfig
from .runner import ScenarioResult, ScenarioRunner

__all__ = [
    "ScenarioConfig",
    "ScenarioResult",
    "ScenarioRunner",
]
