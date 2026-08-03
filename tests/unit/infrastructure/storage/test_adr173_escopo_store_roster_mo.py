"""Persistência de Escopo.roster_mo via EscopoStore (ADR-173 F1, filesystem).

Mesmo padrão de `logistica_consumiveis` (ADR-128 F5): `update_meta` grava o dict
cru, `to_escopo()` valida contra o modelo Pydantic (converte para MembroEquipeReal).
"""

from __future__ import annotations

from concilium.infrastructure.storage.escopo_store import EscopoStore


def _make_escopo_store(tmp_path):
    root = tmp_path / "escopos" / "esc-1"
    root.mkdir(parents=True)
    es = EscopoStore(root=root)
    es.update_meta(
        escopo_id="esc-1",
        projeto_id="proj-1",
        nome="Lote A",
        tipo_obra="terraplenagem",
        localizacao="Fortaleza-CE",
        coordenadas_lat=-3.7172,
        coordenadas_lng=-38.5433,
        data_inicio="2026-01-01",
        data_termino="2026-12-31",
    )
    return es


class TestRosterMoPersistenciaFilesystem:
    def test_default_e_lista_vazia(self, tmp_path):
        es = _make_escopo_store(tmp_path)
        escopo = es.to_escopo()
        assert escopo is not None
        assert escopo.roster_mo == []

    def test_persiste_e_rele_roster(self, tmp_path):
        es = _make_escopo_store(tmp_path)
        es.update_meta(
            roster_mo=[
                {
                    "individuo_id": "mo-001",
                    "funcao_id": "MO-ARMADOR",
                    "salario_base_mensal": 3200.0,
                    "data_admissao": "2026-01-05",
                }
            ]
        )
        escopo = es.to_escopo()
        assert len(escopo.roster_mo) == 1
        assert escopo.roster_mo[0].individuo_id == "mo-001"
        assert escopo.roster_mo[0].funcao_id == "MO-ARMADOR"

    def test_roundtrip_preserva_desligamento(self, tmp_path):
        es = _make_escopo_store(tmp_path)
        es.update_meta(
            roster_mo=[
                {
                    "individuo_id": "mo-002",
                    "funcao_id": "MO-CARPINTEIRO",
                    "salario_base_mensal": 2800.0,
                    "data_admissao": "2026-01-05",
                    "data_desligamento": "2026-06-30",
                }
            ]
        )
        # nova instância de EscopoStore lendo do mesmo root — roundtrip real via disco
        es2 = EscopoStore(root=es.root)
        escopo = es2.to_escopo()
        assert str(escopo.roster_mo[0].data_desligamento) == "2026-06-30"

    def test_update_meta_incremental_preserva_membros_anteriores_quando_reenviado_completo(self, tmp_path):
        """update_meta faz merge de chaves top-level — para roster_mo, quem chama
        deve reenviar a lista completa (merge por-membro é responsabilidade da
        camada MCP/gerir_escopo, ADR-173 F3, não do EscopoStore)."""
        es = _make_escopo_store(tmp_path)
        es.update_meta(
            roster_mo=[
                {
                    "individuo_id": "mo-001",
                    "funcao_id": "MO-ARMADOR",
                    "salario_base_mensal": 3200.0,
                    "data_admissao": "2026-01-05",
                }
            ]
        )
        es.update_meta(
            roster_mo=[
                {
                    "individuo_id": "mo-001",
                    "funcao_id": "MO-ARMADOR",
                    "salario_base_mensal": 3200.0,
                    "data_admissao": "2026-01-05",
                },
                {
                    "individuo_id": "mo-002",
                    "funcao_id": "MO-ARMADOR",
                    "salario_base_mensal": 3100.0,
                    "data_admissao": "2026-02-01",
                },
            ]
        )
        escopo = es.to_escopo()
        assert {m.individuo_id for m in escopo.roster_mo} == {"mo-001", "mo-002"}
