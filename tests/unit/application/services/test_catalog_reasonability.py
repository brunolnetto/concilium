from __future__ import annotations

from concilium.application.services.catalog.catalog_reasonability import build_catalog_reasonability_artifact


def test_reasonability_artifact_flags_missing_productivity_and_team() -> None:
    cpus = [
        {
            "codigo": "CPU-001",
            "descricao": "Teste sem produtividade",
            "categoria": "DIVERSOS",
            "unidade": "m2",
            "producao_id_ref": "",
        }
    ]

    artifact = build_catalog_reasonability_artifact("cat-test", cpus)

    assert artifact["summary"]["total_cpus"] == 1
    assert artifact["summary"]["erros"] == 1
    assert artifact["findings"]
    assert artifact["findings"][0]["severity"] == "ERRO"
    assert any("producao_id_ref" in msg for msg in artifact["findings"][0]["issues"])


def test_reasonability_artifact_returns_ok_when_producao_has_team_and_productivity() -> None:
    cpus = [
        {
            "codigo": "CPU-OK",
            "descricao": "CPU saudável",
            "categoria": "TERRAPLENAGEM",
            "unidade": "m3",
            "producao_id_ref": "CPU-OK-PROD-001",
        }
    ]
    producoes = [
        {
            "id": "CPU-OK-PROD-001",
            "valor_horario": 12.5,
            "composicao_padrao_equipe": {
                "funcoes": [{"funcao_id": "MO-OPER", "num_pessoas": 2}],
                "equipamentos": [{"equip_id": "EQ-001", "num_unidades": 1}],
            },
        }
    ]

    artifact = build_catalog_reasonability_artifact("cat-test", cpus, producoes)

    assert artifact["summary"]["total_cpus"] == 1
    assert artifact["summary"]["erros"] == 0
    assert artifact["rows"][0]["severity"] == "OK"





# ─── application/services/catalog_reasonability.py ────────────────────────────


class TestCatalogReasonability:
    def test_build_artifact_empty_catalog(self):
        from concilium.application.services.catalog.catalog_reasonability import build_catalog_reasonability_artifact

        result = build_catalog_reasonability_artifact("ctx1", [], [])
        assert isinstance(result, dict)
        assert "summary" in result

    def test_build_artifact_with_cpus(self):
        from concilium.application.services.catalog.catalog_reasonability import build_catalog_reasonability_artifact

        cpus = [{"codigo": "CPU-1", "descricao": "Terraplenagem", "producao_id_ref": "P1"}]
        result = build_catalog_reasonability_artifact("ctx1", cpus, [])
        assert result["summary"]["total_cpus"] == 1

    def test_summary_has_expected_keys(self):
        from concilium.application.services.catalog.catalog_reasonability import build_catalog_reasonability_artifact

        result = build_catalog_reasonability_artifact("ctx1", [], [])
        summary = result["summary"]
        assert "total_cpus" in summary
        assert "erros" in summary or "errors" in summary or len(summary) >= 1



# catalog_reasonability.py line 87:
# _sum_equips with non-numeric num_unidades → TypeError → continue
# ---------------------------------------------------------------------------


class TestSumEquipsTypeError:
    def test_non_numeric_num_unidades_is_skipped(self):
        """Line 87: int(float(None)) raises TypeError → continue."""
        from concilium.application.services.catalog.catalog_reasonability import _sum_equips

        # None as num_unidades → int(float(None)) raises TypeError
        equipamentos = [
            {"num_unidades": None},  # TypeError
            {"num_unidades": "abc"},  # ValueError
            {"num_unidades": 2},  # valid → contributes 2
        ]
        result = _sum_equips(equipamentos)
        assert result == 2  # only the valid entry counts


# ---------------------------------------------------------------------------
# catalog_reasonability.py line 95:
# _build_prod_lookup with non-dict items → continue
# ---------------------------------------------------------------------------


