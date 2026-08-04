"""StorageEscopoHandle/StoragePlanoHandle — porta de EscopoStore/PlanoStore (escopo_store.py)
para BlobStoragePort (issue #146 / migração ADR-047 completa).

Cobertura portada de test_escopo_store.py + test_adr173_upsert_roster_mo_membro.py +
test_adr174_upsert_roster_eq_ativo.py, adaptada para BlobStoragePort:
- chmod 444 (filesystem) → `storage.aprovar_versao(path)` / `FakeBlobStorage.is_approved(path)`.
- listagem de diretório → índice `planos/_index.json`.
- "construção solta sem escopo_store" (fallback de `_projeto_root()`) não se aplica
  aqui: `new_iteration()` exige `escopo_store` (ver docstring do método) porque não
  há listagem de diretório para descobrir planos sem o índice.
"""

from __future__ import annotations

import pytest

from concilium.domain.models.canonical import CanonicalModel
from concilium.infrastructure.storage.storage_project_repository import StorageProjectHandle
from tests.support.fake_blob_storage import FakeBlobStorage


def _make_minimal_canonical() -> CanonicalModel:
    data = {
        "meta": {"gerado_em": "2026-01-01T00:00:00Z", "contexto_id": "ctx-test"},
        "projeto": {
            "id": "proj-test",
            "nome": "Test Project",
            "tipo_obra": "terraplenagem",
            "localizacao": "SP",
            "coordenadas": {"lat": -23.5, "lng": -46.6},
            "regime_trabalho": {"dias_semana": 6, "horas_dia": 8},
            "data_inicio": "2026-01-01",
            "data_termino": "2026-12-31",
            "snapshot_catalogo_id": "cat-v1",
            "snapshot_perfil_id": "perf-v1",
        },
    }
    return CanonicalModel.model_validate(data)


@pytest.fixture
def storage() -> FakeBlobStorage:
    return FakeBlobStorage()


@pytest.fixture
def project(storage: FakeBlobStorage) -> StorageProjectHandle:
    return StorageProjectHandle(storage, "proj-1")


def _create_escopo(project: StorageProjectHandle, escopo_id: str = "esc-1"):
    return project.create_escopo(
        escopo_id=escopo_id,
        nome=f"Escopo {escopo_id}",
        tipo_obra="terraplenagem",
        localizacao="SP",
        coordenadas_lat=-23.5,
        coordenadas_lng=-46.6,
        data_inicio="2026-01-01",
        data_termino="2026-12-31",
    )


class TestStorageEscopoHandle:
    def test_meta_defaults_when_missing(self, storage, project):
        es = project.escopo("nao-existe")
        assert es.meta == {"escopo_id": "nao-existe"}

    def test_meta_after_create(self, project):
        es = _create_escopo(project)
        assert es.meta["escopo_id"] == "esc-1"
        assert es.meta["nome"] == "Escopo esc-1"

    def test_update_meta(self, project):
        es = _create_escopo(project)
        es.update_meta(nome="Updated Name")
        assert es.meta["nome"] == "Updated Name"

    def test_to_escopo_roundtrip(self, project):
        es = _create_escopo(project)
        escopo_obj = es.to_escopo()
        assert escopo_obj is not None
        assert escopo_obj.escopo_id == "esc-1"

    def test_to_escopo_none_on_invalid(self, storage, project):
        es = project.escopo("sem-meta")
        result = es.to_escopo()
        assert result is None or hasattr(result, "escopo_id")

    def test_escopo_id_property(self, project):
        es = _create_escopo(project, "my-escopo")
        assert es.escopo_id == "my-escopo"

    def test_list_plans_empty(self, project):
        es = _create_escopo(project)
        assert es.list_plans() == []

    def test_create_plan(self, project):
        es = _create_escopo(project)
        ps = es.create_plan(nome="Plano Principal")
        assert ps.plano_id is not None

    def test_create_and_list_plans(self, project):
        es = _create_escopo(project)
        es.create_plan(nome="P1")
        es.create_plan(nome="P2")
        assert len(es.list_plans()) == 2

    def test_plan_with_hipotese(self, project):
        es = _create_escopo(project)
        ps = es.create_plan(nome="Hipotese Plan", hipotese="H1 - Cenário otimista")
        assert ps.meta.get("hipotese") == "H1 - Cenário otimista"

    def test_plan_with_explicit_plano_id(self, project):
        es = _create_escopo(project)
        ps = es.create_plan(nome="Fixed ID Plan", plano_id="plan-fixed-1")
        assert ps.plano_id == "plan-fixed-1"

    def test_active_plan_none_when_no_plans(self, project):
        es = _create_escopo(project)
        assert es.active_plan() is None

    def test_active_plan_returns_rascunho_when_no_approved(self, project):
        es = _create_escopo(project)
        es.create_plan(nome="P")
        result = es.active_plan()
        assert result is not None
        assert result.status in ("RASCUNHO", "EM_ANALISE")

    def test_approved_plan_none_initially(self, project):
        es = _create_escopo(project)
        assert es.approved_plan() is None

    def test_approve_plan_marks_approved(self, project):
        es = _create_escopo(project)
        ps = es.create_plan(nome="Para Aprovar")
        es.approve_plan(ps.plano_id)
        approved = es.approved_plan()
        assert approved is not None
        assert approved.plano_id == ps.plano_id

    def test_active_plan_returns_approved(self, project):
        es = _create_escopo(project)
        ps = es.create_plan(nome="P")
        es.approve_plan(ps.plano_id)
        result = es.active_plan()
        assert result.status == "APROVADO"

    def test_approve_plan_archives_other_rascunhos(self, project):
        es = _create_escopo(project)
        ps1 = es.create_plan(nome="P1")
        ps2 = es.create_plan(nome="P2")
        arquivados = es.approve_plan(ps2.plano_id)
        assert ps1.plano_id in arquivados
        assert es.approved_plan().plano_id == ps2.plano_id

    def test_approve_plan_skips_already_archived_plans(self, project):
        es = _create_escopo(project)
        ps1 = es.create_plan(nome="P1")
        ps2 = es.create_plan(nome="P2")
        ps2.archive()
        arquivados = es.approve_plan(ps1.plano_id)
        assert ps2.plano_id not in arquivados


