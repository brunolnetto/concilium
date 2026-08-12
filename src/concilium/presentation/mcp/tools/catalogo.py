"""Ferramentas MCP de Catálogo — Simplificadas (ADR-037)."""

from __future__ import annotations

import asyncio
import functools
from collections.abc import Callable
from pathlib import Path
from types import FunctionType
from typing import Any

from mcp.server.fastmcp import FastMCP

from concilium.infrastructure.auth.permission_guard import permission
from concilium.presentation.mcp._context import TOOL_IO_TIMEOUT_S, _wrap_response
from concilium.presentation.mcp.rate_limit import mcp_rate_limit

from ._catalogo_tools_helpers_a import (
    MAX_LOTE_INSUMOS,
    _impl_adicionar_variante_producao,
    _impl_atualizar_composicao_item_cpu,
    _impl_atualizar_preco_insumo,
    _impl_atualizar_precos_insumos_lote,
    _impl_consultar_preco_insumo_temporal,
    _impl_consultar_saude_catalogo,
    _impl_criar_insumo,
    _impl_criar_insumos_lote,
    _impl_descontinuar_insumo,
    _impl_descontinuar_insumos_lote,
    _impl_listar_contextos,
    _impl_listar_insumos,
    _impl_pesquisar_catalogo,
)
from ._catalogo_tools_helpers_b import (
    _impl_avaliar_plausibilidade_catalogo,
    _impl_calcular_pu_producao,
    _impl_comparar_catalogo,
    _impl_mesclar_catalogo,
    _impl_tendencia_precos_catalogo,
    _impl_verificar_integridade_catalogo,
)


def _catalog_root(config_dir: Path, catalogo_id: str) -> Path:
    return config_dir / "catalogos" / catalogo_id


def _com_deadline_de_catalogo(tool_fn: FunctionType) -> Callable[..., Any]:
    """Decorator: tira uma tool de catálogo do event loop e aplica deadline de parede.

    2026-08-12: mesma classe de bug de #147/#148/#149/#153 (pesquisar_catalogo) —
    tools MCP síncronas rodam direto na coroutine do event loop (o SDK `mcp` não
    tira isso pra thread sozinho); com concilium-mcp de worker único, uma chamada
    travada (ex.: leitura de catálogo via SharePoint sob throttling) congela o
    event loop inteiro — inclusive chamadas novas de OUTRAS tools, mesmo leves
    (achado real: atualizar_composicao_item_cpu, sem bug próprio — reproduz em
    <1s local — travou 4min em produção porque outra chamada seguurava o loop).
    `asyncio.to_thread` tira a execução do loop; `wait_for` dá erro rápido em vez
    de hang silencioso quando o próprio trabalho demora demais.

    Aplicado direto sobre a função `def` original (que fica igual a antes de
    #147/#153 — sem duplicar a lista de parâmetros nem repetir o nome da tool
    como string solta): `functools.wraps` preserva nome/docstring/assinatura,
    e como o resultado aqui já nasce `async def`, compõe corretamente com
    `@permission`/`@mcp_rate_limit()` por cima (ambos async-aware — ver
    issue #148 e o fix equivalente em rate_limit.mcp_rate_limit).
    """
    tool_name = tool_fn.__name__

    @functools.wraps(tool_fn)
    async def wrapper(*args: Any, **kwargs: Any) -> dict[str, Any]:
        try:
            return await asyncio.wait_for(asyncio.to_thread(tool_fn, *args, **kwargs), timeout=TOOL_IO_TIMEOUT_S)
        except TimeoutError:
            return {
                "erro": (
                    f"{tool_name} excedeu {TOOL_IO_TIMEOUT_S:.0f}s. Pode ser catálogo grande com "
                    "cache frio (pós-deploy/restart) ou contenção com outra chamada em andamento — "
                    "tente novamente."
                )
            }

    return wrapper


