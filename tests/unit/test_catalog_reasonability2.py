"""Tests for application/services/catalog/catalog_reasonability.py."""

from __future__ import annotations


class TestQuantileFunctions:
    def test_q_empty(self):
        from concilium.application.services.catalog.catalog_reasonability import _q

        assert _q([], 0.5) == 0.0

    def test_q_single(self):
        from concilium.application.services.catalog.catalog_reasonability import _q

        assert _q([5.0], 0.5) == 5.0

    def test_q_median(self):
        from concilium.application.services.catalog.catalog_reasonability import _q

        result = _q([1.0, 2.0, 3.0, 4.0, 5.0], 0.5)
        assert abs(result - 3.0) < 0.01

    def test_iqr_bounds_too_few_returns_none(self):
        from concilium.application.services.catalog.catalog_reasonability import _iqr_bounds

        assert _iqr_bounds([1, 2, 3]) is None  # < 8 values

    def test_iqr_bounds_zero_iqr_returns_none(self):
        from concilium.application.services.catalog.catalog_reasonability import _iqr_bounds

        # All same values → IQR = 0
        assert _iqr_bounds([5.0] * 10) is None

    def test_iqr_bounds_normal_spread(self):
        from concilium.application.services.catalog.catalog_reasonability import _iqr_bounds

        vals = list(range(1, 20))
        result = _iqr_bounds(vals)
        assert result is not None
        low, high = result
        assert low < high

    def test_iqr_bounds_non_negative(self):
        from concilium.application.services.catalog.catalog_reasonability import _iqr_bounds

        vals = list(range(1, 20))
        result = _iqr_bounds(vals, non_negative=True)
        assert result is not None
        assert result[0] >= 0.0

    def test_robust_bounds_too_few(self):
        from concilium.application.services.catalog.catalog_reasonability import _robust_bounds

        assert _robust_bounds([1, 2]) is None

    def test_robust_bounds_with_concentrated_values(self):
        from concilium.application.services.catalog.catalog_reasonability import _robust_bounds

        # All same → IQR=None, falls back to q10/q90
        vals = [5.0] * 20
        result = _robust_bounds(vals)
        # q10=q90=5.0 → low=high, but still returns bounds
        assert result is not None

    def test_robust_bounds_spread(self):
        from concilium.application.services.catalog.catalog_reasonability import _robust_bounds

        vals = list(range(1, 30))
        low, high = _robust_bounds(vals)
        assert low < high


class TestHelpers:
    def test_safe_float_none(self):
        from concilium.application.services.catalog.catalog_reasonability import _safe_float

        assert _safe_float(None) is None
        assert _safe_float("bad") is None

    def test_safe_float_valid(self):
        from concilium.application.services.catalog.catalog_reasonability import _safe_float

        assert _safe_float("3.14") == 3.14

    def test_sum_people(self):
        from concilium.application.services.catalog.catalog_reasonability import _sum_people

        funcoes = [{"num_pessoas": 2}, {"num_pessoas": "3"}, {"num_pessoas": None}]
        assert _sum_people(funcoes) == 5

    def test_sum_equips(self):
        from concilium.application.services.catalog.catalog_reasonability import _sum_equips

        equips = [{"num_unidades": 1}, {"num_unidades": 2}]
        assert _sum_equips(equips) == 3

    def test_build_prod_lookup(self):
        from concilium.application.services.catalog.catalog_reasonability import _build_prod_lookup

        prods = [{"id": "P1", "valor_horario": 10}, {"id": "P2"}, {"valor_horario": 5}]
        lookup = _build_prod_lookup(prods)
        assert "P1" in lookup
        assert "P2" in lookup
        assert len(lookup) == 2

    def test_resolve_team_from_producao_none(self):
        from concilium.application.services.catalog.catalog_reasonability import _resolve_team_from_producao

        assert _resolve_team_from_producao(None) == ([], [])
        assert _resolve_team_from_producao("not-dict") == ([], [])

    def test_resolve_team_composicao_padrao(self):
        from concilium.application.services.catalog.catalog_reasonability import _resolve_team_from_producao

        prod = {
            "composicao_padrao_equipe": {
                "funcoes": [{"num_pessoas": 2}],
                "equipamentos": [{"num_unidades": 1}],
            }
        }
        funcoes, equips = _resolve_team_from_producao(prod)
        assert len(funcoes) == 1
        assert len(equips) == 1

    def test_resolve_team_legacy_equipe(self):
        from concilium.application.services.catalog.catalog_reasonability import _resolve_team_from_producao

        prod = {"equipe": {"funcoes": [{"num_pessoas": 1}], "equipamentos": []}}
        funcoes, equips = _resolve_team_from_producao(prod)
        assert len(funcoes) == 1

    def test_build_groups(self):
        from concilium.application.services.catalog.catalog_reasonability import _build_groups

        rows = [
            {"categoria": "TERRA", "unidade": "m³"},
            {"categoria": "TERRA", "unidade": "m³"},
            {"categoria": "PAVE", "unidade": "m²"},
        ]
        groups = _build_groups(rows)
        assert ("TERRA", "m³") in groups
        assert len(groups[("TERRA", "m³")]) == 2

    def test_build_summary_line(self):
        from concilium.application.services.catalog.catalog_reasonability import _build_summary_line

        result = _build_summary_line(100, 5, 10, 3)
        assert "100" in result
        assert "5" in result


