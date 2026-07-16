"""Skill 06 (_precificacao) — Planejamento e BDI.

Calcula preço unitário (sem e com BDI) por item da EAP, decomposto em 4 categorias:
material, diesel, mão de obra, equipamentos (ADR-023: BDI auditável via TabelaBdi).

Ordem de precedência para BDI — ver skill.py::_resolve_bdi para a ordem completa
(bdi_aplicado > tax_scenario > tabela_bdi > aliquotas_bdi_jurisdicao > DEFAULT_BDI_TABELA).
Este módulo implementa o passo 2 (`_rb_try_tax_scenario`, ADR-055 CBS/IBS).

Mapeamento de categorias ADR-023 -> modelo flat Planejamento.bdi:
    MAO_OBRA  -> mao_obra
    MATERIAL  -> material
    DIESEL    -> diesel
    SERVICOS  -> equipamentos (via tabela_bdi.servicos)
"""

from __future__ import annotations

from concilium.domain.models.canonical import (
    ValidacaoItem,
)
from concilium.domain.models.financial.bdi import (
    DEFAULT_BDI_TABELA,
    TaxSimulationScenario,
    resolver_bdi_cbs_ibs,
)

from ._lookups import _get_bdi_value  # ty: ignore[unresolved-import]


def _rb_try_tax_scenario(inputs: dict, validacoes: list) -> dict | None:
    """Tries TaxSimulationScenario path. Returns BDI dict or None."""
    tax_scenario_raw = inputs.get("tax_scenario")
    if not (tax_scenario_raw and isinstance(tax_scenario_raw, dict)):
        return None
    try:
        scenario = TaxSimulationScenario.from_dict(tax_scenario_raw)
        tabela_cbs_ibs = resolver_bdi_cbs_ibs(DEFAULT_BDI_TABELA, scenario)
        bdi_mo = tabela_cbs_ibs.mao_obra.bdi_total
        bdi_mat = tabela_cbs_ibs.material.bdi_total
        bdi_dies = tabela_cbs_ibs.diesel.bdi_total
        bdi_equip = tabela_cbs_ibs.servicos.bdi_total
        t_ef = scenario.tributos_efetivos_por_categoria()
        split_note = " ⚠️ split_payment ativo." if scenario.split_payment else ""
        validacoes.append(
            ValidacaoItem(
                codigo="VAL-BDI-REGIME",
                status="OK",
                mensagem=(
                    f"BDI via TaxSimulationScenario ADR-055 "
                    f"(regime={scenario.regime_version.value}, "
                    f"CBS_IBS_bruto={scenario.cbs_ibs_combined_rate * 100:.1f}%, "
                    f"T_ef_MO={t_ef['mao_obra'] * 100:.2f}%, "
                    f"T_ef_MAT={t_ef['material'] * 100:.2f}%).{split_note}"
                ),
            )
        )
        return {
            "material": round(bdi_mat, 6),
            "diesel": round(bdi_dies, 6),
            "mao_obra": round(bdi_mo, 6),
            "equipamentos": round(bdi_equip, 6),
        }
    except Exception as exc:
        validacoes.append(
            ValidacaoItem(
                codigo="VAL-BDI-REGIME",
                status="AVISO",
                mensagem=f"Falha ao aplicar tax_scenario CBS/IBS: {exc}. Usando path legado.",
            )
        )
        return None


def _rb_try_manual_bdi(inputs: dict, validacoes: list) -> dict | None:
    """Tries manual bdi_aplicado path. Returns BDI dict or None."""
    if not inputs.get("bdi_aplicado"):
        return None
    manual = dict(inputs["bdi_aplicado"])
    mo = _get_bdi_value(manual, "mao_obra", "mo")
    mat = _get_bdi_value(manual, "material", "mat")
    diesel = _get_bdi_value(manual, "diesel", "combustivel", "comb")
    serv = _get_bdi_value(manual, "servicos", "serv", default=mo)
    eq = _get_bdi_value(manual, "equipamentos", "eq", default=serv)
    validacoes.append(
        ValidacaoItem(
            codigo="VAL-BDI-FONTE",
            status="AVISO",
            mensagem=(
                "BDI aplicado via override manual (inputs.bdi_aplicado). "
                f"MO={mo * 100:.2f}% | EQ={eq * 100:.2f}% | MAT={mat * 100:.2f}% | "
                f"COMB={diesel * 100:.2f}% | SERV={serv * 100:.2f}%. "
                "Preferir TabelaBdi (ADR-023)."
            ),
        )
    )
    return {"material": mat, "diesel": diesel, "mao_obra": mo, "equipamentos": eq}
