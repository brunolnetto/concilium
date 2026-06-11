---
name: 07-custos-indiretos
description: Use when sizing the indirect project structure (administration, topography, lab, quality, mobilization) based on project duration and direct operation size.
---

# Skill 05 — Indiretos

Dimensiona a estrutura indireta da obra (administração, topografia, laboratório, qualidade, mobilização) com base no prazo total e no tamanho da operação direta. Categorias específicas vêm do perfil de construtora.

## Quando ativar

Após `equipes-diretas` (precisa do tamanho da equipe direta para dimensionar mobilização) e idealmente após `cronograma` (para saber prazo total). Pode rodar em paralelo com `planejamento-bdi`.

## Inputs

| Nome | Tipo | Origem | Obrigatório |
|------|------|--------|-------------|
| `projeto.data_inicio` | date | Canônico | sim |
| `projeto.data_termino` | date | Canônico | sim |
| `equipes_diretas[]` | array | Canônico | sim |
| `cronograma[]` | array | Canônico | sim |
| `categorias_indireto` | array | `perfis/agis.json` | sim |
| `composicoes_indireto` | object | `perfis/agis.json` ou catálogo dedicado | sim |
| `dados_mobilizacao` | object | Input do planejador | sim |

**Sobre `dados_mobilizacao`**: para a categoria MOB, o planejador fornece origem/destino dos equipamentos, distância, custo por km, número de mobilizações. A skill calcula custos de mobilização e desmobilização a partir disso.

## Depende de

**Skills predecessoras**:
- [`04-cronograma`](../04-cronograma/SKILL.md) — para prazo total da obra
- [`03-equipes-diretas`](../03-equipes-diretas/SKILL.md) — para tamanho da equipe direta (input para baixadas, alimentação, plano de saúde)

**Recursos consumidos**:
- `perfis/agis.json` — quais categorias de indireto a construtora dimensiona (ADM, TOP, LAB, QSMS, MOB)
// insumos.json removido: use arquivos separados por tipo
- `dados/mob.json` (ou similar) — preços por km de mobilização, valores de baixada padrão

**Dependências externas**: nenhuma.

## Produz

**Seção do canônico**: `indiretos` (array, um item por categoria ativa no perfil).

Campos populados por categoria:
- `categoria` (ADM, TOP, LAB, QSMS, MOB)
- `descricao`
- `funcoes[]` — mão de obra alocada
- `equipamentos[]` — equipamentos alocados
- `verbas_mensais[]` — itens recorrentes (alojamento, água/luz, comunicação)
- `verbas_fixas[]` — itens únicos (instalação de canteiro)
- `mobilizacoes[]` — exclusivo da categoria MOB
- `baixadas[]` — exclusivo da categoria MOB
- `permanencia_meses`
- `custo_total`

**Validações executadas**:
- `VAL-POL-INDIRETO` (Configurável): razão indireto/direto dentro da faixa do perfil

## Lógica de cálculo

```
prazo_meses = meses_entre(projeto.data_inicio, projeto.data_termino)
num_pessoas_direta = soma(eq.funcoes[*].num_pessoas para eq em equipes_diretas)

para cada categoria em perfil.categorias_indireto:

    se categoria in [ADM, TOP, LAB, QSMS]:
        composicao = composicoes_indireto[categoria]
        funcoes_alocadas = composicao.funcoes
        equipamentos_alocados = composicao.equipamentos
        verbas_mensais = composicao.verbas_mensais
        verbas_fixas = composicao.verbas_fixas
        permanencia = prazo_meses

        custo_total = (
            soma(funcao.custo_mensal_unitario * funcao.num_pessoas) * permanencia
            + soma(equip.custo_mensal_total * equip.num_unidades) * permanencia
            + soma(verba.total_mensal) * permanencia
            + soma(verba_fixa.valor_total)
        )

    se categoria == MOB:
        # Mobilização e desmobilização de equipamentos
        para cada mob em dados_mobilizacao.equipamentos:
            custo_total_mob = mob.num_unidades * mob.distancia_km * mob.custo_km

        # Despesas com a equipe direta
        baixadas = calcular_baixadas(num_pessoas_direta, prazo_meses, valor_padrao)
        alimentacao_etc = num_pessoas_direta * custo_pessoa_mes * prazo_meses

        custo_total = mobilizacoes + desmobilizacoes + baixadas + alimentacao_etc
```

## Notas de implementação

- O perfil define 5 categorias de indireto (ADM, TOP, LAB, QSMS, MOB). Outras construtoras poderiam ter granularidade diferente (ex.: agrupar QSMS em ADM). O framework não engessa — quem define é o perfil.
- A categoria MOB é "especial" porque tem campos que outras categorias não têm (`mobilizacoes`, `baixadas`). O schema canônico permite isso (campos opcionais), mas a skill precisa tratar a lógica diferente. Considere ramificar a função em `_dimensionar_indireto_padrao` e `_dimensionar_mob`.
- A planilha original tem composições indiretas detalhadíssimas (ADM tem 23 linhas de funções + verbas). Para Fase 1, espelhe a estrutura atual no `composicoes_indireto`. Refinamento depois.
- A faixa de razão indireto/direto da  não está no documento atual — assumir 15-25% como faixa-alvo provisória até diretor comercial confirmar.
- DEC-13 (snapshot inline): após calcular, os valores resolvidos ficam no canônico — adapter não precisa acessar `perfis/agis.json` durante a renderização.

## Output esperado (estrutura)

```json
{
  "indiretos": [
    {
      "categoria": "ADM",
      "descricao": "Administração de obra",
      "funcoes": [...],
      "equipamentos": [],
      "verbas_mensais": [...],
      "verbas_fixas": [...],
      "permanencia_meses": 18,
      "custo_total": 337300
    },
    {
      "categoria": "MOB",
      "descricao": "Mobilização e desmobilização",
      "mobilizacoes": [...],
      "baixadas": [...],
      "custo_total": 614400
    }
  ],
  "validacoes": [
    { "codigo": "VAL-POL-INDIRETO", "status": "OK" }
  ]
}
```

## Próxima skill no pipeline

-> [`06-consolidar`](../06-consolidar/SKILL.md)
