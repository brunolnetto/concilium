"""Skill 06 — Consolidar Resultado.

Reúne tudo que foi computado pelas skills 03, 04, 05 e produz:
- ponto_equilibrio: array com reconciliação por item da EAP
- resultado: agregação final com venda, custo, margem, status, validações

Esta skill não recomputa custos — apenas agrega o que já está no canônico.
"""

from typing import Any

from concilium.models.canonical import (
    CanonicalModel,
    CustoTotal,
    PontoEquilibrio,
    Resultado,
    StatusMargem,
    ValidacaoItem,
    Venda,
)
from concilium.skills.escopo import SkillResult


def _classificar_margem(
    margem: float,
    faixa_alvo: dict[str, float],
    faixa_aceitavel: dict[str, float],
) -> StatusMargem:
    """VERDE = dentro do alvo; AMARELO = fora do alvo mas dentro do aceitável; VERMELHO = fora do aceitável."""
    if faixa_alvo["min"] <= margem <= faixa_alvo["max"]:
        return "VERDE"
    if faixa_aceitavel["min"] <= margem <= faixa_aceitavel["max"]:
        return "AMARELO"
    return "VERMELHO"


def run_consolidar_resultado(
    canonical_in: CanonicalModel,
    inputs: dict[str, Any],
    perfil: dict[str, Any],
) -> SkillResult:
    """Popula seções 'ponto_equilibrio' e 'resultado'.

    Pré-condições: equipes_diretas, planejamento, indiretos populados.
    perfil deve conter:
        - limiar_ponto_equilibrio: float
        - faixa_margem_alvo: {min, max}
        - faixa_margem_aceitavel: {min, max}
    """
    validacoes: list[ValidacaoItem] = []

    if not canonical_in.equipes_diretas or not canonical_in.planejamento:
        validacoes.append(
            ValidacaoItem(
                codigo="VAL-CONSOL-PRECONDICAO",
                status="ERRO",
                mensagem="Skill 06 requer equipes_diretas e planejamento populados",
            )
        )
        return SkillResult(canonical_in, validacoes)

    limiar_pe = perfil["limiar_ponto_equilibrio"]
    faixa_alvo = perfil["faixa_margem_alvo"]
    faixa_aceitavel = perfil["faixa_margem_aceitavel"]

    # 1. Reconciliação ponto de equilíbrio por item
    ponto_eq: list[PontoEquilibrio] = []
    equipe_por_item = {e.item_id: e for e in canonical_in.equipes_diretas}
    plan_por_item = {p.item_id: p for p in canonical_in.planejamento}
    cron_por_item = {c.item_id: c for c in canonical_in.cronograma}

    for item in canonical_in.eap:
        eq = equipe_por_item.get(item.item_id)
        plan = plan_por_item.get(item.item_id)
        if eq is None or plan is None:
            continue

        # custo_fixo_equipe = custo total da equipe ao longo da obra
        custo_fixo = eq.custo_total

        # custo_venda_cpu: preço sem BDI × quantitativo (base SICRO/coeficientes)
        # Mas para PE, o que importa é: o preço de venda cobre o custo da equipe?
        # Interpretação correta: custo_venda = preco_unit_sem_bdi × quantitativo
        # Isso representa o que o cliente paga antes do BDI pelo volume executado
        custo_venda = plan.subtotal.sem_bdi.total

        # Custo unitário real da equipe (normalizado pelo quantitativo)
        custo_unit_real = custo_fixo / item.quantitativo if item.quantitativo > 0 else 0
        custo_unit_venda = plan.preco_unitario.total

        delta = abs(custo_unit_real - custo_unit_venda)
        delta_pct = delta / custo_unit_real if custo_unit_real > 0 else 0.0

        if delta_pct > limiar_pe:
            status = "ERRO"
            validacoes.append(
                ValidacaoItem(
                    codigo="VAL-PE-01",
                    status="ERRO",
                    mensagem=(
                        f"Item {item.item_id}: delta unitário {delta_pct*100:.1f}% > limiar "
                        f"{limiar_pe*100:.1f}% (custo unit. real R$ {custo_unit_real:.4f}, "
                        f"custo unit. CPU R$ {custo_unit_venda:.4f})"
                    ),
                )
            )
        elif delta_pct > limiar_pe / 2:
            status = "AVISO"
        else:
            status = "OK"

        ponto_eq.append(
            PontoEquilibrio(
                item_id=item.item_id,
                custo_fixo_equipe=custo_fixo,
                custo_venda_cpu=custo_venda,
                delta=custo_venda - custo_fixo,
                delta_pct=delta_pct,
                status_validacao=status,
            )
        )

    if not any(v.codigo == "VAL-PE-01" for v in validacoes):
        validacoes.append(
            ValidacaoItem(
                codigo="VAL-PE-01",
                status="OK",
                mensagem=f"Todos itens dentro do limiar {limiar_pe*100:.1f}%",
            )
        )

    # 2. Agregação venda
    venda_sem_bdi = sum(p.subtotal.sem_bdi.total for p in canonical_in.planejamento)
    venda_com_bdi = sum(p.subtotal.com_bdi.total for p in canonical_in.planejamento)

    # 3. Agregação custos
    custo_direto = sum(e.custo_total for e in canonical_in.equipes_diretas)
    custos_indiretos: dict[str, float] = {
        "ADM": 0.0, "TOP": 0.0, "LAB": 0.0, "QSMS": 0.0, "MOB": 0.0,
    }
    for ind in canonical_in.indiretos:
        custos_indiretos[ind.categoria] = ind.custo_total

    custo_total_val = custo_direto + sum(custos_indiretos.values())

    # 4. Resultado financeiro e margem
    resultado_financeiro = venda_com_bdi - custo_total_val
    margem_pct = resultado_financeiro / venda_com_bdi if venda_com_bdi > 0 else 0.0
    status_margem = _classificar_margem(margem_pct, faixa_alvo, faixa_aceitavel)

    # 5. Validação de política de margem
    if status_margem == "VERMELHO":
        validacoes.append(
            ValidacaoItem(
                codigo="VAL-POL-MARGEM",
                status="ERRO",
                mensagem=f"Margem {margem_pct*100:.2f}% fora da faixa aceitável "
                f"({faixa_aceitavel['min']*100:.1f}%-{faixa_aceitavel['max']*100:.1f}%)",
            )
        )
    elif status_margem == "AMARELO":
        validacoes.append(
            ValidacaoItem(
                codigo="VAL-POL-MARGEM",
                status="AVISO",
                mensagem=f"Margem {margem_pct*100:.2f}% fora da faixa-alvo "
                f"({faixa_alvo['min']*100:.1f}%-{faixa_alvo['max']*100:.1f}%); status AMARELO",
            )
        )
    else:
        validacoes.append(
            ValidacaoItem(
                codigo="VAL-POL-MARGEM",
                status="OK",
                mensagem=f"Margem {margem_pct*100:.2f}% dentro da faixa-alvo",
            )
        )

    custo_modelo = CustoTotal(
        direto_equipes=custo_direto,
        indireto_adm=custos_indiretos["ADM"],
        indireto_top=custos_indiretos["TOP"],
        indireto_lab=custos_indiretos["LAB"],
        indireto_qsms=custos_indiretos["QSMS"],
        indireto_mob=custos_indiretos["MOB"],
        total=custo_total_val,
    )
    resultado = Resultado(
        venda=Venda(total_sem_bdi=venda_sem_bdi, total_com_bdi=venda_com_bdi),
        custo=custo_modelo,
        resultado_financeiro=resultado_financeiro,
        margem_pct=margem_pct,
        status_margem=status_margem,
        validacoes=validacoes,
    )

    novo = canonical_in.model_copy(
        update={"ponto_equilibrio": ponto_eq, "resultado": resultado}
    )
    return SkillResult(novo, validacoes)
