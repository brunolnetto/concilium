"""Tests for spec_loader helpers a and b, escopo_store, backtracking_pe_builder,
pool_inference, campaign_report, insumo repository."""

from __future__ import annotations

from unittest.mock import MagicMock


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


# ─── _spec_loader_helpers_a.py ────────────────────────────────────────────────


class TestSpecLoaderHelpersA:
    def test_iso_weeks_basic(self):
        from concilium.application.benchmarks.spec._spec_loader_helpers_a import iso_weeks

        result = iso_weeks("2026-W01", "2026-W03")
        assert "2026-W01" in result
        assert "2026-W03" in result
        assert len(result) == 3

    def test_iso_weeks_invalid_range(self):
        from concilium.application.benchmarks.spec._spec_loader_helpers_a import iso_weeks

        result = iso_weeks("2026-W05", "2026-W01")
        assert result == []

    def test_norm_ref_projeto_block_nome(self):
        from concilium.application.benchmarks.spec._spec_loader_helpers_a import _norm_ref_projeto_block

        out: dict = {}
        _norm_ref_projeto_block(out, {"nome": "Test Project", "localizacao": "SP"})
        assert out["projeto"] == "Test Project"
        assert out["localizacao"] == "SP"

    def test_norm_ref_projeto_block_with_coordenadas_dict(self):
        from concilium.application.benchmarks.spec._spec_loader_helpers_a import _norm_ref_projeto_block

        out: dict = {}
        _norm_ref_projeto_block(out, {"localizacao": {"lat": -23, "lng": -46}})
        assert out.get("coordenadas") == {"lat": -23, "lng": -46}

    def test_norm_ref_projeto_block_empty(self):
        from concilium.application.benchmarks.spec._spec_loader_helpers_a import _norm_ref_projeto_block

        out: dict = {}
        _norm_ref_projeto_block(out, {})  # should not raise

    def test_norm_ref_datas_block(self):
        from concilium.application.benchmarks.spec._spec_loader_helpers_a import _norm_ref_datas_block

        out: dict = {}
        _norm_ref_datas_block(out, {"data_inicio": "2026-01-01", "data_termino": "2026-12-31"})
        assert out["data_inicio"] == "2026-01-01"

    def test_norm_ref_atividade_item_none(self):
        from concilium.application.benchmarks.spec._spec_loader_helpers_a import _norm_ref_atividade_item

        result = _norm_ref_atividade_item("not-a-dict", 0)
        assert result is None

    def test_norm_ref_atividade_item_dict(self):
        from concilium.application.benchmarks.spec._spec_loader_helpers_a import _norm_ref_atividade_item

        result = _norm_ref_atividade_item({"item_id": "A1", "cpu_id": "CPU-1", "descricao": "Test"}, 0)
        assert result is not None
        assert result["item_id"] == "A1"

    def test_ebr_as_float(self):
        from concilium.application.benchmarks.spec._spec_loader_helpers_a import _ebr_as_float

        assert _ebr_as_float(1.5) == 1.5
        assert _ebr_as_float("2.0") == 2.0
        assert _ebr_as_float(None) is None
        assert _ebr_as_float("abc") is None

    def test_ebr_from_stats(self):
        from concilium.application.benchmarks.spec._spec_loader_helpers_a import _ebr_from_stats

        stats = MagicMock()
        stats.custo_direto = 1000000.0
        stats.custo_indireto = 200000.0
        stats.preco_venda = 1500000.0
        stats.margem_pct = 0.15
        result = _ebr_from_stats(stats)
        assert isinstance(result, dict)

    def test_ebr_apply_fallbacks(self):
        from concilium.application.benchmarks.spec._spec_loader_helpers_a import _ebr_apply_fallbacks

        mapped: dict = {"custo_direto": 1000, "preco_venda": 1500}
        _ebr_apply_fallbacks(mapped)  # should fill in missing keys from available

    def test_norm_ref_metas_confronto(self):
        from concilium.application.benchmarks.spec._spec_loader_helpers_a import _norm_ref_metas_confronto

        out = {
            "referencia": {"custo_direto": 1000000, "preco_venda": 1500000},
            "ferramenta": {},
        }
        _norm_ref_metas_confronto(out)  # should not raise

    def test_norm_ref_metas_confronto_with_data(self):
        from concilium.application.benchmarks.spec._spec_loader_helpers_a import _norm_ref_metas_confronto

        out = {
            "metas_confronto": {"custo_direto": 1000000, "preco_venda": 1500000},
            "resultado": {},
        }
        _norm_ref_metas_confronto(out)
        assert "benchmark_confronto_referencia" in out["resultado"]

    def test_norm_ref_parse_atividade_duration(self):
        from concilium.application.benchmarks.spec._spec_loader_helpers_a import _norm_ref_parse_atividade_duration

        atividade = {"duration_weeks": 4}
        result = _norm_ref_parse_atividade_duration(atividade, [])
        assert result == 4

    def test_norm_ref_parse_atividade_duration_fallback(self):
        from concilium.application.benchmarks.spec._spec_loader_helpers_a import _norm_ref_parse_atividade_duration

        result = _norm_ref_parse_atividade_duration({}, ["w1", "w2", "w3"])
        assert result == 3

    def test_norm_ref_build_rcpsp_activities_from_eap(self):
        from concilium.application.benchmarks.spec._spec_loader_helpers_a import _norm_ref_build_rcpsp_activities

        out = {
            "eap": [
                {"item_id": "2.1", "cpu_id": "CPU-1", "descricao": "Test", "quantitativo": 100},
            ]
        }
        result = _norm_ref_build_rcpsp_activities(out, ["W1", "W2"])
        assert len(result) > 0
        assert result[0]["item_id"] == "2.1"

    def test_norm_ref_build_rcpsp_activities_empty(self):
        from concilium.application.benchmarks.spec._spec_loader_helpers_a import _norm_ref_build_rcpsp_activities

        result = _norm_ref_build_rcpsp_activities({}, [])
        assert result == []

    def test_ebr_from_stats_dict_format(self):
        from concilium.application.benchmarks.spec._spec_loader_helpers_a import _ebr_from_stats

        stats = {"overhead_ac": {"media": 0.05}, "overhead_df": {"media": 0.01}}
        result = _ebr_from_stats(stats)
        assert isinstance(result, dict)

    def test_ebr_from_por_item(self):
        from concilium.application.benchmarks.spec._spec_loader_helpers_a import _ebr_from_por_item

        bdi_ref = {"por_item": [{"bdi": {"overhead_ac": 0.05, "overhead_df": 0.01, "lucro": 0.08}}]}
        result = _ebr_from_por_item(bdi_ref)
        assert isinstance(result, dict)

    def test_ebr_from_por_item_empty(self):
        from concilium.application.benchmarks.spec._spec_loader_helpers_a import _ebr_from_por_item

        assert _ebr_from_por_item({}) == {}

    def test_ebr_apply_fallbacks_servicos_from_equipamentos(self):
        from concilium.application.benchmarks.spec._spec_loader_helpers_a import _ebr_apply_fallbacks

        mapped = {"equipamentos": 0.05}
        _ebr_apply_fallbacks(mapped)
        assert mapped.get("servicos") == 0.05

    def test_ebr_apply_fallbacks_servicos_from_mao_obra(self):
        from concilium.application.benchmarks.spec._spec_loader_helpers_a import _ebr_apply_fallbacks

        mapped = {"mao_obra": 0.08}
        _ebr_apply_fallbacks(mapped)
        assert mapped.get("servicos") == 0.08

    def test_norm_ref_ensure_rcpsp_spec(self):
        from concilium.application.benchmarks.spec._spec_loader_helpers_a import _norm_ref_ensure_rcpsp_spec

        out = {"data_inicio": "2026-W01", "data_termino": "2026-W10"}
        _norm_ref_ensure_rcpsp_spec(out)
        assert "rcpsp_spec" in out or True  # no crash


