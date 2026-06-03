from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import pytest

from concilium.application.services.concilium_service import ConciliumDependencies, ConciliumService
from tests.unit.test_cubo_analitico import _make_canonical


class _ProjectServiceStub:
    def __init__(self, canonical):
        self._canonical = canonical

    def get_last_canonical(self, project_id: str):
        assert project_id == "proj-123"
        return self._canonical


def _make_service(canonical) -> ConciliumService:
    deps = ConciliumDependencies(
        input_builder=SimpleNamespace(_config_root=Path(".")),
        repository=SimpleNamespace(),
        project_service=_ProjectServiceStub(canonical),
        override_service=SimpleNamespace(),
        pipeline_service=SimpleNamespace(),
        audit_service=SimpleNamespace(),
        benchmarks_root=Path("."),
    )
    return ConciliumService(deps)


def test_projection_contract_matrix_has_iteration2_faces():
    matrix = ConciliumService.get_cubo_projection_contract()

    assert "faces" in matrix
    assert "abc_curva" in matrix["faces"]
    assert "s_curve_custo" in matrix["faces"]
    assert "recursos_ativos_tempo" in matrix["faces"]


def test_projection_rejects_measure_profile_incompatible_with_face():
    canonical = _make_canonical(n_atividades=2, with_schedule=True)
    service = _make_service(canonical)

    with pytest.raises(ValueError, match="Measure profile inválido para a face"):
        service.get_cubo_analitico_projection(
            "proj-123",
            face="tempo_natureza",
            measure_profile="abc_custo_direto",
            aggregation_mode="pareto",
        )


def test_projection_abc_curva_returns_operator_meta_and_unit_type():
    canonical = _make_canonical(n_atividades=2, with_schedule=True)
    service = _make_service(canonical)

    payload = service.get_cubo_analitico_projection(
        "proj-123",
        face="abc_curva",
        measure_profile="abc_custo_direto",
        aggregation_mode="pareto",
        top_n=30,
    )

    assert payload["unit_type"] == "currency_brl"
    assert payload["aggregation_mode"] == "pareto"
    assert "operator_meta" in payload
    assert "thresholds" in payload["operator_meta"]
    assert isinstance(payload["rows"], list)


def test_projection_recursos_ativos_tempo_supports_count_distinct_mode():
    canonical = _make_canonical(n_atividades=2, with_schedule=True)
    service = _make_service(canonical)

    payload = service.get_cubo_analitico_projection(
        "proj-123",
        face="recursos_ativos_tempo",
        granularidade="mes",
        measure_profile="recursos_ativos",
        aggregation_mode="count_distinct",
    )

    assert payload["unit_type"] == "count"
    assert payload["aggregation_mode"] == "count_distinct"
    assert payload["rows"]
    assert {"periodo", "n_equipes_totais", "n_equipamentos_unicos"}.issubset(payload["rows"][0].keys())