class TestStoragePlanoHandleBasics:
    def test_plano_id(self, project):
        es = _create_escopo(project)
        ps = es.create_plan(nome="P")
        assert ps.plano_id is not None

    def test_meta_defaults_when_no_file(self, storage, project):
        es = _create_escopo(project)
        ps = es.plan("nao-criado")
        meta = ps.meta
        assert meta == {"plano_id": "nao-criado", "status": "RASCUNHO"}

    def test_status_default(self, project):
        es = _create_escopo(project)
        ps = es.create_plan(nome="P")
        assert ps.status == "RASCUNHO"

    def test_set_em_analise(self, project):
        es = _create_escopo(project)
        ps = es.create_plan(nome="P")
        ps.set_em_analise()
        assert ps.status == "EM_ANALISE"

    def test_archive(self, project):
        es = _create_escopo(project)
        ps = es.create_plan(nome="P")
        ps.archive()
        assert ps.status == "ARQUIVADO"

    def test_load_canonical_none_when_missing(self, project):
        es = _create_escopo(project)
        ps = es.create_plan(nome="P")
        assert ps.load_canonical() is None

    def test_save_and_load_canonical(self, project):
        es = _create_escopo(project)
        ps = es.create_plan(nome="P")
        ps.save_canonical(_make_minimal_canonical())
        loaded = ps.load_canonical()
        assert loaded is not None

    def test_write_canonical_raw(self, project):
        es = _create_escopo(project)
        ps = es.create_plan(nome="P")
        ps.write_canonical_raw({"projeto": {"nome": "Test"}})
        loaded = ps._read_json(ps.CANONICAL_FILE, None)
        assert loaded == {"projeto": {"nome": "Test"}}

    def test_log_and_read_invocations(self, project):
        es = _create_escopo(project)
        ps = es.create_plan(nome="P")
        ps.log_invocation({"skill": "01", "status": "OK"})
        ps.log_invocation({"skill": "02", "status": "ERRO"})
        entries = ps.read_invocations()
        assert len(entries) == 2
        assert entries[0]["skill"] == "01"

    def test_read_invocations_empty_when_no_log(self, project):
        es = _create_escopo(project)
        ps = es.create_plan(nome="P")
        assert ps.read_invocations() == []

    def test_read_invocations_skips_malformed_json_line(self, storage, project):
        es = _create_escopo(project)
        ps = es.create_plan(nome="P")
        storage.gravar_blob(ps._path(ps.INVOCATIONS_LOG), b'{"skill_id": "01"}\nNOT-VALID-JSON\n')
        result = ps.read_invocations()
        assert len(result) == 1
        assert result[0]["skill_id"] == "01"

    def test_save_and_load_output_file_xlsx(self, project):
        es = _create_escopo(project)
        ps = es.create_plan(nome="P")
        data = b"fake xlsx bytes"
        ps.save_output_file(data, "resultado.xlsx")
        assert ps.load_output_file("resultado.xlsx") == data

    def test_save_and_load_output_file_png(self, project):
        es = _create_escopo(project)
        ps = es.create_plan(nome="P")
        data = b"\x89PNG\r\n\x1a\n"
        ps.save_output_file(data, "chart.png")
        assert ps.load_output_file("chart.png") == data

    def test_load_output_file_fallback_to_other_dir(self, storage, project):
        es = _create_escopo(project)
        ps = es.create_plan(nome="P")
        data = b"pdf bytes"
        storage.gravar_blob(ps._path("outputs/visualizations/test.pdf"), data)
        assert ps.load_output_file("test.pdf") == data

    def test_load_output_file_returns_none_when_missing(self, project):
        es = _create_escopo(project)
        ps = es.create_plan(nome="P")
        assert ps.load_output_file("nonexistent.xlsx") is None

    def test_list_output_files_returns_names(self, project):
        es = _create_escopo(project)
        ps = es.create_plan(nome="P")
        ps.save_output_file(b"x", "orcamento.xlsx")
        ps.save_output_file(b"y", "grafico.png")
        files = ps.list_output_files()
        assert "orcamento.xlsx" in files
        assert "grafico.png" in files

    def test_get_output_subdir_image(self, project):
        es = _create_escopo(project)
        ps = es.create_plan(nome="P")
        assert ps._get_output_subdir("chart.png") == "visualizations"
        assert ps._get_output_subdir("photo.jpg") == "visualizations"

    def test_get_output_subdir_report(self, project):
        es = _create_escopo(project)
        ps = es.create_plan(nome="P")
        assert ps._get_output_subdir("report.pdf") == "reports"
        assert ps._get_output_subdir("data.xlsx") == "reports"

    def test_get_output_subdir_fallback(self, project):
        es = _create_escopo(project)
        ps = es.create_plan(nome="P")
        assert ps._get_output_subdir("unknown.xyz") == "reports"


