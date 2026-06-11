# ADR-105 — Mobilização e Desmobilização de Mão-de-Obra e Equipamentos: Política Integrada Diretos+Indiretos

**Status:** Parcialmente Implementado ⚠️ _(auditado 2026-06-09)_

> **Nota:** `mob_schedule` inferido automaticamente via `infer_mob_windows` em skill-04; skill-07 consome `mob_schedule` do canônico. `detalhamento` interno do evento MOB extraído de `indiretos.mob.txt` para 11 benchmarks (§2.5). Desdobramento em três fases, janelas de equipes diretas e lógica SS/FF aguardam Sprint S3 (ADR-106).  
**Data:** 2026-06-08  
**Atualizado:** 2026-06-09 (§1.2 dados empíricos expandidos; §2.5 estrutura interna do evento MOB)  
**Contexto:** MendesLobo Construtora — Concilium  
**Depende de:** ADR-046, ADR-054, ADR-071, ADR-072, ADR-085, ADR-090  
**Substitui parcialmente:** ADR-054 (política refinada)  
**Incorpora:** ADR-107 (supersedido — conteúdo integrado aqui)  

---

## 1. Contexto

### 1.1 Problema

**P1: Redundância de rcpsp_spec em benchmarks minimalista**
- `spec.rcpsp_spec` contém ~250 linhas de dados redundantes:
  - `activities`: duplica `spec.eap` (já contém atividades + predecessores)
  - `resource_pool`: define pools genéricos (inferiáveis de `spec.cronograma` + `spec.bdi`)
  - `precedence`: redundante (já em `eap.predecessores`)
  - `resource_costs`: redundante (já em `spec.bdi` + `spec.indiretos`)

**P2: Falta de política clara para mobilização/desmobilização**
- Benchmarks têm custos de MOB (Mobilização) e custos de operação (Canteiro), mas sem estrutura tipificada
- Dados dos planejamentos.txt mostram padrão claro (ODFJELL, MATEC):
  - Mobilização inicial (fase): R$ 2.044.560 (9.7% do custo total)
  - Operação contínua (mensal): Custos de canteiro/combustível
  - Desmobilização final (fase): R$ 408.912 (3.0% do custo total)

**P3: Confusão semântica entre diretos e indiretos**
- Mão-de-obra em mobilização é custo indireto (não tem atividade EAP associada)
- Equipamentos em mobilização podem ser diretos (alocados a atividades) ou indiretos (canteiro)
- Não há distinção clara entre:
  - Mobilização de **recursos produtivos** (diretos: equipes alocadas a EAP)
  - Mobilização de **infraestrutura** (indiretos: canteiro, acampamento, etc.)

### 1.2 Contexto Adicional

**Dados empíricos de 11 benchmarks (2026-06-09) — análise de `indiretos.mob.txt`:**

Os arquivos `indiretos.mob.txt` de todos os benchmarks têm estrutura consistente em três camadas:

```
EQUIPAMENTOS  R$ X   ← transporte de frota: n_eq × distância × R$/km (ida+volta)
MÃO DE OBRA   R$ Y   ← transporte de equipe: n_pessoas × custo/pessoa
VERBAS        R$ Z   ← setup logístico: contêineres, banheiros, mob. equipe direta
              ─────
TOTAL         R$ T   (T = X + Y + Z, invariante verificado com Δ=0% nos 11 benchmarks)
```

