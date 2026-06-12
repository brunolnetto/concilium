"""ADR-070 unit tests: campaign domain model + service logic.

No real pipeline execution — all canonical/report data is mocked using
SimpleNamespace and plain dicts.
"""
from __future__ import annotations

from types import SimpleNamespace

import pytest

from concilium.application.services.campaign_service import (
    _apply_overrides,
    calcular_pareto,
    classificar_EF,
    classificar_O,
    curar_shortlist,
    gerar_grid,
    classificar_bundle,
    extrair_vetor_O,
    extrair_vetor_EF,
)
from concilium.domain.models.campaign import (
    CenarioAvaliado,
    GoResearchCampaignBundle,
    ParametroSweep,
    PerfilExpectativas,
    VetorEspacoEF,
    VetorEspacoO,
)


# ---------------------------------------------------------------------------
# Fixtures / helpers
# ---------------------------------------------------------------------------

def _make_cenario(
    cid: str,
    *,
    viabilidade: str = "APROVADO",
    prazo: int | None = 40,
    fe_nec: float | None = 0.9,
    gap_pool: float | None = 0.0,
    margem: float | None = 0.12,
    custo_ind: float | None = 10_000.0,
    erro: str | None = None,
) -> CenarioAvaliado:
    perfil = PerfilExpectativas()
    v_O = VetorEspacoO(
        prazo_semanas=prazo,
        folga_semanas=None,
        fe_nec_medio=fe_nec,
        itens_criticos_pct=0.0,
        gap_pool_total=gap_pool,
    )
    v_EF = VetorEspacoEF(
        margem_pct=margem,
        custo_indireto=custo_ind,
        ratio_pool_vs_cat=0.95,
    )
    cl_O = classificar_O(v_O, perfil)
    cl_EF = classificar_EF(v_EF, perfil)
    return CenarioAvaliado(
        cenario_id=cid,
        parametros_variados={"objetivo": cid},
        viabilidade=viabilidade,  # type: ignore[arg-type]
        vetor_O=v_O,
        vetor_EF=v_EF,
        classificacao_O=cl_O,
        classificacao_EF=cl_EF,
        erro=erro,
    )


# ---------------------------------------------------------------------------
# 1. gerar_grid — 2 params × 3 values each → 9 scenarios
# ---------------------------------------------------------------------------

def test_gerar_grid_cross_product():
    sweep = [
        ParametroSweep("spec.a", [1, 2, 3]),
        ParametroSweep("spec.b", ["x", "y", "z"]),
    ]
    bundle = GoResearchCampaignBundle(base_spec={"spec": {}}, sweep=sweep)
    grid = gerar_grid(bundle)
    assert len(grid) == 9
    # All combos of a × b present
    combos = {(sv["spec"]["a"], sv["spec"]["b"]) for sv, _ in grid}
    assert combos == {(a, b) for a in [1, 2, 3] for b in ["x", "y", "z"]}


def test_gerar_grid_empty_sweep_returns_base():
    bundle = GoResearchCampaignBundle(base_spec={"key": "val"}, sweep=[])
    grid = gerar_grid(bundle)
    assert len(grid) == 1
    assert grid[0][0] == {"key": "val"}
    assert grid[0][1] == {}


# ---------------------------------------------------------------------------
# 2. _apply_overrides — nested dot-path works
# ---------------------------------------------------------------------------

def test_apply_overrides_nested():
    spec = {"a": {"b": {"c": 0}}}
    result = _apply_overrides(spec, {"a.b.c": 99})
    assert result["a"]["b"]["c"] == 99


def test_apply_overrides_creates_missing_keys():
    spec = {}
    result = _apply_overrides(spec, {"x.y.z": "hello"})
    assert result["x"]["y"]["z"] == "hello"


def test_apply_overrides_top_level():
    spec = {"pool_config": {"objetivo": "balanceado"}}
    result = _apply_overrides(spec, {"pool_config": {"objetivo": "minimizar_prazo"}})
    assert result["pool_config"]["objetivo"] == "minimizar_prazo"


