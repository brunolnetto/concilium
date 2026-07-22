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
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

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


def marcar_revisado(rascunho_data: dict[str, Any], revisor: str) -> dict[str, Any]:
    """RASCUNHO -> REVISADO: registra que divergências/impacto foram revisados.

    No-op (retorna os dados inalterados) se o rascunho já está em estado
    terminal (APROVADO/REJEITADO) — revisão tardia não deveria reabrir o
    ciclo de vida.
    """
    if estado_rascunho(rascunho_data) in (ESTADO_APROVADO, ESTADO_REJEITADO):
        return rascunho_data
    return {**rascunho_data, "_revisado": True, "_revisado_por": revisor}


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
    criado_por = rascunho_data.get("created_by")
    if criado_por and criado_por == aprovador:
        raise CatalogDraftGovernanceError(
            f"Violação da regra dos quatro olhos: '{aprovador}' criou este rascunho e não pode aprová-lo."
        )


def assert_pode_rejeitar(rascunho_data: dict[str, Any]) -> None:
    """Bloqueia rejeitar_rascunho_catalogo sobre rascunho em estado terminal."""
    estado = estado_rascunho(rascunho_data)
    if estado == ESTADO_APROVADO:
        raise CatalogDraftGovernanceError("Rascunho já foi aprovado e não pode mais ser rejeitado.")
    if estado == ESTADO_REJEITADO:
        raise CatalogDraftGovernanceError("Rascunho já havia sido rejeitado.")


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
