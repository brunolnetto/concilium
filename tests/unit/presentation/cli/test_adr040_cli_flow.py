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
    """Copia config/ uma única vez por sessão (evita copytree 3×).

    PERFORMANCE: Ignora arquivos grandes (referencias/, xlsx, zip, 7z) e usa
    dirs_exist_ok para evitar falhas em reruns. Leva ~1-2s na primeira execução.
    """
    global _SHARED_CONFIG
    repo_root = Path(__file__).resolve().parents[4]
    src_config = repo_root / "config"
    cfg = tmp_path_factory.mktemp("adr040_config", numbered=False)
    # Ignora pastas e arquivos pesados que não são necessários para testes unitários
    IGNORE = shutil.ignore_patterns(
        "referencias", "*.7z", "*.xlsx", "*.zip", "*.pdf", "catalogos/mendeslobo", "__pycache__"
    )
    shutil.copytree(src_config, cfg / "config", ignore=IGNORE, dirs_exist_ok=True)
    return cfg / "config"


@pytest.fixture
def adr040_env(tmp_path: Path, monkeypatch, _adr040_shared_config: Path) -> dict[str, Path]:
    # Usa a cópia compartilhada da sessão para o config (evita copytree repetido)
    cfg = _adr040_shared_config

    projects = tmp_path / "projetos"
    projects.mkdir()

    monkeypatch.setenv("CONCILIUM__CONFIG_ROOT", str(cfg))
    monkeypatch.setenv("CONCILIUM__PROJECTS_ROOT", str(projects))
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
    """ADR-150: promote agora passa pelo core gated (quatro-olhos + SCD2 real +
    CatalogSnapshot), não mais pela reimplementação manual de histórico via
    `--insumo`/`_write_json` direto — por isso o override é gravado com a mesma
    chave composta `codigo::BASE` usada por `atualizar_preco_insumo`, e quem
    "editou" (rascunho de projeto) precisa ser diferente de `--actor` (regra
    dos quatro-olhos)."""
    from concilium.application.orchestrators.catalog_draft_lifecycle import rascunho_projeto_file_path
    from concilium.application.orchestrators.catalog_governance import validate_and_resolve_insumo_file

    config_root = adr040_env["config"]
    projects_root = adr040_env["projects"]

    contexto_id, insumo_id = _first_master_insumo(config_root)
    project = ProjectStore.init(projects_root, "adr040-promote", "test")
    project.update_meta(contexto_id=contexto_id)
    project_id = project.root.name

    override_path = project.root / "overrides" / "insumos_override.json"
    override_payload = {
        f"{insumo_id}::BASE": {
            "preco_calibrado": 9.5,
            "motivo": "Calibracao de campo",
        }
    }
    override_path.write_text(json.dumps(override_payload, indent=2, ensure_ascii=False), encoding="utf-8")
    # Simula que o override foi editado por outra pessoa antes da promoção
    # (regra dos quatro-olhos, ADR-150 D2) — sem isso, a state machine trataria
    # o próprio --actor da promoção como "criador" (rascunho implícito).
    estado_path = rascunho_projeto_file_path(projects_root, project_id)
    estado_path.write_text(
        json.dumps({"_rascunho": True, "created_by": "engenheiro-campo", "projeto_id": project_id}),
        encoding="utf-8",
    )

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
                "--justificativa",
                "Virou preco de mercado",
                "--actor",
                "gestor-catalogo",
                "--force",
            ],
        )
        assert result.exit_code == 0, result.stdout

        updated = json.loads(insumo_file.read_text(encoding="utf-8"))
        assert float(updated.get("preco_unitario", 0.0)) == pytest.approx(9.5)
        historico = updated.get("historico_precos", [])
        assert isinstance(historico, list) and len(historico) >= 1
        assert float(historico[-1].get("preco_unitario", 0.0)) == pytest.approx(9.5)

        # Overrides aplicados são arquivados e o arquivo live esvaziado (ADR-040 D4)
        override_after = json.loads(override_path.read_text(encoding="utf-8"))
        assert override_after == {}
        historico_dir = project.root / "overrides" / "historico"
        arquivados = list(historico_dir.glob("insumos_override_*.json"))
        assert arquivados
        arquivo = json.loads(arquivados[0].read_text(encoding="utf-8"))
        assert f"{insumo_id}::BASE" in arquivo

        # Rascunho de projeto vira estado terminal APROVADO
        estado_final = json.loads(estado_path.read_text(encoding="utf-8"))
        assert estado_final.get("_aprovado") is True
        assert estado_final.get("_aprovado_por") == "gestor-catalogo"

        # CatalogSnapshot real gerado (ADR-024/145), não mais um promotions.jsonl ad hoc
        snapshots_dir = catalog_root / "snapshots"
        assert snapshots_dir.exists() and list(snapshots_dir.glob("*.json"))
    finally:
        insumo_file.write_text(json.dumps(original, indent=2, ensure_ascii=False), encoding="utf-8")
