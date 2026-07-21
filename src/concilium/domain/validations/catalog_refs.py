"""Fonte única das referências embutidas (sem FK) de `composicao_padrao_equipe`.

`Producao.composicao_padrao_equipe` (ver diagrama de catálogo — CPU -> Producao ->
{MO, EQ, MAT}) guarda `funcao_id` / `equip_id` / `insumo_id` como strings soltas,
sem constraint de banco. A integridade referencial desses campos é toda de
responsabilidade da aplicação — e hoje é derivada por dois consumidores
independentes: `ValidadorCPUInsumo` (gate obrigatório ADR-035, bloqueia
avancar_plano) e `plausibility_checker` (diagnóstico sob demanda via CLI/MCP).

Antes deste módulo, cada consumidor declarava suas próprias listas/campos na mão.
Os dois pararam exatamente no mesmo lugar — nenhum verificava
`materiais[].insumo_id` (ADR-030 D2, materiais consumidos pela equipe) — porque
não havia uma fonte única para lembrar de atualizar nos dois lugares ao mesmo
tempo. `REFERENCIAS_EQUIPE` existe para que adicionar/remover uma referência
seja uma edição num lugar só, consumida por ambos.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class ReferenciaEquipe:
    """Um campo de `composicao_padrao_equipe` que referencia o catálogo de
    insumos por id solto, sem FK.
    """

    lista: str  # chave da lista dentro de composicao_padrao_equipe
    campo_id: str  # campo do item que carrega o id referenciado
    rotulo: str  # nome plural para mensagens de erro


REF_FUNCOES = ReferenciaEquipe(lista="funcoes", campo_id="funcao_id", rotulo="Funções")
REF_EQUIPAMENTOS = ReferenciaEquipe(lista="equipamentos", campo_id="equip_id", rotulo="Equipamentos")
REF_MATERIAIS = ReferenciaEquipe(lista="materiais", campo_id="insumo_id", rotulo="Materiais")

# Ordem usada por plausibility_checker para iterar todas as referências de uma vez.
REFERENCIAS_EQUIPE: tuple[ReferenciaEquipe, ...] = (REF_FUNCOES, REF_EQUIPAMENTOS, REF_MATERIAIS)


def ids_referenciados(equipe: dict[str, Any], ref: ReferenciaEquipe) -> list[str]:
    """Ids não vazios que `ref` carrega dentro de uma composicao_padrao_equipe."""
    return [valor for item in (equipe.get(ref.lista) or []) if (valor := item.get(ref.campo_id))]


def ids_faltantes(equipe: dict[str, Any], ref: ReferenciaEquipe, existe: Callable[[str], bool]) -> list[str]:
    """Ids de `ref` que não passam no predicado `existe` (ex.: repo.funcao_existe)."""
    return [valor for valor in ids_referenciados(equipe, ref) if not existe(valor)]
