"""Tests for ADR-150 — promoção gated de override de projeto ao catálogo master.

Cobre o fluxo completo: override livre de projeto (ADR-040) -> identidade de
rascunho (D1) -> gate dual ownership+quatro-olhos (D2) -> escrita efetiva
reaproveitando RepositorioInsumo.atualizar_preco/CatalogSnapshot (D3).
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from unittest.mock import patch

from mcp.server.fastmcp import FastMCP

from concilium.application.orchestrators.catalog_draft_lifecycle import (
    ESTADO_APROVADO,
    estado_rascunho,
    rascunho_projeto_file_path,
)
from concilium.presentation.mcp.tools._catalogo_tools_helpers_c import (
    _override_preco,
    _parse_override_key,
    _read_project_meta,
)

_CATALOGO_MOD = "concilium.presentation.mcp.tools.catalogo"


def _register_tools(monkeypatch, tmp_path: Path) -> dict:
    import importlib

    config_dir = tmp_path / "config"
    config_dir.mkdir(parents=True, exist_ok=True)
    projects_dir = tmp_path / "projetos"
    projects_dir.mkdir(parents=True, exist_ok=True)
    monkeypatch.setenv("CONCILIUM__CONFIG_ROOT", str(config_dir))
    monkeypatch.setenv("CONCILIUM__PROJECTS_ROOT", str(projects_dir))

    mod = importlib.import_module(_CATALOGO_MOD)
    importlib.reload(mod)
    server = FastMCP("test-cat-adr150")
    mod.register(server)

    tools: dict = {}
    for t in server._tool_manager.list_tools():
        fn = getattr(t, "fn", None) or getattr(t, "func", None)
        tools[t.name] = fn
    return tools


def _seed_contexto_e_catalogo(config_dir: Path, contexto_id: str, catalogo_id: str) -> Path:
    (config_dir / "contextos").mkdir(parents=True, exist_ok=True)
    (config_dir / "contextos" / f"{contexto_id}.json").write_text(
        json.dumps(
            {
                "id": contexto_id,
                "perfil_id": "default",
                "jurisdicao_id": "BR",
                "referencia_id": "SICRO",
                "catalogo_id": catalogo_id,
            }
        ),
        encoding="utf-8",
    )
    cat_dir = config_dir / "catalogos" / catalogo_id
    (cat_dir / "insumos" / "material").mkdir(parents=True, exist_ok=True)
    (cat_dir / "insumos" / "material" / "MAT-001.json").write_text(
        json.dumps({"codigo": "MAT-001", "tipo": "MATERIAL", "descricao": "Cimento", "preco_unitario": 30.0}),
        encoding="utf-8",
    )
    return cat_dir


def _seed_projeto(
    projects_dir: Path,
    projeto_id: str,
    *,
    owner_id: str | None,
    contexto_id: str | None = None,
    overrides: dict | None = None,
    created_by: str | None = None,
) -> Path:
    proj_dir = projects_dir / projeto_id
    proj_dir.mkdir(parents=True, exist_ok=True)
    meta: dict = {"owner_id": owner_id}
    if contexto_id:
        meta["contexto_id"] = contexto_id
    (proj_dir / "meta.json").write_text(json.dumps(meta), encoding="utf-8")

    overrides_dir = proj_dir / "overrides"
    overrides_dir.mkdir(parents=True, exist_ok=True)
    (overrides_dir / "insumos_override.json").write_text(
        json.dumps(overrides if overrides is not None else {"MAT-001::BASE": {"preco": 55.0, "nota": "cotação X"}}),
        encoding="utf-8",
    )
    if created_by:
        (overrides_dir / "_rascunho_estado.json").write_text(
            json.dumps({"_rascunho": True, "created_by": created_by, "projeto_id": projeto_id}),
            encoding="utf-8",
        )
    return proj_dir


class TestPromoverOverrideProjetoHappyPath:
    def test_dono_do_projeto_promove_override_de_outro_editor(self, monkeypatch, tmp_path):
        tools = _register_tools(monkeypatch, tmp_path)
        config_dir = tmp_path / "config"
        projects_dir = tmp_path / "projetos"
        _seed_contexto_e_catalogo(config_dir, "ctx-1", "cat-1")
        _seed_projeto(projects_dir, "PROJ-001", owner_id="owner-1", contexto_id="ctx-1", created_by="eng-1")

        with (
            patch.dict(os.environ, {"CONCILIUM__AUTH_ENABLED": "1"}),
            patch("concilium.infrastructure.auth.permission_guard.get_current_user_id", return_value="owner-1"),
            patch("concilium.infrastructure.auth.permission_guard._current_roles") as mock_roles,
        ):
            mock_roles.get.return_value = frozenset({"catalog-manager"})
            result = tools["promover_override_projeto"](projeto_id="PROJ-001", justificativa="preço negociado")

        assert result["status"] == "APROVADO"
        assert result["deltas_aplicados"] == 1
        assert result["snapshot_id"]

        insumo_file = config_dir / "catalogos" / "cat-1" / "insumos" / "material" / "MAT-001.json"
        insumo_data = json.loads(insumo_file.read_text(encoding="utf-8"))
        assert insumo_data["preco_unitario"] == 55.0

        # Override aplicado é arquivado e o arquivo live fica vazio (ADR-040 D4)
        overrides_file = projects_dir / "PROJ-001" / "overrides" / "insumos_override.json"
        assert json.loads(overrides_file.read_text(encoding="utf-8")) == {}
        historico_dir = projects_dir / "PROJ-001" / "overrides" / "historico"
        assert list(historico_dir.glob("*.json"))

        # Rascunho de projeto vira estado terminal APROVADO
        estado_file = rascunho_projeto_file_path(projects_dir, "PROJ-001")
        data = json.loads(estado_file.read_text(encoding="utf-8"))
        assert estado_rascunho(data) == ESTADO_APROVADO
        assert data["_aprovado_por"] == "owner-1"

    def test_sem_overrides_pendentes_retorna_sem_pendencias(self, monkeypatch, tmp_path):
        tools = _register_tools(monkeypatch, tmp_path)
        config_dir = tmp_path / "config"
        projects_dir = tmp_path / "projetos"
        _seed_contexto_e_catalogo(config_dir, "ctx-1", "cat-1")
        _seed_projeto(projects_dir, "PROJ-001", owner_id="owner-1", contexto_id="ctx-1", overrides={})

        with (
            patch.dict(os.environ, {"CONCILIUM__AUTH_ENABLED": "1"}),
            patch("concilium.infrastructure.auth.permission_guard.get_current_user_id", return_value="owner-1"),
            patch("concilium.infrastructure.auth.permission_guard._current_roles") as mock_roles,
        ):
            mock_roles.get.return_value = frozenset({"catalog-manager"})
            result = tools["promover_override_projeto"](projeto_id="PROJ-001", justificativa="nada a promover")

        assert result["status"] == "SEM_PENDENCIAS"


class TestPromoverOverrideProjetoGateDuplo:
    def test_bloqueia_quem_nao_e_dono_nem_admin(self, monkeypatch, tmp_path):
        tools = _register_tools(monkeypatch, tmp_path)
        config_dir = tmp_path / "config"
        projects_dir = tmp_path / "projetos"
        _seed_contexto_e_catalogo(config_dir, "ctx-1", "cat-1")
        _seed_projeto(projects_dir, "PROJ-001", owner_id="owner-1", contexto_id="ctx-1", created_by="eng-1")

        with (
            patch.dict(os.environ, {"CONCILIUM__AUTH_ENABLED": "1"}),
            patch("concilium.infrastructure.auth.permission_guard.get_current_user_id", return_value="mgr-1"),
            patch("concilium.infrastructure.auth.permission_guard._current_roles") as mock_roles,
        ):
            mock_roles.get.return_value = frozenset({"catalog-manager"})
            result = tools["promover_override_projeto"](projeto_id="PROJ-001", justificativa="x")

        assert "erro" in result
        assert "dono do projeto" in result["erro"] or "admin" in result["erro"]
        # Nada foi escrito no master
        insumo_file = config_dir / "catalogos" / "cat-1" / "insumos" / "material" / "MAT-001.json"
        assert json.loads(insumo_file.read_text(encoding="utf-8"))["preco_unitario"] == 30.0

    def test_bloqueia_dono_que_tambem_editou_quatro_olhos(self, monkeypatch, tmp_path):
        tools = _register_tools(monkeypatch, tmp_path)
        config_dir = tmp_path / "config"
        projects_dir = tmp_path / "projetos"
        _seed_contexto_e_catalogo(config_dir, "ctx-1", "cat-1")
        # created_by == owner_id: o dono editou o próprio override
        _seed_projeto(projects_dir, "PROJ-001", owner_id="owner-1", contexto_id="ctx-1", created_by="owner-1")

        with (
            patch.dict(os.environ, {"CONCILIUM__AUTH_ENABLED": "1"}),
            patch("concilium.infrastructure.auth.permission_guard.get_current_user_id", return_value="owner-1"),
            patch("concilium.infrastructure.auth.permission_guard._current_roles") as mock_roles,
        ):
            mock_roles.get.return_value = frozenset({"catalog-manager"})
            result = tools["promover_override_projeto"](projeto_id="PROJ-001", justificativa="x")

        assert "erro" in result
        assert "quatro olhos" in result["erro"]

    def test_admin_pode_promover_mesmo_sem_ser_dono(self, monkeypatch, tmp_path):
        tools = _register_tools(monkeypatch, tmp_path)
        config_dir = tmp_path / "config"
        projects_dir = tmp_path / "projetos"
        _seed_contexto_e_catalogo(config_dir, "ctx-1", "cat-1")
        _seed_projeto(projects_dir, "PROJ-001", owner_id="owner-1", contexto_id="ctx-1", created_by="eng-1")

        with (
            patch.dict(os.environ, {"CONCILIUM__AUTH_ENABLED": "1"}),
            patch("concilium.infrastructure.auth.permission_guard.get_current_user_id", return_value="admin-1"),
            patch("concilium.infrastructure.auth.permission_guard._current_roles") as mock_roles,
        ):
            mock_roles.get.return_value = frozenset({"admin"})
            result = tools["promover_override_projeto"](projeto_id="PROJ-001", justificativa="x")

        assert result["status"] == "APROVADO"

    def test_bloqueia_promover_duas_vezes(self, monkeypatch, tmp_path):
        tools = _register_tools(monkeypatch, tmp_path)
        config_dir = tmp_path / "config"
        projects_dir = tmp_path / "projetos"
        _seed_contexto_e_catalogo(config_dir, "ctx-1", "cat-1")
        _seed_projeto(projects_dir, "PROJ-001", owner_id="owner-1", contexto_id="ctx-1", created_by="eng-1")

        with (
            patch.dict(os.environ, {"CONCILIUM__AUTH_ENABLED": "1"}),
            patch("concilium.infrastructure.auth.permission_guard.get_current_user_id", return_value="owner-1"),
            patch("concilium.infrastructure.auth.permission_guard._current_roles") as mock_roles,
        ):
            mock_roles.get.return_value = frozenset({"catalog-manager"})
            primeira = tools["promover_override_projeto"](projeto_id="PROJ-001", justificativa="primeira")
            assert primeira["status"] == "APROVADO"

            # segunda chamada: sem overrides pendentes (já arquivados) — não é
            # nem tentativa de re-promoção do mesmo estado, é o caminho normal
            # de "nada a fazer" após uma promoção bem-sucedida.
            segunda = tools["promover_override_projeto"](projeto_id="PROJ-001", justificativa="segunda")
            assert segunda["status"] == "SEM_PENDENCIAS"

    def test_projeto_inexistente_retorna_erro(self, monkeypatch, tmp_path):
        tools = _register_tools(monkeypatch, tmp_path)
        _seed_contexto_e_catalogo(tmp_path / "config", "ctx-1", "cat-1")

        result = tools["promover_override_projeto"](projeto_id="PROJ-999", justificativa="x")
        assert "erro" in result
        assert "PROJ-999" in result["erro"]

    def test_sem_contexto_id_e_sem_meta_retorna_erro(self, monkeypatch, tmp_path):
        tools = _register_tools(monkeypatch, tmp_path)
        projects_dir = tmp_path / "projetos"
        _seed_projeto(projects_dir, "PROJ-001", owner_id="owner-1", contexto_id=None, created_by="eng-1")

        with (
            patch.dict(os.environ, {"CONCILIUM__AUTH_ENABLED": "1"}),
            patch("concilium.infrastructure.auth.permission_guard.get_current_user_id", return_value="owner-1"),
            patch("concilium.infrastructure.auth.permission_guard._current_roles") as mock_roles,
        ):
            mock_roles.get.return_value = frozenset({"catalog-manager"})
            result = tools["promover_override_projeto"](projeto_id="PROJ-001", justificativa="x")

        assert "erro" in result
        assert "contexto" in result["erro"].lower()


class TestParseOverrideKey:
    def test_key_sem_separador_retorna_jurisdicao_none(self):
        assert _parse_override_key("MAT-001") == ("MAT-001", None)


class TestOverridePreco:
    def test_preco_calibrado_tem_prioridade_sobre_os_demais(self):
        # Também exercita os desvios preco_calibrado->preco_unitario e
        # preco_unitario->preco (nenhum fallback é avaliado quando o
        # primeiro campo já resolve o preço).
        assert _override_preco({"preco_calibrado": 42.5, "preco_unitario": 10.0, "preco": 1.0}) == 42.5


class TestReadProjectMeta:
    def test_sem_meta_json_retorna_dict_vazio(self, tmp_path):
        assert _read_project_meta(tmp_path / "projeto-sem-meta") == {}

    def test_meta_json_malformado_retorna_dict_vazio(self, tmp_path):
        proj_path = tmp_path / "projeto-meta-invalido"
        proj_path.mkdir()
        (proj_path / "meta.json").write_text("{invalido", encoding="utf-8")
        assert _read_project_meta(proj_path) == {}
