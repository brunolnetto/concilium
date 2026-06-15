"""Tests for concilium.presentation.cli.commands_configuration.

Covers:
- temas_list: valid tema.json, malformed tema.json fallback, empty temas/ dir
- jurisdicao_list: full aliquotas, missing motor_tributario_bdi, malformed JSON (skipped),
  nested (rglob) jurisdicao files
"""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import patch

import pytest
from typer.testing import CliRunner

from concilium.presentation.cli.commands_configuration import app_jurisdicao, app_temas

runner = CliRunner()

MODULE = "concilium.presentation.cli.commands_configuration"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _patch_config_root(monkeypatch, path: Path):
    """Monkeypatch _config_root() in commands_configuration to return *path*."""
    monkeypatch.setattr(
        f"{MODULE}._config_root",
        lambda: path,
    )


# ═══════════════════════════════════════════════════════════════════════════
# temas_list
# ═══════════════════════════════════════════════════════════════════════════


class TestTemasList:
    def test_valid_tema_json_shows_empresa_and_perfil(self, tmp_path, monkeypatch):
        """Valid tema.json — empresa, perfil_exibicao and hex swatches appear in output."""
        temas_dir = tmp_path / "temas"
        tema_dir = temas_dir / "mendeslobo"
        tema_dir.mkdir(parents=True)

        tema_data = {
            "id": "mendeslobo",
            "empresa": "Mendes Lobo",
            "perfil_exibicao": "Engenharia",
            "cores": {
                "cabecalho_fundo": "0A1628",
                "cabecalho_texto": "FFFFFF",
                "destaque": "D4A017",
            },
            "fontes": {"corpo": "Inter"},
        }
        (tema_dir / "tema.json").write_text(json.dumps(tema_data), encoding="utf-8")

        _patch_config_root(monkeypatch, tmp_path)
        result = runner.invoke(app_temas, [])

        assert result.exit_code == 0, result.output
        # Rich may wrap "Mendes Lobo" across two lines; check parts separately
        assert "Mendes" in result.output
        assert "Engenharia" in result.output
        # hex swatches — colours appear in output
        assert "0A1628" in result.output
        assert "D4A017" in result.output

    def test_malformed_tema_json_shows_fallback_row(self, tmp_path, monkeypatch):
        """Malformed (invalid JSON) tema.json — fallback row with '?' appears."""
        temas_dir = tmp_path / "temas"
        tema_dir = temas_dir / "broken"
        tema_dir.mkdir(parents=True)
        (tema_dir / "tema.json").write_text("{NOT VALID JSON", encoding="utf-8")

        _patch_config_root(monkeypatch, tmp_path)
        result = runner.invoke(app_temas, [])

        assert result.exit_code == 0, result.output
        assert "?" in result.output

    def test_missing_tema_json_shows_fallback_row(self, tmp_path, monkeypatch):
        """Missing tema.json entirely — fallback row with '?' appears."""
        temas_dir = tmp_path / "temas"
        tema_dir = temas_dir / "no-json"
        tema_dir.mkdir(parents=True)
        # No tema.json written

        _patch_config_root(monkeypatch, tmp_path)
        result = runner.invoke(app_temas, [])

        assert result.exit_code == 0, result.output
        assert "?" in result.output

    def test_empty_temas_dir_renders_empty_table(self, tmp_path, monkeypatch):
        """Empty temas/ directory — table renders without data rows (no '?')."""
        temas_dir = tmp_path / "temas"
        temas_dir.mkdir(parents=True)

        _patch_config_root(monkeypatch, tmp_path)
        result = runner.invoke(app_temas, [])

        assert result.exit_code == 0, result.output
        # Table header should be present but no data rows
        assert "Temas" in result.output
        assert "?" not in result.output

    def test_non_directory_entries_are_skipped(self, tmp_path, monkeypatch):
        """Files directly inside temas/ are skipped (only dirs processed)."""
        temas_dir = tmp_path / "temas"
        temas_dir.mkdir(parents=True)
        (temas_dir / "stray_file.json").write_text("{}", encoding="utf-8")

        _patch_config_root(monkeypatch, tmp_path)
        result = runner.invoke(app_temas, [])

        assert result.exit_code == 0, result.output
        assert "?" not in result.output

    def test_multiple_temas_sorted_output(self, tmp_path, monkeypatch):
        """Multiple tema dirs appear sorted alphabetically."""
        temas_dir = tmp_path / "temas"
        for name, empresa in [("zzz", "ZZZ Corp"), ("aaa", "AAA Corp")]:
            d = temas_dir / name
            d.mkdir(parents=True)
            (d / "tema.json").write_text(
                json.dumps({"empresa": empresa, "perfil_exibicao": "P", "cores": {}, "fontes": {}}),
                encoding="utf-8",
            )

        _patch_config_root(monkeypatch, tmp_path)
        result = runner.invoke(app_temas, [])

        assert result.exit_code == 0, result.output
        assert "AAA Corp" in result.output
        assert "ZZZ Corp" in result.output
        # sorted: aaa before zzz
        assert result.output.index("AAA") < result.output.index("ZZZ")

    def test_tema_uses_dir_name_when_id_missing(self, tmp_path, monkeypatch):
        """When id is absent in tema.json, the directory name is used as the tema id."""
        temas_dir = tmp_path / "temas"
        tema_dir = temas_dir / "custom-id"
        tema_dir.mkdir(parents=True)
        # no "id" key
        (tema_dir / "tema.json").write_text(
            json.dumps({"empresa": "My Co", "perfil_exibicao": "P", "cores": {}, "fontes": {}}),
            encoding="utf-8",
        )

        _patch_config_root(monkeypatch, tmp_path)
        result = runner.invoke(app_temas, [])

        assert result.exit_code == 0, result.output
        assert "custom-id" in result.output


