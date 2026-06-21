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
    "disparar_pipeline('{project_id}', skill_id='06-resultado-financeiro') para recomputar precificação+indiretos+consolidação",
    "disparar_pipeline('{project_id}', skill_id='11-replanejamento-e-cenarios') para reanalisar sugestões e cenários",
    "disparar_pipeline('{project_id}', skill_id='10-relatorio-e-artefatos') para gerar relatório final",
]

# Mensagens de Erro Comuns
ERR_NO_ACTIVE_VERSION = "Nenhuma versão ativa encontrada para o projeto."
ERR_CANONICAL_NOT_FOUND = "Modelo canônico não encontrado para a versão solicitada."

# Procurement Intent (ADR-115)
NOTAS_RFX = {
    "rfi": (
        "RFI: fase exploratória. Priorize custo de catálogo (PU x quantitativo) "
        "para comparação inicial, sem concluir compra."
    ),
    "rfp": (
        "RFP: fase comparativa técnico-econômica. Considere cronograma, clima e "
        "tempo não-produtivo (custo operacional tende a ser maior que catálogo puro)."
    ),
}
