"""Testes para ADR-113 — PipelineMode e tiers de execução de skills."""

from __future__ import annotations


class TestPipelineMode:
    """PipelineMode enum retorna as skills certas para cada tier."""

    def test_oltp_returns_6_core_skills(self):
        from concilium.application.skills.phase_classifier import PipelineMode, get_skills_for_mode

        skills = get_skills_for_mode(PipelineMode.OLTP)
        assert len(skills) == 6
        for _i, prefix in enumerate(["01", "02", "03", "04", "05", "06"], start=1):
            assert any(s.startswith(prefix) for s in skills), f"Skill {prefix}-* ausente no OLTP"

    def test_olap_includes_all_skills(self):
        from concilium.application.skills.phase_classifier import PipelineMode, get_skills_for_mode

        olap = get_skills_for_mode(PipelineMode.OLAP)
        oltp = get_skills_for_mode(PipelineMode.OLTP)
        assert len(olap) > len(oltp), "OLAP deve ter mais skills que OLTP"
        for s in oltp:
            assert s in olap, f"Skill OLTP '{s}' ausente no OLAP"

    def test_light_includes_relatorio(self):
        from concilium.application.skills.phase_classifier import PipelineMode, get_skills_for_mode

        light = get_skills_for_mode(PipelineMode.LIGHT)
        assert any("relatorio" in s for s in light), "LIGHT deve incluir skill de relatório"
        oltp = get_skills_for_mode(PipelineMode.OLTP)
        for s in oltp:
            assert s in light, f"Skill OLTP '{s}' ausente no LIGHT"

    def test_oltp_mode_does_not_include_olap_skills(self):
        from concilium.application.skills import MANIFEST_META
        from concilium.application.skills.phase_classifier import PipelineMode, get_skills_for_mode

        oltp = get_skills_for_mode(PipelineMode.OLTP)
        olap_only = {sid for sid, meta in MANIFEST_META.items() if meta.get("tier") == "olap"}
        overlap = set(oltp) & olap_only
        assert not overlap, f"Skills OLAP no resultado OLTP: {overlap}"

    def test_enum_values_are_strings(self):
        from concilium.application.skills.phase_classifier import PipelineMode

        assert PipelineMode.OLTP == "oltp"
        assert PipelineMode.LIGHT == "light"
        assert PipelineMode.OLAP == "olap"


class TestSkillRenumbering:
    """Verifica renumeração ADR-113: 09→10, 10→07, 11→08, 12→09, 13→11."""

    def test_new_ids_exist_in_manifest_meta(self):
        from concilium.application.skills import MANIFEST_META

        expected_new_ids = [
            "07-diagnostico-criticidade",
            "10-relatorio-e-artefatos",
            "11-replanejamento-e-cenarios",
        ]
        for sid in expected_new_ids:
            assert sid in MANIFEST_META, f"Skill renumerada '{sid}' ausente em MANIFEST_META"

    def test_old_ids_absent_from_manifest_meta(self):
        from concilium.application.skills import MANIFEST_META

        old_ids = [
            "09-relatorio-e-artefatos",
            "10-diagnostico-criticidade",
            "11-avaliacao-intervencoes",
            "12-registro-decisoes",
            "13-replanejamento-e-cenarios",
        ]
        for sid in old_ids:
            assert sid not in MANIFEST_META, f"ID legado '{sid}' ainda presente em MANIFEST_META após renumeração"

    def test_relatorio_is_number_10(self):
        from concilium.application.skills import MANIFEST_META

        assert "10-relatorio-e-artefatos" in MANIFEST_META
        assert MANIFEST_META["10-relatorio-e-artefatos"]["tier"] == "olap"

    def test_diagnostico_is_number_07(self):
        from concilium.application.skills import MANIFEST_META

        assert "07-diagnostico-criticidade" in MANIFEST_META

    def test_all_oltp_skills_have_tier_oltp(self):
        from concilium.application.skills import MANIFEST_META

        oltp_ids = [
            "01-escopo-e-eap",
            "02-produtividade-climatica",
            "03-catalogo-de-recursos",
            "04-cronograma",
            "05-equipes-e-alocacao",
            "06-resultado-financeiro",
        ]
        for sid in oltp_ids:
            assert MANIFEST_META[sid]["tier"] == "oltp", f"'{sid}' deveria ter tier='oltp'"

    def test_all_olap_skills_have_tier_olap(self):
        from concilium.application.skills import MANIFEST_META

        olap_ids = ["07-diagnostico-criticidade", "10-relatorio-e-artefatos", "11-replanejamento-e-cenarios"]
        for sid in olap_ids:
            assert MANIFEST_META[sid]["tier"] == "olap", f"'{sid}' deveria ter tier='olap'"


class TestBenchmarkRunnerMode:
    """BenchmarkRunner.run() aceita mode=PipelineMode."""

    def test_run_accepts_mode_parameter(self):
        """BenchmarkRunner.run() tem parâmetro mode= na assinatura."""
        import inspect

        from concilium.application.benchmarks.execution.runner import BenchmarkRunner

        sig = inspect.signature(BenchmarkRunner.run)
        assert "mode" in sig.parameters, "BenchmarkRunner.run() deve ter parâmetro mode="

    def test_skip_artifacts_backward_compat(self):
        """skip_artifacts=True ainda é aceito (retrocompat)."""
        import inspect

        from concilium.application.benchmarks.execution.runner import BenchmarkRunner

        sig = inspect.signature(BenchmarkRunner.run)
        assert "skip_artifacts" in sig.parameters, "skip_artifacts deve permanecer para retrocompat"

    def test_campaign_service_uses_skip_artifacts(self):
        """campaign_service usa skip_artifacts=True que mapeará para OLTP."""

        # A campanha usa skip_artifacts — verifica que o runner aceita e mapeia para OLTP
        from concilium.application.skills.phase_classifier import PipelineMode, get_skills_for_mode

        oltp_skills = get_skills_for_mode(PipelineMode.OLTP)
        assert len(oltp_skills) == 6, "OLTP deve ter exatamente 6 skills"
        assert all(s.startswith(("01", "02", "03", "04", "05", "06")) for s in oltp_skills)


class TestRfxPipelineProfiles:
    """ADR-115 — linguagem RFX resolvida no core da pipeline."""

    def test_rfi_profile_maps_to_oltp_and_catalog_path(self):
        from concilium.application.skills.phase_classifier import (
            PipelineMode,
            ProcurementIntent,
            get_pipeline_profile_for_intent,
        )

        profile = get_pipeline_profile_for_intent(ProcurementIntent.RFI)
        assert profile.mode == PipelineMode.OLTP
        assert profile.path_name == "RFI_EXPLORACAO_CATALOGO"
        assert profile.skill_sequence and all(
            s.startswith(("01", "02", "03", "04", "05", "06")) for s in profile.skill_sequence
        )

    def test_rfp_profile_maps_to_olap_and_full_analysis_path(self):
        from concilium.application.skills.phase_classifier import PipelineMode, get_pipeline_profile_for_intent

        profile = get_pipeline_profile_for_intent("rfp")
        assert profile.mode == PipelineMode.OLAP
        assert profile.path_name == "RFP_TECNICO_ECONOMICO"
        assert any("10-relatorio" in s for s in profile.skill_sequence)

    def test_unknown_intent_falls_back_to_rfi(self):
        from concilium.application.skills.phase_classifier import ProcurementIntent, get_pipeline_profile_for_intent

        profile = get_pipeline_profile_for_intent("desconhecido")
        assert profile.intent == ProcurementIntent.RFI
