"""EscopoStore.upsert_roster_eq_ativo (ADR-174 F1/D2).

Espelha test_adr173_upsert_roster_mo_membro.py — merge por ativo_id, nunca
remove.
"""

from __future__ import annotations

import pytest

from concilium.infrastructure.storage.escopo_store import EscopoStore


def _make_escopo_store(tmp_path):
    root = tmp_path / "escopos" / "esc-1"
    root.mkdir(parents=True)
    es = EscopoStore(root=root)
    es.update_meta(escopo_id="esc-1", projeto_id="proj-1")
    return es


class TestUpsertRosterEqAtivo:
    def test_adiciona_ativo_novo(self, tmp_path):
        es = _make_escopo_store(tmp_path)
        es.upsert_roster_eq_ativo(
            {
                "ativo_id": "eq-001",
                "equip_id": "EQ-ESCAVADEIRA",
                "custo_locacao_mensal_real": 12000.0,
                "data_contrato_inicio": "2026-01-05",
            }
        )
        roster = es.meta["roster_eq"]
        assert len(roster) == 1
        assert roster[0]["ativo_id"] == "eq-001"

    def test_edita_ativo_existente_merge_raso(self, tmp_path):
        es = _make_escopo_store(tmp_path)
        es.upsert_roster_eq_ativo(
            {
                "ativo_id": "eq-001",
                "equip_id": "EQ-ESCAVADEIRA",
                "custo_locacao_mensal_real": 12000.0,
                "data_contrato_inicio": "2026-01-05",
            }
        )
        es.upsert_roster_eq_ativo({"ativo_id": "eq-001", "data_contrato_fim": "2026-06-30"})

        roster = es.meta["roster_eq"]
        assert len(roster) == 1
        assert roster[0]["equip_id"] == "EQ-ESCAVADEIRA"
        assert roster[0]["custo_locacao_mensal_real"] == 12000.0
        assert roster[0]["data_contrato_fim"] == "2026-06-30"

    def test_nunca_remove_ativo_existente(self, tmp_path):
        es = _make_escopo_store(tmp_path)
        es.upsert_roster_eq_ativo({"ativo_id": "eq-001", "equip_id": "EQ-ESCAVADEIRA"})
        es.upsert_roster_eq_ativo({"ativo_id": "eq-002", "equip_id": "EQ-CAMINHAO"})
        roster = es.meta["roster_eq"]
        assert {a["ativo_id"] for a in roster} == {"eq-001", "eq-002"}

    def test_exige_ativo_id(self, tmp_path):
        es = _make_escopo_store(tmp_path)
        with pytest.raises(ValueError, match="ativo_id"):
            es.upsert_roster_eq_ativo({"equip_id": "EQ-ESCAVADEIRA"})

    def test_roundtrip_via_to_escopo(self, tmp_path):
        es = _make_escopo_store(tmp_path)
        es.update_meta(
            nome="Lote A",
            tipo_obra="terraplenagem",
            localizacao="Fortaleza-CE",
            coordenadas_lat=-3.7172,
            coordenadas_lng=-38.5433,
            data_inicio="2026-01-01",
            data_termino="2026-12-31",
        )
        es.upsert_roster_eq_ativo(
            {
                "ativo_id": "eq-001",
                "equip_id": "EQ-ESCAVADEIRA",
                "custo_locacao_mensal_real": 12000.0,
                "data_contrato_inicio": "2026-01-05",
            }
        )
        escopo = es.to_escopo()
        assert escopo.roster_eq[0].ativo_id == "eq-001"
