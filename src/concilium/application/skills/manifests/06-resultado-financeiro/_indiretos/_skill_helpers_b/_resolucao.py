"""Skill 05 — Indiretos (ADR-009, ADR-023 §D4).

Resolução de composição por categoria, sub-custos, BDI e validações.
"""

from __future__ import annotations

from typing import Any

from concilium.domain.constants import SEMANAS_POR_MES as _SEMANAS_POR_MES  # ADR-056 §T3
from concilium.domain.models.canonical import (
    CanonicalModel,
    IndirectoCategoria,
    Indireto,
    IndiretoComBdi,
    ValidacaoItem,
)
from concilium.domain.models.financial.bdi import DEFAULT_BDI_TABELA, TabelaBdi

from ._categoria import _as_categoria_indireto, _build_categoria_from_dict  # ty: ignore[unresolved-import]

try:
    # Hyphenated manifest dir: only loaded at runtime via a synthetic package
    # (see concilium/application/skills/__init__.py); ty cannot resolve this
    # statically.
    from .._skill_helpers_a import (  # ty: ignore[unresolved-import]
        _composicao_default_por_categoria,
        _dimensionar_automatico,
    )
except ImportError:
    import importlib.util
    from pathlib import Path

    _here = Path(__file__).resolve().parent.parent
    _path_a = _here / "_skill_helpers_a.py"
    _spec_a = importlib.util.spec_from_file_location("skill07_helpers_a_for_b_resolucao", _path_a)
    if _spec_a is None or _spec_a.loader is None:
        raise ImportError(f"Não foi possível carregar spec para: {_path_a}") from None
    _mod_a = importlib.util.module_from_spec(_spec_a)
    _spec_a.loader.exec_module(_mod_a)
    _composicao_default_por_categoria = _mod_a._composicao_default_por_categoria
    _dimensionar_automatico = _mod_a._dimensionar_automatico


def _resolve_categoria_comp(
    codigo: str,
    cat: dict,
    composicoes_input: dict,
    categorias_config_raw: list,
    n_semanas: int,
    repo: Any,
    data_base: Any,
    overrides: dict | None,
    jurisdicao_id: str | None,
    canonical_in: CanonicalModel,
    catalogo: dict | None,
) -> IndirectoCategoria:
    cat_cfg_raw = next((c for c in categorias_config_raw if c.get("categoria") == codigo), None)
    if cat_cfg_raw:
        return IndirectoCategoria(**cat_cfg_raw)
    if codigo in composicoes_input:
        return _build_categoria_from_dict(
            codigo,
            composicoes_input[codigo],
            n_semanas,
            repo,
            data_base,
            overrides=overrides,
            jurisdicao_id=jurisdicao_id,
        )
    if "regra_dimensionamento" in cat:
        comp_auto = _dimensionar_automatico(codigo, cat["regra_dimensionamento"], canonical_in, catalogo)
        return _build_categoria_from_dict(
            codigo, comp_auto, n_semanas, repo, data_base, overrides=overrides, jurisdicao_id=jurisdicao_id
        )
    comp_default = _composicao_default_por_categoria(codigo)
    return _build_categoria_from_dict(
        codigo, comp_default, n_semanas, repo, data_base, overrides=overrides, jurisdicao_id=jurisdicao_id
    )


def _apply_dv4_scale_to_categoria(
    cat_obj: IndirectoCategoria,
    dv4_policy: str | None,
    policy_scale: dict,
    n_semanas: int,
    prazo_meses: float | None = None,
) -> tuple[float, IndirectoCategoria]:
    if cat_obj.driver == "permanencia" and prazo_meses is not None:
        custo = round(cat_obj.custo_fixo_mensal * float(prazo_meses), 2)
    else:
        custo = cat_obj.custo_total_para_semanas(n_semanas)
    if dv4_policy and dv4_policy in policy_scale:
        scale = policy_scale[dv4_policy]
        custo = round(custo * scale, 2)
        cat_obj = cat_obj.model_copy(update={"custo_fixo_mensal": round(cat_obj.custo_fixo_mensal * scale, 2)})
    return custo, cat_obj


