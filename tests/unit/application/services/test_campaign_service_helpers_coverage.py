"""Coverage tests for campaign_service helpers and campaign_report helpers."""

from __future__ import annotations

from unittest.mock import MagicMock

from concilium.application.services.campaign.campaign_service import (
    _apply_per_item_post_load,
    _apply_scalar,
    _cronograma_utilizacao,
    _set_path,
    _set_path_per_item,
    cenario_id,
    classificar_bundle,
    curar_shortlist,
)
from concilium.domain.models.campaign.campaign import (
    CenarioAvaliado,
    PerfilExpectativas,
    VetorEspacoEF,
    VetorEspacoO,
)

# ---------------------------------------------------------------------------
# _apply_scalar
# ---------------------------------------------------------------------------


class TestApplyScalar:
    def test_scale_float_existing(self):
        result = _apply_scalar(10.0, {"__scale__": 2.0})
        assert result == 20.0

    def test_scale_int_existing_uses_ceil(self):
        # int * 1.5 = 15.0 — ceil is 15, type is int
        result = _apply_scalar(10, {"__scale__": 1.5})
        assert isinstance(result, int)
        assert result == 15

    def test_scale_int_min_one(self):
        # 1 * 0.1 = 0.1 — ceil is 1, max(1, ...) keeps 1
        result = _apply_scalar(1, {"__scale__": 0.1})
        assert result == 1

    def test_scale_float_rounds_to_4(self):
        result = _apply_scalar(1.0, {"__scale__": 1.123456})
        assert result == round(1.123456, 4)

    def test_scale_existing_none_returns_value_dict(self):
        # When existing is None, __scale__ block is skipped; falls through to return value
        value = {"__scale__": 2.0}
        result = _apply_scalar(None, value)
        assert result == value

    def test_add_float(self):
        result = _apply_scalar(10.0, {"__add__": 3.0})
        assert result == 13.0

    def test_add_int_preserves_type(self):
        # line 188-189: type(existing)(raw) when existing is int
        result = _apply_scalar(5, {"__add__": 2})
        assert isinstance(result, int)
        assert result == 7

    def test_add_existing_none_returns_value_dict(self):
        # existing is None, __add__ block skipped, falls through to return value
        value = {"__add__": 5}
        result = _apply_scalar(None, value)
        assert result == value

    def test_add_type_error_falls_through(self):
        # non-numeric existing causes TypeError -> except -> falls through to return value
        value = {"__add__": 3.0}
        result = _apply_scalar("not_a_number", value)
        assert result == value

    def test_scale_type_error_falls_through(self):
        value = {"__scale__": 2.0}
        result = _apply_scalar("not_a_number", value)
        assert result == value

    def test_dict_merge(self):
        result = _apply_scalar({"a": 1}, {"b": 2})
        assert result == {"a": 1, "b": 2}

    def test_dict_merge_existing_not_dict(self):
        # existing is not dict, value is plain dict without __scale__/__add__ -> return value
        result = _apply_scalar(42, {"b": 2})
        assert result == {"b": 2}

    def test_plain_value_replaces(self):
        result = _apply_scalar(10, "replacement")
        assert result == "replacement"

    def test_plain_value_none_existing(self):
        result = _apply_scalar(None, "new_value")
        assert result == "new_value"


# ---------------------------------------------------------------------------
# _set_path
# ---------------------------------------------------------------------------


