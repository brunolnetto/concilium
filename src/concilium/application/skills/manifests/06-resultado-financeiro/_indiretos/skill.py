"""Skill 05 — Indiretos (ADR-009, ADR-023 §D4).

Dimensiona custos indiretos com granularidade semanal.
ADR-023 §D4: também emite IndiretoComBdi com BDI-INDIRETO aplicado sobre cada categoria.

Categorias suportadas: ADM, TOP, LAB, QSMS, MOB.

Drivers:
  permanencia: custo_fixo_mensal ÷ 4.33 × n_semanas (TOP, ADM, LAB, QSMS)
  one_time:    custo_fixo_total alocado nas semanas 0 e final (MOB)

Inputs (no dict 'inputs'):
    composicoes_indireto: dict[categoria, dict] — opcional, override por categoria
    dados_mobilizacao:    dict — para categoria MOB (legado)
    perc_encargos:        float — default 0.92
    categorias_config:    list[dict] — lista de IndirectoCategoria serializadas (ADR-009 novo)
    tabela_bdi:           TabelaBdi serializada — para bdi_indireto (ADR-023 §D4); opcional
"""

from __future__ import annotations

from typing import Any

from concilium.application.skills.base import SkillResult
from concilium.domain.models.canonical import (
    CanonicalModel,
    Indireto,
    IndiretoSemanal,
    ValidacaoItem,
)
from concilium.infrastructure.repositories.insumo import RepositorioInsumo

try:
    from ._skill_helpers_a import (
        _composicao_default_por_categoria,
        _meses_entre,
        _semanas_projeto,
    )
    from ._skill_helpers_b import (
        _apply_bdi_to_indiretos,
        _apply_dv4_scale_to_categoria,
        _build_indireto_from_cat_obj,
        _build_semanal_breakdown,
        _count_pessoas_diretas,
        _extract_dv4_policy,
        _extract_overrides,
        _get_pipeline_blocked,
        _process_mob_categoria,
        _resolve_categoria_comp,
        _validate_dv4_policy,
        _validate_razao_indireto_direto,
    )
except ImportError:
    import importlib.util
    from pathlib import Path

    _here = Path(__file__).resolve().parent
    _spec_a = importlib.util.spec_from_file_location("skill07_helpers_a", _here / "_skill_helpers_a.py")
    _mod_a = importlib.util.module_from_spec(_spec_a)  # type: ignore[arg-type]
    _spec_a.loader.exec_module(_mod_a)  # type: ignore[union-attr]

    _spec_b = importlib.util.spec_from_file_location("skill07_helpers_b", _here / "_skill_helpers_b.py")
    _mod_b = importlib.util.module_from_spec(_spec_b)  # type: ignore[arg-type]
    _spec_b.loader.exec_module(_mod_b)  # type: ignore[union-attr]

    _composicao_default_por_categoria = _mod_a._composicao_default_por_categoria
    _meses_entre = _mod_a._meses_entre
    _semanas_projeto = _mod_a._semanas_projeto
    _apply_bdi_to_indiretos = _mod_b._apply_bdi_to_indiretos
    _apply_dv4_scale_to_categoria = _mod_b._apply_dv4_scale_to_categoria
    _build_indireto_from_cat_obj = _mod_b._build_indireto_from_cat_obj
    _build_semanal_breakdown = _mod_b._build_semanal_breakdown
    _count_pessoas_diretas = _mod_b._count_pessoas_diretas
    _extract_dv4_policy = _mod_b._extract_dv4_policy
    _extract_overrides = _mod_b._extract_overrides
    _get_pipeline_blocked = _mod_b._get_pipeline_blocked
    _process_mob_categoria = _mod_b._process_mob_categoria
    _resolve_categoria_comp = _mod_b._resolve_categoria_comp
    _validate_dv4_policy = _mod_b._validate_dv4_policy
    _validate_razao_indireto_direto = _mod_b._validate_razao_indireto_direto

# Fator padrão: 1 mês = 4.33 semanas
# _SEMANAS_POR_MES agora importada de domain/constants.py (era 4.33, corrigido para 4.3482)


