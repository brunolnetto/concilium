---
name: 02-produtividade-climatica
description: Use when calculating the monthly productive percentage of the project from geographic coordinates, work schedule, and historical climate data.
---

# Skill 01 — Praticabilidade

Calcula o percentual produtivo mensal da obra a partir de coordenadas geográficas, regime de trabalho e dados climáticos históricos. Primeira skill do pipeline, consumida pela `cronograma`.

## Quando ativar

Use esta skill no estágio inicial do orçamento, **antes** de qualquer dimensionamento de cronograma. A praticabilidade resultante é congelada no canônico (não recalcula sozinha em revisões posteriores do projeto).

## Inputs

| Nome | Tipo | Origem | Obrigatório |
|------|------|--------|-------------|
| `projeto.coordenadas` | `{lat, lng}` | Canônico (seção `projeto`) | sim |
| `projeto.data_inicio` | `date` | Canônico | sim |
| `projeto.data_termino` | `date` | Canônico | sim |
| `projeto.regime_trabalho` | `{dias_semana, horas_dia}` | Canônico | sim |
| `jurisdicao.fonte_climatica` | `string` | `jurisdicoes/BR.json` | sim |
| `perfil.limiar_inviabilidade_mm` | `number` | `perfis/agis.json` | sim |

## Depende de

**Skills predecessoras**: nenhuma — esta é a primeira skill do pipeline.

**Recursos consumidos**:
- `jurisdicoes/{id}.json` — para descobrir qual fonte climática está habilitada na jurisdição ativa
- `perfis/{id}.json` — para obter o limiar de precipitação que define dia inviável (ex.: AGIS usa 10mm)
- API externa da fonte climática

**Dependências externas**:
- HTTP cliente (Python `requests` ou equivalente) para consumir a API climática
- Tratamento de timeout e fallback quando API estiver indisponível

## Produz

**Seção do canônico**: `praticabilidade` (objeto único, ver `canonical.schema.json` para estrutura completa).

Campos populados:
- `fonte` — string identificando o provedor usado (ex.: "meteoblue")
- `limiar_inviabilidade_mm` — copiado do perfil ativo
- `calculada_em` — timestamp ISO 8601 do cálculo
- `percentual_produtivo_mensal` — objeto com 12 chaves ("01" a "12"), cada uma um percentual (0-1)

**Validações executadas**:
- `VAL-PRAT-01` (ERRO): % produtivo mensal entre 0% e 100%
- `VAL-PRAT-02` (ERRO): cobertura completa do prazo (todos os meses entre `data_inicio` e `data_termino` têm valor)

## Lógica de cálculo

```
para cada mês de janeiro a dezembro:
    consultar fonte climática para a região (lat, lng):
        - dias com precipitação >= 5mm e < 10mm  -> d5_10
        - dias com precipitação >= 10mm e < 20mm -> d10_20
        - dias com precipitação >= 20mm          -> d20+

    dias_total_mes = dias_uteis_no_mes(regime_trabalho)

    se limiar = 5mm:  dias_inviáveis = d5_10 + d10_20 + d20+
    se limiar = 10mm: dias_inviáveis = d10_20 + d20+   ← caso AGIS
    se limiar = 20mm: dias_inviáveis = d20+

    percentual_produtivo[mês] = (dias_total_mes - dias_inviáveis) / dias_total_mes
```

## Notas de implementação

- A API meteoblue não tem endpoint estruturado público; a planilha original construía URL por nome de cidade. Considere: (a) parsear HTML da página de história climática, ou (b) usar API alternativa (Open-Meteo é gratuita e tem dados históricos via REST).
- Cache local agressivo recomendado — coordenadas + período climático histórico não mudam. Salvar em `projetos/{id}/cache/climatica.json`.
- Se o prazo da obra cruza o ano (ex.: começa em mar/26 e termina em ago/27), o cálculo dos 12 meses serve para ambos; o cronograma é que distribui mês-ano específico depois.

## Output esperado (estrutura)

```json
{
  "praticabilidade": {
    "fonte": "meteoblue",
    "limiar_inviabilidade_mm": 10,
    "calculada_em": "2026-04-25T14:00:00Z",
    "percentual_produtivo_mensal": {
      "01": 0.52, "02": 0.48, "03": 0.55,
      "04": 0.70, "05": 0.85, "06": 0.92,
      "07": 0.95, "08": 0.95, "09": 0.88,
      "10": 0.80, "11": 0.68, "12": 0.58
    }
  },
  "validacoes": [
    { "codigo": "VAL-PRAT-01", "status": "OK" },
    { "codigo": "VAL-PRAT-02", "status": "OK" }
  ]
}
```

## Próxima skill no pipeline

-> [`04-cronograma`](../04-cronograma/SKILL.md)