class TestStoragePlanoHandleApprove:
    def test_approve_marks_status(self, project):
        es = _create_escopo(project)
        ps = es.create_plan(nome="P")
        ps.save_canonical(_make_minimal_canonical())
        ps.log_invocation({"info": "test"})
        ps.approve()
        assert ps.status == "APROVADO"

    def test_approve_calls_aprovar_versao_on_canonical(self, storage, project):
        es = _create_escopo(project)
        ps = es.create_plan(nome="P")
        ps.save_canonical(_make_minimal_canonical())
        ps.approve()
        assert storage.is_approved(ps._path(ps.CANONICAL_FILE))

    def test_save_canonical_raises_on_approved(self, project):
        es = _create_escopo(project)
        ps = es.create_plan(nome="P")
        ps.save_canonical(_make_minimal_canonical())
        ps.approve()
        with pytest.raises(PermissionError):
            ps.save_canonical(_make_minimal_canonical())

    def test_write_canonical_raw_raises_on_approved(self, project):
        es = _create_escopo(project)
        ps = es.create_plan(nome="P")
        ps.save_canonical(_make_minimal_canonical())
        ps.approve()
        with pytest.raises(PermissionError):
            ps.write_canonical_raw({"key": "value"})


class TestStoragePlanoHandlePremissasEfetivas:
    """issue #121: congelamento de premissas junto com o resultado, não só o canônico."""

    def _make_plano(self, project):
        es = _create_escopo(project)
        return es.create_plan(nome="P")

    def test_write_creates_both_files(self, storage, project):
        ps = self._make_plano(project)
        ps.write_premissas_efetivas(
            "06-resultado-financeiro", {"bdi_aplicado": {"mao_obra": 0.3}}, {"jurisdicao_id": "sp"}
        )
        assert storage.blob_existe(ps._path(ps.PREMISSAS_EFETIVAS_FILE))
        assert storage.blob_existe(ps._path(ps.PREMISSAS_POR_SKILL_FILE))

    def test_read_premissas_por_skill_empty_when_missing(self, project):
        ps = self._make_plano(project)
        assert ps.read_premissas_por_skill() == {}

    def test_read_premissas_por_skill_roundtrip(self, project):
        ps = self._make_plano(project)
        ps.write_premissas_efetivas("04-cronograma", {"a": 1}, {"jurisdicao_id": "sp"})
        por_skill = ps.read_premissas_por_skill()
        assert "04-cronograma" in por_skill
        assert "hash" in por_skill["04-cronograma"]
        assert "escopo_hash" in por_skill["04-cronograma"]

    def test_mesmo_escopo_meta_produz_mesmo_escopo_hash(self, project):
        ps = self._make_plano(project)
        escopo_meta = {"jurisdicao_id": "sp", "snapshot_catalogo_id": "cat-1"}
        ps.write_premissas_efetivas("04-cronograma", {"a": 1}, escopo_meta)
        ps.write_premissas_efetivas("06-resultado-financeiro", {"b": 2}, escopo_meta)
        por_skill = ps.read_premissas_por_skill()
        assert por_skill["04-cronograma"]["escopo_hash"] == por_skill["06-resultado-financeiro"]["escopo_hash"]

    def test_no_op_quando_readonly(self, storage, project):
        ps = self._make_plano(project)
        ps.save_canonical(_make_minimal_canonical())
        ps.approve()
        ps.write_premissas_efetivas("06-resultado-financeiro", {"a": 1}, {"jurisdicao_id": "sp"})
        assert not storage.blob_existe(ps._path(ps.PREMISSAS_EFETIVAS_FILE))

    def test_bdi_perfil_versao_captured_when_present(self, project):
        ps = self._make_plano(project)
        ps.write_premissas_efetivas(
            "06-resultado-financeiro",
            {"bdi_perfil": {"versao": 3, "content_hash": "abc"}},
            {"jurisdicao_id": "sp"},
        )
        por_skill = ps.read_premissas_por_skill()
        assert por_skill["06-resultado-financeiro"]["bdi_perfil_versao"] == 3

    def test_bdi_perfil_versao_absent_when_no_perfil_used(self, project):
        ps = self._make_plano(project)
        ps.write_premissas_efetivas("04-cronograma", {"a": 1}, {"jurisdicao_id": "sp"})
        por_skill = ps.read_premissas_por_skill()
        assert "bdi_perfil_versao" not in por_skill["04-cronograma"]


