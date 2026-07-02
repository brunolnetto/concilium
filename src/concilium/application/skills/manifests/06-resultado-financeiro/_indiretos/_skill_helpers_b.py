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

import logging
from typing import Any

from concilium.application.scheduling.mob_scheduling import calcular_custo_indireto_mob
from concilium.domain.constants import SEMANAS_POR_MES as _SEMANAS_POR_MES  # ADR-056 §T3
from concilium.domain.models.canonical import (
    CanonicalModel,
    IndirectoCategoria,
    IndirectoCostComponent,
    Indireto,
    IndiretoComBdi,
    IndiretoSemanal,
    Mobilizacao,
    ValidacaoItem,
)
from concilium.domain.models.financial.bdi import DEFAULT_BDI_TABELA, TabelaBdi
from concilium.domain.models.project.decision_variables import DecisionVariables
from concilium.infrastructure.repositories.insumo import RepositorioInsumo

try:
    from ._skill_helpers_a import (
        _bcfd_enrich_mo_itens,
        _composicao_default_por_categoria,
        _dimensionar_automatico,
        _parse_component,
    )
except ImportError:
    import importlib.util
    from pathlib import Path

    _here = Path(__file__).resolve().parent
    _spec_a = importlib.util.spec_from_file_location("skill07_helpers_a_for_b", _here / "_skill_helpers_a.py")
    _mod_a = importlib.util.module_from_spec(_spec_a)  # type: ignore[arg-type]
    _spec_a.loader.exec_module(_mod_a)  # type: ignore[union-attr]
    _bcfd_enrich_mo_itens = _mod_a._bcfd_enrich_mo_itens
    _composicao_default_por_categoria = _mod_a._composicao_default_por_categoria
    _dimensionar_automatico = _mod_a._dimensionar_automatico
    _parse_component = _mod_a._parse_component

logger = logging.getLogger(__name__)

# Fator padrão: 1 mês = 4.33 semanas
# _SEMANAS_POR_MES agora importada de domain/constants.py (era 4.33, corrigido para 4.3482)


def _build_categoria_from_dict(
    codigo: str,
    comp_dict: dict,
    n_semanas: int,
    repo: RepositorioInsumo | None = None,
    data_base=None,
    overrides: dict[str, Any] | None = None,
    jurisdicao_id: str | None = None,
) -> IndirectoCategoria:
    """Constrói IndirectoCategoria a partir de dict de composição (ADR-009 driver=permanencia)."""
    _bcfd_enrich_mo_itens(comp_dict, repo, jurisdicao_id, overrides, data_base)
    mo = _parse_component(comp_dict.get("mao_de_obra"))
    eq = _parse_component(comp_dict.get("equipamentos"))
    vb = _parse_component(comp_dict.get("verbas"))
    custo_mensal = (
        (mo.custo_fixo_mensal if mo else 0.0)
        + (eq.custo_fixo_mensal if eq else 0.0)
        + (vb.custo_fixo_mensal if vb else 0.0)
    )
    custo_total = round(custo_mensal * (n_semanas / _SEMANAS_POR_MES), 2)
    return IndirectoCategoria(
        categoria=codigo,  # type: ignore[arg-type]
        driver="permanencia",
        mao_de_obra=mo,
        equipamentos=eq,
        verbas=vb,
        custo_fixo_mensal=custo_mensal,
        custo_fixo_total=custo_total,
    )


