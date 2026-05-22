from __future__ import annotations

import pytest

fastapi = pytest.importorskip("fastapi", reason="fastapi nao instalado - pule este modulo de teste")
from fastapi.testclient import TestClient  # noqa: E402

try:
    from concilium.presentation.api.app import create_app
    from concilium.presentation.api.container import get_concilium_service
except TypeError as exc:  # FastAPI/Starlette version mismatch in local env
    pytest.skip(f"Ambiente FastAPI incompatível para teste de rota: {exc}", allow_module_level=True)

pytestmark = [pytest.mark.slow]


class _FakeService:
    def get_cubo_analitico(self, project_id: str, version: str | None = None):
        assert project_id == "proj-123"
        return {
            "version": version or "v1",
            "cubo_analitico": {
                "projeto_id": "Projeto Demo",
                "total_preco_venda": 1000.0,
                "resumo_por_natureza": {"direto": 600.0, "indireto": 400.0},
                "resumo_por_natureza_temporal": {
                    "semana": {"2026-W24": {"direto": 300.0, "indireto": 200.0}},
                    "mes": {"2026-06": {"direto": 600.0, "indireto": 400.0}},
                },
            },
        }

    def get_cubo_analitico_projection(
        self,
        project_id: str,
        version: str | None,
        face: str,
        granularidade: str,
        categoria: str | None,
        componente_bdi: str | None,
        atividade_id: str | None,
        top_n: int,
        measure_profile: str | None = None,
        aggregation_mode: str | None = None,
        abc_threshold_a: float = 0.80,
        abc_threshold_b: float = 0.95,
    ):
        assert project_id == "proj-123"
        assert top_n >= 1
        assert abc_threshold_a < abc_threshold_b
        return {
            "version": version or "v1",
            "face": face,
            "granularidade": granularidade,
            "measure_profile": measure_profile or "financial_default",
            "aggregation_mode": aggregation_mode or "sum",
            "unit_type": "currency_brl",
            "chart_hint": "line",
            "columns": [
                {"id": "periodo", "label": "Período", "dtype": "str", "role": "x"},
                {"id": "componente_bdi", "label": "Componente BDI", "dtype": "str", "role": "series"},
                {"id": "valor_rs", "label": "Valor (R$)", "dtype": "float", "role": "value"},
            ],
            "operator_meta": {},
            "filtros_aplicados": {
                "categoria": categoria,
                "componente_bdi": componente_bdi,
                "atividade_id": atividade_id,
                "top_n": top_n,
            },
            "rows": [
                {"periodo": "2026-06", "componente_bdi": "custo_direto", "valor_rs": 600.0},
                {"periodo": "2026-07", "componente_bdi": "custo_direto", "valor_rs": 700.0},
            ],
            "totais": {
                "total_preco_venda": 1000.0,
                "total_custo_direto": 600.0,
                "total_tributos": 100.0,
                "total_despesas_indiretas": 200.0,
                "total_margem_lucro": 100.0,
            },
        }

    def get_cubo_projection_contract(self):
        return {
            "faces": {
                "tempo_natureza": {
                    "label": "Tempo x natureza",
                    "unit_type": "currency_brl",
                    "measure_profiles": ["financial_default"],
                    "aggregation_modes": ["sum"],
                },
                "abc_curva": {
                    "label": "Curva ABC",
                    "unit_type": "currency_brl",
                    "measure_profiles": ["abc_custo_direto"],
                    "aggregation_modes": ["pareto"],
                },
            },
            "granularidades": ["semana", "mes"],
            "measure_profiles": ["financial_default", "abc_custo_direto"],
            "aggregation_modes": ["sum", "pareto"],
            "abc_defaults": {"threshold_a": 0.80, "threshold_b": 0.95},
        }


def test_get_cubo_analitico_route_returns_payload():
    app = create_app()
    app.dependency_overrides[get_concilium_service] = lambda: _FakeService()
    client = TestClient(app)

    response = client.get("/api/projects/proj-123/cubo-analitico")

    assert response.status_code == 200
    body = response.json()
    assert body["version"] == "v1"
    assert "cubo_analitico" in body
    assert body["cubo_analitico"]["resumo_por_natureza"]["direto"] == 600.0
    assert "mes" in body["cubo_analitico"]["resumo_por_natureza_temporal"]


