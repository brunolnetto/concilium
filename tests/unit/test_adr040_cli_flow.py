from __future__ import annotations

import json
import shutil
from pathlib import Path

import pytest
from typer.testing import CliRunner

from concilium.application.runtime import Runtime
from concilium.infrastructure.storage.project import ProjectStore
from concilium.presentation.main import app

runner = CliRunner()


_SHARED_CONFIG: Path | None = None


@pytest.fixture(scope="session")
def _adr040_shared_config(tmp_path_factory: pytest.TempPathFactory) -> Path:
    """Copia config/ uma única vez por sessão (evita copytree 3×)."""
    global _SHARED_CONFIG
    repo_root = Path(__file__).resolve().parents[2]
    src_config = repo_root / "config"
    cfg = tmp_path_factory.mktemp("adr040_config", numbered=False)
    IGNORE = shutil.ignore_patterns("referencias", "*.7z", "*.xlsx", "*.zip")
    shutil.copytree(src_config, cfg / "config", ignore=IGNORE)
    return cfg / "config"


@pytest.fixture
def adr040_env(tmp_path: Path, monkeypatch, _adr040_shared_config: Path) -> dict[str, Path]:
    # Usa a cópia compartilhada da sessão para o config (evita copytree repetido)
    cfg = _adr040_shared_config

    projects = tmp_path / "projetos"
    projects.mkdir()

    monkeypatch.setenv("CONCILIUM_CONFIG_ROOT", str(cfg))
    monkeypatch.setenv("CONCILIUM_PROJECTS_ROOT", str(projects))
    return {"config": cfg, "projects": projects}


def _first_master_insumo(config_root: Path) -> tuple[str, str]:
    rt = Runtime(config_root)
    contextos_dir = config_root / "contextos"
    for ctx_file in sorted(contextos_dir.glob("*.json")):
        contexto_id = ctx_file.stem
        ctx = rt.load_contexto(contexto_id)
        catalogo = rt.load_catalogo(ctx.catalogo_id)
        for item in catalogo.get("insumos", []):
            if not isinstance(item, dict) or not item.get("codigo"):
                continue
            return contexto_id, str(item["codigo"])
    raise AssertionError("Nenhum contexto com insumo disponível foi encontrado")


@pytest.mark.slow
def test_survey_requires_project_by_default(adr040_env: dict[str, Path]) -> None:
    result = runner.invoke(app, ["catalog", "survey", "--contexto", "test", "--type", "price"])
    assert result.exit_code == 1
    assert "--project" in result.stdout


def test_survey_project_writes_in_project_layer_with_audit(adr040_env: dict[str, Path], monkeypatch) -> None:
    import concilium.infrastructure.exporters.price_survey as price_survey_mod

    class DummyPriceSurveyExporter:
        def __init__(self, catalogo, jurisdicao_id=None):
            self.catalogo = catalogo
            self.jurisdicao_id = jurisdicao_id

        def export(self, output_path: Path) -> None:
            output_path.write_bytes(b"xlsx-mock")

    monkeypatch.setattr(price_survey_mod, "PriceSurveyExporter", DummyPriceSurveyExporter)

    projects_root = adr040_env["projects"]
    project = ProjectStore.init(projects_root, "adr040-survey", "test")
    project_id = project.root.name

    result = runner.invoke(
        app,
        [
            "catalog",
            "survey",
            "--contexto",
            "test",
            "--type",
            "price",
            "--project",
            project_id,
        ],
    )
    assert result.exit_code == 0, result.stdout

    generated = project.root / "overrides" / "surveys" / "pesquisa_price_test.xlsx"
    assert generated.exists()

    audit_log = project.root / "audit_log.jsonl"
    assert audit_log.exists()
    lines = [json.loads(line) for line in audit_log.read_text(encoding="utf-8").splitlines() if line.strip()]
    assert any(row.get("action") == "catalog_survey_export" for row in lines)


def test_promote_moves_project_override_to_master_with_history(adr040_env: dict[str, Path]) -> None:
    from concilium.application.orchestrators.catalog_governance import validate_and_resolve_insumo_file

    config_root = adr040_env["config"]
    projects_root = adr040_env["projects"]

    contexto_id, insumo_id = _first_master_insumo(config_root)
    project = ProjectStore.init(projects_root, "adr040-promote", "test")
    project.update_meta(contexto_id=contexto_id)
    project_id = project.root.name

    override_path = project.root / "overrides" / "insumos_override.json"
    override_payload = {
        insumo_id: {
            "preco_calibrado": 9.5,
            "motivo": "Calibracao de campo",
        }
    }
    override_path.write_text(json.dumps(override_payload, indent=2, ensure_ascii=False), encoding="utf-8")

    rt = Runtime(config_root)
    ctx = rt.load_contexto(contexto_id)
    catalog_root = config_root / "catalogos" / ctx.catalogo_id
    insumo_file = validate_and_resolve_insumo_file(catalog_root, insumo_id, 1.0)
    original = json.loads(insumo_file.read_text(encoding="utf-8"))
    if original.get("preco_unitario") is None:
        original["preco_unitario"] = 1.0
        insumo_file.write_text(json.dumps(original, indent=2, ensure_ascii=False), encoding="utf-8")

    try:
        result = runner.invoke(
            app,
            [
                "catalog",
                "promote",
                "--project",
                project_id,
                "--insumo",
                insumo_id,
                "--justificativa",
                "Virou preco de mercado",
                "--force",
            ],
        )
        assert result.exit_code == 0, result.stdout

        updated = json.loads(insumo_file.read_text(encoding="utf-8"))
        assert float(updated.get("preco_unitario", 0.0)) == pytest.approx(9.5)
        historico = updated.get("historico_precos", [])
        assert isinstance(historico, list) and len(historico) >= 1
        assert float(historico[-1].get("preco_unitario", 0.0)) == pytest.approx(9.5)

        override_after = json.loads(override_path.read_text(encoding="utf-8"))
        assert insumo_id not in override_after

        promotions_log = project.root / "overrides" / "historico" / "promotions.jsonl"
        assert promotions_log.exists()
        rows = [json.loads(line) for line in promotions_log.read_text(encoding="utf-8").splitlines() if line.strip()]
        assert any(row.get("insumo_id") == insumo_id for row in rows)

        audit_log = project.root / "audit_log.jsonl"
        assert audit_log.exists()
        audit_rows = [json.loads(line) for line in audit_log.read_text(encoding="utf-8").splitlines() if line.strip()]
        assert any(row.get("action") == "catalog_promote_insumo" for row in audit_rows)
    finally:
        insumo_file.write_text(json.dumps(original, indent=2, ensure_ascii=False), encoding="utf-8")
