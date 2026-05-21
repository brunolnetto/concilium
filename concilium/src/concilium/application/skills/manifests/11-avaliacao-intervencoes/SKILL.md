---
name: 11-avaliacao-intervencoes
description: Use when evaluating possible budget interventions through ROI, Effort, and Risk dimensions, presented as a decision matrix.
---

# Skill 10 — Intervention ROI Matrix

Avalia intervenções possíveis (mudanças em variáveis do orçamento) através de três dimensões independentes: ROI, Effort e Risk. Apresenta como matriz de decisão, não como score combinado.

## Quando ativar

Após `09-cost-criticality`. Skill analítica opcional.

## Princípio fundamental: classificar, não combinar

A tentação é construir um score único `final = ROI / (Risk × Effort)`. Isso é **otimização disfarçada** — cria objetivo implícito que o sistema otimiza. Concilium evita.

A matriz mantém as três dimensões separadas. A combinação é trabalho do humano que decide.

## Inputs

| Nome | Tipo | Origem | Obrigatório |
|------|------|--------|-------------|
| `cost_criticality_report` | object | Canônico (skill 09) | sim |
| `intervencoes_propostas` | array | Usuário | sim |
| `effort_catalog` | object | `perfis/agis.json` ou catálogo dedicado | sim |

**Estrutura de `intervencoes_propostas`**:
```json
[
  {
    "intervencao_id": "int-001",
    "variavel": "produtividade_terraplenagem",
    "tipo_perturbacao": "+10%",
    "descricao": "Aumentar produtividade em 10% via aluguel de equipamento maior"
  }
]
```

**Sobre `effort_catalog`**: classificação de esforço por tipo de intervenção. Não é derivado pelo sistema — vem do conhecimento operacional da construtora. Exemplo: aumentar produtividade via novo equipamento é HIGH effort; aumentar regime para 6 dias úteis é MED effort.

## Depende de

**Skills predecessoras**: pelo menos até `09-cost-criticality`. Idealmente também simulações OFAT já executadas.

**Recursos consumidos**:
- `perfis/agis.json` — catálogo de effort por tipo de intervenção
- Cenários simulados (se disponíveis) para calcular ROI real

## Produz

**Seção do canônico**: `intervention_assessments`.

Para cada intervenção:
```json
{
  "intervention_assessments": [
    {
      "intervencao_id": "int-001",
      "variavel": "produtividade_terraplenagem",
      "roi_margem_pp": 2.0,
      "delta_prazo_dias": -30,
      "effort": {
        "nivel": "HIGH",
        "tipo": "contratacao_equipamento"
      },
      "risk": {
        "nivel": "MEDIUM",
        "drivers": ["dependencia_climatica", "variabilidade_produtividade"]
      },
      "matrix_position": "HIGH_ROI / HIGH_EFFORT / MED_RISK",
      "decision_class": "strategic_move"
    }
  ]
}
```

## Lógica

```
para cada intervencao:

    # ROI — vem de cenários simulados (se houver) ou estimativa heurística
    se cenarios_disponiveis:
        roi_margem_pp = (margem_cenario - margem_baseline) em pontos percentuais
        delta_prazo_dias = (prazo_cenario - prazo_baseline) em dias
    senão:
        roi_estimado_via_sensibilidade  # heurística da skill 09

    # Effort — vem do catálogo, NÃO derivado
    effort = effort_catalog[intervencao.tipo_perturbacao]

    # Risk — derivado de duas fontes
    se cenarios_+10_e_+20_disponiveis:
        # Variância do ROI entre perturbações pequenas e grandes
        ratio = abs(roi_+20% - roi_+10% × 2) / abs(roi_+10%)
        se ratio < 0.3: risk = LOW
        elif ratio < 0.7: risk = MEDIUM
        else: risk = HIGH
    senão:
        # Heurística por dependência climática + variabilidade da CPU
        risk = estimar_via_heuristica()

    # Matrix position — string descritiva, não score
    matrix_position = f"{roi_class}_ROI / {effort.nivel}_EFFORT / {risk.nivel}_RISK"

    # Decision class — categoria descritiva
    decision_class = classificar_intervencao(roi_class, effort, risk)
```

## Categorias de classificação descritiva

```
quick_win          -> ROI MED-HIGH + Effort LOW + Risk LOW
strategic_move     -> ROI HIGH + Effort HIGH + Risk MED-LOW
opportunistic      -> ROI HIGH + Effort LOW + Risk HIGH
risk_averse        -> ROI LOW-MED + Effort LOW + Risk LOW
constraint_driven  -> ROI MED + Effort qualquer + cumpre restrição declarada
not_recommended    -> ROI LOW + Effort HIGH (qualquer risco)
```

## Notas de implementação

- **Sem score combinado, sem ranking.** A skill apresenta intervenções classificadas, não uma lista priorizada. Decisão final é humana.
- **Effort vem de fora do sistema.** O catálogo de effort é dado humano, refletindo conhecimento operacional. Pode ser tão simples quanto uma tabela `tipo_intervenção -> nivel_esforço`.
- **Risk via variância entre perturbações** é o método robusto. Exige rodar cada cenário em duas magnitudes (+10% e +20%, por exemplo). Sem isso, cai-se em heurística menos precisa.
- **Esta skill NÃO recomenda decisão.** Apresenta opções classificadas. Próxima skill (`12-registro-decisoes`) é onde o humano registra qual escolheu e por quê.

## Próxima skill no pipeline

-> [`12-registro-decisoes`](../12-registro-decisoes/SKILL.md)