def run_custos_indiretos(
    canonical_in: CanonicalModel,
    inputs: dict[str, Any],
    catalogo: dict[str, Any] | None = None,
    perfil: dict[str, Any] | None = None,
    **kwargs: Any,
) -> SkillResult:
    """Popula seções 'indiretos' e 'indiretos_semanal' do canônico."""
    validacoes: list[ValidacaoItem] = []

    repo = RepositorioInsumo(catalogo) if catalogo else None
    data_base = canonical_in.projeto.data_base_orcamento
    overrides = _extract_overrides(inputs)
    jurisdicao_id = inputs.get("jurisdicao_id")

    _blocked = _get_pipeline_blocked(canonical_in)
    mob_bloqueada = bool(_blocked & {"03-equipes-diretas", "05-equipes-e-alocacao"})

    if mob_bloqueada:
        validacoes.append(
            ValidacaoItem(
                codigo="VAL-INDIR-MOB-BLOQUEADO",
                status="AVISO",
                mensagem=(
                    "MOB omitido: skill 03-equipes-diretas está em pipeline_blocked_from."
                    " Custo de mobilização não calculado para evitar MOB=R$0 silencioso (ADR-022 D5)."
                    " Corrija skill 03 e re-execute 07-custos-indiretos."
                ),
            )
        )
    elif not canonical_in.equipes_diretas:
        validacoes.append(
            ValidacaoItem(
                codigo="VAL-IND-PRECONDICAO",
                status="AVISO",
                mensagem="equipes_diretas vazia — usando 0 pessoas para cálculo de MOB",
            )
        )

    # Indiretos acompanham as atividades diretas: usar makespan do algoritmo de otimização.
    # A duração do canteiro é determinada pelo cronograma produtivo (RCPSP), não pelo prazo
    # contratual — a obra termina quando o cronograma diz que termina.
    # Se o makespan exceder o prazo contratual (projeto atrasado), usa-se o makespan.
    # Fallback: n_semanas_contrato quando não há cronograma calculado.
    cron = getattr(canonical_in, "cronograma", None)
    makespan_real = int(getattr(cron, "makespan_weeks", 0) or 0)
    n_semanas_contrato = _semanas_projeto(canonical_in.projeto.data_inicio, canonical_in.projeto.data_termino)
    n_semanas = makespan_real if makespan_real > 0 else n_semanas_contrato
    prazo_meses = round(n_semanas / 4.345, 1)
    num_pessoas_direta = _count_pessoas_diretas(canonical_in)

    composicoes_input = inputs.get("composicoes_indireto", {})
    dados_mob = inputs.get("dados_mobilizacao", {})
    categorias_config_raw: list[dict] = inputs.get("categorias_config", [])
    dv4_policy = _extract_dv4_policy(inputs)
    policy_scale = {"lean": 0.85, "standard": 1.0, "robust": 1.15}

    # ADR-105: Tentar obter mob_schedule do canônico (inferido por Skill-04)
    mob_schedule = getattr(canonical_in, "mob_schedule", None)

    indiretos_out: list[Indireto] = []
    indiretos_semanal_out: list[IndiretoSemanal] = []

    for cat in (perfil or {}).get("categorias_indireto", []):
        codigo: str = cat["codigo"]
        if codigo == "MOB" and mob_bloqueada:
            continue
        if codigo == "MOB":
            indir, semanal = _process_mob_categoria(
                cat,
                categorias_config_raw,
                dados_mob,
                num_pessoas_direta,
                prazo_meses,
                n_semanas,
                dv4_policy,
                policy_scale,
                mob_schedule=mob_schedule,
            )
            indiretos_out.append(indir)
            indiretos_semanal_out.extend(semanal)
        else:
            cat_obj = _resolve_categoria_comp(
                codigo,
                cat,
                composicoes_input,
                categorias_config_raw,
                n_semanas,
                repo,
                data_base,
                overrides,
                jurisdicao_id,
                canonical_in,
                catalogo,
            )
            custo, cat_obj = _apply_dv4_scale_to_categoria(
                cat_obj,
                dv4_policy,
                policy_scale,
                n_semanas,
                float(prazo_meses),
            )
            indiretos_out.append(
                _build_indireto_from_cat_obj(
                    codigo,
                    cat["descricao"],
                    cat_obj,
                    custo,
                    n_semanas,
                    float(prazo_meses),
                )
            )
            indiretos_semanal_out.extend(_build_semanal_breakdown(cat_obj, n_semanas, custo))

    _validate_dv4_policy(dv4_policy, validacoes, policy_scale)
    _validate_razao_indireto_direto(perfil, canonical_in, indiretos_out, validacoes)
    indiretos_com_bdi_out = _apply_bdi_to_indiretos(inputs.get("tabela_bdi"), indiretos_out, validacoes)

    novo = canonical_in.model_copy(
        update={
            "indiretos": indiretos_out,
            "indiretos_semanal": indiretos_semanal_out,
            "indiretos_com_bdi": indiretos_com_bdi_out,
        }
    )
    custo_total_semanal = sum(s.custo_semanal for s in indiretos_semanal_out)
    validacoes.append(
        ValidacaoItem(
            codigo="VAL-IND-OK",
            status="OK",
            mensagem=(
                f"{len(indiretos_out)} categorias; {n_semanas} semanas; custo semanal total={custo_total_semanal:.2f}"
            ),
        )
    )
    return SkillResult(novo, validacoes)