# ═══════════════════════════════════════════════════════════════════════════
# jurisdicao_list
# ═══════════════════════════════════════════════════════════════════════════


class TestJurisdicaoList:
    def test_full_aliquotas_shows_formatted_percentages(self, tmp_path, monkeypatch):
        """Full aliquotas dict — ISS, PIS, COFINS, CPRB and Total appear as x.xx%."""
        jur_dir = tmp_path / "jurisdicoes"
        jur_dir.mkdir(parents=True)

        jur_data = {
            "codigo": "SP-CAP",
            "nome": "São Paulo Capital",
            "parent_id": "SP",
            "motor_tributario_bdi": {
                "aliquotas": {
                    "ISS": 0.05,
                    "PIS": 0.0065,
                    "COFINS": 0.03,
                    "CPRB": 0.045,
                }
            },
        }
        (jur_dir / "sp_capital.json").write_text(json.dumps(jur_data), encoding="utf-8")

        _patch_config_root(monkeypatch, tmp_path)
        result = runner.invoke(app_jurisdicao, [])

        assert result.exit_code == 0, result.output
        assert "5.00%" in result.output   # ISS
        assert "0.65%" in result.output   # PIS
        assert "3.00%" in result.output   # COFINS
        assert "4.50%" in result.output   # CPRB
        # Total = 0.05 + 0.0065 + 0.03 + 0.045 = 0.1315 → 13.15%
        assert "13.15%" in result.output

    def test_missing_motor_tributario_bdi_shows_dashes(self, tmp_path, monkeypatch):
        """Jurisdicao JSON missing motor_tributario_bdi — all aliquota columns show '-'."""
        jur_dir = tmp_path / "jurisdicoes"
        jur_dir.mkdir(parents=True)

        jur_data = {
            "codigo": "RJ",
            "nome": "Rio de Janeiro",
            "parent_id": None,
            # no motor_tributario_bdi key
        }
        (jur_dir / "rj.json").write_text(json.dumps(jur_data), encoding="utf-8")

        _patch_config_root(monkeypatch, tmp_path)
        result = runner.invoke(app_jurisdicao, [])

        assert result.exit_code == 0, result.output
        # All 4 tax columns + total should be "-"
        assert result.output.count("-") >= 5

    def test_malformed_json_is_silently_skipped(self, tmp_path, monkeypatch):
        """Malformed JSON file is silently skipped (continue branch); output must not crash."""
        jur_dir = tmp_path / "jurisdicoes"
        jur_dir.mkdir(parents=True)

        # Malformed file
        (jur_dir / "broken.json").write_text("{INVALID", encoding="utf-8")
        # Valid file alongside the broken one
        good_data = {
            "codigo": "MG",
            "nome": "Minas Gerais",
            "motor_tributario_bdi": {"aliquotas": {"ISS": 0.03}},
        }
        (jur_dir / "mg.json").write_text(json.dumps(good_data), encoding="utf-8")

        _patch_config_root(monkeypatch, tmp_path)
        result = runner.invoke(app_jurisdicao, [])

        assert result.exit_code == 0, result.output
        # Good file still renders (Rich may wrap text; check identifier)
        assert "MG" in result.output
        # No Python traceback leaked
        assert "Traceback" not in result.output

    def test_nested_jurisdicao_files_picked_up_via_rglob(self, tmp_path, monkeypatch):
        """Files in subdirectories are also picked up (rglob)."""
        jur_dir = tmp_path / "jurisdicoes"
        sub = jur_dir / "estados" / "sp"
        sub.mkdir(parents=True)

        jur_data = {
            "codigo": "SP-INT",
            "nome": "São Paulo Interior",
            "motor_tributario_bdi": {"aliquotas": {"ISS": 0.02}},
        }
        (sub / "interior.json").write_text(json.dumps(jur_data), encoding="utf-8")

        _patch_config_root(monkeypatch, tmp_path)
        result = runner.invoke(app_jurisdicao, [])

        assert result.exit_code == 0, result.output
        # "SP-INT" is the codigo; name may be wrapped across lines
        assert "SP-INT" in result.output

    def test_empty_jurisdicoes_dir_renders_empty_table(self, tmp_path, monkeypatch):
        """Empty jurisdicoes/ directory — table header renders, no data rows."""
        jur_dir = tmp_path / "jurisdicoes"
        jur_dir.mkdir(parents=True)

        _patch_config_root(monkeypatch, tmp_path)
        result = runner.invoke(app_jurisdicao, [])

        assert result.exit_code == 0, result.output
        assert "Jurisdições" in result.output or "Jurisdi" in result.output

    def test_jurisdicao_uses_stem_when_codigo_missing(self, tmp_path, monkeypatch):
        """When codigo is absent, the file stem is used as the row identifier."""
        jur_dir = tmp_path / "jurisdicoes"
        jur_dir.mkdir(parents=True)

        jur_data = {"nome": "Unnamed Jur"}  # no codigo, no motor_tributario_bdi
        (jur_dir / "my_stem.json").write_text(json.dumps(jur_data), encoding="utf-8")

        _patch_config_root(monkeypatch, tmp_path)
        result = runner.invoke(app_jurisdicao, [])

        assert result.exit_code == 0, result.output
        assert "my_stem" in result.output

    def test_empty_aliquotas_dict_shows_none_total(self, tmp_path, monkeypatch):
        """Empty aliquotas dict — total is None, so '-' is shown."""
        jur_dir = tmp_path / "jurisdicoes"
        jur_dir.mkdir(parents=True)

        jur_data = {
            "codigo": "BA",
            "nome": "Bahia",
            "motor_tributario_bdi": {"aliquotas": {}},
        }
        (jur_dir / "ba.json").write_text(json.dumps(jur_data), encoding="utf-8")

        _patch_config_root(monkeypatch, tmp_path)
        result = runner.invoke(app_jurisdicao, [])

        assert result.exit_code == 0, result.output
        assert "Bahia" in result.output
        # total is None → shown as "-"
        assert "-" in result.output
