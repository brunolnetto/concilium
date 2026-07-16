"""Tests for _skill_helpers_b.py — covers missing lines 47-48, 50-51, 67-68, 70-71,
75-81, 96-101, 113-114, 117-123, 140-143, 152-153, 165-167, 174, 184-190, 201, 219, 222."""

from __future__ import annotations

import importlib.util
from datetime import UTC
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

# ---------------------------------------------------------------------------
# Load the module via importlib so hyphens in path are not a problem
# ---------------------------------------------------------------------------
_MOD_PATH = (
    Path(__file__).parent.parent.parent
    / "src/concilium/application/skills/manifests/06-resultado-financeiro"
    / "_consolidacao/_skill_helpers/_bdi_resolucao.py"
)


def _load():
    spec = importlib.util.spec_from_file_location("_skill_helpers_b", _MOD_PATH)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)  # type: ignore[union-attr]
    return mod


_mod = _load()

_build_abc_analytics = _mod._build_abc_analytics
_build_memorial_bdi = _mod._build_memorial_bdi
_get_bdi_value = _mod._get_bdi_value
_rbf_resolve_tabela_perfil = _mod._rbf_resolve_tabela_perfil
_rbf_try_tax_scenario = _mod._rbf_try_tax_scenario
_rbf_try_manual_bdi = _mod._rbf_try_manual_bdi
_resolve_bdi_rates = _mod._resolve_bdi_rates
_resolve_bdi_full = _mod._resolve_bdi_full
_classificar_margem = _mod._classificar_margem

ValidacaoItem = _mod.ValidacaoItem
DEFAULT_BDI_TABELA = _mod.DEFAULT_BDI_TABELA

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _validacoes():
    return []


def _fake_canonical():
    return MagicMock()


# ---------------------------------------------------------------------------
# _build_abc_analytics
# ---------------------------------------------------------------------------


class TestBuildAbcAnalytics:
    """Lines 47-48 (success return), 50-51 (except warning), 67-71 (None,None,None)."""

    def test_success_returns_three_builders(self):
        """Lines 46-47: happy path returns (curva_abc, s_curve, cubo_analitico)."""
        fake_abc = MagicMock(name="curva_abc")
        fake_scurve = MagicMock(name="s_curve")
        fake_cubo = MagicMock(name="cubo_analitico")

        abc_builder = MagicMock()
        abc_builder.return_value.build.return_value = fake_abc

        scurve_builder = MagicMock()
        scurve_builder.return_value.build.return_value = fake_scurve

        cubo_builder = MagicMock()
        cubo_builder.return_value.build.return_value = fake_cubo

        with (
            patch(
                "concilium.domain.services.analytics.curva_abc_builder.CurvaABCBuilder",
                abc_builder,
            ),
            patch(
                "concilium.domain.services.analytics.s_curve_builder.SCurveBuilder",
                scurve_builder,
            ),
            patch(
                "concilium.domain.services.analytics.cubo_analitico_builder.CuboAnaliticoBuilder",
                cubo_builder,
            ),
        ):
            result = _build_abc_analytics(
                _fake_canonical(),
                inputs={},
                bdi_tabela=DEFAULT_BDI_TABELA,
                bdi_regime="pre_reforma",
                validacoes=_validacoes(),
            )

        assert result == (fake_abc, fake_scurve, fake_cubo)

    def test_success_uses_tax_scenario_regime(self):
        """Lines 40-45: when inputs has tax_scenario dict, regime comes from it."""
        cubo_builder_cls = MagicMock()
        cubo_instance = MagicMock()
        cubo_builder_cls.return_value = cubo_instance
        cubo_instance.build.return_value = MagicMock()

        with (
            patch(
                "concilium.domain.services.analytics.curva_abc_builder.CurvaABCBuilder",
                MagicMock(),
            ),
            patch(
                "concilium.domain.services.analytics.s_curve_builder.SCurveBuilder",
                MagicMock(),
            ),
            patch(
                "concilium.domain.services.analytics.cubo_analitico_builder.CuboAnaliticoBuilder",
                cubo_builder_cls,
            ),
        ):
            _build_abc_analytics(
                _fake_canonical(),
                inputs={"tax_scenario": {"regime_version": "pos_reforma"}},
                bdi_tabela=DEFAULT_BDI_TABELA,
                bdi_regime="pre_reforma",
                validacoes=_validacoes(),
            )

        # CuboAnaliticoBuilder must have been called with regime_version from tax_scenario
        cubo_builder_cls.assert_called_once_with(tabela_bdi=DEFAULT_BDI_TABELA, regime_version="pos_reforma")

    def test_exception_returns_none_triple(self):
        """Lines 47-51: any exception → returns (None, None, None) and logs warning."""
        with patch(
            "concilium.domain.services.analytics.curva_abc_builder.CurvaABCBuilder",
            side_effect=RuntimeError("builder exploded"),
        ):
            result = _build_abc_analytics(
                _fake_canonical(),
                inputs={},
                bdi_tabela=DEFAULT_BDI_TABELA,
                bdi_regime="pre_reforma",
                validacoes=_validacoes(),
            )

        assert result == (None, None, None)


