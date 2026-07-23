"""Tests for several small modules to boost coverage."""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock, patch

# ─── cli/shared.py: _tools_root / benchmark_projects_root / _find_projects_by_name ──


class TestToolsRoot:
    def test_storage_root_is_workspace_returns_it_directly(self, tmp_path):
        from concilium.presentation.cli import shared

        storage = MagicMock(root=tmp_path)
        with (
            patch("concilium.presentation.cli.shared.get_storage", return_value=storage),
            patch("concilium.presentation.cli.shared._looks_like_workspace_root", return_value=True),
        ):
            result = shared._tools_root()
        assert result == tmp_path.resolve()

    def test_falls_back_to_cwd_ancestor_when_storage_root_is_not_workspace(self, tmp_path, monkeypatch):
        from concilium.presentation.cli import shared

        storage_root = tmp_path / "not_a_workspace"
        storage_root.mkdir()
        cwd_dir = tmp_path / "cwd_is_workspace"
        cwd_dir.mkdir()
        storage = MagicMock(root=storage_root)
        monkeypatch.chdir(cwd_dir)

        def fake_looks_like(path):
            return path == cwd_dir.resolve()

        with (
            patch("concilium.presentation.cli.shared.get_storage", return_value=storage),
            patch("concilium.presentation.cli.shared._looks_like_workspace_root", side_effect=fake_looks_like),
        ):
            result = shared._tools_root()
        assert result == cwd_dir.resolve()

    def test_falls_back_to_original_storage_root_when_nothing_matches(self, tmp_path, monkeypatch):
        """Regression: the fallback loop used to shadow `candidate`, so when no
        ancestor of cwd looked like a workspace root it silently returned the
        filesystem root ("/") instead of the original storage root."""
        from concilium.presentation.cli import shared

        storage_root = tmp_path / "not_a_workspace"
        storage_root.mkdir()
        cwd_dir = tmp_path / "cwd_also_not_workspace"
        cwd_dir.mkdir()
        storage = MagicMock(root=storage_root)
        monkeypatch.chdir(cwd_dir)

        with (
            patch("concilium.presentation.cli.shared.get_storage", return_value=storage),
            patch("concilium.presentation.cli.shared._looks_like_workspace_root", return_value=False),
        ):
            result = shared._tools_root()
        assert result == storage_root
        assert result != Path("/")


class TestBenchmarkProjectsRoot:
    def test_creates_directory_and_returns_it(self, tmp_path):
        from concilium.presentation.cli import shared

        target = tmp_path / "benchmarks" / "projetos"
        with patch("concilium.presentation.cli.shared._benchmark_projects_root", return_value=target):
            result = shared.benchmark_projects_root()
        assert result == target
        assert target.is_dir()

    def test_benchmark_projects_root_falls_back_to_tools_root(self, tmp_path):
        from concilium.presentation.cli import shared

        storage = MagicMock(benchmark_projects_root=None)
        with (
            patch("concilium.presentation.cli.shared.get_storage", return_value=storage),
            patch("concilium.presentation.cli.shared._tools_root", return_value=tmp_path),
        ):
            result = shared._benchmark_projects_root()
        assert result == tmp_path / "benchmarks" / "projetos"


class TestFindProjectsByName:
    def test_skips_non_dir_entries_and_dirs_without_meta(self, tmp_path):
        from concilium.presentation.cli.shared import _find_projects_by_name

        (tmp_path / "a_file.txt").write_text("x", encoding="utf-8")
        no_meta_dir = tmp_path / "NO_META"
        no_meta_dir.mkdir()
        with_meta_dir = tmp_path / "WITH_META"
        with_meta_dir.mkdir()
        (with_meta_dir / "meta.json").write_text(json.dumps({"nome": "Proj X"}), encoding="utf-8")

        matches = _find_projects_by_name(tmp_path, "Proj X")
        assert matches == [with_meta_dir]

    def test_skips_dirs_with_non_matching_nome(self, tmp_path):
        """Branch 109->102: quando meta['nome'] não bate, o loop segue para o
        próximo diretório sem adicionar aos matches."""
        from concilium.presentation.cli.shared import _find_projects_by_name

        other_dir = tmp_path / "OTHER"
        other_dir.mkdir()
        (other_dir / "meta.json").write_text(json.dumps({"nome": "Outro Projeto"}), encoding="utf-8")
        target_dir = tmp_path / "TARGET"
        target_dir.mkdir()
        (target_dir / "meta.json").write_text(json.dumps({"nome": "Proj X"}), encoding="utf-8")

        matches = _find_projects_by_name(tmp_path, "Proj X")
        assert matches == [target_dir]

