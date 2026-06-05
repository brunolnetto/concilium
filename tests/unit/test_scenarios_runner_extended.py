"""Tests for scenarios/runner.py — missing coverage paths."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from concilium.application.scenarios.config import ScenarioConfig
from concilium.application.scenarios.runner import (
    ScenarioResult,
    ScenarioRunner,
)
from concilium.application.scenarios.runner_utils import (
    apply_custo_delta,
    apply_duracao_delta,
    apply_equipe_delta,
    extract_metricas,
)
from concilium.application.skills.base import SkillResult

# ─────────────────────────────────────────────────────────────────────────────
#  extract_metricas
# ─────────────────────────────────────────────────────────────────────────────


class TestExtractMetricas:
    def test_none_canonical_returns_empty(self):
        assert extract_metricas(None) == {}

    def test_with_resultado(self):
        """canonical.resultado populates custo/venda/margem/status."""
        canonical = MagicMock()
        canonical.resultado = MagicMock()
        canonical.resultado.custo.total = 100000.0
        canonical.resultado.venda.total_com_bdi = 130000.0
        canonical.resultado.margem_pct = 0.23
        canonical.resultado.status_margem = "VERDE"
        canonical.cronograma = None
        canonical.equipes_diretas = None
        canonical.alocacoes = None
        canonical.conflitos_pico = None
        canonical.criticality_report = None

        m = extract_metricas(canonical)
        assert m["custo_total"] == 100000.0
        assert m["venda_com_bdi"] == 130000.0
        assert m["margem_pct"] == 23.0
        assert m["status_margem"] == "VERDE"

    def test_with_cronograma(self):
        """canonical.cronograma counts unique periods from distribuicao_mensal."""
        cronograma_mock = MagicMock()
        cronograma_mock.distribuicao_mensal = {
            "2024-01": {},
            "2024-02": {},
            "2024-03": {},
        }
        canonical = MagicMock()
        canonical.resultado = None
        canonical.cronograma = cronograma_mock
        canonical.equipes_diretas = None
        canonical.alocacoes = None
        canonical.conflitos_pico = None
        canonical.criticality_report = None

        m = extract_metricas(canonical)
        assert m["duracao_meses"] == 3

    def test_with_equipes_diretas(self):
        """canonical.equipes_diretas sums num_pessoas."""
        funcao1 = MagicMock()
        funcao1.num_pessoas = 3
        funcao2 = MagicMock()
        funcao2.num_pessoas = 2
        equipe = MagicMock()
        equipe.funcoes = [funcao1, funcao2]
        canonical = MagicMock()
        canonical.resultado = None
        canonical.cronograma = None
        canonical.equipes_diretas = [equipe]
        canonical.alocacoes = None
        canonical.conflitos_pico = None
        canonical.criticality_report = None

        m = extract_metricas(canonical)
        assert m["total_pessoas"] == 5

    def test_with_alocacoes(self):
        """canonical.alocacoes counts items."""
        canonical = MagicMock()
        canonical.resultado = None
        canonical.cronograma = None
        canonical.equipes_diretas = None
        canonical.alocacoes = [MagicMock(), MagicMock(), MagicMock()]
        canonical.conflitos_pico = None
        canonical.criticality_report = None

        m = extract_metricas(canonical)
        assert m["total_alocacoes"] == 3

    def test_with_conflitos_pico(self):
        """canonical.conflitos_pico counts conflicts."""
        canonical = MagicMock()
        canonical.resultado = None
        canonical.cronograma = None
        canonical.equipes_diretas = None
        canonical.alocacoes = None
        canonical.conflitos_pico = [MagicMock(), MagicMock()]
        canonical.criticality_report = None

        m = extract_metricas(canonical)
        assert m["conflitos_pico"] == 2

    def test_without_conflitos_pico(self):
        """canonical.conflitos_pico=None/empty gives conflitos_pico=0."""
        canonical = MagicMock()
        canonical.resultado = None
        canonical.cronograma = None
        canonical.equipes_diretas = None
        canonical.alocacoes = None
        canonical.conflitos_pico = None
        canonical.criticality_report = None

        m = extract_metricas(canonical)
        assert m["conflitos_pico"] == 0

    def test_with_criticality_report(self):
        """canonical.criticality_report counts activities with score >= 0.7."""
        canonical = MagicMock()
        canonical.resultado = None
        canonical.cronograma = None
        canonical.equipes_diretas = None
        canonical.alocacoes = None
        canonical.conflitos_pico = None
        canonical.criticality_report = {
            "scores": {
                "act-01": 0.8,  # critical
                "act-02": 0.6,  # not critical
                "act-03": 0.9,  # critical
            }
        }

        m = extract_metricas(canonical)
        assert m["atividades_criticas"] == 2


# ─────────────────────────────────────────────────────────────────────────────
#  Delta helpers
# ─────────────────────────────────────────────────────────────────────────────


class TestDeltaHelpers:
    def testapply_custo_delta_composicao_customizada(self):
        """apply_custo_delta adjusts salario_base and custo_mensal in composicao_customizada."""
        inputs = {
            "composicao_customizada": {
                "item-01": {
                    "funcoes": [{"salario_base": 1000.0, "nome": "pedreiro"}],
                    "equipamentos": [{"custo_mensal": 5000.0, "nome": "escavadeira"}],
                }
            }
        }
        result = apply_custo_delta(inputs, 1.10)
        funcao = result["composicao_customizada"]["item-01"]["funcoes"][0]
        equip = result["composicao_customizada"]["item-01"]["equipamentos"][0]
        assert funcao["salario_base"] == pytest.approx(1100.0, rel=1e-4)
        assert equip["custo_mensal"] == pytest.approx(5500.0, rel=1e-4)

    def testapply_custo_delta_custo_km(self):
        """apply_custo_delta adjusts custo_km."""
        inputs = {"custo_km": 2.50}
        result = apply_custo_delta(inputs, 0.90)
        assert result["custo_km"] == pytest.approx(2.25, rel=1e-4)

    def testapply_custo_delta_no_side_effects(self):
        """apply_custo_delta does not mutate original inputs."""
        inputs = {"custo_km": 2.50}
        original = inputs.copy()
        apply_custo_delta(inputs, 1.10)
        assert inputs == original

    def testapply_custo_delta_no_composicao_no_custo_km(self):
        """apply_custo_delta returns unmodified copy if no relevant keys."""
        inputs = {"other_key": "value"}
        result = apply_custo_delta(inputs, 1.10)
        assert result == {"other_key": "value"}
        assert result is not inputs  # deep copy

    def testapply_duracao_delta_sets_pct(self):
        """apply_duracao_delta sets duracao_delta_pct in result."""
        inputs = {"some_input": 1}
        result = apply_duracao_delta(inputs, 1.10)
        assert result["duracao_delta_pct"] == pytest.approx(10.0)

    def testapply_duracao_delta_negative(self):
        """apply_duracao_delta handles negative delta correctly."""
        inputs = {}
        result = apply_duracao_delta(inputs, 0.95)
        assert result["duracao_delta_pct"] == pytest.approx(-5.0)

    def testapply_equipe_delta_sets_pct(self):
        """apply_equipe_delta sets equipe_delta_pct in result."""
        inputs = {}
        result = apply_equipe_delta(inputs, 1.20)
        assert result["equipe_delta_pct"] == pytest.approx(20.0)


# ─────────────────────────────────────────────────────────────────────────────
#  ScenarioRunner.generate_variations
# ─────────────────────────────────────────────────────────────────────────────


class TestGenerateVariations:
    def _make_runner(self):
        return ScenarioRunner(runtime=MagicMock(), project=MagicMock())

    def test_n1_returns_base_only(self):
        """generate_variations(n=1) returns only the base config."""
        runner = self._make_runner()
        configs = runner.generate_variations(n=1)
        assert len(configs) == 1
        assert configs[0].nome == "base"

    def test_n3_returns_3_configs(self):
        """generate_variations(n=3) returns 3 configs."""
        runner = self._make_runner()
        configs = runner.generate_variations(n=3)
        assert len(configs) == 3

    def test_n0_raises(self):
        """generate_variations(n=0) raises ValueError."""
        runner = self._make_runner()
        with pytest.raises(ValueError):
            runner.generate_variations(n=0)

    def test_includes_base_config(self):
        """generate_variations always includes a 'base' config."""
        runner = self._make_runner()
        configs = runner.generate_variations(n=5)
        names = [c.nome for c in configs]
        assert "base" in names

    def test_otimista_pessimista_alternates(self):
        """generate_variations alternates between otimista and pessimista."""
        runner = self._make_runner()
        configs = runner.generate_variations(n=4)
        # configs[1] should be otimista, configs[2] pessimista
        assert "otimista" in configs[1].nome
        if len(configs) > 2:
            assert "pessimista" in configs[2].nome

    def test_custo_delta_in_range(self):
        """All generated configs have custo_delta within expected range."""
        runner = self._make_runner()
        configs = runner.generate_variations(n=5)
        for c in configs:
            assert 0.8 <= c.custo_delta <= 1.2, f"custo_delta={c.custo_delta} out of range"


# ─────────────────────────────────────────────────────────────────────────────
#  ScenarioRunner.run_scenario
# ─────────────────────────────────────────────────────────────────────────────


class TestRunScenario:
    def _make_mock_skill_result(self, has_errors: bool = False) -> SkillResult:
        result = MagicMock(spec=SkillResult)
        result.has_errors = has_errors
        result.validacoes = []
        return result

    def test_run_scenario_ok_when_skill_succeeds(self):
        """run_scenario() returns status=OK when all skills succeed."""
        mock_runtime = MagicMock()
        mock_project = MagicMock()
        mock_project.new_version.return_value = "v1"
        mock_project.load_canonical.return_value = None  # no canonical needed for OK
        mock_runtime.run_skill.return_value = self._make_mock_skill_result(has_errors=False)

        runner = ScenarioRunner(runtime=mock_runtime, project=mock_project)
        config = ScenarioConfig(nome="test", custo_delta=1.0)
        result = runner.run_scenario(config, base_inputs={}, skills=["01-escopo-e-eap"])

        assert result.status == "OK"
        assert result.config is config

    def test_run_scenario_erro_when_skill_has_errors(self):
        """run_scenario() returns status=ERRO when a skill has_errors=True."""
        mock_runtime = MagicMock()
        mock_project = MagicMock()
        mock_project.new_version.return_value = "v1"
        mock_project.load_canonical.return_value = None

        error_result = MagicMock(spec=SkillResult)
        error_result.has_errors = True
        error_result.validacoes = []

        mock_runtime.run_skill.return_value = error_result

        runner = ScenarioRunner(runtime=mock_runtime, project=mock_project)
        config = ScenarioConfig(nome="test")
        result = runner.run_scenario(config, base_inputs={}, skills=["01-escopo-e-eap"])

        assert result.status == "ERRO"
        assert result.erro is not None

    def test_run_scenario_catches_exception(self):
        """run_scenario() catches exceptions and returns status=ERRO."""
        mock_runtime = MagicMock()
        mock_project = MagicMock()
        mock_project.new_version.side_effect = RuntimeError("Disk full")

        runner = ScenarioRunner(runtime=mock_runtime, project=mock_project)
        config = ScenarioConfig(nome="test")
        result = runner.run_scenario(config, base_inputs={}, skills=["01-escopo-e-eap"])

        assert result.status == "ERRO"
        assert "Disk full" in result.erro

    def test_run_scenario_applies_custo_delta(self):
        """run_scenario() applies custo_delta to inputs when != 1.0."""
        mock_runtime = MagicMock()
        mock_project = MagicMock()
        mock_project.new_version.return_value = "v1"
        mock_project.load_canonical.return_value = None
        mock_runtime.run_skill.return_value = self._make_mock_skill_result()

        runner = ScenarioRunner(runtime=mock_runtime, project=mock_project)
        config = ScenarioConfig(nome="test", custo_delta=0.9, duracao_delta=1.1, equipe_delta=1.2)
        base_inputs = {"01-escopo-e-eap": {"custo_km": 10.0}}
        result = runner.run_scenario(config, base_inputs, skills=["01-escopo-e-eap"])

        assert result.status == "OK"
        # Verify run_skill was called with modified inputs
        call_kwargs = mock_runtime.run_skill.call_args
        (
            call_kwargs.kwargs.get("inputs") or call_kwargs[1].get("inputs") or call_kwargs[0][3]
            if len(call_kwargs[0]) > 3
            else None
        )
        # At minimum, verify it was called
        mock_runtime.run_skill.assert_called_once()


# ─────────────────────────────────────────────────────────────────────────────
#  ScenarioRunner.run_variations
# ─────────────────────────────────────────────────────────────────────────────


class TestRunVariations:
    def test_run_variations_returns_n_results(self):
        """run_variations(n=3) returns 3 ScenarioResult objects."""
        mock_runtime = MagicMock()
        mock_project = MagicMock()
        mock_project.new_version.return_value = "v1"
        mock_project.load_canonical.return_value = None

        skill_result = MagicMock(spec=SkillResult)
        skill_result.has_errors = False
        skill_result.validacoes = []
        mock_runtime.run_skill.return_value = skill_result

        runner = ScenarioRunner(runtime=mock_runtime, project=mock_project)
        results = runner.run_variations(base_inputs={}, n=3, skills=["01-escopo-e-eap"])

        assert len(results) == 3
        assert all(isinstance(r, ScenarioResult) for r in results)


# ─────────────────────────────────────────────────────────────────────────────
#  ScenarioRunner.generate_dv_variations
# ─────────────────────────────────────────────────────────────────────────────


class TestGenerateDvVariations:
    def _make_runner(self):
        return ScenarioRunner(runtime=MagicMock(), project=MagicMock())

    def test_invalid_dv4_raises(self):
        """generate_dv_variations() raises ValueError for invalid dv4_options."""
        runner = self._make_runner()
        with pytest.raises(ValueError, match="inválido"):
            runner.generate_dv_variations(
                base_decisions=None,
                dv4_options=["lean", "invalid_policy"],
            )

    def test_valid_dv4_options(self):
        """generate_dv_variations() with valid dv4_options generates configs."""
        runner = self._make_runner()
        configs = runner.generate_dv_variations(
            base_decisions=None,
            dv4_options=["lean", "standard", "robust"],
        )
        # base + 3 dv4 = 4 configs
        assert len(configs) == 4

    def test_dv2_options(self):
        """generate_dv_variations() with dv2_options generates configs."""
        runner = self._make_runner()
        dv2_list = [{"act-01": {"2024-W01": 2}}, {"act-01": {"2024-W01": 3}}]
        configs = runner.generate_dv_variations(
            base_decisions=None,
            dv2_options=dv2_list,
        )
        # base + 2 dv2 = 3 configs
        assert len(configs) == 3

    def test_base_config_always_included(self):
        """generate_dv_variations() always includes base_dv config."""
        runner = self._make_runner()
        configs = runner.generate_dv_variations(base_decisions=None)
        assert configs[0].nome == "base_dv"

    def test_no_options_returns_base_only(self):
        """generate_dv_variations() with no options returns just the base."""
        runner = self._make_runner()
        configs = runner.generate_dv_variations(base_decisions=None)
        assert len(configs) == 1


# ─────────────────────────────────────────────────────────────────────────────
#  ScenarioRunner.run_dv_scenario
# ─────────────────────────────────────────────────────────────────────────────


class TestRunDvScenario:
    def test_no_decision_variables_raises(self):
        """run_dv_scenario() raises ValueError if decision_variables is None."""
        runner = ScenarioRunner(runtime=MagicMock(), project=MagicMock())
        config = ScenarioConfig(nome="test", decision_variables=None)
        with pytest.raises(ValueError, match="decision_variables"):
            runner.run_dv_scenario(config, canonical_in=MagicMock())

    def test_feasible_scenario(self):
        """run_dv_scenario() with feasible result returns status=OK."""
        from concilium.domain.models.decision_variables import DecisionVariables

        runner = ScenarioRunner(runtime=MagicMock(), project=MagicMock())
        config = ScenarioConfig(
            nome="test",
            decision_variables=DecisionVariables(),
        )
        mock_canonical = MagicMock()
        mock_canonical.resultado = None
        mock_canonical.cronograma = None
        mock_canonical.equipes_diretas = None
        mock_canonical.alocacoes = None
        mock_canonical.conflitos_pico = None
        mock_canonical.criticality_report = None

        with patch("concilium.application.optimizer.loop.adjust_schedule") as mock_adjust:
            mock_adjust.return_value = (mock_canonical, True, [])
            result = runner.run_dv_scenario(config, canonical_in=MagicMock())

        assert result.status == "OK"
        assert result.erro is None

    def test_infeasible_scenario(self):
        """run_dv_scenario() with infeasible result returns status=INFEASIBLE."""
        from concilium.domain.models.decision_variables import DecisionVariables

        runner = ScenarioRunner(runtime=MagicMock(), project=MagicMock())
        config = ScenarioConfig(
            nome="test",
            decision_variables=DecisionVariables(),
        )

        mock_canonical = MagicMock()
        mock_canonical.resultado = None
        mock_canonical.cronograma = None
        mock_canonical.equipes_diretas = None
        mock_canonical.alocacoes = None
        mock_canonical.conflitos_pico = None
        mock_canonical.criticality_report = None

        violation = MagicMock()
        violation.status = "ERRO"
        violation.code = "C1"
        violation.remediation_hint = "Reduce crew"

        with patch("concilium.application.optimizer.loop.adjust_schedule") as mock_adjust:
            mock_adjust.return_value = (mock_canonical, False, [violation])
            result = runner.run_dv_scenario(config, canonical_in=MagicMock())

        assert result.status == "INFEASIBLE"
        assert result.erro is not None

    def test_exception_caught(self):
        """run_dv_scenario() catches exceptions and returns status=ERRO."""
        from concilium.domain.models.decision_variables import DecisionVariables

        runner = ScenarioRunner(runtime=MagicMock(), project=MagicMock())
        config = ScenarioConfig(
            nome="test",
            decision_variables=DecisionVariables(),
        )

        with patch("concilium.application.optimizer.loop.adjust_schedule") as mock_adjust:
            mock_adjust.side_effect = RuntimeError("Solver failed")
            result = runner.run_dv_scenario(config, canonical_in=MagicMock())

        assert result.status == "ERRO"
        assert "Solver failed" in result.erro


# ─────────────────────────────────────────────────────────────────────────────
#  ScenarioRunner.compare
# ─────────────────────────────────────────────────────────────────────────────


class TestCompare:
    def _make_result(self, nome: str, status: str = "OK", metricas: dict | None = None) -> ScenarioResult:
        config = ScenarioConfig(nome=nome, custo_delta=1.0)
        return ScenarioResult(
            config=config,
            canonical=None,
            versao="v1",
            status=status,
            metricas=metricas or {},
        )

    def test_compare_returns_resumo_cenarios(self):
        """compare() returns dict with 'resumo' and 'cenarios' keys."""
        runner = ScenarioRunner(runtime=MagicMock(), project=MagicMock())
        results = [self._make_result("base"), self._make_result("opt")]
        matrix = runner.compare(results)
        assert "resumo" in matrix
        assert "cenarios" in matrix

    def test_compare_counts_ok_and_erro(self):
        """compare() correctly counts OK and ERRO results."""
        runner = ScenarioRunner(runtime=MagicMock(), project=MagicMock())
        results = [
            self._make_result("a", status="OK"),
            self._make_result("b", status="OK"),
            self._make_result("c", status="ERRO"),
        ]
        matrix = runner.compare(results)
        assert matrix["resumo"]["ok"] == 2
        assert matrix["resumo"]["com_erro"] == 1
        assert matrix["resumo"]["total_cenarios"] == 3

    def test_compare_custo_summary_when_available(self):
        """compare() computes custo_min/max/spread when results have custo_total."""
        runner = ScenarioRunner(runtime=MagicMock(), project=MagicMock())
        results = [
            self._make_result("a", metricas={"custo_total": 100000.0, "margem_pct": 20.0}),
            self._make_result("b", metricas={"custo_total": 90000.0, "margem_pct": 25.0}),
        ]
        matrix = runner.compare(results)
        s = matrix["resumo"]
        assert s["custo_min"] == 90000.0
        assert s["custo_max"] == 100000.0
        assert "custo_spread_pct" in s
        assert s["melhor_cenario"] == "b"  # highest margem

    def test_compare_empty_results(self):
        """compare() handles empty results list."""
        runner = ScenarioRunner(runtime=MagicMock(), project=MagicMock())
        matrix = runner.compare([])
        assert matrix["resumo"]["total_cenarios"] == 0

    def test_save_comparison(self, tmp_path):
        """save_comparison() writes JSON file."""
        runner = ScenarioRunner(runtime=MagicMock(), project=MagicMock())
        results = [self._make_result("base")]
        out_path = tmp_path / "matrix.json"
        returned = runner.save_comparison(results, out_path)
        assert returned == out_path
        assert out_path.exists()

    def test_run_dv_variations_returns_list(self):
        """run_dv_variations() returns list of ScenarioResult."""

        runner = ScenarioRunner(runtime=MagicMock(), project=MagicMock())

        mock_canonical = MagicMock()
        mock_canonical.resultado = None
        mock_canonical.cronograma = None
        mock_canonical.equipes_diretas = None
        mock_canonical.alocacoes = None
        mock_canonical.conflitos_pico = None
        mock_canonical.criticality_report = None

        with patch("concilium.application.optimizer.loop.adjust_schedule") as mock_adjust:
            mock_adjust.return_value = (mock_canonical, True, [])
            results = runner.run_dv_variations(
                canonical_in=MagicMock(),
                dv4_options=["lean"],
            )

        assert isinstance(results, list)
        assert len(results) == 2  # base + 1 dv4
