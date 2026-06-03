# Skill 15: Relatório Executivo Consolidado

## Propósito
Materializa o estado de criticidade, sensibilidade e intervenção em um único relatório executivo oficial, anexando as trilhas de auditoria (ArtifactEnvelopes) para a governança corporativa. Consolida as antigas skills 15, 16 e 17.

## Entradas Canônicas
| Seção | Tipo | Fonte | Requerido |
| --- | --- | --- | --- |
| `cost_criticality_report` | object | Canônico (skill 09) | sim |
| `replan_suggestions` | object | Canônico (skill 13) | sim |
| `plan_space_result` | object | Canônico (skill 14) | sim |
| `resultado` | object | Canônico (skill 06) | sim |

## Saídas Canônicas
| Seção | Tipo | Descrição |
| --- | --- | --- |
| `relatorio_criticidade` | object | Ranking Pareto de itens A+, A, B e C |
| `relatorio_sensibilidade` | object | Mapeamento de alavancas (levers) de repair/otimização |
| `relatorio_intervencao` | object | Eixos de intervenção e recomendação primária |

## Comportamento
1. **Criticidade**: Mapeia dados de `cost_criticality_report` para o ranking executivo.
2. **Sensibilidade**: Transpõe as sugestões de replanejamento da Skill 13 para alavancas de impacto na margem.
3. **Intervenção**: Extrai os caminhos da Skill 14 (fronteira de Pareto) para recomendar o melhor curso de ação.
4. **Governança**: Emite três `ArtifactEnvelope` (um para cada tipo de relatório) para manter a compatibilidade com sistemas legados de auditoria.
