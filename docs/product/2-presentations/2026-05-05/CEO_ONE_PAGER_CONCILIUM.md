# Concilium — One-Pager para Fala do CEO
**MendesLobo Construtora | Maio 2026**

## Mensagem principal

O Concilium amadureceu. Em menos de duas semanas, o framework evoluiu de um pipeline de projeto único para um modelo capaz de gerenciar **múltiplos escopos paralelos com planos de trabalho independentes** — tudo dentro do mesmo projeto, com consolidação financeira automática.

Em termos executivos: a empresa passa a poder **comparar cenários antes de comprometer capital**, planejar lotes distintos de uma obra com premissas diferentes e ter uma visão consolidada de margem em nível de projeto — não apenas de lote.

## O que avançou desde Abril

Em 27/04/2026 o Concilium tinha um pipeline funcional para projetos de escopo único. Hoje, o sistema suporta:

- **Múltiplos escopos por projeto** (Lote A, Lote B, Fase 1, Fase 2...) com cronogramas, equipes e BDI independentes
- **Planos de trabalho paralelos** — variantes concorrentes de um mesmo escopo (ex.: "Plano Agressivo" vs. "Plano Conservador") que tramitam em simultâneo para comparação antes da aprovação
- **Consolidação multi-escopo** — a margem do projeto é calculada automaticamente como agregação ponderada dos escopos aprovados, com classificação VERDE / AMARELO / VERMELHO em nível de empreendimento
- **Governança de aprovação por plano** — ao aprovar um plano, os demais são arquivados automaticamente; o canônico aprovado torna-se imutável (somente leitura)
- **Retrocompatibilidade total** — projetos existentes (estrutura `vN/`) continuam funcionando sem migração

## Diferenciais ampliados

| Diferencial | O que muda para a empresa |
|---|---|
| **Escopos paralelos** | Obras com múltiplos lotes ou fases podem ser planejadas e aprovadas em ritmos diferentes dentro do mesmo projeto |
| **Planos alternativos** | É possível rodar dois cenários de planejamento simultaneamente (ex.: 4 equipes vs. 6 equipes) e aprovar um só após comparação técnica |
| **Consolidação de margem** | A diretoria vê a margem total do empreendimento, não apenas de cada lote — com breakdown por escopo e semáforo de risco |
| **Hipótese registrada** | Cada plano de trabalho registra a hipótese que o diferencia — rastreabilidade da intenção técnica, não só do resultado |
| **Integração com IA preservada** | Todos os novos recursos estão disponíveis via MCP (Claude Desktop) — o agente pode criar escopos, comparar planos e consolidar margem por instrução de linguagem natural |

## O que já está entregue

- Pipeline completo de projeto único (skills 00, 01, 06 e as demais em andamento)
- **ADR-031 totalmente implementado**: Escopo, PlanoTrabalho, EscopoStore, PlanoStore, CLI e MCP
- Consolidação financeira multi-escopo (ResultadoConsolidadoProjeto)
- 1.145 testes automatizados, 100% passando
- Suporte a projetos legados via shim transparente — sem migração forçada

## O ganho estratégico desta fase

Antes, um projeto era tratado como uma unidade indivisível de planejamento. Agora, o Concilium reflete a realidade operacional da MendesLobo: **obras de infraestrutura são compostas de partes que podem ser planejadas, revisadas e aprovadas em velocidades diferentes**.

Isso cria três efeitos imediatos:

1. **Aprovação seletiva de lotes**: a empresa pode aprovar o Lote A enquanto ainda refina o Lote B, sem travar o processo inteiro.
2. **Análise de cenário formal**: em vez de recalcular tudo na planilha para simular "e se fossem 6 equipes?", o engenheiro cria um plano alternativo no sistema e compara os dois lado a lado antes de decidir.
3. **Visão executiva consolidada**: a diretoria recebe um único número de margem do empreendimento, composto pelos planos aprovados de cada lote, com rastreabilidade até cada premissa técnica.

## Próximos marcos

| Marco | Objetivo executivo |
|---|---|
| **Skills 02–05** | Completar o pipeline: cronograma, equipes diretas, BDI e indiretos end-to-end |
| **Piloto em obra real** | Executar o Concilium em paralelo com o método atual e comparar resultados |
| **Consolidação multi-escopo no piloto** | Validar a visão de margem agregada com dados reais de campo |
| **Fase 1B analítica** | Criticidade, ROI de intervenção e aprendizado pós-decisão |

## Fechamento sugerido para a fala

O Concilium deixou de ser um orçador de obra. Está se tornando uma **plataforma de decisão de empreendimento** — onde cada lote tem seu planejamento próprio, cada cenário tem sua hipótese registrada e a diretoria vê a margem consolidada antes de comprometer qualquer recurso.

O próximo passo é levar isso para uma obra real e validar na prática o que já está provado em laboratório: o sistema produz os mesmos resultados para as mesmas premissas, preserva o histórico e entrega rastreabilidade completa.

*Documento de apoio para apresentação executiva em 05/05/2026.*
