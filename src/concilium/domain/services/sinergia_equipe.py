"""ADR-130 — Composição de Equipe como Grafo de Sinergia: motor de derivação.

Funções puras (sem I/O) que implementam:
  D2 — derivação da produtividade horária a partir do gargalo (min de capacidades efetivas)
  D3 — precedência de resolução (calibrado > derivado > declarado) como função consultiva,
       nunca como sobrescrita silenciosa de `Producao.valor_horario` (ADR-130 A3 rejeitado)
  D4 — validações VAL-SINERGIA-01..05
  D5 — atualização da capacidade do elemento gargalo (alvo estruturado de calibração)

Este módulo não depende de nenhuma skill; é consumido por skill-03/05 (e futuramente
pelo fluxo de calibração ADR-076) como serviço de domínio puro.
"""

from __future__ import annotations

import math
from collections import defaultdict
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

from concilium.domain.models.canonical._base import ValidacaoItem

if TYPE_CHECKING:
    from concilium.domain.models.catalog.catalogo import ComposicaoPadraoEquipe
    from concilium.domain.models.catalog.producao import (
        CapacidadeElemento,
        FonteCapacidade,
        GrafoSinergiaEquipe,
        Producao,
        RelacaoSinergia,
    )

# ADR-130 D4: limiar de divergência entre producao_horaria_derivada e valor_horario declarado.
LIMIAR_DIVERGENCIA_SINERGIA = 0.15


@dataclass(frozen=True)
class DerivacaoSinergia:
    """Resultado da derivação D2 — gargalo e produtividade horária computada."""

    producao_horaria_derivada: float | None
    gargalo_derivado: str | None
    capacidades_efetivas: dict[str, float] = field(default_factory=dict)


@dataclass(frozen=True)
class ResolucaoProducao:
    """Resultado da precedência D3 — valor consultivo, nunca grava em `Producao.valor_horario`."""

    valor: float
    fonte: str  # "calibrado" | "derivado" | "declarado"
    derivacao: DerivacaoSinergia | None
    validacoes: list[ValidacaoItem]


def elementos_validos(composicao: ComposicaoPadraoEquipe) -> set[str]:
    """IDs de todos os elementos existentes na composição (funções, equipamentos, materiais)."""
    ids: set[str] = set()
    ids.update(f.funcao_id for f in composicao.funcoes)
    ids.update(e.equip_id for e in composicao.equipamentos)
    ids.update(m.insumo_id for m in composicao.materiais)
    return ids


def _num_unidades_elemento(elemento_id: str, composicao: ComposicaoPadraoEquipe) -> float:
    for f in composicao.funcoes:
        if f.funcao_id == elemento_id:
            return float(f.num_pessoas)
    for e in composicao.equipamentos:
        if e.equip_id == elemento_id:
            return float(e.num_unidades)
    for m in composicao.materiais:
        if m.insumo_id == elemento_id:
            return 1.0
    return 1.0


def validar_referencias_grafo(grafo: GrafoSinergiaEquipe, composicao: ComposicaoPadraoEquipe) -> list[ValidacaoItem]:
    """VAL-SINERGIA-01 (ERRO): referência a elemento inexistente na composição."""
    validos = elementos_validos(composicao)
    out: list[ValidacaoItem] = []
    for r in grafo.relacoes:
        for elemento_id, papel in ((r.origem, "origem"), (r.destino, "destino")):
            if elemento_id not in validos:
                out.append(
                    ValidacaoItem(
                        codigo="VAL-SINERGIA-01",
                        status="ERRO",
                        mensagem=(
                            f"RelacaoSinergia.{papel}={elemento_id!r} (tipo={r.tipo!r}) não referencia "
                            "elemento existente na composição."
                        ),
                    )
                )
    for c in grafo.capacidades:
        if c.elemento_id not in validos:
            out.append(
                ValidacaoItem(
                    codigo="VAL-SINERGIA-01",
                    status="ERRO",
                    mensagem=(
                        f"CapacidadeElemento.elemento_id={c.elemento_id!r} não referencia elemento "
                        "existente na composição."
                    ),
                )
            )
    if grafo.gargalo_declarado is not None and grafo.gargalo_declarado not in validos:
        out.append(
            ValidacaoItem(
                codigo="VAL-SINERGIA-01",
                status="ERRO",
                mensagem=(
                    f"gargalo_declarado={grafo.gargalo_declarado!r} não referencia elemento existente na composição."
                ),
            )
        )
    return out


