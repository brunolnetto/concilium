---
name: 04-cronograma
description: Use when distributing EAP service execution across project months, considering hourly output, team count, and monthly productive percentage.
---

# Skill 04 — Cronograma

Distribui a execução de cada serviço da EAP ao longo dos meses do prazo, considerando produção horária, número de equipes alocadas e percentual produtivo mensal. Produz a quantidade executada e acumulada por mês para cada item da EAP.

## Quando ativar

Após a skill `praticabilidade` ter populado o canônico. O cronograma é o estágio que une produção (Camada 2 — CPU) com tempo disponível (Camada 4 — praticabilidade) para gerar a malha temporal da obra.

## Inputs

| Nome | Tipo | Origem | Obrigatório |
|------|------|--------|-------------|
| `eap[]` | array de itens | Canônico | sim |
| `praticabilidade.percentual_produtivo_mensal` | object | Canônico | sim |
| `projeto.data_inicio` | date | Canônico | sim |
| `projeto.data_termino` | date | Canônico | sim |
| `projeto.regime_trabalho.dias_semana` | int | Canônico | sim |
| `projeto.regime_trabalho.horas_dia` | int | Canônico | sim |
| `cpus[].producao_horaria` | number | `catalogo/cpus.json` (snapshot) | sim |
| `num_equipes_por_mes` | object | **Input do usuário** (planejador) | sim |

**Sobre `num_equipes_por_mes`**: este é o único input livre do planejador no estágio de cronograma. Ele define quantas equipes paralelas executam cada serviço em cada mês. A skill calcula a produção resultante; cabe ao planejador iterar até atingir 100% de execução no prazo.

## Depende de

**Skills predecessoras**:
- [`02-produtividade-climatica`](../02-produtividade-climatica/SKILL.md) — fornece `percentual_produtivo_mensal`

**Recursos consumidos**:
- `catalogo/cpus.json` (via snapshot do projeto) — para obter `producao_horaria` de cada CPU referenciada na EAP

**Dependências externas**: nenhuma.

## Produz

**Seção do canônico**: `cronograma` (array, um item por entrada da EAP).

Campos populados por item:
- `item_id` — referência ao `eap[].item_id`
- `dias_trabalhados_semana` — copiado de `projeto.regime_trabalho.dias_semana`
- `distribuicao_mensal` — objeto com chaves no formato `AAAA-MM`, valores `{num_equipes, qtd_executada, qtd_acumulada, pct}`
- `pct_completude` — quanto da `eap[].quantitativo` foi executado pelo cronograma (deve ser 1.0)

**Validações executadas**:
- `VAL-CRON-01` (ERRO): cada item atinge 100% de execução até a `data_termino`
- `VAL-CRON-02` (ERRO): não há mês com `num_equipes = 0` no meio da execução de um item

## Lógica de cálculo

```
para cada item_eap:
    cpu = lookup(catalogo.cpus, item_eap.cpu_id)
    producao_diaria = cpu.producao_horaria * projeto.regime_trabalho.horas_dia

    para cada mês entre projeto.data_inicio e projeto.data_termino:
        num_equipes = num_equipes_por_mes[item_eap.item_id][mês]
        pct_produtivo = praticabilidade.percentual_produtivo_mensal[mês_num]
        dias_uteis_mes = calc_dias_uteis(mês, regime_trabalho.dias_semana)

        qtd_executada = (
            producao_diaria
            * dias_uteis_mes
            * pct_produtivo
            * num_equipes
        )

        qtd_acumulada += qtd_executada
        pct = qtd_acumulada / item_eap.quantitativo

        distribuicao_mensal[mês_ano] = {num_equipes, qtd_executada, qtd_acumulada, pct}
```

## Notas de implementação

- O input `num_equipes_por_mes` vem do planejador iterativamente. A skill **não decide** quantas equipes alocar — calcula o que produziria com a alocação informada. Se `pct_completude < 1.0`, retorna o cronograma como está e dispara `VAL-CRON-01` como ERRO; cabe ao planejador aumentar equipes ou prazo.
- A função `calc_dias_uteis(mês, dias_semana)` precisa considerar feriados nacionais (camada de jurisdição traz o calendário). Para Fase 1 inicial, simplificação aceitável é usar dias úteis efetivos (seg-sáb se dias_semana=6) sem descontar feriados; refinar depois.
- DEC-09: equipes são idênticas. `num_equipes_por_mes` é apenas inteiro — não há configuração diferente por equipe.
- Cuidado com mudança de equipes mês-a-mês criando "buracos" — VAL-CRON-02 detecta isso. Permitir transição suave (ex.: 2 equipes em junho, 1 em julho) é OK; ter 0 equipes em julho com produção pendente é ERRO.

## Output esperado (estrutura)

```json
{
  "cronograma": [
    {
      "item_id": "eap-001",
      "dias_trabalhados_semana": 6,
      "distribuicao_mensal": {
        "2026-03": {"num_equipes": 1, "qtd_executada": 4160, "qtd_acumulada": 4160, "pct": 0.033},
        "2026-04": {"num_equipes": 1, "qtd_executada": 5600, "qtd_acumulada": 9760, "pct": 0.078}
      },
      "pct_completude": 1.0
    }
  ],
  "validacoes": [
    { "codigo": "VAL-CRON-01", "status": "OK" },
    { "codigo": "VAL-CRON-02", "status": "OK" }
  ]
}
```

## Próxima skill no pipeline

-> [`05-equipes-e-alocacao`](../05-equipes-e-alocacao/SKILL.md)