| Benchmark | Total (T) | Equipamentos | Pessoal (n) | Distância | Rota |
|---|---|---|---|---|---|
| RUMO | R$820k | R$329k (12eq) | R$85k (56p) | 1.372km | Goiânia→Dom Aquino |
| PRIVATE_LOG | R$1,8M | R$550k (19eq) | R$60k (50p) | 1.080km | BH→Serra |
| VALE | R$1,1M | R$270k (4eq) | R$239k (100p) | 960km | Goiânia→Cocalinho |
| CTC | R$6,3M | R$1,3M (23eq) | R$119k (99p) | 2.100km | Londrina→Barra do Ribeiro |
| LUNDIN | R$1,5M | R$135k (4eq) | R$98k (41p) | 700km | Goiânia→Alto Horizonte |
| ODFJELL | R$247k | R$124k (5eq) | R$31k (31p) | 98km | Rio Verde→Santa Helena |
| MATEC_GUARULHOS | R$2,0M | R$123k (20eq) | R$126k (53p) | ~200km | SP→Guarulhos |
| MARA_ROSA | R$439k | R$66k (10eq) | R$77k (32p) | 200km | Natal→Parnamirim |
| ROSH | R$439k | R$66k (10eq) | R$77k (32p) | 200km | Natal→Parnamirim |
| MATEC_HINES | R$1,5M | R$113k (17eq) | R$85k (66p) | 200km | SP→Guarulhos |
| MATEC_UBERLANDIA | R$2,3M | R$463k (1eq) | R$161k (54p) | 1.080km | BH→Uberlândia |

**Observação crítica:** Os arquivos `indiretos.mob.txt` cobrem **somente** o evento de transporte (mobilização + desmobilização combinados). A fase `operacao` do modelo abaixo — custos mensais de canteiro (veículos de suporte, geradores, combustível recorrente) — **não está no mob.txt**: está na seção EQUIPAMENTOS de `indiretos.adm.txt`. Isso implica que a extração da fase `operacao` requer parsing adicional do ADM.

**Estrutura de `spec.indiretos` existente nos benchmarks (estado atual):**
```json
"indiretos": [
  {"categoria": "ADM", "driver": "mensal", "custo_fixo_mensal_total": 875249, "mao_obra": [...]},
  {"categoria": "TOP", "driver": "mensal", "custo_fixo_mensal_total": 284934, "mao_obra": [...]},
  {"categoria": "LAB", "driver": "mensal", "custo_fixo_mensal_total": 195867, "mao_obra": [...]},
  {"categoria": "QSMS", "driver": "mensal", "custo_fixo_mensal_total": 7673,   "mao_obra": [...]},
  {"categoria": "MOB", "driver": "projeto", "custo_fixo_total": 819637, "detalhamento": {...}}
]
```

> **Nota de campo:** Os benchmarks usam `categoria` (não `tipo` como este ADR originalmente propôs). O alinhamento do nome de campo para `tipo` será feito quando o desdobramento em fases for implementado (Sprint S3).

---

## 2. Decisão

### 2.1 Política de Mobilização e Desmobilização (MOB)

**Define estrutura tipificada para `spec.indiretos` com tipo `MOB` e três fases explícitas:**

```json
"indiretos": [
  {
    "tipo": "MOB",
    "fase": "mobilizacao",              // início: semana 1
    "driver": "projeto",                 // custo fixo único (não recorrente)
    "custo_fixo_total": 2044560.87,     // extraído de planejamento.txt
    "descricao": "Mobilização e aquisição de equipamentos produtivos",
    "categorias": ["equipamentos", "transporte"]
  },
  {
    "tipo": "MOB",
    "fase": "operacao",                  // contínuo: semana 1 até semana N
    "driver": "mensal",                  // recorrente durante execução
    "custo_fixo_mensal": 50000.00,      // Canteiro, geradores, combustível
    "descricao": "Custos de canteiro de obras (aluguel, manutenção, utilidades)",
    "categorias": ["canteiro", "utilidades"]
  },
  {
    "tipo": "MOB",
    "fase": "desmobilizacao",            // fim: semana N+1 até semana N+2
    "driver": "projeto",                 // custo fixo único (não recorrente)
    "custo_fixo_total": 408912.17,      // limpeza, desmontagem, restauração
    "descricao": "Remoção de equipamentos e restauração do sítio",
    "categorias": ["desmontagem", "restauracao"]
  },
  {
    "tipo": "ADM",
    "driver": "mensal",
    "custo_fixo_mensal": 384000.00,
    "descricao": "Administração geral do projeto"
  }
]
```

### 2.2 Cronograma de Mobilização (Derivado Determinístico)