class _UnionFind:
    def __init__(self, items: list[str]) -> None:
        self._parent = {i: i for i in items}

    def find(self, x: str) -> str:
        while self._parent[x] != x:
            self._parent[x] = self._parent[self._parent[x]]
            x = self._parent[x]
        return x

    def union(self, a: str, b: str) -> None:
        ra, rb = self.find(a), self.find(b)
        if ra != rb:
            self._parent[ra] = rb


def _capacidades_efetivas_iniciais(
    capacidades: dict[str, CapacidadeElemento], composicao: ComposicaoPadraoEquipe
) -> dict[str, float]:
    return {eid: c.capacidade_horaria * _num_unidades_elemento(eid, composicao) for eid, c in capacidades.items()}


def _aplicar_acoplamento(efetivas: dict[str, float], relacoes: list[RelacaoSinergia]) -> None:
    """Propaga o acoplamento (par opera na capacidade do menor) via union-find, in-place."""
    uf = _UnionFind(list(efetivas.keys()))
    for r in relacoes:
        if r.tipo == "acoplamento" and r.origem in efetivas and r.destino in efetivas:
            uf.union(r.origem, r.destino)

    grupos: dict[str, list[str]] = defaultdict(list)
    for eid in efetivas:
        grupos[uf.find(eid)].append(eid)
    for membros in grupos.values():
        if len(membros) > 1:
            minimo = min(efetivas[m] for m in membros)
            for m in membros:
                efetivas[m] = minimo


def _aplicar_dimensionamento(efetivas: dict[str, float], relacoes: list[RelacaoSinergia]) -> None:
    """Satura capacidade_efetiva(destino) pela de origem, in-place."""
    for r in relacoes:
        if r.tipo == "dimensionamento" and r.origem in efetivas and r.destino in efetivas:
            efetivas[r.destino] = min(efetivas[r.destino], efetivas[r.origem])


def _dominio_sem_precondicao(efetivas: dict[str, float], relacoes: list[RelacaoSinergia]) -> dict[str, float]:
    """Exclui do domínio do mínimo os elementos que são origem de uma relação `precondicao`."""
    excluidos_precondicao = {r.origem for r in relacoes if r.tipo == "precondicao"}
    return {eid: v for eid, v in efetivas.items() if eid not in excluidos_precondicao}


def derivar_producao_horaria(grafo: GrafoSinergiaEquipe, composicao: ComposicaoPadraoEquipe) -> DerivacaoSinergia:
    """ADR-130 D2 — produtividade derivada do gargalo (min de capacidades efetivas).

    capacidade_efetiva(e) = capacidade_horaria(e) × num_unidades(e, composicao)
      - acoplamento: par (origem, destino) opera na capacidade do menor dos dois
        (propagado transitivamente via union-find quando há cadeias de acoplamento)
      - dimensionamento: capacidade_efetiva(destino) é saturada pela capacidade_efetiva(origem)
        (não adianta caminhão além do ciclo da escavadeira)
      - precondicao: não altera a taxa — o elemento origem de uma relação `precondicao`
        é excluído do domínio do mínimo (expõe risco via ADR-128, não a taxa)

    Retorna producao_horaria_derivada=None quando não há nenhuma capacidade declarada
    (ou todas foram excluídas por precondicao) — nesse caso não há gargalo computável.
    """
    capacidades = {c.elemento_id: c for c in grafo.capacidades}
    if not capacidades:
        return DerivacaoSinergia(producao_horaria_derivada=None, gargalo_derivado=None, capacidades_efetivas={})

    efetivas = _capacidades_efetivas_iniciais(capacidades, composicao)
    _aplicar_acoplamento(efetivas, grafo.relacoes)
    _aplicar_dimensionamento(efetivas, grafo.relacoes)

    dominio = _dominio_sem_precondicao(efetivas, grafo.relacoes)
    if not dominio:
        return DerivacaoSinergia(producao_horaria_derivada=None, gargalo_derivado=None, capacidades_efetivas=efetivas)

    gargalo_id = min(dominio, key=lambda k: dominio[k])
    return DerivacaoSinergia(
        producao_horaria_derivada=round(dominio[gargalo_id], 6),
        gargalo_derivado=gargalo_id,
        capacidades_efetivas=efetivas,
    )


