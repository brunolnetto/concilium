"""Tests for concilium.presentation.cli.commands_campaign — covering missing lines."""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock, patch

import typer
from typer.testing import CliRunner

from concilium.presentation.cli.commands_campaign import (
    _canonical_to_base_spec,
    _default_config_root,
    _default_projects_root,
    _load_project_base_spec,
    campaign,
)

runner = CliRunner()


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_app() -> typer.Typer:
    """Build a minimal Typer app wrapping the campaign command."""
    app = typer.Typer()
    app.command()(campaign)
    return app


def _minimal_campaign_cfg(tmp_path: Path) -> Path:
    """Write a minimal campaign_v1.json and return its path."""
    cfg = {
        "descricao": "Teste de campanha",
        "campaign_version": "v1",
        "top_k": 3,
        "perfil_expectativas": {
            "meta_margem_pct": 0.10,
            "tolerancia_margem": 0.03,
        },
        "sweep": [
            {"campo": "n_frentes", "valores": [1, 2]},
        ],
    }
    p = tmp_path / "campaign_v1.json"
    p.write_text(json.dumps(cfg), encoding="utf-8")
    return p


def _make_mock_result(shortlist=None):
    """Build a realistic mock CampaignOutputBundle."""
    result = MagicMock()
    result.status = "PARCIAL"
    result.n_cenarios_avaliados = 2
    result.n_cenarios_viaveis = 1
    result.n_falhas = 0
    result.campaign_version = "v1"
    result.shortlist = shortlist or []
    # Make sweep iterable for the n_cenarios product loop
    sw = MagicMock()
    sw.valores = [1, 2]
    result.sweep = [sw]
    return result


def _make_mock_store() -> MagicMock:
    store = MagicMock()
    store.new_run.return_value = "run_001"
    store.run_path.return_value = Path("/tmp/fake_store/run_001")
    store.list_run_files.return_value = ["report.md", "bundle.json"]
    store.list_runs.return_value = ["run_001"]
    return store


PATCH_EXECUTAR = "concilium.application.services.campaign.campaign_service.executar_campanha"
PATCH_CUBO = "concilium.application.services.campaign.campaign_service.construir_cubo"
PATCH_SERIALIZE = "concilium.application.services.campaign.campaign_report.serialize_campaign_report"
PATCH_RENDER_MD = "concilium.application.services.campaign.campaign_report.render_campaign_report_md"
PATCH_RENDER_PDF = "concilium.application.services.campaign.campaign_report.render_campaign_report_pdf"
PATCH_STORE = "concilium.infrastructure.storage.campaign_store.CampaignRunStore"
PATCH_BASE_SPEC = "concilium.presentation.cli.commands_campaign._load_project_base_spec"
PATCH_CFG_ROOT = "concilium.presentation.cli.commands_campaign._default_config_root"
PATCH_PROJ_ROOT = "concilium.presentation.cli.commands_campaign._default_projects_root"


# ---------------------------------------------------------------------------
# Happy path: campaign_file provided, full pipeline runs
# ---------------------------------------------------------------------------


