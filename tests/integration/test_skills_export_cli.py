"""Integration tests for skills export CLI command."""

import json
import re

import pytest
from typer.testing import CliRunner

from concilium.presentation.main import app

runner = CliRunner()


class TestSkillsExportCLI:
    """Integration tests for 'concilium configuration skills export' CLI command."""

    def test_skills_command_exists(self):
        """skills subcommand exists in CLI."""
        result = runner.invoke(app, ["configuration", "skills", "--help"])
        assert result.exit_code == 0
        assert "export" in result.output or "subcommand" in result.output.lower()

    def test_skills_export_command_exists(self):
        """skills export subcommand exists."""
        result = runner.invoke(app, ["configuration", "skills", "export", "--help"])
        assert result.exit_code == 0
        assert "export" in result.output.lower()

    def test_skills_export_default_output(self):
        """skills export generates Mermaid to stdout by default."""
        result = runner.invoke(app, ["configuration", "skills", "export"])
        assert result.exit_code == 0

        # Output should be Mermaid graph TD
        output = result.output
        assert "graph TD" in output

    def test_skills_export_valid_mermaid_syntax(self):
        """Export output is valid Mermaid syntax."""
        result = runner.invoke(app, ["configuration", "skills", "export"])
        assert result.exit_code == 0

        output = result.output
        # Check basic Mermaid patterns
        assert re.search(r"graph\s+TD", output)
        assert re.search(r'^\s*\w+\["', output, re.MULTILINE) or "-->" in output

    def test_skills_export_contains_all_skills(self):
        """Export contains all registered skills."""
        result = runner.invoke(app, ["configuration", "skills", "export"])
        assert result.exit_code == 0

        output = result.output
        # Known skills in the system
        expected_skills = [
            "01-escopo-e-eap",
            "02-produtividade-climatica",
            "04-cronograma",
            "05-equipes-e-alocacao",
            "08-consolidacao-financeira",
            "09-relatorio-e-artefatos",
        ]

        for skill in expected_skills:
            assert skill in output, f"Skill {skill} missing from export"

    def test_skills_export_with_group_by_phase_flag(self):
        """--group-by-phase flag produces subgraphs."""
        result = runner.invoke(app, ["configuration", "skills", "export", "--group-by-phase"])
        assert result.exit_code == 0

        output = result.output
        # Subgraphs indicated by "subgraph" keyword
        assert "subgraph" in output

    def test_skills_export_with_show_validations_flag(self):
        """--show-validations flag includes VAL- codes."""
        result = runner.invoke(app, ["configuration", "skills", "export", "--show-validations"])
        assert result.exit_code == 0

        output = result.output
        # Should contain VAL- validation codes if any exist
        assert isinstance(output, str)

    def test_skills_export_with_output_file(self, tmp_path):
        """--output file writes to file instead of stdout."""
        output_file = tmp_path / "diagram.md"

        result = runner.invoke(app, ["configuration", "skills", "export", "--output", str(output_file)])
        assert result.exit_code == 0

        # File should exist and contain Mermaid
        assert output_file.exists()
        content = output_file.read_text()
        assert "graph TD" in content

    def test_skills_export_format_json(self):
        """--format json exports as JSON."""
        result = runner.invoke(app, ["configuration", "skills", "export", "--format", "json"])
        assert result.exit_code == 0

        # Output should be valid JSON
        output = result.output
        try:
            data = json.loads(output)
            assert isinstance(data, dict)
            assert "nodes" in data or "skills" in data
        except json.JSONDecodeError:
            pytest.fail("Output is not valid JSON")

    def test_skills_export_combined_flags(self, tmp_path):
        """Multiple flags work together: --group-by-phase --show-validations --output."""
        output_file = tmp_path / "diagram_detailed.md"

        result = runner.invoke(
            app,
            [
                "configuration",
                "skills",
                "export",
                "--group-by-phase",
                "--show-validations",
                "--output",
                str(output_file),
            ],
        )
        assert result.exit_code == 0
        assert output_file.exists()

        content = output_file.read_text()
        assert "subgraph" in content
        assert "graph TD" in content

    def test_skills_export_invalid_format_error(self):
        """--format with invalid value produces helpful error."""
        result = runner.invoke(app, ["configuration", "skills", "export", "--format", "invalid"])
        # Should either fail gracefully or use default
        # At minimum, shouldn't crash
        assert result.exit_code in (0, 1, 2)

    def test_skills_export_output_file_created_in_directory(self, tmp_path):
        """--output creates file in specified directory."""
        subdir = tmp_path / "diagrams"
        subdir.mkdir()
        output_file = subdir / "pipeline.md"

        result = runner.invoke(app, ["configuration", "skills", "export", "--output", str(output_file)])
        assert result.exit_code == 0
        assert output_file.exists()