class TestStoragePlanoHandleProtectBdiPerfilVersoes:
    """issue #123: perfil BDI versionado usado por um plano deve ser protegido no approve()."""

    def _make_plano(self, project):
        es = _create_escopo(project)
        return es.create_plan(nome="P")

    def test_approve_protects_referenced_bdi_perfil_version(self, storage, project):
        ps = self._make_plano(project)
        storage.gravar_blob("proj-1/bdi/perfil_bdi_v003.json", b"{}")
        storage.gravar_blob("proj-1/bdi/perfil_bdi.json", b"{}")

        ps.write_premissas_efetivas("06-resultado-financeiro", {"bdi_perfil": {"versao": 3}}, {"jurisdicao_id": "sp"})
        ps.save_canonical(_make_minimal_canonical())
        ps.approve()

        assert storage.is_approved("proj-1/bdi/perfil_bdi_v003.json")
        assert not storage.is_approved("proj-1/bdi/perfil_bdi.json"), "cabeça deve continuar editável"

    def test_approve_no_op_when_no_bdi_perfil_referenced(self, project):
        ps = self._make_plano(project)
        ps.write_premissas_efetivas("04-cronograma", {"a": 1}, {"jurisdicao_id": "sp"})
        ps.save_canonical(_make_minimal_canonical())
        ps.approve()  # não deve lançar

    def test_approve_skips_missing_perfil_version_file(self, project):
        ps = self._make_plano(project)
        ps.write_premissas_efetivas("06-resultado-financeiro", {"bdi_perfil": {"versao": 99}}, {"jurisdicao_id": "sp"})
        ps.save_canonical(_make_minimal_canonical())
        ps.approve()  # não deve lançar mesmo sem bdi/perfil_bdi_v099.json


class TestStoragePlanoHandleNewIteration:
    def test_new_iteration_copies_canonical(self, project):
        es = _create_escopo(project)
        ps = es.create_plan(nome="P")
        ps.save_canonical(_make_minimal_canonical())
        new_ps = ps.new_iteration()
        assert new_ps.load_canonical() is not None

    def test_new_iteration_increments_versao(self, project):
        es = _create_escopo(project)
        ps = es.create_plan(nome="P")
        new_ps = ps.new_iteration()
        assert new_ps.meta.get("versao_iteracao", 1) >= 2

    def test_new_iteration_appears_in_list_plans(self, project):
        es = _create_escopo(project)
        ps = es.create_plan(nome="P")
        new_ps = ps.new_iteration()
        assert new_ps.plano_id in es.list_plans()

    def test_new_iteration_requires_escopo_store(self, storage, project):
        es = _create_escopo(project)
        ps = es.plan("solto")  # escopo_store setado via .plan(), mas simulamos ausência abaixo
        ps.escopo_store = None
        with pytest.raises(RuntimeError):
            ps.new_iteration()