class TestCampaignHappyPath:
    def test_happy_path_full_pipeline(self, tmp_path: Path):
        """Lines 32-34, 39, 42-43, 45, 48, 55, 57, 62-63, 67, 73-74, 79-80,
        88-91, 94-95, 97, 105-106, 108-110, 113, 116-118, 120-123, 131-133."""
        campaign_file = _minimal_campaign_cfg(tmp_path)
        base_spec = {"slug": "AGIS", "meta": {}}
        mock_result = _make_mock_result()
        mock_store = _make_mock_store()
        mock_report = {"cubo": {"dim": []}, "cenarios": []}

        app = _make_app()

        with (
            patch(PATCH_BASE_SPEC, return_value=base_spec),
            patch(PATCH_EXECUTAR, return_value=mock_result) as mock_exec,
            patch(PATCH_CUBO, return_value=MagicMock()) as mock_cubo,
            patch(PATCH_SERIALIZE, return_value=mock_report),
            patch(PATCH_RENDER_MD, return_value="# Markdown"),
            patch(PATCH_RENDER_PDF, return_value=b"%PDF"),
            patch(PATCH_STORE, return_value=mock_store),
        ):
            result = runner.invoke(
                app,
                [
                    "AGIS",
                    "--campaign",
                    str(campaign_file),
                    "--config",
                    str(tmp_path / "config"),
                    "--projects",
                    str(tmp_path / "projetos"),
                    "--workers",
                    "2",
                ],
            )

        assert result.exit_code == 0, result.output
        assert "[INFO] Campanha:" in result.output
        assert "[INFO] Grid:" in result.output
        assert "[RESULTADO]" in result.output
        assert "[STORE] Novo run:" in result.output
        assert "[SAVE]" in result.output
        assert "[INFO] Runs disponíveis:" in result.output
        mock_exec.assert_called_once()
        mock_cubo.assert_called_once()

    def test_happy_path_with_shortlist(self, tmp_path: Path):
        """Lines 98-102: shortlist items echoed to output."""
        campaign_file = _minimal_campaign_cfg(tmp_path)
        base_spec = {"slug": "AGIS", "meta": {}}

        justificativa = MagicMock()
        justificativa.motivo_inclusao = "melhor_custo"
        justificativa.destaques_EF = ["EF1"]
        justificativa.destaques_O = ["O1", "O2"]

        cenario = MagicMock()
        cenario.cenario_id = "CEN-001"

        ranked = MagicMock()
        ranked.rank = 1
        ranked.cenario = cenario
        ranked.justificativa = justificativa

        mock_result = _make_mock_result(shortlist=[ranked])
        mock_store = _make_mock_store()

        app = _make_app()

        with (
            patch(PATCH_BASE_SPEC, return_value=base_spec),
            patch(PATCH_EXECUTAR, return_value=mock_result),
            patch(PATCH_CUBO, return_value=MagicMock()),
            patch(PATCH_SERIALIZE, return_value={"cubo": {}}),
            patch(PATCH_RENDER_MD, return_value="# md"),
            patch(PATCH_RENDER_PDF, return_value=b""),
            patch(PATCH_STORE, return_value=mock_store),
        ):
            result = runner.invoke(
                app,
                [
                    "AGIS",
                    "--campaign",
                    str(campaign_file),
                    "--config",
                    str(tmp_path / "config"),
                    "--projects",
                    str(tmp_path / "projetos"),
                ],
            )

        assert result.exit_code == 0, result.output
        assert "#1 CEN-001" in result.output
        assert "melhor_custo" in result.output

    def test_save_meta_called_correctly(self, tmp_path: Path):
        """Lines 123-129: save_meta is called with the correct dict."""
        campaign_file = _minimal_campaign_cfg(tmp_path)
        base_spec = {"slug": "AGIS", "meta": {}}
        mock_result = _make_mock_result()
        mock_result.status = "COMPLETO"
        mock_result.n_cenarios_avaliados = 4
        mock_result.n_cenarios_viaveis = 3
        mock_result.n_falhas = 1
        mock_result.campaign_version = "v2"
        mock_store = _make_mock_store()

        app = _make_app()

        with (
            patch(PATCH_BASE_SPEC, return_value=base_spec),
            patch(PATCH_EXECUTAR, return_value=mock_result),
            patch(PATCH_CUBO, return_value=MagicMock()),
            patch(PATCH_SERIALIZE, return_value={"cubo": None}),
            patch(PATCH_RENDER_MD, return_value=""),
            patch(PATCH_RENDER_PDF, return_value=b""),
            patch(PATCH_STORE, return_value=mock_store),
        ):
            result = runner.invoke(
                app,
                [
                    "AGIS",
                    "--campaign",
                    str(campaign_file),
                    "--config",
                    str(tmp_path / "config"),
                    "--projects",
                    str(tmp_path / "projetos"),
                ],
            )

        assert result.exit_code == 0, result.output
        mock_store.save_meta.assert_called_once()
        meta_arg = mock_store.save_meta.call_args[0][1]
        assert meta_arg["campaign_version"] == "v2"
        assert meta_arg["n_avaliados"] == 4
        assert meta_arg["n_viaveis"] == 3
        assert meta_arg["n_falhas"] == 1


