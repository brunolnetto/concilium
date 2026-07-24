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

import json
from pathlib import Path
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
            f"Rascunho foi rejeitado (motivo: {rascunho_data.get('_motivo_rejeicao') or '?'}) e não pode ser promovido."
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


# ── ADR-150: rascunho de override de projeto (mesmos estados, escopo de projeto) ──


def rascunho_projeto_file_path(projects_dir: Path, projeto_id: str) -> Path:
    """Caminho do arquivo de estado do rascunho de overrides de um projeto (ADR-150 D1)."""
    return projects_dir / projeto_id / "overrides" / "_rascunho_estado.json"


def abrir_ou_obter_rascunho_projeto(projects_dir: Path, projeto_id: str, actor: str) -> dict[str, Any]:
    """Abre (lazy) ou retorna o estado de rascunho dos overrides de um projeto (ADR-150 D1).

    Reaproveita as mesmas flags/estados de `RascunhoCatalogoStateMachine`
    (RASCUNHO/REVISADO/APROVADO/REJEITADO) sem duplicar a máquina de estados —
    só muda o local de armazenamento (por projeto, não por contexto global) e o
    campo extra `projeto_id` para rastreabilidade.

    Chamado a cada edição de override (`atualizar_preco_insumo(projeto_id=...)`):
    se o arquivo de estado ainda não existe, cria com `created_by=actor` (o
    primeiro a editar vira o "criador" para efeito da regra dos quatro olhos,
    ADR-150 D2); chamadas seguintes apenas retornam o estado existente sem
    sobrescrever `created_by`. Overrides gravados antes desta ADR (sem arquivo
    de estado) são tratados como RASCUNHO implícito na primeira leitura —
    nenhuma migração de dado é necessária.
    """
    path = rascunho_projeto_file_path(projects_dir, projeto_id)
    if path.exists():
        return json.loads(path.read_text(encoding="utf-8"))
    data: dict[str, Any] = {"_rascunho": True, "created_by": actor, "projeto_id": projeto_id}
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    return data


def assert_pode_promover_projeto(
    rascunho_data: dict[str, Any],
    *,
    projeto_owner_id: str | None,
    promotor_id: str,
    promotor_roles: list[str],
) -> None:
    """Gate dual de promoção de override de projeto ao catálogo master (ADR-150 D2).

    Exige, cumulativamente:
      (a) ownership — `promotor_id` é o dono do projeto ou admin (ADR-126,
          `require_owner_or_admin`); e
      (b) quatro olhos — `promotor_id` é diferente de quem abriu/editou o
          rascunho de override (`created_by`), mesma regra do rascunho global
          (ADR-120 D5). A checagem de role `catalog:merge` em si é feita pelo
          decorator `@permission` do tool MCP, antes de chegar aqui.

    Não exige estado REVISADO (diferente de `assert_pode_aprovar`) — não há
    hoje um tool de "revisar divergências" para override de projeto; qualquer
    estado não-terminal (RASCUNHO ou REVISADO) é promovível.
    """
    from concilium.infrastructure.auth.permission_guard import require_owner_or_admin

    estado = estado_rascunho(rascunho_data)
    if estado == ESTADO_APROVADO:
        raise CatalogDraftGovernanceError("Override de projeto já foi promovido anteriormente.")
    if estado == ESTADO_REJEITADO:
        raise CatalogDraftGovernanceError("Override de projeto foi rejeitado e não pode ser promovido.")
    require_owner_or_admin(actor_id=promotor_id, owner_id=projeto_owner_id, roles=promotor_roles)
    _checar_quatro_olhos(rascunho_data.get("created_by"), promotor_id)


def marcar_rascunho_projeto_aprovado(projects_dir: Path, projeto_id: str, aprovador: str) -> None:
    """Marca o rascunho de override do projeto como APROVADO (estado terminal, ADR-150 D2)."""
    path = rascunho_projeto_file_path(projects_dir, projeto_id)
    if path.exists():
        data = json.loads(path.read_text(encoding="utf-8"))
    else:
        data = {"_rascunho": True, "projeto_id": projeto_id}
    data["_aprovado"] = True
    data["_aprovado_por"] = aprovador
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def _group_insumos_by_tipo(insumos: list[dict[str, Any]]) -> dict[str, list[dict[str, Any]]]:
    grouped: dict[str, list[dict[str, Any]]] = {}
    for item in insumos:
        tipo = str(item.get("tipo", "outro")).lower()
        grouped.setdefault(tipo, []).append(item)
    return grouped


def build_and_persist_snapshot(
    config_root: Path,
    catalogo_id: str,
    catalogo_depois: dict[str, Any],
    *,
    actor: str,
    contexto_id: str,
    rascunho_id: str,
    justificativa: str,
) -> tuple[str, str]:
    """Gera e persiste CatalogSnapshot/CatalogDiff do merge (ADR-145 D3, ADR-024).

    Chamado por aprovar_merge_catalogo depois que os deltas do rascunho já
    foram aplicados ao catálogo mestre em disco. `justificativa` é gravada
    junto ao diff — não apenas ecoada na resposta MCP (fecha P5 do ADR-145).

    Returns:
        (snapshot_id, diff_summary)
    """
    from concilium.domain.models.catalog.snapshot import CatalogSnapshot, compute_catalog_diff

    snapshot = CatalogSnapshot.create(
        catalog_name=catalogo_id,
        cpus=catalogo_depois.get("cpus", []),
        insumos=_group_insumos_by_tipo(catalogo_depois.get("insumos", [])),
        produtividades=catalogo_depois.get("producoes", []),
        created_by=actor,
    )

    snapshots_dir = config_root / "catalogos" / catalogo_id / "snapshots"
    snapshots_dir.mkdir(parents=True, exist_ok=True)
    (snapshots_dir / f"{snapshot.meta.snapshot_id}.json").write_text(
        snapshot.model_dump_json(indent=2), encoding="utf-8"
    )

    diff_summary = "Primeiro snapshot registrado para este catálogo."
    latest_meta_file = snapshots_dir / "latest_meta.json"
    if latest_meta_file.exists():
        try:
            prev_meta = json.loads(latest_meta_file.read_text(encoding="utf-8"))
            prev_snapshot_file = snapshots_dir / f"{prev_meta['snapshot_id']}.json"
            if prev_snapshot_file.exists():
                prev_snapshot = CatalogSnapshot.model_validate_json(prev_snapshot_file.read_text(encoding="utf-8"))
                diff = compute_catalog_diff(prev_snapshot, snapshot)
                diff_summary = diff.summary
                diffs_dir = snapshots_dir / "diffs"
                diffs_dir.mkdir(parents=True, exist_ok=True)
                (diffs_dir / f"{diff.diff_id}.json").write_text(
                    json.dumps(
                        {
                            "diff": diff.model_dump(mode="json"),
                            "contexto_id": contexto_id,
                            "rascunho_id": rascunho_id,
                            "aprovador": actor,
                            "justificativa": justificativa,
                        },
                        ensure_ascii=False,
                        indent=2,
                    ),
                    encoding="utf-8",
                )
        except Exception:
            pass

    latest_meta_file.write_text(snapshot.meta.model_dump_json(indent=2), encoding="utf-8")
    return snapshot.meta.snapshot_id, diff_summary
