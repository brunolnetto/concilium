"""P11-C Skill06 stage: typed preview exported, partial evidence fails closed."""
from __future__ import annotations

from fractions import Fraction as F
from importlib.util import module_from_spec, spec_from_file_location
from pathlib import Path

import pytest

from concilium.application.scheduling.contractual_cost_ledger import (
    CostPosting,
    ExclusiveCostLedger,
    PostingNature,
)
from concilium.application.scheduling.financial_cost_reconciliation import (
    ExactFinancialReconciliation,
    WeekFinancialBalance,
)
from concilium.domain.models.canonical import (
    CanonicalModel,
    Cronograma,
    DistribuicaoSemanal,
    Resultado,
    ScheduledActivityCanonical,
)

ROOT = Path(__file__).resolve().parents[4]
W = "2026-W01"
BDI = {
    "MO": F(3, 10), "EQ": F(3, 10),
    "MAT": F(1, 10), "COMB": F(1, 10), "IND": F(1, 5),
}


def stage():
    path = (
        ROOT / "src/concilium/application/skills/manifests/"
        "06-resultado-financeiro/skill.py"
    )
    spec = spec_from_file_location("_p11c_skill06_manifest", path)
    assert spec is not None and spec.loader is not None
    module = module_from_spec(spec)
    spec.loader.exec_module(module)
    module._load_estagio("_consolidacao", "run_consolidacao_financeira")
    import sys

    return sys.modules["_concilium_resultado_financeiro_stage_consolidacao.skill"]


def snapshot():
    physical = DistribuicaoSemanal(
        num_equipes=1, qtd_executada=100, qtd_acumulada=100,
        pct=1, q_max_celula=400, capacidade_disponivel_semana=400,
    )
    canonical = CanonicalModel.model_construct(
        cronograma=Cronograma(scheduled_activities=[
            ScheduledActivityCanonical(
                activity_id="A", start_week=0, end_week=0,
                duration_weeks=1, distribuicao_semanal={W: physical},
            )
        ]),
        equipes_diretas=[object()],
        planejamento=[object()],
    )
    pool = ExclusiveCostLedger((
        CostPosting(("K", W), PostingNature.ACTIVE, "MO", F(400), "crew", W),
        CostPosting(("V", W), PostingNature.ACQUISITION, "MAT", F(100), "good", W),
    ))
    reconciled = ExactFinancialReconciliation(
        pool, (WeekFinancialBalance(W, F(400), F(100), F(0)),), False,
    )
    return canonical, reconciled


def params(reconciled) -> dict:
    return {
        "p11_financial_reconciliation": reconciled,
        "p11_scopes_by_activity": {"A": 100},
        "p11_bdi_by_category": BDI,
        "p11_independent_variable_unit_rate": F(1),
    }


def test_stage_rejects_partial_or_forged_preview_before_pricing() -> None:
    mod = stage()
    can, recon = snapshot()
    partial = mod.run_consolidacao_financeira(
        can, {"p11_financial_reconciliation": recon}, {},
    )
    assert partial.has_errors
    assert any(v.codigo == "VAL-P11-PROVENANCE" for v in partial.validacoes)
    assert partial.canonical is can

    invalid = mod.run_consolidacao_financeira(
        can, {**params(recon), "p11_financial_reconciliation": object()}, {},
    )
    assert invalid.has_errors
    assert any(v.codigo == "VAL-P11-PROVENANCE" for v in invalid.validacoes)
    assert invalid.canonical is can


def test_stage_persists_only_separately_labeled_exact_p11_preview(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    mod = stage()
    can, recon = snapshot()
    result = Resultado.model_construct()
    supplied = (
        result, {}, None, "", "", False,
        0.0, 0.0, 0.2, 0.0, "OK", 0.0, 0.0, 0.0, [],
    )
    monkeypatch.setattr(mod, "_build_resultado", lambda *args: supplied)
    monkeypatch.setattr(mod, "_build_ponto_equilibrio", lambda *args: [])
    monkeypatch.setattr(mod, "enrich_pe_bdi_equivalente", lambda *args: None)
    monkeypatch.setattr(mod, "_build_bridge_from_pe", lambda *args: ({}, None))
    monkeypatch.setattr(mod, "_build_diagnostico_pe", lambda *args: (None, None))
    monkeypatch.setattr(mod, "_build_abc_analytics", lambda *args: (None, None, None))
    monkeypatch.setattr(mod, "_build_memorial_bdi", lambda *args: None)

    response = mod.run_consolidacao_financeira(can, params(recon), {})
    assert not response.has_errors
    preview = response.canonical.resultado.metricas_realizadas_p11
    assert preview is not None
    assert preview.contractual_k == "400"
    assert preview.physically_purchased_v == "100"
    assert preview.zeta == "5/8"
    assert preview.pi == "5/2"
    assert preview.authority.endswith("NOT_PROJECT_GO")
    assert response.canonical.resultado.model_dump()[
        "metricas_realizadas_p11"
    ]["price_once_bdi"] == "630"
