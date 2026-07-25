"""Tests for application/services/skill_content.py (ADR-144 D5/D6).

TDD: escritos antes da implementação. Promove `_read_skill_tutorial()`
(antes privada em `notifications.py`, ADR-123) para uso compartilhado entre
o anexo de onboarding e a tool MCP `obter_instrucoes_atualizadas` (D6) — e
adiciona parsing da versão no front matter YAML do SKILL.md (D5).
"""

from __future__ import annotations

import zipfile
from io import BytesIO
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

        skill_path = tmp_path / "SKILL.md"
        skill_path.write_text("---\nname: x\ndescription: y\nversion: 1\n---\nconteúdo original", encoding="utf-8")

        with patch.object(mod, "SKILL_PATH", skill_path):
            first = mod.read_skill_content()
            skill_path.write_text(
                "---\nname: x\ndescription: y\nversion: 2\n---\nconteúdo atualizado", encoding="utf-8"
            )
            second = mod.read_skill_content()

        assert first != second
        assert b"conteudo atualizado" not in first  # sanity: não é o mesmo objeto cacheado
        assert b"conte\xc3\xbado atualizado" in second


class TestGetSkillVersion:
    def test_parses_version_field_in_frontmatter(self):
        from concilium.application.services.skill_content import get_skill_version

        content = b"---\nname: x\ndescription: y\nversion: 3\n---\nresto do conteudo"
        assert get_skill_version(content) == 3

    def test_ignores_version_mentioned_in_body(self):
        """A versão só conta se estiver dentro do front matter — não em qualquer
        menção a "version:" no corpo do documento (ex.: texto explicando o campo)."""
        from concilium.application.services.skill_content import get_skill_version

        content = (
            b"---\nname: x\ndescription: y\nversion: 7\n---\nTexto explicando que o campo version: 99 fica no topo.\n"
        )
        assert get_skill_version(content) == 7

    def test_returns_zero_when_frontmatter_absent(self):
        from concilium.application.services.skill_content import get_skill_version

        content = b"# Tutorial sem front matter\nconteudo"
        assert get_skill_version(content) == 0

    def test_returns_zero_when_version_field_absent_from_frontmatter(self):
        from concilium.application.services.skill_content import get_skill_version

        content = b"---\nname: x\ndescription: y\n---\nconteudo"
        assert get_skill_version(content) == 0

    def test_returns_zero_for_empty_content(self):
        from concilium.application.services.skill_content import get_skill_version

        assert get_skill_version(b"") == 0

    def test_defaults_to_reading_current_file_when_no_content_given(self):
        from concilium.application.services.skill_content import get_skill_version

        # O arquivo real do repo já deve ter um cabeçalho de versão (D5).
        assert get_skill_version() >= 1


class TestPackageSkillZip:
    def test_produces_a_valid_zip_with_skill_folder_as_root(self):
        from concilium.application.services import skill_content as mod

        data = mod.package_skill_zip()

        with zipfile.ZipFile(BytesIO(data)) as zf:
            assert zf.testzip() is None  # None == nenhum membro corrompido
            names = zf.namelist()
            assert names == [f"{mod.SKILL_DIR.name}/SKILL.md"]
            assert zf.read(names[0]) == mod.read_skill_content()

    def test_falls_back_when_source_file_missing(self, tmp_path):
        from concilium.application.services import skill_content as mod

        with patch.object(mod, "SKILL_PATH", tmp_path / "nao-existe.skill"):
            data = mod.package_skill_zip()

        with zipfile.ZipFile(BytesIO(data)) as zf:
            assert zf.read(f"{mod.SKILL_DIR.name}/SKILL.md") == mod.SKILL_FALLBACK
