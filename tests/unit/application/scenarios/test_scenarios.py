from datetime import UTC, date, datetime
from pathlib import Path

from concilium.application.scenarios import ScenarioConfig, ScenarioResult, ScenarioRunner
from concilium.domain.models.canonical import (
    CanonicalModel,
    Coordenadas,
    CustoTotal,
    Meta,
    Projeto,
    RegimeTrabalho,
    Resultado,
    Venda,
)
from concilium.domain.models.project.decision_variables import DecisionVariables


class _FakeSkillResult:
    def __init__(self, has_errors: bool = False):
        self.has_errors = has_errors
        self.validacoes = []


class _FakeRuntime:
    def __init__(self, fail_skill: str | None = None):
        self.fail_skill = fail_skill
        self.calls: list[str] = []

    def run_skill(self, skill_id: str, _project, version: str, inputs: dict):
        self.calls.append(skill_id)
        if self.fail_skill == skill_id:
            return _FakeSkillResult(has_errors=True)
        return _FakeSkillResult(has_errors=False)


class _FakeProject:
    def __init__(self, canonical: CanonicalModel):
        self._canonical = canonical
        self._next = 0
        self.root = Path("/tmp/fake-project")

    def new_version(self) -> str:
        self._next += 1
        return f"v{self._next}"

    def load_canonical(self, _version: str):
        return self._canonical


def _canonical_com_metricas() -> CanonicalModel:
    return CanonicalModel(
        meta=Meta(gerado_em=datetime.now(UTC), contexto_id="mendeslobo"),
        projeto=Projeto(
            id="p1",
            nome="Cenario",
            tipo_obra="terraplenagem",
            localizacao="X",
            coordenadas=Coordenadas(lat=-4.36, lng=-38.73),
            regime_trabalho=RegimeTrabalho(dias_semana=6, horas_dia=8),
            data_inicio=date(2026, 1, 1),
            data_termino=date(2026, 12, 31),
            snapshot_catalogo_id="cat",
            snapshot_perfil_id="perfil",
        ),
        resultado=Resultado(
            venda=Venda(total_sem_bdi=100.0, total_com_bdi=120.0),
            custo=CustoTotal(direto_equipes=80.0, total=90.0),
            resultado_financeiro=30.0,
            margem_pct=0.25,
            status_margem="VERDE",
            validacoes=[],
        ),
        cronograma=[],
        equipes_diretas=[],
        alocacoes=[],
        conflitos_pico=[],
        criticality_report={"scores": {"a": 0.8, "b": 0.6}},
    )


def test_generate_variations_rejeita_n_invalido() -> None:
    runner = ScenarioRunner(runtime=_FakeRuntime(), project=_FakeProject(_canonical_com_metricas()))
    try:
        runner.generate_variations(0)
        raise AssertionError("Era esperado ValueError")
    except ValueError:
        assert True


def test_generate_variations_inclui_cenario_base() -> None:
    runner = ScenarioRunner(runtime=_FakeRuntime(), project=_FakeProject(_canonical_com_metricas()))
    cfgs = runner.generate_variations(3)
    assert len(cfgs) == 3
    assert cfgs[0].nome == "base"
    assert cfgs[0].custo_delta == 1.0


def test_run_scenario_ok_retorna_metricas() -> None:
    canonical = _canonical_com_metricas()
    runner = ScenarioRunner(runtime=_FakeRuntime(), project=_FakeProject(canonical))
    result = runner.run_scenario(ScenarioConfig(nome="x"), base_inputs={})
    assert result.status == "OK"
    assert result.metricas["custo_total"] == 90.0
    assert result.metricas["margem_pct"] == 25.0
    assert result.metricas["atividades_criticas"] == 1


def test_run_scenario_para_no_primeiro_erro() -> None:
    canonical = _canonical_com_metricas()
    runtime = _FakeRuntime(fail_skill="05-equipes-e-alocacao")
    runner = ScenarioRunner(runtime=runtime, project=_FakeProject(canonical))

    result = runner.run_scenario(ScenarioConfig(nome="falha"), base_inputs={})

    assert result.status == "ERRO"
    assert "05-equipes-e-alocacao" in (result.erro or "")
    assert len(runtime.calls) >= 1