**Sem rcpsp_spec, a mobilização é inferida automaticamente da timeline do projeto:**

```python
# Pseudo-código para inferência automática
def infer_mob_schedule(meta, spec_eap):
    project_start = parse_date(meta.data_inicio)
    project_end = parse_date(meta.data_termino)
    
    # EAP dates (topological sort via predecessores)
    first_eap_date = min(activity.start_date for activity in topo_sort(spec_eap))
    last_eap_date = max(activity.end_date for activity in topo_sort(spec_eap))
    
    # Windows
    mob_start = project_start                           # Semana 1
    mob_end = first_eap_date - timedelta(days=7)        # 1 semana antes primeira atividade
    
    operation_start = mob_start
    operation_end = last_eap_date + timedelta(days=7)   # 1 semana após última atividade
    
    demob_start = last_eap_date
    demob_end = project_end
    
    return {
        "mobilizacao": (mob_start, mob_end),
        "operacao": (operation_start, operation_end),
        "desmobilizacao": (demob_start, demob_end)
    }
```

**Distribuição de custos:**
- **driver="projeto"** (MOB mobilização/desmobilização): Custo total incorre na primeira/última semana
- **driver="mensal"** (MOB operação): Distribuído proporcionalmente aos meses dentro da janela

### 2.3 Integração com Diretos e Indiretos

**Semântica clara:**

| Fase | Tipo | Driver | Componentes | Destino | Exemplos |
|------|------|--------|-------------|---------|----------|
| **Mobilização** | MOB | projeto | Equipamentos produtivos, transporte | Indireto | Escavadeiras, Caminhões, Geradores |
| **Operação** | MOB | mensal | Canteiro, manutenção, combustível | Indireto | Aluguel canteiro, Diesel, Manutenção |
| **Desmobilização** | MOB | projeto | Limpeza, desmontagem, restauração | Indireto | Remoção de entulho, Limpeza sítio |
| **Equipes Diretas** | (não MOB) | — | Mão-de-obra alocada a EAP | Direto | Operadores, Pedreiros (alocados a atividades) |

**Nota importante:** Mão-de-obra em MOB é **indireto** (não alocada a atividades específicas). Mão-de-obra direta vem de `spec.cronograma[].num_equipes` (via skill-05).

### 2.5 Estrutura Interna do Evento MOB (implementado em 2026-06-09)

As fases `mobilizacao` e `desmobilizacao` (ambas `driver: "projeto"`) têm estrutura interna em **três camadas de custo**, extraídas de `indiretos.mob.txt`:

**Camada A — Transporte de frota** (`equipamentos`): `n_eq × distancia_km × custo_km`  
**Camada B — Transporte de pessoal** (`pessoal`): `n_pessoas × custo_por_pessoa`  
**Camada C — Setup logístico** (`verbas`): contêineres, banheiros, mob. equipe direta

Estrutura de dados atual (enquanto MOB permanece entrada única antes do desdobramento em §2.1):

```json
{
  "categoria": "MOB",
  "driver": "projeto",
  "custo_fixo_total": 819636.54,
  "detalhamento": {
    "rota": { "origem": "GOIÂNIA", "destino": "DOM AQUINO", "distancia_km": 1372 },
    "equipamentos": { "quantidade_mob": 12, "custo_km": 9.50, "distancia_km": 1372, "subtotal": 328516.0 },
    "pessoal":      { "quantidade_pessoas": 56, "custo_por_pessoa": 750.0, "subtotal": 84600.0 },
    "verbas":       {
      "subtotal": 406520.54,
      "itens": [
        {"descricao": "MOBILIZAÇÃO EQUIPE DIRETA", "quantidade": 0.42, "preco_unitario": 281169.29, "subtotal": 117153.87},
        {"descricao": "MOBILIZAÇÃO DE EQUIPAMENTOS", "quantidade": 0.21, "preco_unitario": 836000.0, "subtotal": 174166.67}
      ]
    }
  }
}
```

**Invariante:** `custo_fixo_total = equipamentos.subtotal + pessoal.subtotal + verbas.subtotal` (verificado Δ=0% em 11 benchmarks).

