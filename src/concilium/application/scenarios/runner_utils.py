"""Helper functions for scenario runner."""

from __future__ import annotations

import copy
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from concilium.domain.models.canonical import CanonicalModel


def _extract_total_pessoas(equipes_diretas) -> int:
    total = 0
    for eq in equipes_diretas:
        for f in eq.funcoes:
            total += f.num_pessoas
    return total


def _extract_atividades_criticas(criticality_report) -> int:
    criticas = []
    for a, s in criticality_report.get("scores", {}).items():
        if s >= 0.7:
            criticas.append(a)
    return len(criticas)


def extract_metricas(canonical: CanonicalModel | None) -> dict[str, Any]:
    """Extrai métricas-resumo do canônico para a matriz de comparação."""

    if canonical is None:
        return {}
    m: dict[str, Any] = {}

    if canonical.resultado:
        r = canonical.resultado
        m["custo_total"] = round(r.custo.total, 2)
        m["venda_com_bdi"] = round(r.venda.total_com_bdi, 2)
        m["margem_pct"] = round(r.margem_pct * 100, 2)
        m["status_margem"] = r.status_margem

    if canonical.cronograma:
        m["duracao_meses"] = len(canonical.cronograma.distribuicao_mensal)

    if canonical.equipes_diretas:
        m["total_pessoas"] = _extract_total_pessoas(canonical.equipes_diretas)

    if canonical.alocacoes:
        m["total_alocacoes"] = len(canonical.alocacoes)

    if canonical.conflitos_pico:
        m["conflitos_pico"] = len(canonical.conflitos_pico)
    else:
        m["conflitos_pico"] = 0

    if canonical.criticality_report:
        m["atividades_criticas"] = _extract_atividades_criticas(canonical.criticality_report)

    return m


def apply_custo_delta(inputs: dict[str, Any], delta: float) -> dict[str, Any]:
    """Aplica delta de custo nos inputs de referência."""
    result = copy.deepcopy(inputs)
    if "composicao_customizada" in result:
        for _item_id, comp in result["composicao_customizada"].items():
            for funcao in comp.get("funcoes", []):
                if "salario_base" in funcao:
                    funcao["salario_base"] = round(funcao["salario_base"] * delta, 2)
            for equip in comp.get("equipamentos", []):
                if "custo_mensal" in equip:
                    equip["custo_mensal"] = round(equip["custo_mensal"] * delta, 2)
    if "custo_km" in result:
        result["custo_km"] = round(result["custo_km"] * delta, 4)
    return result


def apply_duracao_delta(inputs: dict[str, Any], delta: float) -> dict[str, Any]:
    """Aplica delta de duração nos inputs."""
    result = copy.deepcopy(inputs)
    result["duracao_delta_pct"] = round((delta - 1.0) * 100, 1)
    return result


def apply_equipe_delta(inputs: dict[str, Any], delta: float) -> dict[str, Any]:
    """Aplica delta de tamanho de equipe nos inputs."""
    result = copy.deepcopy(inputs)
    result["equipe_delta_pct"] = round((delta - 1.0) * 100, 1)
    return result
