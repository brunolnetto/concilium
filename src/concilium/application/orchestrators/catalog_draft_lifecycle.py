"""ADR-120 D5: state machine do ciclo de vida de um rascunho de catálogo.

As 5 etapas do processo de atualização de catálogo (comparar → abrir
rascunho → revisar divergências/impacto → aprovar ou rejeitar publicação,
ver `presentation/mcp/tools/catalogo.py`) eram, até esta correção, 5 MCP
tools independentes sem nenhuma ordem imposta pelo sistema: nada impedia
chamar `aprovar_merge_catalogo` logo após `criar_rascunho_catalogo`, pulando
a revisão, nem aprovar um rascunho já rejeitado. Este módulo centraliza as
transições válidas para que os tools deleguem aqui em vez de checar flags
soltas cada um por conta própria.

Estados (derivados das flags gravadas no JSON do rascunho, sem campo próprio
de "estado" — mantém retrocompatibilidade com rascunhos já em disco):
    RASCUNHO  -- criado, ainda sem revisão registrada.
    REVISADO  -- listar_divergencias_rascunho ou consultar_impacto_reajuste
                 já foram chamados sobre este rascunho.
    APROVADO  -- promovido a versão ativa (terminal).
    REJEITADO -- descartado (terminal).

A transição efetiva (escrita das flags) é feita por `RascunhoCatalogoStateMachine`
(via `python-statemachine`, mesmo padrão de `application.jobs.state`): o grafo
de estados garante estruturalmente que um rascunho nunca fica simultaneamente
aprovado e rejeitado, e que `aprovar`/`rejeitar` só disparam a partir dos
estados de origem válidos. `assert_pode_aprovar`/`assert_pode_rejeitar`
continuam existindo como checagem antecipada, para produzir mensagens de erro
específicas para cada MCP tool antes de sequer tentar a transição.
"""

from __future__ import annotations

from typing import Any

from statemachine import State, StateMachine

ESTADO_RASCUNHO = "RASCUNHO"
ESTADO_REVISADO = "REVISADO"
ESTADO_APROVADO = "APROVADO"
ESTADO_REJEITADO = "REJEITADO"


class CatalogDraftGovernanceError(ValueError):
    """Violação de transição de estado do ciclo de vida do rascunho de catálogo."""


def estado_rascunho(rascunho_data: dict[str, Any]) -> str:
    """Deriva o estado atual do rascunho a partir das flags gravadas no JSON.

    Ordem de checagem importa: rejeitado/aprovado são terminais e prevalecem
    sobre `_revisado` (um rascunho pode ter sido revisado e depois rejeitado).
    """
    if rascunho_data.get("_rejeitado"):
        return ESTADO_REJEITADO
    if rascunho_data.get("_aprovado"):
        return ESTADO_APROVADO
    if rascunho_data.get("_revisado"):
        return ESTADO_REVISADO
    return ESTADO_RASCUNHO


def _checar_quatro_olhos(criado_por: str | None, aprovador: str) -> None:
    if criado_por and criado_por == aprovador:
        raise CatalogDraftGovernanceError(
            f"Violação da regra dos quatro olhos: '{aprovador}' criou este rascunho e não pode aprová-lo."
        )


class RascunhoCatalogoStateMachine(StateMachine):
    """Máquina de estados do ciclo de vida do rascunho de catálogo (ADR-120 D5)."""

    rascunho = State(initial=True, value=ESTADO_RASCUNHO)
    revisado = State(value=ESTADO_REVISADO)
    aprovado = State(value=ESTADO_APROVADO, final=True)
    rejeitado = State(value=ESTADO_REJEITADO, final=True)

    # Rever um rascunho já revisado é permitido (atualiza só quem revisou por
    # último) — por isso o self-loop em `revisado`.
    revisar = rascunho.to(revisado) | revisado.to(revisado)
    aprovar = revisado.to(aprovado)
    rejeitar = rascunho.to(rejeitado) | revisado.to(rejeitado)

    def __init__(self, rascunho_data: dict[str, Any]):
        self.rascunho_data = rascunho_data
        super().__init__()

    def before_aprovar(self, aprovador: str) -> None:
        _checar_quatro_olhos(self.rascunho_data.get("created_by"), aprovador)

    def on_revisar(self, revisor: str) -> None:
        self.rascunho_data["_revisado"] = True
        self.rascunho_data["_revisado_por"] = revisor

    def on_aprovar(self, aprovador: str) -> None:
        self.rascunho_data["_aprovado"] = True
        self.rascunho_data["_aprovado_por"] = aprovador

    def on_rejeitar(self, motivo: str, rejeitado_por: str | None = None) -> None:
        self.rascunho_data["_rejeitado"] = True
        self.rascunho_data["_motivo_rejeicao"] = motivo
        if rejeitado_por:
            self.rascunho_data["_rejeitado_por"] = rejeitado_por


