# NEP-042: Modelo de Três Camadas de Precificação — Formalização e Materialização

**Status:** Implementado ✅ _(D1-D4 concluídos 2026-06-10; D5 bridge já derivado em skill-08)_  
**Prioridade:** 🟠 Alta  
**Área:** Arquitetura de Custo · Skills 05/06/08 · Modelo de Domínio  
**Tipo:** Governança · Formalização · Evolução de Produto  
**Esforço:** L  
**Identificado em:** 2026-06-10

---

## Contexto

O framework Concilium computa custo de obras por três metodologias distintas que
coexistem no pipeline e se relacionam de forma precisa. Esta NEP formaliza o modelo,
documenta o status quo de implementação e define a evolução necessária para que as
três camadas sejam explicitamente materializadas, comparáveis e auditáveis por item.

A motivação imediata vem de uma discussão com stakeholders sobre precificação, que
revelou que o modelo do mercado (custo horário × permanência) é um caso especial do
nosso modelo mais geral, e que a distinção entre as três camadas explica o fenômeno
observado em produção: custo pool abaixo ou acima do catálogo dependendo das decisões
de sequenciamento e reaproveitamento de recursos.

---

## O Modelo Formal

### Camada 1 — Preço Unitário de Catálogo (PU_cat)

```
PU_cat_i = custo_hora_total_referencia_i / valor_horario_i
         = Σ_k (preco_insumo_k × coeficiente_k) / producao_horaria_i
```

Decomposto por categoria de custo:

```
PU_cat = PU_MO + PU_EQ + PU_diesel + PU_material
```

**Significado:** quanto custa produzir 1 unidade segundo a composição padrão de equipe
do catálogo, a plena eficiência sem perdas climáticas ou de gestão.
É o preço de referência de mercado — a base do contrato com o cliente.

**Status quo:** implementado em skill 06, persistido em `Planejamento.preco_unitario`.
Fonte: `cpu.precos_unitarios_sbdi` (modo primário) ou `cpu.composicao_itens × preco_insumo`
(fallback — ver NEP-029).

---

### Camada 2 — Preço Unitário Operacional Autônomo (PU_op)

#### 2.1 A célula fundamental

O cronograma decompõe cada atividade i em células semanais j. A `DistribuicaoSemanal[j]`
armazena:

```
m_{ij}     = num_equipes_j           — equipes ativas na semana j (inteiro)
η_p_j      = fator_clima × fator_calendario  — praticabilidade (0–1)
η_w_j      = eficiencia_j            — eficiência de gestão (0–1)
η_j        = fator_total_j = η_s · η_p · η_w — eficiência total observada
q_{ij}     = qtd_executada_j         — produção realizada na semana j
```

#### 2.2 O custo célula a célula — decomposição por natureza

O custo de manter a equipe na célula j é:

```
c_{ij} = m_{ij} × [ c_fixo_i  +  c_comb_i × η_j ]
```

Onde:
- `c_fixo_i = (c_MO + c_EQ) / semanas_por_mês` — custo fixo semanal por equipe
- `c_comb_i = c_diesel / semanas_por_mês` — custo de combustível semanal por equipe

Esta separação é **física**, não arbitrária:

| Componente | Comportamento frente a η_j | Razão |
|---|---|---|
| MO (`c_MO`) | Invariante — pago para toda semana ativa | CLT — salário independe de produção |
| Equipamento (`c_EQ`) | Invariante — pago para toda semana ativa | Locação — dia parado é pago |
| Combustível (`c_comb`) | Proporcional a η_j | Diesel só é consumido quando há produção |

#### 2.3 Grandezas agregadas

```
MW_i   = Σ_j m_{ij}              — machine-weeks brutas (semanas-equipe)
eMW_i  = Σ_j (m_{ij} × η_j)     — machine-weeks efetivas (ponderadas pela produtividade)
η_real_i = eMW_i / MW_i          — eficiência média ponderada pelas equipes
```

#### 2.4 Custo autônomo total e PU operacional

```
custo_aut_i = c_fixo_i × MW_i  +  c_comb_i × eMW_i

Q_i         = Σ_j q_{ij}  =  P_i × h × eMW_i
              (onde P_i = produtividade_horaria, h = horas_semana)

PU_op_i     = custo_aut_i / Q_i
            = c_fixo_i / (P_i × h × η_real_i)  +  c_comb_i / (P_i × h)
            = PU_fixo_cat / η_real_i            +  PU_comb_cat
```

