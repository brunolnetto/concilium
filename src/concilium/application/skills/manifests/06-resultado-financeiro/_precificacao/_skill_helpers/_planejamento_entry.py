"""Skill 06 (_precificacao) — Planejamento e BDI.

Construção da entrada de Planejamento e overrides antecipados.
"""

from __future__ import annotations

from typing import Any

from concilium.domain.models.canonical import (
    BdiCategorias,
    Planejamento,
    PrecoUnitarioCategoria,
    SubtotalCategorias,
    SubtotalSemBdiComBdi,
    ValidacaoItem,
)


def _build_planejamento_entry(
    item: Any,
    preco_cat: dict,
    preco_cat_com_bdi: dict,
    bdi_aplicado: dict,
    precificacao_via_fallback_composicao: bool = False,
    produtividade_catalogo: float = 0.0,
    beta_praticabilidade: float = 1.0,
) -> Planejamento:
    q = item.quantitativo
    total_sem_bdi = sum(preco_cat.values())
    total_com_bdi = sum(preco_cat_com_bdi.values())
    return Planejamento(
        item_id=item.item_id,
        cpu_id=item.cpu_id,
        quantitativo=q,
        precificacao_via_fallback_composicao=precificacao_via_fallback_composicao,
        produtividade_catalogo=produtividade_catalogo,
        beta_praticabilidade=beta_praticabilidade,
        preco_unitario=PrecoUnitarioCategoria(
            material=round(preco_cat["material"], 4),
            diesel=round(preco_cat["diesel"], 4),
            mao_obra=round(preco_cat["mao_obra"], 4),
            equipamentos=round(preco_cat["equipamentos"], 4),
            total=round(total_sem_bdi, 4),
        ),
        bdi=BdiCategorias(**bdi_aplicado),
        preco_unitario_com_bdi=PrecoUnitarioCategoria(
            material=round(preco_cat_com_bdi["material"], 4),
            diesel=round(preco_cat_com_bdi["diesel"], 4),
            mao_obra=round(preco_cat_com_bdi["mao_obra"], 4),
            equipamentos=round(preco_cat_com_bdi["equipamentos"], 4),
            total=round(total_com_bdi, 4),
        ),
        subtotal=SubtotalSemBdiComBdi(
            sem_bdi=SubtotalCategorias(
                material=round(preco_cat["material"] * q, 2),
                diesel=round(preco_cat["diesel"] * q, 2),
                mao_obra=round(preco_cat["mao_obra"] * q, 2),
                equipamentos=round(preco_cat["equipamentos"] * q, 2),
                total=round(total_sem_bdi * q, 2),
            ),
            com_bdi=SubtotalCategorias(
                material=round(preco_cat_com_bdi["material"] * q, 2),
                diesel=round(preco_cat_com_bdi["diesel"] * q, 2),
                mao_obra=round(preco_cat_com_bdi["mao_obra"] * q, 2),
                equipamentos=round(preco_cat_com_bdi["equipamentos"] * q, 2),
                total=round(total_com_bdi * q, 2),
            ),
        ),
    )


def _try_early_override(
    item: Any,
    planejamento_item_overrides: Any,
    bdi_aplicado: dict,
    validacoes: list,
) -> Planejamento | None:
    _item_ovr_early = (
        planejamento_item_overrides.get(item.item_id, {}) if isinstance(planejamento_item_overrides, dict) else {}
    )
    _pu_early = _item_ovr_early.get("preco_unitario") if isinstance(_item_ovr_early, dict) else None
    if not isinstance(_pu_early, dict):
        return None
    if not any(float(v or 0) != 0 for v in _pu_early.values()):
        return None
    _preco_early = {
        "material": float(_pu_early.get("material", 0.0)),
        "diesel": float(_pu_early.get("diesel", 0.0)),
        "mao_obra": float(_pu_early.get("mao_obra", 0.0)),
        "equipamentos": float(_pu_early.get("equipamentos", 0.0)),
    }
    _com_bdi_early = {cat: _preco_early[cat] * (1 + bdi_aplicado[cat]) for cat in _preco_early}
    validacoes.append(
        ValidacaoItem(
            codigo="VAL-PLAN-OVR-ITEM",
            status="INFO",
            mensagem=f"Item '{item.item_id}': preço unitário sem BDI calibrado por referência.",
        )
    )
    return _build_planejamento_entry(item, _preco_early, _com_bdi_early, bdi_aplicado)


def _apply_equip_decomp(
    ci: Any, insumo: dict, contribuicao: float, preco_cat: dict, equip_sem_decomp_item: set
) -> None:
    decomp_raw = (insumo.get("atributos_especificos") or {}).get("decomposicao_equip")
    if decomp_raw and decomp_raw.get("custo_hora_total", 0.0) > 0:
        total_h = decomp_raw["custo_hora_total"]
        frac_mo = (decomp_raw.get("custo_mao_obra_h", 0.0) + decomp_raw.get("custo_capital_h", 0.0)) / total_h
        frac_die = decomp_raw.get("custo_diesel_h", 0.0) / total_h
        frac_mat = decomp_raw.get("custo_material_h", 0.0) / total_h
        preco_cat["mao_obra"] += contribuicao * frac_mo
        preco_cat["diesel"] += contribuicao * frac_die
        preco_cat["material"] += contribuicao * frac_mat
        preco_cat["equipamentos"] += contribuicao * max(0.0, 1.0 - frac_mo - frac_die - frac_mat)
    else:
        equip_sem_decomp_item.add(ci.insumo_id)
        preco_cat["equipamentos"] += contribuicao


