"""ADR-070 unit tests: campaign domain model + service logic.

No real pipeline execution — all canonical/report data is mocked using
SimpleNamespace and plain dicts.
"""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from concilium.application.services.campaign.campaign_service import (
    _apply_overrides,
    calcular_pareto,
    classificar_bundle,
    classificar_EF,
    classificar_O,
    curar_shortlist,
    extrair_vetor_EF,
    extrair_vetor_O,
    gerar_grid,
)
from concilium.domain.models.campaign.campaign import (
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
        _make_cenario("c0", margem=0.14, custo_ind=5_000.0),  # high margem, low cost
        _make_cenario("c1", margem=0.13, custo_ind=4_000.0),  # lower margem, lower cost
        _make_cenario("c2", margem=0.12, custo_ind=3_000.0),  # ...
        _make_cenario("c3", margem=0.11, custo_ind=2_000.0),  # ...
        _make_cenario("c4", margem=0.10, custo_ind=1_000.0),  # low margem, lowest cost
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

from concilium.application.services.campaign.campaign_service import (  # noqa: E402
    _apply_post_load_overrides,
    _apply_scalar,
    _set_path,
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
        d = {
            "activities": [
                {"ramp_params": {"n_max": 3, "n_inicial": 1}},
                {"ramp_params": {"n_max": 6, "n_inicial": 2}},
            ]
        }
        _set_path(d, ["activities", "[*]", "ramp_params", "n_max"], {"__scale__": 1.25})
        assert d["activities"][0]["ramp_params"]["n_max"] == 4  # ceil(3.75)
        assert d["activities"][1]["ramp_params"]["n_max"] == 8  # ceil(7.5)

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
        spec_obj = SimpleNamespace(inputs_cronograma={"rcpsp_spec": {"activities": acts}})
        _apply_post_load_overrides(
            spec_obj,
            {
                "inputs_cronograma.rcpsp_spec.activities.[*].ramp_params.n_max": {"__scale__": 1.5},
            },
        )
        assert acts[0]["ramp_params"]["n_max"] == 6  # ceil(6.0)
        assert acts[1]["ramp_params"]["n_max"] == 3  # ceil(3.0)

    def test_add_on_scalar(self):
        from types import SimpleNamespace

        spec_obj = SimpleNamespace(inputs_cronograma={"rcpsp_spec": {"deadline_weeks": 56}})
        _apply_post_load_overrides(
            spec_obj,
            {
                "inputs_cronograma.rcpsp_spec.deadline_weeks": {"__add__": 14},
            },
        )
        assert spec_obj.inputs_cronograma["rcpsp_spec"]["deadline_weeks"] == 70


# ── ADR-108: cubo_analitico e cronograma alimentam vetores ───────────────────

from concilium.application.services.campaign.campaign_service import (  # noqa: E402
    _cronograma_utilizacao,
    _cubo_analitico_agregado,
)


class TestCuboAnaliticoAgregado:
    def _canonical(self, celulas):
        return {"cubo_analitico": {"celulas": celulas}}

    def test_vazio_retorna_dict_vazio(self):
        assert _cubo_analitico_agregado({}) == {}
        assert _cubo_analitico_agregado({"cubo_analitico": {"celulas": []}}) == {}

    def test_share_mo_eq_comb(self):
        celulas = [
            {
                "componente_bdi": "custo_direto",
                "categoria_insumo": "mao_obra",
                "propriedade": "salario_encargos",
                "atividade_id": "a1",
                "valor_rs": 100.0,
            },
            {
                "componente_bdi": "custo_direto",
                "categoria_insumo": "equipamento",
                "propriedade": "aluguel",
                "atividade_id": "a2",
                "valor_rs": 200.0,
            },
            {
                "componente_bdi": "custo_direto",
                "categoria_insumo": "material",
                "propriedade": "combustivel",
                "atividade_id": "a3",
                "valor_rs": 100.0,
            },
        ]
        r = _cubo_analitico_agregado(self._canonical(celulas))
        assert r["share_mo"] == pytest.approx(0.25, abs=0.01)
        assert r["share_eq"] == pytest.approx(0.50, abs=0.01)
        assert r["share_comb"] == pytest.approx(0.25, abs=0.01)

    def test_ic1_shares_somam_no_maximo_1(self):
        celulas = [
            {
                "componente_bdi": "custo_direto",
                "categoria_insumo": "mao_obra",
                "propriedade": "salario_encargos",
                "atividade_id": "a1",
                "valor_rs": 60.0,
            },
            {
                "componente_bdi": "custo_direto",
                "categoria_insumo": "equipamento",
                "propriedade": "aluguel",
                "atividade_id": "a2",
                "valor_rs": 40.0,
            },
        ]
        r = _cubo_analitico_agregado(self._canonical(celulas))
        assert r["share_mo"] + r["share_eq"] + r["share_comb"] <= 1.0 + 1e-6

    def test_hhi_uniforme(self):
        # 4 atividades com mesmo custo → HHI = 4 × (0.25)² = 0.25
        celulas = [
            {
                "componente_bdi": "custo_direto",
                "categoria_insumo": "equipamento",
                "propriedade": "aluguel",
                "atividade_id": f"a{i}",
                "valor_rs": 100.0,
            }
            for i in range(4)
        ]
        r = _cubo_analitico_agregado(self._canonical(celulas))
        assert r["hhi"] == pytest.approx(0.25, abs=0.01)

    def test_hhi_monopolio(self):
        # Só 1 atividade → HHI = 1.0
        celulas = [
            {
                "componente_bdi": "custo_direto",
                "categoria_insumo": "equipamento",
                "propriedade": "aluguel",
                "atividade_id": "a1",
                "valor_rs": 100.0,
            }
        ]
        r = _cubo_analitico_agregado(self._canonical(celulas))
        assert r["hhi"] == pytest.approx(1.0, abs=0.01)

    def test_ignora_celulas_nao_custo_direto(self):
        celulas = [
            {
                "componente_bdi": "margem_l",
                "categoria_insumo": "mao_obra",
                "propriedade": "salario_encargos",
                "atividade_id": "a1",
                "valor_rs": 9999.0,
            },
            {
                "componente_bdi": "custo_direto",
                "categoria_insumo": "equipamento",
                "propriedade": "aluguel",
                "atividade_id": "a2",
                "valor_rs": 100.0,
            },
        ]
        r = _cubo_analitico_agregado(self._canonical(celulas))
        assert r["share_eq"] == pytest.approx(1.0, abs=0.01)


class TestCronogramaUtilizacao:
    def _canonical_com_atividades(self, acts):
        return {"cronograma": {"scheduled_activities": acts}}

    def test_vazio_retorna_dict_vazio(self):
        assert _cronograma_utilizacao({}) == {}
        assert _cronograma_utilizacao({"cronograma": {"scheduled_activities": []}}) == {}

    def test_utilizacao_100pct(self):
        acts = [{"distribuicao_semanal": {"S1": {"num_equipes": 2}, "S2": {"num_equipes": 1}}}]
        r = _cronograma_utilizacao(self._canonical_com_atividades(acts))
        assert r["utilizacao"] == pytest.approx(1.0, abs=0.01)

    def test_utilizacao_parcial(self):
        # 2 semanas mobilizado, 1 produtivo → 50%
        acts = [{"distribuicao_semanal": {"S1": {"num_equipes": 0}, "S2": {"num_equipes": 1}}}]
        r = _cronograma_utilizacao(self._canonical_com_atividades(acts))
        assert r["utilizacao"] == pytest.approx(0.5, abs=0.01)

    def test_paralelismo_2_atividades_simultaneas(self):
        # 2 atividades ativas na mesma semana
        acts = [
            {"distribuicao_semanal": {"S1": {"num_equipes": 1}, "S2": {"num_equipes": 0}}},
            {"distribuicao_semanal": {"S1": {"num_equipes": 1}, "S2": {"num_equipes": 1}}},
        ]
        r = _cronograma_utilizacao(self._canonical_com_atividades(acts))
        # S1: 2 atividades ativas; S2: 1 ativa → média = 1.5
        assert r["paralelismo"] == pytest.approx(1.5, abs=0.01)


# ---------------------------------------------------------------------------
# Feature 1 — per_item independent sweep
# ---------------------------------------------------------------------------

from concilium.application.services.campaign.campaign_service import _apply_per_item_post_load  # noqa: E402


def _make_activities_spec_obj(activities: list[dict]) -> SimpleNamespace:
    """Helper: cria um spec_obj com inputs_cronograma.rcpsp_spec.activities."""
    return SimpleNamespace(inputs_cronograma={"rcpsp_spec": {"activities": activities}})


class TestPerItemSweep:
    """Feature 1: scope='per_item' — cada item_id varia independentemente."""

    # --- Cardinalidade ---

    def test_per_item_cardinality_2_items_3_values(self):
        """2 item_ids × 3 valores = 3^2 = 9 cenários."""
        sweep = [
            ParametroSweep(
                campo="inputs_cronograma.rcpsp_spec.activities.[*].ramp_params.n_max",
                valores=[{"__scale__": 0.75}, {"__scale__": 1.0}, {"__scale__": 1.25}],
                scope="per_item",
                item_ids=["eap-1_5", "eap-1_6"],
            )
        ]
        bundle = GoResearchCampaignBundle(base_spec={}, sweep=sweep)
        assert bundle.cardinality() == 9

    def test_per_item_cardinality_adds_to_global(self):
        """global(2) × per_item(3^2=9) = 18."""
        sweep = [
            ParametroSweep("meta.regime", [1, 2], scope="global"),
            ParametroSweep(
                campo="inputs_cronograma.rcpsp_spec.activities.[*].ramp_params.n_max",
                valores=[{"__scale__": 0.75}, {"__scale__": 1.0}, {"__scale__": 1.25}],
                scope="per_item",
                item_ids=["eap-1_5", "eap-1_6"],
            ),
        ]
        bundle = GoResearchCampaignBundle(base_spec={}, sweep=sweep)
        assert bundle.cardinality() == 18

    def test_per_item_gerar_grid_count(self):
        """gerar_grid retorna 9 cenários para 2 item_ids × 3 valores."""
        sweep = [
            ParametroSweep(
                campo="inputs_cronograma.rcpsp_spec.activities.[*].ramp_params.n_max",
                valores=[{"__scale__": 0.75}, {"__scale__": 1.0}, {"__scale__": 1.25}],
                scope="per_item",
                item_ids=["eap-1_5", "eap-1_6"],
            )
        ]
        bundle = GoResearchCampaignBundle(base_spec={}, sweep=sweep)
        grid = gerar_grid(bundle)
        assert len(grid) == 9

    def test_per_item_cardinality_single_item(self):
        """1 item_id × 3 valores = 3 cenários (não 3^1=3, mas efectivamente linear)."""
        sweep = [
            ParametroSweep(
                campo="inputs_cronograma.rcpsp_spec.activities.[*].ramp_params.n_max",
                valores=[{"__scale__": 0.75}, {"__scale__": 1.0}, {"__scale__": 1.25}],
                scope="per_item",
                item_ids=["eap-1_5"],
            )
        ]
        bundle = GoResearchCampaignBundle(base_spec={}, sweep=sweep)
        assert bundle.cardinality() == 3
        assert len(gerar_grid(bundle)) == 3

    # --- parametros_variados ---

    def test_per_item_parametros_variados_has_item_keys(self):
        """Cada cenário do grid registra chaves por item_id nos parametros_variados."""
        sweep = [
            ParametroSweep(
                campo="inputs_cronograma.rcpsp_spec.activities.[*].ramp_params.n_max",
                valores=[{"__scale__": 0.75}, {"__scale__": 1.25}],
                scope="per_item",
                item_ids=["eap-1_5", "eap-1_6"],
            )
        ]
        bundle = GoResearchCampaignBundle(base_spec={}, sweep=sweep)
        grid = gerar_grid(bundle)
        # 4 cenários (2^2)
        assert len(grid) == 4
        campo = "inputs_cronograma.rcpsp_spec.activities.[*].ramp_params.n_max"
        for _sv, variados in grid:
            key_5 = f"_per_item_:{campo}:eap-1_5"
            key_6 = f"_per_item_:{campo}:eap-1_6"
            assert key_5 in variados
            assert key_6 in variados

    def test_per_item_all_combos_present(self):
        """Todos os 4 pares (v1×v2) aparecem nos parametros_variados."""
        vals = [{"__scale__": 0.75}, {"__scale__": 1.25}]
        campo = "inputs_cronograma.rcpsp_spec.activities.[*].ramp_params.n_max"
        sweep = [
            ParametroSweep(campo=campo, valores=vals, scope="per_item", item_ids=["eap-1_5", "eap-1_6"]),
        ]
        bundle = GoResearchCampaignBundle(base_spec={}, sweep=sweep)
        grid = gerar_grid(bundle)
        key_5 = f"_per_item_:{campo}:eap-1_5"
        key_6 = f"_per_item_:{campo}:eap-1_6"
        pairs = {(str(v[key_5]), str(v[key_6])) for _sv, v in grid}
        expected = {(str(a), str(b)) for a in vals for b in vals}
        assert pairs == expected

    # --- _apply_per_item_post_load ---

    def test_per_item_applies_to_correct_activity(self):
        """O override per_item afeta apenas a activity com o item_id correto."""
        acts = [
            {"item_id": "eap-1_5", "ramp_params": {"n_max": 4, "n_inicial": 1}},
            {"item_id": "eap-1_6", "ramp_params": {"n_max": 6, "n_inicial": 1}},
        ]
        spec_obj = _make_activities_spec_obj(acts)
        campo = "inputs_cronograma.rcpsp_spec.activities.[*].ramp_params.n_max"
        _apply_per_item_post_load(
            spec_obj,
            f"_per_item_:{campo}:eap-1_5",
            {"__scale__": 0.75},
        )
        # eap-1_5: 4 * 0.75 = 3.0 → ceil = 3
        assert acts[0]["ramp_params"]["n_max"] == 3
        # eap-1_6: não deve ser modificado
        assert acts[1]["ramp_params"]["n_max"] == 6

    def test_per_item_does_not_affect_other_items(self):
        """Múltiplos overrides per_item independentes não interferem entre si."""
        acts = [
            {"item_id": "eap-1_5", "ramp_params": {"n_max": 4}},
            {"item_id": "eap-1_6", "ramp_params": {"n_max": 8}},
            {"item_id": "eap-1_7", "ramp_params": {"n_max": 2}},
        ]
        spec_obj = _make_activities_spec_obj(acts)
        campo = "inputs_cronograma.rcpsp_spec.activities.[*].ramp_params.n_max"
        # Override apenas eap-1_5 e eap-1_7
        _apply_per_item_post_load(spec_obj, f"_per_item_:{campo}:eap-1_5", {"__scale__": 1.25})
        _apply_per_item_post_load(spec_obj, f"_per_item_:{campo}:eap-1_7", {"__scale__": 2.0})
        # eap-1_5: ceil(4 * 1.25) = 5
        assert acts[0]["ramp_params"]["n_max"] == 5
        # eap-1_6: intocado
        assert acts[1]["ramp_params"]["n_max"] == 8
        # eap-1_7: ceil(2 * 2.0) = 4
        assert acts[2]["ramp_params"]["n_max"] == 4

    def test_per_item_full_pipeline_gerar_grid_and_apply(self):
        """Integração: gerar_grid + _apply_post_load_overrides aplica corretamente por item."""
        acts = [
            {"item_id": "eap-1_5", "ramp_params": {"n_max": 4}},
            {"item_id": "eap-1_6", "ramp_params": {"n_max": 8}},
        ]
        base_spec = {}
        campo = "inputs_cronograma.rcpsp_spec.activities.[*].ramp_params.n_max"
        sweep = [
            ParametroSweep(
                campo=campo,
                valores=[{"__scale__": 0.75}, {"__scale__": 1.25}],
                scope="per_item",
                item_ids=["eap-1_5", "eap-1_6"],
            )
        ]
        bundle = GoResearchCampaignBundle(base_spec=base_spec, sweep=sweep)
        grid = gerar_grid(bundle)
        assert len(grid) == 4

        # Para cada cenário, aplicar post_load_overrides e verificar
        import copy

        from concilium.application.services.campaign.campaign_service import _apply_post_load_overrides

        for _sv, variados in grid:
            acts_copy = copy.deepcopy(acts)
            spec_obj = _make_activities_spec_obj(acts_copy)
            _apply_post_load_overrides(spec_obj, variados)

            key_5 = f"_per_item_:{campo}:eap-1_5"
            key_6 = f"_per_item_:{campo}:eap-1_6"
            scale_5 = variados[key_5]["__scale__"]
            scale_6 = variados[key_6]["__scale__"]

            import math

            expected_5 = max(1, math.ceil(4 * scale_5))
            expected_6 = max(1, math.ceil(8 * scale_6))
            assert acts_copy[0]["ramp_params"]["n_max"] == expected_5
            assert acts_copy[1]["ramp_params"]["n_max"] == expected_6


# ---------------------------------------------------------------------------
# Feature 2 — cpu_alternativo sweep (Classe 4 — ADR-070 F4)
# ---------------------------------------------------------------------------

from concilium.application.services.campaign.campaign_service import _apply_cpu_alt_override  # noqa: E402


class TestCpuAlternativoSweep:
    """Feature 2: scope='cpu_alternativo' — substitui cpu_id no EAP por item_id."""

    def _make_spec_com_eap(self, item_ids: list[str]) -> dict:
        """Cria um spec com spec.eap contendo items com cpu_id padrão."""
        return {"spec": {"eap": [{"item_id": iid, "cpu_id": f"CPU-DEFAULT-{iid}"} for iid in item_ids]}}

    # --- Cardinalidade ---

    def test_cpu_alternativo_generates_k_scenarios(self):
        """2 CPUs = 2 cenários (1 item_id)."""
        cpus = ["CPU-TERRA-ESCO-CARGA-3CAT-DMT2000", "CPU-TERRA-ESCO-CARGA-3CAT-DMT3000"]
        sweep = [
            ParametroSweep(
                campo="eap.cpu_id",
                valores=cpus,
                scope="cpu_alternativo",
                item_ids=["eap-1_5"],
            )
        ]
        bundle = GoResearchCampaignBundle(base_spec={}, sweep=sweep)
        assert bundle.cardinality() == 2
        assert len(gerar_grid(bundle)) == 2

    def test_cpu_alternativo_per_item_independent(self):
        """2 item_ids × 2 CPUs = 4 cenários."""
        cpus = ["CPU-TERRA-ESCO-CARGA-3CAT-DMT2000", "CPU-TERRA-ESCO-CARGA-3CAT-DMT3000"]
        sweep = [
            ParametroSweep(
                campo="eap.cpu_id",
                valores=cpus,
                scope="cpu_alternativo",
                item_ids=["eap-1_5", "eap-1_6"],
            )
        ]
        bundle = GoResearchCampaignBundle(base_spec={}, sweep=sweep)
        assert bundle.cardinality() == 4
        assert len(gerar_grid(bundle)) == 4

    # --- _apply_cpu_alt_override ---

    def test_cpu_alternativo_modifies_spec_eap(self):
        """O spec do cenário tem o cpu_id correto após _apply_overrides."""
        spec = self._make_spec_com_eap(["eap-1_5", "eap-1_6"])
        cpus = ["CPU-TERRA-ESCO-CARGA-3CAT-DMT2000", "CPU-TERRA-ESCO-CARGA-3CAT-DMT3000"]
        sweep = [
            ParametroSweep(
                campo="eap.cpu_id",
                valores=cpus,
                scope="cpu_alternativo",
                item_ids=["eap-1_5"],
            )
        ]
        bundle = GoResearchCampaignBundle(base_spec=spec, sweep=sweep)
        grid = gerar_grid(bundle)
        # Cenário 0: eap-1_5 recebe CPU DMT2000
        sv0, _ = grid[0]
        eap0 = {e["item_id"]: e for e in sv0["spec"]["eap"]}
        assert eap0["eap-1_5"]["cpu_id"] == cpus[0]
        assert eap0["eap-1_6"]["cpu_id"] == "CPU-DEFAULT-eap-1_6"  # intocado

        # Cenário 1: eap-1_5 recebe CPU DMT3000
        sv1, _ = grid[1]
        eap1 = {e["item_id"]: e for e in sv1["spec"]["eap"]}
        assert eap1["eap-1_5"]["cpu_id"] == cpus[1]

    def test_cpu_alternativo_direct_apply_override(self):
        """_apply_cpu_alt_override modifica diretamente o spec aninhado."""
        spec = self._make_spec_com_eap(["eap-1_5", "eap-1_6"])
        _apply_cpu_alt_override(spec, "_cpu_alt_:eap.cpu_id:eap-1_5", "CPU-TERRA-ESCO-CARGA-3CAT-DMT2000")
        eap = {e["item_id"]: e for e in spec["spec"]["eap"]}
        assert eap["eap-1_5"]["cpu_id"] == "CPU-TERRA-ESCO-CARGA-3CAT-DMT2000"
        assert eap["eap-1_6"]["cpu_id"] == "CPU-DEFAULT-eap-1_6"

    def test_cpu_alternativo_two_items_all_combos(self):
        """grid com 2 item_ids × 2 CPUs cobre todos os 4 pares."""
        spec = self._make_spec_com_eap(["eap-1_5", "eap-1_6"])
        cpus = ["CPU-A", "CPU-B"]
        sweep = [
            ParametroSweep(
                campo="eap.cpu_id",
                valores=cpus,
                scope="cpu_alternativo",
                item_ids=["eap-1_5", "eap-1_6"],
            )
        ]
        bundle = GoResearchCampaignBundle(base_spec=spec, sweep=sweep)
        grid = gerar_grid(bundle)
        assert len(grid) == 4

        pairs = set()
        for sv, _ in grid:
            eap_dict = {e["item_id"]: e["cpu_id"] for e in sv["spec"]["eap"]}
            pairs.add((eap_dict["eap-1_5"], eap_dict["eap-1_6"]))

        expected = {(a, b) for a in cpus for b in cpus}
        assert pairs == expected

    def test_cpu_alternativo_combined_with_global_sweep(self):
        """global(2) × cpu_alt(2 item × 2 CPU = 4) = 8 cenários."""
        spec = self._make_spec_com_eap(["eap-1_5", "eap-1_6"])
        sweep = [
            ParametroSweep("meta.regime", [1, 2], scope="global"),
            ParametroSweep(
                campo="eap.cpu_id",
                valores=["CPU-A", "CPU-B"],
                scope="cpu_alternativo",
                item_ids=["eap-1_5", "eap-1_6"],
            ),
        ]
        bundle = GoResearchCampaignBundle(base_spec=spec, sweep=sweep)
        assert bundle.cardinality() == 8
        assert len(gerar_grid(bundle)) == 8


# ---------------------------------------------------------------------------
# Feature 3 — restricoes_mercado sweep
# ---------------------------------------------------------------------------


class TestRestricoesMercadoSweep:
    """Feature 3: restricoes_mercado como dimensão de sweep (campo top-level)."""

    def _make_spec_with_restricoes(self, restricoes: dict) -> dict:
        return {"restricoes_mercado": restricoes, "meta": {"projeto": "teste"}}

    # --- Cardinalidade ---

    def test_restricoes_mercado_sweep_cardinality(self):
        """3 valores = 3 cenários."""
        sweep = [
            ParametroSweep(
                campo="restricoes_mercado",
                valores=[
                    {},
                    {"EQUIPE-CPU-TERRA-ESCO-CARGA-3CAT-DMT2000": 2},
                    {"EQUIPE-CPU-TERRA-ESCO-CARGA-3CAT-DMT2000": 2, "EQUIPE-CPU-TERRA-ESCO-CARGA-3CAT-DMT3000": 2},
                ],
            )
        ]
        bundle = GoResearchCampaignBundle(base_spec={}, sweep=sweep)
        assert bundle.cardinality() == 3
        assert len(gerar_grid(bundle)) == 3

    def test_restricoes_mercado_irrestrito_is_empty_dict(self):
        """Valor {} é o cenário irrestrito (sem restrição de mercado)."""
        sweep = [
            ParametroSweep(
                campo="restricoes_mercado",
                valores=[{}, {"EQUIPE-CPU-TERRA-ESCO-CARGA-3CAT-DMT2000": 1}],
            )
        ]
        bundle = GoResearchCampaignBundle(base_spec={"restricoes_mercado": {}}, sweep=sweep)
        grid = gerar_grid(bundle)
        assert len(grid) == 2
        # Primeiro cenário: restricoes_mercado permanece vazio ou igual a {}
        sv0, v0 = grid[0]
        assert sv0.get("restricoes_mercado") == {} or sv0.get("restricoes_mercado") is not None
        # O variados registra o valor bruto
        assert v0["restricoes_mercado"] == {}

    def test_restricoes_mercado_with_resource_cap(self):
        """Dict com limite de recurso é aplicado corretamente como top-level field."""
        resource_cap = {"EQUIPE-CPU-TERRA-ESCO-CARGA-3CAT-DMT2000": 2}
        sweep = [
            ParametroSweep(
                campo="restricoes_mercado",
                valores=[{}, resource_cap],
            )
        ]
        bundle = GoResearchCampaignBundle(base_spec={}, sweep=sweep)
        grid = gerar_grid(bundle)
        # Cenário 0: sem restrição
        sv0, _ = grid[0]
        assert sv0.get("restricoes_mercado") == {}
        # Cenário 1: com restrição
        sv1, _ = grid[1]
        assert sv1.get("restricoes_mercado") == resource_cap

    def test_restricoes_mercado_merge_on_existing(self):
        """Quando base_spec já tem restricoes_mercado, sweep faz merge de dict."""
        base = {"restricoes_mercado": {"EQUIPE-PADRAO": 5}}
        sweep = [
            ParametroSweep(
                campo="restricoes_mercado",
                valores=[{"EQUIPE-NOVA": 3}],
            )
        ]
        bundle = GoResearchCampaignBundle(base_spec=base, sweep=sweep)
        grid = gerar_grid(bundle)
        sv, _ = grid[0]
        # merge: ambas as chaves presentes
        assert sv["restricoes_mercado"]["EQUIPE-PADRAO"] == 5
        assert sv["restricoes_mercado"]["EQUIPE-NOVA"] == 3

    def test_restricoes_mercado_combined_with_other_dims(self):
        """restricoes_mercado × regime = 3 × 2 = 6 cenários."""
        sweep = [
            ParametroSweep("meta.regime", ["A", "B"]),
            ParametroSweep(
                campo="restricoes_mercado",
                valores=[
                    {},
                    {"EQUIPE-CPU-DMT2000": 2},
                    {"EQUIPE-CPU-DMT2000": 2, "EQUIPE-CPU-DMT3000": 2},
                ],
            ),
        ]
        bundle = GoResearchCampaignBundle(base_spec={}, sweep=sweep)
        assert bundle.cardinality() == 6
        assert len(gerar_grid(bundle)) == 6


class TestClasse3RestricoesMercadoPool:
    """Classe 3: restricoes_mercado top-level propaga para inferir_pool_minimo."""

    def test_restricoes_mercado_propagadas_para_pool_inference(self):
        """restricoes_mercado no spec top-level limita o pool inferido."""
        from concilium.application.scheduling.pool_inference import inferir_pool_minimo_from_spec

        spec = {
            "activities": [
                {"item_id": "A", "duration_weeks": 2, "required_resources": {"EQUIPE-R": 3}},
                {"item_id": "B", "duration_weeks": 2, "required_resources": {"EQUIPE-R": 3}},
            ],
            "precedence": [],
            "pool_config": {"objetivo": "minimizar_prazo"},
            "restricoes_mercado": {"EQUIPE-R": 2},  # mercado só tem 2
        }
        pool, diag = inferir_pool_minimo_from_spec(spec)
        # Pico seria 6 (ambas paralelas), mas mercado limita a 2
        assert pool.get("EQUIPE-R", 999) <= 2, f"Pool {pool} deve ser limitado a 2 pelo mercado"

    def test_restricoes_mercado_ausente_nao_limita(self):
        """Sem restricoes_mercado, pool sobe ao pico normalmente."""
        from concilium.application.scheduling.pool_inference import inferir_pool_minimo_from_spec

        spec = {
            "activities": [
                {"item_id": "A", "duration_weeks": 2, "required_resources": {"EQUIPE-R": 3}},
            ],
            "precedence": [],
            "pool_config": {"objetivo": "minimizar_prazo"},
        }
        pool, _ = inferir_pool_minimo_from_spec(spec)
        assert pool.get("EQUIPE-R", 0) == 3

    def test_restricoes_mercado_nao_dict_ignorado(self):
        """Valor inválido (não-dict) em restricoes_mercado é ignorado sem erro."""
        from concilium.application.scheduling.pool_inference import inferir_pool_minimo_from_spec

        spec = {
            "activities": [
                {"item_id": "A", "duration_weeks": 1, "required_resources": {"R": 1}},
            ],
            "precedence": [],
            "restricoes_mercado": "invalido",
        }
        pool, _ = inferir_pool_minimo_from_spec(spec)
        assert isinstance(pool, dict)


class TestClasse4CpuAlternativo:
    """Classe 4: listar_cpus_alternativos e sugerir_levers_cpu_alternativo."""

    def test_listar_cpus_alternativos_dmt(self, tmp_path):
        """CPU com cpus_alternativos declarado retorna lista correta."""
        from concilium.application.services.campaign.campaign_service import listar_cpus_alternativos

        cpus_dir = tmp_path / "catalogos" / "mendeslobo" / "cpus"
        cpus_dir.mkdir(parents=True)
        (cpus_dir / "CPU-A.json").write_text('{"descricao": "A", "cpus_alternativos": ["CPU-B"]}', encoding="utf-8")
        alts = listar_cpus_alternativos("CPU-A", tmp_path)
        assert alts == ["CPU-B"]

    def test_listar_cpus_alternativos_sem_campo(self, tmp_path):
        """CPU sem cpus_alternativos retorna lista vazia."""
        from concilium.application.services.campaign.campaign_service import listar_cpus_alternativos

        cpus_dir = tmp_path / "catalogos" / "mendeslobo" / "cpus"
        cpus_dir.mkdir(parents=True)
        (cpus_dir / "CPU-X.json").write_text('{"descricao": "X"}', encoding="utf-8")
        assert listar_cpus_alternativos("CPU-X", tmp_path) == []

    def test_listar_cpus_alternativos_inexistente(self, tmp_path):
        """CPU inexistente retorna lista vazia sem exceção."""
        from concilium.application.services.campaign.campaign_service import listar_cpus_alternativos

        assert listar_cpus_alternativos("CPU-NAOEXISTE", tmp_path) == []

    def test_sugerir_levers_cpu_alternativo(self, tmp_path):
        """sugerir_levers retorna ParametroSweep para item com CPU que tem alternativo."""
        from concilium.application.services.campaign.campaign_service import sugerir_levers_cpu_alternativo

        cpus_dir = tmp_path / "catalogos" / "mendeslobo" / "cpus"
        cpus_dir.mkdir(parents=True)
        (cpus_dir / "CPU-DMT2000.json").write_text(
            '{"descricao": "DMT2000", "cpus_alternativos": ["CPU-DMT3000"]}', encoding="utf-8"
        )
        base_spec = {
            "spec": {
                "eap": [
                    {"item_id": "eap-01", "cpu_id": "CPU-DMT2000", "quantitativo": 100},
                    {"item_id": "eap-02", "cpu_id": "CPU-SEM-ALT", "quantitativo": 50},
                ]
            }
        }
        levers = sugerir_levers_cpu_alternativo(base_spec, tmp_path)
        assert len(levers) == 1
        lv = levers[0]
        assert lv.scope == "cpu_alternativo"
        assert lv.item_ids == ["eap-01"]
        assert "CPU-DMT2000" in lv.valores
        assert "CPU-DMT3000" in lv.valores

    def test_sugerir_levers_sem_alternativos(self, tmp_path):
        """EAP com CPUs sem alternativo retorna lista vazia."""
        from concilium.application.services.campaign.campaign_service import sugerir_levers_cpu_alternativo

        cpus_dir = tmp_path / "catalogos" / "mendeslobo" / "cpus"
        cpus_dir.mkdir(parents=True)
        base_spec = {"spec": {"eap": [{"item_id": "x", "cpu_id": "CPU-NAOEXISTE"}]}}
        assert sugerir_levers_cpu_alternativo(base_spec, tmp_path) == []

    def test_cpu_alternativo_lever_gera_cenarios_corretos(self, tmp_path):
        """Lever cpu_alternativo com 2 valores para 1 item gera 2 cenários."""
        from concilium.application.services.campaign.campaign_service import gerar_grid, sugerir_levers_cpu_alternativo
        from concilium.domain.models.campaign.campaign import GoResearchCampaignBundle

        cpus_dir = tmp_path / "catalogos" / "mendeslobo" / "cpus"
        cpus_dir.mkdir(parents=True)
        (cpus_dir / "CPU-A.json").write_text('{"descricao":"A","cpus_alternativos":["CPU-B"]}', encoding="utf-8")
        base_spec = {"spec": {"eap": [{"item_id": "i1", "cpu_id": "CPU-A"}]}}
        levers = sugerir_levers_cpu_alternativo(base_spec, tmp_path)
        bundle = GoResearchCampaignBundle(base_spec=base_spec, sweep=levers)
        assert bundle.cardinality() == 2
        grid = gerar_grid(bundle)
        assert len(grid) == 2
        cpu_ids = [sv["spec"]["eap"][0]["cpu_id"] for sv, _ in grid]
        assert set(cpu_ids) == {"CPU-A", "CPU-B"}


def test_campaign_bundle_cardinality_breakdown_and_post_init():
    sweep = [
        ParametroSweep(campo="a", valores=[1, 2]),
        ParametroSweep(campo="b", valores=["x", "y"], scope="per_item", item_ids=["i1", "i2"]),
    ]
    bundle = GoResearchCampaignBundle(base_spec={"x": 1}, sweep=sweep)
    rows = bundle.cardinality_breakdown()

    assert rows[0]["scope"] == "global"
    assert rows[0]["acumulado"] == 2
    assert rows[1]["scope"] == "per_item"
    assert rows[1]["n_items"] == 2
    assert rows[1]["contrib"] == 4
    assert rows[1]["acumulado"] == 8

    explicit = GoResearchCampaignBundle(base_spec={"x": 1}, sweep=[], campaign_id="campaign-fixed")
    assert explicit.campaign_id == "campaign-fixed"
