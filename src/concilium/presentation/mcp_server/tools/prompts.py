"""Templates de mensagens e instruções para o Agente MCP (ADR-031)."""

# Sugestões de EAP e Catálogo
NOTA_EAP_SUGERIDA = "Use cpu_id dos serviços desejados ao chamar iniciar_orcamento."
DICA_BUSCA_CPU = "Use o campo cpu_id de cada resultado como 'cpu_id' nos itens da EAP ao chamar iniciar_orcamento."

# Diagnóstico e Viabilidade
NOTAS_VIABILIDADE = {
    "VIAVEL": "Cronograma dentro do prazo contratual.",
    "INVIAVEL": (
        "Cronograma excede prazo contratual em {semanas} semanas. "
        "Opções: (1) extend_deadline via simular_impacto_replan, "
        "(2) add_resource para acelerar atividades críticas, "
        "(3) reduce_scope para adiar atividades não-críticas."
    ),
}

# Replanejamento
PROXIMOS_PASSOS_REPLAN = [
    "avancar_pipeline('{project_id}', '08-consolidacao-financeira') para recomputar consolidação",
    "avancar_pipeline('{project_id}', '13-assessor-replanejamento') para reanalisar sugestões",
    "avancar_pipeline('{project_id}', '09-relatorio-e-artefatos') para gerar relatório final",
]

# Mensagens de Erro Comuns
ERR_NO_ACTIVE_VERSION = "Nenhuma versão ativa encontrada para o projeto."
ERR_CANONICAL_NOT_FOUND = "Modelo canônico não encontrado para a versão solicitada."
