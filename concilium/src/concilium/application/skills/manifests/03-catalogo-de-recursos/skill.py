"""Skill 01A — Declarar Recursos.

Declara catálogo de tipos de recurso e pool inicial do projeto.
Esta skill roda antes do cronograma e não cria requisitos por atividade.

Inputs:
    tipos_recurso: list[{id, nome, categoria, custo_unitario_dia, especificacoes?}]
    pool_inicial: list[{tipo_id, quantidade_total, custo_aquisicao_total?}]
    templates_recursos: dict[cpu_id | "default", list[{tipo|tipo_id, nome, categoria,
                         custo_unitario_dia, especificacoes?}]]
"""

import uuid
from typing import Any

from concilium.application.skills.base import SkillResult
from concilium.domain.models.canonical import (
    CanonicalModel,
    RecursoPool,
    TipoRecurso,
    ValidacaoItem,
)
from concilium.infrastructure.repositories.insumo import RepositorioInsumo


def _resolve_custo_unit_from_repo(
    tipo_id: str,
    repo: object,
    jurisdicao_id: str | None,
    overrides: dict | None,
    data_base: str | None,
) -> float:
    """Resolve custo_unitario_dia via repositório; retorna 0.0 se indisponível."""
    if not repo:
        return 0.0
    insumo = repo.obter_insumo(tipo_id)  # type: ignore[attr-defined]
    if not insumo:
        return 0.0
    preco_resolvido, _fonte = repo.resolver_preco(  # type: ignore[attr-defined]
        tipo_id,
        jurisdicao_id=jurisdicao_id,
        overrides=overrides,
        data_referencia=data_base,
    )
    preco = float(preco_resolvido or insumo.get("preco_unitario", 0.0))
    unid = insumo.get("unidade", "h")
    if unid == "h":
        return preco * 8
    if unid == "mes":
        return preco / 30
    return preco


def _make_tipo_recurso(
    spec: dict, tipo_id: str, repo: object, jurisdicao_id: str | None, overrides: dict | None, data_base: str | None
) -> "TipoRecurso":
    custo_unit = float(spec.get("custo_unitario_dia", 0))
    if custo_unit == 0:
        custo_unit = _resolve_custo_unit_from_repo(tipo_id, repo, jurisdicao_id, overrides, data_base)
    return TipoRecurso(
        id=tipo_id,
        nome=spec.get("nome", tipo_id),
        categoria=spec.get("categoria", "EQUIPAMENTO"),
        custo_unitario_dia=custo_unit,
        especificacoes=spec.get("especificacoes", {}),
    )


def _process_tipos_in(
    tipos_in: list,
    tipos: dict,
    repo: object,
    jurisdicao_id: str | None,
    overrides: dict | None,
    data_base: str | None,
    validacoes: list,
) -> None:
    for spec in tipos_in:
        tipo_id = spec.get("id") or spec.get("tipo") or spec.get("tipo_id")
        if not tipo_id:
            validacoes.append(
                ValidacaoItem(
                    codigo="VAL-DECL-01",
                    status="AVISO",
                    mensagem="Entrada em tipos_recurso sem id/tipo/tipo_id foi ignorada.",
                )
            )
            continue
        tipos[tipo_id] = _make_tipo_recurso(spec, tipo_id, repo, jurisdicao_id, overrides, data_base)


def _process_templates(
    templates: dict,
    tipos: dict,
    repo: object,
    jurisdicao_id: str | None,
    overrides: dict | None,
    data_base: str | None,
) -> None:
    for template_list in templates.values():
        for spec in template_list:
            tipo_id = spec.get("tipo") or spec.get("tipo_id") or spec.get("nome", "").upper().replace(" ", "_")
            if not tipo_id or tipo_id in tipos:
                continue
            tipos[tipo_id] = _make_tipo_recurso(spec, tipo_id, repo, jurisdicao_id, overrides, data_base)


def _build_pool_from_specs(
    pool_inicial: list,
    tipos_por_id: dict,
    pools_existentes: dict,
    projeto_id: str,
    validacoes: list,
) -> list:
    pool: list = []
    for spec in pool_inicial:
        tipo_id = spec["tipo_id"]
        if tipo_id not in tipos_por_id:
            validacoes.append(
                ValidacaoItem(
                    codigo="VAL-REC-01",
                    status="ERRO",
                    mensagem=f"pool_inicial referencia tipo desconhecido: '{tipo_id}'",
                )
            )
            validacoes.append(
                ValidacaoItem(
                    codigo="VAL-DECL-02",
                    status="AVISO",
                    mensagem=f"pool_inicial referencia tipo desconhecido: '{tipo_id}' (compat)",
                )
            )
            continue
        qtd = int(spec.get("quantidade_total", 1))
        if qtd <= 0:
            validacoes.append(
                ValidacaoItem(
                    codigo="VAL-REC-02",
                    status="ERRO",
                    mensagem=f"pool_inicial quantidade_total inválida para tipo '{tipo_id}': {qtd}",
                )
            )
            continue
        pool.append(
            RecursoPool(
                id=str(uuid.uuid4()),
                tipo_id=tipo_id,
                projeto_id=projeto_id,
                quantidade_total=qtd,
                quantidade_disponivel=qtd,
                custo_aquisicao_total=float(spec.get("custo_aquisicao_total", 0)),
            )
        )
    if not pool:
        if pools_existentes:
            pool = list(pools_existentes.values())
        else:
            for tipo_id in tipos_por_id:
                pool.append(
                    RecursoPool(
                        id=str(uuid.uuid4()),
                        tipo_id=tipo_id,
                        projeto_id=projeto_id,
                        quantidade_total=1,
                        quantidade_disponivel=1,
                    )
                )
    return pool


def run_catalogo_de_recursos(
    canonical_in: CanonicalModel,
    inputs: dict[str, Any],
    catalogo: dict[str, Any] | None = None,
    **_kwargs: Any,
) -> SkillResult:
    validacoes: list[ValidacaoItem] = []

    repo = RepositorioInsumo(catalogo) if catalogo else None
    data_base = canonical_in.projeto.data_base_orcamento
    overrides = inputs.get("insumos_override") if isinstance(inputs.get("insumos_override"), dict) else None
    jurisdicao_id = inputs.get("jurisdicao_id")

    tipos_in: list[dict] = inputs.get("tipos_recurso", [])
    templates: dict[str, list[dict]] = inputs.get("templates_recursos", {})
    pool_inicial: list[dict] = inputs.get("pool_inicial", [])

    tipos: dict[str, TipoRecurso] = {t.id: t for t in canonical_in.tipos_recurso}

    _process_tipos_in(tipos_in, tipos, repo, jurisdicao_id, overrides, data_base, validacoes)
    _process_templates(templates, tipos, repo, jurisdicao_id, overrides, data_base)

    tipos_list = list(tipos.values())
    tipos_por_id = {t.id: t for t in tipos_list}
    pools_existentes = {p.id: p for p in canonical_in.recurso_pool}
    projeto_id = str(canonical_in.projeto.id)

    pool = _build_pool_from_specs(pool_inicial, tipos_por_id, pools_existentes, projeto_id, validacoes)

    novo = canonical_in.model_copy(update={"tipos_recurso": tipos_list, "recurso_pool": pool})
    validacoes.append(
        ValidacaoItem(
            codigo="VAL-DECL-OK",
            status="OK",
            mensagem=f"Tipos declarados: {len(tipos_list)}; pools declarados: {len(pool)}.",
        )
    )
    return SkillResult(novo, validacoes)