# ---------------------------------------------------------------------------
# 3. classificar_O — IDEAL/ATENCAO/CRITICO thresholds
# ---------------------------------------------------------------------------

PERFIL = PerfilExpectativas(meta_margem_pct=0.10, tolerancia_margem=0.03)


def test_classificar_O_ideal():
    v = VetorEspacoO(folga_semanas=5.0, fe_nec_medio=0.95, itens_criticos_pct=0.0)
    assert classificar_O(v, PERFIL) == "IDEAL"


def test_classificar_O_atencao_folga_negativa_leve():
    v = VetorEspacoO(folga_semanas=-1.0, fe_nec_medio=0.95, itens_criticos_pct=0.0)
    assert classificar_O(v, PERFIL) == "ATENCAO"


def test_classificar_O_critico_folga():
    v = VetorEspacoO(folga_semanas=-5.0, fe_nec_medio=0.95, itens_criticos_pct=0.0)
    assert classificar_O(v, PERFIL) == "CRITICO"


def test_classificar_O_critico_fe_nec():
    v = VetorEspacoO(folga_semanas=2.0, fe_nec_medio=1.30, itens_criticos_pct=0.0)
    assert classificar_O(v, PERFIL) == "CRITICO"


def test_classificar_O_atencao_fe_nec():
    v = VetorEspacoO(folga_semanas=2.0, fe_nec_medio=1.20, itens_criticos_pct=0.0)
    assert classificar_O(v, PERFIL) == "ATENCAO"


def test_classificar_O_critico_itens():
    v = VetorEspacoO(folga_semanas=2.0, fe_nec_medio=0.90, itens_criticos_pct=0.30)
    assert classificar_O(v, PERFIL) == "CRITICO"


def test_classificar_O_atencao_no_data():
    v = VetorEspacoO()  # all None
    assert classificar_O(v, PERFIL) == "ATENCAO"


# ---------------------------------------------------------------------------
# 4. classificar_EF — DENTRO/ATENCAO/FORA thresholds
# ---------------------------------------------------------------------------

def test_classificar_EF_dentro():
    v = VetorEspacoEF(margem_pct=0.15, ratio_pool_vs_cat=0.90, fidelidade_gates=True)
    assert classificar_EF(v, PERFIL) == "DENTRO_EXPECTATIVA"


def test_classificar_EF_atencao_margem_perto():
    v = VetorEspacoEF(margem_pct=0.08, ratio_pool_vs_cat=0.90)
    assert classificar_EF(v, PERFIL) == "ATENCAO"


def test_classificar_EF_fora_margem_baixa():
    v = VetorEspacoEF(margem_pct=0.05, ratio_pool_vs_cat=0.90)
    assert classificar_EF(v, PERFIL) == "FORA_EXPECTATIVA"


def test_classificar_EF_fora_ratio_alto():
    v = VetorEspacoEF(margem_pct=0.12, ratio_pool_vs_cat=1.15)
    assert classificar_EF(v, PERFIL) == "FORA_EXPECTATIVA"


def test_classificar_EF_fora_gates_reprovado():
    v = VetorEspacoEF(margem_pct=0.12, fidelidade_gates=False)
    assert classificar_EF(v, PERFIL) == "FORA_EXPECTATIVA"


def test_classificar_EF_atencao_no_data():
    v = VetorEspacoEF()
    assert classificar_EF(v, PERFIL) == "ATENCAO"


# ---------------------------------------------------------------------------
# 5. calcular_pareto — basic dominance in O-space
# ---------------------------------------------------------------------------

def test_calcular_pareto_O_basic():
    # c1 strictly dominates c2 (prazo 30 < 40, fe same, gap same)
    c1 = _make_cenario("c1", prazo=30, fe_nec=0.9, gap_pool=0.0)
    c2 = _make_cenario("c2", prazo=40, fe_nec=0.9, gap_pool=0.0)
    pareto = calcular_pareto([c1, c2], "O")
    assert "c1" in pareto
    assert "c2" not in pareto