def _sub_custos_indireto(
    cat_obj: IndirectoCategoria, custo_total: float, perc_encargos: float = 0.0
) -> dict[str, float]:
    """ADR-090: calcula sub-custos por categoria_insumo para BDI diferenciado.

    Se os componentes de cat_obj têm custo explícito, usa-os diretamente.
    Senão, distribui custo_total pelas frações de custo_fixo_mensal de cada componente.
    """

    def _comp_custo(comp) -> float:
        if comp is None:
            return 0.0
        if hasattr(comp, "custo_total") and (comp.custo_total or 0.0) > 0:
            return float(comp.custo_total)
        return float(comp.custo_fixo_mensal or 0.0)

    c_mo = _comp_custo(cat_obj.mao_de_obra)
    c_eq = _comp_custo(cat_obj.equipamentos)
    c_verba = _comp_custo(cat_obj.verbas)

    # ADR-090 (correção 2026-06-11): quando a composição explica só PARTE do custo
    # mensal da categoria (ex.: spec decompõe apenas mao_obra), o resíduo
    # não-decomposto vai para verba (taxa de indireto — conservadora, igual ao
    # fallback de composição ausente). Sem isto, o resíduo herdava a classificação
    # dos componentes presentes (no AGIS: 65% do ADM virava MO → BDI de MO sobre
    # equipamentos+verbas da planilha).
    mensal_total = float(getattr(cat_obj, "custo_fixo_mensal", 0.0) or 0.0)
    c_explicado = c_mo + c_eq + c_verba
    if mensal_total > c_explicado > 0:
        c_verba += mensal_total - c_explicado
    c_base = c_mo + c_eq + c_verba

    if c_base > 0 and custo_total > 0:
        scale = custo_total / c_base
        c_mo_scaled = round(c_mo * scale, 2)
        # NEP-037 D4: separar base e encargos na MO indireta.
        # c_mo_scaled = base × (1 + enc) → base = c_mo_scaled / (1 + enc)
        frac_enc = perc_encargos / (1.0 + perc_encargos) if perc_encargos > 0 else 0.0
        c_enc_scaled = round(c_mo_scaled * frac_enc, 2)
        c_mo_base_scaled = c_mo_scaled - c_enc_scaled
        return {
            "custo_mao_obra": c_mo_base_scaled,
            "custo_encargos": c_enc_scaled,
            "custo_equipamentos": round(c_eq * scale, 2),
            "custo_verba": round(c_verba * scale, 2),
            "custo_combustivel": 0.0,
            "custo_mobilizacao": 0.0,
        }
    # Fallback: sem dados de composição → tudo como verba (taxa mais conservadora)
    return {
        "custo_mao_obra": 0.0,
        "custo_encargos": 0.0,
        "custo_equipamentos": 0.0,
        "custo_verba": round(custo_total, 2),
        "custo_combustivel": 0.0,
        "custo_mobilizacao": 0.0,
    }


def _build_indireto_from_cat_obj(
    codigo: str,
    descricao: str,
    cat_obj: IndirectoCategoria,
    custo: float,
    n_semanas: int,
    prazo_meses: float | None = None,
) -> Indireto:
    permanencia_meses = float(prazo_meses) if prazo_meses is not None else round(n_semanas / _SEMANAS_POR_MES, 2)
    subs = _sub_custos_indireto(cat_obj, custo)
    return Indireto(
        categoria=_as_categoria_indireto(codigo),
        descricao=descricao,
        funcoes=[item for item in (cat_obj.mao_de_obra.itens if cat_obj.mao_de_obra else [])],
        equipamentos=[item for item in (cat_obj.equipamentos.itens if cat_obj.equipamentos else [])],
        verbas_mensais=[item for item in (cat_obj.verbas.itens if cat_obj.verbas else [])],
        permanencia_meses=permanencia_meses,
        custo_total=custo,
        # ADR-090: sub-custos para BDI diferenciado por categoria_insumo
        # NEP-037 D4: custo_mao_obra = base sem encargos; custo_encargos = encargos sociais
        custo_mao_obra=subs["custo_mao_obra"],
        custo_encargos=subs.get("custo_encargos", 0.0),
        custo_equipamentos=subs["custo_equipamentos"],
        custo_combustivel=subs["custo_combustivel"],
        custo_verba=subs["custo_verba"],
        custo_mobilizacao=subs["custo_mobilizacao"],
    )


