"""Skill 04 — Planejamento e BDI.

Calcula preço unitário (sem e com BDI) por item da EAP, decomposto em 4 categorias:
material, diesel, mão de obra, equipamentos (DEC-14: BDI por 4 categorias).

Lógica:
    Para cada item da EAP:
        cpu = lookup(catalogo, item.cpu_id)
        Para cada composicao_item da CPU:
            categoria = composicao_item.categoria_custo
            preco_unit_categoria[categoria] += coeficiente × insumo.preco_unitario
        Aplica BDI por categoria (do perfil)
        Calcula subtotal = preco_unit × quantitativo (sem e com BDI)

Inputs:
    bdi_aplicado (opcional): override dos BDIs do perfil
"""

from typing import Any

from concilium.models.canonical import (
    BdiCategorias,
    CanonicalModel,
    Planejamento,
    PrecoUnitarioCategoria,
    SubtotalCategorias,
    SubtotalSemBdiComBdi,
    ValidacaoItem,
)
from concilium.skills.escopo import SkillResult


def _build_lookups(catalogo: dict[str, Any]) -> tuple[dict[str, dict], dict[str, dict]]:
    cpus = {c["codigo"]: c for c in catalogo.get("cpus", [])}
    insumos = {i["codigo"]: i for i in catalogo.get("insumos", [])}
    return cpus, insumos


def _bdi_default_do_perfil(perfil: dict[str, Any]) -> dict[str, float]:
    """Extrai BDI default por categoria do perfil. Usa máximo da faixa."""
    faixas = perfil["formula_bdi"]["faixas_por_categoria"]
    return {
        "material": faixas["material"]["max"],
        "diesel": faixas["diesel"]["max"],
        "mao_obra": faixas["mao_obra"]["max"],
        "equipamentos": faixas["equipamentos"]["max"],
    }


def _validar_bdi_dentro_da_faixa(
    bdi: dict[str, float], perfil: dict[str, Any]
) -> list[str]:
    """Retorna lista de violações."""
    faixas = perfil["formula_bdi"]["faixas_por_categoria"]
    violacoes: list[str] = []
    for cat, valor in bdi.items():
        f = faixas[cat]
        if not (f["min"] <= valor <= f["max"]):
            violacoes.append(
                f"{cat}={valor*100:.1f}% fora da faixa [{f['min']*100:.1f}%, {f['max']*100:.1f}%]"
            )
    return violacoes