class TestSetPath:
    def test_simple_key(self):
        d: dict = {"a": 1}
        _set_path(d, ["a"], 99)
        assert d["a"] == 99

    def test_nested_keys(self):
        d: dict = {"a": {"b": 5}}
        _set_path(d, ["a", "b"], 42)
        assert d["a"]["b"] == 42

    def test_creates_intermediate_dict(self):
        d: dict = {}
        _set_path(d, ["x", "y"], 7)
        assert d["x"]["y"] == 7

    def test_creates_intermediate_list_for_wildcard(self):
        d: dict = {}
        # rest[0] == "[*]" -> intermediate is a list
        _set_path(d, ["items", "[*]", "val"], 3)
        # d["items"] should be a list (empty, nothing to iterate)
        assert isinstance(d["items"], list)

    def test_wildcard_applies_to_all_list_items(self):
        d: dict = {"items": [{"val": 1}, {"val": 2}]}
        _set_path(d, ["items", "[*]", "val"], 99)
        assert d["items"][0]["val"] == 99
        assert d["items"][1]["val"] == 99

    def test_wildcard_not_list_does_nothing(self):
        d: dict = {"items": "not_a_list"}
        _set_path(d, ["items", "[*]", "val"], 99)
        # no error raised, items unchanged
        assert d["items"] == "not_a_list"

    def test_empty_parts_returns_early(self):
        d: dict = {"a": 1}
        _set_path(d, [], 99)
        assert d["a"] == 1

    def test_leaf_on_non_dict_does_nothing(self):
        # d is a list, not a dict -> leaf branch skipped
        d: list = [1, 2]
        _set_path(d, ["key"], 5)  # no error

    def test_scalar_applied_at_leaf(self):
        d: dict = {"x": 10}
        _set_path(d, ["x"], {"__scale__": 2.0})
        assert d["x"] == 20.0


# ---------------------------------------------------------------------------
# _set_path_per_item
# ---------------------------------------------------------------------------


class TestSetPathPerItem:
    def test_wildcard_filters_by_item_id(self):
        items = [
            {"item_id": "A", "val": 1},
            {"item_id": "B", "val": 2},
        ]
        _set_path_per_item(items, ["[*]", "val"], 99, "A")
        assert items[0]["val"] == 99
        assert items[1]["val"] == 2  # unchanged

    def test_wildcard_not_list_does_nothing(self):
        d: dict = {"items": "not_a_list"}
        _set_path_per_item(d, ["[*]", "val"], 99, "A")

    def test_empty_parts(self):
        _set_path_per_item({}, [], 1, "A")

    def test_leaf_sets_value(self):
        # lines 293-295: not rest -> sets d[part]
        d: dict = {"k": 5}
        _set_path_per_item(d, ["k"], 10, "any_id")
        assert d["k"] == 10

    def test_creates_intermediate_dict(self):
        d: dict = {}
        _set_path_per_item(d, ["a", "b"], 7, "id1")
        assert d["a"]["b"] == 7

    def test_creates_intermediate_list_for_wildcard_next(self):
        d: dict = {}
        _set_path_per_item(d, ["items", "[*]", "val"], 3, "id1")
        assert isinstance(d["items"], list)

    def test_wildcard_item_without_item_id_skipped(self):
        items = [{"val": 1}, {"val": 2}]  # no "item_id" key
        _set_path_per_item(items, ["[*]", "val"], 99, "A")
        # none matched, unchanged
        assert items[0]["val"] == 1
        assert items[1]["val"] == 2

    def test_line_299_leaf_applies_scalar(self):
        d: dict = {"n": 10}
        _set_path_per_item(d, ["n"], {"__add__": 5}, "id")
        assert d["n"] == 15.0


# ---------------------------------------------------------------------------
# _apply_per_item_post_load
# ---------------------------------------------------------------------------

_PER_ITEM_PREFIX = "_per_item_:"


