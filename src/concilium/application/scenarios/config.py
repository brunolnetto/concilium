"""Scenario Engine configuration and execution.

Conceitos:
    ScenarioConfig   — parâmetros de uma variação (deltas percentuais por dime

Uso programático:
    runner = ScenarioRunner(runtime, project)
    results = runner.run_variations(base_inputs, n=5)
    matrix = runner.compare(results)

CLI:
    concilium scenario run --project p --variations 5
    concilium scenario compare --project p
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from typing import Any


@dataclass
class ScenarioConfig:
    """Parâmetros de um cenário de variação.

    Modo legado (v2.4) — deltas percentuais:
        custo_delta:    altera custo_unitario dos insumos-chave
        duracao_delta:  altera quantitativos (afeta duração proporcional)
        equipe_delta:   altera num_equipes_base / num_pessoas

    Modo DV (v2.5, DEC-29) — variações restritas ao espaço de decisão:
        decision_variables: DecisionVariables com DV1-DV4.
        Quando presente, os campos custo/duracao/equipe_delta são ignorados
        e a execução usa PlanningLoop ao invés de deltas livres.

    Nota: Nunca varie BDI (F1), indiretos regulatórios (F2), produtividade
    (F3) ou pool de recursos (F4) — esses são elementos fixos do sistema.
    """

    id: str = field(default_factory=lambda: str(uuid.uuid4())[:8])
    nome: str = ""
    custo_delta: float = 1.0  # ex. 0.9 = custo -10%
    duracao_delta: float = 1.0  # ex. 1.05 = duração +5%
    equipe_delta: float = 1.0  # ex. 0.9 = equipe -10% (arredondado)
    inputs_override: dict[str, Any] = field(default_factory=dict)
    descricao: str = ""
    # v2.5: espaço de decisão formal (DEC-29)
    decision_variables: Any | None = None  # DecisionVariables | None