def _marcar_rascunho_revisado(config_root: Path, contexto_id: str, rascunho_id: str, revisor: str) -> None:
    """RASCUNHO -> REVISADO (ADR-120 D5): no-op se o arquivo do rascunho não existir."""
    import json

    from concilium.application.orchestrators.catalog_draft_lifecycle import marcar_revisado

    rascunho_file = config_root / "contextos" / contexto_id / "versions" / f"{rascunho_id}.json"
    if not rascunho_file.exists():
        return
    data = json.loads(rascunho_file.read_text(encoding="utf-8"))
    data = marcar_revisado(data, revisor)
    rascunho_file.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def register(server: FastMCP) -> None:
    """Registra as ferramentas consolidadas de catálogo."""

    # ── Lookup / pesquisa ────────────────────────────────────────────────────

    @server.tool(
        description="Lista os contextos de catálogo disponíveis (ex: mendeslobo, test). "
        "Ponto de entrada para descobrir contexto_id."
    )
    @permission("catalog:read")
    @_com_deadline_de_catalogo
    def listar_contextos() -> dict[str, Any]:
        return _impl_listar_contextos()

    @server.tool(
        description="Busca CPUs por código ou descrição (ex: query='escavação 1ª cat'). "
        "Use para encontrar cpu_id antes de criar projeto."
    )
    @permission("catalog:read")
    @_com_deadline_de_catalogo
    def pesquisar_catalogo(
        contexto_id: str,
        query: str | None = None,
        tipo_obra: str | None = None,
        limite: int = 20,
    ) -> dict[str, Any]:
        # 2026-08-11: mesmo achado do incidente de ping() (issue #147/#148/#149) —
        # rt.load_catalogo() carrega o catálogo inteiro (ex.: "mendeslobo", 138 CPUs)
        # antes de filtrar; sem deadline, uma leitura fria (cache local expirado/
        # pós-deploy) pendura o tool até o timeout opaco de 60s do client.
        return _impl_pesquisar_catalogo(contexto_id, query, tipo_obra, limite)

    @server.tool(
        description=(
            "Lista/busca insumos (material, mão-de-obra, equipamento) por id, descrição e/ou tipo, paginado. "
            "Use para descobrir insumo_id antes de atualizar_preco_insumo/historico_preco_insumo, "
            "ou para identificar insumos citados em auditar_catalogo (ADR-163)."
        )
    )
    @permission("catalog:read")
    @_com_deadline_de_catalogo
    def listar_insumos(
        contexto_id: str,
        tipo: str | None = None,
        query: str | None = None,
        limite: int = 50,
        offset: int = 0,
        incluir_descontinuados: bool = False,
    ) -> dict[str, Any]:
        return _impl_listar_insumos(contexto_id, tipo, query, limite, offset, incluir_descontinuados)

    # ── Diagnóstico — use um de cada vez ────────────────────────────────────
    # consultar_saude_catalogo  → cobertura (quantos insumos têm preço, % CPUs calculáveis)
    # avaliar_plausibilidade_catalogo → valores fora de faixa (outliers, razões anômalas)
    # verificar_integridade_catalogo  → consistência referencial (insumos pendentes, ciclos, PUs)

    @server.tool(
        description=(
            "Auditoria do catálogo em três modos: "
            "'saude' — cobertura (% insumos com preço, % CPUs calculáveis); "
            "'plausibilidade' — outliers de preço e razões de produtividade anômalas; "
            "'integridade' — consistência referencial, ciclos e recálculo de PUs."
        )
    )
    @permission("catalog:validate")  # ADR-120 F2
    @_com_deadline_de_catalogo
    def auditar_catalogo(
        contexto_id: str,
        modo: str = "saude",
        alpha_clt: float = 1.777,
        alpha_pj: float = 1.06,
        preco_diesel: float = 6.50,
    ) -> dict[str, Any]:
        """Audita o catálogo de referência.

        modos disponíveis:
        - saude: cobertura — % insumos com preço, % CPUs calculáveis. Use antes de orçar.
        - plausibilidade: detecta outliers e razões de produtividade anômalas.
        - integridade: verifica insumos ausentes, ciclos e recalcula PUs com encargos/diesel.

        Args:
            contexto_id: ID do contexto do catálogo a auditar.
            modo: "saude" | "plausibilidade" | "integridade" (padrão: "saude").
            alpha_clt: Multiplicador CLT — só usado no modo "integridade".
            alpha_pj: Multiplicador PJ — só usado no modo "integridade".
            preco_diesel: Preço do diesel (R$/L) — só usado no modo "integridade".
        """
        if modo == "saude":
            return _impl_consultar_saude_catalogo(contexto_id)
        elif modo == "plausibilidade":
            return _impl_avaliar_plausibilidade_catalogo(contexto_id)
        elif modo == "integridade":
            return _impl_verificar_integridade_catalogo(contexto_id, alpha_clt, alpha_pj, preco_diesel)
        else:
            from concilium.presentation.mcp._context import _wrap_response

            return _wrap_response({"erro": f"modo '{modo}' inválido. Use: saude | plausibilidade | integridade"})

    # ── Mutação / atualização ────────────────────────────────────────────────

    @server.tool(
        description="Atualiza o preço, a locação mensal e/ou as funções aplicáveis de um insumo (ex: novo "
        "preço de diesel após cotação, custo de manutenção mensal de um equipamento, ou quais funções MAO_OBRA "
        "usam um EPI/treinamento específico). Informe ao menos um entre novo_preco, novo_valor_locacao_mensal "
        "e novos_funcoes_aplicaveis (ADR-163/165/166). "
        "Para editar o catálogo mestre, informe rascunho_id (criado via criar_rascunho_catalogo) — "
        "a mudança fica pendente até aprovar_merge_catalogo (ADR-145). "
        "Use projeto_id para override de projeto em vez de alterar o master."
    )
    @permission("catalog:write")
    @mcp_rate_limit()
    @_com_deadline_de_catalogo
    def atualizar_preco_insumo(
        contexto_id: str,
        insumo_id: str,
        novo_preco: float | None = None,
        rascunho_id: str | None = None,
        projeto_id: str | None = None,
        jurisdicao_id: str | None = None,
        nota: str | None = None,
        novo_valor_locacao_mensal: float | None = None,
        novos_funcoes_aplicaveis: list[str] | None = None,
    ) -> dict[str, Any]:
        return _impl_atualizar_preco_insumo(
            contexto_id,
            insumo_id,
            novo_preco,
            rascunho_id,
            projeto_id,
            jurisdicao_id,
            nota,
            novo_valor_locacao_mensal,
            novos_funcoes_aplicaveis,
        )

    @server.tool(
        description=(
            "Atualiza preço e/ou locação mensal de múltiplos insumos numa única chamada (ADR-164) — "
            "evita N chamadas individuais para atualizar N insumos. Só catálogo mestre (sem override de "
            f"projeto em lote), requer rascunho_id. Até {MAX_LOTE_INSUMOS} itens por chamada. "
            "Itens inválidos não abortam o lote — resposta reporta sucesso/erro por item."
        )
    )
    @permission("catalog:write")
    @mcp_rate_limit()
    @_com_deadline_de_catalogo
    def atualizar_precos_insumos_lote(
        contexto_id: str,
        rascunho_id: str,
        itens: list[dict[str, Any]],
    ) -> dict[str, Any]:
        return _impl_atualizar_precos_insumos_lote(contexto_id, rascunho_id, itens)

    @server.tool(
        description=(
            "Cria um insumo novo (material/mão-de-obra/equipamento) no catálogo mestre. "
            "Requer rascunho_id (criado via criar_rascunho_catalogo) — a criação fica pendente "
            "até aprovar_merge_catalogo (ADR-163)."
        )
    )
    @permission("catalog:write")
    @mcp_rate_limit()
    @_com_deadline_de_catalogo
    def criar_insumo(
        contexto_id: str,
        rascunho_id: str,
        codigo: str,
        tipo: str,
        descricao: str,
        unidade: str,
        preco_unitario: float,
        categoria: str,
        fonte_preco: str,
        atributos_especificos: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        return _impl_criar_insumo(
            contexto_id,
            rascunho_id,
            codigo,
            tipo,
            descricao,
            unidade,
            preco_unitario,
            categoria,
            fonte_preco,
            atributos_especificos,
        )

    @server.tool(
        description=(
            "Cria múltiplos insumos novos numa única chamada (ADR-164) — evita N chamadas "
            "individuais para criar N insumos. Requer rascunho_id. Cada item aceita os mesmos "
            f"campos de criar_insumo. Até {MAX_LOTE_INSUMOS} itens por chamada. "
            "Itens inválidos (código duplicado no lote, código já existente) não abortam o lote — "
            "resposta reporta sucesso/erro por item."
        )
    )
    @permission("catalog:write")
    @mcp_rate_limit()
    @_com_deadline_de_catalogo
    def criar_insumos_lote(
        contexto_id: str,
        rascunho_id: str,
        itens: list[dict[str, Any]],
    ) -> dict[str, Any]:
        return _impl_criar_insumos_lote(contexto_id, rascunho_id, itens)

    @server.tool(
        description=(
            "Descontinua um insumo do catálogo mestre (soft delete — nunca remove o arquivo, "
            "preserva histórico/snapshots). Requer rascunho_id (criado via criar_rascunho_catalogo) — "
            "fica pendente até aprovar_merge_catalogo. Insumos descontinuados são excluídos de "
            "listar_insumos por padrão (ADR-163)."
        )
    )
    @permission("catalog:write")
    @mcp_rate_limit()
    @_com_deadline_de_catalogo
    def descontinuar_insumo(
        contexto_id: str,
        rascunho_id: str,
        insumo_id: str,
        motivo: str | None = None,
    ) -> dict[str, Any]:
        return _impl_descontinuar_insumo(contexto_id, rascunho_id, insumo_id, motivo)

    @server.tool(
        description=(
            "Descontinua (soft delete) múltiplos insumos numa única chamada (ADR-164) — evita N "
            "chamadas individuais. Requer rascunho_id. Cada item aceita insumo_id e motivo opcional. "
            f"Até {MAX_LOTE_INSUMOS} itens por chamada. Itens inválidos não abortam o lote — "
            "resposta reporta sucesso/erro por item."
        )
    )
    @permission("catalog:write")
    @mcp_rate_limit()
    @_com_deadline_de_catalogo
    def descontinuar_insumos_lote(
        contexto_id: str,
        rascunho_id: str,
        itens: list[dict[str, Any]],
    ) -> dict[str, Any]:
        return _impl_descontinuar_insumos_lote(contexto_id, rascunho_id, itens)

    @server.tool(
        description="Registra uma variante de produtividade documentada para uma producao existente "
        "(ex: equipe alternativa com custo/hora diferente) — fica visível em resolved_catalog.json e "
        "exports, mas NÃO é selecionada automaticamente pelo pipeline: o cálculo sempre usa o "
        "'valor_horario'/'custo_hora_total_referencia' da producao base, nunca uma variante. "
        "Para editar o catálogo mestre, informe rascunho_id (criado via criar_rascunho_catalogo) — "
        "a mudança fica pendente até aprovar_merge_catalogo (ADR-145)."
    )
    @permission("catalog:write")
    @mcp_rate_limit()
    @_com_deadline_de_catalogo
    def adicionar_variante_producao(
        contexto_id: str,
        producao_id: str,
        variante_id: str,
        nome_variante: str,
        valor_horario: float,
        equipe_json: str,
        rascunho_id: str | None = None,
        projeto_id: str | None = None,
    ) -> dict[str, Any]:
        return _impl_adicionar_variante_producao(
            contexto_id,
            producao_id,
            variante_id,
            nome_variante,
            valor_horario,
            equipe_json,
            rascunho_id,
            projeto_id,
        )

    @server.tool(
        description=(
            "Consulta (acao='listar', não requer rascunho_id/insumo_id) ou edita "
            "(adicionar/atualizar/remover um insumo × coeficiente × categoria_custo) a "
            "composicao_itens de uma CPU no catálogo mestre. Edição requer rascunho_id "
            "(criado via criar_rascunho_catalogo) — fica pendente até aprovar_merge_catalogo "
            "(mesmo padrão de governança de atualizar_preco_insumo/criar_insumo, ADR-145/163). "
            "Use para corrigir itens de composição inconsistentes (ex.: categoria_custo "
            "incompatível com o tipo do insumo) sem editar o arquivo da CPU manualmente."
        )
    )
    @permission("catalog:write")
    @mcp_rate_limit()
    @_com_deadline_de_catalogo
    def atualizar_composicao_item_cpu(
        contexto_id: str,
        cpu_id: str,
        acao: str,
        insumo_id: str | None = None,
        rascunho_id: str | None = None,
        coeficiente: float | None = None,
        categoria_custo: str | None = None,
        unidade: str | None = None,
        tipo_combustivel: str | None = None,
        nota: str | None = None,
    ) -> dict[str, Any]:
        return _impl_atualizar_composicao_item_cpu(
            contexto_id,
            cpu_id,
            acao,
            insumo_id,
            rascunho_id,
            coeficiente,
            categoria_custo,
            unidade,
            tipo_combustivel,
            nota,
        )

    # ── Análise temporal / RFI ───────────────────────────────────────────────

    @server.tool(
        description=(
            "Consulta histórico de preços do catálogo em dois modos: "
            "'pontual' — preço de um insumo específico em uma data "
            "(para verificar preço vigente na época do contrato); "
            "'tendencia' — evolução histórica de todos os insumos (para detectar inflação/deflação sistêmica)."
        )
    )
    @permission("catalog:read")
    @_com_deadline_de_catalogo
    def historico_preco_insumo(
        contexto_id: str,
        modo: str = "tendencia",
        insumo_id: str | None = None,
        data_referencia: str | None = None,
        projeto_id: str | None = None,
        jurisdicao_id: str | None = None,
    ) -> dict[str, Any]:
        """Histórico temporal de preços do catálogo.

        modos disponíveis:
        - pontual: preço de um insumo em data específica. Requer insumo_id e data_referencia.
        - tendencia: evolução de todos os insumos. Parâmetros insumo_id e data_referencia ignorados.
        """
        if modo == "pontual":
            if not insumo_id or not data_referencia:
                from concilium.presentation.mcp._context import _wrap_response

                return _wrap_response({"erro": "modo='pontual' requer insumo_id e data_referencia"})
            return _impl_consultar_preco_insumo_temporal(
                contexto_id, insumo_id, data_referencia, projeto_id, jurisdicao_id
            )
        elif modo == "tendencia":
            return _impl_tendencia_precos_catalogo(contexto_id, jurisdicao_id)
        else:
            from concilium.presentation.mcp._context import _wrap_response

            return _wrap_response({"erro": f"modo '{modo}' inválido. Use: pontual | tendencia"})

    @server.tool(
        description="Compara duas fontes de entidades de catálogo (catálogo x catálogo, ou catálogo x planilha "
        "PLANILHA PADRÃO RFI .xlsm/.xlsx) e lista divergências (LEFT_ONLY/INNER_HIGH/INNER_LOW/RIGHT_ONLY). "
        "Sempre dry-run — este tool nunca escreve nada; use mesclar_catalogo para aplicar."
    )
    @permission("financials:read")
    @_com_deadline_de_catalogo
    def comparar_catalogo(
        origem_a: str,
        origem_b: str,
        tipo: str = "todos",
    ) -> dict[str, Any]:
        return _impl_comparar_catalogo(origem_a, origem_b, tipo)

    @server.tool(
        description="Mescla uma fonte de origem (catálogo ou planilha PLANILHA PADRÃO RFI .xlsm/.xlsx) no "
        "catálogo de destino, em duas etapas (ADR-177). dry_run=True (padrão) gera um preview e retorna "
        "`merge_id` — nada é escrito no catálogo. dry_run=False aplica um preview existente: exige `merge_id`, "
        "`catalog:merge`, e um ator diferente do que gerou o preview (quatro olhos, ADR-120); escreve nos "
        "arquivos individuais do catálogo mestre e gera CatalogSnapshot/CatalogDiff."
    )
    @permission("catalog:write")
    @mcp_rate_limit()
    @_com_deadline_de_catalogo
    def mesclar_catalogo(
        destino: str,
        origem: str,
        dry_run: bool = True,
        tipo: str = "todos",
        merge_id: str | None = None,
        justificativa: str = "Merge de catálogo",
    ) -> dict[str, Any]:
        from concilium.infrastructure.auth.permission_guard import get_current_user_id

        actor = get_current_user_id() or "system"
        return _impl_mesclar_catalogo(destino, origem, dry_run, tipo, merge_id, actor, justificativa)

    @server.tool(
        description="Recalcula o preço unitário de uma produção específica dado alpha_clt, alpha_pj e preço do diesel. "
        "Use para simular impacto de mudança de encargos ou combustível em uma CPU. "
        "detalhado=True inclui a contribuição item-a-item de cada insumo da equipe (ADR-163)."
    )
    @permission("catalog:read")
    @_com_deadline_de_catalogo
    def calcular_pu_producao(
        contexto_id: str,
        producao_id: str,
        alpha_clt: float = 1.777,
        alpha_pj: float = 1.06,
        preco_diesel: float = 6.50,
        horas_mes: float = 208.0,
        detalhado: bool = False,
    ) -> dict[str, Any]:
        return _impl_calcular_pu_producao(
            contexto_id, producao_id, alpha_clt, alpha_pj, preco_diesel, horas_mes, detalhado
        )

    # ── Versionamento de contexto (ADR-062) ─────────────────────────────────

    @server.tool(
        description=(
            "Gerencia versões de um contexto de catálogo (ADR-062) em dois modos: "
            "'listar' — histórico de versões com datas e autores; "
            "'comparar' — diff lado a lado entre versao_a e versao_b (requer ambas)."
        )
    )
    @permission("catalog:read")
    @_com_deadline_de_catalogo
    def versoes_catalogo(
        contexto_id: str,
        modo: str = "listar",
        versao_a: str | None = None,
        versao_b: str | None = None,
    ) -> dict[str, Any]:
        """Gerencia versões do catálogo (ADR-062).

        modos disponíveis:
        - listar: histórico de versões — versão atual, datas, autores.
        - comparar: diff entre versao_a e versao_b. Requer ambos os parâmetros.
        """
        from concilium.application.services.catalog.contexto_version_service import ContextoVersionService
        from concilium.infrastructure.settings import get_storage

        config_root = get_storage().config_root
        svc = ContextoVersionService(config_root)
        try:
            if modo == "listar":
                versions = svc.list_versions(contexto_id)
                current = svc.current_version(contexto_id)
                return {
                    "contexto_id": contexto_id,
                    "versao_atual": current,
                    "total_versoes": len(versions),
                    "historico": versions,
                }
            elif modo == "comparar":
                if not versao_a or not versao_b:
                    from concilium.presentation.mcp._context import _wrap_response

                    return _wrap_response({"erro": "modo='comparar' requer versao_a e versao_b"})
                diff = svc.compare(contexto_id, versao_a, versao_b)
                return {"contexto_id": contexto_id, "versao_a": versao_a, "versao_b": versao_b, "diff": diff}
            else:
                from concilium.presentation.mcp._context import _wrap_response

                return _wrap_response({"erro": f"modo '{modo}' inválido. Use: listar | comparar"})
        except Exception as exc:
            return {"erro": str(exc)}

    # ── ADR-120: Ciclo de Vida do Catálogo (Rascunho → Merge) ────────────────

    @server.tool(
        description=(
            "Inicia uma campanha de atualização de catálogo em estado de rascunho. "
            "O rascunho é uma nova versão do contexto que pode ser editada com "
            "atualizar_preco_insumo e adicionar_variante_producao antes do merge. "
            "Requer catalog:write. Para promover ao ativo, use aprovar_merge_catalogo (catalog:merge)."
        )
    )
    @permission("catalog:write")
    @mcp_rate_limit()
    @_com_deadline_de_catalogo
    def criar_rascunho_catalogo(
        contexto_id: str,
        descricao: str,
    ) -> dict[str, Any]:
        """Cria rascunho de campanha de atualização de catálogo (ADR-120 D5).

        Args:
            contexto_id: ID do contexto de catálogo.
            descricao: Descrição da campanha (ex: "Reajuste INCC Jun/2026").
        """
        from concilium.application.services.catalog.contexto_version_service import ContextoVersionService
        from concilium.infrastructure.auth.permission_guard import (
            get_current_user_id,
        )
        from concilium.infrastructure.settings import get_storage

        config_root = get_storage().config_root
        svc = ContextoVersionService(config_root)
        actor = get_current_user_id() or "system"
        try:
            current_v = svc.current_version(contexto_id)
            new_v = svc.create_version(
                contexto_id,
                # `create_version` clona `existing[-1]` inteiro como base (SCD genérico:
                # só remove version/created_at/created_by/motivo) — sem resetar
                # explicitamente as chaves de ciclo de vida abaixo, um novo rascunho
                # criado após o anterior já ter sido aprovado nasceria com _aprovado=True
                # e os _deltas antigos herdados, rejeitando qualquer edição nova como
                # "rascunho em estado terminal" (achado durante ADR-166).
                fields={
                    "_rascunho": True,
                    "_rascunho_descricao": descricao,
                    "_deltas": [],
                    "_revisado": False,
                    "_revisado_por": None,
                    "_aprovado": False,
                    "_aprovado_por": None,
                    "_rejeitado": False,
                    "_rejeitado_por": None,
                    "_motivo_rejeicao": None,
                },
                motivo=f"rascunho: {descricao}",
                author=actor,
                make_current=False,  # não promove automaticamente
            )
        except Exception as exc:
            return _wrap_response({"erro": str(exc)})
        return _wrap_response(
            {
                "contexto_id": contexto_id,
                "rascunho_id": new_v["version"],
                "versao_ativa": current_v,
                "descricao": descricao,
                "criado_por": actor,
                "status": "RASCUNHO",
                "nota": "Use atualizar_preco_insumo/adicionar_variante_producao (informando rascunho_id="
                f"'{new_v['version']}') para editar — as mudanças ficam só no rascunho até o merge. "
                "Use aprovar_merge_catalogo para promover (requer catalog:merge).",
            }
        )

    @server.tool(
        description=(
            "Lista divergências entre um rascunho de catálogo e a versão ativa. "
            "Mostra insumos com preços alterados, CPUs adicionadas/removidas e variantes novas. "
            "Requer catalog:validate."
        )
    )
    @permission("catalog:validate")
    @_com_deadline_de_catalogo
    def listar_divergencias_rascunho(
        contexto_id: str,
        rascunho_id: str,
    ) -> dict[str, Any]:
        """Diff entre rascunho e catálogo ativo (ADR-120 D5).

        Marca o rascunho como revisado (RASCUNHO -> REVISADO) — pré-requisito
        para aprovar_merge_catalogo.

        Args:
            contexto_id: ID do contexto de catálogo.
            rascunho_id: Versão do rascunho (ex: "v3").
        """
        from concilium.application.services.catalog.contexto_version_service import ContextoVersionService
        from concilium.infrastructure.auth.permission_guard import get_current_user_id
        from concilium.infrastructure.settings import get_storage

        config_root = get_storage().config_root
        svc = ContextoVersionService(config_root)
        try:
            current_v = svc.current_version(contexto_id)
            diff = svc.compare(contexto_id, current_v, rascunho_id)
            rascunho_data = svc.resolve(contexto_id, rascunho_id) or {}
            _marcar_rascunho_revisado(config_root, contexto_id, rascunho_id, get_current_user_id() or "system")
        except Exception as exc:
            return _wrap_response({"erro": str(exc)})
        return _wrap_response(
            {
                "contexto_id": contexto_id,
                "versao_ativa": current_v,
                "rascunho_id": rascunho_id,
                "divergencias": diff,
                # ADR-145 D1: os deltas acumulados (preço/variante) ainda não aplicados ao master
                "deltas": rascunho_data.get("_deltas", []),
            }
        )

    @server.tool(
        description=(
            "Consulta o impacto financeiro estimado de um rascunho de catálogo "
            "nos projetos ativos que usam esse contexto. Mostra ΔR$ por projeto. "
            "Requer catalog:validate. Use antes de aprovar_merge_catalogo."
        )
    )
    @permission("catalog:validate")
    @_com_deadline_de_catalogo
    def consultar_impacto_reajuste(
        contexto_id: str,
        rascunho_id: str,
    ) -> dict[str, Any]:
        """Impacto financeiro estimado do rascunho em projetos ativos (ADR-120 D5).

        Marca o rascunho como revisado (RASCUNHO -> REVISADO) — pré-requisito
        para aprovar_merge_catalogo.

        Args:
            contexto_id: ID do contexto de catálogo.
            rascunho_id: Versão do rascunho a avaliar.
        """
        from concilium.application.services.catalog.contexto_version_service import ContextoVersionService
        from concilium.infrastructure.auth.permission_guard import get_current_user_id
        from concilium.infrastructure.settings import get_storage

        config_root = get_storage().config_root
        svc = ContextoVersionService(config_root)
        try:
            current_v = svc.current_version(contexto_id)
            rascunho_data = svc.resolve(contexto_id, rascunho_id) or {}
            _marcar_rascunho_revisado(config_root, contexto_id, rascunho_id, get_current_user_id() or "system")
        except Exception as exc:
            return _wrap_response({"erro": str(exc)})
        # ADR-145 P11: os deltas do rascunho (D1) são a fonte real de "o que mudou" —
        # ContextoVersionService.compare() nunca produziu uma chave "modificados"
        # (retorna "changed"/"unchanged"), então n_insumos_afetados sempre voltava 0.
        insumos_afetados = sorted(
            {d["insumo_id"] for d in rascunho_data.get("_deltas", []) if d.get("tipo") == "preco_insumo"}
        )
        # composicao_item afeta a estrutura de custo de uma CPU (não seu preço de
        # insumo isolado) — visibilidade própria pro revisor dos 4-olhos avaliar
        # o impacto (ex.: remoção de item de composição, troca de categoria_custo).
        cpus_afetadas = sorted(
            {d["cpu_id"] for d in rascunho_data.get("_deltas", []) if d.get("tipo") == "composicao_item"}
        )
        return _wrap_response(
            {
                "contexto_id": contexto_id,
                "versao_ativa": current_v,
                "rascunho_id": rascunho_id,
                "n_insumos_afetados": len(insumos_afetados),
                "insumos_modificados": insumos_afetados[:20],
                "n_cpus_com_composicao_alterada": len(cpus_afetadas),
                "cpus_com_composicao_alterada": cpus_afetadas[:20],
                "impacto_estimado": "indisponível — requer recálculo full de projetos ativos",
                "nota": "Para impacto preciso, execute disparar_pipeline nos projetos após o merge.",
            }
        )

    @server.tool(
        description=(
            "Promove um rascunho de catálogo para a versão ativa (merge). "
            "Operação irreversível — o rascunho passa a ser o catálogo ativo. "
            "Requer catalog:merge e que o rascunho já tenha sido revisado (via "
            "listar_divergencias_rascunho ou consultar_impacto_reajuste). "
            "Princípio dos 4 olhos: quem criou o rascunho não pode aprová-lo "
            "(enforced por ator, não só por role)."
        )
    )
    @permission("catalog:merge")
    @mcp_rate_limit()
    @_com_deadline_de_catalogo
    def aprovar_merge_catalogo(
        contexto_id: str,
        rascunho_id: str,
        justificativa: str,
    ) -> dict[str, Any]:
        """Promove rascunho para versão ativa do catálogo (ADR-120 D5, ADR-145 D2/D3).

        Único ponto de escrita efetiva no catálogo mestre: aplica os deltas de
        preço/variante acumulados no rascunho (via RepositorioInsumo.atualizar_preco,
        SCD2/ADR-041), gera um CatalogSnapshot/CatalogDiff (ADR-024) e persiste a
        justificativa junto ao diff — não apenas na resposta desta chamada.

        Args:
            contexto_id: ID do contexto de catálogo.
            rascunho_id: Versão do rascunho a promover (ex: "v3").
            justificativa: Motivo da aprovação para o audit trail.
        """
        import json as _json
        from datetime import date as _date

        from concilium.application.orchestrators.catalog_draft_lifecycle import (
            assert_pode_aprovar,
            build_and_persist_snapshot,
            criar_state_machine,
        )
        from concilium.application.services.catalog.contexto_version_service import ContextoVersionService
        from concilium.infrastructure.auth.permission_guard import (
            _current_roles,
            get_current_user_id,
        )
        from concilium.infrastructure.settings import get_storage
        from concilium.presentation.mcp._context import _runtime

        from ._catalogo_tools_helpers_a import (
            _apply_composicao_item_delta,
            _apply_criar_insumo_delta,
            _apply_descontinuacao_insumo_delta,
            _apply_preco_insumo_delta,
            _apply_variante_producao_delta,
        )
        from ._catalogo_tools_helpers_a import (
            _catalog_root as _resolve_catalog_root,
        )

        config_root = get_storage().config_root
        svc = ContextoVersionService(config_root)
        actor = get_current_user_id() or "system"
        roles = list(_current_roles.get())
        deltas_aplicados = 0
        snapshot_id: str | None = None
        diff_summary: str | None = None
        try:
            # Verifica que o rascunho existe
            rascunho_data = svc.resolve(contexto_id, rascunho_id)
            if rascunho_data is None:
                return _wrap_response({"erro": f"Rascunho '{rascunho_id}' não encontrado."})
            assert_pode_aprovar(rascunho_data, actor)
            versao_anterior = svc.current_version(contexto_id)

            deltas = rascunho_data.get("_deltas", [])
            ctx = None
            if deltas:
                # Só resolve contexto/catálogo se houver algo a aplicar — rascunhos
                # sem deltas (ex.: só reordenam metadados) não precisam de um
                # contexto real configurado.
                rt = _runtime()
                ctx = rt.load_contexto(contexto_id)
                catalog_root = _resolve_catalog_root(config_root, ctx.catalogo_id)
                hoje = _date.today()

                for delta in deltas:
                    tipo = delta.get("tipo")
                    if tipo == "preco_insumo":
                        _apply_preco_insumo_delta(
                            catalog_root,
                            delta["insumo_id"],
                            delta["novo_preco"],
                            delta.get("jurisdicao_id"),
                            delta.get("nota"),
                            delta.get("autor") or actor,
                            hoje,
                            novo_valor_locacao_mensal=delta.get("novo_valor_locacao_mensal"),
                            novos_funcoes_aplicaveis=delta.get("novos_funcoes_aplicaveis"),
                        )
                        deltas_aplicados += 1
                    elif tipo == "variante_producao":
                        _apply_variante_producao_delta(
                            catalog_root,
                            delta["producao_id"],
                            delta["variante_id"],
                            delta["nome_variante"],
                            delta["valor_horario"],
                            delta["equipe"],
                        )
                        deltas_aplicados += 1
                    elif tipo == "criacao_insumo":
                        _apply_criar_insumo_delta(catalog_root, delta["insumo"])
                        deltas_aplicados += 1
                    elif tipo == "descontinuacao_insumo":
                        _apply_descontinuacao_insumo_delta(catalog_root, delta["insumo_id"], delta.get("motivo"))
                        deltas_aplicados += 1
                    elif tipo == "composicao_item":
                        _apply_composicao_item_delta(
                            catalog_root,
                            delta["cpu_id"],
                            delta["insumo_id"],
                            delta["acao"],
                            delta.get("coeficiente"),
                            delta.get("categoria_custo"),
                            delta.get("unidade"),
                            delta.get("tipo_combustivel"),
                        )
                        deltas_aplicados += 1

            # Promove: atualiza ponteiro "current" para o rascunho
            entity_dir = config_root / "contextos" / contexto_id
            current_file = entity_dir / "current"
            if entity_dir.exists():
                current_file.write_text(rascunho_id, encoding="utf-8")
                meta_file = entity_dir / f"{contexto_id}.json"
                if meta_file.exists():
                    meta = _json.loads(meta_file.read_text(encoding="utf-8"))
                    meta["current_version"] = rascunho_id
                    meta_file.write_text(_json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")
            # Marca o rascunho como aprovado (estado terminal) para que
            # rejeitar_rascunho_catalogo não possa mais descartá-lo depois.
            rascunho_file = entity_dir / "versions" / f"{rascunho_id}.json"
            if rascunho_file.exists():
                data = _json.loads(rascunho_file.read_text(encoding="utf-8"))
                sm = criar_state_machine(data)
                sm.aprovar(aprovador=actor)
                rascunho_file.write_text(_json.dumps(sm.rascunho_data, ensure_ascii=False, indent=2), encoding="utf-8")

            if deltas_aplicados:
                # deltas_aplicados só é incrementado dentro do `if deltas:` acima,
                # onde `ctx` é sempre atribuído primeiro.
                assert ctx is not None
                # Runtime novo: bypassa o cache em memória do `rt` acima, que já
                # tem o catálogo pré-merge cacheado nesta mesma chamada.
                catalogo_depois = _runtime().load_catalogo(ctx.catalogo_id)
                snapshot_id, diff_summary = build_and_persist_snapshot(
                    config_root,
                    ctx.catalogo_id,
                    catalogo_depois,
                    actor=actor,
                    contexto_id=contexto_id,
                    rascunho_id=rascunho_id,
                    justificativa=justificativa,
                )
        except Exception as exc:
            return _wrap_response({"erro": str(exc)})
        return _wrap_response(
            {
                "contexto_id": contexto_id,
                "versao_anterior": versao_anterior,
                "versao_ativa": rascunho_id,
                "aprovado_por": actor,
                "role_aprovador": roles[0] if roles else None,
                "justificativa": justificativa,
                "deltas_aplicados": deltas_aplicados,
                "snapshot_id": snapshot_id,
                "diff_summary": diff_summary,
                "status": "APROVADO",
            }
        )

    @server.tool(
        description=(
            "Descarta um rascunho de catálogo (rejeição). "
            "O rascunho é marcado como rejeitado e não pode mais ser promovido. "
            "Requer catalog:merge."
        )
    )
    @permission("catalog:merge")
    @mcp_rate_limit()
    @_com_deadline_de_catalogo
    def rejeitar_rascunho_catalogo(
        contexto_id: str,
        rascunho_id: str,
        motivo: str,
    ) -> dict[str, Any]:
        """Rejeita e descarta rascunho de catálogo (ADR-120 D5).

        Args:
            contexto_id: ID do contexto de catálogo.
            rascunho_id: Versão do rascunho a rejeitar.
            motivo: Justificativa da rejeição para o audit trail.
        """
        from concilium.application.orchestrators.catalog_draft_lifecycle import (
            assert_pode_rejeitar,
            criar_state_machine,
        )
        from concilium.application.services.catalog.contexto_version_service import ContextoVersionService
        from concilium.infrastructure.auth.permission_guard import (
            get_current_user_id,
        )
        from concilium.infrastructure.settings import get_storage

        config_root = get_storage().config_root
        svc = ContextoVersionService(config_root)
        actor = get_current_user_id() or "system"
        try:
            rascunho_data = svc.resolve(contexto_id, rascunho_id)
            if rascunho_data is None:
                return _wrap_response({"erro": f"Rascunho '{rascunho_id}' não encontrado."})
            assert_pode_rejeitar(rascunho_data)
            versao_ativa = svc.current_version(contexto_id)
            # Sinaliza rejeição no arquivo do rascunho
            import json as _json

            rascunho_file = config_root / "contextos" / contexto_id / "versions" / f"{rascunho_id}.json"
            if rascunho_file.exists():
                data = _json.loads(rascunho_file.read_text(encoding="utf-8"))
                sm = criar_state_machine(data)
                sm.rejeitar(motivo=motivo, rejeitado_por=actor)
                rascunho_file.write_text(_json.dumps(sm.rascunho_data, ensure_ascii=False, indent=2), encoding="utf-8")
        except Exception as exc:
            return _wrap_response({"erro": str(exc)})
        return _wrap_response(
            {
                "contexto_id": contexto_id,
                "rascunho_id": rascunho_id,
                "versao_ativa": versao_ativa,
                "rejeitado_por": actor,
                "motivo": motivo,
                "status": "REJEITADO",
            }
        )

    # ── ADR-150: Promoção de Override de Projeto ao Catálogo Master ──────────

    @server.tool(
        description=(
            "Promove os overrides de insumo e CPU pendentes de um projeto (calibrados livremente via "
            "atualizar_preco_insumo/extend_cpu com projeto_id) para o catálogo master. "
            "Requer catalog:merge E ser o dono do projeto (ou admin) — gate duplo, ADR-150. "
            "Quem editou o override não pode ser quem promove (quatro olhos)."
        )
    )
    @permission("catalog:merge")
    @mcp_rate_limit()
    @_com_deadline_de_catalogo
    def promover_override_projeto(
        projeto_id: str,
        justificativa: str,
        contexto_id: str | None = None,
    ) -> dict[str, Any]:
        """Promove overrides de insumo e CPU de um projeto ao catálogo master (ADR-150 D2/D3).

        Fecha o bypass de governança do `catalog promote` (CLI), que escrevia
        direto no catálogo mestre sem gate algum (ADR-150 P2). Reaproveita o
        mesmo caminho de escrita de `aprovar_merge_catalogo` (SCD2/ADR-041,
        CatalogSnapshot/CatalogDiff ADR-024/145).

        Cobre `insumos_override.json` (preço) e `cpus_override.json`
        (produtividade/composição calibrada), sob o mesmo rascunho de projeto e
        o mesmo gate. `bdi_override.json` não é coberto — não tem leitor no
        pipeline real; BDI de projeto é governado por `PerfilBdiProjeto`/
        `bdi-update`, um mecanismo próprio sem conceito de promoção ao master
        (ver ADR-150, seção Achados).

        Args:
            projeto_id: ID do projeto de origem do override.
            justificativa: Motivo da promoção para o audit trail.
            contexto_id: Contexto de catálogo a promover. Se omitido, usa o
                contexto_id gravado no meta do projeto.
        """
        from ._catalogo_tools_helpers_c import _impl_promover_override_projeto

        return _impl_promover_override_projeto(projeto_id, contexto_id, justificativa)

    # ── Pesquisa de mercado ──────────────────────────────────────────────────

    @server.tool(
        description=(
            "Gera planilha de pesquisa de mercado (Mapa de Cotação ou Aferição de Produtividade). "
            "Retorna o arquivo Excel em base64 para envio a fornecedores. "
            "Exclusivo do catalog-manager — não exige acesso a projetos de clientes."
        )
    )
    @permission("catalog:read")
    @_com_deadline_de_catalogo
    def exportar_pesquisa_mercado(
        contexto_id: str = "mendeslobo",
        jurisdicao_id: str = "",
        tipo: str = "price",
    ) -> dict[str, Any]:
        """Gera planilha de pesquisa de mercado para coleta de preços com fornecedores.

        Tipos disponíveis:
          price        — Mapa de Cotação: lista insumos (material/mão-de-obra/equipamento)
                         com preços de benchmark e campos em branco para o fornecedor preencher.
          productivity — Aferição de Produtividade: lista CPUs com índices de referência
                         e campos para registro de produtividade observada em campo.

        Args:
            contexto_id:   ID do contexto de catálogo (default: "mendeslobo").
            jurisdicao_id: ID da jurisdição para benchmark regional (default: do contexto).
            tipo:          Tipo da pesquisa: "price" ou "productivity".

        Returns:
            nome_arquivo, tamanho_mb, conteudo_base64 (xlsx), instrucao de uso.
        """
        import base64
        import tempfile

        from concilium.presentation.mcp._context import _runtime, _wrap_response

        if tipo not in ("price", "productivity"):
            return _wrap_response({"erro": f"Tipo inválido '{tipo}'. Use 'price' ou 'productivity'."})

        try:
            rt = _runtime()
            ctx = rt.load_contexto(contexto_id)
            catalogo = rt.load_catalogo(ctx.catalogo_id)
            catalogo["identidade_visual"] = rt.load_tema(ctx.tema_id).to_catalogo_dict()
        except Exception as exc:
            return _wrap_response({"erro": f"Falha ao carregar contexto '{contexto_id}': {exc}"})

        jur_id = jurisdicao_id or ctx.jurisdicao_id

        try:
            if tipo == "price":
                from concilium.infrastructure.exporters.price_survey import PriceSurveyExporter

                exporter = PriceSurveyExporter(catalogo, jurisdicao_id=jur_id)
                nome = f"mapa_cotacao_{contexto_id}_{jur_id}.xlsx"
            else:
                from concilium.infrastructure.exporters.productivity_survey import ProductivitySurveyExporter

                exporter = ProductivitySurveyExporter(catalogo, jurisdicao_id=jur_id)
                nome = f"afericao_produtividade_{contexto_id}_{jur_id}.xlsx"

            with tempfile.NamedTemporaryFile(suffix=".xlsx", delete=False) as tmp:
                tmp_path = Path(tmp.name)

            exporter.export(tmp_path)
            size_mb = round(tmp_path.stat().st_size / (1024 * 1024), 3)

            if size_mb > 20:
                return _wrap_response(
                    {
                        "aviso": f"Planilha ({size_mb} MB) muito grande para transferência inline.",
                        "instrucao": "Execute via CLI: concilium catalog survey --type price",
                    }
                )

            conteudo_b64 = base64.b64encode(tmp_path.read_bytes()).decode("ascii")
            tmp_path.unlink(missing_ok=True)
        except Exception as exc:
            return _wrap_response({"erro": f"Falha ao gerar pesquisa: {exc}"})

        return _wrap_response(
            {
                "nome_arquivo": nome,
                "tipo": tipo,
                "contexto_id": contexto_id,
                "jurisdicao_id": jur_id,
                "tamanho_mb": size_mb,
                "conteudo_base64": conteudo_b64,
                "encoding": "base64",
                "instrucao": "Decodifique base64 e salve como .xlsx. "
                "Campos destacados em amarelo são para preenchimento do fornecedor.",
            }
        )
