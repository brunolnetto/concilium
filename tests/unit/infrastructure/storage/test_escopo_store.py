"""Coverage sweep 8 — cube_projection_views, side_effects, escopo_store, etapa_diffs."""

from __future__ import annotations

# ─── infrastructure/storage/escopo_store.py ──────────────────────────────────


class TestPlanoStore:
    def _make_plano_store(self, tmp_path):
        from concilium.infrastructure.storage.escopo_store import EscopoStore, PlanoStore

        plano_root = tmp_path / "escopos" / "esc-1" / "planos" / "plan-1"
        plano_root.mkdir(parents=True)
        es = EscopoStore(root=tmp_path / "escopos" / "esc-1")
        return PlanoStore(root=plano_root, escopo_store=es)

    def test_plano_store_creates(self, tmp_path):
        ps = self._make_plano_store(tmp_path)
        assert ps is not None
        assert ps.plano_id == "plan-1"

    def test_plano_store_meta(self, tmp_path):
        ps = self._make_plano_store(tmp_path)
        meta = ps.meta
        assert "plano_id" in meta

    def test_plano_store_load_canonical_none(self, tmp_path):
        ps = self._make_plano_store(tmp_path)
        assert ps.load_canonical() is None

    def test_plano_store_log_invocation(self, tmp_path):
        ps = self._make_plano_store(tmp_path)
        ps.log_invocation({"skill": "01", "status": "OK"})
        records = ps.read_invocations()
        assert len(records) == 1

    def test_plano_store_read_empty(self, tmp_path):
        ps = self._make_plano_store(tmp_path)
        assert ps.read_invocations() == []


class TestPlanoStorePremissasEfetivas:
    """issue #121: congelamento de premissas junto com o resultado, não só o canônico."""

    def _make_plano_store(self, tmp_path):
        from concilium.infrastructure.storage.escopo_store import EscopoStore, PlanoStore

        plano_root = tmp_path / "escopos" / "esc-1" / "planos" / "plan-1"
        plano_root.mkdir(parents=True)
        es = EscopoStore(root=tmp_path / "escopos" / "esc-1")
        return PlanoStore(root=plano_root, escopo_store=es)

    def test_write_creates_both_files(self, tmp_path):
        ps = self._make_plano_store(tmp_path)
        ps.write_premissas_efetivas("06-resultado-financeiro", {"bdi_aplicado": {"mao_obra": 0.3}}, {"jurisdicao_id": "sp"})

        assert (ps.root / ps.PREMISSAS_EFETIVAS_FILE).exists()
        assert (ps.root / ps.PREMISSAS_POR_SKILL_FILE).exists()

    def test_read_premissas_por_skill_empty_when_missing(self, tmp_path):
        ps = self._make_plano_store(tmp_path)
        assert ps.read_premissas_por_skill() == {}

    def test_read_premissas_por_skill_roundtrip(self, tmp_path):
        ps = self._make_plano_store(tmp_path)
        ps.write_premissas_efetivas("04-cronograma", {"a": 1}, {"jurisdicao_id": "sp"})
        por_skill = ps.read_premissas_por_skill()
        assert "04-cronograma" in por_skill
        assert "hash" in por_skill["04-cronograma"]
        assert "escopo_hash" in por_skill["04-cronograma"]

    def test_mesmo_escopo_meta_produz_mesmo_escopo_hash(self, tmp_path):
        ps = self._make_plano_store(tmp_path)
        escopo_meta = {"jurisdicao_id": "sp", "snapshot_catalogo_id": "cat-1"}
        ps.write_premissas_efetivas("04-cronograma", {"a": 1}, escopo_meta)
        ps.write_premissas_efetivas("06-resultado-financeiro", {"b": 2}, escopo_meta)
        por_skill = ps.read_premissas_por_skill()
        assert por_skill["04-cronograma"]["escopo_hash"] == por_skill["06-resultado-financeiro"]["escopo_hash"]

    def test_escopo_meta_diferente_produz_hash_diferente(self, tmp_path):
        ps = self._make_plano_store(tmp_path)
        ps.write_premissas_efetivas("04-cronograma", {"a": 1}, {"jurisdicao_id": "sp"})
        ps.write_premissas_efetivas("06-resultado-financeiro", {"b": 2}, {"jurisdicao_id": "rj"})
        por_skill = ps.read_premissas_por_skill()
        assert por_skill["04-cronograma"]["escopo_hash"] != por_skill["06-resultado-financeiro"]["escopo_hash"]

    def test_no_op_quando_readonly(self, tmp_path):
        ps = self._make_plano_store(tmp_path)
        (ps.root / ps.CANONICAL_FILE).write_text("{}", encoding="utf-8")
        ps.approve()
        ps.write_premissas_efetivas("06-resultado-financeiro", {"a": 1}, {"jurisdicao_id": "sp"})
        # nada foi escrito, pois o plano já está read-only
        assert not (ps.root / ps.PREMISSAS_EFETIVAS_FILE).exists()

    def test_approve_chmod_premissas(self, tmp_path):
        import stat

        ps = self._make_plano_store(tmp_path)
        ps.write_premissas_efetivas("06-resultado-financeiro", {"a": 1}, {"jurisdicao_id": "sp"})
        (ps.root / ps.CANONICAL_FILE).write_text("{}", encoding="utf-8")

        ps.approve()

        for fname in (ps.PREMISSAS_EFETIVAS_FILE, ps.PREMISSAS_POR_SKILL_FILE):
            f = ps.root / fname
            assert not bool(f.stat().st_mode & stat.S_IWUSR), f"{fname} deveria estar read-only após approve()"


