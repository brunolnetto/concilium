"""ADR-093: Ferramentas MCP de artefatos — listar, ler texto, baixar binário e bundle zip.

Expõem os entregáveis do pipeline (relatórios, memoriais, planilhas, gráficos)
de forma programática para agentes LLM e stakeholders remotos, sem exigir acesso
ao filesystem local. Cada artefato é classificado por audiência
(``agente`` | ``humano`` | ``ambos``).
"""

from __future__ import annotations

from typing import Any

from mcp.server.fastmcp import FastMCP

from concilium.application.services import artifact_bundle as ab
from concilium.presentation.mcp_server._context import _project, _wrap_response


def register(server: FastMCP) -> None:
    """Registra as ferramentas de artefatos no servidor MCP."""

    @server.tool()
    def listar_artefatos_projeto(project_id: str, versao: str | None = None) -> dict[str, Any]:
        """Lista os artefatos disponíveis de um projeto com nome, tipo, tamanho e audiência.

        ``audiencia`` indica o que processar (``agente`` = narrativa/dados textuais),
        o que é para humanos (``humano`` = planilhas, gráficos, PDFs) ou ``ambos``.
        Use ``versao`` para uma versão específica; omita para a versão atual.
        """
        store = _project(project_id)
        return _wrap_response(ab.list_artifacts(store, versao))

    @server.tool()
    def ler_artefato_texto(
        project_id: str, nome_arquivo: str, versao: str | None = None
    ) -> dict[str, Any]:
        """Retorna o conteúdo de um artefato textual (md, json, csv, txt) como string.

        Para binários (PNG, XLSX, PDF) use ``baixar_artefato_binario``.
        """
        store = _project(project_id)
        try:
            return _wrap_response(ab.read_text(store, versao, nome_arquivo))
        except (FileNotFoundError, ValueError) as e:
            return _wrap_response({"erro": str(e), "nome": nome_arquivo})

    @server.tool()
    def baixar_artefato_binario(
        project_id: str, nome_arquivo: str, versao: str | None = None
    ) -> dict[str, Any]:
        """Retorna um artefato binário (PNG, XLSX, PDF) como base64.

        Arquivos abaixo de 10 MB vêm inline em ``conteudo_base64``; acima disso,
        retorna o caminho (em produção Azure, uma URL pré-assinada — ADR-096).
        """
        store = _project(project_id)
        try:
            return _wrap_response(ab.read_binary_b64(store, versao, nome_arquivo))
        except (FileNotFoundError, ValueError) as e:
            return _wrap_response({"erro": str(e), "nome": nome_arquivo})

    @server.tool()
    def baixar_bundle_zip(
        project_id: str, versao: str | None = None, filtro: list[str] | None = None
    ) -> dict[str, Any]:
        """Empacota os entregáveis do projeto em um zip (base64) com MANIFESTO.md.

        ``filtro`` opcional restringe por audiência (``["humano"]``, ``["agente"]``)
        ou por nomes de arquivo específicos. PNGs são organizados sob ``graficos/``.
        """
        store = _project(project_id)
        try:
            return _wrap_response(ab.build_bundle(store, versao, filtro))
        except (FileNotFoundError, ValueError) as e:
            return _wrap_response({"erro": str(e), "project_id": project_id})