def test_calcular_pareto_O_no_dominance():
    # c1 better prazo, c2 better fe — neither dominates
    c1 = _make_cenario("c1", prazo=30, fe_nec=1.2, gap_pool=0.0)
    c2 = _make_cenario("c2", prazo=40, fe_nec=0.8, gap_pool=0.0)
    pareto = calcular_pareto([c1, c2], "O")
    assert "c1" in pareto
    assert "c2" in pareto


def test_calcular_pareto_EF_basic():
    # c1: margem 0.20, c2: margem 0.10 — c1 dominates (same custo_ind)
    c1 = _make_cenario("c1", margem=0.20, custo_ind=5_000.0)
    c2 = _make_cenario("c2", margem=0.10, custo_ind=5_000.0)
    pareto = calcular_pareto([c1, c2], "EF")
    assert "c1" in pareto
    assert "c2" not in pareto


def test_calcular_pareto_single_item_always_pareto():
    c = _make_cenario("solo")
    pareto = calcular_pareto([c], "O")
    assert "solo" in pareto


# ---------------------------------------------------------------------------
# 6. curar_shortlist — top-k with tie-break
# ---------------------------------------------------------------------------

def test_curar_shortlist_returns_top_k():
    # Use scenarios that are non-dominated in EF space (different margem vs custo_ind tradeoffs)
    # so the Pareto frontier has multiple members and top_k cap is exercised.
    cs = [
        _make_cenario("c0", margem=0.14, custo_ind=5_000.0),   # high margem, low cost
        _make_cenario("c1", margem=0.13, custo_ind=4_000.0),   # lower margem, lower cost
        _make_cenario("c2", margem=0.12, custo_ind=3_000.0),   # ...
        _make_cenario("c3", margem=0.11, custo_ind=2_000.0),   # ...
        _make_cenario("c4", margem=0.10, custo_ind=1_000.0),   # low margem, lowest cost
    ]
    shortlist = curar_shortlist(cs, top_k=3, perfil=PERFIL)
    # All 5 are Pareto-non-dominated (each has one better dimension), top_k=3 caps to 3
    assert len(shortlist) == 3
    # Ranks are monotonically increasing
    assert shortlist[0].rank == 1


def test_curar_shortlist_empty_when_no_viaveis():
    cs = [_make_cenario("c1", viabilidade="BLOQUEADO"), _make_cenario("c2", viabilidade="ERRO")]
    shortlist = curar_shortlist(cs, top_k=5, perfil=PERFIL)
    assert shortlist == []


def test_curar_shortlist_pareto_flags_set():
    # c1 dominates c2 in both spaces
    c1 = _make_cenario("c1", prazo=30, fe_nec=0.8, gap_pool=0.0, margem=0.20, custo_ind=5_000.0)
    c2 = _make_cenario("c2", prazo=40, fe_nec=1.0, gap_pool=1_000.0, margem=0.10, custo_ind=8_000.0)
    shortlist = curar_shortlist([c1, c2], top_k=5, perfil=PERFIL)
    top = shortlist[0].cenario
    assert top.cenario_id == "c1"
    assert top.pareto_O
    assert top.pareto_EF


def test_curar_shortlist_rank_increases():
    cs = [_make_cenario(f"c{i}", margem=0.10 + i * 0.01) for i in range(4)]
    shortlist = curar_shortlist(cs, top_k=4, perfil=PERFIL)
    ranks = [r.rank for r in shortlist]
    assert ranks == sorted(ranks)


# ---------------------------------------------------------------------------
# 7. classificar_bundle — SUCESSO/FRONTEIRA_UNICA/INFEASIBLE
# ---------------------------------------------------------------------------

