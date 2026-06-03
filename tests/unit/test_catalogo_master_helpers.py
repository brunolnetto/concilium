from __future__ import annotations

import json

from concilium.presentation.ui.templates import _catalogo_master_helpers as helpers


def test_resolve_equipe_prefers_inline_team(monkeypatch):
    cpu = {"equipe": {"funcoes": [{"funcao_id": "MO-001", "num_pessoas": 2}], "equipamentos": []}}

    def _fail_if_called(_catalog_id: str):
        raise AssertionError("productivity index should not be consulted when equipe is inline")

    monkeypatch.setattr(helpers, "_cmb_load_produtividades_index", _fail_if_called)

    equipe = helpers._cmb_resolve_equipe(cpu, "demo")
    assert equipe["equipamentos"] == []
    assert equipe["funcoes"][0]["funcao_id"] == "MO-001"
    assert equipe["funcoes"][0]["num_pessoas"] == 2


def test_resolve_equipe_uses_produtividade_index(tmp_path, monkeypatch):
    catalog_root = tmp_path / "config" / "catalogos" / "demo" / "produtividades"
    catalog_root.mkdir(parents=True)
    (catalog_root / "CPU-001-PROD-001.json").write_text(
        json.dumps(
            {
                "id": "CPU-001-PROD-001",
                "composicao_padrao_equipe": {
                    "funcoes": [{"funcao_id": "MO-ENCARREG-TERRA", "num_pessoas": 1}],
                    "equipamentos": [{"equip_id": "EQ-E0001", "num_unidades": 1}],
                },
            }
        ),
        encoding="utf-8",
    )

    monkeypatch.setattr(helpers, "_cmb_workspace_root", lambda: tmp_path)
    monkeypatch.setattr(helpers.st, "session_state", {})

    cpu = {"codigo": "CPU-001", "producao_id_ref": "CPU-001-PROD-001"}
    equipe = helpers._cmb_resolve_equipe(cpu, "demo")

    assert equipe.get("funcoes", [])[0]["funcao_id"] == "MO-ENCARREG-TERRA"
    assert equipe.get("equipamentos", [])[0]["equip_id"] == "EQ-E0001"


def test_resolve_equipe_enriches_funcoes_from_insumos(tmp_path, monkeypatch):
    prod_root = tmp_path / "config" / "catalogos" / "demo" / "produtividades"
    insumo_root = tmp_path / "config" / "catalogos" / "demo" / "insumos" / "mao_obra"
    prod_root.mkdir(parents=True)
    insumo_root.mkdir(parents=True)

    (prod_root / "CPU-001-PROD-001.json").write_text(
        json.dumps(
            {
                "id": "CPU-001-PROD-001",
                "composicao_padrao_equipe": {
                    "funcoes": [{"funcao_id": "MO-ENCARREG-TERRA", "num_pessoas": 1}],
                    "equipamentos": [],
                },
            }
        ),
        encoding="utf-8",
    )
    (insumo_root / "MO-ENCARREG-TERRA.json").write_text(
        json.dumps(
            {
                "codigo": "MO-ENCARREG-TERRA",
                "tipo": "MAO_OBRA",
                "descricao": "Encarregado de Terraplenagem",
                "unidade": "mes",
                "preco_unitario": 4485.36,
                "atributos_especificos": {"categoria_sindical": "horista_CE"},
            }
        ),
        encoding="utf-8",
    )

    monkeypatch.setattr(helpers, "_cmb_workspace_root", lambda: tmp_path)
    monkeypatch.setattr(helpers.st, "session_state", {})

    cpu = {"codigo": "CPU-001", "producao_id_ref": "CPU-001-PROD-001"}
    equipe = helpers._cmb_resolve_equipe(cpu, "demo")
    funcao = equipe.get("funcoes", [])[0]

    assert funcao["regime"] == "Horista"
    assert funcao["salario_base"] == 4485.36


def test_comp_badge_only_falls_back_when_empty(monkeypatch):
    monkeypatch.setattr(helpers, "_cmb_load_produtividades_index", lambda _catalog_id: {})

    empty_cpu = {"codigo": "CPU-Z"}
    assert helpers._cmb_comp_badge(empty_cpu, "demo") == "(sem composição)"


def test_enrich_composicao_itens_includes_description_and_unit(tmp_path, monkeypatch):
    insumo_root = tmp_path / "config" / "catalogos" / "demo" / "insumos" / "material"
    insumo_root.mkdir(parents=True)
    (insumo_root / "MA-DIESEL-S10.json").write_text(
        json.dumps(
            {
                "codigo": "MA-DIESEL-S10",
                "tipo": "MATERIAL",
                "descricao": "Óleo diesel S10",
                "unidade": "litro",
                "preco_unitario": 6.99,
            }
        ),
        encoding="utf-8",
    )

    monkeypatch.setattr(helpers, "_cmb_workspace_root", lambda: tmp_path)
    monkeypatch.setattr(helpers.st, "session_state", {})

    enriched = helpers._cmb_enrich_composicao_itens(
        [{"insumo_id": "MA-DIESEL-S10", "coeficiente": 10, "categoria_custo": "DIESEL"}],
        "demo",
    )

    row = enriched[0]
    assert row["descricao"] == "Óleo diesel S10"
    assert row["unidade"] == "litro"


def test_enrich_equipamentos_includes_monthly_cost(tmp_path, monkeypatch):
    equip_root = tmp_path / "config" / "catalogos" / "demo" / "insumos" / "equipamento"
    equip_root.mkdir(parents=True)
    (equip_root / "EQ-E0001.json").write_text(
        json.dumps(
            {
                "codigo": "EQ-E0001",
                "tipo": "EQUIPAMENTO",
                "descricao": "Automóvel (veículo leve)",
                "unidade": "h",
                "preco_unitario": 22.0,
                "atributos_especificos": {"valor_locacao_mensal": 4400.0, "horas_mes": 200},
            }
        ),
        encoding="utf-8",
    )

    monkeypatch.setattr(helpers, "_cmb_workspace_root", lambda: tmp_path)
    monkeypatch.setattr(helpers.st, "session_state", {})

    enriched = helpers._cmb_enrich_equipamentos([{"equip_id": "EQ-E0001", "num_unidades": 1}], "demo")

    row = enriched[0]
    assert row["descricao"] == "Automóvel (veículo leve)"
    assert row["unidade"] == "h"
    assert row["custo_mensal"] == 4400.0
