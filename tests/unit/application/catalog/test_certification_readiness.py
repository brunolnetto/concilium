"""Readiness audit uses the pipeline's own predicates and agrees with the golden GO."""

from __future__ import annotations

import copy
import json
from pathlib import Path

import pytest

from concilium.application.catalog.certification_readiness import audit_catalog, render_markdown
from concilium.application.runtime import Runtime
from concilium.application.scheduling.formalism_certification_service import production_calibration_gaps

ROOT = Path(__file__).resolve().parents[4]
GOLDEN = json.loads((ROOT / "tests/fixtures/formalism_golden_rfp/spec.json").read_text(encoding="utf-8"))


@pytest.fixture(scope="module")
def mendeslobo_with_fixture_cpus() -> dict:
    catalog = copy.deepcopy(Runtime(ROOT / "config").load_catalogo("mendeslobo"))
    catalog["cpus"] = list(catalog["cpus"]) + GOLDEN["fixture_cpus"]
    return catalog


def test_calibrated_sicro_production_has_no_gaps(mendeslobo_with_fixture_cpus: dict) -> None:
    productions = {p["id"]: p for p in mendeslobo_with_fixture_cpus["producoes"]}
    assert production_calibration_gaps(productions["PROD-USINAGEM-CBUQ-001"]) == []


def test_estimated_production_reports_each_missing_field() -> None:
    gaps = production_calibration_gaps({"origem": {"tipo": "estimado"}, "grafo_sinergia": {"relacoes": []}})
    assert any("origem.tipo='estimado'" in g for g in gaps)
    assert {"origem.fonte_id ausente", "auditoria.versao ausente"} <= set(gaps)
    assert any(g.startswith("qualidade.quantidade_amostras") for g in gaps)


def test_audit_agrees_with_the_golden_go(mendeslobo_with_fixture_cpus: dict) -> None:
    rows = {r.codigo: r for r in audit_catalog(mendeslobo_with_fixture_cpus)}
    for code in ("CPU-FIXT-USINAGEM-BGTC", "CPU-FIXT-USINAGEM-CBUQ"):
        assert rows[code].pronta, rows[code]
    # Real catalog CPUs are not ready today, and every non-ready row says why.
    real = [r for c, r in rows.items() if not c.startswith("CPU-FIXT-")]
    assert real and not any(r.pronta for r in real)
    assert all(r.acoes for r in real)


def test_audit_classifies_consumption_situations() -> None:
    catalog = {
        "cpus": [
            {"codigo": "CPU-NONE", "unidade": "m2", "producao_id_ref": "P1", "composicao_itens": []},
            {
                "codigo": "CPU-DECL",
                "unidade": "m2",
                "producao_id_ref": "P1",
                "composicao_itens": [],
                "consumiveis_declarados": {"status": "NENHUM", "justificativa": "serviço manual", "fonte": "campo"},
            },
            {"codigo": "CPU-HOUR", "unidade": "m2", "producao_id_ref": "P2", "composicao_itens": []},
        ],
        "producoes": [
            {"id": "P1", "unidade": "m2", "producao_horaria": 10, "composicao_padrao_equipe": {"funcoes": []}},
            {
                "id": "P2",
                "unidade": "m2",
                "producao_horaria": 10,
                "composicao_padrao_equipe": {
                    "equipamentos": [{"equip_id": "E", "num_unidades": 1, "consumo_litros_hora": 9}]
                },
            },
        ],
        "insumos": [],
    }
    rows = {r.codigo: r for r in audit_catalog(catalog)}
    assert (rows["CPU-NONE"].p18_situacao, rows["CPU-NONE"].p18_erro is not None) == ("SEM_BOM", True)
    assert any("consumiveis_declarados" in a for a in rows["CPU-NONE"].acoes)
    assert (rows["CPU-DECL"].p18_situacao, rows["CPU-DECL"].p18_erro) == ("DECLARADO_NENHUM", None)
    assert rows["CPU-HOUR"].p18_situacao == "CONSUMO_SO_HORARIO"
    report = render_markdown("synthetic", list(rows.values()))
    assert "| V5 — produtividade calibrada | 0 | 3 |" in report