# ---------------------------------------------------------------------------
# campaign_file auto-discovery
# ---------------------------------------------------------------------------


class TestCampaignAutoDiscovery:
    def test_auto_discovery_finds_candidate(self, tmp_path: Path):
        """Lines 48-55: campaign_file=None, auto-discovery finds first candidate."""
        # Create the default candidate: projetos/AGIS/campaigns/campaign_v1.json
        proj_root = tmp_path / "projetos"
        campaigns_dir = proj_root / "AGIS" / "campaigns"
        campaigns_dir.mkdir(parents=True)
        campaign_file = campaigns_dir / "campaign_v1.json"
        campaign_file.write_text(
            json.dumps(
                {
                    "descricao": "Auto-discovered",
                    "campaign_version": "v1",
                    "top_k": 2,
                    "perfil_expectativas": {},
                    "sweep": [],
                }
            ),
            encoding="utf-8",
        )

        base_spec = {"slug": "AGIS", "meta": {}}
        mock_result = _make_mock_result()
        mock_store = _make_mock_store()

        app = _make_app()

        with (
            patch(PATCH_BASE_SPEC, return_value=base_spec),
            patch(PATCH_EXECUTAR, return_value=mock_result),
            patch(PATCH_CUBO, return_value=MagicMock()),
            patch(PATCH_SERIALIZE, return_value={"cubo": {}}),
            patch(PATCH_RENDER_MD, return_value=""),
            patch(PATCH_RENDER_PDF, return_value=b""),
            patch(PATCH_STORE, return_value=mock_store),
        ):
            result = runner.invoke(
                app,
                [
                    "AGIS",
                    "--config",
                    str(tmp_path / "config"),
                    "--projects",
                    str(proj_root),
                ],
            )

        assert result.exit_code == 0, result.output
        assert "Auto-discovered" in result.output

    def test_auto_discovery_no_candidate_exits_1(self, tmp_path: Path):
        """Lines 57-59: campaign_file=None, no candidate exists → Exit(1)."""
        proj_root = tmp_path / "projetos"
        proj_root.mkdir()

        app = _make_app()

        result = runner.invoke(
            app,
            [
                "NOEXIST",
                "--config",
                str(tmp_path / "config"),
                "--projects",
                str(proj_root),
            ],
        )

        assert result.exit_code == 1
        assert "[ERRO]" in result.output or "[ERRO]" in (result.stderr or "")

    def test_campaign_file_not_found_exits_1(self, tmp_path: Path):
        """Lines 57-59: explicit campaign_file that does not exist → Exit(1)."""
        missing = tmp_path / "no_such_campaign.json"

        app = _make_app()

        result = runner.invoke(
            app,
            [
                "AGIS",
                "--campaign",
                str(missing),
                "--config",
                str(tmp_path / "config"),
                "--projects",
                str(tmp_path / "projetos"),
            ],
        )

        assert result.exit_code == 1
        assert "[ERRO]" in result.output or "[ERRO]" in (result.stderr or "")

    def test_base_spec_none_exits_1(self, tmp_path: Path):
        """Lines 68-70: base_spec is None → Exit(1)."""
        campaign_file = _minimal_campaign_cfg(tmp_path)

        app = _make_app()

        with patch(PATCH_BASE_SPEC, return_value=None):
            result = runner.invoke(
                app,
                [
                    "AGIS",
                    "--campaign",
                    str(campaign_file),
                    "--config",
                    str(tmp_path / "config"),
                    "--projects",
                    str(tmp_path / "projetos"),
                ],
            )

        assert result.exit_code == 1
        assert "[ERRO]" in result.output or "[ERRO]" in (result.stderr or "")


# ---------------------------------------------------------------------------
# _load_project_base_spec
# ---------------------------------------------------------------------------


