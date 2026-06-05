# Skill 13: Replan Advisor

## Propósito
Analisa a criticidade da obra e gera sugestões ativas (levers) de replanejamento de cronograma, aumento de equipes, ou revisão de BDI para restaurar o balanço e a saúde financeira/produtiva do projeto.

## Entradas Canônicas
| Seção | Tipo | Fonte | Requerido |
| --- | --- | --- | --- |
| `cost_criticality_report` | object | Canônico (skill 09) | sim |
| `resultado` | object | Canônico (skill 06) | sim |
| `balanco_de_controle` | object | Canônico (skill 06) | sim |

## Saídas Canônicas
| Seção | Tipo | Descrição |
| --- | --- | --- |
| `replan_suggestions` | object | Lista de alavancas (levers) e cenários potenciais de replanejamento |

## Comportamento
1. Avalia se o status do projeto é AMARELO ou VERMELHO.
2. Com base nas atividades classificadas como `A+` e `A`, gera sugestões de intervenção (redução de duração, adição de recursos, etc).
3. Projetar impacto percentual na margem (delta).
