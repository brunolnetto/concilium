from __future__ import annotations

from concilium.application.benchmarks.inference import BenchmarkInferenceService


def test_derives_reference_projection_with_itemized_direct_override() -> None:
    """reference_projection é extraída corretamente — custo_direto vem da soma dos itens."""
    ref = {
        "planejamento_detalhado": [
            {"subtotal": {"sem_bdi": {"total": 60.0}, "com_bdi": {"total": 80.0}}},
            {"subtotal": {"sem_bdi": {"total": 40.0}, "com_bdi": {"total": 50.0}}},
        ],
        "resultado": {
            "benchmark_confronto_referencia": {
                "custo_direto": 95.0,
                "custo_indireto": 30.0,
                "custo_total": 125.0,
                "preco_venda": 140.0,
            }
        },
    }

    pack = BenchmarkInferenceService.derive(ref)

    assert pack.reference_projection is not None
    assert pack.reference_projection["custo_direto"] == 100.0  # soma dos itens, não confronto
    assert pack.reference_projection["custo_total"] == 130.0
    assert pack.reference_projection["preco_venda"] == 140.0


def test_nep030_bdi_indireto_efetivo_not_injected() -> None:
    """NEP-030: bdi_indireto_efetivo NÃO é mais injetado no skill-08.

    Era um override circular: garantia que o preço de venda fechasse com a referência
    independentemente da qualidade do algoritmo.
    """
    ref = {
        "planejamento_detalhado": [
            {"subtotal": {"com_bdi": {"total": 100.0}}},
            {"subtotal": {"com_bdi": {"total": 50.0}}},
        ],
        "resultado": {
            "benchmark_confronto_referencia": {
                "preco_venda": 170.0,
                "custo_indireto": 10.0,
            }
        },
    }

    pack = BenchmarkInferenceService.derive(ref)

    # bdi_indireto_efetivo não deve estar nos inputs de skill-08
    skill08_inputs = pack.skill_inputs.get("06-resultado-financeiro", {})
    assert "bdi_indireto_efetivo" not in skill08_inputs

    # skill-08 não recebe benchmark_mode (executa como produção)
    assert "benchmark_mode" not in skill08_inputs


def test_nep030_benchmark_mode_only_in_skill09() -> None:
    """NEP-030: benchmark_mode=True é injetado APENAS no skill-09 (relatório de comparação).

    Skills 06 e 08 executam em modo de produção — sem fork de comportamento.
    """
    ref = {
        "resultado": {
            "benchmark_confronto_referencia": {
                "custo_direto": 100.0,
                "custo_indireto": 20.0,
                "custo_total": 120.0,
                "preco_venda": 140.0,
            }
        }
    }

    pack = BenchmarkInferenceService.derive(ref)

    # skill-09 recebe benchmark_mode para habilitar comparação final
    assert pack.skill_inputs.get("10-relatorio-e-artefatos", {}).get("benchmark_mode") is True

    # skills 06 e 08 NÃO recebem benchmark_mode
    assert "benchmark_mode" not in pack.skill_inputs.get("06-resultado-financeiro", {})
    assert "benchmark_mode" not in pack.skill_inputs.get("06-resultado-financeiro", {})


def test_apply_to_skill_inputs_preserves_existing_fields() -> None:
    """apply_to_skill_inputs mescla sem perder campos já existentes nos inputs."""
    ref = {
        "resultado": {
            "benchmark_confronto_referencia": {
                "custo_direto": 100.0,
                "custo_indireto": 20.0,
                "custo_total": 120.0,
                "preco_venda": 140.0,
            }
        }
    }
    pack = BenchmarkInferenceService.derive(ref)

    base_inputs = {
        "06-resultado-financeiro": {"foo": "bar", "preco_diesel": 6.20},
    }

    merged = BenchmarkInferenceService.apply_to_skill_inputs(base_inputs, pack)

    # campos originais preservados
    assert merged["06-resultado-financeiro"]["foo"] == "bar"
    assert merged["06-resultado-financeiro"]["preco_diesel"] == 6.20

    # overrides circulares ausentes (NEP-030)
    assert "bdi_indireto_efetivo" not in merged.get("06-resultado-financeiro", {})
    assert "benchmark_mode" not in merged.get("06-resultado-financeiro", {})
    assert "benchmark_mode" not in merged.get("06-resultado-financeiro", {})
