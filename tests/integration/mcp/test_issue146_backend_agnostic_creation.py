"""Regressão issue #146 / migração ADR-047: `iniciar_orcamento` (MCP) cria e roda
um projeto de ponta a ponta sobre um backend não-filesystem (BlobStoragePort),
não sobre o filesystem local do container.

Antes da Fase 3, `mcp/_context.py::_project()`/`mcp/tools/projeto.py::iniciar_orcamento`
construíam `ProjectStore` diretamente, ignorando `CONCILIUM__STORE_BACKEND` — todo
projeto criado via Claude Desktop ficava em disco local (efêmero no container ACA),
nunca chegando ao SharePoint configurado. Antes da Fase 1, mesmo se a tool
respeitasse o backend, `StorageProjectHandle.escopo()`/`.snapshots` eram stubs —
a skill 01 quebraria com AttributeError na primeira execução.

Este teste usa `FakeBlobStorage` (não SharePoint real) porque a parte específica
do SharePoint (chamadas Graph API) já é testada em `test_adr047_sharepoint.py`;
o que importa aqui é que a MESMA implementação (`StorageProjectRepository` +
`StorageEscopoHandle`/`StoragePlanoHandle`) usada por sharepoint/s3/azure/gdrive
funciona de ponta a ponta a partir do ponto de entrada real do MCP.
"""

from __future__ import annotations

from unittest.mock import patch

import pytest
from mcp.server.fastmcp import FastMCP

from concilium.application.orchestrators.lifecycle_coordinator import LifecycleCoordinator
from concilium.application.runtime import Runtime
from concilium.infrastructure.storage.storage_project_repository import StorageProjectRepository
from concilium.presentation.mcp.tools import projeto as projeto_tools
from tests.support.fake_blob_storage import FakeBlobStorage


def _get_tools(server: FastMCP) -> dict:
    return {name: tool.fn for name, tool in server._tool_manager._tools.items()}


@pytest.fixture
def iniciar_orcamento(config_root):
    server = FastMCP("test-issue146")
    projeto_tools.register(server)
    tool = _get_tools(server)["iniciar_orcamento"]

    storage = FakeBlobStorage()
    repo = StorageProjectRepository(storage=storage)
    rt = Runtime(config_root)
    coord = LifecycleCoordinator(rt)

    with (
        patch("concilium.presentation.mcp.tools.projeto._project_repository", return_value=repo),
        patch("concilium.presentation.mcp.tools.projeto._runtime", return_value=rt),
        patch("concilium.presentation.mcp.tools.projeto._lifecycle_coordinator", return_value=coord),
    ):
        yield tool, storage, repo


def test_iniciar_orcamento_creates_and_runs_skill01_on_blob_backend(iniciar_orcamento):
    tool, storage, repo = iniciar_orcamento

    result = tool(
        nome="Terraplenagem Aracoiaba — issue146",
        contexto_id="test",
        tipo_obra="terraplenagem",
        localizacao="Aracoiaba, CE",
        coordenadas_lat=-4.3622,
        coordenadas_lng=-38.7392,
        data_inicio="2026-06-01",
        data_termino="2026-12-31",
        eap=[
            {
                "item_id": "eap-01",
                "ordem": 1,
                "cpu_id": "ESCO-CARGA-1CAT-DMT2000",
                "descricao": "Escavação 1ª categoria",
                "unidade": "m3",
                "quantitativo": 80000,
            }
        ],
    )

    assert "erro" not in result, result
    assert result["skills_executadas"][0]["status"] == "OK"
    project_id = result["project_id"]

    # A prova real: o projeto/escopo/plano existem no BlobStoragePort injetado
    # (não em filesystem local) — a mesma verificação que "concilium ops blob
    # status" faz em produção contra o SharePoint real.
    handle = repo.get_project(project_id)
    assert storage.blob_existe(f"projetos/{project_id}/meta.json")

    es = handle.escopo(result["escopo_id"])
    assert es.meta["escopo_id"] == result["escopo_id"]
    ps = es.plan(result["plano_id"])
    assert ps.load_canonical() is not None