def criar_state_machine(rascunho_data: dict[str, Any]) -> RascunhoCatalogoStateMachine:
    """Reconstrói a state machine posicionada no estado atual do rascunho.

    Repõe (sem alterar valores já gravados) as transições já ocorridas a
    partir das flags persistidas, no mesmo espírito de
    `application.jobs.state.criar_state_machine`. Usado pelos MCP tools para
    executar a transição seguinte (`sm.aprovar(...)`/`sm.rejeitar(...)`).
    """
    sm = RascunhoCatalogoStateMachine(rascunho_data)
    estado_atual = estado_rascunho(rascunho_data)
    if estado_atual == ESTADO_RASCUNHO:
        return sm
    if rascunho_data.get("_revisado"):
        sm.revisar(revisor=rascunho_data.get("_revisado_por") or "?")
    if estado_atual == ESTADO_APROVADO:
        sm.aprovar(aprovador=rascunho_data.get("_aprovado_por") or "?")
    elif estado_atual == ESTADO_REJEITADO:
        sm.rejeitar(
            motivo=rascunho_data.get("_motivo_rejeicao") or "?",
            rejeitado_por=rascunho_data.get("_rejeitado_por"),
        )
    return sm


def marcar_revisado(rascunho_data: dict[str, Any], revisor: str) -> dict[str, Any]:
    """RASCUNHO -> REVISADO: registra que divergências/impacto foram revisados.

    No-op (retorna os dados inalterados) se o rascunho já está em estado
    terminal (APROVADO/REJEITADO) — revisão tardia não deveria reabrir o
    ciclo de vida.
    """
    if estado_rascunho(rascunho_data) in (ESTADO_APROVADO, ESTADO_REJEITADO):
        return rascunho_data
    novo = dict(rascunho_data)
    criar_state_machine(novo).revisar(revisor=revisor)
    return novo


def assert_pode_aprovar(rascunho_data: dict[str, Any], aprovador: str) -> None:
    """Bloqueia aprovar_merge_catalogo fora da sequência revisar -> aprovar.

    Verifica, nesta ordem: não está rejeitado, não está já aprovado, já foi
    revisado (REVISADO, não RASCUNHO cru), e a regra dos quatro olhos
    (aprovador != criador).
    """
    estado = estado_rascunho(rascunho_data)
    if estado == ESTADO_REJEITADO:
        raise CatalogDraftGovernanceError(
            f"Rascunho foi rejeitado (motivo: {rascunho_data.get('_motivo_rejeicao') or '?'}) "
            "e não pode ser promovido."
        )
    if estado == ESTADO_APROVADO:
        raise CatalogDraftGovernanceError("Rascunho já foi aprovado anteriormente.")
    if estado == ESTADO_RASCUNHO:
        raise CatalogDraftGovernanceError(
            "Rascunho ainda não foi revisado — use listar_divergencias_rascunho ou "
            "consultar_impacto_reajuste antes de aprovar_merge_catalogo."
        )
    _checar_quatro_olhos(rascunho_data.get("created_by"), aprovador)


def assert_pode_rejeitar(rascunho_data: dict[str, Any]) -> None:
    """Bloqueia rejeitar_rascunho_catalogo sobre rascunho em estado terminal."""
    estado = estado_rascunho(rascunho_data)
    if estado == ESTADO_APROVADO:
        raise CatalogDraftGovernanceError("Rascunho já foi aprovado e não pode mais ser rejeitado.")
    if estado == ESTADO_REJEITADO:
        raise CatalogDraftGovernanceError("Rascunho já havia sido rejeitado.")