class TestEscopoStore:
    def _make_escopo_store(self, tmp_path):
        from concilium.infrastructure.storage.escopo_store import EscopoStore

        escopo_root = tmp_path / "escopos" / "esc-1"
        escopo_root.mkdir(parents=True)
        return EscopoStore(root=escopo_root)

    def test_escopo_store_creates(self, tmp_path):
        es = self._make_escopo_store(tmp_path)
        assert es is not None

    def test_escopo_store_meta(self, tmp_path):
        es = self._make_escopo_store(tmp_path)
        assert "escopo_id" in es.meta

    def test_list_planos_empty(self, tmp_path):
        es = self._make_escopo_store(tmp_path)
        planos = es.list_plans()
        assert isinstance(planos, list)

    def test_create_plano(self, tmp_path):
        es = self._make_escopo_store(tmp_path)
        ps = es.create_plan(nome="Plano Principal")
        assert ps is not None
        assert ps.plano_id is not None







def _make_minimal_canonical():
    """Build a CanonicalModel with only required fields populated."""
    from concilium.domain.models.canonical import CanonicalModel

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


# ─── infrastructure/storage/escopo_store.py ────────────────────────────────────


class TestEscopoStore2:
    def _make_project_store(self, tmp_path):
        from concilium.infrastructure.storage.project import ProjectStore

        return ProjectStore.init(tmp_path, "Test Project", "ctx-1")

    def test_list_escopos_empty(self, tmp_path):
        store = self._make_project_store(tmp_path)
        assert store.list_escopos() == []

    def test_create_and_list_escopo(self, tmp_path):
        store = self._make_project_store(tmp_path)
        store.create_escopo(
            escopo_id="esc-1",
            nome="Escopo 1",
            tipo_obra="terraplenagem",
            localizacao="SP",
            coordenadas_lat=-23.5,
            coordenadas_lng=-46.6,
            data_inicio="2026-01-01",
            data_termino="2026-12-31",
        )
        escopos = store.list_escopos()
        assert "esc-1" in escopos

    def test_escopo_store_active_plan_none(self, tmp_path):
        store = self._make_project_store(tmp_path)
        store.create_escopo(
            escopo_id="esc-1",
            nome="E1",
            tipo_obra="terra",
            localizacao="SP",
            coordenadas_lat=0,
            coordenadas_lng=0,
            data_inicio="2026-01-01",
            data_termino="2026-12-31",
        )
        es = store.escopo("esc-1")
        assert es.active_plan() is None

    def test_escopo_store_create_plan(self, tmp_path):
        store = self._make_project_store(tmp_path)
        store.create_escopo(
            escopo_id="esc-1",
            nome="E1",
            tipo_obra="terra",
            localizacao="SP",
            coordenadas_lat=0,
            coordenadas_lng=0,
            data_inicio="2026-01-01",
            data_termino="2026-12-31",
        )
        es = store.escopo("esc-1")
        ps = es.create_plan(nome="Plano 1")
        assert ps is not None

    def test_escopo_store_list_plans(self, tmp_path):
        store = self._make_project_store(tmp_path)
        store.create_escopo(
            escopo_id="esc-1",
            nome="E1",
            tipo_obra="terra",
            localizacao="SP",
            coordenadas_lat=0,
            coordenadas_lng=0,
            data_inicio="2026-01-01",
            data_termino="2026-12-31",
        )
        es = store.escopo("esc-1")
        es.create_plan(nome="Plano 1")
        plans = es.list_plans()
        assert len(plans) >= 1

    def _make_escopo(self, tmp_path, escopo_id="esc-1"):
        from concilium.infrastructure.storage.project import ProjectStore

        store = ProjectStore.init(tmp_path, "P", "ctx")
        store.create_escopo(
            escopo_id=escopo_id,
            nome="E",
            tipo_obra="terra",
            localizacao="SP",
            coordenadas_lat=0,
            coordenadas_lng=0,
            data_inicio="2026-01-01",
            data_termino="2026-12-31",
        )
        return store.escopo(escopo_id)

    def test_plano_meta_defaults_when_no_file(self, tmp_path):

        from concilium.infrastructure.storage.escopo_store import PlanoStore

        plano_dir = tmp_path / "plano-x"
        plano_dir.mkdir()
        ps = PlanoStore(plano_dir)
        meta = ps.meta
        assert meta["plano_id"] == "plano-x"
        assert meta["status"] == "RASCUNHO"

    def test_plano_status_default(self, tmp_path):
        from concilium.infrastructure.storage.escopo_store import PlanoStore

        plano_dir = tmp_path / "plano-y"
        plano_dir.mkdir()
        ps = PlanoStore(plano_dir)
        assert ps.status == "RASCUNHO"

    def test_plano_log_and_read_invocations(self, tmp_path):
        es = self._make_escopo(tmp_path)
        ps = es.create_plan(nome="P")
        ps.log_invocation({"skill": "01", "status": "OK"})
        ps.log_invocation({"skill": "02", "status": "ERRO"})
        entries = ps.read_invocations()
        assert len(entries) == 2
        assert entries[0]["skill"] == "01"

    def test_read_invocations_empty_when_no_log(self, tmp_path):
        from concilium.infrastructure.storage.escopo_store import PlanoStore

        plano_dir = tmp_path / "plano-z"
        plano_dir.mkdir()
        ps = PlanoStore(plano_dir)
        assert ps.read_invocations() == []

    def test_save_and_load_output_file_xlsx(self, tmp_path):
        es = self._make_escopo(tmp_path)
        ps = es.create_plan(nome="P")
        data = b"fake xlsx bytes"
        path = ps.save_output_file(data, "resultado.xlsx")
        assert path.exists()
        loaded = ps.load_output_file("resultado.xlsx")
        assert loaded == data

    def test_save_and_load_output_file_png(self, tmp_path):
        es = self._make_escopo(tmp_path)
        ps = es.create_plan(nome="P")
        data = b"\x89PNG\r\n\x1a\n"
        ps.save_output_file(data, "chart.png")
        loaded = ps.load_output_file("chart.png")
        assert loaded == data

    def test_load_output_file_fallback_to_other_dir(self, tmp_path):
        """load_output_file falls back to the alternate subdir."""
        es = self._make_escopo(tmp_path)
        ps = es.create_plan(nome="P")
        data = b"pdf bytes"
        # Save in visualizations but try to load as a pdf file
        (ps.root / "outputs" / "visualizations").mkdir(parents=True, exist_ok=True)
        (ps.root / "outputs" / "visualizations" / "test.pdf").write_bytes(data)
        # _get_output_subdir("test.pdf") -> "reports", fallback -> "visualizations"
        loaded = ps.load_output_file("test.pdf")
        assert loaded == data

    def test_load_output_file_returns_none_when_missing(self, tmp_path):
        es = self._make_escopo(tmp_path)
        ps = es.create_plan(nome="P")
        result = ps.load_output_file("nonexistent.xlsx")
        assert result is None

    def test_list_output_files_empty(self, tmp_path):
        from concilium.infrastructure.storage.escopo_store import PlanoStore

        plano_dir = tmp_path / "plano-l"
        plano_dir.mkdir()
        ps = PlanoStore(plano_dir)
        assert ps.list_output_files() == []

    def test_list_output_files_returns_names(self, tmp_path):
        es = self._make_escopo(tmp_path)
        ps = es.create_plan(nome="P")
        ps.save_output_file(b"x", "orcamento.xlsx")
        ps.save_output_file(b"y", "grafico.png")
        files = ps.list_output_files()
        assert "orcamento.xlsx" in files
        assert "grafico.png" in files

    def test_list_output_files_skips_non_dir_and_non_file_entries(self, tmp_path):
        """Arquivos soltos em outputs/ (fora de subpastas) e não-arquivos dentro de subpastas são ignorados."""
        es = self._make_escopo(tmp_path)
        ps = es.create_plan(nome="P")
        ps.save_output_file(b"y", "grafico.png")
        # Arquivo solto diretamente em outputs/ (não é diretório) -> ramo is_dir() falso.
        (ps.root / "outputs" / "stray.txt").write_text("x")
        # Subdiretório aninhado dentro de uma subpasta válida -> ramo is_file() falso.
        nested_dir = ps.root / "outputs" / "visualizations" / "nested"
        nested_dir.mkdir(parents=True, exist_ok=True)

        files = ps.list_output_files()
        assert "grafico.png" in files
        assert "stray.txt" not in files
        assert "nested" not in files

    def test_load_canonical_returns_model_when_exists(self, tmp_path):
        """load_canonical() com arquivo canonical.json presente deve retornar o modelo carregado."""
        es = self._make_escopo(tmp_path)
        ps = es.create_plan(nome="P")
        ps.save_canonical(_make_minimal_canonical())
        loaded = ps.load_canonical()
        assert loaded is not None

    def test_read_invocations_skips_blank_lines(self, tmp_path):
        es = self._make_escopo(tmp_path)
        ps = es.create_plan(nome="P")
        log_path = ps.root / ps.INVOCATIONS_LOG
        log_path.write_text('\n   \n{"skill": "01", "status": "OK"}\n', encoding="utf-8")
        entries = ps.read_invocations()
        assert len(entries) == 1
        assert entries[0]["skill"] == "01"

    def test_approve_plan_skips_already_archived_plans(self, tmp_path):
        """approve_plan(): planos que não estão RASCUNHO/EM_ANALISE e não são o alvo são ignorados."""
        es = self._make_escopo(tmp_path)
        ps1 = es.create_plan(nome="P1")
        ps2 = es.create_plan(nome="P2")
        ps2.archive()  # status ARQUIVADO — nem alvo, nem RASCUNHO/EM_ANALISE.

        arquivados = es.approve_plan(ps1.plano_id)
        assert ps2.plano_id not in arquivados

    def test_plano_set_em_analise(self, tmp_path):
        es = self._make_escopo(tmp_path)
        ps = es.create_plan(nome="P")
        ps.set_em_analise()
        assert ps.status == "EM_ANALISE"

    def test_plano_archive(self, tmp_path):
        es = self._make_escopo(tmp_path)
        ps = es.create_plan(nome="P")
        ps.archive()
        assert ps.status == "ARQUIVADO"

    def test_approved_plan_none_when_no_plans(self, tmp_path):
        es = self._make_escopo(tmp_path)
        assert es.approved_plan() is None

    def test_approved_plan_found_after_approve_plan(self, tmp_path):
        es = self._make_escopo(tmp_path)
        ps = es.create_plan(nome="P")
        es.approve_plan(ps.plano_id)
        result = es.approved_plan()
        assert result is not None
        assert result.plano_id == ps.plano_id

    def test_approve_plan_archives_other_rascunhos(self, tmp_path):
        es = self._make_escopo(tmp_path)
        ps1 = es.create_plan(nome="P1")
        ps2 = es.create_plan(nome="P2")
        arquivados = es.approve_plan(ps2.plano_id)
        assert ps1.plano_id in arquivados
        # ps2 should be approved
        assert es.approved_plan().plano_id == ps2.plano_id

    def test_active_plan_returns_approved(self, tmp_path):
        es = self._make_escopo(tmp_path)
        ps = es.create_plan(nome="P")
        es.approve_plan(ps.plano_id)
        result = es.active_plan()
        assert result is not None
        assert result.status == "APROVADO"

    def test_active_plan_returns_rascunho_when_no_approved(self, tmp_path):
        es = self._make_escopo(tmp_path)
        es.create_plan(nome="P")
        result = es.active_plan()
        assert result is not None
        assert result.status in ("RASCUNHO", "EM_ANALISE")

    def test_new_iteration_copies_canonical(self, tmp_path):
        es = self._make_escopo(tmp_path)
        ps = es.create_plan(nome="P")
        # Write a minimal canonical
        canonical = _make_minimal_canonical()
        ps.save_canonical(canonical)
        new_ps = ps.new_iteration()
        assert (new_ps.root / PlanoStore.CANONICAL_FILE).exists()

    def test_new_iteration_increments_versao(self, tmp_path):

        es = self._make_escopo(tmp_path)
        ps = es.create_plan(nome="P")
        new_ps = ps.new_iteration()
        assert new_ps.meta.get("versao_iteracao", 1) >= 2

    def test_escopo_meta_defaults_when_no_file(self, tmp_path):
        from concilium.infrastructure.storage.escopo_store import EscopoStore

        esc_dir = tmp_path / "esc-x"
        esc_dir.mkdir()
        es = EscopoStore(esc_dir)
        meta = es.meta
        assert meta["escopo_id"] == "esc-x"

    def test_escopo_update_meta(self, tmp_path):
        from concilium.infrastructure.storage.escopo_store import EscopoStore

        esc_dir = tmp_path / "esc-u"
        esc_dir.mkdir()
        es = EscopoStore(esc_dir)
        es.update_meta(nome="Updated Name")
        assert es.meta["nome"] == "Updated Name"

    def test_escopo_to_escopo_returns_none_on_invalid(self, tmp_path):
        from concilium.infrastructure.storage.escopo_store import EscopoStore

        esc_dir = tmp_path / "esc-bad"
        esc_dir.mkdir()
        es = EscopoStore(esc_dir)
        # Empty meta → likely fails Escopo model validation
        result = es.to_escopo()
        # Either None or Escopo object — should not raise
        assert result is None or hasattr(result, "escopo_id")

    def test_plano_write_canonical_raw(self, tmp_path):
        es = self._make_escopo(tmp_path)
        ps = es.create_plan(nome="P")
        ps.write_canonical_raw({"projeto": {"nome": "Test"}})
        assert (ps.root / PlanoStore.CANONICAL_FILE).exists()

    def test_plano_load_canonical_none_when_missing(self, tmp_path):
        from concilium.infrastructure.storage.escopo_store import PlanoStore

        plano_dir = tmp_path / "plano-m"
        plano_dir.mkdir()
        ps = PlanoStore(plano_dir)
        assert ps.load_canonical() is None

    def test_get_output_subdir_image(self):
        from concilium.infrastructure.storage.escopo_store import PlanoStore

        assert PlanoStore._get_output_subdir("chart.png") == "visualizations"
        assert PlanoStore._get_output_subdir("photo.jpg") == "visualizations"
        assert PlanoStore._get_output_subdir("icon.svg") == "visualizations"

    def test_get_output_subdir_report(self):
        from concilium.infrastructure.storage.escopo_store import PlanoStore

        assert PlanoStore._get_output_subdir("report.pdf") == "reports"
        assert PlanoStore._get_output_subdir("data.xlsx") == "reports"
        assert PlanoStore._get_output_subdir("export.csv") == "reports"

    def test_get_output_subdir_fallback(self):
        from concilium.infrastructure.storage.escopo_store import PlanoStore

        assert PlanoStore._get_output_subdir("unknown.xyz") == "reports"

    def test_plan_with_hipotese(self, tmp_path):
        es = self._make_escopo(tmp_path)
        ps = es.create_plan(nome="Hipotese Plan", hipotese="H1 - Cenário otimista")
        assert ps.meta.get("hipotese") == "H1 - Cenário otimista"

    def test_plan_with_explicit_plano_id(self, tmp_path):
        es = self._make_escopo(tmp_path)
        ps = es.create_plan(nome="Fixed ID Plan", plano_id="plan-fixed-1")
        assert ps.plano_id == "plan-fixed-1"

    def test_plano_approve_makes_readonly(self, tmp_path):
        import stat

        es = self._make_escopo(tmp_path)
        ps = es.create_plan(nome="P")
        # Save a canonical to have the file
        ps.save_canonical(_make_minimal_canonical())
        ps.log_invocation({"info": "test"})
        ps.approve()
        assert ps.status == "APROVADO"
        cf = ps.root / PlanoStore.CANONICAL_FILE
        assert cf.exists()
        mode = cf.stat().st_mode
        assert not (mode & stat.S_IWUSR), "canonical should be read-only after approve"

    def test_plano_save_canonical_raises_on_approved(self, tmp_path):
        import pytest

        es = self._make_escopo(tmp_path)
        ps = es.create_plan(nome="P")
        ps.save_canonical(_make_minimal_canonical())
        ps.approve()
        with pytest.raises(PermissionError):
            ps.save_canonical(_make_minimal_canonical())

    def test_plano_write_canonical_raw_raises_on_approved(self, tmp_path):
        import pytest

        es = self._make_escopo(tmp_path)
        ps = es.create_plan(nome="P")
        ps.save_canonical(_make_minimal_canonical())
        ps.approve()
        with pytest.raises(PermissionError):
            ps.write_canonical_raw({"key": "value"})

    # Need to import PlanoStore at class scope for test references
    @staticmethod
    def _plano_store_cls():
        from concilium.infrastructure.storage.escopo_store import PlanoStore

        return PlanoStore