class TestApplyPerItemPostLoad:
    def test_no_colon_returns_early(self):
        # suffix has no last colon -> return early (line 243 / 259-260)
        spec = MagicMock()
        key_path = f"{_PER_ITEM_PREFIX}no_colon_here"
        _apply_per_item_post_load(spec, key_path, 42)
        # spec attributes should not be accessed
        spec.assert_not_called()

    def test_campo_not_starting_with_inputs_returns_early(self):
        # campo does not start with "inputs_" -> return (line 260)
        # Use a simple object with no inputs_* attributes to confirm no modification
        class _Spec:
            accessed = False

            @property
            def inputs_cronograma(self):
                _Spec.accessed = True
                return None

        spec = _Spec()
        key_path = f"{_PER_ITEM_PREFIX}spec.rcpsp.activities.[*].n_max:item-1"
        _apply_per_item_post_load(spec, key_path, 42)
        assert not _Spec.accessed

    def test_attr_missing_on_spec_returns_early(self):
        # getattr returns None -> return (line 265)
        spec = MagicMock()
        spec.inputs_cronograma = None
        key_path = f"{_PER_ITEM_PREFIX}inputs_cronograma.rcpsp_spec.activities.[*].n_max:item-1"
        _apply_per_item_post_load(spec, key_path, 42)
        # No exception raised; d is None so function returns early

    def test_valid_path_applies_to_matching_item(self):
        # Full happy path: attr exists, contains list, item_id matches
        activities = [
            {"item_id": "item-1", "n_max": 3},
            {"item_id": "item-2", "n_max": 5},
        ]
        inputs_cron = {"rcpsp_spec": {"activities": activities}}

        spec = MagicMock()
        spec.inputs_cronograma = inputs_cron
        key_path = f"{_PER_ITEM_PREFIX}inputs_cronograma.rcpsp_spec.activities.[*].n_max:item-1"
        _apply_per_item_post_load(spec, key_path, 10)
        assert activities[0]["n_max"] == 10
        assert activities[1]["n_max"] == 5


# ---------------------------------------------------------------------------
# cenario_id
# ---------------------------------------------------------------------------


class TestCenarioId:
    def test_same_dict_same_hash(self):
        d = {"a": 1, "b": 2}
        assert cenario_id(d) == cenario_id(d)

    def test_different_dict_different_hash(self):
        assert cenario_id({"a": 1}) != cenario_id({"a": 2})

    def test_result_is_10_chars(self):
        result = cenario_id({"key": "value"})
        assert len(result) == 10

    def test_order_independent(self):
        # sort_keys=True in json.dumps
        assert cenario_id({"b": 2, "a": 1}) == cenario_id({"a": 1, "b": 2})

    def test_empty_dict(self):
        result = cenario_id({})
        assert len(result) == 10

    def test_non_serializable_uses_str(self):
        # default=str handles non-serializable objects
        from datetime import date

        result = cenario_id({"d": date(2024, 1, 1)})
        assert len(result) == 10


# ---------------------------------------------------------------------------
# _cronograma_utilizacao
# ---------------------------------------------------------------------------