def _build_semanal_breakdown(
    categoria: IndirectoCategoria,
    n_semanas: int,
    custo_total_override: float | None = None,
) -> list[IndiretoSemanal]:
    """Gera breakdown semanal para uma categoria (ADR-009 §D2)."""
    result: list[IndiretoSemanal] = []
    if categoria.driver == "permanencia":
        mo_mensal = categoria.mao_de_obra.custo_fixo_mensal if categoria.mao_de_obra else 0.0
        eq_mensal = categoria.equipamentos.custo_fixo_mensal if categoria.equipamentos else 0.0
        vb_mensal = categoria.verbas.custo_fixo_mensal if categoria.verbas else 0.0
        mensal_total = mo_mensal + eq_mensal + vb_mensal

        if custo_total_override is not None and n_semanas > 0 and mensal_total > 0:
            # Preserva a proporção entre componentes e garante soma semanal == custo total utilizado na categoria.
            frac_mo = mo_mensal / mensal_total
            frac_eq = eq_mensal / mensal_total

            custo_sem_base = round(float(custo_total_override) / n_semanas, 2)
            acumulado = 0.0
            for w in range(n_semanas):
                if w < (n_semanas - 1):
                    custo_sem = custo_sem_base
                else:
                    custo_sem = round(float(custo_total_override) - acumulado, 2)
                acumulado += custo_sem

                mo_sem = round(custo_sem * frac_mo, 2)
                eq_sem = round(custo_sem * frac_eq, 2)
                vb_sem = round(custo_sem - mo_sem - eq_sem, 2)

                result.append(
                    IndiretoSemanal(
                        semana=w,
                        categoria=categoria.categoria,
                        custo_mao_de_obra=mo_sem,
                        custo_equipamentos=eq_sem,
                        custo_verbas=vb_sem,
                        custo_semanal=round(custo_sem, 2),
                        ativa=True,
                    )
                )
            return result

        mo_sem = mo_mensal / _SEMANAS_POR_MES
        eq_sem = eq_mensal / _SEMANAS_POR_MES
        vb_sem = vb_mensal / _SEMANAS_POR_MES
        custo_sem = mo_sem + eq_sem + vb_sem
        for w in range(n_semanas):
            result.append(
                IndiretoSemanal(
                    semana=w,
                    categoria=categoria.categoria,
                    custo_mao_de_obra=round(mo_sem, 2),
                    custo_equipamentos=round(eq_sem, 2),
                    custo_verbas=round(vb_sem, 2),
                    custo_semanal=round(custo_sem, 2),
                    ativa=True,
                )
            )
    else:
        # MOB: split entre semana 0 e semana final
        metade = round(categoria.custo_fixo_total / 2, 2)
        for w in range(n_semanas):
            ativa = w == 0 or w == (n_semanas - 1)
            custo_w = metade if ativa else 0.0
            result.append(
                IndiretoSemanal(
                    semana=w,
                    categoria=categoria.categoria,
                    custo_mao_de_obra=0.0,
                    custo_equipamentos=0.0,
                    custo_verbas=round(custo_w, 2) if ativa else 0.0,
                    custo_semanal=round(custo_w, 2),
                    ativa=ativa,
                )
            )
    return result


def _custo_mob_legado(dados_mob: dict, num_pessoas_direta: int, prazo_meses: int) -> tuple[float, list[Mobilizacao]]:
    """Calcula custo MOB legado (retrocompatível com formato anterior)."""
    custo_total = 0.0
    mobilizacoes: list[Mobilizacao] = []
    for m in dados_mob.get("mobilizacoes", []):
        mob = Mobilizacao(
            descricao=m["descricao"],
            num_unidades=m["num_unidades"],
            origem=m["origem"],
            destino=m["destino"],
            distancia_km=m["distancia_km"],
            custo_km=m["custo_km"],
            custo_total=m["num_unidades"] * m["distancia_km"] * m["custo_km"],
        )
        mobilizacoes.append(mob)
        custo_total += mob.custo_total
    custo_pessoa_mes = dados_mob.get(
        "custo_pessoa_mes", 1850
    )  # B3-known: R$1.850 legado; idealmente derivar do catálogo
    custo_total += num_pessoas_direta * custo_pessoa_mes * prazo_meses
    for b in dados_mob.get("baixadas", []):
        n_ocorrencias = len(b.get("meses_ocorrencia", []))
        custo_total += b.get("num_pessoas", 0) * b.get("valor_por_pessoa", 0) * n_ocorrencias
    return round(custo_total, 2), mobilizacoes


