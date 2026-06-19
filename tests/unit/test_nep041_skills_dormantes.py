"""NEP-041 Fase 3 — Skills dormantes excluídas do pipeline default.

TDD: testes escritos antes da implementação.

Skills marcadas com status="dormante" no skill.toml:
  - permanecem em SKILLS (invocáveis explicitamente — sementes para ADR-070)
  - são EXCLUÍDAS de CANONICAL_SKILL_ORDER (não rodam no pipeline automático)

Skills congeladas: 08-avaliacao-intervencoes, 09-registro-decisoes.
"""

from __future__ import annotations


class TestSkillsDormantes:
    def test_11_e_12_ainda_em_SKILLS(self):
        """Dormantes continuam invocáveis explicitamente (não deletadas)."""
        from concilium.application.skills import SKILLS

        assert "08-avaliacao-intervencoes" in SKILLS
        assert "09-registro-decisoes" in SKILLS

    def test_11_e_12_excluidas_de_canonical_order(self):
        """NEP-041 Fase 3: dormantes fora do pipeline automático."""
        from concilium.application.skills.phase_classifier import CANONICAL_SKILL_ORDER

        assert "08-avaliacao-intervencoes" not in CANONICAL_SKILL_ORDER
        assert "09-registro-decisoes" not in CANONICAL_SKILL_ORDER

    def test_manifest_meta_captura_status(self):
        """MANIFEST_META expõe o campo status do skill.toml."""
        from concilium.application.skills import MANIFEST_META

        assert MANIFEST_META["08-avaliacao-intervencoes"].get("status") == "dormante"
        assert MANIFEST_META["09-registro-decisoes"].get("status") == "dormante"

    def test_skills_ativas_continuam_no_canonical_order(self):
        """Skills não-dormantes permanecem no pipeline."""
        from concilium.application.skills.phase_classifier import CANONICAL_SKILL_ORDER

        for sid in [
            "01-escopo-e-eap",
            "05-equipes-e-alocacao",
            "06-resultado-financeiro",
            "10-relatorio-e-artefatos",
            "11-replanejamento-e-cenarios",
        ]:
            assert sid in CANONICAL_SKILL_ORDER, f"{sid} deveria estar no pipeline ativo"

    def test_11_nao_esta_em_analysis_skills(self):
        """Scenario runner não tenta executar skill dormante."""
        from concilium.application.scenarios.runner import ANALYSIS_SKILLS

        assert "08-avaliacao-intervencoes" not in ANALYSIS_SKILLS