class TestBuildCatalogReasonabilityArtifact:
    def _make_cpu(self, codigo="CPU-1", categoria="TERRA", unidade="m³", producao_id_ref="P1"):
        return {
            "codigo": codigo,
            "descricao": f"CPU {codigo}",
            "categoria": categoria,
            "unidade": unidade,
            "producao_id_ref": producao_id_ref,
        }

    def _make_producao(self, pid="P1", valor_horario=50.0):
        return {
            "id": pid,
            "valor_horario": valor_horario,
            "composicao_padrao_equipe": {
                "funcoes": [{"num_pessoas": 2}],
                "equipamentos": [{"num_unidades": 1}],
            },
        }

    def test_empty_catalog(self):
        from concilium.application.services.catalog.catalog_reasonability import build_catalog_reasonability_artifact

        result = build_catalog_reasonability_artifact("cat-1", [])
        assert result["summary"]["total_cpus"] == 0
        assert result["findings"] == []

    def test_cpu_missing_producao_ref(self):
        from concilium.application.services.catalog.catalog_reasonability import build_catalog_reasonability_artifact

        cpu = {"codigo": "CPU-1", "descricao": "Test", "categoria": "TERRA", "unidade": "m³", "producao_id_ref": ""}
        result = build_catalog_reasonability_artifact("cat-1", [cpu], [])
        row = result["rows"][0]
        assert "CPU sem producao_id_ref" in row["issues"]
        assert row["severity"] == "ERRO"

    def test_cpu_with_valid_producao(self):
        from concilium.application.services.catalog.catalog_reasonability import build_catalog_reasonability_artifact

        cpu = self._make_cpu()
        prod = self._make_producao()
        result = build_catalog_reasonability_artifact("cat-1", [cpu], [prod])
        row = result["rows"][0]
        assert row["producao_horaria"] == 50.0
        assert row["team_people"] == 2
        assert row["severity"] == "OK"

    def test_cpu_with_missing_producao_entry(self):
        from concilium.application.services.catalog.catalog_reasonability import build_catalog_reasonability_artifact

        cpu = self._make_cpu(producao_id_ref="P-MISSING")
        result = build_catalog_reasonability_artifact("cat-1", [cpu], [])
        row = result["rows"][0]
        assert any("producao_id_ref sem registro" in msg for msg in row["issues"])

    def test_outlier_detection(self):
        from concilium.application.services.catalog.catalog_reasonability import build_catalog_reasonability_artifact

        # Create enough CPUs (>8) with one extreme outlier
        cpus = []
        prods = []
        for i in range(10):
            cid = f"CPU-{i}"
            pid = f"P-{i}"
            val = 50.0 if i < 9 else 5000.0  # last is outlier
            cpus.append(self._make_cpu(cid, producao_id_ref=pid))
            prods.append(self._make_producao(pid, val))
        result = build_catalog_reasonability_artifact("cat-1", cpus, prods)
        assert result["summary"]["outliers"] > 0

    def test_artifact_structure(self):
        from concilium.application.services.catalog.catalog_reasonability import build_catalog_reasonability_artifact

        cpu = self._make_cpu()
        prod = self._make_producao()
        result = build_catalog_reasonability_artifact("cat-1", [cpu], [prod])
        assert "catalog_id" in result
        assert "generated_at" in result
        assert "summary" in result
        assert "narrative" in result
        assert "findings" in result
        assert "rows" in result