def test_classificar_bundle_sucesso():
    c1 = _make_cenario("c1", prazo=30, fe_nec=0.8, margem=0.20)
    c2 = _make_cenario("c2", prazo=40, fe_nec=1.0, margem=0.10)
    # Run shortlist so pareto flags get set
    curar_shortlist([c1, c2], top_k=5, perfil=PERFIL)
    # c1 dominates both O and EF → pareto_intersecao = True
    # We need to manually set since classificar_bundle reads the flag
    c1.pareto_intersecao = True
    status = classificar_bundle([c1, c2])
    assert status == "SUCESSO"


def test_classificar_bundle_infeasible():
    c1 = _make_cenario("c1", viabilidade="BLOQUEADO")
    c2 = _make_cenario("c2", viabilidade="BLOQUEADO")
    status = classificar_bundle([c1, c2])
    assert status == "INFEASIBLE"


def test_classificar_bundle_abortado_all_errors():
    c1 = _make_cenario("c1", viabilidade="ERRO", erro="pipeline crash")
    c2 = _make_cenario("c2", viabilidade="ERRO", erro="timeout")
    status = classificar_bundle([c1, c2])
    assert status == "ABORTADO"


def test_classificar_bundle_sucesso_parcial():
    # Both viable, but no pareto_intersecao and no separate pareto_O + pareto_EF frontier
    c1 = _make_cenario("c1", prazo=30, fe_nec=0.9, margem=0.12)
    c2 = _make_cenario("c2", prazo=35, fe_nec=0.9, margem=0.11)
    # Don't run curar_shortlist — pareto flags remain False
    status = classificar_bundle([c1, c2])
    assert status == "SUCESSO_PARCIAL"


# ---------------------------------------------------------------------------
# 8. extrair_vetor_O — canonical dict parsing
# ---------------------------------------------------------------------------

def test_extrair_vetor_O_from_makespan():
    canonical = {
        "cronograma": {"makespan_semanas": 42},
        "ponto_equilibrio": [
            {"frentes_equivalentes_necessarias": 0.9, "gap_pool_overhead": 100.0},
            {"frentes_equivalentes_necessarias": 1.1, "gap_pool_overhead": 200.0},
        ],
        "equipes_diretas": [{"custo_inst_mob_demob": 5000.0}],
    }
    v = extrair_vetor_O(canonical, prazo_contratual=56)
    assert v.prazo_semanas == 42
    assert v.folga_semanas == 14.0
    assert abs(v.fe_nec_medio - 1.0) < 0.01
    assert v.itens_criticos_pct == 0.0  # neither > 1.25
    assert v.gap_pool_total == 300.0
    assert v.custo_mob_window_total == 5000.0


def test_extrair_vetor_O_fallback_to_scheduled_activities():
    canonical = {
        "cronograma": {
            "scheduled_activities": [
                {"end_week": 30},
                {"end_week": 45},
                {"end_week": 38},
            ]
        },
    }
    v = extrair_vetor_O(canonical, prazo_contratual=50)
    assert v.prazo_semanas == 45
    assert v.folga_semanas == 5.0


# ---------------------------------------------------------------------------
# 9. extrair_vetor_EF — canonical dict parsing
# ---------------------------------------------------------------------------

def test_extrair_vetor_EF_basic():
    canonical = {
        "resultado": {
            "margem_pct": 0.176,
            "custo": {
                "direto_equipes": 50_000_000.0,
                "custo_indireto_total": 8_000_000.0,
            },
            "venda": {
                "total_com_bdi": 68_000_000.0,
                "total_sem_bdi": 60_000_000.0,
            },
        }
    }
    report = {"quality_gates": {"decision": "APROVADO"}}
    v = extrair_vetor_EF(canonical, report)
    assert v.margem_pct == pytest.approx(0.176, abs=1e-4)
    assert v.custo_execucao_pool == 50_000_000.0
    assert v.preco_venda == 68_000_000.0
    assert v.ratio_pool_vs_cat == pytest.approx(50_000_000 / 60_000_000, abs=1e-4)
    assert v.fidelidade_gates is True