def _val_sinergia_divergencia(derivacao: DerivacaoSinergia, valor_horario: float) -> list[ValidacaoItem]:
    """VAL-SINERGIA-02 (AVISO): derivado diverge do declarado além do limiar."""
    if derivacao.producao_horaria_derivada is None or valor_horario <= 0:
        return []
    divergencia = abs(derivacao.producao_horaria_derivada - valor_horario) / valor_horario
    if divergencia <= LIMIAR_DIVERGENCIA_SINERGIA:
        return []
    return [
        ValidacaoItem(
            codigo="VAL-SINERGIA-02",
            status="AVISO",
            mensagem=(
                f"producao_horaria_derivada={derivacao.producao_horaria_derivada:g} diverge "
                f"{divergencia:.1%} do valor_horario declarado={valor_horario:g} "
                f"(limiar {LIMIAR_DIVERGENCIA_SINERGIA:.0%}). Valor declarado preservado."
            ),
        )
    ]


def _val_sinergia_gargalo_divergente(
    grafo: GrafoSinergiaEquipe, derivacao: DerivacaoSinergia
) -> list[ValidacaoItem]:
    """VAL-SINERGIA-03 (AVISO): gargalo_declarado não coincide com o gargalo derivado."""
    if grafo.gargalo_declarado is None or grafo.gargalo_declarado == derivacao.gargalo_derivado:
        return []
    return [
        ValidacaoItem(
            codigo="VAL-SINERGIA-03",
            status="AVISO",
            mensagem=(
                f"gargalo_declarado={grafo.gargalo_declarado!r} não coincide com o gargalo "
                f"derivado das capacidades={derivacao.gargalo_derivado!r}."
            ),
        )
    ]


def _avaliar_grafo_sinergia(
    grafo: GrafoSinergiaEquipe, producao: Producao
) -> tuple[DerivacaoSinergia, bool, list[ValidacaoItem]]:
    """Valida referências, deriva a produção e monta VAL-SINERGIA-02/03 para um grafo presente."""
    validacoes = list(validar_referencias_grafo(grafo, producao.composicao_padrao_equipe))
    grafo_invalido = any(v.status == "ERRO" for v in validacoes)
    derivacao = derivar_producao_horaria(grafo, producao.composicao_padrao_equipe)
    validacoes.extend(_val_sinergia_divergencia(derivacao, producao.valor_horario))
    validacoes.extend(_val_sinergia_gargalo_divergente(grafo, derivacao))
    return derivacao, grafo_invalido, validacoes


def _decidir_fonte_producao(
    producao: Producao, grafo_invalido: bool, derivacao: DerivacaoSinergia | None
) -> tuple[float, str]:
    """Precedência D3: calibrado > derivado > declarado."""
    if producao.origem.tipo == "calibrado_contra_obra_real":
        return producao.valor_horario, "calibrado"
    if not grafo_invalido and derivacao is not None and derivacao.producao_horaria_derivada is not None:
        return derivacao.producao_horaria_derivada, "derivado"
    return producao.valor_horario, "declarado"


def resolver_producao_efetiva(producao: Producao) -> ResolucaoProducao:
    """ADR-130 D3 — precedência calibrado > derivado > declarado.

    Função consultiva: NUNCA muta `producao.valor_horario`. Quando derivado e declarado
    coexistem e divergem, o valor declarado/calibrado é o que este objeto `Producao`
    carrega e continua sendo usado por qualquer código legado que leia `valor_horario`
    diretamente — o valor "derivado" retornado aqui é instrumento de explicação/decisão
    do engenheiro (ADR-130 D3, A3 rejeitado: sobrescrita silenciosa não é aceitável).

    Se `validar_referencias_grafo` encontrar VAL-SINERGIA-01 (ERRO — referência órfã),
    o grafo é tratado como inválido e `fonte="derivado"` nunca é retornado, mesmo que
    `derivar_producao_horaria` produza um valor (Copilot, PR #78): um grafo com
    referência quebrada não pode influenciar o resultado — cai para calibrado/declarado.
    """
    validacoes: list[ValidacaoItem] = []
    derivacao: DerivacaoSinergia | None = None
    grafo = producao.grafo_sinergia
    grafo_invalido = False

    if grafo is not None:
        derivacao, grafo_invalido, extra_validacoes = _avaliar_grafo_sinergia(grafo, producao)
        validacoes.extend(extra_validacoes)

    valor, fonte = _decidir_fonte_producao(producao, grafo_invalido, derivacao)
    return ResolucaoProducao(valor=valor, fonte=fonte, derivacao=derivacao, validacoes=validacoes)


