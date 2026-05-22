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

from concilium.domain.models.canonical import (
    CanonicalModel,
    IndirectoCostComponent,
)

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


def _bcfd_resolve_salario_base(preco: float, unidade: str) -> float:
    """Converts unit price to monthly salary base; fallback on error."""
    from concilium.domain.services.conversor_unidades import ConversorUnidades

    try:
        return ConversorUnidades.converter_preco(preco, unidade, "mes")
    except Exception:
        return preco


def _bcfd_apply_encargos(salario_base: float, atrib: dict) -> float:
    """Applies social charges based on categoria_sindical attribute."""
    from concilium.domain.constants import ENCARGOS_CLT, ENCARGOS_MENSALISTA

    cat_sind = (atrib.get("categoria_sindical") or "").lower()
    if cat_sind.startswith("pj"):
        return salario_base
    override_val = atrib.get("custo_com_encargos")
    if override_val and override_val > 0:
        return float(override_val)
    enc = ENCARGOS_CLT if cat_sind.startswith("horista") else ENCARGOS_MENSALISTA
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
