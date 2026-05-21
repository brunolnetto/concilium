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
from concilium.domain.constants import SEMANAS_POR_MES as _SEMANAS_POR_MES  # ADR-056 §T3
from concilium.domain.models.bdi import DEFAULT_BDI_TABELA, TabelaBdi
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
from concilium.domain.models.decision_variables import DecisionVariables
from concilium.infrastructure.repositories.insumo import RepositorioInsumo

# Fator padrão: 1 mês = 4.33 semanas
# _SEMANAS_POR_MES agora importada de domain/constants.py (era 4.33, corrigido para 4.3482)


def _semanas_projeto(inicio, fim) -> int:
    """Conta semanas entre datas (inclusive)."""
    return max(1, ((fim - inicio).days // 7) + 1)


def _meses_entre(inicio, fim) -> int:
    """Conta meses inteiros entre datas (inclusivo). Retrocompatível."""
    return (fim.year - inicio.year) * 12 + (fim.month - inicio.month) + 1


def _composicao_default_por_categoria(categoria: str) -> dict:
    """Composição default mínima por categoria (heurística Fase 1A)."""
    if categoria == "ADM":
        return {
            "mao_de_obra": {
                "nome": "MÃO DE OBRA ADM",
                "custo_fixo_mensal": 12500.0,
                "itens": [
                    {"funcao": "Coordenador", "quantidade": 1, "custo_mensal": 12500.0},
                ],
            },
            "verbas": {
                "nome": "VERBAS ADM",
                "custo_fixo_mensal": 3500.0,
                "itens": [
                    {"descricao": "Alojamento", "valor_mensal": 3500.0},
                ],
            },
        }
    if categoria == "TOP":
        return {
            "mao_de_obra": {
                "nome": "MÃO DE OBRA TOP",
                "custo_fixo_mensal": 9216.0,
                "itens": [
                    {"funcao": "Topógrafo", "quantidade": 1, "custo_mensal": 9216.0},
                ],
            },
        }
    if categoria == "LAB":
        return {
            "verbas": {
                "nome": "VERBAS LAB",
                "custo_fixo_mensal": 4000.0,
                "itens": [
                    {"descricao": "Ensaios laboratoriais", "valor_mensal": 4000.0},
                ],
            },
        }
    if categoria == "QSMS":
        return {
            "verbas": {
                "nome": "VERBAS QSMS",
                "custo_fixo_mensal": 3000.0,
                "itens": [
                    {"descricao": "EPIs e treinamentos", "valor_mensal": 3000.0},
                ],
            },
        }
    return {}


def _da_hc_direto(codigo: str, regra: dict, canonical) -> dict:
    """Driver hc_direto: proporcional ao headcount direto."""
    num_diretos = sum(sum(f.num_pessoas for f in eq.funcoes) for eq in canonical.equipes_diretas)
    proporcao = regra.get("proporcao", 100)
    qty = max(1, round(num_diretos / proporcao))
    return {
        "mao_de_obra": {
            "nome": f"Equipe {codigo} (Proporcional HC)",
            "itens": [{"funcao_id": regra["funcao_lider"], "quantidade": qty}],
        }
    }


def _da_frentes_ativas(codigo: str, regra: dict, canonical) -> dict:
    """Driver frentes_ativas: proporcional ao n\u00famero de equipes diretas."""
    num_frentes = len(canonical.equipes_diretas)
    proporcao = regra.get("proporcao", 3)
    qty = max(1, round(num_frentes / proporcao))
    itens = [{"funcao_id": regra["funcao_lider"], "quantidade": qty}]
    for apoio in regra.get("itens_apoio", []):
        itens.append({"funcao_id": apoio["funcao_id"], "quantidade": apoio["quantidade"] * qty})
    return {"mao_de_obra": {"nome": f"Equipe {codigo} (Proporcional Frentes)", "itens": itens}}


def _da_magnitude_financeira(codigo: str, regra: dict, canonical, catalogo: dict) -> dict | None:
    """Driver magnitude_financeira: escolhe template conforme faixa de valor de venda."""
    venda_sem_bdi = sum(p.subtotal.sem_bdi.total for p in (canonical.planejamento or []))
    tpl_id = None
    for step in regra.get("steps", []):
        if "ate_valor" in step and venda_sem_bdi <= step["ate_valor"]:
            tpl_id = step["equipe_base"]
            break
        if "acima_de" in step and venda_sem_bdi > step["acima_de"]:
            tpl_id = step["equipe_base"]
            break
    if not tpl_id:
        return None
    estruturas = catalogo.get("estruturas_indiretas", [])
    template = next((t for t in estruturas if t["codigo"] == tpl_id), None)
    if template is None:
        return None
    return {
        "mao_de_obra": {"nome": f"ADM ({tpl_id})", "itens": template.get("mao_de_obra", [])},
        "equipamentos": {"nome": "Equipamentos ADM", "itens": template.get("equipamentos", [])},
        "verbas": {"nome": "Verbas ADM", "itens": template.get("verbas", [])},
    }


def _da_volume_mensal(codigo: str, regra: dict, canonical) -> dict:
    """Driver volume_mensal: proporcional ao volume mensal m\u00e9dio."""
    volume_total = sum(p.quantitativo for p in (canonical.planejamento or []))
    prazo_meses = max(1, ((canonical.projeto.data_termino - canonical.projeto.data_inicio).days // 30))
    vol_mensal = volume_total / prazo_meses
    proporcao = regra.get("proporcao", 50000)
    qty = max(1, round(vol_mensal / proporcao))
    return {
        "verbas": {
            "nome": f"Verba {codigo} (Proporcional Volume)",
            "custo_fixo_mensal": qty * 5000.0,
            "itens": [{"descricao": f"Servi\u00e7os {codigo}", "valor_mensal": 5000.0, "quantidade": qty}],
        }
    }


def _dimensionar_automatico(codigo: str, regra: dict, canonical: CanonicalModel, catalogo: dict | None = None) -> dict:
    """Aplica regras de proporcionalidade para dimensionar indiretos (ADR Autonomia)."""
    driver = regra.get("driver")
    if driver == "hc_direto":
        return _da_hc_direto(codigo, regra, canonical)
    if driver == "frentes_ativas":
        return _da_frentes_ativas(codigo, regra, canonical)
    if driver == "magnitude_financeira" and catalogo:
        result = _da_magnitude_financeira(codigo, regra, canonical, catalogo)
        if result is not None:
            return result
    if driver == "volume_mensal":
        return _da_volume_mensal(codigo, regra, canonical)
    return _composicao_default_por_categoria(codigo)


def _parse_component(comp_dict: dict | None) -> IndirectoCostComponent | None:
    if not comp_dict:
        return None

    itens = comp_dict.get("itens", [])
    # Recalcula custo_fixo_mensal se não fornecido, somando os itens
    custo_fixo_mensal = float(comp_dict.get("custo_fixo_mensal", 0.0))
    if custo_fixo_mensal == 0.0 and itens:
        for f in itens:
            q = float(f.get("quantidade", f.get("qtd", f.get("num_pessoas", 1.0))))
            c = float(f.get("custo_mensal", f.get("salario_base", f.get("valor_mensal", 0.0))))
            custo_fixo_mensal += q * c

    return IndirectoCostComponent(
        nome=comp_dict.get("nome", ""),
        custo_fixo_mensal=custo_fixo_mensal,
        itens=itens,
    )


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

    # Enriquecimento via catálogo para MO e Equipamentos se faltar custo_mensal
    if repo and "mao_de_obra" in comp_dict:
        mo_dict = comp_dict["mao_de_obra"]
        for f in mo_dict.get("itens", []):
            if "custo_mensal" not in f and "funcao_id" in f:
                insumo = repo.obter_insumo(f["funcao_id"])
                if insumo:
                    from concilium.domain.services.conversor_unidades import ConversorUnidades

                    preco_resolvido, _fonte = repo.resolver_preco(
                        f["funcao_id"],
                        jurisdicao_id=jurisdicao_id,
                        overrides=overrides,
                        data_referencia=data_base,
                    )
                    preco = float(preco_resolvido or insumo.get("preco_unitario", 0.0))
                    unidade = insumo.get("unidade", "mes")

                    # Converte preço unitário para base mensal
                    try:
                        salario_base = ConversorUnidades.converter_preco(preco, unidade, "mes")
                    except Exception:
                        salario_base = preco

                    # Aplica encargos conforme categoria
                    atrib = insumo.get("atributos_especificos", {}) or {}
                    cat_sind = (atrib.get("categoria_sindical") or "").lower()

                    if cat_sind.startswith("pj"):
                        custo_mensal = salario_base
                    else:
                        # Se houver custo_com_encargos no catálogo, usa ele como override
                        override = atrib.get("custo_com_encargos")
                        if override and override > 0:
                            custo_mensal = override
                        else:
                            # enc_horista/mensalista devem ser passados ou obtidos globalmente
                            # Para simplificar mantemos os fallbacks de Skill 03 se não injetados
                            from concilium.domain.constants import ENCARGOS_CLT, ENCARGOS_MENSALISTA

                            enc = ENCARGOS_CLT if cat_sind.startswith("horista") else ENCARGOS_MENSALISTA
                            custo_mensal = salario_base * (1 + enc)

                    f["custo_mensal"] = round(custo_mensal, 2)
                    if "descricao" not in f:
                        f["descricao"] = insumo.get("descricao", f["funcao_id"])

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
) -> list[IndiretoSemanal]:
    """Gera breakdown semanal para uma categoria (ADR-009 §D2)."""
    result: list[IndiretoSemanal] = []
    if categoria.driver == "permanencia":
        mo_sem = (categoria.mao_de_obra.custo_fixo_mensal if categoria.mao_de_obra else 0.0) / _SEMANAS_POR_MES
        eq_sem = (categoria.equipamentos.custo_fixo_mensal if categoria.equipamentos else 0.0) / _SEMANAS_POR_MES
        vb_sem = (categoria.verbas.custo_fixo_mensal if categoria.verbas else 0.0) / _SEMANAS_POR_MES
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
    custo_pessoa_mes = dados_mob.get("custo_pessoa_mes", 1850)
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
    indir = Indireto(
        categoria="MOB", descricao=descricao, mobilizacoes=mobs, permanencia_meses=float(prazo_meses), custo_total=custo
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
) -> tuple[float, IndirectoCategoria]:
    custo = cat_obj.custo_total_para_semanas(n_semanas)
    if dv4_policy and dv4_policy in policy_scale:
        scale = policy_scale[dv4_policy]
        custo = round(custo * scale, 2)
        cat_obj = cat_obj.model_copy(update={"custo_fixo_mensal": round(cat_obj.custo_fixo_mensal * scale, 2)})
    return custo, cat_obj


def _build_indireto_from_cat_obj(
    codigo: str,
    descricao: str,
    cat_obj: IndirectoCategoria,
    custo: float,
    n_semanas: int,
) -> Indireto:
    return Indireto(
        categoria=codigo,  # type: ignore[arg-type]
        descricao=descricao,
        funcoes=[item for item in (cat_obj.mao_de_obra.itens if cat_obj.mao_de_obra else [])],
        equipamentos=[item for item in (cat_obj.equipamentos.itens if cat_obj.equipamentos else [])],
        verbas_mensais=[item for item in (cat_obj.verbas.itens if cat_obj.verbas else [])],
        permanencia_meses=round(n_semanas / _SEMANAS_POR_MES, 2),
        custo_total=custo,
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
                    f"Razão indireto/direto {razao * 100:.1f}% fora da faixa [{razao_alvo['min'] * 100:.1f}%, {razao_alvo['max'] * 100:.1f}%]"
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
    tabela_bdi: TabelaBdi = DEFAULT_BDI_TABELA
    if tabela_bdi_raw is not None:
        try:
            tabela_bdi = (
                TabelaBdi.model_validate(tabela_bdi_raw) if isinstance(tabela_bdi_raw, dict) else tabela_bdi_raw
            )
        except Exception as e:
            validacoes.append(
                ValidacaoItem(
                    codigo="VAL-INDIR-BDI-PARSE",
                    status="AVISO",
                    mensagem=f"Falha ao parsear inputs.tabela_bdi: {e}. Usando DEFAULT_BDI_TABELA.",
                )
            )
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
        except Exception as e:
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
                    f"BDI-INDIRETO {bdi_indir * 100:.2f}% aplicado a {len(indiretos_com_bdi_out)} categorias: sem_bdi=R${custo_total_sem:,.2f} -> com_bdi=R${custo_total_com:,.2f}"
                ),
            )
        )
    return indiretos_com_bdi_out


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
                    "MOB omitido: skill 03-equipes-diretas está em pipeline_blocked_from. Custo de mobilização não calculado para evitar MOB=R$0 silencioso (ADR-022 D5). Corrija skill 03 e re-execute 07-custos-indiretos."
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

    n_semanas = _semanas_projeto(canonical_in.projeto.data_inicio, canonical_in.projeto.data_termino)
    prazo_meses = _meses_entre(canonical_in.projeto.data_inicio, canonical_in.projeto.data_termino)
    num_pessoas_direta = _count_pessoas_diretas(canonical_in)

    composicoes_input = inputs.get("composicoes_indireto", {})
    dados_mob = inputs.get("dados_mobilizacao", {})
    categorias_config_raw: list[dict] = inputs.get("categorias_config", [])
    dv4_policy = _extract_dv4_policy(inputs)
    policy_scale = {"lean": 0.85, "standard": 1.0, "robust": 1.15}

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
            custo, cat_obj = _apply_dv4_scale_to_categoria(cat_obj, dv4_policy, policy_scale, n_semanas)
            indiretos_out.append(_build_indireto_from_cat_obj(codigo, cat["descricao"], cat_obj, custo, n_semanas))
            indiretos_semanal_out.extend(_build_semanal_breakdown(cat_obj, n_semanas))

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