Quando o desdobramento em §2.1 for implementado (Sprint S3), o `detalhamento` migra integralmente para a fase `mobilizacao`. A fase `desmobilizacao` reutiliza os mesmos parâmetros de rota com simetria de custo (mesmo custo de transporte de retorno). A fase `operacao` será extraída da seção EQUIPAMENTOS de `indiretos.adm.txt`.

**Roadmap paramétrico** (integrado ao plano de Sprint S3):

- **F1** — Derivar `n_equipamentos` do pool RCPSP (não declarar manualmente)
- **F2** — Derivar `distancia_km` de `localizacao.{lat,lng}` → depósito base via geocodificação
- **F3** — Sensibilidade de escopo: redução do pool → recalculo automático do custo MOB
- **F4** — Extrair fase `operacao` dos equipamentos de `indiretos.adm.txt`
- **F5** — Desdobrar entrada única MOB nas três entradas de fase do §2.1 + alinhar `categoria`→`tipo`

**Pré-requisito estrutural implementado (2026-06-10 — precede Sprint S3):**

`EquipeDireta` agora tem os campos receptores das fases, todos com `default=0.0`:
- `custo_mobilizacao_mensal` — custo de transporte + montagem na chegada
- `custo_operacao_mensal` — custos fixos recorrentes de canteiro (≠ mob/demob)
- `custo_desmobilizacao_mensal` — custo de desmontagem + transporte de retorno

Invariante documentado: `custo_mobilizacao_mensal + custo_desmobilizacao_mensal ≈ custo_mob_desmob`.
`custo_operacao_mensal` é independente — captura canteiro em `indiretos.adm` (F4).
8 testes em `tests/unit/test_adr105_f1f3_mob_fases.py` validam os campos e retrocompatibilidade.

### 2.4 Eliminação de rcpsp_spec

Com esta política, `spec.rcpsp_spec` pode ser eliminado completamente:

| Campo rcpsp_spec | Substituído por | Mecanismo |
|------------------|-----------------|-----------|
| `activities` | `spec.eap` | Direto: item_id, predecessores já estão em EAP |
| `resource_pool` | `spec.indiretos.MOB` + `spec.cronograma` | Indireto: definido como typed MOB phases |
| `precedence` | `spec.eap[].predecessores` | Direto: DAG derivado de predecessores |
| `resource_costs` | `spec.bdi` + `spec.indiretos` | Direto: BDI componentes + MOB fases |
| `deadline_weeks` | `meta.data_termino - meta.data_inicio` | Direto: calculado da timeline do projeto |

**Benefício:** Redução ~80% no tamanho do arquivo (rcpsp_spec era 250+ linhas, spec.indiretos MOB são ~30 linhas).

---

## 3. Alternativas Rejeitadas

| ID | Alternativa | Motivo da Rejeição |
|----|-------------|-------------------|
| **A1** | Manter rcpsp_spec + adicionar MOB phases em indiretos | **Redundância e manutenção:** Dois fontes de verdade para mesma informação (scheduling). Falha no princípio DRY. |
| **A2** | Usar cronograma para mobilização (sem MOB tipo) | **Falta de semântica:** Cronograma é para atividades EAP. MOB não é atividade. Confunde modelos de dados. |
| **A3** | Criar tipo indireto separado "MOBEQ" (equipamentos) + "MOBMO" (mão-de-obra) | **Over-engineering:** MOB já é suficiente. Categorias internas (equipamentos, canteiro) resolvem classificação sem fragmentar. |
| **A4** | Incluir mobilização em cada atividade EAP | **Incorreto semanticamente:** Mobilização é *projeto-wide*, não por atividade. Causaria duplicação de custos. |

---

## 4. Consequências

### 4.1 Positivas