class TestLoadProjectBaseSpec:
    def test_referencia_json_in_data(self, tmp_path: Path):
        """Lines 151-155: referencia.json found in data/{slug}/ → returns parsed dict."""
        slug = "MYPROJ"
        data_dir = tmp_path / "data" / slug
        data_dir.mkdir(parents=True)
        spec = {"slug": slug, "meta": {"projeto": "My Project"}}
        (data_dir / "referencia.json").write_text(json.dumps(spec))

        # projects_root is tmp_path/projetos so parent is tmp_path
        projects_root = tmp_path / "projetos"
        projects_root.mkdir()

        result = _load_project_base_spec(projects_root, slug)
        assert result == spec

    def test_referencia_json_case_upper(self, tmp_path: Path):
        """Case-insensitive slug: lowercase slug param finds uppercase dir."""
        slug = "myproj"
        data_dir = tmp_path / "data" / "MYPROJ"
        data_dir.mkdir(parents=True)
        spec = {"slug": "MYPROJ"}
        (data_dir / "referencia.json").write_text(json.dumps(spec))

        projects_root = tmp_path / "projetos"
        projects_root.mkdir()

        result = _load_project_base_spec(projects_root, slug)
        assert result == spec

    def test_spec_json_in_projetos(self, tmp_path: Path):
        """Lines 158-161: no referencia, spec.json found in projetos/{slug}/ → returns parsed dict."""
        slug = "MYPROJ"
        proj_dir = tmp_path / "projetos" / slug
        proj_dir.mkdir(parents=True)
        spec = {"slug": slug, "via": "spec.json"}
        (proj_dir / "spec.json").write_text(json.dumps(spec))

        projects_root = tmp_path / "projetos"

        result = _load_project_base_spec(projects_root, slug)
        assert result == spec

    def test_canonical_json_fallback(self, tmp_path: Path):
        """Lines 163-168: no referencia/spec, canonical.json found → stripped dict via _canonical_to_base_spec."""
        slug = "MYPROJ"
        can_dir = tmp_path / "projetos" / slug / "v1"
        can_dir.mkdir(parents=True)
        canonical = {
            "projeto": {
                "nome": "My Project",
                "data_inicio": "2025-01-01",
                "data_termino": "2025-12-31",
                "regime_trabalho": {"dias": 5},
            }
        }
        (can_dir / "canonical.json").write_text(json.dumps(canonical))

        projects_root = tmp_path / "projetos"
        # No data/ directory at all

        result = _load_project_base_spec(projects_root, slug)
        assert result is not None
        assert result["slug"] == slug
        assert result["meta"]["projeto"] == "My Project"

    def test_nothing_found_returns_none(self, tmp_path: Path):
        """Line 170: nothing found → returns None."""
        projects_root = tmp_path / "projetos"
        projects_root.mkdir()

        result = _load_project_base_spec(projects_root, "GHOST")
        assert result is None


# ---------------------------------------------------------------------------
# _canonical_to_base_spec
# ---------------------------------------------------------------------------


class TestCanonicalToBaseSpec:
    def test_full_canonical(self):
        """Lines 175-185: full canonical → expected meta dict."""
        canonical = {
            "projeto": {
                "nome": "Obra Alpha",
                "data_inicio": "2025-03-01",
                "data_termino": "2026-02-28",
                "regime_trabalho": {"dias_semana": 5, "horas_dia": 8},
            }
        }
        result = _canonical_to_base_spec(canonical, "ALPHA")
        assert result["slug"] == "ALPHA"
        assert result["meta"]["projeto"] == "Obra Alpha"
        assert result["meta"]["data_inicio"] == "2025-03-01"
        assert result["meta"]["data_termino"] == "2026-02-28"
        assert result["meta"]["regime_trabalho"]["dias_semana"] == 5

    def test_empty_canonical(self):
        """_canonical_to_base_spec with empty dict uses slug as project name."""
        result = _canonical_to_base_spec({}, "EMPTY")
        assert result["slug"] == "EMPTY"
        assert result["meta"]["projeto"] == "EMPTY"
        assert result["meta"]["data_inicio"] == ""
        assert result["meta"]["regime_trabalho"] == {}

    def test_canonical_missing_regime(self):
        """regime_trabalho missing defaults to empty dict."""
        canonical = {"projeto": {"nome": "Proj X"}}
        result = _canonical_to_base_spec(canonical, "X")
        assert result["meta"]["regime_trabalho"] == {}