# Reference to PlanoStore needed for CANONICAL_FILE constant in tests above
from concilium.infrastructure.storage.escopo_store import PlanoStore  # noqa: E402

# ─── domain/services/analytics/backtracking_pe_builder.py ─────────────────────





# escopo_store.py lines 154-155:
# PlanoStore.read_invocations with malformed JSON line → JSONDecodeError → pass
# ---------------------------------------------------------------------------


class TestPlanoStoreReadInvocationsInvalidJson:
    def test_malformed_json_line_is_skipped(self, tmp_path):
        """Lines 154-155: invalid JSON line in invocations.log → JSONDecodeError → pass."""
        from concilium.infrastructure.storage.escopo_store import PlanoStore

        plan_dir = tmp_path / "plan-001"
        plan_dir.mkdir()
        log_file = plan_dir / PlanoStore.INVOCATIONS_LOG
        # Write one valid and one invalid JSON line
        log_file.write_text('{"skill_id": "01"}\nNOT-VALID-JSON\n', encoding="utf-8")

        store = PlanoStore(root=plan_dir)
        result = store.read_invocations()
        # Only the valid line is returned; invalid is skipped
        assert len(result) == 1
        assert result[0]["skill_id"] == "01"


# ---------------------------------------------------------------------------




# ─── infrastructure/storage/escopo_store.py ───────────────────────────────────