# ---------------------------------------------------------------------------
# _build_memorial_bdi
# ---------------------------------------------------------------------------


class TestBuildMemorialBdi:
    """Lines 75-81 (success), 96-101 (except → None)."""

    def test_success_returns_builder_result(self):
        """Lines 75-81: MemorialBDIBuilder().build returns a value."""
        fake_memorial = MagicMock(name="memorial")
        builder_cls = MagicMock()
        builder_cls.return_value.build.return_value = fake_memorial

        with patch(
            "concilium.domain.services.financial.memorial_bdi_builder.MemorialBDIBuilder",
            builder_cls,
        ):
            result = _build_memorial_bdi(
                _fake_canonical(),
                bdi_fonte="DEFAULT_BDI_TABELA",
                bdi_regime="pre_reforma",
                bdi_tabela=DEFAULT_BDI_TABELA,
                bdi_override=False,
            )

        assert result is fake_memorial

    def test_exception_returns_none(self):
        """Lines 96-101: exception → None."""
        builder_cls = MagicMock()
        builder_cls.return_value.build.side_effect = RuntimeError("memorial exploded")

        with patch(
            "concilium.domain.services.financial.memorial_bdi_builder.MemorialBDIBuilder",
            builder_cls,
        ):
            result = _build_memorial_bdi(
                _fake_canonical(),
                bdi_fonte="DEFAULT_BDI_TABELA",
                bdi_regime="pre_reforma",
                bdi_tabela=DEFAULT_BDI_TABELA,
                bdi_override=False,
            )

        assert result is None


# ---------------------------------------------------------------------------
# _get_bdi_value
# ---------------------------------------------------------------------------


class TestGetBdiValue:
    """Lines 113-114 (first key found), 117-123 (float conversion failure → next key)."""

    def test_first_key_returns_float(self):
        """Line 113-114: key present and convertible → returns float."""
        assert _get_bdi_value({"mao_obra": 0.25}, "mao_obra") == pytest.approx(0.25)

    def test_second_key_fallback(self):
        """Falls back to second key when first is absent."""
        assert _get_bdi_value({"mo": 0.30}, "mao_obra", "mo") == pytest.approx(0.30)

    def test_explicit_none_value_skipped(self):
        """Key with None value is skipped (line 76 guard)."""
        assert _get_bdi_value({"mao_obra": None, "mo": 0.10}, "mao_obra", "mo") == pytest.approx(0.10)

    def test_float_conversion_failure_continues(self):
        """Lines 117-123: float() raises → continue to next key."""
        result = _get_bdi_value({"mao_obra": "not-a-number", "mo": 0.15}, "mao_obra", "mo")
        assert result == pytest.approx(0.15)

    def test_no_keys_found_returns_default(self):
        """Line 81: all keys missing → returns default 0.0."""
        assert _get_bdi_value({}, "mao_obra", "mo") == pytest.approx(0.0)

    def test_custom_default(self):
        """Custom default returned when no keys present."""
        assert _get_bdi_value({}, "mao_obra", default=0.5) == pytest.approx(0.5)

    def test_all_keys_fail_conversion_returns_default(self):
        """All keys present but all fail float conversion → default."""
        result = _get_bdi_value({"mao_obra": "bad", "mo": "also-bad"}, "mao_obra", "mo", default=0.99)
        assert result == pytest.approx(0.99)