# ---------------------------------------------------------------------------
# _default_config_root
# ---------------------------------------------------------------------------


class TestDefaultConfigRoot:
    def test_returns_path_ending_config(self):
        """Lines 191-195, 197-199: real repo structure → returns a Path."""
        result = _default_config_root()
        assert isinstance(result, Path)
        # In the real repo, config/catalogos exists
        assert result.name == "config"

    def test_config_catalogos_present(self):
        """The returned config directory exists and has a catalogos child."""
        result = _default_config_root()
        # Config/catalogos structure exists in the repo
        assert (result / "catalogos").exists()

    def test_fallback_git_root(self, tmp_path: Path, monkeypatch):
        """Lines 204-206: no config/catalogos anywhere, but a .git dir exists at an
        ancestor → returns <that ancestor>/config.

        __file__ is a plain module global read at call time, so pointing it at a
        fake path inside tmp_path makes Path(__file__).resolve().parents walk the
        real tmp_path tree instead of the real repo.
        """
        (tmp_path / ".git").mkdir()
        fake_file = tmp_path / "src" / "pkg" / "module.py"
        fake_file.parent.mkdir(parents=True)
        fake_file.write_text("")

        monkeypatch.setattr(
            "concilium.presentation.cli.commands_campaign.__file__",
            str(fake_file),
        )

        result = _default_config_root()
        assert result == tmp_path / "config"

    def test_fallback_no_git_no_catalogos(self, tmp_path: Path, monkeypatch):
        """Line 207: neither config/catalogos nor .git found in any ancestor →
        ultimate fallback Path('config')."""
        fake_file = tmp_path / "src" / "pkg" / "module.py"
        fake_file.parent.mkdir(parents=True)
        fake_file.write_text("")

        monkeypatch.setattr(
            "concilium.presentation.cli.commands_campaign.__file__",
            str(fake_file),
        )

        result = _default_config_root()
        assert result == Path("config")


# ---------------------------------------------------------------------------
# _default_projects_root
# ---------------------------------------------------------------------------


class TestDefaultProjectsRoot:
    def test_benchmarks_projetos_structure(self, tmp_path: Path, monkeypatch):
        """benchmarks/projetos structure present → returns <ancestor>/benchmarks/projetos."""
        (tmp_path / "benchmarks" / "projetos").mkdir(parents=True)
        fake_file = tmp_path / "src" / "pkg" / "module.py"
        fake_file.parent.mkdir(parents=True)
        fake_file.write_text("")

        monkeypatch.setattr(
            "concilium.presentation.cli.commands_campaign.__file__",
            str(fake_file),
        )

        result = _default_projects_root()
        assert result == tmp_path / "benchmarks" / "projetos"

    def test_real_repo_returns_benchmarks_projetos(self):
        """In the real repo, _default_projects_root returns .../benchmarks/projetos."""
        result = _default_projects_root()
        assert isinstance(result, Path)
        assert result.name == "projetos"

    def test_projetos_dir_present(self, tmp_path: Path, monkeypatch):
        """Line 216: projetos dir present but no benchmarks/projetos anywhere → returns
        <ancestor>/projetos."""
        (tmp_path / "projetos").mkdir()
        fake_file = tmp_path / "src" / "pkg" / "module.py"
        fake_file.parent.mkdir(parents=True)
        fake_file.write_text("")

        monkeypatch.setattr(
            "concilium.presentation.cli.commands_campaign.__file__",
            str(fake_file),
        )

        result = _default_projects_root()
        assert result == tmp_path / "projetos"

    def test_fallback_no_structure(self, tmp_path: Path, monkeypatch):
        """Line 217: ultimate fallback → Path('projetos') when no ancestor has
        benchmarks/projetos nor projetos."""
        fake_file = tmp_path / "src" / "pkg" / "module.py"
        fake_file.parent.mkdir(parents=True)
        fake_file.write_text("")

        monkeypatch.setattr(
            "concilium.presentation.cli.commands_campaign.__file__",
            str(fake_file),
        )

        result = _default_projects_root()
        assert result == Path("projetos")