def revalidar_apos_mudanca_composicao(
    producao: Producao, nova_composicao: ComposicaoPadraoEquipe
) -> list[ValidacaoItem]:
    """ADR-130 F3 — re-derivação em mudança de composição (VAL-SINERGIA-04/05).

    Retorna [] quando a `Producao` não tem grafo de sinergia (retrocompatibilidade total).
    """
    grafo = producao.grafo_sinergia
    if grafo is None:
        return []

    validacoes: list[ValidacaoItem] = []
    validacoes.extend(validar_referencias_grafo(grafo, nova_composicao))

    derivacao_nova = derivar_producao_horaria(grafo, nova_composicao)
    if derivacao_nova.producao_horaria_derivada is not None:
        validacoes.append(
            ValidacaoItem(
                codigo="VAL-SINERGIA-04",
                status="INFO",
                mensagem=(
                    "Composição alterada com grafo de sinergia presente — produtividade re-derivada "
                    f"automaticamente: {derivacao_nova.producao_horaria_derivada:g} "
                    f"(gargalo={derivacao_nova.gargalo_derivado!r})."
                ),
            )
        )

    capacidades_ids = {c.elemento_id for c in grafo.capacidades}
    for r in grafo.relacoes:
        if r.tipo != "dimensionamento" or r.razao is None:
            continue
        if r.origem not in capacidades_ids or r.destino not in capacidades_ids:
            continue
        n_origem = _num_unidades_elemento(r.origem, nova_composicao)
        n_destino = _num_unidades_elemento(r.destino, nova_composicao)
        esperado = n_origem * r.razao
        if n_destino < esperado:
            validacoes.append(
                ValidacaoItem(
                    codigo="VAL-SINERGIA-05",
                    status="AVISO",
                    mensagem=(
                        f"Relação dimensionamento {r.origem}->{r.destino}: razão declarada {r.razao:g} "
                        f"un/un exige {esperado:g} unidades de {r.destino}, composição atual tem "
                        f"{n_destino:g}."
                    ),
                )
            )

    return validacoes


def atualizar_capacidade_gargalo(
    producao: Producao,
    nova_capacidade_horaria: float,
    fonte: FonteCapacidade = "medicao_obra",
    justificativa: str | None = None,
) -> Producao:
    """ADR-130 D5/F5 — calibração de campo atualiza a capacidade do elemento gargalo.

    Substitui `CapacidadeElemento.capacidade_horaria` (e `fonte`) do elemento que hoje
    realiza o mínimo (gargalo derivado), preservando a estrutura (`relacoes`) intacta —
    confina o risco de staleness aos poucos parâmetros de `capacidades` (ADR-130 D5).

    Retorna uma nova instância de `Producao` (imutável); NÃO altera `valor_horario` —
    a produtividade re-deriva na próxima chamada a `resolver_producao_efetiva`/
    `derivar_producao_horaria`, mantendo a precedência D3 (o engenheiro decide quando
    promover o valor derivado a `valor_horario`).
    """
    # Copilot (PR #78): model_copy(update=...) não revalida em Pydantic v2 — o
    # Field(gt=0) de CapacidadeElemento.capacidade_horaria seria contornável.
    # Valida explicitamente antes de construir a cópia.
    if not math.isfinite(nova_capacidade_horaria) or nova_capacidade_horaria <= 0:
        raise ValueError(
            f"nova_capacidade_horaria deve ser finita e > 0, recebido {nova_capacidade_horaria!r} (ADR-130 D1)."
        )

    grafo = producao.grafo_sinergia
    if grafo is None or not grafo.capacidades:
        raise ValueError(
            "Producao sem GrafoSinergiaEquipe/capacidades — não há elemento gargalo para calibrar (ADR-130 F5)."
        )

    derivacao = derivar_producao_horaria(grafo, producao.composicao_padrao_equipe)
    if derivacao.gargalo_derivado is None:
        raise ValueError("Não foi possível determinar o elemento gargalo para calibração (ADR-130 F5).")

    gargalo_id = derivacao.gargalo_derivado
    novas_capacidades = [
        c.model_copy(
            update={"capacidade_horaria": nova_capacidade_horaria, "fonte": fonte, "justificativa": justificativa}
        )
        if c.elemento_id == gargalo_id
        else c
        for c in grafo.capacidades
    ]
    novo_grafo = grafo.model_copy(update={"capacidades": novas_capacidades})
    return producao.model_copy(update={"grafo_sinergia": novo_grafo})
