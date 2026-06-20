"""MCP Server do Concilium — Fase 2 (esqueleto inicial).

Expõe operações de negócio de alto nível ao Claude Desktop, em vez de
expor skills granulares. Skills permanecem implementação interna,
orquestradas via Runtime.

Operações expostas (Fase 2 inicial):
    iniciar_orcamento     — cria projeto novo a partir de contexto + escopo
    consultar_status      — estado atual de um projeto/versão
    disparar_pipeline     — dispara execução assíncrona do pipeline (ADR-102)
"""