**Consequência central:** apenas as parcelas fixas (MO + EQ) são amplificadas por
`1/η_real`. O combustível não — ele é proporcional à produção, portanto seu PU permanece
igual ao catálogo independentemente da praticabilidade.

Quando η_real < 1 (clima, escala, etc.):

```
PU_op_i > PU_cat_i     →  frentes_necessarias = PU_op_i / PU_cat_i > 1
```

**Status quo:** `custo_aut_i` é implementado em `_calc_custo_cron` via
`_sum_eq_weeks_and_cron_cost` (skill 05, `_skill_helpers_a.py:602`), persistido em
`EquipeDireta.custo_total_autonomo`. `PU_op_i` é **implícito** — calculado na
construção do `PontoEquilibrio` como `pu_calibrado_unitario = max(PU_cat, custo_aut / Q)`,
mas não materializado como campo independente. `eMW_i` e `η_real_i` não são persistidos
no canônico (apenas recalculados no `DiagnosticoPEBuilder` para itens em déficit).

---

### Camada 3 — Custo Pool Instancial por Atividade (custo_pool_i)

#### 3.1 O contrato de pool

Para cada tipo de recurso r, o pool contrata pelo pico de demanda simultânea:

```
custo_contrato_r = peak_demand_r × custo_unit_semanal_r × semanas_contrato_r
                 + custo_mob_desmob_r  (via cadeias de perpetuação — ADR-073)
                 + custo_standby_r     (idle entre atividades da mesma cadeia)
```

Onde:
- `peak_demand_r = max_j(demanda_simultânea_do_tipo_r_na_semana_j)`
- `custo_unit_semanal_r = custo_hora_total_referencia × horas_semana` (por unidade do tipo)

#### 3.2 Atribuição por atividade — a fração Q_i/C_i

A atribuição do custo de pool à atividade i usa machine-weeks como base de Shapley:

```
C_r_total = Σ_i MW_{ir}                   — total machine-weeks do tipo r
fração_i  = MW_{ir} / C_r_total           — esta é a expressão Q_i/C_i do usuário

custo_pool_{ir} = fração_i × custo_contrato_r
               + custo_mob_imputado_{ir}   — mob/demob da cadeia de perpetuação
               + custo_ocioso_imputado_{ir} — idle imputado como sucessor da cadeia
```

O custo pool total por item agrega sobre todos os tipos de recurso:

```
custo_pool_i = Σ_r custo_pool_{ir}
```

E o PU pool:

```
PU_pool_i = custo_pool_i / Q_i
```

**Status quo:** `custo_pool_i` está persistido em
`CustoParticionadoItem.custo_total_particionado` (por tipo r, dentro de
`RecursoContrato.particao_por_item`). `PU_pool_i` não é materializado como campo —
requer divisão por Q no momento de uso.

#### 3.3 A ineficiência comprada

```
economia_vs_autonomo_i = custo_aut_i - custo_pool_i
```

Quando positiva: o pool economiza por compartilhar recursos entre atividades (pico
menor que a soma, mob/demob compartilhado). Quando negativa: o pool custa mais porque
a atividade tem janela curta forçando alta intensidade com idle alto.

---

## Relação entre as três camadas

```
N1 = Σ_i (PU_cat_i × Q_i)           — catálogo puro (base de mercado)
N2 = Σ_i (PU_op_i × Q_i)            — autônomo (clima + escala)
N3 = Σ_i custo_pool_i + mob_demob   — pool instancial (otimização de frota)
```

Ou em termos de bridge (ADR-039, agora derivado do `PontoEquilibrio`):

```
N2 - N1 = Σ_i gap_escala_i          — custo de arredondar frentes para cima
N3 - N2 = Σ_i gap_praticabilidade_i  — custo climático residual após escala
(N3 - N3) — ponto fixo do pool          — pool é N3 por construção quando convergido
N4 = custo_operacional_real          — soma de N3 + indiretos
```

---

## Status Quo — O Que Existe e O Que Está Implícito

