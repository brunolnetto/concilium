"""Skill 04 — Planejamento e BDI.

Validações de encargos, cobertura, e aplicação de overrides sem/com BDI.
"""

from __future__ import annotations

from typing import Any

from concilium.domain.models.canonical import (
    CanonicalModel,
    ValidacaoItem,
)


def _validate_encargos_separacao(
    cpu_codigo: str,
    cpu: dict,
    insumo_lookup: dict,
    validacoes: list,
) -> None:
    """NEP-031 L5: valida separação entre encargos trabalhistas (α) e BDI de MO.

    Arquitetura correta (dois mecanismos complementares sem sobreposição):
      α (skill-05): converte salário mensal em custo real do trabalhador para a empresa
                    (INSS, FGTS, férias, 13°, SESI, SENAI, etc.)
                    Fórmula: custo_unit = salario × (1 + α)
                    Valores: α_CLT ≈ 1.777, α_mensalista ≈ 1.060, α_PJ ≈ 0.06

      BDI_MO (skill-06): markup do serviço sobre o custo direto de MO
                         (administração central, seguros, risco, lucro, tributos)
                         Fórmula: preco_venda = custo_direto × (1 + BDI_MO)

    RISCO de dupla contagem: se um insumo de MO em composicao_itens tem
    preco_unitario já incluindo encargos (ex: R$/h "all-in" de prestador),
    e o mesmo insumo é processado com BDI_MO pelo skill-06 E também pelo
    skill-05 com α → o custo da mão de obra seria contabilizado duas vezes.

    Heurística de detecção: insumo em composicao_itens com categoria_custo=MAO_OBRA
    e preco_unitario > limiar de salário típico + encargos CLT sugere que encargos
    já estão embutidos (limiar: R$100/h → ~R$16.000/mês para 160h mensais).
    """
    _LIMIAR_PU_MO_H = 100.0  # R$/h — acima disso, encargos provavelmente já incluídos
    for ci in cpu.get("composicao_itens") or []:
        cat = (ci.get("categoria_custo") or "").upper()
        if cat not in {"MAO_OBRA", "MO", "MAO DE OBRA", "MÃO_OBRA"}:
            continue
        iid = ci.get("insumo_id", "")
        ins = insumo_lookup.get(iid)
        if ins is None:
            continue
        preco = float(ins.get("preco_unitario", 0.0) or 0.0)
        unidade = (ins.get("unidade") or "").lower()
        if unidade == "h" and preco > _LIMIAR_PU_MO_H:
            validacoes.append(
                ValidacaoItem(
                    codigo="VAL-PLAN-ENCARGOS-DUPLA",
                    status="AVISO",
                    mensagem=(
                        f"CPU '{cpu_codigo}': insumo '{iid}' tem categoria_custo=MAO_OBRA "
                        f"e preco_unitario={preco:.2f} R$/h (> {_LIMIAR_PU_MO_H} R$/h). "
                        "Possível inclusão de encargos no preço unitário — verifique se "
                        "alpha (encargos trabalhistas de skill-05) não será aplicado em duplicata. "
                        "Se o preço já inclui encargos, defina atributos_especificos.custo_com_encargos "
                        "no insumo para evitar dupla contagem."
                    ),
                )
            )


def _apply_sem_bdi_override(item_id: str, item_override: Any, preco_cat: dict, validacoes: list) -> None:
    override_sem = item_override.get("preco_unitario") if isinstance(item_override, dict) else None
    if not isinstance(override_sem, dict):
        return
    for cat in ("material", "diesel", "mao_obra", "equipamentos"):
        if cat in override_sem:
            try:
                preco_cat[cat] = float(override_sem[cat])
            except Exception:
                pass
    validacoes.append(
        ValidacaoItem(
            codigo="VAL-PLAN-OVR-ITEM",
            status="INFO",
            mensagem=f"Item '{item_id}': preço unitário sem BDI calibrado por referência.",
        )
    )


def _apply_com_bdi_override(
    item_id: str, item_override: Any, preco_cat: dict, bdi_aplicado: dict, validacoes: list
) -> dict:
    override_com = item_override.get("preco_unitario_com_bdi") if isinstance(item_override, dict) else None
    if isinstance(override_com, dict):
        preco_cat_com_bdi = {
            "material": float(override_com.get("material", preco_cat["material"] * (1 + bdi_aplicado["material"]))),
            "diesel": float(override_com.get("diesel", preco_cat["diesel"] * (1 + bdi_aplicado["diesel"]))),
            "mao_obra": float(override_com.get("mao_obra", preco_cat["mao_obra"] * (1 + bdi_aplicado["mao_obra"]))),
            "equipamentos": float(
                override_com.get("equipamentos", preco_cat["equipamentos"] * (1 + bdi_aplicado["equipamentos"]))
            ),
        }
        validacoes.append(
            ValidacaoItem(
                codigo="VAL-PLAN-OVR-ITEM-BDI",
                status="INFO",
                mensagem=f"Item '{item_id}': preço unitário com BDI calibrado por referência.",
            )
        )
    else:
        preco_cat_com_bdi = {cat: preco_cat[cat] * (1 + bdi_aplicado[cat]) for cat in preco_cat}
    return preco_cat_com_bdi


def _validate_coverage(canonical_in: CanonicalModel, plan_out: list, validacoes: list) -> None:
    if not canonical_in.equipes_diretas:
        return
    from concilium.domain.services.validador_cobertura_item import validar_cobertura_item

    equipe_lookup_cob = {eq.item_id: eq for eq in canonical_in.equipes_diretas}
    planejamento_lookup_cob = {p.item_id: p for p in plan_out}
    for item in canonical_in.eap:
        equipe = equipe_lookup_cob.get(item.item_id)
        planej = planejamento_lookup_cob.get(item.item_id)
        if equipe and planej:
            validacoes.extend(validar_cobertura_item(item, equipe, planej))