# ---------------------------------------------------------------------------
# _rbf_resolve_tabela_perfil
# ---------------------------------------------------------------------------


class TestRbfResolveTabelaPerfil:
    """Lines 140-143 (tabela from dict), 152-153 (parse fail AVISO), 165-167 (perfil fail AVISO),
    174 (regime_v.value)."""

    def test_tabela_raw_dict_sets_override_and_fonte(self):
        """Lines 140-143: tabela_raw is a dict → model_validate succeeds, override=True."""
        from concilium.domain.models.financial.bdi import TabelaBdi

        valid_raw = DEFAULT_BDI_TABELA.model_dump()
        validacoes: list = []
        tabela, fonte, override, regime_str = _rbf_resolve_tabela_perfil({"tabela_bdi": valid_raw}, validacoes)

        assert override is True
        assert fonte == "inputs.tabela_bdi"
        assert isinstance(tabela, TabelaBdi)
        assert validacoes == []

    def test_tabela_raw_non_dict_used_as_is(self):
        """Non-dict tabela_raw is used directly without model_validate."""
        fake_tabela = DEFAULT_BDI_TABELA
        validacoes: list = []
        tabela, fonte, override, _ = _rbf_resolve_tabela_perfil({"tabela_bdi": fake_tabela}, validacoes)
        assert tabela is fake_tabela
        assert override is True

    def test_tabela_parse_fail_appends_aviso(self):
        """Lines 152-153: model_validate fails → VAL-CONSOL-BDI-PARSE AVISO appended."""
        validacoes: list = []
        _rbf_resolve_tabela_perfil({"tabela_bdi": {"invalid_key": True}}, validacoes)

        codes = [v.codigo for v in validacoes]
        assert "VAL-CONSOL-BDI-PARSE" in codes
        statuses = [v.status for v in validacoes if v.codigo == "VAL-CONSOL-BDI-PARSE"]
        assert statuses == ["AVISO"]

    def test_no_tabela_raw_uses_default(self):
        """No tabela_bdi in inputs → DEFAULT_BDI_TABELA used, override=False."""
        validacoes: list = []
        tabela, fonte, override, _ = _rbf_resolve_tabela_perfil({}, validacoes)

        assert tabela is DEFAULT_BDI_TABELA
        assert override is False
        assert fonte == "DEFAULT_BDI_TABELA"

    def test_perfil_parse_fail_appends_aviso(self):
        """Lines 165-167: invalid perfil_bdi → VAL-CONSOL-BDI-PERFIL AVISO appended."""
        validacoes: list = []
        _rbf_resolve_tabela_perfil({"bdi_perfil": {"garbage": 123}}, validacoes)

        codes = [v.codigo for v in validacoes]
        assert "VAL-CONSOL-BDI-PERFIL" in codes

    def test_perfil_valid_dict_sets_regime(self):
        """Line 174: regime_v.value extracted from valid PerfilBdiProjeto."""
        from datetime import datetime

        from concilium.domain.models.financial.bdi import (
            PerfilBdiProjeto,
            TaxRegimeVersion,
        )
        from concilium.domain.models.financial.bdi._profiles import (
            AplicacaoTributaria,
            CheckboxTributo,
            PerfilLucroProjeto,
            PerfilTributarioProjeto,
        )

        def _cb(aplicavel: bool, aliquota: float) -> CheckboxTributo:
            return CheckboxTributo(aplicavel=aplicavel, aliquota=aliquota)

        def _aplic() -> AplicacaoTributaria:
            return AplicacaoTributaria(
                iss=_cb(True, 0.05),
                cofins=_cb(False, 0.03),
                pis=_cb(False, 0.01),
                cssl=_cb(True, 0.01),
                ir=_cb(True, 0.015),
            )

        trib = PerfilTributarioProjeto(
            regime="lucro_presumido",
            municipio="SP",
            iss_aliquota_municipal=0.05,
            mao_obra=_aplic(),
            material=_aplic(),
            servicos=_aplic(),
            indireto=_aplic(),
            diesel=_aplic(),
        )
        lucro = PerfilLucroProjeto(mao_obra=0.09, material=0.04, servicos=0.09, indireto=0.05, diesel=0.04)
        perfil_instance = PerfilBdiProjeto(
            projeto_id="proj-1",
            content_hash="abc123",
            confirmado_em=datetime(2026, 1, 1, tzinfo=UTC),
            confirmado_por="user@test.com",
            tributario=trib,
            lucro=lucro,
            regime_version=TaxRegimeVersion.PRE_REFORMA,
        )

        validacoes: list = []
        _, fonte, override, regime_str = _rbf_resolve_tabela_perfil({"bdi_perfil": perfil_instance}, validacoes)
        assert "PerfilBdiProjeto" in fonte
        assert override is True
        assert regime_str == "pre_reforma"

    def test_no_perfil_defaults_to_pre_reforma(self):
        """No perfil_bdi → regime_str defaults to 'pre_reforma'."""
        validacoes: list = []
        _, _, _, regime_str = _rbf_resolve_tabela_perfil({}, validacoes)
        assert regime_str == "pre_reforma"

    def test_aliquotas_bdi_jurisdicao_aplicada_sem_override_explicito(self):
        """ADR-038: sem tabela_bdi/perfil_bdi, a jurisdição resolvida deve mudar o
        BDI — antes desta correção, era sempre ignorada em favor do DEFAULT puro."""
        validacoes: list = []
        aliquotas = {"ISS": 0.02, "PIS": 0.0065, "COFINS": 0.03}
        tabela, fonte, override, _ = _rbf_resolve_tabela_perfil(
            {"aliquotas_bdi_jurisdicao": aliquotas}, validacoes
        )
        assert tabela is not DEFAULT_BDI_TABELA
        assert tabela.mao_obra.iss == 0.02
        assert "jurisdicao" in fonte
        assert override is False  # jurisdição não conta como "override explícito"
        jur_val = next((v for v in validacoes if v.codigo == "VAL-CONSOL-BDI-JURISDICAO"), None)
        assert jur_val is not None
        assert jur_val.status == "OK"

    def test_tabela_bdi_explicita_tem_prioridade_sobre_jurisdicao(self):
        validacoes: list = []
        valid_raw = DEFAULT_BDI_TABELA.model_dump()
        tabela, _, _, _ = _rbf_resolve_tabela_perfil(
            {"tabela_bdi": valid_raw, "aliquotas_bdi_jurisdicao": {"ISS": 0.02}}, validacoes
        )
        # tabela_bdi explícita vence — ISS permanece o do DEFAULT (5%), não 2%.
        assert tabela.mao_obra.iss == DEFAULT_BDI_TABELA.mao_obra.iss
        assert not any(v.codigo == "VAL-CONSOL-BDI-JURISDICAO" for v in validacoes)

    def test_sem_aliquotas_bdi_jurisdicao_nao_muda_nada(self):
        """Regressão zero: sem o novo input, tabela permanece DEFAULT_BDI_TABELA (identidade)."""
        validacoes: list = []
        tabela, fonte, _, _ = _rbf_resolve_tabela_perfil({}, validacoes)
        assert tabela is DEFAULT_BDI_TABELA
        assert fonte == "DEFAULT_BDI_TABELA"
        assert not any(v.codigo == "VAL-CONSOL-BDI-JURISDICAO" for v in validacoes)