def test_extrair_vetor_EF_bloqueado_gates():
    canonical = {"resultado": {"margem_pct": 0.05}}
    report = {"quality_gates": {"decision": "BLOQUEADO"}}
    v = extrair_vetor_EF(canonical, report)
    assert v.fidelidade_gates is False


# ── Testes de _apply_scalar e _set_path ([*] wildcard + __scale__) ──────────

from concilium.application.services.campaign_service import (
    _apply_scalar,
    _set_path,
    _apply_post_load_overrides,
)


class TestApplyScalar:
    def test_scale_int(self):
        assert _apply_scalar(4, {"__scale__": 2.0}) == 8

    def test_scale_float(self):
        assert abs(_apply_scalar(3, {"__scale__": 1.25}) - 4) < 0.01  # ceil(3.75)=4

    def test_scale_preserves_min_1(self):
        assert _apply_scalar(1, {"__scale__": 0.5}) == 1  # max(1, ceil(0.5))

    def test_add_int(self):
        assert _apply_scalar(3, {"__add__": 2}) == 5

    def test_plain_replace(self):
        assert _apply_scalar(3, 7) == 7

    def test_dict_merge(self):
        result = _apply_scalar({"a": 1}, {"b": 2})
        assert result == {"a": 1, "b": 2}

    def test_scale_none_fallback(self):
        # When existing is None, cannot scale — returns value as-is
        result = _apply_scalar(None, {"__scale__": 2.0})
        assert result == {"__scale__": 2.0}  # unchanged (no existing to scale)


class TestSetPath:
    def test_simple_path(self):
        d = {"a": {"b": 5}}
        _set_path(d, ["a", "b"], 10)
        assert d["a"]["b"] == 10

    def test_wildcard_list(self):
        d = {"items": [{"n": 2}, {"n": 4}, {"n": 6}]}
        _set_path(d, ["items", "[*]", "n"], {"__scale__": 2.0})
        assert d["items"][0]["n"] == 4
        assert d["items"][1]["n"] == 8
        assert d["items"][2]["n"] == 12

    def test_wildcard_nested(self):
        d = {"activities": [
            {"ramp_params": {"n_max": 3, "n_inicial": 1}},
            {"ramp_params": {"n_max": 6, "n_inicial": 2}},
        ]}
        _set_path(d, ["activities", "[*]", "ramp_params", "n_max"], {"__scale__": 1.25})
        assert d["activities"][0]["ramp_params"]["n_max"] == 4   # ceil(3.75)
        assert d["activities"][1]["ramp_params"]["n_max"] == 8   # ceil(7.5)

    def test_wildcard_creates_missing_key(self):
        d = {"items": [{"a": 1}, {"a": 2}]}
        _set_path(d, ["items", "[*]", "b"], 99)
        assert d["items"][0]["b"] == 99
        assert d["items"][1]["b"] == 99


class TestApplyPostLoadOverrides:
    def test_wildcard_scale_on_activities(self):
        from types import SimpleNamespace
        acts = [
            {"ramp_params": {"n_max": 4, "n_inicial": 1}},
            {"ramp_params": {"n_max": 2, "n_inicial": 1}},
        ]
        spec_obj = SimpleNamespace(
            inputs_cronograma={"rcpsp_spec": {"activities": acts}}
        )
        _apply_post_load_overrides(spec_obj, {
            "inputs_cronograma.rcpsp_spec.activities.[*].ramp_params.n_max": {"__scale__": 1.5},
        })
        assert acts[0]["ramp_params"]["n_max"] == 6  # ceil(6.0)
        assert acts[1]["ramp_params"]["n_max"] == 3  # ceil(3.0)

    def test_add_on_scalar(self):
        from types import SimpleNamespace
        spec_obj = SimpleNamespace(
            inputs_cronograma={"rcpsp_spec": {"deadline_weeks": 56}}
        )
        _apply_post_load_overrides(spec_obj, {
            "inputs_cronograma.rcpsp_spec.deadline_weeks": {"__add__": 14},
        })
        assert spec_obj.inputs_cronograma["rcpsp_spec"]["deadline_weeks"] == 70
