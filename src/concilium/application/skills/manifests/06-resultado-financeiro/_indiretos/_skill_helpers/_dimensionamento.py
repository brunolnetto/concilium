"""Skill 06 (_indiretos) — Indiretos (ADR-009, ADR-023 §D4).

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

import math
from typing import Any

from concilium.domain.constants import SEMANAS_POR_MES as _SEMANAS_POR_MES
from concilium.domain.models.canonical import (
    CanonicalModel,
    EquipeDireta,
    IndirectoCostComponent,
)

# Fator padrão: 1 mês = 4.33 semanas
# _SEMANAS_POR_MES agora importada de domain/constants.py (era 4.33, corrigido para 4.3482)

# ADR-166 D2: dias/mês para amortizar custo de RH (EPI/treinamento/exame) por vida_util_dias.
_DIAS_POR_MES = _SEMANAS_POR_MES * 7


def _semanas_projeto(inicio, fim) -> int:
    """Conta semanas entre datas (inclusive)."""
    return max(1, ((fim - inicio).days // 7) + 1)


def _meses_entre(inicio, fim) -> int:
    """Conta meses inteiros entre datas (inclusivo). Retrocompatível."""
    return (fim.year - inicio.year) * 12 + (fim.month - inicio.month) + 1


def _headcount_direto(equipes_diretas: list | None) -> int:
    """Soma num_pessoas de todas as funções de todas as equipes diretas."""
    return sum(f.num_pessoas for eq in (equipes_diretas or []) for f in (getattr(eq, "funcoes", None) or []))


def _custo_alojamento_bottom_up(
    headcount: int,
    quartos_por_casa: int = 3,
    pessoas_por_quarto: int = 2,
    valor_aluguel_mensal: float = 4000.0,
) -> dict | None:
    """ADR-168: custo de "Alojamento" a partir do número de casas necessárias
    para o headcount direto — cada casa comporta `quartos_por_casa ×
    pessoas_por_quarto` pessoas (default 3×2=6), ao valor de aluguel informado
    (default R$4.000/mês/casa). Ambos os parâmetros são configuráveis por
    categoria via `cat["alojamento"]` (ADR-168 D2). Retorna `None` se
    `headcount<=0` ou capacidade por casa inválida — o chamador cai então para
    a verba lump default (degradação segura, mesmo padrão do QSMS/MOB ADR-166).
    """
    if headcount <= 0:
        return None
    capacidade_por_casa = quartos_por_casa * pessoas_por_quarto
    if capacidade_por_casa <= 0:
        return None
    num_casas = math.ceil(headcount / capacidade_por_casa)
    custo_total = round(num_casas * valor_aluguel_mensal, 2)
    return {
        "nome": "VERBAS ADM",
        "custo_fixo_mensal": custo_total,
        "itens": [
            {"descricao": "Alojamento", "quantidade": num_casas, "valor_mensal": valor_aluguel_mensal},
        ],
    }


def _composicao_default_por_categoria(
    categoria: str,
    equipes_diretas: list | None = None,
    alojamento_config: dict | None = None,
) -> dict:
    """Composição default mínima por categoria (heurística Fase 1A).

    ADR-167: ADM ("Coordenador" -> `P0092`) e TOP ("Topógrafo" -> `P0057`) ganham
    `funcao_id` real — `_bcfd_enrich_mo_itens` (chamada por `_build_categoria_from_dict`
    para qualquer comp_dict, inclusive este fallback) preenche `custo_mensal` com o
    preço real do catálogo quando o código existe no repo. Sem `custo_fixo_mensal`
    fixo no componente `mao_de_obra` (removido de propósito): `_parse_component`
    recalcula a partir dos itens, usando `custo_mensal` (enriquecido) se presente ou
    `valor_mensal` (o número antigo, como fallback) senão — mesma degradação segura
    dos bottom-up de QSMS/MOB (ADR-166).

    ADR-168: a verba "Alojamento" de ADM usa `_custo_alojamento_bottom_up` quando
    `equipes_diretas` tem headcount — cai para o lump de R$3.500/mês senão.
    """
    if categoria == "ADM":
        cfg = alojamento_config or {}
        verbas = None
        if equipes_diretas:
            verbas = _custo_alojamento_bottom_up(
                _headcount_direto(equipes_diretas),
                quartos_por_casa=cfg.get("quartos_por_casa", 3),
                pessoas_por_quarto=cfg.get("pessoas_por_quarto", 2),
                valor_aluguel_mensal=cfg.get("valor_aluguel_mensal", 4000.0),
            )
        if verbas is None:
            verbas = {
                "nome": "VERBAS ADM",
                "custo_fixo_mensal": 3500.0,
                "itens": [
                    {"descricao": "Alojamento", "valor_mensal": 3500.0},
                ],
            }
        return {
            "mao_de_obra": {
                "nome": "MÃO DE OBRA ADM",
                "itens": [
                    {"funcao_id": "P0092", "descricao": "Coordenador", "quantidade": 1, "valor_mensal": 12500.0},
                ],
            },
            "verbas": verbas,
        }
    if categoria == "TOP":
        return {
            "mao_de_obra": {
                "nome": "MÃO DE OBRA TOP",
                "itens": [
                    {"funcao_id": "P0057", "descricao": "Topógrafo", "quantidade": 1, "valor_mensal": 9216.0},
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


def _rh_insumos_por_tipo(catalogo: dict | None) -> tuple[list[dict], list[dict], list[dict]]:
    """ADR-166 D2: separa insumos EPI (MATERIAL prefixo `EPI-`)/TREINAMENTO/EXAME
    ativos do catálogo — a base de dado para a composição QSMS bottom-up."""
    if not catalogo:
        return [], [], []
    epis: list[dict] = []
    treinamentos: list[dict] = []
    exames: list[dict] = []
    for ins in catalogo.get("insumos", []):
        if ins.get("status") == "descontinuado":
            continue
        tipo = ins.get("tipo")
        codigo = ins.get("codigo", "")
        if tipo == "MATERIAL" and codigo.startswith("EPI-"):
            epis.append(ins)
        elif tipo == "TREINAMENTO":
            treinamentos.append(ins)
        elif tipo == "EXAME":
            exames.append(ins)
    return epis, treinamentos, exames


def _custo_mensal_rh_por_funcao(funcao_id: str, *grupos_insumos: list[dict]) -> float:
    """ADR-166 D2: soma o custo mensal amortizado (preço ÷ vida_util_dias × dias/mês) dos
    itens aplicáveis a `funcao_id` — comuns (`funcoes_aplicaveis` None) + específicos
    (`funcao_id` presente na lista)."""
    total = 0.0
    for grupo in grupos_insumos:
        for ins in grupo:
            atributos = ins.get("atributos_especificos") or {}
            aplicaveis = atributos.get("funcoes_aplicaveis")
            if aplicaveis is not None and funcao_id not in aplicaveis:
                continue
            vida_util = atributos.get("vida_util_dias")
            if not vida_util:
                continue
            total += ins.get("preco_unitario", 0.0) / vida_util * _DIAS_POR_MES
    return total


def _composicao_qsms_bottom_up(equipes_diretas: list[EquipeDireta], catalogo: dict | None) -> dict | None:
    """ADR-166 D2: composição QSMS bottom-up por função (EPI+treinamento+exame),
    substituindo a verba lump default (`_composicao_default_por_categoria`) quando o
    catálogo tiver itens RH cadastrados (ADR-165). Retorna `None` se não houver
    itens RH no catálogo, nenhum headcount direto, ou nenhuma função com custo
    aplicável — o chamador cai então para o fallback lump (degradação segura)."""
    epis, treinamentos, exames = _rh_insumos_por_tipo(catalogo)
    if not (epis or treinamentos or exames):
        return None

    headcount: dict[str, int] = {}
    for eq in equipes_diretas:
        for f in eq.funcoes:
            headcount[f.funcao_id] = headcount.get(f.funcao_id, 0) + f.num_pessoas
    if not headcount:
        return None

    itens: list[dict[str, Any]] = []
    total_mensal = 0.0
    for funcao_id in sorted(headcount):
        num_pessoas = headcount[funcao_id]
        custo_unitario = _custo_mensal_rh_por_funcao(funcao_id, epis, treinamentos, exames)
        if custo_unitario <= 0:
            continue
        custo_funcao = round(custo_unitario * num_pessoas, 2)
        total_mensal += custo_funcao
        itens.append(
            {
                "descricao": f"EPI/treinamento/exame — {funcao_id}",
                "funcao_id": funcao_id,
                "quantidade": num_pessoas,
                "valor_mensal": custo_funcao,
            }
        )
    if not itens:
        return None

    return {
        "verbas": {
            "nome": "QSMS — EPI/Treinamento/Exame (bottom-up ADR-166)",
            "custo_fixo_mensal": round(total_mensal, 2),
            "itens": itens,
        }
    }


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


def _dmf_find_template_id(regra: dict, venda_sem_bdi: float) -> str | None:
    """Selects template id from steps based on venda_sem_bdi."""
    for step in regra.get("steps", []):
        if "ate_valor" in step and venda_sem_bdi <= step["ate_valor"]:
            return step["equipe_base"]
        if "acima_de" in step and venda_sem_bdi > step["acima_de"]:
            return step["equipe_base"]
    return None


def _da_magnitude_financeira(codigo: str, regra: dict, canonical, catalogo: dict) -> dict | None:
    """Driver magnitude_financeira: escolhe template conforme faixa de valor de venda."""
    venda_sem_bdi = sum(p.subtotal.sem_bdi.total for p in canonical.planejamento)
    tpl_id = _dmf_find_template_id(regra, venda_sem_bdi)
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
    return _composicao_default_por_categoria(codigo, canonical.equipes_diretas, regra.get("alojamento"))


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


def _bcfd_resolve_salario_base(preco: float, unidade: str) -> float:
    """Converts unit price to monthly salary base; fallback on error."""
    from concilium.domain.services.conversor_unidades import ConversorUnidades

    try:
        return ConversorUnidades.converter_preco(preco, unidade, "mes")
    except Exception:
        return preco


def _bcfd_apply_encargos(salario_base: float, atrib: dict) -> float:
    """Aplica encargos sociais sobre salário-base conforme categoria_sindical."""
    from concilium.domain.services.financial.encargo_resolver import resolver_encargo

    cat_sind = (atrib.get("categoria_sindical") or "").lower()
    if cat_sind.startswith("pj"):
        return salario_base
    override_val = atrib.get("custo_com_encargos")
    if override_val and override_val > 0:
        return float(override_val)
    enc = resolver_encargo(atrib)
    return salario_base * (1 + enc)


def _bcfd_enrich_mo_item(
    f: dict,
    repo,
    jurisdicao_id: str | None,
    overrides: dict | None,
    data_base,
) -> None:
    """Enriches a single MO item dict with custo_mensal from catalog (in-place)."""
    insumo = repo.obter_insumo(f["funcao_id"])
    if not insumo:
        return
    preco_resolvido, _fonte = repo.resolver_preco(
        f["funcao_id"],
        jurisdicao_id=jurisdicao_id,
        overrides=overrides,
        data_referencia=data_base,
    )
    preco = float(preco_resolvido or insumo.get("preco_unitario", 0.0))
    salario_base = _bcfd_resolve_salario_base(preco, insumo.get("unidade", "mes"))
    atrib = insumo.get("atributos_especificos", {}) or {}
    custo_mensal = _bcfd_apply_encargos(salario_base, atrib)
    f["custo_mensal"] = round(custo_mensal, 2)
    if "descricao" not in f:
        f["descricao"] = insumo.get("descricao", f["funcao_id"])


def _bcfd_enrich_mo_itens(
    comp_dict: dict,
    repo,
    jurisdicao_id: str | None,
    overrides: dict | None,
    data_base,
) -> None:
    """Enriches all MO items in comp_dict that lack custo_mensal (in-place)."""
    if not (repo and "mao_de_obra" in comp_dict):
        return
    mo_dict = comp_dict["mao_de_obra"]
    for f in mo_dict.get("itens", []):
        if "custo_mensal" not in f and "funcao_id" in f:
            _bcfd_enrich_mo_item(f, repo, jurisdicao_id, overrides, data_base)