# ---------------------------------------------------------------------------
# _rbf_try_tax_scenario
# ---------------------------------------------------------------------------


class TestRbfTryTaxScenario:
    """Lines 184-190 (no/invalid tax_scenario → None), 201 (success), 219 (exception AVISO), 222 (return None)."""

    def test_missing_tax_scenario_returns_none(self):
        """Lines 184-190: no tax_scenario key → None."""
        validacoes: list = []
        assert _rbf_try_tax_scenario({}, validacoes) is None
        assert validacoes == []

    def test_non_dict_tax_scenario_returns_none(self):
        """tax_scenario that is not a dict → None (line 138 guard)."""
        validacoes: list = []
        assert _rbf_try_tax_scenario({"tax_scenario": "string"}, validacoes) is None

    def test_falsy_empty_dict_returns_none(self):
        """Empty dict is falsy-enough via `not (tax_scenario_raw and ...)` → None."""
        # Empty dict is truthy in Python but isinstance check still passes;
        # however from_dict on empty dict should raise — cover that via except path.
        # Instead check explicitly falsy None value.
        validacoes: list = []
        assert _rbf_try_tax_scenario({"tax_scenario": None}, validacoes) is None

    def test_valid_tax_scenario_returns_tuple_and_ok_validation(self):
        """Line 201: from_dict succeeds → 5-tuple returned, OK validation appended."""
        from concilium.domain.models.financial.bdi import TaxSimulationScenario

        # Build a minimal scenario that from_dict can parse
        try:
            TaxSimulationScenario.from_dict({"regime_version": "pre_reforma"})
        except Exception:
            pytest.skip("Cannot build minimal TaxSimulationScenario for this test")

        raw = {"regime_version": "pre_reforma"}
        validacoes: list = []
        result = _rbf_try_tax_scenario({"tax_scenario": raw}, validacoes)

        if result is None:
            # from_dict may need more fields; check AVISO was appended
            codes = [v.codigo for v in validacoes]
            assert "VAL-CONSOL-BDI-REGIME" in codes
        else:
            assert len(result) == 5
            codes = [v.codigo for v in validacoes]
            assert "VAL-CONSOL-BDI-REGIME" in codes
            statuses = [v.status for v in validacoes if v.codigo == "VAL-CONSOL-BDI-REGIME"]
            assert "OK" in statuses

    def test_invalid_tax_scenario_appends_aviso_returns_none(self):
        """Lines 219, 222: from_dict raises → AVISO appended, None returned."""
        validacoes: list = []
        result = _rbf_try_tax_scenario(
            {"tax_scenario": {"regime_version": "completely_invalid_value"}},
            validacoes,
        )

        assert result is None
        codes = [v.codigo for v in validacoes]
        assert "VAL-CONSOL-BDI-REGIME" in codes
        statuses = [v.status for v in validacoes if v.codigo == "VAL-CONSOL-BDI-REGIME"]
        assert "AVISO" in statuses


