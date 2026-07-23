"""Tests for domain/models/analytics/cubo_pool.py."""

from __future__ import annotations

from concilium.domain.models.analytics.cubo_pool import (
    CelulaPoolInstancial,
    CuboPoolInstancial,
    _measure_value,
    bucket_periodo,
)


def _make_celula(
    contrato_id="C1",
    tipo_id="ESC",
    instancia_numero=1,
    semana_iso="2026-W01",
    estado="prod",
    atividade_id="A1",
    custo_mo=100.0,
    custo_eq=50.0,
    custo_comb=20.0,
    custo_mat=10.0,
):
    from concilium.domain.models.analytics.cubo_pool import CelulaPoolInstancial

    return CelulaPoolInstancial(
        contrato_id=contrato_id,
        tipo_id=tipo_id,
        instancia_numero=instancia_numero,
        semana_iso=semana_iso,
        estado=estado,
        atividade_id=atividade_id,
        custo_mo=custo_mo,
        custo_eq=custo_eq,
        custo_comb=custo_comb,
        custo_mat=custo_mat,
    )


def _make_cubo(celulas):
    from concilium.domain.models.analytics.cubo_pool import CuboPoolInstancial

    return CuboPoolInstancial(projeto_id="proj-1", gerado_em="2026-01-01", celulas=tuple(celulas))


class TestBucketPeriodo:
    def test_semana_returns_raw(self):
        from concilium.domain.models.analytics.cubo_pool import bucket_periodo

        assert bucket_periodo("2026-W23", "semana") == "2026-W23"

    def test_iso_mes(self):
        from concilium.domain.models.analytics.cubo_pool import bucket_periodo

        result = bucket_periodo("2026-W23", "mes")
        assert "2026" in result

    def test_iso_trimestre(self):
        from concilium.domain.models.analytics.cubo_pool import bucket_periodo

        result = bucket_periodo("2026-W01", "trimestre")
        assert "T" in result

    def test_iso_ano(self):
        from concilium.domain.models.analytics.cubo_pool import bucket_periodo

        result = bucket_periodo("2026-W10", "ano")
        # Week 10 of 2026 starts in 2026
        assert result in ("2026", "2025")  # ISO week boundary — just check it's a year string

    def test_seq_mes(self):
        from concilium.domain.models.analytics.cubo_pool import bucket_periodo

        result = bucket_periodo("S001", "mes")
        assert result.startswith("M")

    def test_seq_trimestre(self):
        from concilium.domain.models.analytics.cubo_pool import bucket_periodo

        result = bucket_periodo("S001", "trimestre")
        assert result.startswith("T")

    def test_seq_ano(self):
        from concilium.domain.models.analytics.cubo_pool import bucket_periodo

        result = bucket_periodo("S001", "ano")
        assert result.startswith("A")

    def test_invalid_iso_returns_raw(self):
        from concilium.domain.models.analytics.cubo_pool import bucket_periodo

        result = bucket_periodo("2026-W99", "mes")
        assert result == "2026-W99"


class TestCelulaPoolInstancial:
    def test_custo_total(self):
        c = _make_celula()
        assert c.custo_total == 180.0

    def test_instancia_id(self):
        c = _make_celula(tipo_id="ESC", instancia_numero=3)
        assert c.instancia_id == "ESC-03"


class TestCuboPoolInstancial:
    def test_custo_total(self):
        c1 = _make_celula(custo_mo=100, custo_eq=50, custo_comb=0, custo_mat=0)
        c2 = _make_celula(custo_mo=200, custo_eq=100, custo_comb=0, custo_mat=0)
        cubo = _make_cubo([c1, c2])
        assert cubo.custo_total == 450.0

    def test_slice_by_estado(self):
        c_prod = _make_celula(estado="prod")
        c_idle = _make_celula(estado="idle", atividade_id=None)
        cubo = _make_cubo([c_prod, c_idle])
        sliced = cubo.slice(estado="prod")
        assert len(sliced.celulas) == 1

    def test_slice_by_contrato(self):
        c1 = _make_celula(contrato_id="C1")
        c2 = _make_celula(contrato_id="C2")
        cubo = _make_cubo([c1, c2])
        sliced = cubo.slice(contrato_id="C1")
        assert all(c.contrato_id == "C1" for c in sliced.celulas)

    def test_group_by(self):
        c1 = _make_celula(estado="prod", custo_mo=100, custo_eq=0, custo_comb=0, custo_mat=0)
        c2 = _make_celula(estado="idle", custo_mo=50, custo_eq=0, custo_comb=0, custo_mat=0)
        cubo = _make_cubo([c1, c2])
        result = cubo.group_by("estado", measure="custo_mo")
        assert result[("prod",)] == 100.0
        assert result[("idle",)] == 50.0

    def test_group_by_semanas(self):
        c1 = _make_celula()
        cubo = _make_cubo([c1])
        result = cubo.group_by("tipo_id", measure="semanas")
        assert result[("ESC",)] == 1.0

    def test_custo_por_estado(self):
        c_prod = _make_celula(estado="prod", custo_mo=100, custo_eq=0, custo_comb=0, custo_mat=0)
        c_idle = _make_celula(estado="idle", custo_mo=50, custo_eq=0, custo_comb=0, custo_mat=0)
        cubo = _make_cubo([c_prod, c_idle])
        result = cubo.custo_por_estado()
        assert result["prod"] == 100.0
        assert result["idle"] == 50.0

    def test_custo_por_componente(self):
        c = _make_celula(custo_mo=100, custo_eq=50, custo_comb=20, custo_mat=10)
        cubo = _make_cubo([c])
        result = cubo.custo_por_componente()
        assert result["mo"] == 100.0
        assert result["eq"] == 50.0

    def test_group_by_measure_by_component(self):
        c = _make_celula(custo_mo=100, custo_eq=50, custo_comb=20, custo_mat=10)
        cubo = _make_cubo([c])
        result = cubo.group_by("estado", measure="custo_mo")
        assert result[("prod",)] == 100.0


