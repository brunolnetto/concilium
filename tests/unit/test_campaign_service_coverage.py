"""Unit tests para campaign_service.py — funções auxiliares não cobertas (CC=11C, 65.7%).

Cobre:
  _apply_overrides (inputs_ skip, _cpu_alt_ prefix, merge dict, set path)
  _apply_cpu_alt_override (no colon, flat spec, nested spec, no match)
  _apply_scalar (__scale__, __add__, dict merge, plain replace)
  _set_path ([*] wildcard, leaf, intermediate)
  _tendencia (crescente, decrescente, nao_monotona, indeterminado)
  _get_metrica
  _label_variados
  listar_cpus_alternativos
  construir_cubo (faces, resumos, single dim)
"""

from __future__ import annotations

import json
from datetime import UTC

import pytest

from concilium.application.services.campaign.campaign_service import (
    _apply_cpu_alt_override,
    _apply_overrides,
    _apply_scalar,
    _get_metrica,
    _label_variados,
    _set_path,
    _tendencia,
    cenario_id,
    classificar_EF,
    classificar_O,
    construir_cubo,
    listar_cpus_alternativos,
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
# Helpers
# ---------------------------------------------------------------------------


def _make_cenario(
    cid, *, margem=0.12, prazo=40, fe_nec=0.9, gap=0.0, custo_ind=10_000.0, erro=None, viabilidade="APROVADO"
):
    perfil = PerfilExpectativas()
    v_O = VetorEspacoO(prazo_semanas=prazo, fe_nec_medio=fe_nec, itens_criticos_pct=0.0, gap_pool_total=gap)
    v_EF = VetorEspacoEF(margem_pct=margem, custo_indireto=custo_ind, ratio_pool_vs_cat=0.95)
    cl_O = classificar_O(v_O, perfil)
    cl_EF = classificar_EF(v_EF, perfil)
    return CenarioAvaliado(
        cenario_id=cid,
        parametros_variados={"objetivo": cid},
        viabilidade=viabilidade,
        vetor_O=v_O,
        vetor_EF=v_EF,
        classificacao_O=cl_O,
        classificacao_EF=cl_EF,
        erro=erro,
    )


# ---------------------------------------------------------------------------
# _apply_overrides — branches não cobertos
# ---------------------------------------------------------------------------


class TestApplyOverrides:
    def test_inputs_prefix_skipped(self):
        """Chaves que começam com 'inputs_' são ignoradas."""
        spec = {"meta": {"prazo": 10}}
        result = _apply_overrides(spec, {"inputs_cronograma": {"semana": 1}})
        assert "inputs_cronograma" not in result

    def test_per_item_prefix_skipped(self):
        """Chaves _per_item_ são ignoradas."""
        spec = {"meta": {"prazo": 10}}
        result = _apply_overrides(spec, {"_per_item_eap.cpu_id:eap-1": "CPU-ALT"})
        # Não deve modificar spec
        assert result == spec

    def test_cpu_alt_prefix_delegates(self):
        """Chaves _cpu_alt_: delegam para _apply_cpu_alt_override."""
        spec = {"spec": {"eap": [{"item_id": "eap-1", "cpu_id": "CPU-OLD"}]}}
        result = _apply_overrides(spec, {"_cpu_alt_:eap.cpu_id:eap-1": "CPU-NEW"})
        assert result["spec"]["eap"][0]["cpu_id"] == "CPU-NEW"

    def test_merge_dict_values(self):
        """Valor dict em chave existente dict → merge (não substituição)."""
        spec = {"meta": {"prazo": 10, "nome": "X"}}
        result = _apply_overrides(spec, {"meta": {"prazo": 20}})
        assert result["meta"]["prazo"] == 20
        assert result["meta"]["nome"] == "X"  # preservado

    def test_set_nested_path(self):
        """Caminho aninhado com '.' cria intermediários se necessário."""
        spec = {}
        result = _apply_overrides(spec, {"a.b.c": 42})
        assert result["a"]["b"]["c"] == 42

    def test_non_dict_intermediate_replaced(self):
        """Intermediário que não é dict é substituído por {}."""
        spec = {"a": "não_é_dict"}
        result = _apply_overrides(spec, {"a.b": 1})
        assert result["a"]["b"] == 1


class TestApplyCpuAltOverride:
    def test_no_colon_returns_early(self):
        """suffix sem ':' → retorna sem modificar."""
        spec = {"spec": {"eap": [{"item_id": "eap-1", "cpu_id": "OLD"}]}}
        _apply_cpu_alt_override(spec, "_cpu_alt_:sem_colon", "NEW")
        assert spec["spec"]["eap"][0]["cpu_id"] == "OLD"

    def test_flat_spec_eap_used(self):
        """Spec plano (sem chave 'spec') usa spec.get('eap') diretamente."""
        spec = {"eap": [{"item_id": "eap-2", "cpu_id": "OLD"}]}
        _apply_cpu_alt_override(spec, "_cpu_alt_:eap.cpu_id:eap-2", "NEW")
        assert spec["eap"][0]["cpu_id"] == "NEW"

    def test_nested_spec_eap_used(self):
        """Spec com chave 'spec' aninhado usa spec['spec']['eap']."""
        spec = {"spec": {"eap": [{"item_id": "eap-3", "cpu_id": "OLD"}]}}
        _apply_cpu_alt_override(spec, "_cpu_alt_:eap.cpu_id:eap-3", "NEW")
        assert spec["spec"]["eap"][0]["cpu_id"] == "NEW"

    def test_no_matching_item_does_nothing(self):
        """item_id não encontrado → nenhuma modificação."""
        spec = {"eap": [{"item_id": "eap-1", "cpu_id": "OLD"}]}
        _apply_cpu_alt_override(spec, "_cpu_alt_:eap.cpu_id:eap-999", "NEW")
        assert spec["eap"][0]["cpu_id"] == "OLD"

    def test_not_a_list_returns_early(self):
        """eap não é lista → retorna sem modificar."""
        spec = {"eap": "not_a_list"}
        _apply_cpu_alt_override(spec, "_cpu_alt_:eap.cpu_id:eap-1", "NEW")
        assert spec["eap"] == "not_a_list"


# ---------------------------------------------------------------------------
# _apply_scalar
# ---------------------------------------------------------------------------


class TestApplyScalar:
    def test_scale_int_existing(self):
        """__scale__ em campo int → arredonda para cima, preserva int."""
        result = _apply_scalar(10, {"__scale__": 1.5})
        assert result == 15  # ceil(15.0)

    def test_scale_float_existing(self):
        """__scale__ em campo float → resultado float arredondado."""
        result = _apply_scalar(10.0, {"__scale__": 1.5})
        assert result == 15.0

    def test_scale_none_existing_falls_through(self):
        """__scale__ com existing=None cai no replace."""
        result = _apply_scalar(None, {"__scale__": 2.0})
        assert result == {"__scale__": 2.0}  # merge dict (existing é None, não dict)

    def test_add_int(self):
        """__add__ em campo int."""
        result = _apply_scalar(10, {"__add__": 5})
        assert result == 15

    def test_add_float(self):
        """__add__ em campo float."""
        result = _apply_scalar(10.5, {"__add__": 2.5})
        assert abs(result - 13.0) < 0.001

    def test_add_none_falls_through(self):
        """__add__ com existing=None cai no replace."""
        result = _apply_scalar(None, {"__add__": 3})
        assert result == {"__add__": 3}

    def test_dict_merge_when_existing_is_dict(self):
        """Dict sem __scale__/__add__ faz merge se existing é dict."""
        result = _apply_scalar({"a": 1, "b": 2}, {"b": 99, "c": 3})
        assert result == {"a": 1, "b": 99, "c": 3}

    def test_plain_value_replaces(self):
        """Valor simples substitui."""
        assert _apply_scalar("old", "new") == "new"

    def test_scale_type_error_falls_through(self):
        """__scale__ com tipo inválido cai no comportamento padrão."""
        result = _apply_scalar("not_a_number", {"__scale__": 2.0})
        # TypeError → passa para o merge de dict
        assert isinstance(result, dict)


# ---------------------------------------------------------------------------
# _set_path
# ---------------------------------------------------------------------------


class TestSetPath:
    def test_wildcard_applies_to_list(self):
        """[*] aplica a todos os itens de uma lista."""
        items = [{"qty": 1}, {"qty": 2}, {"qty": 3}]
        _set_path(items, ["[*]", "qty"], {"__add__": 10})
        assert items[0]["qty"] == 11
        assert items[2]["qty"] == 13

    def test_wildcard_on_non_list_does_nothing(self):
        """[*] em não-lista não modifica nada."""
        d = {"key": "value"}
        _set_path(d, ["[*]", "key"], "new")
        assert d == {"key": "value"}

    def test_leaf_set_on_dict(self):
        """Folha (sem rest) aplica em dict."""
        d = {"x": 5}
        _set_path(d, ["x"], 10)
        assert d["x"] == 10

    def test_leaf_on_non_dict_does_nothing(self):
        """Folha em não-dict não modifica."""
        lst = [1, 2, 3]
        _set_path(lst, ["key"], 99)
        assert lst == [1, 2, 3]

    def test_empty_parts_does_nothing(self):
        """parts vazio → retorna imediatamente."""
        d = {"x": 1}
        _set_path(d, [], 99)
        assert d == {"x": 1}

    def test_intermediate_creates_if_missing(self):
        """Intermediário ausente → cria {}."""
        d = {}
        _set_path(d, ["a", "b"], 42)
        assert d["a"]["b"] == 42


# ---------------------------------------------------------------------------
# _tendencia
# ---------------------------------------------------------------------------


class TestTendencia:
    def test_crescente(self):
        assert _tendencia([1, 2, 3], [0.1, 0.2, 0.3]) == "crescente"

    def test_decrescente(self):
        assert _tendencia([1, 2, 3], [0.3, 0.2, 0.1]) == "decrescente"

    def test_nao_monotona(self):
        assert _tendencia([1, 2, 3], [0.1, 0.3, 0.2]) == "nao_monotona"

    def test_indeterminado_zero_valid(self):
        """Apenas 0 ou 1 valores válidos → indeterminado."""
        assert _tendencia([1, 2, 3], [None, None, None]) == "indeterminado"
        assert _tendencia([1], [0.5]) == "indeterminado"

    def test_indeterminado_all_none(self):
        assert _tendencia([], []) == "indeterminado"


# ---------------------------------------------------------------------------
# _get_metrica e _label_variados
# ---------------------------------------------------------------------------


class TestGetMetricaELabelVariados:
    def test_get_metrica_from_vetor_O(self):
        c = _make_cenario("c1", prazo=35)
        result = _get_metrica(c, "prazo_semanas")
        assert result == 35

    def test_get_metrica_from_vetor_EF(self):
        c = _make_cenario("c1", margem=0.15)
        result = _get_metrica(c, "margem_pct")
        assert result == pytest.approx(0.15)

    def test_get_metrica_not_found_returns_none(self):
        c = _make_cenario("c1")
        assert _get_metrica(c, "campo_inexistente") is None

    def test_label_variados_scalar(self):
        result = _label_variados({"campo.prazo": 40, "campo.equipes": 3})
        assert "40" in result
        assert "3" in result

    def test_label_variados_dict_value(self):
        result = _label_variados({"campo": {"k": "v"}})
        assert "k=v" in result

    def test_label_variados_empty(self):
        d = {}
        result = _label_variados(d)
        assert result == str(d)


# ---------------------------------------------------------------------------
# listar_cpus_alternativos
# ---------------------------------------------------------------------------


class TestListarCpusAlternativos:
    def test_cpu_not_found_returns_empty(self, tmp_path):
        """Arquivo não existe em nenhuma raiz → retorna []."""
        result = listar_cpus_alternativos("CPU-INEXISTENTE", tmp_path)
        assert result == []

    def test_cpu_with_alternatives(self, tmp_path):
        """Arquivo com cpus_alternativos retorna lista."""
        cpu_dir = tmp_path / "catalogos" / "mendeslobo" / "cpus"
        cpu_dir.mkdir(parents=True)
        cpu_file = cpu_dir / "CPU-BASE.json"
        cpu_file.write_text(json.dumps({"cpus_alternativos": ["CPU-ALT-1", "CPU-ALT-2"]}))
        result = listar_cpus_alternativos("CPU-BASE", tmp_path)
        assert result == ["CPU-ALT-1", "CPU-ALT-2"]

    def test_cpu_without_alternatives(self, tmp_path):
        """Arquivo existe mas sem cpus_alternativos → retorna []."""
        cpu_dir = tmp_path / "catalogos" / "mendeslobo" / "cpus"
        cpu_dir.mkdir(parents=True)
        (cpu_dir / "CPU-X.json").write_text(json.dumps({"codigo": "CPU-X"}))
        result = listar_cpus_alternativos("CPU-X", tmp_path)
        assert result == []

    def test_cpu_in_test_subdir(self, tmp_path):
        """Raiz secundária 'test' é encontrada quando mendeslobo não tem o arquivo."""
        test_dir = tmp_path / "catalogos" / "test" / "cpus"
        test_dir.mkdir(parents=True)
        (test_dir / "CPU-TEST.json").write_text(json.dumps({"cpus_alternativos": ["CPU-B"]}))
        result = listar_cpus_alternativos("CPU-TEST", tmp_path)
        assert result == ["CPU-B"]

    def test_cpu_in_samples_subdir(self, tmp_path):
        """Raiz secundária 'samples' é encontrada."""
        samples_dir = tmp_path / "catalogos" / "samples" / "cpus"
        samples_dir.mkdir(parents=True)
        (samples_dir / "CPU-S.json").write_text(json.dumps({"cpus_alternativos": ["CPU-S2"]}))
        result = listar_cpus_alternativos("CPU-S", tmp_path)
        assert result == ["CPU-S2"]

    def test_malformed_json_returns_empty(self, tmp_path):
        """JSON malformado → retorna []."""
        cpu_dir = tmp_path / "catalogos" / "mendeslobo" / "cpus"
        cpu_dir.mkdir(parents=True)
        (cpu_dir / "CPU-BAD.json").write_text("not valid json {{{")
        result = listar_cpus_alternativos("CPU-BAD", tmp_path)
        assert result == []


# ---------------------------------------------------------------------------
# construir_cubo
# ---------------------------------------------------------------------------


class TestConstruirCubo:
    _BASE_SPEC = {"meta": {"equipes": 1, "prazo": 40}}

    def _make_bundle_single_dim(self, n=2):
        sweep = [ParametroSweep(campo="meta.equipes", valores=[1, 2], scope="scalar")]
        bundle = GoResearchCampaignBundle(
            base_spec=self._BASE_SPEC,
            sweep=sweep,
            perfil_expectativas=PerfilExpectativas(),
        )
        return bundle

    def _make_bundle_two_dims(self):
        sweep = [
            ParametroSweep(campo="meta.equipes", valores=[1, 2], scope="scalar"),
            ParametroSweep(campo="meta.prazo", valores=[30, 40], scope="scalar"),
        ]
        bundle = GoResearchCampaignBundle(
            base_spec=self._BASE_SPEC,
            sweep=sweep,
            perfil_expectativas=PerfilExpectativas(),
        )
        return bundle

    def _make_output(self, bundle, cenarios):
        from datetime import datetime

        from concilium.domain.models.campaign.campaign import CampaignOutputBundle

        return CampaignOutputBundle(
            campaign_id=bundle.campaign_id,
            campaign_version=bundle.campaign_version,
            gerado_em=datetime.now(UTC),
            n_cenarios_avaliados=len(cenarios),
            n_cenarios_viaveis=sum(1 for c in cenarios if c.viabilidade in {"APROVADO", "APROVADO_COM_RESSALVAS"}),
            n_falhas=sum(1 for c in cenarios if c.erro),
            status="SUCESSO",
            cenarios=cenarios,
            shortlist=[],
        )

    def test_single_dim_no_faces(self):
        """1 dimensão → sem faces (faces requerem ≥2 dims)."""
        bundle = self._make_bundle_single_dim()
        c1 = _make_cenario(cenario_id({"meta.equipes": 1}), margem=0.10)
        c2 = _make_cenario(cenario_id({"meta.equipes": 2}), margem=0.12)
        output = self._make_output(bundle, [c1, c2])
        cubo = construir_cubo(bundle, output)
        assert len(cubo.faces) == 0
        assert len(cubo.dimensoes) == 1
        assert len(cubo.celulas) == 2

    def test_two_dims_generates_faces(self):
        """2 dimensões → faces geradas para pares."""
        bundle = self._make_bundle_two_dims()
        cenarios = []
        for eq in [1, 2]:
            for pr in [30, 40]:
                cid = cenario_id({"meta.equipes": eq, "meta.prazo": pr})
                cenarios.append(_make_cenario(cid, margem=0.10, prazo=pr))
        output = self._make_output(bundle, cenarios)
        cubo = construir_cubo(bundle, output)
        assert len(cubo.faces) > 0
        assert len(cubo.resumos_marginais) > 0

    def test_resumos_marginais_computed(self):
        """Resumos marginais contêm tendência calculada."""
        bundle = self._make_bundle_single_dim()
        c1 = _make_cenario(cenario_id({"meta.equipes": 1}), margem=0.10)
        c2 = _make_cenario(cenario_id({"meta.equipes": 2}), margem=0.15)
        output = self._make_output(bundle, [c1, c2])
        cubo = construir_cubo(bundle, output)
        # Deve ter resumos para as métricas disponíveis
        assert len(cubo.resumos_marginais) > 0
        tendencias = {r.tendencia for r in cubo.resumos_marginais}
        assert tendencias.issubset({"crescente", "decrescente", "nao_monotona", "indeterminado"})

    def test_celulas_sem_cenario_viaveis_zero(self):
        """Células sem cenário correspondente têm viabilidade None."""
        bundle = self._make_bundle_single_dim()
        # Só passa c1, c2 fica sem cenário
        c1 = _make_cenario(cenario_id({"meta.equipes": 1}), margem=0.10)
        output = self._make_output(bundle, [c1])
        cubo = construir_cubo(bundle, output)
        celulas_sem = [ce for ce in cubo.celulas if ce.cenario_id is None]
        assert len(celulas_sem) == 1
        assert celulas_sem[0].viabilidade is None

    def test_cobertura_pct_calculated(self):
        """cobertura_pct é calculado corretamente."""
        bundle = self._make_bundle_single_dim()
        c1 = _make_cenario(cenario_id({"meta.equipes": 1}), margem=0.10)
        output = self._make_output(bundle, [c1])
        cubo = construir_cubo(bundle, output)
        assert cubo.cobertura_pct == pytest.approx(0.5)  # 1 de 2

    def test_two_dims_with_missing_cell_no_match_in_face(self):
        """Lines 994-998: célula de grid sem cenário correspondente → matching vazio, row=None."""
        bundle = self._make_bundle_two_dims()
        cenarios = []
        for eq in [1, 2]:
            for pr in [30, 40]:
                if eq == 2 and pr == 40:
                    continue  # deixa essa combinação sem cenário avaliado
                cid = cenario_id({"meta.equipes": eq, "meta.prazo": pr})
                cenarios.append(_make_cenario(cid, margem=0.10, prazo=pr))
        output = self._make_output(bundle, cenarios)
        cubo = construir_cubo(bundle, output)
        assert len(cubo.faces) > 0
        # ao menos uma grade de face deve conter None (célula não avaliada)
        assert any(v is None for face in cubo.faces for row in face.grade for v in row)

    def test_empty_sweep_no_crash(self):
        """Bundle sem sweep → cubo vazio sem crash."""
        bundle = GoResearchCampaignBundle(
            base_spec={},
            sweep=[],
            perfil_expectativas=PerfilExpectativas(),
        )
        from datetime import datetime

        from concilium.domain.models.campaign.campaign import CampaignOutputBundle

        output = CampaignOutputBundle(
            campaign_id=bundle.campaign_id,
            campaign_version=bundle.campaign_version,
            gerado_em=datetime.now(UTC),
            n_cenarios_avaliados=0,
            n_cenarios_viaveis=0,
            n_falhas=0,
            status="SUCESSO",
            cenarios=[],
            shortlist=[],
        )
        cubo = construir_cubo(bundle, output)
        # sweep vazio → gerar_grid retorna 1 produto cartesiano vazio (sem cenário)
        assert cubo.n_celulas_avaliadas == 0
        assert cubo.cobertura_pct == 0.0
        assert len(cubo.faces) == 0
        assert len(cubo.dimensoes) == 0


# ---------------------------------------------------------------------------
# _set_path — line 217->exit (d not dict at intermediate node)
# ---------------------------------------------------------------------------


class TestSetPathDNotDict:
    def test_set_path_list_at_intermediate_no_crash(self):
        """Line 217->exit: d is not dict at intermediate node → skip."""
        from concilium.application.services.campaign.campaign_service import _set_path

        d = [1, 2, 3]  # list, not dict
        _set_path(d, ["key", "sub"], 42)
        assert d == [1, 2, 3]  # unchanged

    def test_set_path_none_at_intermediate(self):
        from concilium.application.services.campaign.campaign_service import _set_path

        _set_path(None, ["key", "sub"], 42)  # no crash


# ---------------------------------------------------------------------------
# _apply_post_load_overrides — lines 238, 243
# ---------------------------------------------------------------------------


class TestApplyPostLoadOverridesBranches:
    def test_non_inputs_key_skipped(self):
        """Line 238: key not starting with 'inputs_' → continue."""
        from types import SimpleNamespace

        from concilium.application.services.campaign.campaign_service import _apply_post_load_overrides

        spec_obj = SimpleNamespace()
        _apply_post_load_overrides(spec_obj, {"meta.prazo": 10})  # not inputs_ → skip
        assert not hasattr(spec_obj, "meta")

    def test_none_attr_skipped(self):
        """Line 243: getattr returns None → continue."""
        from types import SimpleNamespace

        from concilium.application.services.campaign.campaign_service import _apply_post_load_overrides

        spec_obj = SimpleNamespace()  # has no inputs_cronograma attr
        _apply_post_load_overrides(spec_obj, {"inputs_cronograma.deadline_weeks": 52})
        # getattr(spec_obj, "inputs_cronograma", None) = None → skip


# ---------------------------------------------------------------------------
# _set_path_per_item — lines 293->295, 297->exit
# ---------------------------------------------------------------------------


class TestSetPathPerItemBranches:
    def test_leaf_d_not_dict_returns(self):
        """Lines 293->295: not rest, d is not dict → skip (no assignment)."""
        from concilium.application.services.campaign.campaign_service import _set_path_per_item

        d = [1, 2, 3]  # list, not dict
        _set_path_per_item(d, ["key"], 42, "item1")
        assert d == [1, 2, 3]  # unchanged

    def test_intermediate_d_not_dict_returns(self):
        """Line 297->exit: rest non-empty, d is not dict → exit."""
        from concilium.application.services.campaign.campaign_service import _set_path_per_item

        d = [1, 2, 3]
        _set_path_per_item(d, ["key", "sub"], 42, "item1")
        assert d == [1, 2, 3]


# ---------------------------------------------------------------------------
# extrair_vetor_O — lines 318->321 (scheduled_activities fallback, acts empty)
# ---------------------------------------------------------------------------


class TestExtrairVetorO:
    def test_prazo_from_scheduled_activities(self):
        """Lines 318->321: makespan_semanas absent → max(end_week) from acts."""
        from concilium.application.services.campaign.campaign_service import extrair_vetor_O

        canonical = {
            "cronograma": {
                "scheduled_activities": [
                    {"end_week": 45},
                    {"end_week": 52},
                    {"end_week": 38},
                ]
            }
        }
        v = extrair_vetor_O(canonical, None)
        assert v.prazo_semanas == 52

    def test_prazo_none_when_no_acts(self):
        """Line 318->321 False branch: no makespan, no acts → prazo stays None."""
        from concilium.application.services.campaign.campaign_service import extrair_vetor_O

        v = extrair_vetor_O({}, None)
        assert v.prazo_semanas is None

    def test_folga_computed_when_both_available(self):
        """prazo and prazo_contratual → folga = contratual - makespan."""
        from concilium.application.services.campaign.campaign_service import extrair_vetor_O

        canonical = {"cronograma": {"makespan_semanas": 48}}
        v = extrair_vetor_O(canonical, 52)
        assert v.folga_semanas == pytest.approx(4.0)


# ---------------------------------------------------------------------------
# _cubo_analitico_agregado — lines 384->370 (empty aid), 388 (total <= 0)
# ---------------------------------------------------------------------------


class TestCuboAnaliticoAgregadoBranches:
    def test_empty_atividade_id_not_counted(self):
        """Line 384->370: aid='' is skipped (no entry in por_atividade)."""
        from concilium.application.services.campaign.campaign_service import _cubo_analitico_agregado

        canonical = {
            "cubo_analitico": {
                "celulas": [
                    {
                        "componente_bdi": "custo_direto",
                        "valor_rs": 100.0,
                        "categoria_insumo": "mao_obra",
                        "propriedade": "",
                        "atividade_id": "",
                    },
                ]
            }
        }
        result = _cubo_analitico_agregado(canonical)
        assert result["share_mo"] == pytest.approx(1.0)
        assert result.get("hhi") is None  # por_atividade empty → hhi None

    def test_total_zero_returns_empty_dict(self):
        """Line 388: total <= 0 → return {} (no custo_direto celulas)."""
        from concilium.application.services.campaign.campaign_service import _cubo_analitico_agregado

        canonical = {
            "cubo_analitico": {
                "celulas": [
                    {
                        "valor_rs": 0.0,
                        "componente_bdi": "bdi",
                        "categoria_insumo": "",
                        "propriedade": "",
                        "atividade_id": "",
                    }
                ]
            }
        }
        result = _cubo_analitico_agregado(canonical)
        assert result == {}


# ---------------------------------------------------------------------------
# _domina_O, _domina_EF — lines 535, 545
# ---------------------------------------------------------------------------


class TestDominaFunctions:
    def test_domina_O_all_none_returns_false(self):
        """Line 535: all dims are None → return False."""
        from concilium.application.services.campaign.campaign_service import _domina_O

        a = _make_cenario("a", prazo=None, fe_nec=None, gap=None)
        b = _make_cenario("b", prazo=None, fe_nec=None, gap=None)
        assert _domina_O(a, b) is False

    def test_domina_EF_margem_none_returns_false(self):
        """Line 545: margem_pct is None → return False."""
        from concilium.application.services.campaign.campaign_service import _domina_EF

        a = _make_cenario("a", margem=None)
        b = _make_cenario("b", margem=None)
        assert _domina_EF(a, b) is False


# ---------------------------------------------------------------------------
# _build_justificativa — lines 578->580, 582->585, 586->588, 588->594
# ---------------------------------------------------------------------------


class TestBuildJustificativaBranches:
    def _make_with_none_fields(self):
        """CenarioAvaliado with fe_nec=None, itens_criticos_pct=None, margem=None, ratio=None."""
        v_O = VetorEspacoO(
            prazo_semanas=40,
            folga_semanas=None,
            fe_nec_medio=None,
            itens_criticos_pct=None,
            gap_pool_total=0.0,
        )
        v_EF = VetorEspacoEF(margem_pct=None, custo_indireto=None, ratio_pool_vs_cat=None)
        perfil = PerfilExpectativas()
        return CenarioAvaliado(
            cenario_id="xn",
            parametros_variados={},
            viabilidade="APROVADO",
            vetor_O=v_O,
            vetor_EF=v_EF,
            classificacao_O=classificar_O(v_O, perfil),
            classificacao_EF=classificar_EF(v_EF, perfil),
        )

    def test_fe_nec_none_no_fe_destaque(self):
        """Line 578->580: fe_nec_medio is None → no fe_nec destaque."""
        from concilium.application.services.campaign.campaign_service import _build_justificativa

        c = self._make_with_none_fields()
        just = _build_justificativa(c, "test")
        assert not any("fe_nec" in d for d in just.destaques_O)

    def test_itens_criticos_none_no_destaque(self):
        """Line 582->585: itens_criticos_pct is None → no criticos destaque."""
        from concilium.application.services.campaign.campaign_service import _build_justificativa

        c = self._make_with_none_fields()
        just = _build_justificativa(c, "test")
        assert not any("criticos" in d for d in just.destaques_O)

    def test_margem_none_no_margem_destaque(self):
        """Line 586->588: margem_pct is None → no margem destaque."""
        from concilium.application.services.campaign.campaign_service import _build_justificativa

        c = self._make_with_none_fields()
        just = _build_justificativa(c, "test")
        assert not any("Margem" in d for d in just.destaques_EF)

    def test_ratio_none_no_pool_destaque(self):
        """Line 588->594: ratio_pool_vs_cat is None → no pool destaque."""
        from concilium.application.services.campaign.campaign_service import _build_justificativa

        c = self._make_with_none_fields()
        just = _build_justificativa(c, "test")
        assert not any("Pool" in d for d in just.destaques_EF)

    def test_ratio_above_1_above_market_label(self):
        """Line 592: ratio > 1 → 'acima mercado' label."""
        from concilium.application.services.campaign.campaign_service import _build_justificativa

        v_O = VetorEspacoO(prazo_semanas=40)
        v_EF = VetorEspacoEF(margem_pct=0.12, ratio_pool_vs_cat=1.2)
        perfil = PerfilExpectativas()
        c = CenarioAvaliado(
            cenario_id="r2",
            parametros_variados={},
            viabilidade="APROVADO",
            vetor_O=v_O,
            vetor_EF=v_EF,
            classificacao_O=classificar_O(v_O, perfil),
            classificacao_EF=classificar_EF(v_EF, perfil),
        )
        just = _build_justificativa(c, "test")
        assert any("acima mercado" in d for d in just.destaques_EF)

    def test_itens_criticos_nonzero_pct_destaque(self):
        """Line 582->583: non-zero non-None itens_criticos → percentage destaque."""
        from concilium.application.services.campaign.campaign_service import _build_justificativa

        v_O = VetorEspacoO(prazo_semanas=40, itens_criticos_pct=0.3)
        v_EF = VetorEspacoEF(margem_pct=0.12)
        perfil = PerfilExpectativas()
        c = CenarioAvaliado(
            cenario_id="cr",
            parametros_variados={},
            viabilidade="APROVADO",
            vetor_O=v_O,
            vetor_EF=v_EF,
            classificacao_O=classificar_O(v_O, perfil),
            classificacao_EF=classificar_EF(v_EF, perfil),
        )
        just = _build_justificativa(c, "test")
        assert any("criticos" in d for d in just.destaques_O)


# ---------------------------------------------------------------------------
# executar_campanha — lines 810-871 (via mocked _run_campaign_task)
# ---------------------------------------------------------------------------


class TestExecutarCampanha:
    def test_executar_campanha_basic(self):
        """Lines 810-871: full executar_campanha with mocked task runner."""
        from unittest.mock import patch

        from concilium.application.services.campaign.campaign_service import executar_campanha
        from concilium.domain.models.campaign.campaign import (
            GoResearchCampaignBundle,
            ParametroSweep,
            PerfilExpectativas,
        )

        bundle = GoResearchCampaignBundle(
            base_spec={"slug": "test-spec", "id": "test-spec"},
            sweep=[ParametroSweep(campo="meta.prazo", valores=[40, 52])],
            perfil_expectativas=PerfilExpectativas(),
            top_k=2,
        )

        prebuilt = _make_cenario("c1", margem=0.12, prazo=40)

        with patch(
            "concilium.application.services.campaign.campaign_service._runner._run_campaign_task", return_value=prebuilt
        ):
            output = executar_campanha(bundle, config_root="/tmp", projects_root="/tmp", num_workers=1)

        assert output.n_cenarios_avaliados == 2
        assert output.status in {"SUCESSO", "SUCESSO_PARCIAL", "FRONTEIRA_UNICA", "INCONCLUSO", "BLOQUEADO"}

    def test_executar_campanha_cardinality_warning(self):
        """Lines 816-827: cardinality > threshold → warning emitted."""
        import warnings
        from unittest.mock import MagicMock, patch

        from concilium.application.services.campaign.campaign_service import executar_campanha
        from concilium.domain.models.campaign.campaign import (
            GoResearchCampaignBundle,
            ParametroSweep,
            PerfilExpectativas,
        )

        bundle = GoResearchCampaignBundle(
            base_spec={"slug": "big"},
            sweep=[ParametroSweep(campo="meta.x", valores=list(range(20)))],
            perfil_expectativas=PerfilExpectativas(),
        )

        cfg_mock = MagicMock()
        cfg_mock.cardinality_threshold = 5
        cfg_mock.max_workers = 3
        cfg_mock.seconds_per_scenario = 10

        prebuilt = _make_cenario("c1")

        with (
            patch(
                "concilium.application.services.campaign.campaign_service._runner._run_campaign_task",
                return_value=prebuilt,
            ),
            patch("concilium.infrastructure.settings.get_campaign", return_value=cfg_mock),
        ):
            with warnings.catch_warnings(record=True) as w:
                warnings.simplefilter("always")
                executar_campanha(bundle, config_root="/tmp", projects_root="/tmp", num_workers=1)

        assert any("cardinality" in str(warning.message).lower() for warning in w)


# ---------------------------------------------------------------------------
# _run_campaign_task — lines 692-792 (module-level task, picklável)
# ---------------------------------------------------------------------------


class TestRunCampaignTask:
    def _make_task(self, tmp_path, *, spec_v=None):
        from concilium.application.services.campaign.campaign_service import _CampaignTask

        return _CampaignTask(
            spec_v=spec_v or {"slug": "myproj", "id": "myproj", "meta": {"projeto": "Meu Projeto"}},
            variados={"meta.prazo": 40},
            config_root=str(tmp_path / "config"),
            projects_root=str(tmp_path / "projetos"),
            prazo_contratual=40,
            perfil=PerfilExpectativas(),
            procurement_intent="rfp",
            do_reset=True,
        )

    def test_success_path_exact_slug_canonical(self, tmp_path):
        """Lines 728-768: happy path, canonical.json encontrado no slug exato (primeira tentativa)."""
        from unittest.mock import MagicMock, patch

        from concilium.application.services.campaign.campaign_service import _run_campaign_task

        task = self._make_task(tmp_path)
        projects_root = tmp_path / "projetos"
        proj_dir = projects_root / "myproj-abc123" / "v1"
        proj_dir.mkdir(parents=True)
        (proj_dir / "canonical.json").write_text(json.dumps({"foo": "bar"}))

        spec_obj = MagicMock()
        spec_obj.slug = "myproj-abc123"

        runner_instance = MagicMock()
        runner_instance.run.return_value = {"quality_gates": {"decision": "APROVADO"}}

        with (
            patch(
                "concilium.application.benchmarks.spec.spec_loader.load_spec_from_dict",
                return_value=spec_obj,
            ),
            patch(
                "concilium.application.benchmarks.execution.runner.BenchmarkRunner",
                return_value=runner_instance,
            ),
            patch(
                "concilium.application.services.campaign.campaign_service._task._apply_post_load_overrides",
            ),
        ):
            result = _run_campaign_task(task)

        assert result.viabilidade == "APROVADO"
        assert result.erro is None
        # cleanup deve ter removido o diretório do projeto de cenário
        assert not proj_dir.parent.exists()

    def test_success_path_invokes_silent_report_printer(self, tmp_path):
        """Line 701: the local `_Silent.print()` override (`pass`) is only ever
        invoked through the real BenchmarkRunner.run() -> report_printer.print()
        call — a MagicMock runner never exercises it. Use a lightweight fake
        BenchmarkRunner that actually calls report_printer.print(), matching the
        production contract, so the override body itself gets covered."""
        from unittest.mock import MagicMock, patch

        from concilium.application.services.campaign.campaign_service import _run_campaign_task

        task = self._make_task(tmp_path)
        projects_root = tmp_path / "projetos"
        proj_dir = projects_root / "myproj-abc123" / "v1"
        proj_dir.mkdir(parents=True)
        (proj_dir / "canonical.json").write_text(json.dumps({"foo": "bar"}))

        spec_obj = MagicMock()
        spec_obj.slug = "myproj-abc123"

        class _FakeRunner:
            def __init__(self, **kwargs):
                self._printer = kwargs["report_printer"]

            def run(self, *_a, **_k):
                report = {"quality_gates": {"decision": "APROVADO"}}
                self._printer.print(report)  # exercises _Silent.print's `pass` body
                return report

        with (
            patch(
                "concilium.application.benchmarks.spec.spec_loader.load_spec_from_dict",
                return_value=spec_obj,
            ),
            patch(
                "concilium.application.benchmarks.execution.runner.BenchmarkRunner",
                _FakeRunner,
            ),
            patch(
                "concilium.application.services.campaign.campaign_service._task._apply_post_load_overrides",
            ),
        ):
            result = _run_campaign_task(task)

        assert result.viabilidade == "APROVADO"

    def test_success_path_canonical_found_via_upper_variant(self, tmp_path):
        """Lines 744-748: primeira tentativa (slug exato) falha, encontra via .upper()."""
        from unittest.mock import MagicMock, patch

        from concilium.application.services.campaign.campaign_service import _run_campaign_task

        task = self._make_task(tmp_path)
        projects_root = tmp_path / "projetos"
        proj_dir = projects_root / "MYPROJ-ABC123" / "v1"
        proj_dir.mkdir(parents=True)
        (proj_dir / "canonical.json").write_text(json.dumps({"foo": "bar"}))

        spec_obj = MagicMock()
        spec_obj.slug = "myproj-abc123"

        runner_instance = MagicMock()
        runner_instance.run.return_value = {"quality_gates": {"decision": "BLOQUEADO_COM_INVESTIGACAO"}}

        with (
            patch(
                "concilium.application.benchmarks.spec.spec_loader.load_spec_from_dict",
                return_value=spec_obj,
            ),
            patch(
                "concilium.application.benchmarks.execution.runner.BenchmarkRunner",
                return_value=runner_instance,
            ),
            patch(
                "concilium.application.services.campaign.campaign_service._task._apply_post_load_overrides",
            ),
        ):
            result = _run_campaign_task(task)

        assert result.viabilidade == "BLOQUEADO_COM_INVESTIGACAO"
        # cleanup também deve encontrar via variante upper e remover
        assert not proj_dir.parent.exists()

    def test_no_canonical_found_defaults_bloqueado_decision(self, tmp_path):
        """Nenhum canonical.json existe → decision default 'BLOQUEADO' (via_map)."""
        from unittest.mock import MagicMock, patch

        from concilium.application.services.campaign.campaign_service import _run_campaign_task

        task = self._make_task(tmp_path)
        spec_obj = MagicMock()
        spec_obj.slug = "myproj-abc123"

        runner_instance = MagicMock()
        runner_instance.run.return_value = {"quality_gates": {}}

        with (
            patch(
                "concilium.application.benchmarks.spec.spec_loader.load_spec_from_dict",
                return_value=spec_obj,
            ),
            patch(
                "concilium.application.benchmarks.execution.runner.BenchmarkRunner",
                return_value=runner_instance,
            ),
            patch(
                "concilium.application.services.campaign.campaign_service._task._apply_post_load_overrides",
            ),
        ):
            result = _run_campaign_task(task)

        assert result.viabilidade == "BLOQUEADO"

    def test_exception_path_produces_erro_cenario(self, tmp_path):
        """Lines 769-778: exceção durante load_spec_from_dict → CenarioAvaliado com erro."""
        from unittest.mock import patch

        from concilium.application.services.campaign.campaign_service import _run_campaign_task

        task = self._make_task(tmp_path)

        with patch(
            "concilium.application.benchmarks.spec.spec_loader.load_spec_from_dict",
            side_effect=RuntimeError("boom"),
        ):
            result = _run_campaign_task(task)

        assert result.viabilidade == "ERRO"
        assert result.classificacao_O == "CRITICO"
        assert result.classificacao_EF == "FORA_EXPECTATIVA"
        assert result.erro == "boom"

    def test_exception_path_no_actual_slug_cleans_scenario_slug_only(self, tmp_path):
        """Lines 780-790: exceção antes de obter actual_project_slug → cleanup usa só scenario_slug."""
        from unittest.mock import patch

        from concilium.application.services.campaign.campaign_service import _run_campaign_task

        task = self._make_task(tmp_path)
        cid = task.variados
        from concilium.application.services.campaign.campaign_service import cenario_id

        scenario_slug = f"myproj-{cenario_id(cid)[:6]}"
        projects_root = tmp_path / "projetos"
        proj_dir = projects_root / scenario_slug
        proj_dir.mkdir(parents=True)

        with patch(
            "concilium.application.benchmarks.spec.spec_loader.load_spec_from_dict",
            side_effect=RuntimeError("boom"),
        ):
            result = _run_campaign_task(task)

        assert result.viabilidade == "ERRO"
        assert not proj_dir.exists()


# ---------------------------------------------------------------------------
# sugerir_levers_cpu_alternativo — lines 1108, 1112
# ---------------------------------------------------------------------------


class TestSugerirLeversCpuAlternativo:
    def test_non_dict_item_skipped(self):
        """Line 1108: non-dict item in eap → continue."""
        from concilium.application.services.campaign.campaign_service import sugerir_levers_cpu_alternativo

        spec = {"eap": ["string_item", None, 42]}
        result = sugerir_levers_cpu_alternativo(spec, config_root="/tmp")
        assert result == []

    def test_missing_item_id_skipped(self):
        """Line 1112: item without item_id or cpu_id → continue."""
        from concilium.application.services.campaign.campaign_service import sugerir_levers_cpu_alternativo

        spec = {"eap": [{"item_id": "", "cpu_id": "CPU1"}, {"item_id": "I1", "cpu_id": ""}]}
        result = sugerir_levers_cpu_alternativo(spec, config_root="/tmp")
        assert result == []