| Grandeza | Campo no canônico | Persistido? |
|---|---|---|
| `PU_cat_i` | `Planejamento.preco_unitario.total` | ✅ Explícito |
| `m_{ij}` | `distribuicao_semanal[j].num_equipes` | ✅ Explícito |
| `η_j` | `distribuicao_semanal[j].fator_total` | ✅ Explícito |
| `MW_i = Σ m_{ij}` | `EquipeDireta` via team_weeks | ✅ Calculado (não exposto) |
| `eMW_i = Σ m_{ij}η_j` | — | ⚠️ Implícito |
| `η_real_i = eMW_i/MW_i` | `DiagnosticoPEBuilder.eta_real` (só déficit) | ⚠️ Parcial |
| `custo_aut_i` | `EquipeDireta.custo_total_autonomo` | ✅ Explícito |
| `PU_op_i = custo_aut_i / Q_i` | `PontoEquilibrio.pu_calibrado_unitario` (max) | ⚠️ Implícito |
| `custo_pool_i` | `CustoParticionadoItem.custo_total_particionado` (por tipo r) | ✅ Explícito |
| `PU_pool_i = custo_pool_i / Q_i` | — | ❌ Não materializado |
| `economia_vs_autonomo_i` | `CustoParticionadoItem.economia_vs_autonomo` (por tipo) | ✅ Explícito |

---

## Problema

O modelo de três camadas é **correto e coerente** na implementação, mas **não é visível**
como tal. Os gaps são:

### G1 — PU_op_i implícito

`PU_op_i` é recuperável via `custo_aut_i / Q_i`, mas não é um campo de primeira
classe no `PontoEquilibrio`. O campo `pu_calibrado_unitario` é o `max(PU_cat, PU_op)`,
perdendo a distinção quando PU_op < PU_cat.

### G2 — eMW_i e η_real_i não persistidos por item

A eficiência real ponderada (`η_real_i`) é calculada no `DiagnosticoPEBuilder` apenas
para itens em déficit. Não existe campo canônico que exponha essa grandeza para todos
os itens, o que impede diagnóstico comparativo.

### G3 — PU_pool_i não materializado

O custo pool por item está em `CustoParticionadoItem.custo_total_particionado`, mas
dividido por tipo de recurso r, não como grandeza agregada por atividade. Para obter
`PU_pool_i = Σ_r custo_pool_{ir} / Q_i` é necessário join + computação on demand.

### G4 — Ausência de view consolidada por item

Não existe nenhum campo ou artefato que apresente os três PUs lado a lado por item:

```
item_id | PU_cat | PU_op | PU_pool | frentes_nec | economia_pool
```

Essa view seria o diagnóstico preciso de onde cada desvio ocorre.

---

## Decisões

### D1 — Materializar `PU_op_autonomo_i` como campo explícito

Adicionar `pu_operacional_autonomo: float = 0.0` ao modelo `PontoEquilibrio`.
Distinguir de `pu_calibrado_unitario` (que continua sendo o max).

```python
pu_operacional_autonomo = custo_total_autonomo / quantitativo  # sempre exposto
pu_calibrado_unitario = max(pu_catalogo, pu_operacional_autonomo)  # como hoje
```

### D2 — Materializar `eMW_i` e `η_real_i` para todos os itens

Adicionar `machine_weeks_efetivas: float = 0.0` e `eta_real: float = 1.0` ao
`PontoEquilibrio`. Populados para todos os itens (não apenas déficit) em
`_bpe_process_equipe`.

### D3 — Materializar `PU_pool_i` e `custo_pool_total_i` por item

Adicionar ao `PontoEquilibrio`:
```python
custo_pool_total: float = 0.0       # Σ_r custo_total_particionado_r
pu_pool: float = 0.0                # custo_pool_total / Q_i
```

Computado em `_bpe_process_equipe` via join com `particao_por_item`.

### D4 — Expor view consolidada de três camadas no cubo analítico

Adicionar dimensão `preco_unitario_tres_camadas` ao `CuboAnalitico` e ao artefato
de saída do skill 09, com os campos:

```
item_id, cpu_id, descricao, unidade, quantitativo,
pu_cat, pu_op_autonomo, pu_pool,
frentes_necessarias, eta_real,
economia_pool_abs, economia_pool_pct
```

### D5 — Atualizar `bridge_analysis` para referenciar as três camadas

