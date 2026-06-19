"""Skill 06 — Consolidação Financeira (Consolidada).

Consolida:
1. Consolidação de Resultado (antiga 06)
2. Reconciliação de Custos de Recurso (antiga 06A)
3. Análise de Compensação Estrutural — The Bridge (ADR-039)

Objetivo: Produzir o balanço final de venda, custo e margem, já considerando impactos de aquisição
e separando os desvios estruturais (escala + clima) do delta real de gestão.
"""

from __future__ import annotations

from typing import Any

from concilium.domain.models.canonical import (
    CanonicalModel,
    ValidacaoItem,
)
from concilium.domain.models.financial.bdi import (
    DEFAULT_BDI_TABELA,
    PerfilBdiProjeto,
    TabelaBdi,
    TaxSimulationScenario,
    resolver_bdi_cbs_ibs,
    resolver_componentes_bdi,
)


def _build_abc_analytics(
    canonical_in: CanonicalModel, inputs: dict, bdi_tabela: Any, bdi_regime: str, validacoes: list
) -> tuple:
    try:
        from concilium.domain.services.analytics.cubo_analitico_builder import CuboAnaliticoBuilder
        from concilium.domain.services.analytics.curva_abc_builder import CurvaABCBuilder
        from concilium.domain.services.analytics.s_curve_builder import SCurveBuilder

        curva_abc = CurvaABCBuilder().build(canonical_in)
        s_curve = SCurveBuilder().build(canonical_in)
        _regime = (
            inputs.get("tax_scenario", {}).get("regime_version", "pre_reforma")
            if isinstance(inputs.get("tax_scenario"), dict)
            else bdi_regime
        )
        cubo_analitico = CuboAnaliticoBuilder(tabela_bdi=bdi_tabela, regime_version=_regime).build(canonical_in)
        return curva_abc, s_curve, cubo_analitico
    except Exception as exc:
        import logging

        logging.getLogger(__name__).warning("CurvaABC/SCurve/Cubo falhou (best-effort): %s", exc)
        return None, None, None


def _build_memorial_bdi(
    canonical_in: CanonicalModel, bdi_fonte: str, bdi_regime: str, bdi_tabela: Any, bdi_override: bool
) -> Any:
    try:
        from concilium.domain.services.financial.memorial_bdi_builder import MemorialBDIBuilder

        return MemorialBDIBuilder().build(
            canonical_in=canonical_in,
            bdi_fonte=bdi_fonte,
            regime_version=bdi_regime,
            tabela_usada=bdi_tabela,
            override_aplicado=bdi_override,
        )
    except Exception as exc:
        import logging

        logging.getLogger(__name__).warning("Memorial BDI falhou (best-effort): %s", exc)
        return None


def _get_bdi_value(manual: dict[str, Any], *keys: str, default: float = 0.0) -> float:
    for key in keys:
        if key in manual and manual.get(key) is not None:
            try:
                return float(manual.get(key) or 0.0)
            except Exception:
                continue
    return float(default)


def _rbf_resolve_tabela_perfil(
    inputs: dict[str, Any], validacoes: list[ValidacaoItem]
) -> tuple[TabelaBdi, str, bool, str]:
    """Resolves TabelaBdi from inputs.tabela_bdi and optional perfil_bdi.

    Returns (tabela, fonte, override, regime_str).
    """
    tabela_raw = inputs.get("tabela_bdi")
    tabela: TabelaBdi | None = None
    fonte = "DEFAULT_BDI_TABELA"
    override = False
    if tabela_raw is not None:
        try:
            tabela = TabelaBdi.model_validate(tabela_raw) if isinstance(tabela_raw, dict) else tabela_raw
            fonte = "inputs.tabela_bdi"
            override = True
        except Exception as e:
            validacoes.append(
                ValidacaoItem(
                    codigo="VAL-CONSOL-BDI-PARSE",
                    status="AVISO",
                    mensagem=f"Falha ao parsear tabela_bdi: {e}. Usando DEFAULT_BDI_TABELA.",
                )
            )
    if tabela is None:
        tabela = DEFAULT_BDI_TABELA
    perfil_bdi_raw = inputs.get("bdi_perfil") or inputs.get("perfil_bdi")
    regime_str = "pre_reforma"
    if perfil_bdi_raw is not None:
        try:
            perfil_bdi = (
                PerfilBdiProjeto.model_validate(perfil_bdi_raw) if isinstance(perfil_bdi_raw, dict) else perfil_bdi_raw
            )
            tabela = resolver_componentes_bdi(tabela, perfil_bdi)
            fonte += " + PerfilBdiProjeto"
            override = True
            regime_v = getattr(perfil_bdi, "regime_version", None)
            regime_str = regime_v.value if regime_v else "pre_reforma"
        except Exception as e:
            validacoes.append(
                ValidacaoItem(
                    codigo="VAL-CONSOL-BDI-PERFIL",
                    status="AVISO",
                    mensagem=f"Falha ao aplicar perfil_bdi: {e}. Mantendo tabela base.",
                )
            )
    return tabela, fonte, override, regime_str