def run_planejamento_bdi(
    canonical_in: CanonicalModel,
    inputs: dict[str, Any],
    catalogo: dict[str, Any],
    perfil: dict[str, Any],
) -> SkillResult:
    """Popula seção 'planejamento' do canônico."""
    validacoes: list[ValidacaoItem] = []

    if not canonical_in.eap:
        validacoes.append(
            ValidacaoItem(codigo="VAL-PLAN-PRECONDICAO", status="ERRO", mensagem="EAP vazia")
        )
        return SkillResult(canonical_in, validacoes)

    cpu_lookup, insumo_lookup = _build_lookups(catalogo)

    # BDI: input override > perfil default
    bdi_aplicado = inputs.get("bdi_aplicado") or _bdi_default_do_perfil(perfil)

    # Validar BDI contra faixa do perfil
    violacoes_bdi = _validar_bdi_dentro_da_faixa(bdi_aplicado, perfil)
    if violacoes_bdi:
        validacoes.append(
            ValidacaoItem(
                codigo="VAL-POL-BDI",
                status="AVISO",
                mensagem=f"BDI fora da faixa do perfil: {'; '.join(violacoes_bdi)}",
            )
        )
    else:
        validacoes.append(ValidacaoItem(codigo="VAL-POL-BDI", status="OK"))

    plan_out: list[Planejamento] = []
    erros_eap: list[str] = []
    erros_insumo: set[str] = set()

    for item in canonical_in.eap:
        cpu = cpu_lookup.get(item.cpu_id)
        if cpu is None:
            erros_eap.append(item.cpu_id)
            continue

        # Decompõe preço unitário por categoria
        preco_cat = {"material": 0.0, "diesel": 0.0, "mao_obra": 0.0, "equipamentos": 0.0}
        for ci in cpu["composicao_itens"]:
            insumo = insumo_lookup.get(ci["insumo_id"])
            if insumo is None:
                erros_insumo.add(ci["insumo_id"])
                continue
            categoria = ci["categoria_custo"].lower()
            # Map "EQUIPAMENTO" → "equipamentos"
            if categoria == "equipamento":
                categoria = "equipamentos"
            if categoria not in preco_cat:
                continue
            contribuicao = ci["coeficiente"] * insumo["preco_unitario"]
            preco_cat[categoria] += contribuicao

        total_sem_bdi = sum(preco_cat.values())

        preco_unit_sem_bdi = PrecoUnitarioCategoria(
            material=round(preco_cat["material"], 4),
            diesel=round(preco_cat["diesel"], 4),
            mao_obra=round(preco_cat["mao_obra"], 4),
            equipamentos=round(preco_cat["equipamentos"], 4),
            total=round(total_sem_bdi, 4),
        )

        # Aplica BDI por categoria
        preco_cat_com_bdi = {
            cat: preco_cat[cat] * (1 + bdi_aplicado[cat]) for cat in preco_cat
        }
        total_com_bdi = sum(preco_cat_com_bdi.values())

        preco_unit_com_bdi = PrecoUnitarioCategoria(
            material=round(preco_cat_com_bdi["material"], 4),
            diesel=round(preco_cat_com_bdi["diesel"], 4),
            mao_obra=round(preco_cat_com_bdi["mao_obra"], 4),
            equipamentos=round(preco_cat_com_bdi["equipamentos"], 4),
            total=round(total_com_bdi, 4),
        )

        # Subtotais (preço × quantitativo)
        q = item.quantitativo
        subtotal_sem_bdi = SubtotalCategorias(
            material=round(preco_cat["material"] * q, 2),
            diesel=round(preco_cat["diesel"] * q, 2),
            mao_obra=round(preco_cat["mao_obra"] * q, 2),
            equipamentos=round(preco_cat["equipamentos"] * q, 2),
            total=round(total_sem_bdi * q, 2),
        )
        subtotal_com_bdi = SubtotalCategorias(
            material=round(preco_cat_com_bdi["material"] * q, 2),
            diesel=round(preco_cat_com_bdi["diesel"] * q, 2),
            mao_obra=round(preco_cat_com_bdi["mao_obra"] * q, 2),
            equipamentos=round(preco_cat_com_bdi["equipamentos"] * q, 2),
            total=round(total_com_bdi * q, 2),
        )

        plan_out.append(
            Planejamento(
                item_id=item.item_id,
                cpu_id=item.cpu_id,
                quantitativo=q,
                preco_unitario=preco_unit_sem_bdi,
                bdi=BdiCategorias(**bdi_aplicado),
                preco_unitario_com_bdi=preco_unit_com_bdi,
                subtotal=SubtotalSemBdiComBdi(sem_bdi=subtotal_sem_bdi, com_bdi=subtotal_com_bdi),
            )
        )

    if erros_eap:
        validacoes.append(
            ValidacaoItem(
                codigo="VAL-EAP-01",
                status="ERRO",
                mensagem=f"CPUs não encontradas: {', '.join(erros_eap)}",
            )
        )

    if erros_insumo:
        validacoes.append(
            ValidacaoItem(
                codigo="VAL-PLAN-INSUMO",
                status="ERRO",
                mensagem=f"Insumos da CPU não encontrados no catálogo: {', '.join(erros_insumo)}",
            )
        )

    novo = canonical_in.model_copy(update={"planejamento": plan_out})
    return SkillResult(novo, validacoes)
