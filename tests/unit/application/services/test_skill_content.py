"""Tests for application/services/skill_content.py (ADR-144 D5/D6).

TDD: escritos antes da implementação. Promove `_read_skill_tutorial()`
(antes privada em `notifications.py`, ADR-123) para uso compartilhado entre
o anexo de onboarding e a tool MCP `obter_instrucoes_atualizadas` (D6) — e
adiciona parsing do cabeçalho de versão (D5).
"""

from __future__ import annotations

from unittest.mock import patch


class TestReadSkillContent:
    def test_reads_real_file_from_disk(self):
        from concilium.application.services import skill_content as mod

        content = mod.read_skill_content()
        assert content  # arquivo real do repo, não vazio
        assert content != mod.SKILL_FALLBACK

    def test_missing_file_falls_back(self, tmp_path):
        from concilium.application.services import skill_content as mod

        with patch.object(mod, "SKILL_PATH", tmp_path / "nao-existe.skill"):
            content = mod.read_skill_content()
        assert content == mod.SKILL_FALLBACK

    def test_never_cached_across_calls(self, tmp_path):
        """Achado crítico do ADR-144 D6: precisa ler do disco a cada chamada,
        nunca congelar no import/boot (ao contrário do padrão ui:// do ADR-101)."""
        from concilium.application.services import skill_content as mod

        skill_path = tmp_path / "concilium_usage_tutorial.skill"
        skill_path.write_text("# Versão: 1 — 2026-01-01\nconteúdo original", encoding="utf-8")

        with patch.object(mod, "SKILL_PATH", skill_path):
            first = mod.read_skill_content()
            skill_path.write_text("# Versão: 2 — 2026-07-20\nconteúdo atualizado", encoding="utf-8")
            second = mod.read_skill_content()

        assert first != second
        assert b"conteudo atualizado" not in first  # sanity: não é o mesmo objeto cacheado
        assert b"2026-07-20" in second


class TestGetSkillVersion:
    def test_parses_version_header(self):
        from concilium.application.services.skill_content import get_skill_version

        content = b"# Versao: 3 - 2026-07-20\nresto do conteudo"
        assert get_skill_version(content) == 3

    def test_parses_version_header_with_accents(self):
        from concilium.application.services.skill_content import get_skill_version

        content = "# Versão: 7 — 2026-07-20\nresto".encode()
        assert get_skill_version(content) == 7

    def test_returns_zero_when_header_absent(self):
        from concilium.application.services.skill_content import get_skill_version

        content = b"# Tutorial sem cabecalho de versao\nconteudo"
        assert get_skill_version(content) == 0

    def test_returns_zero_for_empty_content(self):
        from concilium.application.services.skill_content import get_skill_version

        assert get_skill_version(b"") == 0

    def test_defaults_to_reading_current_file_when_no_content_given(self):
        from concilium.application.services.skill_content import get_skill_version

        # O arquivo real do repo já deve ter um cabeçalho de versão (D5).
        assert get_skill_version() >= 1