def _extract_overrides(inputs: dict) -> dict | None:
    val = inputs.get("insumos_override")
    if isinstance(val, dict):
        return val
    return None


def _count_pessoas_diretas(canonical_in: CanonicalModel) -> int:
    return sum(sum(f.num_pessoas for f in eq.funcoes) for eq in canonical_in.equipes_diretas)


def _get_pipeline_blocked(canonical_in: CanonicalModel) -> set:
    return set(canonical_in.pipeline_blocked_from or [])


def _extract_dv4_policy(inputs: dict) -> str | None:
    dv_obj = inputs.get("decision_variables") or inputs.get("dv")
    if dv_obj is None:
        return None
    if isinstance(dv_obj, dict):
        return dv_obj.get("dv4_indirect_policy")
    if isinstance(dv_obj, DecisionVariables):
        return dv_obj.dv4_indirect_policy
    return getattr(dv_obj, "dv4_indirect_policy", None)


def _process_mob_categoria(
    cat: dict,
    categorias_config_raw: list,
    dados_mob: dict,
    num_pessoas_direta: int,
    prazo_meses: int,
    n_semanas: int,
    dv4_policy: str | None,
    policy_scale: dict,
    mob_schedule: dict | None = None,
) -> tuple[Indireto, list[IndiretoSemanal]]:
    descricao: str = cat["descricao"]
    cat_cfg_raw = next((c for c in categorias_config_raw if c.get("categoria") == "MOB"), None)
    if cat_cfg_raw:
        cat_obj = IndirectoCategoria(**cat_cfg_raw)
        custo = cat_obj.custo_fixo_total
        mobs: list[Mobilizacao] = []
    else:
        custo, mobs = _custo_mob_legado(dados_mob, num_pessoas_direta, prazo_meses)
        cat_obj = IndirectoCategoria(
            categoria="MOB",
            driver="one_time",
            custo_fixo_total=custo,
            verbas=IndirectoCostComponent(nome="MOB", custo_fixo_mensal=0.0),
        )
    if dv4_policy and dv4_policy in policy_scale:
        custo = round(custo * policy_scale[dv4_policy], 2)
        cat_obj = cat_obj.model_copy(update={"custo_fixo_total": custo})

    # ADR-105: Se mob_schedule disponível, calcular distribuição por fase MOB/OP/DEMOB.
    # B1-fix (2026-06-19): resultado era descartado (try/pass dead code); agora loga
    # a distribuição e atualiza custo quando mob_schedule fornece total mais preciso.
    if mob_schedule:
        try:
            indiretos_mob = [
                {
                    "tipo": "MOB",
                    "categoria": "MOB",
                    "fase": "mobilizacao",
                    "driver": "projeto",
                    "custo_fixo_total": custo,  # B2-fix: usar custo real, não 0.15×custo
                }
            ]
            mob_result = calcular_custo_indireto_mob(indiretos_mob, mob_schedule)
            mob_total = mob_result.get("custo_mob_total", 0.0)
            if mob_total > 0:
                custo = round(mob_total, 2)
                cat_obj = cat_obj.model_copy(update={"custo_fixo_total": custo})
                logger.debug(
                    "MOB custo atualizado via mob_schedule: R$%.2f (fases: %s)",
                    custo,
                    list(mob_result.get("mob", {}).keys()),
                )
        except Exception as e:  # pragma: no cover
            logger.warning(
                "Falha ao calcular custo MOB com mob_schedule — usando custo legado R$%.2f: %s",
                custo,
                e,
                exc_info=True,
            )

    indir = Indireto(
        categoria="MOB",
        descricao=descricao,
        mobilizacoes=mobs,
        permanencia_meses=float(prazo_meses),
        custo_total=custo,
        # ADR-090: MOB é overhead administrativo → BDI_indireto
        custo_mobilizacao=round(custo, 2),
    )
    return indir, _build_semanal_breakdown(cat_obj, n_semanas)


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
        categoria=codigo,  # type: ignore[arg-type]
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