def test_get_cubo_analitico_projection_contract_default_payload():
    app = create_app()
    app.dependency_overrides[get_concilium_service] = lambda: _FakeService()
    client = TestClient(app)

    response = client.get("/api/projects/proj-123/cubo-analitico/projecao")

    assert response.status_code == 200
    body = response.json()
    assert body["version"] == "v1"
    assert body["face"] == "tempo_natureza"
    assert body["granularidade"] == "mes"
    assert body["measure_profile"] == "financial_default"
    assert body["aggregation_mode"] == "sum"
    assert body["unit_type"] == "currency_brl"
    assert body["chart_hint"]
    assert isinstance(body["columns"], list)
    assert {"id", "label", "dtype", "role"}.issubset(set(body["columns"][0].keys()))
    assert isinstance(body["rows"], list)
    assert isinstance(body["totais"], dict)


@pytest.mark.parametrize("face", ["tempo_natureza", "tempo_componente", "categoria_componente", "abc_curva"])
@pytest.mark.parametrize("granularidade", ["semana", "mes", "trimestre"])
def test_get_cubo_analitico_projection_accepts_valid_face_and_granularity(face: str, granularidade: str):
    app = create_app()
    app.dependency_overrides[get_concilium_service] = lambda: _FakeService()
    client = TestClient(app)

    response = client.get(
        "/api/projects/proj-123/cubo-analitico/projecao",
        params={"face": face, "granularidade": granularidade},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["face"] == face
    assert body["granularidade"] == granularidade


def test_get_cubo_analitico_projection_accepts_measure_profile_and_aggregation_mode():
    app = create_app()
    app.dependency_overrides[get_concilium_service] = lambda: _FakeService()
    client = TestClient(app)

    response = client.get(
        "/api/projects/proj-123/cubo-analitico/projecao",
        params={
            "face": "abc_curva",
            "measure_profile": "abc_custo_direto",
            "aggregation_mode": "pareto",
            "abc_threshold_a": 0.75,
            "abc_threshold_b": 0.92,
        },
    )

    assert response.status_code == 200
    body = response.json()
    assert body["measure_profile"] == "abc_custo_direto"
    assert body["aggregation_mode"] == "pareto"


def test_get_cubo_analitico_projection_accepts_version_query_param():
    app = create_app()
    app.dependency_overrides[get_concilium_service] = lambda: _FakeService()
    client = TestClient(app)

    response = client.get(
        "/api/projects/proj-123/cubo-analitico/projecao",
        params={"version": "v2"},
    )

    assert response.status_code == 200
    assert response.json()["version"] == "v2"


def test_get_cubo_analitico_projection_rejects_invalid_face():
    app = create_app()
    app.dependency_overrides[get_concilium_service] = lambda: _FakeService()
    client = TestClient(app)

    response = client.get(
        "/api/projects/proj-123/cubo-analitico/projecao",
        params={"face": "face_inexistente"},
    )

    assert response.status_code == 422


def test_get_cubo_analitico_projection_rejects_invalid_granularity():
    app = create_app()
    app.dependency_overrides[get_concilium_service] = lambda: _FakeService()
    client = TestClient(app)

    response = client.get(
        "/api/projects/proj-123/cubo-analitico/projecao",
        params={"granularidade": "dia"},
    )

    assert response.status_code == 422


def test_get_cubo_analitico_projection_rejects_invalid_filters():
    app = create_app()
    app.dependency_overrides[get_concilium_service] = lambda: _FakeService()
    client = TestClient(app)

    response = client.get(
        "/api/projects/proj-123/cubo-analitico/projecao",
        params={"categoria": "infra", "componente_bdi": "foo"},
    )

    assert response.status_code == 422


def test_get_cubo_analitico_projection_rejects_invalid_measure_profile():
    app = create_app()
    app.dependency_overrides[get_concilium_service] = lambda: _FakeService()
    client = TestClient(app)

    response = client.get(
        "/api/projects/proj-123/cubo-analitico/projecao",
        params={"measure_profile": "abc_custo_com_bdi"},
    )

    assert response.status_code == 422


def test_get_cubo_analitico_projection_contract_matrix_endpoint():
    app = create_app()
    app.dependency_overrides[get_concilium_service] = lambda: _FakeService()
    client = TestClient(app)

    response = client.get("/api/projects/proj-123/cubo-analitico/projecao/contrato")

    assert response.status_code == 200
    body = response.json()
    assert "faces" in body
    assert "abc_curva" in body["faces"]
    assert body["faces"]["abc_curva"]["aggregation_modes"] == ["pareto"]
