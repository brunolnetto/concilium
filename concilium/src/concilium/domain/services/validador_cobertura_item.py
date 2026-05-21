"""Validação de cobertura de custo e margem por item da EAP (substitui ADR-051 Camada 2).

Compara o custo real derivado da equipe (custo_total / Q) contra o preço de venda
calculado pela skill 06. Detecta três condições:

  VAL-COB-NEG   — preço de venda abaixo do custo direto da equipe (margem negativa)
  VAL-COB-BAIXA — margem efetiva abaixo do limiar mínimo (risco financeiro)
  VAL-COB-OK    — cobertura adequada

A fórmula é derivada inteiramente dos dados do pipeline; não depende de preço de
referência do catálogo (precos_unitarios_sbdi foi removido).
"""

from __future__ import annotations

from concilium.domain.models.canonical import EapItem, EquipeDireta, Planejamento, ValidacaoItem

MARGEM_MINIMA: float = 0.05  # 5 % — abaixo disso é risco financeiro por item


def validar_cobertura_item(
    item: EapItem,
    equipe: EquipeDireta,
    planejamento: Planejamento,
) -> list[ValidacaoItem]:
    """Retorna validações de cobertura de custo e margem para um item da EAP."""
    item_id = item.item_id
    Q = item.quantitativo

    if Q <= 0 or equipe.custo_total <= 0:
        return [
            ValidacaoItem(
                codigo="VAL-COB-SEM-DADOS",
                status="AVISO",
                mensagem=f"Item '{item_id}': custo_total={equipe.custo_total:.2f} ou Q={Q} inválido — cobertura não calculada.",  # noqa: E501
            )
        ]

    if not planejamento.preco_unitario_com_bdi or planejamento.preco_unitario_com_bdi.total <= 0:
        return [
            ValidacaoItem(
                codigo="VAL-COB-SEM-PRECO",
                status="AVISO",
                mensagem=f"Item '{item_id}': preco_unitario_com_bdi ausente — cobertura não calculada.",
            )
        ]

    custo_real = equipe.custo_total / Q  # R$/unidade — todos os custos da equipe
    pu_venda = planejamento.preco_unitario_com_bdi.total  # R$/unidade com BDI
    margem = (pu_venda - custo_real) / pu_venda  # fração 0-1

    margem_pct = round(margem * 100, 2)
    custo_rs = round(custo_real, 4)
    venda_rs = round(pu_venda, 4)

    if margem < 0:
        return [
            ValidacaoItem(
                codigo="VAL-COB-NEG",
                status="ERRO",
                mensagem=(
                    f"Item '{item_id}': preço de venda ({venda_rs}) abaixo do custo da equipe ({custo_rs}). "
                    f"Margem={margem_pct:.2f}%. Revisar dimensionamento ou repassar ao cliente."
                ),
            )
        ]

    if margem < MARGEM_MINIMA:
        return [
            ValidacaoItem(
                codigo="VAL-COB-BAIXA",
                status="AVISO",
                mensagem=(
                    f"Item '{item_id}': margem efetiva {margem_pct:.2f}% abaixo do limiar {MARGEM_MINIMA * 100:.0f}%. "
                    f"Custo={custo_rs}, Venda={venda_rs}."
                ),
            )
        ]

    return [
        ValidacaoItem(
            codigo="VAL-COB-OK",
            status="OK",
            mensagem=f"Item '{item_id}': margem={margem_pct:.2f}% (custo={custo_rs}, venda={venda_rs}).",
        )
    ]
