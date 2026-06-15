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
import pytest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from concilium.application.services.campaign.campaign_service import (
    _apply_overrides,
    _apply_cpu_alt_override,
    _apply_scalar,
    _set_path,
    _tendencia,
    _get_metrica,
    _label_variados,
    listar_cpus_alternativos,
    construir_cubo,
    classificar_O,
    classificar_EF,
    calcular_pareto,
    curar_shortlist,
    cenario_id,
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

def _make_cenario(cid, *, margem=0.12, prazo=40, fe_nec=0.9, gap=0.0, custo_ind=10_000.0, erro=None, viabilidade="APROVADO"):
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
        spec = {
            "spec": {
                "eap": [{"item_id": "eap-1", "cpu_id": "CPU-OLD"}]
            }
        }
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
        from concilium.domain.models.campaign.campaign import CampaignOutputBundle
        from datetime import datetime, timezone
        return CampaignOutputBundle(
            campaign_id=bundle.campaign_id,
            campaign_version=bundle.campaign_version,
            gerado_em=datetime.now(timezone.utc),
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

    def test_empty_sweep_no_crash(self):
        """Bundle sem sweep → cubo vazio sem crash."""
        bundle = GoResearchCampaignBundle(
            base_spec={},
            sweep=[],
            perfil_expectativas=PerfilExpectativas(),
        )
        from concilium.domain.models.campaign.campaign import CampaignOutputBundle
        from datetime import datetime, timezone
        output = CampaignOutputBundle(
            campaign_id=bundle.campaign_id,
            campaign_version=bundle.campaign_version,
            gerado_em=datetime.now(timezone.utc),
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