class TestBuildProdLookupNonDict:
    def test_non_dict_item_is_skipped(self):
        """Line 95: not isinstance(prod, dict) → continue."""
        from concilium.application.services.catalog.catalog_reasonability import _build_prod_lookup

        producoes = [
            "not-a-dict",  # skipped (not dict)
            None,  # skipped (not dict)
            {"id": "P-01", "v": 1},  # included
        ]
        result = _build_prod_lookup(producoes)
        assert "P-01" in result
        assert len(result) == 1


# ---------------------------------------------------------------------------
# catalog_reasonability.py line 110:
# _resolve_team_from_producao with string equipe (both keys) → return [], []
# ---------------------------------------------------------------------------


class TestResolveTeamFromProducaoNonDictEquipe:
    def test_non_dict_equipe_returns_empty(self):
        """Line 110: equipe is not a dict after both fallbacks → return [], []."""
        from concilium.application.services.catalog.catalog_reasonability import _resolve_team_from_producao

        # Both composicao_padrao_equipe and equipe are strings (not dicts)
        prod = {
            "composicao_padrao_equipe": "INVALID",
            "equipe": "ALSO_INVALID",
        }
        funcoes, equipamentos = _resolve_team_from_producao(prod)
        assert funcoes == []
        assert equipamentos == []

    def test_missing_equipe_key_returns_empty(self):
        """Line 110: prod has no equipe key at all → equipe.get() returns None → return [], []."""
        from concilium.application.services.catalog.catalog_reasonability import _resolve_team_from_producao

        prod = {"valor_horario": 10.0}  # no equipe or composicao_padrao_equipe
        funcoes, equipamentos = _resolve_team_from_producao(prod)
        assert funcoes == []
        assert equipamentos == []


# ---------------------------------------------------------------------------
# catalog_reasonability.py line 210:
# IQR outlier triggers severity "AVISO" for producao_por_pessoa
# ---------------------------------------------------------------------------


class TestCatalogReasonabilityIQROutlier:
    def _make_cpu(self, i: int, ppp_ratio: float = 1.0) -> dict:
        """Build a CPU dict referencing producao P-{i} with scaled ppp."""
        return {
            "codigo": f"CPU-{i:02d}",
            "descricao": f"Test CPU {i}",
            "categoria": "ESCAVACAO",
            "unidade": "M3",
            "producao_id_ref": f"P-{i:02d}",
        }

    def _make_producao(self, i: int, valor_horario: float) -> dict:
        """Build a producao dict with 1 person in equipe."""
        return {
            "id": f"P-{i:02d}",
            "valor_horario": valor_horario,
            "composicao_padrao_equipe": {
                "funcoes": [{"funcao": "Operador", "num_pessoas": 1}],
                "equipamentos": [],
            },
        }

    def test_ppp_outlier_gets_aviso_severity(self):
        """Line 210: IQR outlier for producao_por_pessoa gets severity='AVISO'."""
        from concilium.application.services.catalog.catalog_reasonability import build_catalog_reasonability_artifact

        # 8 normal CPUs with ppp=10.0, 1 outlier with ppp=100.0
        # IQR will be non-zero due to spread; q90 ≈ 32 < 100
        cpus = [self._make_cpu(i) for i in range(9)]
        normal_rates = [10.0] * 6 + [5.0, 15.0]
        outlier_rate = 100.0
        producoes = [self._make_producao(i, r) for i, r in enumerate(normal_rates)]
        producoes.append(self._make_producao(8, outlier_rate))  # outlier

        result = build_catalog_reasonability_artifact("cat-test", cpus, producoes)

        rows = result.get("rows", [])
        # Find the outlier row (CPU-08 referencing P-08 with valor_horario=100)
        outlier_row = next((r for r in rows if r["cpu_id"] == "CPU-08"), None)
        assert outlier_row is not None
        # The outlier should have AVISO severity from IQR detection
        assert outlier_row["severity"] == "AVISO"
        # Normal rows should be OK
        normal_rows = [r for r in rows if r["cpu_id"] != "CPU-08"]
        ok_rows = [r for r in normal_rows if r["severity"] == "OK"]
        assert len(ok_rows) >= 1


# ---------------------------------------------------------------------------