def test_compare_resumo_e_melhor_cenario() -> None:
    r1 = ScenarioResult(
        config=ScenarioConfig(nome="a"),
        canonical=None,
        versao="v1",
        status="OK",
        metricas={"custo_total": 100, "margem_pct": 8},
    )
    r2 = ScenarioResult(
        config=ScenarioConfig(nome="b"),
        canonical=None,
        versao="v2",
        status="OK",
        metricas={"custo_total": 90, "margem_pct": 12},
    )
    r3 = ScenarioResult(config=ScenarioConfig(nome="c"), canonical=None, versao="v3", status="ERRO")

    runner = ScenarioRunner(runtime=_FakeRuntime(), project=_FakeProject(_canonical_com_metricas()))
    matrix = runner.compare([r1, r2, r3])

    resumo = matrix["resumo"]
    assert resumo["total_cenarios"] == 3
    assert resumo["ok"] == 2
    assert resumo["com_erro"] == 1
    assert resumo["melhor_cenario"] == "b"
    assert resumo["custo_spread_pct"] == round((100 - 90) / 90 * 100, 1)


def test_save_comparison_grava_json(tmp_path: Path) -> None:
    runner = ScenarioRunner(runtime=_FakeRuntime(), project=_FakeProject(_canonical_com_metricas()))
    results = [ScenarioResult(config=ScenarioConfig(nome="base"), canonical=None, versao="v1", status="OK")]
    out = runner.save_comparison(results, tmp_path / "scenarios" / "comparison.json")
    assert out.exists()
    assert '"resumo"' in out.read_text()


# ── v2.5: DV1-DV4 tests (DEC-29) ─────────────────────────────────────────────


def test_scenario_config_accepts_decision_variables() -> None:
    """ScenarioConfig deve aceitar decision_variables (v2.5 DEC-29)."""
    dv = DecisionVariables(dv4_indirect_policy="lean")
    cfg = ScenarioConfig(nome="dv_test", decision_variables=dv)
    assert cfg.decision_variables is not None
    assert cfg.decision_variables.dv4_indirect_policy == "lean"
    # Deltas legados permanecem em 1.0 (não foram variados)
    assert cfg.custo_delta == 1.0
    assert cfg.duracao_delta == 1.0


def test_generate_dv_variations_inclui_base() -> None:
    """generate_dv_variations deve sempre incluir cenário base."""
    runner = ScenarioRunner(runtime=_FakeRuntime(), project=_FakeProject(_canonical_com_metricas()))
    dv = DecisionVariables(dv4_indirect_policy="standard")
    cfgs = runner.generate_dv_variations(base_decisions=dv)
    assert len(cfgs) >= 1
    assert cfgs[0].nome == "base_dv"
    assert cfgs[0].decision_variables is not None


def test_generate_dv_variations_com_dv4_options() -> None:
    """generate_dv_variations com dv4_options deve gerar cenários por política."""
    runner = ScenarioRunner(runtime=_FakeRuntime(), project=_FakeProject(_canonical_com_metricas()))
    cfgs = runner.generate_dv_variations(
        base_decisions=None,
        dv4_options=["lean", "robust"],
    )
    nomes = [c.nome for c in cfgs]
    assert "dv4_lean" in nomes
    assert "dv4_robust" in nomes


def test_generate_dv_variations_rejeita_policy_invalida() -> None:
    """generate_dv_variations deve rejeitar dv4_indirect_policy fora do enum."""
    runner = ScenarioRunner(runtime=_FakeRuntime(), project=_FakeProject(_canonical_com_metricas()))
    try:
        runner.generate_dv_variations(base_decisions=None, dv4_options=["invalid_policy"])
        raise AssertionError("Era esperado ValueError")
    except ValueError as e:
        assert "DEC-29" in str(e)


def test_run_dv_scenario_requer_decision_variables() -> None:
    """run_dv_scenario deve lançar ValueError se config.decision_variables for None."""
    runner = ScenarioRunner(runtime=_FakeRuntime(), project=_FakeProject(_canonical_com_metricas()))
    cfg = ScenarioConfig(nome="sem_dv")  # decision_variables=None
    try:
        runner.run_dv_scenario(cfg, canonical_in=_canonical_com_metricas())
        raise AssertionError("Era esperado ValueError")
    except ValueError as e:
        assert "decision_variables" in str(e)
