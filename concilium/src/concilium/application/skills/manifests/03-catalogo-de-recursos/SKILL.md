---
name: 03-catalogo-de-recursos
description: Use when declaring the project resource type catalog and initial available pool, making capacity constraints explicit early in the pipeline.
---

# Skill 01A — Declarar Recursos

Declara o catálogo de tipos de recurso do projeto e o pool inicial disponível. Esta skill roda cedo no pipeline para explicitar restrições de capacidade antes das etapas de cálculo detalhado.

## Quando ativar

Após `02-produtividade-climatica` e antes de `04-cronograma`.

## Inputs

| Nome | Tipo | Obrigatório |
|------|------|-------------|
| `tipos_recurso` | `list[{id, nome, categoria, custo_unitario_dia, especificacoes?}]` | não |
| `templates_recursos` | `dict[cpu_id|"default", list[{tipo|tipo_id, nome, categoria, custo_unitario_dia}]]` | não |
| `pool_inicial` | `list[{tipo_id, quantidade_total, custo_aquisicao_total?}]` | não |

## Depende de

- [`02-produtividade-climatica`](../02-produtividade-climatica/SKILL.md)

## Produz

- `canonical.tipos_recurso`
- `canonical.recurso_pool`

## Validações

- `VAL-DECL-01` (AVISO): item inválido em `tipos_recurso`
- `VAL-DECL-02` (AVISO): pool referencia tipo inexistente
- `VAL-DECL-OK` (OK): declaração concluída