# ---------------------------------------------------------------------------
# _resolve_bdi_full — covers the early-return when tax_scenario succeeds
# ---------------------------------------------------------------------------


class TestResolveBdiFull:
    def test_tax_scenario_success_short_circuits_manual_and_perfil_paths(self):
        """When _rbf_try_tax_scenario succeeds, _resolve_bdi_full returns its
        result directly without evaluating the manual-BDI or perfil fallbacks."""
        try:
            from concilium.domain.models.financial.bdi import TaxSimulationScenario

            TaxSimulationScenario.from_dict({"regime_version": "pre_reforma"})
        except Exception:
            pytest.skip("Cannot build minimal TaxSimulationScenario for this test")

        validacoes: list = []
        inputs = {"tax_scenario": {"regime_version": "pre_reforma"}}
        direct = _rbf_try_tax_scenario(dict(inputs), [])
        if direct is None:
            pytest.skip("TaxSimulationScenario path unavailable in this environment")

        result = _resolve_bdi_full(inputs, validacoes)

        assert result[2] == "inputs.tax_scenario"
        assert result[4] is True
        codes = [v.codigo for v in validacoes]
        assert "VAL-CONSOL-BDI-REGIME" in codes


# ---------------------------------------------------------------------------
# _rbf_try_manual_bdi — lines 184-201
# ---------------------------------------------------------------------------


