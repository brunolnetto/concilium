---
name: 06-resultado-financeiro-precificacao
description: Use when calculating unit prices with and without BDI per EAP item, broken into 4 cost categories (material, diesel, labor, equipment).
---

# Skill 06 — Planejamento e BDI

Calcula preço unitário (sem e com BDI) por item da EAP, decompondo em 4 categorias (material, diesel, mão de obra, equipamentos) conforme DEC-14. Multiplica pelo quantitativo para obter subtotais. Esta skill é o coração do "preço de venda" do orçamento.

## Quando ativar

Após `equipes-diretas`. Pode rodar em paralelo com `indiretos` se necessário (ambas dependem só do que veio antes).

## Inputs

| Nome | Tipo | Origem | Obrigatório |
|------|------|--------|-------------|
| `eap[]` | array | Canônico | sim |
| `cpus[]` | array | `catalogo/cpus.json` (snapshot) | sim |
| `composicao_itens[]` | array | `catalogo/cpus.json` (snapshot) | sim |
| `insumos[]` | array | `catalogo/insumos/mao_obra.json`, `equipamento.json`, `material.json` | sim |
| `formula_bdi` | ref | `perfis/agis.json` | sim |
| `faixas_bdi_por_categoria` | object | `perfis/agis.json` | sim |

## Depende de

**Skills predecessoras**:
- [`04-cronograma`](../../04-cronograma/SKILL.md) — usa para validar consistência (delta do ponto de equilíbrio é checado em skill posterior; aqui só prepara dados)

**Recursos consumidos**:
- `catalogo/cpus.json` — composições completas de cada CPU
// insumos.json removido: use arquivos separados por tipo
- `perfis/agis.json` — fórmula de cálculo do BDI e faixas por categoria

**Dependências externas**: nenhuma.

## Produz

**Seção do canônico**: `planejamento` (array, um item por entrada da EAP).

Campos populados por item:
- `item_id`, `cpu_id`, `quantitativo`
- `preco_unitario` — decomposto em `{material, diesel, mao_obra, equipamentos, total}` (sem BDI)
- `bdi` — `{material, diesel, mao_obra, equipamentos}` em decimal
- `preco_unitario_com_bdi` — mesma estrutura de `preco_unitario` mas pós-BDI
- `subtotal` — `{sem_bdi: {...}, com_bdi: {...}}`, cada um decomposto em 4 categorias + total

**Validações executadas**:
- `VAL-EAP-01` (ERRO): toda EAP_ITEM referencia uma CPU existente no snapshot
- `VAL-POL-BDI` (Configurável): BDI aplicado dentro da faixa do perfil por categoria
- (Reconciliação de ponto de equilíbrio é feita na skill `_consolidacao`, não aqui)

## Lógica de cálculo

```
para cada item_eap:
    cpu = lookup(catalogo.cpus, item_eap.cpu_id)
    se cpu não existe -> erro VAL-EAP-01

    # Decompor o preço unitário por categoria de custo
    preco_unit_categoria = { material: 0, diesel: 0, mao_obra: 0, equipamentos: 0 }

    para cada composicao_item em cpu.composicao_itens:
        insumo = lookup(catalogo.insumos, composicao_item.insumo_id)
        contribuicao = composicao_item.coeficiente * insumo.preco_unitario
        categoria = composicao_item.categoria_custo  # MATERIAL, DIESEL, MAO_OBRA, EQUIPAMENTO
        preco_unit_categoria[categoria] += contribuicao

    preco_unit_total_sem_bdi = soma(preco_unit_categoria.valores)

    # Aplicar BDI por categoria (DEC-14)
    bdi_aplicado = perfil.faixas_bdi_por_categoria  # ex: {material: 0, diesel: 0.27, ...}

    para cada categoria:
        preco_unit_com_bdi[categoria] = preco_unit_categoria[categoria] * (1 + bdi_aplicado[categoria])

    preco_unit_total_com_bdi = soma(preco_unit_com_bdi.valores)

    # Subtotais (multiplicar pelo quantitativo)
    para cada categoria:
        subtotal_sem_bdi[categoria] = preco_unit_categoria[categoria] * item_eap.quantitativo
        subtotal_com_bdi[categoria] = preco_unit_com_bdi[categoria] * item_eap.quantitativo
```

## Notas de implementação

- **DEC-14**: BDI por 4 categorias é fundamental aqui. Note que a categoria `material` frequentemente tem BDI=0 (porque já vem com margem do fornecedor) e as demais têm BDI próprio. As 4 categorias precisam estar todas presentes mesmo que o valor seja zero.
- A categoria `categoria_custo` em cada `composicao_item` deve ser populada já no catálogo. Se vier vazia, defina regra: tipo do insumo (MATERIAL->material, EQUIPAMENTO->equipamentos, etc.) com fallback explícito.
- Atenção aos números — a planilha original tem subtotais com casas decimais variando. Sugiro fixar arredondamento em 2 casas em outputs e mais casas em cálculo intermediário, com nota explícita no canônico.
- A reconciliação de ponto de equilíbrio (delta entre custo da equipe direta — `05-equipes-e-alocacao` — e custo de venda da CPU — esta skill) é feita pela skill `_consolidacao`. Aqui só preparamos os dados.

## Sobre a fórmula do BDI no perfil

Cada construtora pode usar fórmula diferente para chegar ao percentual de BDI por categoria. A AGIS hoje usa uma fórmula padrão de mercado (Acórdão TCU 2622/2013), mas o framework não amarra isso — em `perfis/agis.json`, o campo `formula_bdi` referencia um identificador de fórmula. Para Fase 1, basta uma fórmula padrão; expandir conforme necessidade.

## Output esperado (estrutura)

```json
{
  "planejamento": [
    {
      "item_id": "eap-001",
      "cpu_id": "ESCO-CARGA-1CAT-DMT2000",
      "quantitativo": 125000,
      "preco_unitario": {
        "material": 0, "diesel": 1.47, "mao_obra": 3.86, "equipamentos": 0.97, "total": 6.30
      },
      "bdi": {
        "material": 0, "diesel": 0.27, "mao_obra": 0.27, "equipamentos": 0.27
      },
      "preco_unitario_com_bdi": {
        "material": 0, "diesel": 1.87, "mao_obra": 4.91, "equipamentos": 1.23, "total": 8.01
      },
      "subtotal": {
        "sem_bdi": {"material": 0, "diesel": 183750, "mao_obra": 482500, "equipamentos": 121250, "total": 787500},
        "com_bdi": {"material": 0, "diesel": 233375, "mao_obra": 613575, "equipamentos": 153925, "total": 1000875}
      }
    }
  ],
  "validacoes": [
    { "codigo": "VAL-EAP-01", "status": "OK" },
    { "codigo": "VAL-POL-BDI", "status": "OK" }
  ]
}
```

## Próxima skill no pipeline

-> [`_indiretos`](../_indiretos/SKILL.md)
