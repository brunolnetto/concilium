# Workflows de Engenharia Autônoma via MCP

Este documento descreve os fluxos de trabalho que o Agente IA (via Claude Desktop ou interface MCP) pode executar de forma determinística sobre o ecossistema Concilium.

## 1. Workflow de Calibração de Mercado (Market Intelligence)

**Objetivo:** Manter o catálogo de preços atualizado e regionalizado.

1.  **Geração:** O Agente chama `catalog_survey(contexto_id="mendeslobo", jurisdicao_id="BR-SP")`.
2.  **Input:** O usuário fornece dados de cotação (ex: via leitura de PDF ou Planilha).
3.  **Raciocínio (Reasoning):** O Agente compara os preços recebidos com o benchmark atual. Identifica que o preço do aço em SP subiu 15%.
4.  **Execução:** O Agente chama `atualizar_preco_insumo(insumo_id="MA-ACO-CA50", novo_preco=9.50, jurisdicao_id="BR-SP")`.
5.  **Resultado:** O catálogo Mendes Lobo agora reflete a realidade de SP sem afetar os preços do Ceará.

## 2. Workflow de Feedback de Performance (Técnico)

**Objetivo:** Ajustar produtividades teóricas com base na realidade do canteiro.

1.  **Monitoramento:** O Agente recebe um relatório de produtividade de campo.
2.  **Raciocínio:** O Agente nota que em "Solo Arenoso", a escavadeira 38t produz 300m3/h (mais que os 233m3/h do benchmark).
3.  **Execução:** O Agente chama `adicionar_variante_producao` criando a variante `solo_arenoso` com a nova produtividade e a mesma equipe.
4.  **Ação Futura:** Em novos orçamentos, o Agente pode sugerir usar a variante "Solo Arenoso" se o relatório geotécnico indicar esse solo.

## 3. Workflow de Saneamento e Governança (Audit)

**Objetivo:** Garantir que o catálogo esteja 100% íntegro para o pipeline de skills.

1.  **Diagnóstico:** O Agente chama `consultar_saude_catalogo(contexto_id="mendeslobo")`.
2.  **Raciocínio:** O Agente identifica erros de integridade (ex: CPUs sem equipe vinculada).
3.  **Cura (Heal):** O Agente utiliza ferramentas de escrita para corrigir os vínculos (linking) e normalizar os IDs.

## 4. Workflow de Planejamento Determinístico

**Objetivo:** Gerar orçamentos auditáveis em segundos.

1.  **Setup:** `iniciar_orcamento(projeto_id="Novo_Lote_SP", contexto_id="mendeslobo")`.
2.  **EAP:** O Agente chama `pesquisar_catalogo(tipo_obra="terraplenagem")` para carregar o template de serviços.
3.  **Pipeline:** O Agente chama `avancar_pipeline` sucessivamente até a Skill 06 (Consolidação).
4.  **Output:** Exportação da planilha auditável para o cliente final.