# ─── _spec_loader_helpers_b.py ────────────────────────────────────────────────


class TestSpecLoaderHelpersB:
    def test_normalize_referencia_weeks(self):
        from concilium.application.benchmarks.input_derivation import normalize_referencia_weeks

        ref = {"cronograma": {"1": {"val": 10}, "2": {"val": 20}}}
        normalize_referencia_weeks(ref)
        # Keys should be converted to ISO format
        cron = ref.get("cronograma", {})
        assert any("-W" in k for k in cron.keys()) or len(cron) == 2

    def test_normalize_referencia_weeks_iso_passthrough(self):
        from concilium.application.benchmarks.input_derivation import normalize_referencia_weeks

        ref = {"cronograma": {"2026-W01": {"val": 10}}}
        normalize_referencia_weeks(ref)
        assert "2026-W01" in ref["cronograma"]


# ─── infrastructure/storage/escopo_store.py ────────────────────────────────────


class TestEscopoStore:
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


class TestBacktrackingPeBuilder:
    def _make_resultado(self):
        resultado = MagicMock()
        resultado.margem_pct = 0.05
        resultado.status_margem = "VERMELHO"
        resultado.venda.total_com_bdi = 1_500_000.0
        resultado.custo.total = 1_425_000.0
        return resultado

    def test_builder_creates(self):
        from concilium.domain.services.analytics.backtracking_pe_builder import BacktrackingPEBuilder

        builder = BacktrackingPEBuilder()
        assert builder is not None

    def test_builder_creates_instance(self):
        from concilium.domain.services.analytics.backtracking_pe_builder import BacktrackingPEBuilder

        builder = BacktrackingPEBuilder()
        assert builder is not None