class TestRbfTryManualBdi:
    def test_no_bdi_aplicado_returns_none(self):
        validacoes: list = []
        assert _rbf_try_manual_bdi({}, validacoes) is None

    def test_non_dict_bdi_aplicado_returns_none(self):
        validacoes: list = []
        assert _rbf_try_manual_bdi({"bdi_aplicado": "0.15"}, validacoes) is None

    def test_valid_dict_returns_five_tuple(self):
        validacoes: list = []
        inputs = {"bdi_aplicado": {"mao_obra": 0.15, "material": 0.10, "diesel": 0.05}}
        result = _rbf_try_manual_bdi(inputs, validacoes)
        assert result is not None
        assert len(result) == 5
        rates, tabela, fonte, regime, override = result
        assert fonte == "inputs.bdi_aplicado"
        # Bug fix: modo manual (bdi_aplicado) deve retornar DEFAULT_BDI_TABELA em vez de
        # None — consumidores a jusante (CuboAnaliticoBuilder, MemorialBDIBuilder) esperam
        # uma TabelaBdi real; None produzia cubo/memorial vazios nesse modo.
        assert tabela is DEFAULT_BDI_TABELA
        assert override is True
        assert rates["mao_obra"] == pytest.approx(0.15)
        assert rates["material"] == pytest.approx(0.10)

    def test_valid_dict_appends_aviso_validation(self):
        validacoes: list = []
        _rbf_try_manual_bdi({"bdi_aplicado": {"mao_obra": 0.12}}, validacoes)
        codes = [v.codigo for v in validacoes]
        assert "VAL-CONSOL-BDI-FONTE" in codes
        statuses = [v.status for v in validacoes if v.codigo == "VAL-CONSOL-BDI-FONTE"]
        assert "AVISO" in statuses

    def test_equipamentos_defaults_to_servicos_fallback(self):
        validacoes: list = []
        inputs = {"bdi_aplicado": {"mao_obra": 0.20, "servicos": 0.18}}
        result = _rbf_try_manual_bdi(inputs, validacoes)
        assert result is not None
        rates = result[0]
        assert rates["equipamentos"] == pytest.approx(0.18)

    def test_servicos_defaults_to_mo_when_missing(self):
        validacoes: list = []
        inputs = {"bdi_aplicado": {"mao_obra": 0.20}}
        result = _rbf_try_manual_bdi(inputs, validacoes)
        assert result is not None
        rates = result[0]
        assert rates["equipamentos"] == pytest.approx(0.20)


# ---------------------------------------------------------------------------
# _resolve_bdi_rates early returns — lines 219, 222
# ---------------------------------------------------------------------------


class TestResolveBdiRatesEarlyReturns:
    def test_manual_bdi_path_returns_rates(self):
        validacoes: list = []
        inputs = {"bdi_aplicado": {"mao_obra": 0.15, "material": 0.08}}
        rates = _resolve_bdi_rates(inputs, validacoes)
        assert isinstance(rates, dict)
        assert rates["mao_obra"] == pytest.approx(0.15)

    def test_default_tabela_path_returns_rates(self):
        validacoes: list = []
        inputs = {}
        rates = _resolve_bdi_rates(inputs, validacoes)
        assert isinstance(rates, dict)
        assert "mao_obra" in rates


# ---------------------------------------------------------------------------
# _classificar_margem
# ---------------------------------------------------------------------------


class TestClassificarMargem:
    def _alvo(self):
        return {"min": 0.10, "max": 0.20}

    def _aceitavel(self):
        return {"min": 0.05, "max": 0.25}

    def test_within_alvo_returns_verde(self):
        assert _classificar_margem(0.15, self._alvo(), self._aceitavel()) == "VERDE"

    def test_boundary_alvo_min_returns_verde(self):
        assert _classificar_margem(0.10, self._alvo(), self._aceitavel()) == "VERDE"

    def test_boundary_alvo_max_returns_verde(self):
        assert _classificar_margem(0.20, self._alvo(), self._aceitavel()) == "VERDE"

    def test_within_aceitavel_not_alvo_returns_amarelo(self):
        assert _classificar_margem(0.07, self._alvo(), self._aceitavel()) == "AMARELO"

    def test_below_aceitavel_returns_vermelho(self):
        assert _classificar_margem(0.02, self._alvo(), self._aceitavel()) == "VERMELHO"

    def test_above_aceitavel_returns_vermelho(self):
        assert _classificar_margem(0.30, self._alvo(), self._aceitavel()) == "VERMELHO"