def _validate_dv4_policy(dv4_policy: str | None, validacoes: list, policy_scale: dict) -> None:
    if not dv4_policy:
        return
    if dv4_policy in policy_scale:
        validacoes.append(
            ValidacaoItem(
                codigo="VAL-IND-POL-01",
                status="OK",
                mensagem=f"Policy '{dv4_policy}' aplicada (scale={policy_scale[dv4_policy]})",
            )
        )
    else:
        validacoes.append(
            ValidacaoItem(codigo="VAL-IND-POL-01", status="ERRO", mensagem=f"Policy desconhecida: '{dv4_policy}'")
        )


def _validate_razao_indireto_direto(
    perfil: dict | None,
    canonical_in: CanonicalModel,
    indiretos_out: list,
    validacoes: list,
) -> None:
    razao_alvo = (perfil or {}).get("razao_indireto_direto_alvo")
    if not razao_alvo or not canonical_in.equipes_diretas:
        return
    custo_direto = sum(eq.custo_total for eq in canonical_in.equipes_diretas)
    custo_indireto = sum(i.custo_total for i in indiretos_out)
    if custo_direto <= 0:
        return
    razao = custo_indireto / custo_direto
    if not (razao_alvo["min"] <= razao <= razao_alvo["max"]):
        validacoes.append(
            ValidacaoItem(
                codigo="VAL-POL-INDIRETO",
                status="AVISO",
                mensagem=(
                    f"Razão indireto/direto {razao * 100:.1f}% fora da faixa"
                    f" [{razao_alvo['min'] * 100:.1f}%, {razao_alvo['max'] * 100:.1f}%]"
                ),
            )
        )
    else:
        validacoes.append(ValidacaoItem(codigo="VAL-POL-INDIRETO", status="OK"))


def _apply_bdi_to_indiretos(
    tabela_bdi_raw: Any,
    indiretos_out: list,
    validacoes: list,
) -> list[IndiretoComBdi]:
    from concilium.domain.models.financial.bdi import resolve_bdi_tabela

    try:
        tabela_bdi: TabelaBdi = resolve_bdi_tabela(tabela_bdi_raw)
    except Exception as e:
        validacoes.append(
            ValidacaoItem(
                codigo="VAL-INDIR-BDI-PARSE",
                status="AVISO",
                mensagem=f"Falha ao parsear inputs.tabela_bdi: {e}. Usando DEFAULT_BDI_TABELA.",
            )
        )
        tabela_bdi = DEFAULT_BDI_TABELA
    bdi_indir = tabela_bdi.indireto.bdi_total
    indiretos_com_bdi_out: list[IndiretoComBdi] = []
    for ind in indiretos_out:
        custo_sem = ind.custo_total
        custo_com = round(custo_sem * (1 + bdi_indir), 2)
        try:
            indiretos_com_bdi_out.append(
                IndiretoComBdi(
                    categoria=ind.categoria,
                    custo_sem_bdi=custo_sem,
                    bdi_aplicado=round(bdi_indir, 6),
                    custo_com_bdi=custo_com,
                )
            )
        except Exception as e:  # pragma: no cover
            validacoes.append(
                ValidacaoItem(
                    codigo="VAL-INDIR-BDI-ITEM",
                    status="AVISO",
                    mensagem=f"IndiretoComBdi não gerado para '{ind.categoria}': {e}",
                )
            )
    if indiretos_com_bdi_out:
        custo_total_sem = sum(i.custo_sem_bdi for i in indiretos_com_bdi_out)
        custo_total_com = sum(i.custo_com_bdi for i in indiretos_com_bdi_out)
        validacoes.append(
            ValidacaoItem(
                codigo="VAL-INDIR-BDI-OK",
                status="OK",
                mensagem=(
                    f"BDI-INDIRETO {bdi_indir * 100:.2f}% aplicado a {len(indiretos_com_bdi_out)} categorias:"
                    f" sem_bdi=R${custo_total_sem:,.2f} -> com_bdi=R${custo_total_com:,.2f}"
                ),
            )
        )
    return indiretos_com_bdi_out


