"""Skill 10 — Adapter de Saída (gera JSON + Excel .xlsm) — linhas de PLANEJAMENTO e três camadas."""

from typing import Any

from concilium.domain.models.canonical import CanonicalModel, SubtotalSemBdiComBdi, ValidacaoItem

_MESES_PT = {
    1: "Jan",
    2: "Fev",
    3: "Mar",
    4: "Abr",
    5: "Mai",
    6: "Jun",
    7: "Jul",
    8: "Ago",
    9: "Set",
    10: "Out",
    11: "Nov",
    12: "Dez",
}


def _add_criticidade_validacoes(
    canonical_in: CanonicalModel, has_criticidade: bool, criticidade_lookup: dict, validacoes: list
) -> None:
    if has_criticidade:
        validacoes.append(
            ValidacaoItem(
                codigo="VAL-ADAPTER-CRITICIDADE",
                status="OK",
                mensagem=f"Criticidade aplicada em {len(criticidade_lookup)} atividades.",
            )
        )
    else:
        # Emite AVISO seja quando o relatório está ausente ou quando está presente
        # mas sem atividades classificadas que correspondam à EAP atual.
        if canonical_in.cost_criticality_report is not None:
            msg = "Relatório de criticidade presente, mas sem atividades classificadas."
        else:
            msg = "Relatório de criticidade ausente. Execute skill-15 (diagnóstico) para enriquecer o relatório."
        validacoes.append(
            ValidacaoItem(
                codigo="VAL-ADAPTER-CRITICIDADE",
                status="AVISO",
                mensagem=msg,
            )
        )


def _pe_field(pe: Any, attr: str, default: float) -> float:
    """Lê um atributo numérico do ponto_equilibrio com fallback seguro quando pe é None."""
    return float(getattr(pe, attr, default) or default) if pe else default


def _build_planejamento_row(
    p: Any,
    eap_item: Any,
    pe: Any,
    criticidade_lookup: dict[str, str],
    has_criticidade: bool,
) -> dict:
    """Constrói uma linha de PLANEJAMENTO (item + camadas de precificação NEP-042)."""
    subtotal = p.subtotal if p.subtotal is not None else SubtotalSemBdiComBdi()
    row = {
        "item_id": p.item_id,
        "cpu_id": p.cpu_id,
        "descricao": (eap_item.descricao if eap_item else ""),
        "unidade": (eap_item.unidade if eap_item else ""),
        "quantitativo": p.quantitativo,
        "subtotal_sem_bdi_mo": subtotal.sem_bdi.mao_obra,
        "subtotal_sem_bdi_eq": subtotal.sem_bdi.equipamentos,
        "subtotal_sem_bdi_diesel": subtotal.sem_bdi.diesel,
        "subtotal_sem_bdi_mat": subtotal.sem_bdi.material,
        "subtotal_sem_bdi": subtotal.sem_bdi.total,
        "subtotal_com_bdi": subtotal.com_bdi.total,
        # Camada 1 — catálogo
        "pu_total_sem_bdi": p.preco_unitario.total,
        "pu_total_com_bdi": p.preco_unitario_com_bdi.total,
        # NEP-042: Camada 2 — operacional autônomo
        "pu_op_autonomo": _pe_field(pe, "pu_operacional_autonomo", 0.0),
        "frentes_necessarias": _pe_field(pe, "frentes_equivalentes_necessarias", 1.0),
        "eta_real": _pe_field(pe, "eta_real", 1.0),
        # NEP-042: Camada 3 — burden de permanência instancial
        "burden_pool": _pe_field(pe, "custo_pool_total", 0.0),
        "economia_pool_abs": _pe_field(pe, "economia_pool_abs", 0.0),
    }
    if has_criticidade:
        row["criticidade"] = criticidade_lookup.get(p.item_id, "-")
    return row


def _build_planejamento_rows(
    canonical_in: CanonicalModel, criticidade_lookup: dict[str, str], has_criticidade: bool
) -> list[dict]:
    eap_by_item_id = {e.item_id: e for e in canonical_in.eap}
    # NEP-042: join com ponto_equilibrio para expor as três camadas de precificação
    pe_by_item = {pe.item_id: pe for pe in (canonical_in.ponto_equilibrio or []) if pe.item_id}
    return [
        _build_planejamento_row(
            p, eap_by_item_id.get(p.item_id), pe_by_item.get(p.item_id), criticidade_lookup, has_criticidade
        )
        for p in canonical_in.planejamento
    ]


def _build_tres_camadas_row(p: Any, eap_item: Any, pe: Any) -> dict:
    """Constrói uma linha da view consolidada das três camadas de precificação (NEP-042 D4)."""
    pu_op = _pe_field(pe, "pu_operacional_autonomo", 0.0)
    economia = _pe_field(pe, "economia_pool_abs", 0.0)
    custo_autonomo = pu_op * p.quantitativo if p.quantitativo else 0.0
    economia_pct = (economia / custo_autonomo) if custo_autonomo > 0 else 0.0
    return {
        "item_id": p.item_id,
        "cpu_id": p.cpu_id,
        "descricao": eap_item.descricao if eap_item else "",
        "unidade": eap_item.unidade if eap_item else "",
        "quantitativo": p.quantitativo,
        # Camada 1 — catálogo
        "pu_cat": float(p.preco_unitario.total or 0.0),
        # Camada 2 — operacional autônomo
        "pu_op_autonomo": pu_op,
        "frentes_necessarias": _pe_field(pe, "frentes_equivalentes_necessarias", 1.0),
        "eta_real": _pe_field(pe, "eta_real", 1.0),
        # Camada 3 — burden de permanência instancial
        "pu_pool": _pe_field(pe, "custo_pool_por_unidade", 0.0),
        "economia_pool_abs": economia,
        "economia_pool_pct": round(economia_pct, 4),
    }


def _build_tres_camadas_rows(canonical_in: CanonicalModel) -> list[dict]:
    """NEP-042 D4 — view consolidada das três camadas de precificação por item.

    Apresenta lado a lado: PU_cat (catálogo), PU_op_autonomo (operacional),
    PU_pool (burden instancial), + frentes_necessarias, eta_real e economia de pool.
    Cada linha é um item da EAP com planejamento; itens sem ponto_equilibrio
    expõem apenas a camada de catálogo.
    """
    eap_by_item = {e.item_id: e for e in canonical_in.eap}
    pe_by_item = {pe.item_id: pe for pe in (canonical_in.ponto_equilibrio or []) if pe.item_id}
    return [
        _build_tres_camadas_row(p, eap_by_item.get(p.item_id), pe_by_item.get(p.item_id))
        for p in canonical_in.planejamento
    ]


