# Skill 14: Plan Space Explorer

## Propósito
Explora a fronteira de Pareto de intervenções (levers) sugeridas pela skill 13 para encontrar o caminho ideal (Repair Path) que restaura a margem ao nível aceitável com o menor impacto colateral ou maior viabilidade.

## Entradas Canônicas
| Seção | Tipo | Fonte | Requerido |
| --- | --- | --- | --- |
| `replan_suggestions` | object | Canônico (skill 13) | sim |
| `resultado` | object | Canônico (skill 06) | sim |

## Saídas Canônicas
| Seção | Tipo | Descrição |
| --- | --- | --- |
| `plan_space_result` | object | Caminho consolidado de repair e otimizações com fronteira de Pareto calculada |

## Comportamento
1. Avalia o leque de `sugestoes` do `replan_suggestions`.
2. Constrói o `RepairPath` somando as alavancas (levers) de maior eficácia e menor risco, até atingir a `margem_alvo_min`.
3. Separa alavancas excedentes na lista de `oportunidades` (para obras já no verde).
