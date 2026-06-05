"""ADR-016 — Validação de pool de recursos com taxonomia de três classes.

Substitui a soma uniforme de demanda do ADR-005 por uma validação
que distingue o comportamento de compartilhamento de cada insumo:

  Classe A (exclusivo_dedicado):     demanda = soma direta de instâncias
  Classe B (exclusivo_compartilhavel): demanda = soma ponderada por fracao_uso
  Classe C (concorrente_compartilhavel): demanda = contagem de atividades simultâneas
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field
from typing import Any


@dataclass
class ViolacaoPool:
    """Violação de restrição de pool detectada pelo ResourcePoolValidator."""

    codigo: str
    insumo_id: str
    semana: str
    demanda: float
    capacidade: float
    excedente: float
    classe: str
    recomendacao: str


@dataclass
class ResultadoValidacaoSemana:
    violacoes: list[ViolacaoPool] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return not self.violacoes


def _rpv_get_insumo_classe(insumo) -> tuple:
    """Return (classe, cls_data) for an insumo dict."""
    cls_data = insumo.get("classe_compartilhamento") if isinstance(insumo, dict) else None
    classe = (
        (cls_data or {}).get("classe", "exclusivo_dedicado") if isinstance(cls_data, dict) else "exclusivo_dedicado"
    )
    return classe, cls_data


def _rpv_accumulate_demands(atividades_ativas, alocacoes, insumos) -> tuple:
    """Build demand_a/b/c dicts from weekly allocations and insumo classes."""
    demand_a: dict = defaultdict(float)
    demand_b: dict = defaultdict(float)
    demand_c: dict = defaultdict(int)
    for atividade_id in atividades_ativas:
        alloc = alocacoes.get(atividade_id, {})
        for insumo_id, quantidade in alloc.items():
            if quantidade <= 0:
                continue
            insumo = insumos.get(insumo_id)
            if insumo is None:
                continue
            classe, cls_data = _rpv_get_insumo_classe(insumo)
            if classe == "exclusivo_dedicado":
                demand_a[insumo_id] += quantidade
            elif classe == "exclusivo_compartilhavel":
                fracao = (cls_data or {}).get("fracao_uso", 1.0)
                demand_b[insumo_id] += quantidade * fracao
            elif classe == "concorrente_compartilhavel":
                demand_c[insumo_id] += 1
    return demand_a, demand_b, demand_c


def _check_demand_a(semana: str, demand_a: dict, pool: dict, violacoes: list) -> None:
    for insumo_id, demanda in demand_a.items():
        capacidade = float(pool.get(insumo_id, 0))
        if demanda > capacidade:
            violacoes.append(
                ViolacaoPool(
                    codigo="VAL-POOL-A-01",
                    insumo_id=insumo_id,
                    semana=semana,
                    demanda=demanda,
                    capacidade=capacidade,
                    excedente=demanda - capacidade,
                    classe="exclusivo_dedicado",
                    recomendacao=f"Adquirir {demanda - capacidade:.0f} unidade(s) adicional(is) ou deslocar atividade",
                )
            )


def _check_demand_b(semana: str, demand_b: dict, pool: dict, violacoes: list) -> None:
    for insumo_id, demanda in demand_b.items():
        capacidade = float(pool.get(insumo_id, 0))
        if demanda > capacidade:
            violacoes.append(
                ViolacaoPool(
                    codigo="VAL-POOL-B-01",
                    insumo_id=insumo_id,
                    semana=semana,
                    demanda=demanda,
                    capacidade=capacidade,
                    excedente=demanda - capacidade,
                    classe="exclusivo_compartilhavel",
                    recomendacao="Redistribuir atividades para evitar sobreposição ou adicionar instância",
                )
            )


def _check_demand_c(semana: str, demand_c: dict, insumos: dict, pool: dict, violacoes: list) -> None:
    for insumo_id, n_atividades in demand_c.items():
        insumo = insumos.get(insumo_id)
        cls_data = insumo.get("classe_compartilhamento") if isinstance(insumo, dict) else {}
        cap_cobertura = (cls_data or {}).get("capacidade_cobertura", 1) if isinstance(cls_data, dict) else 1
        instancias = pool.get(insumo_id, 0)
        capacidade_efetiva = instancias * cap_cobertura
        if n_atividades > capacidade_efetiva:
            violacoes.append(
                ViolacaoPool(
                    codigo="VAL-POOL-C-01",
                    insumo_id=insumo_id,
                    semana=semana,
                    demanda=float(n_atividades),
                    capacidade=float(capacidade_efetiva),
                    excedente=float(n_atividades - capacidade_efetiva),
                    classe="concorrente_compartilhavel",
                    recomendacao=f"Adicionar 1 instância cobre até {cap_cobertura} frente(s) adicional(is)",
                )
            )


class ResourcePoolValidator:
    """Valida alocações de equipe contra pool usando restrições por classe (ADR-016 §D3)."""

    def validate_week(
        self,
        semana: str,
        atividades_ativas: list[str],
        alocacoes: dict[str, dict[str, float]],
        insumos: dict[str, Any],
        pool: dict[str, int],
    ) -> ResultadoValidacaoSemana:
        """Valida uma semana contra o pool com consciência de classe.

        Args:
            semana: Chave ISO week "AAAA-Www"
            atividades_ativas: IDs de atividades ativas nesta semana
            alocacoes: {atividade_id: {insumo_id: quantidade}}
            insumos: {insumo_id: dict com campo classe_compartilhamento}
            pool: {insumo_id: quantidade_total}
        """
        demand_a, demand_b, demand_c = _rpv_accumulate_demands(atividades_ativas, alocacoes, insumos)

        violacoes: list[ViolacaoPool] = []

        _check_demand_a(semana, demand_a, pool, violacoes)
        _check_demand_b(semana, demand_b, pool, violacoes)
        _check_demand_c(semana, demand_c, insumos, pool, violacoes)
        return ResultadoValidacaoSemana(violacoes=violacoes)


def atribuir_custo_insumo(
    insumo: dict[str, Any],
    n_atividades_simultaneas: int,
    semanas_ativo: int,
) -> float:
    """Calcula custo atribuído a uma atividade para um insumo compartilhado (ADR-016 §D4).

    Classe A: custo integral.
    Classe B: custo × fracao_uso.
    Classe C: custo / min(n_atividades_simultaneas, capacidade_cobertura).
    """
    custo_unitario = float(insumo.get("preco_unitario", 0))
    custo_base = custo_unitario * semanas_ativo

    cls_data = insumo.get("classe_compartilhamento") if isinstance(insumo, dict) else None
    if cls_data is None:
        return custo_base

    classe = cls_data.get("classe", "exclusivo_dedicado") if isinstance(cls_data, dict) else "exclusivo_dedicado"

    if classe == "exclusivo_dedicado":
        return custo_base

    if classe == "exclusivo_compartilhavel":
        fracao = float((cls_data or {}).get("fracao_uso", 1.0))
        return custo_base * fracao

    if classe == "concorrente_compartilhavel":
        cap = int((cls_data or {}).get("capacidade_cobertura", 1))
        divisor = min(n_atividades_simultaneas, cap)
        if divisor <= 0:
            return custo_base
        return custo_base / divisor

    return custo_base
