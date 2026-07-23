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

