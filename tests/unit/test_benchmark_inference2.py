"""Extended coverage tests for BenchmarkInferenceService.

Targets the scenarios specified in the task brief to push coverage from
~61% toward 80%+.  No I/O, no fixtures — pure unit tests.
"""
from __future__ import annotations

import pytest

from concilium.application.benchmarks.inference import (
    BenchmarkInferenceService,
    BenchmarkInferencePack,
    BenchmarkInferenceTraceEntry,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _rule_ids(pack: BenchmarkInferencePack) -> list[str]:
    return [e.rule_id for e in pack.trace]


# ---------------------------------------------------------------------------
# derive(None) — baseline pack
# ---------------------------------------------------------------------------


def test_derive_none_returns_benchmark_mode_true() -> None:
    pack = BenchmarkInferenceService.derive(None)
    assert pack.benchmark_mode is True


def test_derive_none_skill_inputs_only_skill09() -> None:
    pack = BenchmarkInferenceService.derive(None)
    assert set(pack.skill_inputs.keys()) == {"09-relatorio-e-artefatos"}
    assert pack.skill_inputs["09-relatorio-e-artefatos"].get("benchmark_mode") is True


def test_derive_none_reference_projection_is_none() -> None:
    pack = BenchmarkInferenceService.derive(None)
    assert pack.reference_projection is None


def test_derive_none_has_two_trace_entries() -> None:
    pack = BenchmarkInferenceService.derive(None)
    assert len(pack.trace) == 2


def test_derive_none_trace_contains_inf_bench_001() -> None:
    pack = BenchmarkInferenceService.derive(None)
    assert "INF-BENCH-001" in _rule_ids(pack)


def test_derive_none_trace_contains_inf_bench_030_d2() -> None:
    pack = BenchmarkInferenceService.derive(None)
    assert "INF-BENCH-030-D2" in _rule_ids(pack)


# ---------------------------------------------------------------------------
# derive({}) — empty dict (non-dict guard falls through, reference extracted)
# ---------------------------------------------------------------------------


def test_derive_empty_dict_is_dict_so_extract_runs() -> None:
    """An empty dict is still a dict, so the extraction branch runs."""
    pack = BenchmarkInferenceService.derive({})
    # reference_projection should be None (nothing in the empty dict)
    assert pack.reference_projection is None


def test_derive_empty_dict_trace_has_030_d2() -> None:
    pack = BenchmarkInferenceService.derive({})
    assert "INF-BENCH-030-D2" in _rule_ids(pack)


def test_derive_non_dict_bypasses_extraction() -> None:
    """Passing a list (non-dict) should take the early-return path."""
    pack = BenchmarkInferenceService.derive("not-a-dict")  # type: ignore[arg-type]
    assert pack.reference_projection is None
    # Only INF-BENCH-001 present; INF-BENCH-030-D2 is NOT added
    assert "INF-BENCH-030-D2" not in _rule_ids(pack)
    assert len(pack.trace) == 1


# ---------------------------------------------------------------------------
# derive(ref) with resultado.benchmark_confronto_referencia — INF-BENCH-102
# ---------------------------------------------------------------------------


def _ref_with_confronto(
    custo_direto: float = 95.0,
    custo_indireto: float = 30.0,
    custo_total: float = 125.0,
    preco_venda: float = 140.0,
) -> dict:
    return {
        "resultado": {
            "benchmark_confronto_referencia": {
                "custo_direto": custo_direto,
                "custo_indireto": custo_indireto,
                "custo_total": custo_total,
                "preco_venda": preco_venda,
            }
        }
    }


def test_derive_confronto_inf_bench_102_in_trace() -> None:
    pack = BenchmarkInferenceService.derive(_ref_with_confronto())
    assert "INF-BENCH-102" in _rule_ids(pack)


def test_derive_confronto_reference_projection_not_none() -> None:
    pack = BenchmarkInferenceService.derive(_ref_with_confronto())
    assert isinstance(pack.reference_projection, dict)


def test_derive_confronto_benchmark_reference_projection_in_skill09() -> None:
    pack = BenchmarkInferenceService.derive(_ref_with_confronto())
    skill09 = pack.skill_inputs.get("09-relatorio-e-artefatos", {})
    assert "benchmark_reference_projection" in skill09
    assert isinstance(skill09["benchmark_reference_projection"], dict)


def test_derive_confronto_custo_direto_not_overridden_without_planejamento() -> None:
    """Without planejamento_detalhado, custo_direto comes straight from confronto."""
    pack = BenchmarkInferenceService.derive(_ref_with_confronto(custo_direto=95.0))
    assert pack.reference_projection["custo_direto"] == 95.0


def test_derive_confronto_custo_direto_overridden_by_planejamento() -> None:
    """With planejamento_detalhado, custo_direto is replaced and custo_total recomputed."""
    ref = {
        "planejamento_detalhado": [
            {"subtotal": {"sem_bdi": {"total": 60.0}}},
            {"subtotal": {"sem_bdi": {"total": 40.0}}},
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
    assert pack.reference_projection["custo_direto"] == 100.0
    # custo_total = direto + indireto = 100 + 30 = 130
    assert pack.reference_projection["custo_total"] == 130.0


def test_derive_confronto_preco_venda_preserved() -> None:
    pack = BenchmarkInferenceService.derive(_ref_with_confronto(preco_venda=200.0))
    assert pack.reference_projection["preco_venda"] == 200.0


# ---------------------------------------------------------------------------
# derive(ref) with resultado.canonical — INF-BENCH-103
# ---------------------------------------------------------------------------


def _ref_with_canonical(
    direto_equipes: float = 80.0,
    total_custo: float = 110.0,
    total_com_bdi: float = 130.0,
    indireto_salarios: float = 20.0,
    indireto_equipamentos: float = 10.0,
) -> dict:
    return {
        "resultado": {
            "canonical": {
                "custo": {
                    "direto_equipes": direto_equipes,
                    "total": total_custo,
                    "indireto_salarios": indireto_salarios,
                    "indireto_equipamentos": indireto_equipamentos,
                },
                "venda": {
                    "total_com_bdi": total_com_bdi,
                },
            }
        }
    }


def test_derive_canonical_inf_bench_103_in_trace() -> None:
    pack = BenchmarkInferenceService.derive(_ref_with_canonical())
    assert "INF-BENCH-103" in _rule_ids(pack)


def test_derive_canonical_fallback_applied_true() -> None:
    pack = BenchmarkInferenceService.derive(_ref_with_canonical())
    entry = next(e for e in pack.trace if e.rule_id == "INF-BENCH-103")
    assert entry.fallback_applied is True


def test_derive_canonical_reference_projection_values() -> None:
    pack = BenchmarkInferenceService.derive(
        _ref_with_canonical(
            direto_equipes=80.0,
            total_custo=110.0,
            total_com_bdi=130.0,
            indireto_salarios=20.0,
            indireto_equipamentos=10.0,
        )
    )
    rp = pack.reference_projection
    assert rp is not None
    assert rp["custo_direto"] == 80.0
    assert rp["custo_total"] == 110.0
    assert rp["preco_venda"] == 130.0
    assert rp["custo_indireto"] == 30.0  # 20 + 10


def test_derive_canonical_custo_indireto_zero_becomes_none() -> None:
    """_sum_indireto returns 0.0 when no indireto_ keys; projection maps 0 -> None."""
    ref = {
        "resultado": {
            "canonical": {
                "custo": {"direto_equipes": 50.0, "total": 50.0, "outro_campo": 5.0},
                "venda": {"total_com_bdi": 60.0},
            }
        }
    }
    pack = BenchmarkInferenceService.derive(ref)
    assert pack.reference_projection is not None
    assert pack.reference_projection["custo_indireto"] is None


def test_derive_canonical_uses_total_custo_plus_as_fallback_venda() -> None:
    ref = {
        "resultado": {
            "canonical": {
                "custo": {"direto_equipes": 50.0, "total": 50.0},
                "venda": {"total_custo_plus": 99.0},
            }
        }
    }
    pack = BenchmarkInferenceService.derive(ref)
    assert pack.reference_projection["preco_venda"] == 99.0


# ---------------------------------------------------------------------------
# _sum_planejamento_subtotal
# ---------------------------------------------------------------------------


def test_sum_planejamento_subtotal_empty_list_returns_none() -> None:
    result = BenchmarkInferenceService._sum_planejamento_subtotal({}, "sem_bdi")
    assert result is None


def test_sum_planejamento_subtotal_explicit_empty_list_returns_none() -> None:
    result = BenchmarkInferenceService._sum_planejamento_subtotal(
        {"planejamento_detalhado": []}, "sem_bdi"
    )
    assert result is None


def test_sum_planejamento_subtotal_items_present() -> None:
    ref = {
        "planejamento_detalhado": [
            {"subtotal": {"sem_bdi": {"total": 100.0}}},
            {"subtotal": {"sem_bdi": {"total": 50.5}}},
        ]
    }
    result = BenchmarkInferenceService._sum_planejamento_subtotal(ref, "sem_bdi")
    assert result == 150.5


def test_sum_planejamento_subtotal_skips_missing_branch() -> None:
    """Items without the requested mode branch are skipped; None if no valid items."""
    ref = {
        "planejamento_detalhado": [
            {"subtotal": {"com_bdi": {"total": 200.0}}},  # only com_bdi, no sem_bdi
        ]
    }
    result = BenchmarkInferenceService._sum_planejamento_subtotal(ref, "sem_bdi")
    assert result is None


def test_sum_planejamento_subtotal_fallback_to_planejamento_itens() -> None:
    """Falls back to planejamento.itens when planejamento_detalhado is absent."""
    ref = {
        "planejamento": {
            "itens": [
                {"subtotal": {"sem_bdi": {"total": 70.0}}},
                {"subtotal": {"sem_bdi": {"total": 30.0}}},
            ]
        }
    }
    result = BenchmarkInferenceService._sum_planejamento_subtotal(ref, "sem_bdi")
    assert result == 100.0


def test_sum_planejamento_subtotal_non_dict_items_skipped() -> None:
    ref = {
        "planejamento_detalhado": [
            "not-a-dict",
            {"subtotal": {"sem_bdi": {"total": 25.0}}},
        ]
    }
    result = BenchmarkInferenceService._sum_planejamento_subtotal(ref, "sem_bdi")
    assert result == 25.0


def test_sum_planejamento_subtotal_non_numeric_total_skipped() -> None:
    ref = {
        "planejamento_detalhado": [
            {"subtotal": {"sem_bdi": {"total": "NaN"}}},
            {"subtotal": {"sem_bdi": {"total": 10.0}}},
        ]
    }
    result = BenchmarkInferenceService._sum_planejamento_subtotal(ref, "sem_bdi")
    assert result == 10.0


# ---------------------------------------------------------------------------
# _sum_indireto
# ---------------------------------------------------------------------------


def test_sum_indireto_sums_only_indireto_prefixed_keys() -> None:
    custo = {
        "indireto_salarios": 20.0,
        "indireto_equipamentos": 10.0,
        "direto_equipes": 100.0,   # must NOT be included
        "total": 130.0,            # must NOT be included
    }
    result = BenchmarkInferenceService._sum_indireto(custo)
    assert result == 30.0


def test_sum_indireto_empty_dict_returns_zero() -> None:
    assert BenchmarkInferenceService._sum_indireto({}) == 0.0


def test_sum_indireto_no_indireto_keys_returns_zero() -> None:
    custo = {"direto_equipes": 50.0, "total": 50.0}
    assert BenchmarkInferenceService._sum_indireto(custo) == 0.0


def test_sum_indireto_ignores_non_numeric_values() -> None:
    custo = {"indireto_foo": "not-a-number", "indireto_bar": 5.0}
    assert BenchmarkInferenceService._sum_indireto(custo) == 5.0


def test_sum_indireto_rounding() -> None:
    custo = {"indireto_a": 0.1, "indireto_b": 0.2}
    result = BenchmarkInferenceService._sum_indireto(custo)
    assert result == round(0.3, 2)


# ---------------------------------------------------------------------------
# apply_to_skill_inputs
# ---------------------------------------------------------------------------


def test_apply_to_skill_inputs_does_not_mutate_original() -> None:
    pack = BenchmarkInferenceService.derive(_ref_with_confronto())
    original = {"09-relatorio-e-artefatos": {"existing_key": "existing_value"}}
    original_copy = {"09-relatorio-e-artefatos": {"existing_key": "existing_value"}}
    BenchmarkInferenceService.apply_to_skill_inputs(original, pack)
    assert original == original_copy


def test_apply_to_skill_inputs_merges_pack_into_existing() -> None:
    pack = BenchmarkInferenceService.derive(_ref_with_confronto())
    base = {"09-relatorio-e-artefatos": {"my_flag": True}}
    merged = BenchmarkInferenceService.apply_to_skill_inputs(base, pack)
    skill09 = merged["09-relatorio-e-artefatos"]
    assert skill09["my_flag"] is True
    assert skill09.get("benchmark_mode") is True


def test_apply_to_skill_inputs_creates_skill_key_when_absent() -> None:
    """When the pack introduces a skill key not in base, it is created."""
    pack = BenchmarkInferenceService.derive(None)
    merged = BenchmarkInferenceService.apply_to_skill_inputs({}, pack)
    assert "09-relatorio-e-artefatos" in merged
    assert merged["09-relatorio-e-artefatos"]["benchmark_mode"] is True


def test_apply_to_skill_inputs_empty_pack_returns_copy() -> None:
    from concilium.application.benchmarks.inference import BenchmarkInferencePack
    empty_pack = BenchmarkInferencePack(benchmark_mode=True, skill_inputs={})
    base = {"some-skill": {"x": 1}}
    merged = BenchmarkInferenceService.apply_to_skill_inputs(base, empty_pack)
    assert merged == base
    assert merged is not base  # deep copy


# ---------------------------------------------------------------------------
# _derive_bdi_indireto_efetivo — edge cases returning None
# ---------------------------------------------------------------------------


def test_derive_bdi_none_when_preco_ref_missing() -> None:
    value, trace = BenchmarkInferenceService._derive_bdi_indireto_efetivo({})
    assert value is None
    assert trace == []


def test_derive_bdi_none_when_indireto_ref_missing() -> None:
    ref = {
        "resultado": {
            "benchmark_confronto_referencia": {
                "preco_venda": 200.0,
                # custo_indireto absent
            }
        }
    }
    value, trace = BenchmarkInferenceService._derive_bdi_indireto_efetivo(ref)
    assert value is None


def test_derive_bdi_none_when_indireto_ref_zero() -> None:
    ref = {
        "resultado": {
            "benchmark_confronto_referencia": {
                "preco_venda": 200.0,
                "custo_indireto": 0.0,
            }
        }
    }
    value, trace = BenchmarkInferenceService._derive_bdi_indireto_efetivo(ref)
    assert value is None


def test_derive_bdi_none_when_no_planejamento_for_direto() -> None:
    """Without planejamento, direto_com_bdi is None — returns None."""
    ref = {
        "resultado": {
            "benchmark_confronto_referencia": {
                "preco_venda": 200.0,
                "custo_indireto": 40.0,
            }
        }
    }
    value, trace = BenchmarkInferenceService._derive_bdi_indireto_efetivo(ref)
    assert value is None


def test_derive_bdi_none_when_preco_ref_lte_direto_com_bdi() -> None:
    """preco_ref <= direto_com_bdi edge case must return None."""
    ref = {
        "planejamento_detalhado": [
            {"subtotal": {"com_bdi": {"total": 300.0}}},
        ],
        "resultado": {
            "benchmark_confronto_referencia": {
                "preco_venda": 200.0,  # less than direto_com_bdi=300
                "custo_indireto": 40.0,
            }
        },
    }
    value, trace = BenchmarkInferenceService._derive_bdi_indireto_efetivo(ref)
    assert value is None


def test_derive_bdi_correct_value() -> None:
    """Valid inputs: (preco_ref - direto_com_bdi) / indireto_ref - 1."""
    # preco=200, direto_com_bdi=100, indireto_ref=50 => (200-100)/50 - 1 = 1.0
    ref = {
        "planejamento_detalhado": [
            {"subtotal": {"com_bdi": {"total": 100.0}}},
        ],
        "resultado": {
            "benchmark_confronto_referencia": {
                "preco_venda": 200.0,
                "custo_indireto": 50.0,
            }
        },
    }
    value, trace = BenchmarkInferenceService._derive_bdi_indireto_efetivo(ref)
    assert value == pytest.approx(1.0)
    assert any(e.rule_id == "INF-BENCH-201" for e in trace)


def test_derive_bdi_uses_preco_venda_total_fallback() -> None:
    """Falls back to resultado.preco_venda_total when confronto missing preco_venda."""
    ref = {
        "planejamento_detalhado": [
            {"subtotal": {"com_bdi": {"total": 100.0}}},
        ],
        "resultado": {
            "preco_venda_total": 200.0,
            "custo_indireto_total": 50.0,
            "benchmark_confronto_referencia": {},
        },
    }
    value, trace = BenchmarkInferenceService._derive_bdi_indireto_efetivo(ref)
    assert value == pytest.approx(1.0)


def test_derive_bdi_uses_custo_indireto_total_fallback() -> None:
    """Falls back to resultado.custo_indireto_total when confronto has no custo_indireto."""
    ref = {
        "planejamento_detalhado": [
            {"subtotal": {"com_bdi": {"total": 50.0}}},
        ],
        "resultado": {
            "preco_venda_total": 150.0,
            "custo_indireto_total": 25.0,
            "benchmark_confronto_referencia": {},
        },
    }
    # (150 - 50) / 25 - 1 = 3.0
    value, trace = BenchmarkInferenceService._derive_bdi_indireto_efetivo(ref)
    assert value == pytest.approx(3.0)
