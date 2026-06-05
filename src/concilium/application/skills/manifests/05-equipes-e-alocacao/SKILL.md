---
name: 05-equipes-e-alocacao
description: Use when dimensioning direct teams from CPU composition and allocating them to resource pools. Produces monthly costs with fuel/material split per ADR-030.
---

# Skill 05 — Equipes e Alocação

Dimensiona as equipes diretas de cada item da EAP com base na composição da CPU e nos preços do catálogo, e aloca os recursos ao pool do projeto. Consolida as antigas skills 03, 03A, 03B e 03C.

Produz o custo mensal de MO, equipamentos, combustível e material separadamente (ADR-030), a permanência em meses e o custo total por equipe.

## Quando ativar

Após `04-cronograma` ter calculado o `distribuicao_semanal` de cada atividade — a permanência em meses e o custo de combustível (ajustado por `eficiencia`) dependem do cronograma.

## Inputs

| Nome | Tipo | Obrigatório | Descrição |
|------|------|-------------|-----------|
| `percentual_encargos` | float | não | Encargos CLT horistas (default: `ENCARGOS_CLT = 1.777`) |
| `percentual_encargos_mensalista` | float | não | Encargos CLT mensalistas (default: `ENCARGOS_MENSALISTA = 1.06`) |
| `preco_diesel` | float | não | R$/litro do diesel (default catálogo) |
| `composicao_customizada` | dict | não | Salários/consumo overrides por atividade |

## Depende de

**Skills predecessoras**:
- [`01-escopo-e-eap`](../01-escopo-e-eap/SKILL.md) — fornece `eap` e `atividades`
- [`03-catalogo-de-recursos`](../03-catalogo-de-recursos/SKILL.md) — fornece `tipos_recurso` e `recurso_pool`
- [`04-cronograma`](../04-cronograma/SKILL.md) — fornece `cronograma.scheduled_activities` com `distribuicao_semanal`

**Recursos consumidos**: snapshot do catálogo — preços de insumos, composição de equipe via `producao_id_ref → composicao_padrao_equipe` (ADR-053).

## Produz

**Seção do canônico**: `equipes_diretas`, `tipos_recurso`, `recurso_pool`, `requisitos`, `alocacoes`, `conflitos_pico`

| Campo | Tipo | Descrição |
|-------|------|-----------|
| `equipes_diretas` | `list[EquipeDireta]` | Uma equipe por item da EAP, com breakdown de custos |
| `tipos_recurso` | `list[TipoRecurso]` | Tipos de recursos identificados (equipamentos, funções) |
| `recurso_pool` | `list[RecursoPool]` | Capacidade declarada de recursos |
| `requisitos` | `list[RequisitoRecurso]` | Demanda de cada atividade por recurso |
| `alocacoes` | `list[Alocacao]` | Alocação resolvida (recurso × atividade × período) |
| `conflitos_pico` | `list[ConflitoPico]` | Semanas onde demanda > pool disponível |

**Breakdown de custo por `EquipeDireta` (ADR-030)**:
- `custo_mao_obra_mensal` — MO direta (salário × encargos × num_pessoas)
- `custo_equipamentos_mensal` — capital de equipamentos (excl. combustível)
- `custo_combustivel_total_mensal` — diesel a 100% de eficiência
- `custo_material_mensal` — materiais diretos por hora (ADR-030 D2)
- `permanencia_meses` — duração da campanha (semanas ativas / `SEMANAS_POR_MES`)
- `custo_total` — custo real integrando eficiência semanal de praticabilidade

**Validações**:
- `VAL-EQUIP-SEM-CRON` (AVISO): item sem `distribuicao_semanal` no cronograma — usa duração mínima de 1 semana em vez do projeto inteiro (ADR-056 §T4)
- `VAL-EQUIP-LEGADO-053` (AVISO): `composicao_padrao_equipe` lida do CPU em vez da Produtividade — catálogo desatualizado (ADR-053)
- `VAL-EQUIP-DADOS-01` (AVISO): CPU sem `composicao_padrao_equipe` na Produtividade referenciada
- `VAL-EQP-ALOC` (OK/ERRO): resultado consolidado da alocação

## Lógica de cálculo

```
Para cada item da EAP:
    cpu = catalogo[item.cpu_id]
    prod = catalogo.produtividades[cpu.producao_id_ref]   # ADR-053
    comp = prod.composicao_padrao_equipe

    # Custo MO: Σ funcoes { salario × (1 + encargos) × num_pessoas }
    custo_mo = Σ f { ConversorUnidades(f.preco, f.unidade → "mes") × (1+enc) × f.num_pessoas }

    # Custo EQ: Σ equipamentos { preco_mensal × num_unidades }  (excl. combustível)
    # Custo Combustível: Σ equip { consumo_L/h × preco_diesel × horas_mes × num_unidades }
    # Custo Material: Σ mat { consumo/h × preco × horas_mes }

    # Permanência: semanas_ativas_no_schedule / SEMANAS_POR_MES
    # Custo total: integra combustível × eficiencia_semanal semana a semana
```

## Custo de combustível e praticabilidade

O custo de combustível é o único componente **variável** por praticabilidade. Enquanto MO e equipamentos são pagos mensalmente mesmo em semanas de chuva (custo fixo), o diesel só é consumido em horas produtivas:

```
custo_comb_efetivo = Σ_semanas { comb_nominal/semana × eficiencia_j × num_equipes_j }
```

Isso é o coração do ADR-030 D3 — separar custo fixo de custo variável.

## Notas de implementação

- A resolução de `composicao_padrao_equipe` segue a cadeia ADR-053: `cpu.producao_id_ref → produtividade.composicao_padrao_equipe`. Fallback para `cpu.composicao_padrao_equipe` emite `VAL-EQUIP-LEGADO-053`.
- `HORAS_MES = HORAS_MES_REGIME_6x1 = 208.71 h/mês` (regime 6×8h, constante canônica ADR-056).
- Sem `distribuicao_semanal` no cronograma para um item, o custo é calculado com duração de 1 semana e emite `VAL-EQUIP-SEM-CRON` — evita inflação de custo silenciosa (bug corrigido ADR-056 §T4).

## Próximas skills no pipeline

- [`06-precificacao-unitaria`](../06-precificacao-unitaria/SKILL.md)
- [`07-custos-indiretos`](../07-custos-indiretos/SKILL.md)