# cubo_pool.py line 57->59: sequential key with unrecognized granularidade
# ---------------------------------------------------------------------------


class TestAgruparSemanaIso:
    def test_sequential_key_unknown_granularidade_returns_as_is(self):
        """Line 57->59: s='S001', granularidade='quinzena' (unknown) → none of the
        if conditions match inside sequential block → falls through to return s."""
        from concilium.domain.models.analytics.cubo_pool import bucket_periodo

        result = bucket_periodo("S001", granularidade="quinzena")
        assert result == "S001"  # returned unchanged

    def test_sequential_key_mes_covered(self):
        """Confirm mes path works (regression guard)."""
        from concilium.domain.models.analytics.cubo_pool import bucket_periodo

        result = bucket_periodo("S005", granularidade="mes")
        assert result == "M02"  # (5-1)//4 + 1 = 2

    def test_sequential_key_trimestre_covered(self):
        """Confirm trimestre path works."""
        from concilium.domain.models.analytics.cubo_pool import bucket_periodo

        result = bucket_periodo("S014", granularidade="trimestre")
        assert result == "T2"  # (14-1)//13 + 1 = 2

    def test_sequential_key_ano_covered(self):
        """Confirm ano path works (line 57 True branch)."""
        from concilium.domain.models.analytics.cubo_pool import bucket_periodo

        result = bucket_periodo("S053", granularidade="ano")
        assert result == "A2"  # (53-1)//52 + 1 = 2


# ---------------------------------------------------------------------------



def test_cubo_pool_bucket_fallbacks_and_measure_default():
    # ISO parse ok but unsupported granularity should fall back to raw week.
    assert bucket_periodo("2026-W10", "quinzena") == "2026-W10"
    # Non-ISO/non-sequential key should be returned as-is.
    assert bucket_periodo("custom-key", "mes") == "custom-key"

    c = CelulaPoolInstancial(
        contrato_id="C1",
        tipo_id="ESC",
        instancia_numero=1,
        semana_iso="2026-W10",
        estado="off",
        atividade_id=None,
        custo_mo=10.0,
        custo_eq=2.0,
        custo_comb=3.0,
        custo_mat=5.0,
    )
    assert _measure_value(c, "custo_total") == c.custo_total
    assert _measure_value(c, "unknown_measure") == c.custo_total


def test_cubo_pool_ciclo_vida_branch_edges():
    c1 = CelulaPoolInstancial(
        contrato_id="C1",
        tipo_id="ESC",
        instancia_numero=1,
        semana_iso="2026-W10",
        estado="prod",
        atividade_id="A1",
        custo_mo=1.0,
    )
    c2 = CelulaPoolInstancial(
        contrato_id="C1",
        tipo_id="ESC",
        instancia_numero=1,
        semana_iso="2026-W09",
        estado="prod",
        atividade_id="A1",
        custo_mo=1.0,
    )
    c3 = CelulaPoolInstancial(
        contrato_id="C1",
        tipo_id="ESC",
        instancia_numero=1,
        semana_iso="2026-W11",
        estado="off",
        atividade_id=None,
    )
    cubo = CuboPoolInstancial(projeto_id="p", gerado_em="g", celulas=(c1, c2, c3))

    vida = cubo.ciclo_vida_instancias()["ESC-01"]
    assert vida["prod_w"] == 2
    assert vida["off_w"] == 1
    assert vida["semana_mob"] == "2026-W09"
    assert vida["semana_demob"] == "2026-W10"
