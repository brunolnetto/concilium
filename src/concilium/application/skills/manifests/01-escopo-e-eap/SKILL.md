---
name: 01-escopo-e-eap
description: Use when initializing a project — defines EAP, decomposes into activities and builds the sequencing DAG. Entry point of the pipeline.
---

# Skill 01 — Escopo e EAP

Inicializa o projeto: cria o `CanonicalModel` completo a partir dos inputs do planejador, define a Estrutura Analítica do Projeto (EAP), decompõe cada item em atividades e constrói o Grafo de Atividades (DAG) com precedências. Consolida as antigas skills 00, 00A e 00B.

Skill **GATE** — falha bloqueia todo o pipeline downstream.

## Quando ativar

É sempre a primeira skill do pipeline. Não possui predecessores. Recebe os dados do projeto diretamente do planejador (CLI, API ou MCP).

## Inputs

| Nome | Tipo | Obrigatório | Descrição |
|------|------|-------------|-----------|
| `nome` | string | sim | Nome do projeto |
| `tipo_obra` | string | sim | Categoria (terraplenagem, pavimentação, saneamento, etc.) |
| `localizacao` | string | sim | Cidade/estado de execução |
| `coordenadas` | `{lat, lng}` | sim | Geolocalização para praticabilidade |
| `regime_trabalho` | `{dias_semana, horas_dia}` | sim | Regime padrão da obra |
| `data_inicio` | date | sim | `AAAA-MM-DD` |
| `data_termino` | date | sim | `AAAA-MM-DD` |
| `snapshot_catalogo_id` | string | sim | ID do snapshot de catálogo a usar |
| `snapshot_perfil_id` | string | sim | ID do snapshot de perfil BDI |
| `eap` | `list[{item_id, cpu_id, descricao, unidade, quantitativo}]` | sim | Lista de itens da EAP |
| `contexto_id` | string | sim | Contexto de obra (jurisdição, BDI local) |
| `decomposicao` | `{item_id: [{atividade_id, fracao}]}` | não | Decomposição customizada de itens em atividades |
| `precedencias` | `list[{de, para}]` | não | Precedências entre atividades (sobrescreve inferência automática) |

## Depende de

**Skills predecessoras**: nenhuma — é a skill inicial.

**Recursos consumidos**: snapshot do catálogo (`catalogo`) — lido pelo registry para validar `cpu_id` de cada item da EAP.

## Produz

**Seção do canônico**: `eap`, `atividades`, `activity_dag`, `projeto`, `meta`

| Campo | Tipo | Descrição |
|-------|------|-----------|
| `projeto` | `Projeto` | Metadados completos: nome, tipo, regime, datas, coordenadas |
| `eap` | `list[EapItem]` | Items da EAP com `item_id`, `cpu_id`, `quantitativo`, `unidade` |
| `atividades` | `list[Atividade]` | Decomposição em atividades com `fracao_quantitativo` e `cpu_id` |
| `activity_dag` | `ActivityDag` | Grafo de precedências: nós, arestas, ordem topológica |
| `meta` | `Meta` | Timestamp de geração, versão do schema, framework |

**Validações**:
- `VAL-EAP-01` (ERRO): todos os `cpu_id` existem no catálogo snapshot
- `VAL-ATV-01` (ERRO): soma das frações de atividades por item = 1.0 (±0.001)
- `VAL-SEQ-01` (ERRO): DAG não possui ciclos (verificação topológica de Kahn)

## Lógica de cálculo

```
1. Criar Projeto a partir dos inputs
2. Para cada item na EAP:
   a. Validar cpu_id contra catálogo snapshot
   b. Decompor em atividades (decomposicao input ou 1 atividade = 1 item)
   c. Verificar soma de frações = 1.0
3. Construir DAG de atividades:
   a. Usar precedencias input se fornecidas
   b. Senão: inferir por tipo de obra via AGIS (regras de sequenciamento)
   c. Verificar ausência de ciclos (Kahn topological sort)
4. Emitir CanonicalModel inicial com eap, atividades, activity_dag, projeto, meta
```

## Notas de implementação

- A decomposição default (sem `decomposicao` input) cria **uma atividade por item da EAP** com `fracao_quantitativo = 1.0`. Para projetos complexos, o planejador pode especificar decomposição múltipla (ex.: 60%+40%).
- O DAG inferido automaticamente usa regras de sequenciamento por tipo de obra (módulo AGIS). Precedências customizadas no input sobrescrevem completamente a inferência automática.
- A validação `VAL-SEQ-01` usa o algoritmo de Kahn (BFS topológica) — ciclo detectado = ERRO que bloqueia o pipeline.

## Próximas skills no pipeline

- [`02-produtividade-climatica`](../02-produtividade-climatica/SKILL.md)
- [`03-catalogo-de-recursos`](../03-catalogo-de-recursos/SKILL.md)
- [`04-cronograma`](../04-cronograma/SKILL.md)