def _rbf_try_tax_scenario(
    inputs: dict[str, Any], validacoes: list[ValidacaoItem]
) -> tuple[dict[str, float], TabelaBdi, str, str, bool] | None:
    """Attempt BDI resolution via TaxSimulationScenario (ADR-055). Returns None on failure/absence."""
    tax_scenario_raw = inputs.get("tax_scenario")
    if not (tax_scenario_raw and isinstance(tax_scenario_raw, dict)):
        return None
    try:
        scenario = TaxSimulationScenario.from_dict(tax_scenario_raw)
        tabela_cbs_ibs = resolver_bdi_cbs_ibs(DEFAULT_BDI_TABELA, scenario)
        rates = {
            "mao_obra": float(tabela_cbs_ibs.mao_obra.bdi_total),
            "equipamentos": float(
                tabela_cbs_ibs.material.bdi_total
            ),  # Fixed: equipment = capital good, uses material BDI (4%)
            "material": float(tabela_cbs_ibs.material.bdi_total),
            "diesel": float(tabela_cbs_ibs.diesel.bdi_total),
            "indireto": float(tabela_cbs_ibs.indireto.bdi_total),
        }
        t_ef = scenario.tributos_efetivos_por_categoria()
        validacoes.append(
            ValidacaoItem(
                codigo="VAL-CONSOL-BDI-REGIME",
                status="OK",
                mensagem=(
                    f"Consolidação via TaxSimulationScenario ADR-055 "
                    f"(regime={scenario.regime_version.value}): "
                    f"MO={rates['mao_obra'] * 100:.2f}% | IND={rates['indireto'] * 100:.2f}% | "
                    f"T_ef_MO={t_ef['mao_obra'] * 100:.2f}% | T_ef_MAT={t_ef['material'] * 100:.2f}%"
                ),
            )
        )
        return rates, tabela_cbs_ibs, "inputs.tax_scenario", scenario.regime_version.value, True
    except Exception as exc:
        validacoes.append(
            ValidacaoItem(
                codigo="VAL-CONSOL-BDI-REGIME",
                status="AVISO",
                mensagem=f"Falha ao aplicar tax_scenario: {exc}. Usando path legado.",
            )
        )
        return None


def _rbf_try_manual_bdi(
    inputs: dict[str, Any], validacoes: list[ValidacaoItem]
) -> tuple[dict[str, float], None, str, str, bool] | None:
    """Attempt BDI resolution via manual bdi_aplicado dict. Returns None if not present."""
    manual = inputs.get("bdi_aplicado")
    if not isinstance(manual, dict):
        return None
    mo = _get_bdi_value(manual, "mao_obra", "mo")
    mat = _get_bdi_value(manual, "material", "mat")
    diesel = _get_bdi_value(manual, "diesel", "combustivel", "comb")
    serv = _get_bdi_value(manual, "servicos", "serv", default=mo)
    eq = _get_bdi_value(manual, "equipamentos", "eq", default=serv)
    indireto = _get_bdi_value(manual, "indireto", "ind", default=0.0)
    validacoes.append(
        ValidacaoItem(
            codigo="VAL-CONSOL-BDI-FONTE",
            status="AVISO",
            mensagem=(
                "Consolidação financeira usando inputs.bdi_aplicado "
                f"(MO={mo * 100:.2f}%, EQ={eq * 100:.2f}%, MAT={mat * 100:.2f}%, "
                f"COMB={diesel * 100:.2f}%, SERV={serv * 100:.2f}%, IND={indireto * 100:.2f}%)."
            ),
        )
    )
    return (
        {"mao_obra": mo, "equipamentos": eq, "material": mat, "diesel": diesel, "indireto": indireto},
        None,
        "inputs.bdi_aplicado",
        "pre_reforma",
        True,
    )


def _resolve_bdi_full(
    inputs: dict[str, Any], validacoes: list[ValidacaoItem]
) -> tuple[dict[str, float], TabelaBdi, str, str, bool]:
    """ADR-057: resolve BDI retornando também (tabela, fonte, regime_version, override_aplicado).

    Retorna: (rates_dict, tabela_usada, fonte_bdi, regime_version, override_aplicado)
    """
    result = _rbf_try_tax_scenario(inputs, validacoes)
    if result is not None:
        return result
    result = _rbf_try_manual_bdi(inputs, validacoes)
    if result is not None:
        return result

    tabela, fonte, override, regime_str = _rbf_resolve_tabela_perfil(inputs, validacoes)
    rates = {
        "mao_obra": float(tabela.mao_obra.bdi_total),
        # Equipment = capital good, treated as material for BDI purposes (4% per AGIS reference).
        "equipamentos": float(tabela.material.bdi_total),
        "material": float(tabela.material.bdi_total),
        "diesel": float(tabela.diesel.bdi_total),
        "indireto": float(tabela.indireto.bdi_total),
    }
    validacoes.append(
        ValidacaoItem(
            codigo="VAL-CONSOL-BDI-FONTE",
            status="OK",
            mensagem=(
                f"Consolidação financeira por composição ({fonte}): "
                f"MO={rates['mao_obra'] * 100:.2f}% | EQ={rates['equipamentos'] * 100:.2f}% | "
                f"MAT={rates['material'] * 100:.2f}% | DIESEL={rates['diesel'] * 100:.2f}% | "
                f"IND={rates['indireto'] * 100:.2f}%"
            ),
        )
    )
    return rates, tabela, fonte, regime_str, override


def _resolve_bdi_rates(inputs: dict[str, Any], validacoes: list[ValidacaoItem]) -> dict[str, float]:
    """Backward-compat wrapper — retorna apenas os rates."""
    rates, _, _, _, _ = _resolve_bdi_full(inputs, validacoes)
    return rates


def _classificar_margem(margem, alvo, aceitavel):
    if alvo["min"] <= margem <= alvo["max"]:
        return "VERDE"
    if aceitavel["min"] <= margem <= aceitavel["max"]:
        return "AMARELO"
    return "VERMELHO"