# ---------------------------------------------------------------------------
# ADR-105 F4/F5 — Distribuição de fases MOB: mobilizacao / operacao / desmobilizacao
# ---------------------------------------------------------------------------


def _distribuir_mob_fases(
    mob_items: list[dict],
    duracao_semanas: int,
) -> dict:
    """Distribui itens MOB com fases explícitas em custos por semana (ADR-105 F4/F5).

    Suporta três fases tipificadas para itens com campo ``fase``:

    - ``driver="projeto", fase="mobilizacao"``: custo único na semana 0 (início).
    - ``driver="mensal", fase="operacao"``: custo distribuído proporcionalmente
      ao longo de todas as semanas (custo_fixo_mensal × duracao_meses).
    - ``driver="projeto", fase="desmobilizacao"``: custo único na semana final
      (semana duracao_semanas - 1).

    Itens sem campo ``fase`` (legado) são passados adiante sem processamento
    — backward compat: não alteram o resultado.

    Args:
        mob_items: lista de dicts com chaves ``tipo``, ``fase``, ``driver``,
            ``custo_fixo_total`` ou ``custo_fixo_mensal``.
        duracao_semanas: duração total do projeto em semanas (>= 1).

    Returns:
        Dict com:
          - ``total_mob``: soma dos ``custo_fixo_total`` de fase=mobilizacao
          - ``total_operacao``: custo total de fase=operacao (mensal × meses)
          - ``total_demob``: soma dos ``custo_fixo_total`` de fase=desmobilizacao
          - ``semanal``: Dict[int, float] → custo por semana (0-indexed)
    """
    from concilium.domain.constants import SEMANAS_POR_MES as _SEM_MES

    total_mob = 0.0
    total_operacao = 0.0
    total_demob = 0.0

    # Semana última do projeto (0-indexed)
    semana_final = max(duracao_semanas - 1, 0)
    duracao_meses = duracao_semanas / _SEM_MES

    # semanal[s] acumula custo de todos os itens na semana s
    semanal: dict[int, float] = {s: 0.0 for s in range(duracao_semanas)}

    for item in mob_items:
        fase = item.get("fase")
        driver = item.get("driver", "")

        if fase is None:
            # Legado: item sem fase — sem modificação, backward compat
            continue

        if fase == "mobilizacao" and driver == "projeto":
            custo = float(item.get("custo_fixo_total", 0.0) or 0.0)
            total_mob += custo
            if duracao_semanas > 0:
                semanal[0] = round(semanal[0] + custo, 2)

        elif fase == "operacao" and driver == "mensal":
            custo_mensal = float(item.get("custo_fixo_mensal", 0.0) or 0.0)
            custo_total_op = custo_mensal * duracao_meses
            total_operacao += custo_total_op
            if duracao_semanas > 0:
                custo_por_semana = custo_total_op / duracao_semanas
                acumulado = 0.0
                for s in range(duracao_semanas):
                    if s < duracao_semanas - 1:
                        parcela = round(custo_por_semana, 2)
                    else:
                        # última semana recebe o resíduo para preservar conservação
                        parcela = round(custo_total_op - acumulado, 2)
                    semanal[s] = round(semanal[s] + parcela, 2)
                    acumulado += parcela

        elif fase == "desmobilizacao" and driver == "projeto":
            custo = float(item.get("custo_fixo_total", 0.0) or 0.0)
            total_demob += custo
            if duracao_semanas > 0:
                semanal[semana_final] = round(semanal[semana_final] + custo, 2)

    return {
        "total_mob": round(total_mob, 2),
        "total_operacao": round(total_operacao, 2),
        "total_demob": round(total_demob, 2),
        "semanal": semanal,
    }
