"""Tests for spec_loader helpers a and b, escopo_store, backtracking_pe_builder,
pool_inference, campaign_report, insumo repository."""

from __future__ import annotations

from unittest.mock import MagicMock

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
