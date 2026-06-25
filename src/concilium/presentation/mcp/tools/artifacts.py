"""ADR-093: Ferramentas MCP de artefatos — listar, ler texto, baixar binário e bundle zip.

Expõem os entregáveis do pipeline (relatórios, memoriais, planilhas, gráficos)
de forma programática para agentes LLM e stakeholders remotos, sem exigir acesso
ao filesystem local. Cada artefato é classificado por audiência
(``agente`` | ``humano`` | ``ambos``).
"""

from __future__ import annotations

from typing import Any

from mcp.server.fastmcp import FastMCP

from concilium.application.services.artifact import artifact_bundle as ab
from concilium.infrastructure.auth.permission_guard import permission
from concilium.presentation.mcp._context import _project, _wrap_response


def register(server: FastMCP) -> None:
    """Registra as ferramentas de artefatos no servidor MCP."""

    @server.tool()
    @permission("artifacts:read")
    def listar_artefatos_projeto(project_id: str, versao: str | None = None) -> dict[str, Any]:
        """Lista os artefatos disponíveis de um projeto com nome, tipo, tamanho e audiência.

        ``audiencia`` indica o que processar (``agente`` = narrativa/dados textuais),
        o que é para humanos (``humano`` = planilhas, gráficos, PDFs) ou ``ambos``.
        Use ``versao`` para uma versão específica; omita para a versão atual.
        """
        store = _project(project_id)
        return _wrap_response(ab.list_artifacts(store, versao))

    @server.tool()
    @permission("artifacts:download")
    def obter_artefato(
        project_id: str,
        formato: str = "texto",
        nome_arquivo: str | None = None,
        versao: str | None = None,
        filtro: list[str] | None = None,
    ) -> dict[str, Any]:
        """Obtém um artefato do projeto em três formatos.

        formatos disponíveis:
        - texto: conteúdo de artefato textual (md, json, csv, txt) como string. Requer nome_arquivo.
        - binario: artefato binário (PNG, XLSX, PDF) como base64. Requer nome_arquivo.
        - bundle: todos os entregáveis empacotados em zip (base64) com MANIFESTO.md.
          filtro opcional restringe por audiência (["humano"], ["agente"]) ou nomes de arquivo.

        Args:
            project_id: ID do projeto.
            formato: "texto" | "binario" | "bundle" (padrão: "texto").
            nome_arquivo: Nome do arquivo — obrigatório para texto e binario.
            versao: Versão específica; omita para versão atual.
            filtro: Só usado em bundle — filtra por audiência ou nome.
        """
        store = _project(project_id)
        try:
            if formato == "texto":
                if not nome_arquivo:
                    return _wrap_response({"erro": "formato='texto' requer nome_arquivo"})
                return _wrap_response(ab.read_text(store, versao, nome_arquivo))
            elif formato == "binario":
                if not nome_arquivo:
                    return _wrap_response({"erro": "formato='binario' requer nome_arquivo"})
                return _wrap_response(ab.read_binary_b64(store, versao, nome_arquivo))
            elif formato == "bundle":
                return _wrap_response(ab.build_bundle(store, versao, filtro))
            else:
                return _wrap_response({"erro": f"formato '{formato}' inválido. Use: texto | binario | bundle"})
        except (FileNotFoundError, ValueError) as e:
            return _wrap_response({"erro": str(e), "project_id": project_id})
