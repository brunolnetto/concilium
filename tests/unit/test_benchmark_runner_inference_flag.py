from __future__ import annotations

from pathlib import Path

from concilium.application.benchmarks.inference import BenchmarkInferencePack
from concilium.application.benchmarks.report.report_builder import BenchmarkReportBuilder
from concilium.application.benchmarks.report.report_printer import BenchmarkReportPrinter
from concilium.application.benchmarks.execution.runner import BenchmarkRunner
from concilium.application.benchmarks.spec.spec_loader import ProjectSpec


def _runner() -> BenchmarkRunner:
    return BenchmarkRunner(
        config_root=Path("."),
        projects_root=Path("."),
        report_builder=BenchmarkReportBuilder(),
        report_printer=BenchmarkReportPrinter(),
    )


def test_prepare_inputs_nep030_minimal_injection() -> None:
    """_prepare_inputs aplica injeção mínima honesta.

    - skill-06 executa sem benchmark_mode (modo produção)
    - skill-08 recebe benchmark_mode=True: a análise bridge (ADR-039) em contexto
      de benchmark é catalog-vs-reference, não deployment-vs-reference; sem isso
      skill-08 propaga VERMELHO → skill-15 ERRO → status INVIAVEL. Supersede o
      plano NEP-030 original (que mantinha skill-08 limpo) após a precificação
      operacional honesta.
    - bdi_indireto_efetivo não é injetado (era circular)
    - skill-09 recebe benchmark_mode=True + reference_projection para comparação final
    - campos existentes em extra_inputs são preservados
    """
    spec = ProjectSpec(
        nome="Projeto Teste",
        slug="proj-teste",
        contexto_id="ctx",
        extra_inputs={
            "06-resultado-financeiro": {"foo06": "bar", "foo08": "bar"},
        },
    )

    ref = {
        "planejamento_detalhado": [{"subtotal": {"com_bdi": {"total": 100.0}}}],
        "resultado": {
            "benchmark_confronto_referencia": {
                "preco_venda": 120.0,
                "custo_indireto": 10.0,
                "custo_direto": 90.0,
                "custo_total": 100.0,
            }
        },
    }

    skill_inputs = _runner()._prepare_inputs(spec, ref=ref)

    # campos originais dos extra_inputs preservados
    assert skill_inputs["06-resultado-financeiro"]["foo06"] == "bar"
    assert skill_inputs["06-resultado-financeiro"]["foo08"] == "bar"

    # NEP-041 F4: a skill unificada recebe benchmark_mode (consumido internamente
    # pelo estágio de consolidação — bridge ADR-039 catalog-vs-reference); o estágio
    # de precificação ignora o flag (modo produção). SEM override circular de
    # bdi_indireto_efetivo (NEP-030 D2).
    assert skill_inputs.get("06-resultado-financeiro", {}).get("benchmark_mode") is True
    assert "bdi_indireto_efetivo" not in skill_inputs.get("06-resultado-financeiro", {})

    # skill-09 COM benchmark_mode para relatório de comparação
    assert skill_inputs["09-relatorio-e-artefatos"]["benchmark_mode"] is True
    assert "benchmark_reference_projection" in skill_inputs["09-relatorio-e-artefatos"]


def test_prepare_inputs_uses_provided_pack_without_derive(monkeypatch) -> None:
    """Quando inference_pack é fornecido externamente, derive() não é chamado.

    O pack externo é mesclado como-está — permite sobrescrever a injeção
    padrão quando necessário (ex: testes de integração com pack customizado).
    """
    spec = ProjectSpec(
        nome="Projeto Teste",
        slug="proj-teste",
        contexto_id="ctx",
        extra_inputs={
            "06-resultado-financeiro": {"foo08": "bar"},
        },
    )

    def _unexpected_derive(_):
        raise AssertionError("derive should not be called when inference_pack is provided")

    monkeypatch.setattr(
        "concilium.application.benchmarks.execution.runner.BenchmarkInferenceService.derive",
        _unexpected_derive,
    )

    # Pack explicitamente customizado (ex: para teste de compatibilidade)
    pack = BenchmarkInferencePack(
        benchmark_mode=True,
        skill_inputs={
            "06-resultado-financeiro": {
                "benchmark_mode": True,
                "bdi_indireto_efetivo": 0.123,
            },
        },
    )

    skill_inputs = _runner()._prepare_inputs(spec, ref={"resultado": {}}, inference_pack=pack)

    # pack externo aplicado como-está
    assert skill_inputs["06-resultado-financeiro"]["benchmark_mode"] is True
    assert skill_inputs["06-resultado-financeiro"]["bdi_indireto_efetivo"] == 0.123
    assert skill_inputs["06-resultado-financeiro"]["foo08"] == "bar"


def test_prepare_inputs_is_stable_across_repeated_calls() -> None:
    """Chamadas múltiplas com os mesmos parâmetros produzem resultado idêntico."""
    spec = ProjectSpec(
        nome="Projeto Teste",
        slug="proj-teste",
        contexto_id="ctx",
        extra_inputs={
            "06-resultado-financeiro": {"foo08": "bar"},
            "06-resultado-financeiro": {"foo06": "bar"},
        },
    )
    ref = {
        "planejamento_detalhado": [{"subtotal": {"com_bdi": {"total": 100.0}}}],
        "resultado": {
            "benchmark_confronto_referencia": {
                "preco_venda": 120.0,
                "custo_indireto": 10.0,
            }
        },
    }

    first = _runner()._prepare_inputs(spec, ref=ref)
    second = _runner()._prepare_inputs(spec, ref=ref)

    assert first["06-resultado-financeiro"] == second["06-resultado-financeiro"]
    assert first["06-resultado-financeiro"] == second["06-resultado-financeiro"]