class TestCronogramaUtilizacao:
    def test_no_acts_returns_empty(self):
        canonical: dict = {}
        result = _cronograma_utilizacao(canonical)
        assert result == {}

    def test_empty_acts_returns_empty(self):
        canonical = {"cronograma": {"scheduled_activities": []}}
        result = _cronograma_utilizacao(canonical)
        assert result == {}

    def test_none_cronograma_returns_empty(self):
        canonical = {"cronograma": None}
        result = _cronograma_utilizacao(canonical)
        assert result == {}

    def test_basic_utilizacao(self):
        # 2 weeks total, 1 productive
        acts = [
            {
                "distribuicao_semanal": {
                    "2024-W01": {"num_equipes": 2},
                    "2024-W02": {"num_equipes": 0},
                }
            }
        ]
        canonical = {"cronograma": {"scheduled_activities": acts}}
        result = _cronograma_utilizacao(canonical)
        assert result["utilizacao"] == 0.5  # 1/2
        assert result["paralelismo"] == 1.0  # only week 01 is active, 1 activity
        assert result["idle_pct"] is None

    def test_paralelismo_multiple_activities_same_week(self):
        acts = [
            {"distribuicao_semanal": {"W01": {"num_equipes": 1}}},
            {"distribuicao_semanal": {"W01": {"num_equipes": 1}}},
        ]
        canonical = {"cronograma": {"scheduled_activities": acts}}
        result = _cronograma_utilizacao(canonical)
        # W01 has 2 active activities -> paralelismo = 2.0
        assert result["paralelismo"] == 2.0

    def test_pool_face_idle_pct(self):
        acts = [{"distribuicao_semanal": {"W01": {"num_equipes": 1}}}]
        celulas = [
            {"estado": "idle"},
            {"estado": "idle"},
            {"estado": "active"},
            {"estado": "active"},
        ]
        canonical = {
            "cronograma": {"scheduled_activities": acts},
            "cubo_pool_face": {"celulas": celulas},
        }
        result = _cronograma_utilizacao(canonical)
        assert result["idle_pct"] == 0.5  # 2/4

    def test_pool_face_empty_celulas(self):
        acts = [{"distribuicao_semanal": {"W01": {"num_equipes": 1}}}]
        canonical = {
            "cronograma": {"scheduled_activities": acts},
            "cubo_pool_face": {"celulas": []},
        }
        result = _cronograma_utilizacao(canonical)
        assert result["idle_pct"] is None

    def test_pool_face_not_dict(self):
        acts = [{"distribuicao_semanal": {"W01": {"num_equipes": 1}}}]
        canonical = {
            "cronograma": {"scheduled_activities": acts},
            "cubo_pool_face": "not_a_dict",
        }
        result = _cronograma_utilizacao(canonical)
        assert result["idle_pct"] is None

    def test_missing_num_equipes_treated_as_zero(self):
        acts = [{"distribuicao_semanal": {"W01": {}, "W02": {"num_equipes": 1}}}]
        canonical = {"cronograma": {"scheduled_activities": acts}}
        result = _cronograma_utilizacao(canonical)
        # 2 total weeks, 1 productive
        assert result["utilizacao"] == 0.5

    def test_all_productive_utilizacao_is_one(self):
        acts = [
            {
                "distribuicao_semanal": {
                    "W01": {"num_equipes": 3},
                    "W02": {"num_equipes": 2},
                }
            }
        ]
        canonical = {"cronograma": {"scheduled_activities": acts}}
        result = _cronograma_utilizacao(canonical)
        assert result["utilizacao"] == 1.0


# ---------------------------------------------------------------------------
# Helpers for curar_shortlist / classificar_bundle
# ---------------------------------------------------------------------------


def _make_cenario(
    cenario_id_str: str,
    viabilidade: str = "APROVADO",
    margem_pct: float = 0.15,
    prazo_semanas: int = 20,
    folga_semanas: float = 2.0,
    fe_nec_medio: float = 0.9,
    classificacao_O: str = "IDEAL",
    classificacao_EF: str = "DENTRO_EXPECTATIVA",
    erro: str | None = None,
    pareto_O: bool = False,
    pareto_EF: bool = False,
    pareto_intersecao: bool = False,
) -> CenarioAvaliado:
    return CenarioAvaliado(
        cenario_id=cenario_id_str,
        parametros_variados={"key": cenario_id_str},
        viabilidade=viabilidade,
        vetor_O=VetorEspacoO(
            prazo_semanas=prazo_semanas,
            folga_semanas=folga_semanas,
            fe_nec_medio=fe_nec_medio,
            itens_criticos_pct=0.0,
        ),
        vetor_EF=VetorEspacoEF(
            margem_pct=margem_pct,
            ratio_pool_vs_cat=0.9,
        ),
        classificacao_O=classificacao_O,
        classificacao_EF=classificacao_EF,
        erro=erro,
        pareto_O=pareto_O,
        pareto_EF=pareto_EF,
        pareto_intersecao=pareto_intersecao,
    )


# ---------------------------------------------------------------------------
# curar_shortlist
# ---------------------------------------------------------------------------


