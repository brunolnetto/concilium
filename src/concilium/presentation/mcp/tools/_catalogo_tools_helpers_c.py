"""MCP catalogo tool implementations — Part C (ADR-150: promoção de override de projeto)."""

from __future__ import annotations

import json
from datetime import date
from typing import Any

from concilium.application.orchestrators.catalog_draft_lifecycle import (
    abrir_ou_obter_rascunho_projeto,
    assert_pode_promover_projeto,
    build_and_persist_snapshot,
    marcar_rascunho_projeto_aprovado,
)
from concilium.presentation.mcp._context import _config_root, _projetos_root, _runtime, _wrap_response

from ._catalogo_tools_helpers_a import _apply_preco_insumo_delta
from ._catalogo_tools_helpers_a import _catalog_root as _resolve_catalog_root


def _parse_override_key(key: str) -> tuple[str, str | None]:
    """Desfaz a chave composta `codigo::jurisdicao` gravada por atualizar_preco_insumo."""
    if "::" in key:
        insumo_id, jurisdicao = key.split("::", 1)
        return insumo_id, (None if jurisdicao == "BASE" else jurisdicao)
    return key, None


def _override_preco(entry: dict[str, Any]) -> float:
    """Aceita os três nomes de campo de preço usados historicamente no override (ADR-040/145)."""
    preco = entry.get("preco_calibrado")
    if preco is None:
        preco = entry.get("preco_unitario")
    if preco is None:
        preco = entry.get("preco")
    return float(preco or 0.0)


def _read_project_meta(proj_path) -> dict[str, Any]:
    meta_file = proj_path / "meta.json"
    if not meta_file.exists():
        return {}
    try:
        return json.loads(meta_file.read_text(encoding="utf-8"))
    except Exception:
        return {}


def _impl_promover_override_projeto(
    projeto_id: str,
    contexto_id: str | None = None,
    justificativa: str = "",
) -> dict[str, Any]:
    """Promove os overrides de insumo pendentes de um projeto ao catálogo master (ADR-150).

    Fecha o bypass de governança do `concilium manage catalog promote` (CLI):
    antes desta ADR, aquele comando gravava direto no catálogo mestre via
    `_write_json`, sem rascunho, sem 4-olhos, sem `CatalogSnapshot`. Este é o
    caminho gated que o substitui — reaproveitado tanto pelo tool MCP quanto
    pelo comando CLI (ADR-150 D4).

    Gate dual (D2), cumulativo:
      (a) `require_owner_or_admin` (ADR-126) — promotor é o dono do projeto ou admin;
      (b) quatro olhos (ADR-120) — promotor é diferente de quem editou o override.
    A role `catalog:merge` em si é exigida pelo decorator `@permission` do tool MCP
    (ou pelo chamador, no caso do CLI) — não é checada de novo aqui.

    Escrita efetiva (D3) reaproveita `RepositorioInsumo.atualizar_preco()` e
    `CatalogSnapshot`/`CatalogDiff` (`build_and_persist_snapshot`, ADR-024/145) —
    o mesmo caminho de `aprovar_merge_catalogo`, não uma escrita paralela.

    Args:
        projeto_id: ID do projeto de origem do override.
        contexto_id: Contexto de catálogo a promover. Se omitido, usa o
            `contexto_id` gravado no meta do projeto.
        justificativa: Motivo da promoção para o audit trail (CatalogDiff).
    """
    from concilium.infrastructure.auth.permission_guard import _current_roles, get_current_user_id

    config_root = _config_root()
    projects_dir = _projetos_root()
    proj_path = projects_dir / projeto_id
    if not proj_path.exists():
        return {"erro": f"Projeto {projeto_id} não encontrado."}

    meta = _read_project_meta(proj_path)
    owner_id = meta.get("owner_id")
    contexto_efetivo = contexto_id or meta.get("contexto_id")
    if not contexto_efetivo:
        return {"erro": "Não foi possível determinar contexto do projeto para promoção. Informe contexto_id."}

    actor = get_current_user_id() or "system"
    roles = list(_current_roles.get())

    # Checa se há algo a promover ANTES do gate: uma tentativa "vazia" (nada
    # editado ainda, ou já promovido e arquivado) é apenas informativa — não
    # deve levantar um erro de gate confuso (ex.: quatro-olhos contra si mesmo
    # só porque abrir_ou_obter_rascunho_projeto criaria um estado novo agora).
    overrides_file = proj_path / "overrides" / "insumos_override.json"
    overrides: dict[str, Any] = {}
    if overrides_file.exists():
        try:
            overrides = json.loads(overrides_file.read_text(encoding="utf-8"))
        except Exception:
            overrides = {}

    if not overrides:
        return _wrap_response(
            {
                "status": "SEM_PENDENCIAS",
                "projeto_id": projeto_id,
                "nota": "Nenhum override de insumo pendente para promover.",
            }
        )

    rascunho_data = abrir_ou_obter_rascunho_projeto(projects_dir, projeto_id, actor)
    try:
        assert_pode_promover_projeto(
            rascunho_data,
            projeto_owner_id=owner_id,
            promotor_id=actor,
            promotor_roles=roles,
        )
    except Exception as exc:
        return _wrap_response({"erro": str(exc)})

    rt = _runtime()
    ctx = rt.load_contexto(contexto_efetivo)
    catalog_root = _resolve_catalog_root(config_root, ctx.catalogo_id)
    hoje = date.today()

    deltas_aplicados = 0
    for key, entry in overrides.items():
        insumo_id, jurisdicao_id = _parse_override_key(key)
        _apply_preco_insumo_delta(
            catalog_root,
            insumo_id,
            _override_preco(entry),
            jurisdicao_id,
            entry.get("nota") or entry.get("motivo"),
            actor,
            hoje,
        )
        deltas_aplicados += 1

    catalogo_depois = _runtime().load_catalogo(ctx.catalogo_id)
    snapshot_id, diff_summary = build_and_persist_snapshot(
        config_root,
        ctx.catalogo_id,
        catalogo_depois,
        actor=actor,
        contexto_id=contexto_efetivo,
        rascunho_id=f"projeto:{projeto_id}",
        justificativa=justificativa,
    )

    # Arquiva os overrides aplicados (ADR-040 D4) — depois de promovidos, não
    # devem seguir sombreando o preço recém-escrito no master como se ainda
    # fossem uma calibração pendente.
    historico_dir = proj_path / "overrides" / "historico"
    historico_dir.mkdir(parents=True, exist_ok=True)
    (historico_dir / f"insumos_override_{hoje.isoformat()}.json").write_text(
        json.dumps(overrides, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    overrides_file.write_text(json.dumps({}, ensure_ascii=False, indent=2), encoding="utf-8")

    marcar_rascunho_projeto_aprovado(projects_dir, projeto_id, actor)

    return _wrap_response(
        {
            "status": "APROVADO",
            "projeto_id": projeto_id,
            "contexto_id": contexto_efetivo,
            "catalogo_id": ctx.catalogo_id,
            "aprovado_por": actor,
            "justificativa": justificativa,
            "deltas_aplicados": deltas_aplicados,
            "snapshot_id": snapshot_id,
            "diff_summary": diff_summary,
        }
    )