| ID | Consequência | Impacto |
|----|-------------|--------|
| **C1+** | Eliminação de rcpsp_spec redundante | ~80% redução de arquivo, single source of truth |
| **C2+** | Política clara e tipificada para MOB | Consistência entre benchmarks e projetos reais |
| **C3+** | Determinístico: scheduling derivado da timeline | Sem necessidade de entrada manual, menos erro |
| **C4+** | Integração honesta diretos+indiretos | Semântica clara: quem produz vs. quem suporta |
| **C5+** | Compatível com skill-05 (pool contracts) | ADR-071 pool-based costing ainda funciona se rcpsp_spec reutilizado para complexos |
| **C6+** | Backward compatible: legacy rcpsp_spec ignorado | Projetos antigos continuam válidos, nova política é opt-in |

### 4.2 Riscos / Negativos

| ID | Risco | Mitigação |
|----|------|-----------|
| **C1-** | Perda de flexibilidade se MOB phases rígidas | Permitir override de `mob_schedule` em inputs para casos complexos (não coberto por v1) |
| **C2-** | Integração com ADR-085 (custo instancial) | ADR-085 janelas temporais se alinham com MOB phases — compatível, não conflitante |
| **C3-** | Skill-04 (cronograma) precisa entender MOB fases | Skill-04 derivará automaticamente das datas de projeto e EAP — mudança pequena, bem-contida |

---

## 5. Plano de Implementação

### 5.1 Fases

| Fase | Entregas | Duração | Dependências |
|------|----------|---------|--------------|
| **1: Design & Spec** | ADR-105 completa, casos de teste de MOB | 1 sprint | — |
| **2: Skills Update** | Skill-04 (MOB window inference), Skill-07 (MOB cost distribution) | 2 sprints | Fase 1 |
| **3: Migration** | Converter 12 benchmarks: remover rcpsp_spec, popular MOB indiretos | 1 sprint | Fase 2 |
| **4: Validation** | Todos 12 benchmarks APROVADO, custos ≈ referência | 1 sprint | Fase 3 |
| **5: Production** | Deploy, deprecate rcpsp_spec, mark v2 schema legacy | 1 sprint | Fase 4 |

### 5.2 Estimativa de Esforço

- **Skill updates:** 80h (Skill-04: 30h, Skill-07: 40h, Skill-05 compat: 10h)
- **Migration:** 40h (12 benchmarks × 3h each)
- **Testing:** 60h (unit + integration + manual validation)
- **Total:** ~180h (~1 quarter se 20h/week)

---

## 6. Definition of Done

### 6.1 Fase 1 (Design)

- [x] ADR-105 escrita e revisada
- [x] Casos de teste documentados (MOB window, cost distribution)
- [x] Schema v3 de `spec.indiretos.MOB` definido
- [x] Compatibilidade com ADR-085, ADR-071 verificada

### 6.2 Fase 2 (Skills)

- [ ] Skill-04 testes passando (MOB window inference)
- [ ] Skill-07 testes passando (MOB mensal distribution)
- [ ] Skill-05 testes passando (rcpsp_spec compat maintained)
- [ ] Integration test: 1 benchmark com MOB phases APROVADO

### 6.3 Fase 3 (Migration)

- [ ] Todos 12 benchmarks convertidos (rcpsp_spec removido)
- [ ] Todos 12 benchmarks têm `spec.indiretos.MOB` populado
- [ ] Git commit com cleanup de rcpsp_spec code paths

### 6.4 Fase 4 (Validation)

- [ ] `run_benchmarks.py` 12/12 APROVADO
- [ ] Custos finais ≈ referência (delta < 1%)
- [ ] Skill-10 relatórios OK (sem "Custo total é zero")

### 6.5 Fase 5 (Production)

- [ ] rcpsp_spec marked @deprecated em code
- [ ] v2 schema docs marked legacy
- [ ] Release notes com migration guide

---

## 7. Exemplos Concretos

### 7.1 MATEC_GUARULHOS (Planejamento.txt → spec.indiretos.MOB)

**Antes (planejamento.txt):**
```
3.5: Mobilização e desmobilização     R$ 2.044.560,87
3.6: Desmobilização                   R$   408.912,17
INDML8: Despesas Gerais              (mensal)
```