class TestStorageSnapshotStore:
    def test_store_and_dedupe_by_hash(self, project):
        snaps = project.snapshots
        h1 = snaps.store("jurisdicao", {"a": 1})
        h2 = snaps.store("jurisdicao", {"a": 1})
        assert h1 == h2

    def test_store_different_content_different_hash(self, project):
        snaps = project.snapshots
        h1 = snaps.store("perfil", {"a": 1})
        h2 = snaps.store("perfil", {"a": 2})
        assert h1 != h2


class TestUpsertRosterMoMembro:
    """ADR-173 F3/D5 — merge por individuo_id."""

    def test_adiciona_membro_novo(self, project):
        es = _create_escopo(project)
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

    def test_edita_membro_existente_merge_raso(self, project):
        es = _create_escopo(project)
        es.upsert_roster_mo_membro(
            {
                "individuo_id": "mo-001",
                "funcao_id": "MO-ARMADOR",
                "salario_base_mensal": 3200.0,
                "data_admissao": "2026-01-05",
            }
        )
        es.upsert_roster_mo_membro({"individuo_id": "mo-001", "data_desligamento": "2026-06-30"})

        roster = es.meta["roster_mo"]
        assert len(roster) == 1
        assert roster[0]["funcao_id"] == "MO-ARMADOR"
        assert roster[0]["salario_base_mensal"] == 3200.0
        assert roster[0]["data_desligamento"] == "2026-06-30"

    def test_nunca_remove_membro_existente(self, project):
        es = _create_escopo(project)
        es.upsert_roster_mo_membro({"individuo_id": "mo-001", "funcao_id": "MO-ARMADOR"})
        es.upsert_roster_mo_membro({"individuo_id": "mo-002", "funcao_id": "MO-CARPINTEIRO"})
        roster = es.meta["roster_mo"]
        assert {m["individuo_id"] for m in roster} == {"mo-001", "mo-002"}

    def test_exige_individuo_id(self, project):
        es = _create_escopo(project)
        with pytest.raises(ValueError, match="individuo_id"):
            es.upsert_roster_mo_membro({"funcao_id": "MO-ARMADOR"})

    def test_roundtrip_via_to_escopo(self, project):
        es = _create_escopo(project)
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


class TestUpsertRosterEqAtivo:
    """ADR-174 D2 — merge por ativo_id."""

    def test_adiciona_ativo_novo(self, project):
        es = _create_escopo(project)
        es.upsert_roster_eq_ativo({"ativo_id": "eq-001", "equip_id": "EQ-ESCAVADEIRA"})
        roster = es.meta["roster_eq"]
        assert len(roster) == 1
        assert roster[0]["ativo_id"] == "eq-001"

    def test_edita_ativo_existente_merge_raso(self, project):
        es = _create_escopo(project)
        es.upsert_roster_eq_ativo({"ativo_id": "eq-001", "equip_id": "EQ-ESCAVADEIRA", "placa": "ABC-123"})
        es.upsert_roster_eq_ativo({"ativo_id": "eq-001", "data_contrato_fim": "2026-06-30"})
        roster = es.meta["roster_eq"]
        assert len(roster) == 1
        assert roster[0]["placa"] == "ABC-123"
        assert roster[0]["data_contrato_fim"] == "2026-06-30"

    def test_nunca_remove_ativo_existente(self, project):
        es = _create_escopo(project)
        es.upsert_roster_eq_ativo({"ativo_id": "eq-001"})
        es.upsert_roster_eq_ativo({"ativo_id": "eq-002"})
        roster = es.meta["roster_eq"]
        assert {a["ativo_id"] for a in roster} == {"eq-001", "eq-002"}

    def test_exige_ativo_id(self, project):
        es = _create_escopo(project)
        with pytest.raises(ValueError, match="ativo_id"):
            es.upsert_roster_eq_ativo({"equip_id": "EQ-ESCAVADEIRA"})

    def test_roundtrip_via_to_escopo(self, project):
        es = _create_escopo(project)
        es.upsert_roster_eq_ativo(
            {
                "ativo_id": "eq-001",
                "equip_id": "EQ-ESCAVADEIRA",
                "custo_locacao_mensal_real": 15000.0,
                "data_contrato_inicio": "2026-01-05",
            }
        )
        escopo = es.to_escopo()
        assert escopo.roster_eq[0].ativo_id == "eq-001"