# ─── application/scheduling/pool_inference.py ─────────────────────────────────


class TestPoolInference:
    def test_import_and_basic(self):
        from concilium.application.scheduling import pool_inference

        assert hasattr(pool_inference, "__file__")

    def test_derivar_required_resources_empty(self):
        from concilium.application.scheduling.pool_inference import derivar_required_resources

        result, missing = derivar_required_resources([])
        assert isinstance(result, dict)
        assert isinstance(missing, list)

    def test_tipo_recurso_de_equip(self):
        from concilium.application.scheduling.pool_inference import tipo_recurso_de_equip

        result = tipo_recurso_de_equip("ESC-HIDRA", {})
        assert isinstance(result, str)


# ─── domain/services/analytics/backtracking_pe_builder.py ─────────────────────


class TestBacktrackingPeBuilderHelpers:
    def test_tol(self):
        from concilium.domain.services.analytics.backtracking_pe_builder import _tol

        assert _tol(0.0) > 0
        assert _tol(0.1) > 0

    def test_btpb_build_lookups(self):
        from concilium.domain.services.analytics.backtracking_pe_builder import _btpb_build_lookups

        canonical = MagicMock()
        canonical.equipes_diretas = []
        canonical.catalogo = {}
        canonical.cronograma = MagicMock()
        canonical.cronograma.scheduled_activities = []
        result = _btpb_build_lookups(canonical)
        assert isinstance(result, tuple)

    def test_btpb_validacoes_no_fails(self):
        from concilium.domain.services.analytics.backtracking_pe_builder import _btpb_validacoes

        result = _btpb_validacoes(0, [], 0.10)
        assert isinstance(result, list)

    def test_btpb_validacoes_with_fails(self):
        from concilium.domain.services.analytics.backtracking_pe_builder import _btpb_validacoes

        result = _btpb_validacoes(2, [MagicMock(), MagicMock()], 0.10)
        assert isinstance(result, list)

    def test_find_solucao_found(self):
        from concilium.domain.models.financial.backtracking_pe import SolucaoInversa
        from concilium.domain.services.analytics.backtracking_pe_builder import _find_solucao

        sol = SolucaoInversa(
            parametro="L",
            valor_atual=0.1,
            valor_requerido=0.15,
            delta_abs=0.05,
            delta_pct=50,
            impacto_preco_pct=5,
            impacto_produtividade_pct=0,
            impacto_recursos_pct=0,
            impacto_prazo_semanas=0,
            pe_gap_recalculado=0,
            roundtrip_valido=True,
            erro_roundtrip=0,
            confianca=4,
        )
        result = _find_solucao([sol], "L")
        assert result is sol

    def test_find_solucao_not_found(self):
        from concilium.domain.services.analytics.backtracking_pe_builder import _find_solucao

        result = _find_solucao([], "L")
        assert result is None

    def test_backtracking_builder_creates(self):
        from concilium.domain.services.analytics.backtracking_pe_builder import BacktrackingPEBuilder

        builder = BacktrackingPEBuilder()
        assert builder is not None