**Depois (spec.indiretos):**
```json
"indiretos": [
  {
    "tipo": "MOB",
    "fase": "mobilizacao",
    "driver": "projeto",
    "custo_fixo_total": 2044560.87,
    "descricao": "Mobilização e aquisição de equipamentos"
  },
  {
    "tipo": "MOB",
    "fase": "desmobilizacao",
    "driver": "projeto",
    "custo_fixo_total": 408912.17,
    "descricao": "Desmobilização e restauração do sítio"
  },
  {
    "tipo": "MOB",
    "fase": "operacao",
    "driver": "mensal",
    "custo_fixo_mensal": 75000.00,     // R$ 900k/ano / 12 meses
    "descricao": "Despesas gerais de canteiro"
  },
  {
    "tipo": "ADM",
    "driver": "mensal",
    "custo_fixo_mensal": 384000.00
  }
]
```

**Cronograma inferido:**
```python
meta.data_inicio = "2025-01-15"
meta.data_termino = "2027-03-30"  # 27 meses

first_eap_date ≈ "2025-01-20"  # 5 dias depois do start
last_eap_date ≈ "2027-03-20"   # 10 dias antes do end

mob_schedule = {
  "mobilizacao": ("2025-01-15", "2025-01-19"),    # 5 dias
  "operacao": ("2025-01-15", "2027-03-30"),       # 27 meses
  "desmobilizacao": ("2027-03-20", "2027-03-30")  # 10 dias
}

# Custos:
# - Mobilização: R$ 2.044.560,87 na semana 1
# - Operação: R$ 75.000/mês × 27 meses = R$ 2.025.000
# - Desmobilização: R$ 408.912,17 na última semana
# Total MOB: ~R$ 4.478.473
```

### 7.2 Integração com BDI (ADR-090)

BDI é aplicado sobre custos diretos. MOB indiretos recebem BDI próprio:

```python
# skill-08 (Consolidação Financeira)

# Diretos (PUxQ)
custo_direto = sum(cpu.pu * qty for cpu in eap)

# Indiretos (MOB + outros)
custo_indireto_mob = (
    2044560.87 +           # Mobilização (projeto)
    75000 * 27 +           # Operação (mensal × duração)
    408912.17              # Desmobilização (projeto)
)

custo_indireto_adm = 384000 * 27  # ADM (mensal)
custo_indireto_total = custo_indireto_mob + custo_indireto_adm

# BDI sobre tudo
bdi_direto = custo_direto * bdi.diretos
bdi_indireto_mob = custo_indireto_mob * bdi.indireto
bdi_indireto_adm = custo_indireto_adm * bdi.adm

preco_venda = custo_direto + bdi_direto + custo_indireto_total + (bdi_indireto_mob + bdi_indireto_adm)
```

---

## 8. Relacionamento com ADRs Existentes

- **ADR-046 (RCPSP Completo):** Compatível. Se projeto complexo precisar pool scheduling, pode manter rcpsp_spec opcional como override.
- **ADR-054 (Workforce Mobilization Policy):** Complementa. ADR-054 foi genérica; ADR-105 é a política **tipificada**.
- **ADR-071 (Resource Contract Model):** Compatível. Pools em MOB são genéricos; instanciação via skill-05.
- **ADR-085 (Custo Instancial Composicional Temporal):** Compatível. MOB fases se alinham com janelas temporais.
- **ADR-090 (BDI Sistemático):** Compatível. MOB indiretos recebem BDI.

---

## 9. Próximos Passos

1. **Feedback dos stakeholders** (se proposto)
2. **Spec refinement** (se aprovado)
3. **Implementação Fase 1** (Design final, casos de teste)
4. **Skills update** (Fase 2)
5. **Migration** (Fase 3)

---

## 10. Autoria e Referências

- **Baseado em:** Análise de 12 benchmarks (2026-06-08), planejamento.txt patterns
- **Relacionado:** ADR-mobilizacao-desmobilizacao.md (doc. exploratório anterior)
- **Autor:** Engineering Team
- **Reviewed by:** (pending)

---
