from __future__ import annotations

from types import SimpleNamespace

from concilium.application.services.analytics.cube_projection_views import resolve_cubo_projection_rows


class _CuboCategoriaStub:
    def __init__(self) -> None:
        # Totals imply: overhead=10%, lucro=20%, tributos=15% over custo_operacional.
        self.celulas = (
            SimpleNamespace(
                atividade_id="ATV-001",
                categoria="mao_obra",
                semana_iso="2026-W10",
                componente_bdi="custo_direto",
                valor_rs=100.0,
            ),
            SimpleNamespace(
                atividade_id="ATV-001",
                categoria="mao_obra",
                semana_iso="2026-W10",
                componente_bdi="overhead_ac",
                valor_rs=10.0,
            ),
            SimpleNamespace(
                atividade_id="ATV-001",
                categoria="mao_obra",
                semana_iso="2026-W10",
                componente_bdi="margem_l",
                valor_rs=20.0,
            ),
            SimpleNamespace(
                atividade_id="ATV-001",
                categoria="mao_obra",
                semana_iso="2026-W10",
                componente_bdi="tributo_iss",
                valor_rs=15.0,
            ),
        )

    def composicao_por_categoria(self):
        return {
            "mao_obra": {
                "custo_direto": 100.0,
                "overhead_ac": 10.0,
                "margem_l": 20.0,
                "tributo_iss": 15.0,
            }
        }


class _CuboAtividadeStub(_CuboCategoriaStub):
    def group_by(self, dim_a: str, dim_b: str):
        assert dim_a == "atividade_id"
        assert dim_b == "componente_bdi"
        return {
            ("ATV-001", "custo_direto"): 100.0,
            ("ATV-001", "overhead_ac"): 10.0,
            ("ATV-001", "margem_l"): 20.0,
            ("ATV-001", "tributo_iss"): 15.0,
        }


def _canonical_stub():
    return SimpleNamespace(
        indiretos=[
            SimpleNamespace(
                categoria="ADM",
                custo_total=50.0,
                funcoes=[{"custo_total": 20.0}],
                equipamentos=[{"custo_total": 10.0}],
                verbas_mensais=[{"custo_total": 20.0}],
                verbas_fixas=[],
                mobilizacoes=[],
            )
        ]
    )


def test_categoria_componente_has_full_breakdown_for_direto_and_indireto():
    rows, _, _ = resolve_cubo_projection_rows(
        _CuboCategoriaStub(),
        face="categoria_componente",
        granularidade="mes",
        top_n=200,
        canonical=_canonical_stub(),
    )

    by_key = {(r["categoria"], r["componente_bdi"]): float(r["valor_rs"]) for r in rows}

    assert by_key[("direto.mao_obra", "Custo operacional")] == 100.0
    assert by_key[("direto.mao_obra", "Overhead BDI")] == 10.0
    assert by_key[("direto.mao_obra", "Lucro (L)")] == 20.0
    assert by_key[("direto.mao_obra", "Tributos")] == 15.0

    assert by_key[("indireto.mao_obra", "Custo operacional")] == 20.0
    assert by_key[("indireto.mao_obra", "Overhead BDI")] == 2.0
    assert by_key[("indireto.mao_obra", "Lucro (L)")] == 4.0
    assert by_key[("indireto.mao_obra", "Tributos")] == 3.0

    assert by_key[("indireto.equipamento", "Custo operacional")] == 10.0
    assert by_key[("indireto.equipamento", "Overhead BDI")] == 1.0
    assert by_key[("indireto.equipamento", "Lucro (L)")] == 2.0
    assert by_key[("indireto.equipamento", "Tributos")] == 1.5

    assert by_key[("indireto.verbas", "Custo operacional")] == 20.0
    assert by_key[("indireto.verbas", "Overhead BDI")] == 2.0
    assert by_key[("indireto.verbas", "Lucro (L)")] == 4.0
    assert by_key[("indireto.verbas", "Tributos")] == 3.0


def test_atividade_componente_has_full_breakdown_for_direto_and_indireto():
    rows, _, _ = resolve_cubo_projection_rows(
        _CuboAtividadeStub(),
        face="atividade_componente",
        granularidade="mes",
        top_n=200,
        canonical=_canonical_stub(),
    )

    by_key = {(r["atividade_id"], r["componente_bdi"]): float(r["valor_rs"]) for r in rows}

    assert by_key[("direto.ATV-001", "Custo operacional")] == 100.0
    assert by_key[("direto.ATV-001", "Overhead BDI")] == 10.0
    assert by_key[("direto.ATV-001", "Lucro (L)")] == 20.0
    assert by_key[("direto.ATV-001", "Tributos")] == 15.0

    assert by_key[("indireto.ADM", "Custo operacional")] == 50.0
    assert by_key[("indireto.ADM", "Overhead BDI")] == 5.0
    assert by_key[("indireto.ADM", "Lucro (L)")] == 10.0
    assert by_key[("indireto.ADM", "Tributos")] == 7.5
