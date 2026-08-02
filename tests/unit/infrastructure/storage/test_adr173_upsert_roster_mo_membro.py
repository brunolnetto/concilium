"""EscopoStore.upsert_roster_mo_membro (ADR-173 F3/D5).

Merge por individuo_id: adiciona membro novo, edita campos de membro existente
(merge raso), nunca remove um registro já presente na lista.
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


class TestUpsertRosterMoMembro:
    def test_adiciona_membro_novo(self, tmp_path):
        es = _make_escopo_store(tmp_path)
        es.upsert_roster_mo_membro(
            {
                "individuo_id": "mo-001",
                "funcao_id": "MO-ARMADOR",
                "salario_base_mensal": 3200.0,
                "data_admissao": "2026-01-05",
            }
        )
        roster = es.meta["roster_mo"]
        assert len(roster) == 1
        assert roster[0]["individuo_id"] == "mo-001"

    def test_edita_membro_existente_merge_raso(self, tmp_path):
        es = _make_escopo_store(tmp_path)
        es.upsert_roster_mo_membro(
            {
                "individuo_id": "mo-001",
                "funcao_id": "MO-ARMADOR",
                "salario_base_mensal": 3200.0,
                "data_admissao": "2026-01-05",
            }
        )
        # "desligar": só envia individuo_id + data_desligamento
        es.upsert_roster_mo_membro({"individuo_id": "mo-001", "data_desligamento": "2026-06-30"})

        roster = es.meta["roster_mo"]
        assert len(roster) == 1
        assert roster[0]["funcao_id"] == "MO-ARMADOR"  # preservado
        assert roster[0]["salario_base_mensal"] == 3200.0  # preservado
        assert roster[0]["data_desligamento"] == "2026-06-30"  # novo

    def test_nunca_remove_membro_existente(self, tmp_path):
        es = _make_escopo_store(tmp_path)
        es.upsert_roster_mo_membro({"individuo_id": "mo-001", "funcao_id": "MO-ARMADOR"})
        es.upsert_roster_mo_membro({"individuo_id": "mo-002", "funcao_id": "MO-CARPINTEIRO"})
        roster = es.meta["roster_mo"]
        assert {m["individuo_id"] for m in roster} == {"mo-001", "mo-002"}

    def test_exige_individuo_id(self, tmp_path):
        es = _make_escopo_store(tmp_path)
        with pytest.raises(ValueError, match="individuo_id"):
            es.upsert_roster_mo_membro({"funcao_id": "MO-ARMADOR"})

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
        es.upsert_roster_mo_membro(
            {
                "individuo_id": "mo-001",
                "funcao_id": "MO-ARMADOR",
                "salario_base_mensal": 3200.0,
                "data_admissao": "2026-01-05",
            }
        )
        escopo = es.to_escopo()
        assert escopo.roster_mo[0].individuo_id == "mo-001"