# ---------------------------------------------------------------------------
# Additional edge-case tests for campaign()
# ---------------------------------------------------------------------------


class TestCampaignEdgeCases:
    def test_default_roots_used_when_not_provided(self, tmp_path: Path):
        """Lines 42-43: config_root/projects_root defaults resolved via helper functions."""
        campaign_file = _minimal_campaign_cfg(tmp_path)
        base_spec = {"slug": "AGIS", "meta": {}}
        mock_result = _make_mock_result()
        mock_store = _make_mock_store()

        app = _make_app()

        default_cfg = tmp_path / "config"
        default_proj = tmp_path / "projetos"

        with (
            patch(PATCH_CFG_ROOT, return_value=default_cfg) as mock_cfg,
            patch(PATCH_PROJ_ROOT, return_value=default_proj) as mock_proj,
            patch(PATCH_BASE_SPEC, return_value=base_spec),
            patch(PATCH_EXECUTAR, return_value=mock_result),
            patch(PATCH_CUBO, return_value=MagicMock()),
            patch(PATCH_SERIALIZE, return_value={"cubo": {}}),
            patch(PATCH_RENDER_MD, return_value=""),
            patch(PATCH_RENDER_PDF, return_value=b""),
            patch(PATCH_STORE, return_value=mock_store),
        ):
            result = runner.invoke(
                app,
                [
                    "AGIS",
                    "--campaign",
                    str(campaign_file),
                    # No --config or --projects — use defaults
                ],
            )

        assert result.exit_code == 0, result.output
        mock_cfg.assert_called_once()
        mock_proj.assert_called_once()

    def test_slug_uppercased(self, tmp_path: Path):
        """Line 45: project_id is uppercased to slug."""
        campaign_file = _minimal_campaign_cfg(tmp_path)
        base_spec = {"slug": "AGIS", "meta": {}}
        mock_result = _make_mock_result()
        mock_store = _make_mock_store()

        captured_slug = []

        def fake_load_spec(projects_root, slug):
            captured_slug.append(slug)
            return base_spec

        app = _make_app()

        with (
            patch(PATCH_BASE_SPEC, side_effect=fake_load_spec),
            patch(PATCH_EXECUTAR, return_value=mock_result),
            patch(PATCH_CUBO, return_value=MagicMock()),
            patch(PATCH_SERIALIZE, return_value={"cubo": {}}),
            patch(PATCH_RENDER_MD, return_value=""),
            patch(PATCH_RENDER_PDF, return_value=b""),
            patch(PATCH_STORE, return_value=mock_store),
        ):
            result = runner.invoke(
                app,
                [
                    "agis",  # lowercase — should be uppercased
                    "--campaign",
                    str(campaign_file),
                    "--config",
                    str(tmp_path / "config"),
                    "--projects",
                    str(tmp_path / "projetos"),
                ],
            )

        assert result.exit_code == 0, result.output
        assert captured_slug[0] == "AGIS"

    def test_campaign_no_descricao_uses_filename(self, tmp_path: Path):
        """Line 63: cfg without 'descricao' shows filename."""
        cfg_no_desc = {"campaign_version": "v1", "top_k": 2, "perfil_expectativas": {}, "sweep": []}
        campaign_file = tmp_path / "campaign_special.json"
        campaign_file.write_text(json.dumps(cfg_no_desc), encoding="utf-8")

        base_spec = {"slug": "AGIS", "meta": {}}
        mock_result = _make_mock_result()
        mock_store = _make_mock_store()

        app = _make_app()

        with (
            patch(PATCH_BASE_SPEC, return_value=base_spec),
            patch(PATCH_EXECUTAR, return_value=mock_result),
            patch(PATCH_CUBO, return_value=MagicMock()),
            patch(PATCH_SERIALIZE, return_value={"cubo": {}}),
            patch(PATCH_RENDER_MD, return_value=""),
            patch(PATCH_RENDER_PDF, return_value=b""),
            patch(PATCH_STORE, return_value=mock_store),
        ):
            result = runner.invoke(
                app,
                [
                    "AGIS",
                    "--campaign",
                    str(campaign_file),
                    "--config",
                    str(tmp_path / "config"),
                    "--projects",
                    str(tmp_path / "projetos"),
                ],
            )

        assert result.exit_code == 0, result.output
        # Without descricao, filename should be used
        assert "campaign_special.json" in result.output

    def test_shortlist_empty_no_rank_lines(self, tmp_path: Path):
        """Lines 98-102: shortlist empty → no rank lines echoed."""
        campaign_file = _minimal_campaign_cfg(tmp_path)
        base_spec = {"slug": "AGIS", "meta": {}}
        mock_result = _make_mock_result(shortlist=[])
        mock_store = _make_mock_store()

        app = _make_app()

        with (
            patch(PATCH_BASE_SPEC, return_value=base_spec),
            patch(PATCH_EXECUTAR, return_value=mock_result),
            patch(PATCH_CUBO, return_value=MagicMock()),
            patch(PATCH_SERIALIZE, return_value={"cubo": {}}),
            patch(PATCH_RENDER_MD, return_value=""),
            patch(PATCH_RENDER_PDF, return_value=b""),
            patch(PATCH_STORE, return_value=mock_store),
        ):
            result = runner.invoke(
                app,
                [
                    "AGIS",
                    "--campaign",
                    str(campaign_file),
                    "--config",
                    str(tmp_path / "config"),
                    "--projects",
                    str(tmp_path / "projetos"),
                ],
            )

        assert result.exit_code == 0, result.output
        # No "#N " rank lines in output
        assert "  #" not in result.output

    def test_save_cube_none_coalesced(self, tmp_path: Path):
        """Line 121: report.get('cubo') returns None → save_cube called with {}."""
        campaign_file = _minimal_campaign_cfg(tmp_path)
        base_spec = {"slug": "AGIS", "meta": {}}
        mock_result = _make_mock_result()
        mock_store = _make_mock_store()

        app = _make_app()

        with (
            patch(PATCH_BASE_SPEC, return_value=base_spec),
            patch(PATCH_EXECUTAR, return_value=mock_result),
            patch(PATCH_CUBO, return_value=MagicMock()),
            patch(PATCH_SERIALIZE, return_value={"cubo": None}),  # None cubo
            patch(PATCH_RENDER_MD, return_value=""),
            patch(PATCH_RENDER_PDF, return_value=b""),
            patch(PATCH_STORE, return_value=mock_store),
        ):
            result = runner.invoke(
                app,
                [
                    "AGIS",
                    "--campaign",
                    str(campaign_file),
                    "--config",
                    str(tmp_path / "config"),
                    "--projects",
                    str(tmp_path / "projetos"),
                ],
            )

        assert result.exit_code == 0, result.output
        mock_store.save_cube.assert_called_once_with("run_001", {})

    def test_workers_passed_to_executar(self, tmp_path: Path):
        """Line 94: workers param passed to executar_campanha."""
        campaign_file = _minimal_campaign_cfg(tmp_path)
        base_spec = {"slug": "AGIS", "meta": {}}
        mock_result = _make_mock_result()
        mock_store = _make_mock_store()

        app = _make_app()

        with (
            patch(PATCH_BASE_SPEC, return_value=base_spec),
            patch(PATCH_EXECUTAR, return_value=mock_result) as mock_exec,
            patch(PATCH_CUBO, return_value=MagicMock()),
            patch(PATCH_SERIALIZE, return_value={"cubo": {}}),
            patch(PATCH_RENDER_MD, return_value=""),
            patch(PATCH_RENDER_PDF, return_value=b""),
            patch(PATCH_STORE, return_value=mock_store),
        ):
            result = runner.invoke(
                app,
                [
                    "AGIS",
                    "--campaign",
                    str(campaign_file),
                    "--config",
                    str(tmp_path / "config"),
                    "--projects",
                    str(tmp_path / "projetos"),
                    "--workers",
                    "8",
                ],
            )

        assert result.exit_code == 0, result.output
        call_kwargs = mock_exec.call_args
        assert call_kwargs.kwargs.get("num_workers") == 8 or (len(call_kwargs.args) >= 4 and call_kwargs.args[3] == 8)