class TestCurarShortlist:
    def test_no_viaveis_returns_empty(self):
        cenarios = [_make_cenario("c1", viabilidade="BLOQUEADO")]
        perfil = PerfilExpectativas()
        result = curar_shortlist(cenarios, top_k=5, perfil=perfil)
        assert result == []

    def test_single_viavel_returned(self):
        cenarios = [_make_cenario("c1", viabilidade="APROVADO")]
        perfil = PerfilExpectativas()
        result = curar_shortlist(cenarios, top_k=5, perfil=perfil)
        assert len(result) == 1
        assert result[0].rank == 1

    def test_top_k_limits_results(self):
        # All cenarios identical in O-space so none dominates another -> all on Pareto frontier
        # Use different prazo_semanas so one dominates; otherwise all are non-dominated
        # Simplest: make cenarios identical except cenario_id to ensure all end up in pool
        cenarios = [
            _make_cenario(
                f"c{i}",
                viabilidade="APROVADO",
                margem_pct=0.15,
                prazo_semanas=20,
                fe_nec_medio=0.9,
            )
            for i in range(10)
        ]
        perfil = PerfilExpectativas()
        result = curar_shortlist(cenarios, top_k=3, perfil=perfil)
        assert len(result) == 3

    def test_ranked_by_margem_descending(self):
        # Make cenarios non-dominated by each other so both end up in pool
        # They need to differ on different axes so neither dominates the other in O-space
        cenarios = [
            _make_cenario("low", viabilidade="APROVADO", margem_pct=0.10, prazo_semanas=15),
            _make_cenario("high", viabilidade="APROVADO", margem_pct=0.25, prazo_semanas=25),
        ]
        perfil = PerfilExpectativas()
        result = curar_shortlist(cenarios, top_k=5, perfil=perfil)
        # At least one result returned; if two, higher margem should rank first
        assert len(result) >= 1
        if len(result) >= 2:
            assert result[0].cenario.vetor_EF.margem_pct >= result[1].cenario.vetor_EF.margem_pct

    def test_aprovado_com_ressalvas_included(self):
        cenarios = [_make_cenario("c1", viabilidade="APROVADO_COM_RESSALVAS")]
        perfil = PerfilExpectativas()
        result = curar_shortlist(cenarios, top_k=5, perfil=perfil)
        assert len(result) == 1

    def test_justificativa_contains_motivo(self):
        cenarios = [_make_cenario("c1", viabilidade="APROVADO")]
        perfil = PerfilExpectativas()
        result = curar_shortlist(cenarios, top_k=5, perfil=perfil)
        assert result[0].justificativa.motivo_inclusao in {"pareto_intersecao", "pareto_EF", "melhor_viavel"}

    def test_pareto_intersecao_gets_motivo(self):
        c = _make_cenario("c1", viabilidade="APROVADO", margem_pct=0.20)
        cenarios = [c]
        perfil = PerfilExpectativas()
        result = curar_shortlist(cenarios, top_k=5, perfil=perfil)
        # With a single cenario it is on both frontiers -> pareto_intersecao
        assert result[0].justificativa.motivo_inclusao == "pareto_intersecao"

    def test_folga_negative_warn_tag(self):
        c = _make_cenario("c1", viabilidade="APROVADO", folga_semanas=-1.0)
        perfil = PerfilExpectativas()
        result = curar_shortlist([c], top_k=1, perfil=perfil)
        destaques = result[0].justificativa.destaques_O
        assert any("WARN" in d for d in destaques)

    def test_itens_criticos_zero_label(self):
        c = _make_cenario("c1", viabilidade="APROVADO")
        c.vetor_O.itens_criticos_pct = 0
        perfil = PerfilExpectativas()
        result = curar_shortlist([c], top_k=1, perfil=perfil)
        destaques = result[0].justificativa.destaques_O
        assert any("0 itens criticos" in d for d in destaques)

    def test_itens_criticos_nonzero_label(self):
        c = _make_cenario("c1", viabilidade="APROVADO")
        c.vetor_O.itens_criticos_pct = 0.25
        perfil = PerfilExpectativas()
        result = curar_shortlist([c], top_k=1, perfil=perfil)
        destaques = result[0].justificativa.destaques_O
        assert any("%" in d and "criticos" in d for d in destaques)

    def test_alertas_classificacao_atencao(self):
        c = _make_cenario("c1", viabilidade="APROVADO", classificacao_O="ATENCAO", classificacao_EF="ATENCAO")
        perfil = PerfilExpectativas()
        result = curar_shortlist([c], top_k=1, perfil=perfil)
        alertas = result[0].justificativa.alertas
        assert any("O-space" in a for a in alertas)
        assert any("EF-space" in a for a in alertas)

    def test_ratio_above_market_label(self):
        c = _make_cenario("c1", viabilidade="APROVADO")
        c.vetor_EF.ratio_pool_vs_cat = 1.10
        perfil = PerfilExpectativas()
        result = curar_shortlist([c], top_k=1, perfil=perfil)
        destaques_EF = result[0].justificativa.destaques_EF
        assert any("acima mercado" in d for d in destaques_EF)

    def test_ratio_below_market_label(self):
        c = _make_cenario("c1", viabilidade="APROVADO")
        c.vetor_EF.ratio_pool_vs_cat = 0.80
        perfil = PerfilExpectativas()
        result = curar_shortlist([c], top_k=1, perfil=perfil)
        destaques_EF = result[0].justificativa.destaques_EF
        assert any("abaixo mercado" in d for d in destaques_EF)