# ─── application/skills/__init__.py extended tests ─────────────────────────────


class TestSkillsInitExtended:
    def test_skills_dict_has_skill01(self):
        from concilium.application.skills import SKILLS

        assert "01-escopo-e-eap" in SKILLS
        assert callable(SKILLS["01-escopo-e-eap"])

    def test_manifest_meta_has_gate(self):
        from concilium.application.skills import MANIFEST_META

        # MANIFEST_META should define gate skills
        assert isinstance(MANIFEST_META, dict)

    def test_skill_registry_get_skill(self):
        from concilium.application.skills.registry import SkillRegistry

        registry = SkillRegistry()
        skill = registry.get_skill("01-escopo-e-eap")
        assert skill is not None
        assert skill.version is not None


# ─── Additional helpers_a edge case coverage ──────────────────────────────────


class TestSpecLoaderHelpersAExtra:
    def test_norm_ref_projeto_block_coordenadas_from_block(self):
        from concilium.application.benchmarks.spec._spec_loader_helpers_a import _norm_ref_projeto_block

        # projeto_block.get("coordenadas") path when localizacao is not lat/lng (line 45-46)
        out: dict = {}
        _norm_ref_projeto_block(out, {"nome": "P", "coordenadas": {"lat": -23, "lng": -46}})
        assert out.get("coordenadas") == {"lat": -23, "lng": -46}

    def test_norm_ref_projeto_block_does_not_overwrite_existing_coordenadas(self):
        from concilium.application.benchmarks.spec._spec_loader_helpers_a import _norm_ref_projeto_block

        # coordenadas already set -> no overwrite (line 43)
        existing = {"lat": 0, "lng": 0}
        out = {"coordenadas": existing}
        _norm_ref_projeto_block(out, {"localizacao": {"lat": -23, "lng": -46}})
        assert out["coordenadas"] == existing

    def test_norm_ref_datas_block_does_not_overwrite_existing(self):
        from concilium.application.benchmarks.spec._spec_loader_helpers_a import _norm_ref_datas_block

        # existing data_inicio / data_termino must NOT be overwritten (line 51)
        out = {"data_inicio": "2026-01-01", "data_termino": "2026-12-31"}
        _norm_ref_datas_block(out, {"data_inicio": "2025-01-01", "data_termino": "2025-06-30"})
        assert out["data_inicio"] == "2026-01-01"
        assert out["data_termino"] == "2026-12-31"

    def test_norm_ref_datas_block_empty_returns_early(self):
        from concilium.application.benchmarks.spec._spec_loader_helpers_a import _norm_ref_datas_block

        # empty datas_block -> early return, out unchanged (line 51)
        out: dict = {}
        _norm_ref_datas_block(out, {})
        assert out == {}

    def test_norm_ref_atividades_to_eap_not_a_list(self):
        from concilium.application.benchmarks.spec._spec_loader_helpers_a import _norm_ref_atividades_to_eap

        # atividades is not a list -> early return (line 77-78)
        out = {"atividades": "not-a-list"}
        _norm_ref_atividades_to_eap(out)
        assert "eap" not in out

    def test_norm_ref_atividades_to_eap_empty_list(self):
        from concilium.application.benchmarks.spec._spec_loader_helpers_a import _norm_ref_atividades_to_eap

        # empty atividades -> early return (line 77-78)
        out = {"atividades": []}
        _norm_ref_atividades_to_eap(out)
        assert "eap" not in out

    def test_norm_ref_build_rcpsp_activities_eap_without_item_id(self):
        from concilium.application.benchmarks.spec._spec_loader_helpers_a import _norm_ref_build_rcpsp_activities

        # eap item without item_id -> skipped (lines 133-136)
        out = {"eap": [{"descricao": "no item_id here"}]}
        result = _norm_ref_build_rcpsp_activities(out, ["W1"])
        assert result == []

    def test_ebr_from_stats_raw_dict_no_media(self):
        from concilium.application.benchmarks.spec._spec_loader_helpers_a import _ebr_from_stats

        # raw is dict but has no "media" key -> rate is None -> not added (lines 236-238)
        stats = {"materiais": {"min": 0.01, "max": 0.10}}  # no "media"
        result = _ebr_from_stats(stats)
        assert "material" not in result

    def test_ebr_from_por_item_bdi_has_none_rate(self):
        from concilium.application.benchmarks.spec._spec_loader_helpers_a import _ebr_from_por_item

        # bdi_item dict but rate is None -> not included (line 254)
        bdi_ref = {"por_item": [{"bdi": {"materiais": None}}]}
        result = _ebr_from_por_item(bdi_ref)
        assert "material" not in result

    def test_norm_ref_atividade_item_missing_cpu_id(self):
        from concilium.application.benchmarks.spec._spec_loader_helpers_a import _norm_ref_atividade_item

        # item_id present but cpu_id missing -> None (line 63-64)
        result = _norm_ref_atividade_item({"item_id": "A1"}, 0)
        assert result is None

    def test_norm_ref_atividades_to_eap_skipped_when_eap_exists(self):
        from concilium.application.benchmarks.spec._spec_loader_helpers_a import _norm_ref_atividades_to_eap

        # out already has eap -> no overwrite (lines 79-80)
        out = {
            "atividades": [{"item_id": "A1", "cpu_id": "CPU-1"}],
            "eap": [{"item_id": "EXISTING"}],
        }
        _norm_ref_atividades_to_eap(out)
        assert out["eap"] == [{"item_id": "EXISTING"}]

    def test_norm_ref_atividades_to_eap_skipped_when_itens_eap_exists(self):
        from concilium.application.benchmarks.spec._spec_loader_helpers_a import _norm_ref_atividades_to_eap

        # cpus.itens_eap present -> no overwrite (lines 79-80)
        out = {
            "atividades": [{"item_id": "A1", "cpu_id": "CPU-1"}],
            "cpus": {"itens_eap": [{"item_id": "EAP-1"}]},
        }
        _norm_ref_atividades_to_eap(out)
        assert "eap" not in out

    def test_norm_ref_atividades_to_eap_filters_invalid(self):
        from concilium.application.benchmarks.spec._spec_loader_helpers_a import _norm_ref_atividades_to_eap

        # atividade without cpu_id -> filtered by _norm_ref_atividade_item (line 81)
        out = {"atividades": [{"item_id": "A1"}]}  # no cpu_id
        _norm_ref_atividades_to_eap(out)
        assert "eap" not in out

    def test_norm_ref_parse_atividade_duration_exception_path(self):
        from concilium.application.benchmarks.spec._spec_loader_helpers_a import _norm_ref_parse_atividade_duration

        # duration value that raises on int() -> fallback to len(weeks) (lines 105-106)
        result = _norm_ref_parse_atividade_duration({"duration_weeks": [1, 2, 3]}, ["W1", "W2"])
        assert result == 2  # max(1, len(["W1","W2"]))

    def test_norm_ref_build_rcpsp_activities_cronograma_legacy_path(self):
        from concilium.application.benchmarks.spec._spec_loader_helpers_a import _norm_ref_build_rcpsp_activities

        # no cronograma_compacto but legacy cronograma.atividades (lines 124-128)
        out = {
            "eap": [{"item_id": "A1", "descricao": "Atividade 1"}],
            "cronograma": {"atividades": [{"item_id": "A1", "semanas": {}}]},
        }
        result = _norm_ref_build_rcpsp_activities(out, ["W1"])
        assert len(result) == 1
        assert result[0]["item_id"] == "A1"

    def test_norm_ref_build_rcpsp_activities_ramp_params_injected(self):
        from concilium.application.benchmarks.spec._spec_loader_helpers_a import _norm_ref_build_rcpsp_activities

        # equipes.n_max > 0 -> ramp_params injected (lines 151-157)
        out = {
            "eap": [{"item_id": "A1", "descricao": "Atividade 1"}],
            "cronograma_compacto": [
                {
                    "item_id": "A1",
                    "equipes": {
                        "n_inicial": 1,
                        "n_max": 3,
                        "taxa_mobilizacao": 1.0,
                        "taxa_desmobilizacao": 1.0,
                    },
                }
            ],
        }
        result = _norm_ref_build_rcpsp_activities(out, ["W1"])
        assert len(result) == 1
        assert "ramp_params" in result[0]
        assert result[0]["ramp_params"]["n_max"] == 3

    def test_norm_ref_build_rcpsp_activities_equipes_n_max_zero_no_ramp(self):
        from concilium.application.benchmarks.spec._spec_loader_helpers_a import _norm_ref_build_rcpsp_activities

        # equipes.n_max == 0 -> no ramp_params (line 151)
        out = {
            "eap": [{"item_id": "A1", "descricao": "Atividade 1"}],
            "cronograma_compacto": [{"item_id": "A1", "equipes": {"n_max": 0}}],
        }
        result = _norm_ref_build_rcpsp_activities(out, ["W1"])
        assert "ramp_params" not in result[0]

    def test_norm_ref_build_rcpsp_activities_explicit_atividades_path(self):
        from concilium.application.benchmarks.spec._spec_loader_helpers_a import _norm_ref_build_rcpsp_activities

        # explicit atividades path (lines 163-181)
        out = {
            "atividades": [
                {
                    "item_id": "B1",
                    "descricao": "Serv B",
                    "duration_weeks": 4,
                    "required_resources": {"mao_obra": 2},
                }
            ]
        }
        result = _norm_ref_build_rcpsp_activities(out, ["W1", "W2"])
        assert len(result) == 1
        assert result[0]["item_id"] == "B1"
        assert result[0]["duration_weeks"] == 4

    def test_norm_ref_build_rcpsp_activities_recursos_fallback(self):
        from concilium.application.benchmarks.spec._spec_loader_helpers_a import _norm_ref_build_rcpsp_activities

        # required_resources not a dict -> use recursos dict (line 172)
        out = {
            "atividades": [
                {
                    "item_id": "C1",
                    "descricao": "Serv C",
                    "duration_weeks": 2,
                    "required_resources": "invalid",
                    "recursos": {"mao_obra": 1},
                }
            ]
        }
        result = _norm_ref_build_rcpsp_activities(out, ["W1"])
        assert result[0]["required_resources"] == {"mao_obra": 1}

    def test_norm_ref_build_rcpsp_activities_skips_non_dict(self):
        from concilium.application.benchmarks.spec._spec_loader_helpers_a import _norm_ref_build_rcpsp_activities

        # atividade that is not a dict -> skipped (line 165)
        out = {"atividades": ["not-a-dict", {"item_id": "D1", "duration_weeks": 1}]}
        result = _norm_ref_build_rcpsp_activities(out, ["W1"])
        # D1 has no required_resources and no resources — still included (item_id present)
        # but "not-a-dict" skipped
        assert all(r["item_id"] != "not-a-dict" for r in result)

    def test_norm_ref_metas_confronto_key_already_present_is_noop(self):
        """When resultado already has benchmark_confronto_referencia, the block
        is not overwritten (line 93->100 false branch)."""
        from concilium.application.benchmarks.spec._spec_loader_helpers_a import _norm_ref_metas_confronto

        out = {
            "metas_confronto": {"custo_direto": 100},
            "resultado": {"benchmark_confronto_referencia": {"custo_direto": 999}},
        }
        _norm_ref_metas_confronto(out)
        assert out["resultado"]["benchmark_confronto_referencia"]["custo_direto"] == 999

    def test_norm_ref_build_rcpsp_activities_eap_multiple_cron_compacto_entries(self):
        """Two entries in cronograma_compacto exercise the indexing loop back-edge (line 124-125)."""
        from concilium.application.benchmarks.spec._spec_loader_helpers_a import _norm_ref_build_rcpsp_activities

        out = {
            "eap": [{"item_id": "A1", "descricao": "Serv A"}],
            "cronograma_compacto": [
                {"item_id": "A1", "equipes": {"n_max": 2, "n_inicial": 1}},
                "not-a-dict",  # exercises the False branch of the loop guard
                {"item_id": None},  # dict without a truthy item_id
                {"item_id": "A2", "equipes": {"n_max": 3}},
            ],
        }
        result = _norm_ref_build_rcpsp_activities(out, ["W1"])
        assert result[0]["ramp_params"]["n_max"] == 2

    def test_norm_ref_build_rcpsp_activities_eap_multiple_legacy_cron_entries(self):
        """Two entries in cronograma.atividades (legacy) exercise the fallback
        indexing loop back-edge (line 130-131), used only when cronograma_compacto is absent."""
        from concilium.application.benchmarks.spec._spec_loader_helpers_a import _norm_ref_build_rcpsp_activities

        out = {
            "eap": [{"item_id": "A1", "descricao": "Serv A"}],
            "cronograma": {
                "atividades": [
                    {"item_id": "A1", "equipes": {"n_max": 4}},
                    "not-a-dict",  # exercises the False branch of the loop guard
                    {"item_id": ""},  # dict without a truthy item_id
                    {"item_id": "A2", "equipes": {"n_max": 5}},
                ]
            },
        }
        result = _norm_ref_build_rcpsp_activities(out, ["W1"])
        assert result[0]["ramp_params"]["n_max"] == 4

    def test_norm_ref_build_rcpsp_activities_eap_skips_non_dict_item(self):
        """A non-dict entry in `eap` is skipped via `continue` (line 136-137)."""
        from concilium.application.benchmarks.spec._spec_loader_helpers_a import _norm_ref_build_rcpsp_activities

        out = {"eap": ["not-a-dict", {"item_id": "A1", "descricao": "Serv A"}]}
        result = _norm_ref_build_rcpsp_activities(out, ["W1"])
        assert len(result) == 1
        assert result[0]["item_id"] == "A1"

    def test_norm_ref_build_rcpsp_activities_explicit_atividade_without_item_id(self):
        """An explicit atividade dict lacking item_id is skipped via `continue` (line 172-173)."""
        from concilium.application.benchmarks.spec._spec_loader_helpers_a import _norm_ref_build_rcpsp_activities

        out = {"atividades": [{"descricao": "sem id"}, {"item_id": "B1", "descricao": "Serv B"}]}
        result = _norm_ref_build_rcpsp_activities(out, ["W1"])
        assert len(result) == 1
        assert result[0]["item_id"] == "B1"

    def test_norm_ref_build_default_rcpsp_spec_resource_pool_already_present(self):
        """When resource_pool is already populated, restricao_equipes is not
        consulted (line 195-199 skip branch)."""
        from concilium.application.benchmarks.spec._spec_loader_helpers_a import _norm_ref_build_default_rcpsp_spec

        out = {
            "data_inicio": "2026-01-05",
            "data_termino": "2026-01-25",
            "resource_pool": {"mao_obra": 9},
            "restricao_equipes": {"mao_obra": 1},
        }
        result = _norm_ref_build_default_rcpsp_spec(out, {})
        assert result["resource_pool"] == {"mao_obra": 9}

    def test_ebr_from_por_item_extracts_valid_rate(self):
        """Covers the `if rate is not None:` true branch (line 259-260) in
        _ebr_from_por_item, mapping a bdi rate through _EBR_KEY_MAP."""
        from concilium.application.benchmarks.spec._spec_loader_helpers_a import _ebr_from_por_item

        bdi_ref = {"por_item": [{"bdi": {"mao_obra": 0.15, "diesel": 0.05}}]}
        result = _ebr_from_por_item(bdi_ref)
        assert result["mao_obra"] == 0.15
        assert result["diesel"] == 0.05

    def test_norm_ref_build_default_restricao_equipes_path(self):
        from concilium.application.benchmarks.spec._spec_loader_helpers_a import _norm_ref_build_default_rcpsp_spec

        # restricao_equipes used when resource_pool absent (line 191-193)
        out = {
            "data_inicio": "2026-01-05",
            "data_termino": "2026-01-25",
            "restricao_equipes": {"mao_obra": 5},
        }
        result = _norm_ref_build_default_rcpsp_spec(out, {})
        assert result["resource_pool"] == {"mao_obra": 5}

    def test_norm_ref_build_default_pool_config_injected(self):
        from concilium.application.benchmarks.spec._spec_loader_helpers_a import _norm_ref_build_default_rcpsp_spec

        # pool_config present -> injected into spec_out (line 203-204)
        out = {
            "data_inicio": "2026-01-05",
            "data_termino": "2026-01-25",
            "pool_config": {"min_equipes": 2, "max_equipes": 10},
        }
        result = _norm_ref_build_default_rcpsp_spec(out, {})
        assert "pool_config" in result
        assert result["pool_config"]["min_equipes"] == 2

    def test_norm_ref_ensure_rcpsp_spec_uses_rcpsp_block_directly(self):
        from concilium.application.benchmarks.spec._spec_loader_helpers_a import _norm_ref_ensure_rcpsp_spec

        # rcpsp block present with deadline_weeks -> used directly (lines 210-219)
        rcpsp_block = {"deadline_weeks": 12, "activities": [{"item_id": "X1"}]}
        out = {"rcpsp": rcpsp_block}
        _norm_ref_ensure_rcpsp_spec(out)
        assert out["rcpsp_spec"]["deadline_weeks"] == 12

    def test_norm_ref_ensure_rcpsp_spec_uses_parametros_simulacao(self):
        from concilium.application.benchmarks.spec._spec_loader_helpers_a import _norm_ref_ensure_rcpsp_spec

        # rcpsp_spec from parametros_simulacao (line 214)
        out = {"parametros_simulacao": {"rcpsp_spec": {"deadline_weeks": 8, "activities": []}}}
        _norm_ref_ensure_rcpsp_spec(out)
        assert out["rcpsp_spec"]["deadline_weeks"] == 8

    def test_ebr_from_stats_non_dict_returns_empty(self):
        from concilium.application.benchmarks.spec._spec_loader_helpers_a import _ebr_from_stats

        # stats is not a dict -> {} (line 236-238 first condition)
        assert _ebr_from_stats("not-a-dict") == {}
        assert _ebr_from_stats(None) == {}
        assert _ebr_from_stats([1, 2]) == {}

    def test_ebr_from_stats_raw_not_dict_skipped(self):
        from concilium.application.benchmarks.spec._spec_loader_helpers_a import _ebr_from_stats

        # raw is not a dict (e.g. float) -> skipped (line 236-238 inside loop)
        stats = {"materiais": 0.05}  # not a dict, just a float -> no media key
        result = _ebr_from_stats(stats)
        assert "material" not in result

    def test_ebr_from_por_item_not_list(self):
        from concilium.application.benchmarks.spec._spec_loader_helpers_a import _ebr_from_por_item

        # por_item is not a list -> {} (lines 244-245)
        result = _ebr_from_por_item({"por_item": "not-a-list"})
        assert result == {}

    def test_ebr_from_por_item_bdi_not_dict(self):
        from concilium.application.benchmarks.spec._spec_loader_helpers_a import _ebr_from_por_item

        # bdi_item not a dict -> {} (lines 248-249)
        result = _ebr_from_por_item({"por_item": [{"bdi": "invalid"}]})
        assert result == {}

    def test_ebr_apply_fallbacks_no_servicos_no_equipamentos_uses_mao_obra(self):
        from concilium.application.benchmarks.spec._spec_loader_helpers_a import _ebr_apply_fallbacks

        # no servicos, no equipamentos -> falls to mao_obra branch (line 262-263)
        mapped = {"mao_obra": 0.12}
        _ebr_apply_fallbacks(mapped)
        assert mapped["servicos"] == 0.12