Tornar explícita a relação `N1 = Σ(PU_cat × Q)`, `N2 = Σ(PU_op × Q)`,
`N3 = Σ(custo_pool)` no `bridge_analysis`, usando os novos campos de D1–D3.
Isso elimina a necessidade do `BridgeAnalyzer` legacy (já deprecated) como
computação independente.

---

## Escopo

### Incluído

1. D1: `pu_operacional_autonomo` no `PontoEquilibrio` (model + populamento)
2. D2: `eta_real` e `machine_weeks_efetivas` no `PontoEquilibrio`
3. D3: `pu_pool` e `custo_pool_total` no `PontoEquilibrio`
4. D4: view de três camadas no artefato de saída do skill 09
5. Validação de invariante: `PU_cat × η_real ≤ PU_op ≤ PU_cat / η_real` (verificar se isso é verdade)

### Excluído

1. Mudança na lógica de cálculo das camadas (apenas materialização de grandezas já computadas)
2. Alteração no modelo de pool ou nos contratos de recurso
3. Novo critério de margem ou BDI

---

## Plano de Implementação

### Fase 1 — Modelo e populamento (D1 + D2 + D3)

1. Adicionar `pu_operacional_autonomo`, `eta_real`, `machine_weeks_efetivas`,
   `pu_pool`, `custo_pool_total` ao `PontoEquilibrio` no canonical.py.
2. Popular em `_bpe_process_equipe` (skill 08 helpers).
3. Regressão: benchmark AGIS sem alteração de resultado numérico (apenas novos campos).

### Fase 2 — View de três camadas (D4)

1. Gerar artefato `preco_unitario_tres_camadas.json` em skill 09.
2. Expor no cubo analítico como nova dimensão.
3. Integrar ao relatório executivo (skill 15).

### Fase 3 — Bridge derivado das três camadas (D5)

1. Derivar N1/N2/N3 diretamente dos campos de `PontoEquilibrio`.
2. Eliminar o uso residual do `BridgeAnalyzer` na bridge_analysis.
3. Validar que bridge derivado ≡ bridge antigo dentro de ±0,01%.

---

## Critério de Aceite

1. Para cada item i do canônico: `PontoEquilibrio[i].pu_operacional_autonomo == custo_total_autonomo / quantitativo`.
2. Para cada item i: `PontoEquilibrio[i].eta_real ≈ eMW_i / MW_i` (±0,1%).
3. Para cada item i com pool: `PontoEquilibrio[i].pu_pool == custo_pool_total / quantitativo`.
4. Artefato `preco_unitario_tres_camadas.json` presente após skill 09 com as colunas definidas em D4.
5. Projeto AGIS: `N2 = Σ(PU_op × Q)` ≈ `N3 = Σ(custo_pool)` com δ < 2% (pool bem calibrado).
6. Benchmark AGIS: sem regressão em resultado numérico após implementação.

---

## Riscos

1. `custo_pool_total_i` depende de `particao_por_item` ser populado — projetos sem pool
   terão `pu_pool = 0`. Distinguir explicitamente de "pool inexistente" vs "custo zero".
2. `η_real_i` calculado sobre itens de muito curta duração pode ser ruidoso (1–2 semanas).
3. Fase 3 (bridge derivado) pode revelar pequenas discrepâncias na derivação atual de N2.

---

## Evidências Técnicas

- `src/concilium/domain/models/canonical.py:256` — `DistribuicaoSemanal` com η_s/η_p/η_w/fator_total
- `src/concilium/application/skills/manifests/05-equipes-e-alocacao/_skill_helpers_a.py:602` — `_sum_eq_weeks_and_cron_cost` (m_{ij} × c_i célula a célula)
- `src/concilium/application/skills/manifests/05-equipes-e-alocacao/_skill_helpers_a.py:651` — `_calc_custo_cron`
- `src/concilium/application/skills/manifests/08-consolidacao-financeira/_skill_helpers_a.py:470` — `_build_pe_for_equipe` (custo_aut/Q implícito)
- `src/concilium/domain/services/diagnostico_pe_builder.py:26` — `_compute_item_metrics` (η_real via pesos q_max_celula)
- `src/concilium/domain/models/canonical.py:571` — `PontoEquilibrio` (campos atuais)
- `src/concilium/domain/models/canonical.py:721` — `CustoParticionadoItem` (custo_total_particionado por tipo)