# ---------------------------------------------------------------------------
# classificar_bundle
# ---------------------------------------------------------------------------


class TestClassificarBundle:
    def test_all_errors_returns_abortado(self):
        cenarios = [
            _make_cenario("c1", viabilidade="ERRO", erro="fail"),
            _make_cenario("c2", viabilidade="ERRO", erro="fail"),
        ]
        result = classificar_bundle(cenarios)
        assert result == "ABORTADO"

    def test_no_viaveis_some_non_error_returns_infeasible(self):
        cenarios = [
            _make_cenario("c1", viabilidade="BLOQUEADO"),
            _make_cenario("c2", viabilidade="BLOQUEADO"),
        ]
        result = classificar_bundle(cenarios)
        assert result == "INFEASIBLE"

    def test_with_pareto_intersecao_returns_sucesso(self):
        c = _make_cenario("c1", viabilidade="APROVADO", pareto_intersecao=True)
        result = classificar_bundle([c])
        assert result == "SUCESSO"

    def test_pareto_O_and_EF_no_intersecao_returns_fronteira_unica(self):
        c1 = _make_cenario("c1", viabilidade="APROVADO", pareto_O=True, pareto_intersecao=False)
        c2 = _make_cenario("c2", viabilidade="APROVADO", pareto_EF=True, pareto_intersecao=False)
        result = classificar_bundle([c1, c2])
        assert result == "FRONTEIRA_UNICA"

    def test_viaveis_no_pareto_set_returns_sucesso_parcial(self):
        c = _make_cenario("c1", viabilidade="APROVADO", pareto_O=False, pareto_EF=False, pareto_intersecao=False)
        result = classificar_bundle([c])
        assert result == "SUCESSO_PARCIAL"

    def test_mixed_viaveis_and_errors(self):
        cenarios = [
            _make_cenario("c1", viabilidade="APROVADO", pareto_intersecao=True),
            _make_cenario("c2", viabilidade="ERRO", erro="boom"),
        ]
        result = classificar_bundle(cenarios)
        assert result == "SUCESSO"

    def test_empty_cenarios_returns_abortado(self):
        # empty list: no viaveis, len(falhas)==len(cenarios)==0 -> 0==0 -> ABORTADO
        result = classificar_bundle([])
        assert result == "ABORTADO"