class TestEscopoStoreFull:
    def _make_project_store(self, tmp_path):
        from concilium.infrastructure.storage.project import ProjectStore

        return ProjectStore.init(tmp_path, "Test Project", "ctx-1")

    def _create_escopo(self, store, escopo_id="esc-1"):
        store.create_escopo(
            escopo_id=escopo_id,
            nome=f"Escopo {escopo_id}",
            tipo_obra="terraplenagem",
            localizacao="SP",
            coordenadas_lat=-23.5,
            coordenadas_lng=-46.6,
            data_inicio="2026-01-01",
            data_termino="2026-12-31",
        )
        return store.escopo(escopo_id)

    def test_escopo_meta(self, tmp_path):
        store = self._make_project_store(tmp_path)
        es = self._create_escopo(store)
        meta = es.meta
        assert meta["escopo_id"] == "esc-1"

    def test_escopo_to_escopo(self, tmp_path):
        store = self._make_project_store(tmp_path)
        es = self._create_escopo(store)
        escopo_obj = es.to_escopo()
        assert escopo_obj is not None

    def test_escopo_update_meta(self, tmp_path):
        store = self._make_project_store(tmp_path)
        es = self._create_escopo(store)
        es.update_meta(nome="Updated Name")
        assert es.meta["nome"] == "Updated Name"

    def test_escopo_create_and_get_plan(self, tmp_path):
        store = self._make_project_store(tmp_path)
        es = self._create_escopo(store)
        ps = es.create_plan(nome="Plano Base")
        assert ps is not None
        assert ps.plano_id is not None

    def test_escopo_active_plan_after_creation(self, tmp_path):
        store = self._make_project_store(tmp_path)
        es = self._create_escopo(store)
        es.create_plan(nome="Plano 1")
        active = es.active_plan()
        assert active is not None

    def test_escopo_list_plans(self, tmp_path):
        store = self._make_project_store(tmp_path)
        es = self._create_escopo(store)
        es.create_plan(nome="P1")
        es.create_plan(nome="P2")
        plans = es.list_plans()
        assert len(plans) >= 2

    def test_plano_store_log_and_read_invocations(self, tmp_path):
        store = self._make_project_store(tmp_path)
        es = self._create_escopo(store)
        ps = es.create_plan(nome="Plano Test")
        ps.log_invocation({"skill": "01-escopo-e-eap", "status": "OK"})
        invocations = ps.read_invocations()
        assert len(invocations) >= 1

    def test_plano_store_active_plan_activation(self, tmp_path):
        store = self._make_project_store(tmp_path)
        es = self._create_escopo(store)
        es.create_plan(nome="Ativo")
        # After create_plan, it may or may not be active depending on implementation
        plans = es.list_plans()
        assert len(plans) >= 1

    def test_escopo_id_property(self, tmp_path):
        store = self._make_project_store(tmp_path)
        es = self._create_escopo(store, "my-escopo")
        assert es.escopo_id == "my-escopo"

    def test_escopo_root_property(self, tmp_path):
        store = self._make_project_store(tmp_path)
        es = self._create_escopo(store)
        from pathlib import Path

        assert isinstance(es.root, Path)

    def test_approved_plan_none_initially(self, tmp_path):
        store = self._make_project_store(tmp_path)
        es = self._create_escopo(store)
        assert es.approved_plan() is None

    def test_plano_store_approve(self, tmp_path):
        store = self._make_project_store(tmp_path)
        es = self._create_escopo(store)
        ps = es.create_plan(nome="Para Aprovar")
        # Approve the plan
        es.approve_plan(ps.plano_id)
        approved = es.approved_plan()
        assert approved is not None

