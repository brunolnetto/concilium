# Fluxo de Dados Através das Skills — Pipeline CMOC

**Propósito**: Rastrear como cada variável flui de skill para skill, transformações aplicadas, e pontos de integração críticos.

---

## VISÃO GERAL: N1 → N2 → N3 → N4

```
┌─────────────────────────────────────────────────────────────────────┐
│ CAMADA DE ENTRADA (N1)                                              │
├─────────────────────────────────────────────────────────────────────┤
│ • EAP_ITEMS (quantitativos)                                         │
│ • CRONOGRAMA (num_equipes_por_semana)                              │
│ • Contexto (data_inicio, regime_trabalho)                          │
│ • Catálogo (CPU, Producao, Insumo)                                 │
└─────────────────────────────────────────────────────────────────────┘
              ↓ SKILL-01
        ┌──────────────────────┐
        │ ESCOPO & EAP         │
        ├──────────────────────┤
        │ Output:              │
        │ • EAP validada       │
        │ • Quantitativos ✓    │
        │ • Precedências       │
        └──────────────────────┘
              ↓ SKILL-02
        ┌──────────────────────┐
        │ CALENDÁRIO & CLIMA   │
        ├──────────────────────┤
        │ Input: data_inicio   │
        │ Output:              │
        │ • β_i (fator clima)  │
        │ • Semanas válidas    │
        └──────────────────────┘
              ↓ SKILL-03
        ┌──────────────────────┐
        │ CATÁLOGO & INSUMOS   │
        ├──────────────────────┤
        │ Output:              │
        │ • CPU resolvidas     │
        │ • Producao resolvida │
        │ • Insumos carregados │
        └──────────────────────┘
┌─────────────────────────────────────────────────────────────────────┐
│ CAMADA N2: COMPOSIÇÃO DE EQUIPES                                    │
└─────────────────────────────────────────────────────────────────────┘
              ↓ SKILL-04
        ┌──────────────────────────────────────────┐
        │ CRONOGRAMA & DURAÇÃO                     │
        ├──────────────────────────────────────────┤
        │ Input:                                   │
        │ • EAP + quantitativos                    │
        │ • Producao.producao_horaria (ρ)          │
        │ • β_i (fator clima)                      │
        │ • CRONOGRAMA (n_equipes por semana)      │
        │                                          │
        │ Cálculo:                                 │
        │ ├─ Produção efetiva = ρ × β             │
        │ ├─ Duração = ⌈qty / (ρ×β×h×n_equipes)⌉ │
        │ ├─ Quantidade semanal = ρ×β×h×n_eq      │
        │ └─ Acumulado semanal                     │
        │                                          │
        │ Output:                                  │
        │ • cronograma[].atividades[] (semanas)    │
        │ • composicao_equipes_atividade[]         │
        │ • intervalos_atividade[]                 │
        └──────────────────────────────────────────┘
              ↓ SKILL-05
        ┌──────────────────────────────────────────┐
        │ EQUIPES & ALOCAÇÃO                       │
        ├──────────────────────────────────────────┤
        │ Input:                                   │
        │ • Cronograma de skill 04                 │
        │ • Producao.composicao_padrao_equipe      │
        │ • Insumo.preco_unitario                  │
        │                                          │
        │ Cálculo:                                 │
        │ ├─ Equipe-Hora (EH) = Σ pessoas × t     │
        │ ├─ Custo MO = EH × salario_h × 1.66     │
        │ ├─ Equipamento = n_eq × preco_h         │
        │ ├─ Combustível = L/h × preco_l          │
        │ └─ Custo_h total                        │
        │                                          │
        │ Output:                                  │
        │ • equipes_diretas[]                      │
        │ • custo_direto_por_semana[]              │
        │ • indiretos[] (ADM, TOP, LAB, etc)       │
        └──────────────────────────────────────────┘
┌─────────────────────────────────────────────────────────────────────┐
│ CAMADA N3: BRIDGE (DIAGNÓSTICO DE GAPS)                             │
└─────────────────────────────────────────────────────────────────────┘
        [Bridge interno a Skill 06]
        
        • Diagnostica gap_praticabilidade (nunca cobrado em N4)
        • Calcula fator_producao vs composição real
        • Identifica pool overhead
        • Nota: NÃO altera duração (mantém RCPSP)
┌─────────────────────────────────────────────────────────────────────┐
│ CAMADA N4: RESULTADO FINANCEIRO                                     │
└─────────────────────────────────────────────────────────────────────┘
              ↓ SKILL-06
        ┌──────────────────────────────────────────┐
        │ RESULTADO FINANCEIRO & VALIDAÇÃO         │
        ├──────────────────────────────────────────┤
        │ Input:                                   │
        │ • Equipes de skill 05                    │
        │ • Cronograma de skill 04                 │
        │ • CPU.preco_unitario (Fonte 2 fallback)  │
        │                                          │
        │ Cálculo (Precificação):                  │
        │ ├─ PU_sem_bdi = C_h / (ρ × β)            │
        │ ├─ BDI por categoria (SBDI)              │
        │ ├─ PU_com_bdi = PU_sem_bdi × (1+BDI)     │
        │ ├─ Subtotal = PU × qtd                   │
        │ └─ Planejamento[] (um por atividade)     │
        │                                          │
        │ Cálculo (Consolidação):                  │
        │ ├─ C_direto = Σ (custos_atividades)      │
        │ ├─ C_indireto = Σ (indiretos)            │
        │ ├─ C_total = C_direto + C_indireto       │
        │ ├─ Venda = C_total × (1 + Lucro + Trib)  │
        │ ├─ Margem = (Venda - C_total) / Venda    │
        │ └─ Status = VERDE/AMARELO/VERMELHO       │
        │                                          │
        │ Cálculo (Ponto de Equilíbrio):           │
        │ ├─ C_fixo_estrutural = ADM + TOP + ...   │
        │ ├─ frentes_necessarias = C_total / PU    │
        │ ├─ delta = Venda - C_total               │
        │ └─ Status_frentes = OK/AVISO/CRITICO     │
        │                                          │
        │ Output:                                  │
        │ • planejamento[] (PU, BDI, subtotal)     │
        │ • resultado.venda (sem BDI, com BDI)     │
        │ • resultado.custo (direto, indireto)     │
        │ • resultado.margem_pct                   │
        │ • ponto_equilibrio[]                     │
        └──────────────────────────────────────────┘
              ↓ SKILL-07
        ┌──────────────────────────────────────────┐
        │ CUSTOS & ANÁLISE SENSIBILIDADE           │
        ├──────────────────────────────────────────┤
        │ Input: Resultado de skill 06             │
        │ Output:                                  │
        │ • Curva de custo vs volume               │
        │ • Sensibilidade ±5%, ±10%, ±15%          │
        │ • Recomendações de ajuste                │
        └──────────────────────────────────────────┘
              ↓ SKILL-08
        ┌──────────────────────────────────────────┐
        │ PLANOS & RECONCILIAÇÃO                   │
        ├──────────────────────────────────────────┤
        │ • Compatibilidade com cronograma real     │
        │ • Simulações de replanejamento            │
        └──────────────────────────────────────────┘
              ↓ SKILL-09
        ┌──────────────────────────────────────────┐
        │ RELATÓRIO & ARTEFATOS                    │
        ├──────────────────────────────────────────┤
        │ Output:                                  │
        │ • PDF relatório completo                 │
        │ • Excel com planilhas consolidadas       │
        │ • PNG gráficos financeiros               │
        │ • JSON canonical final                   │
        └──────────────────────────────────────────┘
```

---

## RASTREAMENTO DE VARIÁVEIS-CHAVE

### Produtividade (ρ)

```
ENTRADA (N1)
├─ Catalogo.Producao.producao_horaria
│  └─ Armazenado em: `config/catalogos/mendeslobo/produtividades/CPU-TERRA-ATI-04X-PROD-001.json`
│     Valor ex: "producao_horaria": 582.75 (m²/h)
│
SKILL-04 (Cronograma)
├─ Lê producao_horaria via `resolve_catalogo_producao()`
├─ Aplica β_i (fator climático de skill 02)
├─ Calcula produção_efetiva = ρ × β
├─ Armazena em canonical.cronograma[].atividades[].producao_horaria
│
SKILL-05 (Equipes)
├─ Lê production_efetiva de skill 04
├─ Deriva custo_horario = C_h = ρ / custo_total_hora
│
SKILL-06 (Resultado)
├─ Lê planejamento[].produtividade_catalogo (ρ original)
├─ Lê planejamento[].beta_praticabilidade (β)
├─ Calcula PU_sem_bdi = C_h / (ρ × β)
└─ Rastreia em canonical.planejamento[].produtividade_catalogo
```

**Arquivo Central**: `config/catalogos/mendeslobo/produtividades/CPU-TERRA-ATI-04[1-9]-PROD-001.json`

---

### Custo Horário (C_h)

```
ENTRADA (N1)
├─ Catalog.Producao.composicao_padrao_equipe
│  └─ {"funcoes": [...], "equipamentos": [...]}
│  └─ Cada função tem `num_pessoas`, preco_unitario
│  └─ Cada equipamento tem `num_unidades`, preco_unitario
│
SKILL-05 (Equipes)
├─ Lê composicao_padrao_equipe
├─ Resolve preco_unitario para cada insumo (MO, EQ)
├─ Aplica encargos MO = salario × 1.66 (30% CLT + 31% prov + 5% admin)
├─ Calcula custo_horario:
│  ├─ C_h^MO = Σ(salario_mensal / 220h × pessoas × 1.66)
│  ├─ C_h^EQ = Σ(preco_unitario_mensal / 220h × unidades)
│  ├─ C_h^COMB = Σ(l_por_hora × preco_litro)
│  └─ C_h^MAT = (insumos composicao_itens da CPU) / producao_horaria
│
SKILL-06 (Resultado)
├─ Lê custo_operacional_real de skill 05
├─ Usa para calcular PU_sem_bdi
├─ Armazena em canonical.resultado.custo.direto_equipes
└─ Componentes por categoria: MO, EQ, COMBUSTÍVEL, MATERIAL
```

**Arquivo Central**: `src/concilium/application/skills/manifests/04-cronograma/_skill_helpers/_custos.py:72-156`

---

### Preço Unitário (PU)

```
ENTRADA (N1)
├─ CPU.composicao_itens[] (MATERIAL + COMBUSTÍVEL)
│  └─ Fallback quando Producao vazio
│
SKILL-04 (Cronograma)
├─ Calcula cronograma com ρ × β
│
SKILL-05 (Equipes)
├─ Calcula C_h de composição
│
SKILL-06 — PRECIFICAÇÃO (Resultado)
├─ Caminho A (Bottom-Up, recomendado)
│  ├─ PU_sem_bdi = C_h / (ρ × β)
│  ├─ Lê de: canonical.resultado.custo, planejamento[].produtividade_catalogo
│  └─ Armazena: planejamento[].preco_unitario
│
├─ Caminho B (Fallback Composição)
│  ├─ PU_sem_bdi = Σ(insumo_coef × preco_insumo)
│  ├─ Quando: composicao_padrao_equipe vazio ou erro resolução
│  ├─ Sinaliza: planejamento[].precificacao_via_fallback_composicao = true
│  └─ Armazena: planejamento[].preco_unitario
│
├─ Aplicação de BDI
│  ├─ BDI_MO = 34.7%, BDI_EQ = 34.7%, BDI_COMB = 4%
│  ├─ PU_com_bdi = PU_sem_bdi × (1 + BDI_médio_ponderado)
│  └─ Armazena: planejamento[].preco_unitario_com_bdi
│
└─ Subtotal
   ├─ Subtotal_sem_bdi = PU_sem_bdi × quantitativo
   ├─ Subtotal_com_bdi = PU_com_bdi × quantitativo
   └─ Armazena: planejamento[].subtotal.sem_bdi.total
```

**Arquivo Central**: `src/concilium/application/skills/manifests/06-resultado-financeiro/_precificacao/_skill_helpers/_preco_cpu.py`

---

### Cronograma (Quantidade Semanal)

```
ENTRADA (N1)
├─ CRONOGRAMA dict
│  ├─ {"SV-001": {"2026-W45": 2, "2026-W46": 2, ...}}
│  └─ {"SV-004": {"2026-W50": 7, ...}}
│
SKILL-04 (Cronograma)
├─ Valida num_equipes_por_item[item_id][semana] > 0
├─ Calcula para cada semana:
│  ├─ qtd_semanal = producao_efetiva × horas_semana × n_equipes × dias
│  ├─ qtd_acumulada += qtd_semanal
│  └─ Quando qtd_acumulada >= qtd_total → FIM
│
├─ Output: canonical.cronograma[].atividades[]
│  ├─ Cada atividade tem list de semanas
│  └─ Cada semana tem: periodo, numero_equipes, quantidade_semanal, acumulado
│
SKILL-05 (Equipes)
├─ Lê cronograma de skill 04
├─ Para cada semana_ativa:
│  ├─ equipe-hora = n_equipes × horas_semana
│  ├─ custo_semanal = equipe_hora × custo_horario
│  └─ custo_mensal_equivalente
│
SKILL-06 (Resultado)
├─ Valida: ∑(qtd_semanal) == quantitativo_total
├─ Usa para distribuir custos indiretos
└─ Calcula "frentes necessárias" = custo_total / PU_catálogo
```

**Arquivo Central**: `src/concilium/application/skills/manifests/04-cronograma/_skill_helpers/_spec.py:62-128`

---

### Custos Diretos

```
ENTRADA (N1)
├─ EAP_ITEMS com quantitativos
│
SKILL-04
├─ Define cronograma
│
SKILL-05
├─ Calcula custo_semanal = n_equipes × horas × custo_horario
├─ Subtotal atividade = ∑(custos_semanais)
│
SKILL-06
├─ Path: Precificação (_preco_cpu.py)
│  ├─ Coleta todos os subtotais de skill 05
│  ├─ Agrupa por atividade (SKU-001 até SV-009)
│  └─ Calcula PU_sem_bdi para cada atividade
│
├─ Path: Consolidação (_consolidacao.py)
│  ├─ Subtotal_sem_bdi = PU_sem_bdi × quantitativo (por atividade)
│  ├─ Subtotal_com_bdi = aplicar BDI (por categoria)
│  └─ C_direto_total = ∑(subtotais com BDI)
│
└─ Output: canonical.resultado.custo.direto_equipes
   ├─ Rastreado por categoria: MO, EQ, COMBUSTÍVEL, MATERIAL
   └─ Divisão: direto_sbdi (sem BDI) vs com_bdi (com BDI)
```

**Arquivo Central**: `src/concilium/application/skills/manifests/06-resultado-financeiro/_consolidacao/`

---

### Custos Indiretos

```
ENTRADA (N1)
├─ Contexto (data_inicio, regime_trabalho, permanencia)
│
SKILL-05
├─ Para cada categoria (ADM, TOP, LAB, QSMS, MOB):
│  ├─ Lê equipes e verbas do Indireto
│  ├─ MO = ∑(pessoas_indireta × salario × 1.66) × meses
│  ├─ EQ = ∑(equipamento × custo_mensal) × meses
│  ├─ VERBA = ∑(verbas_mensais + verbas_fixas)
│  └─ Custo_total[categoria] = MO + EQ + VERBA
│
SKILL-06
├─ Path: Consolidação
│  ├─ Lê Indireto[] de skill 05
│  ├─ Agrupa por categoria
│  ├─ C_indireto_total = ∑(custos.custo_total)
│  └─ Sub-custos: custo_mao_obra, custo_equipamentos, custo_verba
│
└─ Output: canonical.resultado.custo
   ├─ indireto_adm
   ├─ indireto_top
   ├─ indireto_lab
   ├─ indireto_qsms
   ├─ indireto_mob
   └─ total = direto_equipes + Σ(indiretos)
```

**Arquivo Central**: `src/concilium/application/skills/manifests/06-resultado-financeiro/_indiretos/`

---

### Venda & Resultado Financeiro

```
SKILL-06 — CONSOLIDAÇÃO
├─ Input: custos (direto + indireto)
│
├─ Path: Venda/Precificação (_venda_custo.py)
│  ├─ Metodologia A (Catálogo)
│  │  ├─ Venda_sem_bdi = ∑(subtotal.sem_bdi)
│  │  ├─ Venda_com_bdi = ∑(subtotal.com_bdi)
│  │  └─ BDI_efetivo = (venda_com_bdi - venda_sem_bdi) / venda_sem_bdi
│  │
│  └─ Metodologia B (Custo-Mais)
│     ├─ C_real_total = direto + indireto
│     ├─ Margem = LUCRO (9%) + TRIBUTOS (5.33%) = 14.33%
│     ├─ Venda_custo_plus = C_real_total × (1 + 0.1433)
│     └─ Se diferença com Metodologia A > threshold → AVISO
│
├─ Path: Margem Financeira
│  ├─ Resultado_financeiro = Venda - (direto + indireto)
│  ├─ Margem_pct = Resultado / Venda × 100
│  ├─ Status:
│  │  ├─ VERDE: 8% ≤ margem ≤ 10%
│  │  ├─ AMARELO: 5% ≤ margem < 8% ou 10% < margem ≤ 15%
│  │  └─ VERMELHO: margem < 5% ou > 15%
│  └─ Pode bloquear pipeline se VERMELHO
│
├─ Path: Ponto de Equilíbrio (_ponto_equilibrio.py)
│  ├─ Para cada atividade:
│  │  ├─ C_fixo_equipe = custo_operacional_real
│  │  ├─ Venda_cpu = subtotal_com_bdi
│  │  ├─ Delta = Venda_cpu - C_fixo_equipe
│  │  ├─ Frentes_necessarias = C_fixo_equipe / PU_sem_bdi
│  │  └─ Status:
│  │     ├─ OK: frentes ≤ 1.25
│  │     ├─ AVISO: 1.25 < frentes ≤ 1.5
│  │     └─ CRITICO: frentes > 1.5
│  │
│  └─ Agregado:
│     ├─ Total_hc (headcount operacional + indireto)
│     ├─ Custo_fixo_mensal
│     └─ Numero_equipes_diretas
│
└─ Output: canonical.resultado
   ├─ venda: {total_sem_bdi, total_com_bdi, total_custo_plus}
   ├─ custo: {direto_equipes, indireto_*, total}
   ├─ resultado_financeiro (R$)
   ├─ margem_pct (%)
   ├─ status_margem (VERDE/AMARELO/VERMELHO)
   ├─ ponto_equilibrio[] (por atividade)
   └─ balanco_ponto_equilibrio (agregado)
```

**Arquivo Central**: `src/concilium/application/skills/manifests/06-resultado-financeiro/_consolidacao/_skill_helpers/`

---

## PONTOS DE INTEGRAÇÃO CRÍTICOS

### 1. Ligação Skill 04 ↔ Skill 05

| Variável | Skill 04 (Envia) | Skill 05 (Recebe) | Validação |
|----------|-----------------|------------------|-----------|
| `cronograma[].atividades[]` | Define | Lê composição | Semanas alinhadas? |
| `quantidade_semanal` | Calcula | Usa para custo | ∑ = quantitativo_total? |
| `numero_equipes` | Define | Multiplica horas | > 0 sempre? |
| `producao_efetiva` | ρ × β | Valida contra C_h | Ratio consistente? |

### 2. Ligação Skill 05 ↔ Skill 06

| Variável | Skill 05 (Envia) | Skill 06 (Recebe) | Validação |
|----------|-----------------|------------------|-----------|
| `equipes_diretas[]` | Define composição | Calcula C_h / ρ | PU > 0? |
| `custo_semanal` | Agregado | Valida contra venda | Margem saudável? |
| `indiretos[]` | Calcula custos | Consolida | C_indireto < C_direto? |

### 3. Bridge Interno a Skill 06 (N3 → N4)

```
N3 (Diagnóstico)
├─ gap_praticabilidade = (producao_catálogo - producao_real) × custo_h
│
N4 (Real)
├─ custo_operacional_real = EH_real × custo_horario
│
Limitação (ADR-148)
└─ gap_praticabilidade diagnosticado em N3, MAS NUNCA entra em N4
   (duração não é estendida, mantém RCPSP computável)
```

---

## PIPELINE DE TRANSFORMAÇÃO — EXEMPLO CONCRETO (SV-001)

```
┌─ ENTRADA (N1)
│  └─ quantitativo = 169.798,78 m²
│     cpu_id = CPU-TERRA-ATI-041
│     cronograma = {2026-W45:2, 2026-W46:2, ...}
│
├─ SKILL-04
│  ├─ Producao.producao_horaria = 582,75 m²/h (ρ)
│  ├─ β_i (Nov) = 0,90
│  ├─ producao_efetiva = 582,75 × 0,90 = 524,475 m²/h
│  ├─ horas_semana = 48 (6 dias × 8h)
│  ├─ Semana W45: qtd = 524,475 × 48 × 2 = 50.350 m² (acum = 50.350)
│  ├─ Semana W46: qtd = 50.350 m² (acum = 100.700)
│  ├─ Semana W47: qtd = 50.350 m² (acum = 151.050)
│  └─ Semana W48: qtd = 18.749 m² (acum = 169.799 ≈ total) ✓
│
├─ SKILL-05
│  ├─ Producao.composicao_padrao_equipe = {pessoas: 4, equipamentos: 2}
│  ├─ C_h^MO = (6.300 + 2.525×3) / 220 × 1,66 = R$ 272,44/h
│  ├─ C_h^EQ = (62.400 + 8.500×3) / 220 = R$ 402,27/h
│  ├─ C_h^COMB = 1.095,31/h (diesel)
│  ├─ C_h^MAT = insumos compos / ρ = 0,73/h (mínimo)
│  ├─ C_h_total = 1.770,75/h
│  │
│  ├─ Semana W45: E.H. = 2 eq × 48h = 96 EH
│  ├─ Custo_sem_encargo = 96 × 1.770,75 = R$ 170.152
│  │
│  └─ Equipes_diretas[SV-001] = [{...semanas W45-W48, custos}]
│
├─ SKILL-06 (PRECIFICAÇÃO)
│  ├─ C_h / ρ = 1.770,75 / 582,75 = R$ 3,04/m² (sem BDI)
│  │  [Observação: Valor real pode divergir se composição ajustada]
│  │
│  ├─ BDI aplicado por categoria
│  │  ├─ PU_MO = 0,73 × (1 + 0,347) = R$ 0,98/m²
│  │  ├─ PU_EQ = 0,69 × (1 + 0,347) = R$ 0,93/m²
│  │  ├─ PU_COMB = 1,88 × (1 + 0,04) = R$ 1,95/m²
│  │  └─ PU_com_bdi = R$ 4,09/m²
│  │
│  └─ Planejamento[SV-001] = {
│         preco_unitario: {material: 0.42, diesel: 1.88, mao_obra: 0.73, eq: 0.69},
│         bdi: {material: 0.347, diesel: 0.04, mao_obra: 0.347, eq: 0.347},
│         preco_unitario_com_bdi: {total: 4.09},
│         subtotal: {sem_bdi: 515.698, com_bdi: 694.657}
│     }
│
├─ SKILL-06 (CONSOLIDAÇÃO — agregado 9 atividades)
│  ├─ Σ(subtotal.com_bdi) = R$ 10.650.000 (venda com BDI catálogo)
│  ├─ Σ(custos equipes) = R$ 4.200.000 (direto)
│  ├─ Σ(custos indiretos) = R$ 850.000 (ADM, TOP, LAB, QSMS, MOB)
│  ├─ C_total = R$ 5.050.000
│  │
│  ├─ Venda_metodologia_B = 5.050.000 × (1 + 0,1433) = R$ 5.773.165
│  │
│  ├─ Resultado = 5.773.165 - 5.050.000 = R$ 723.165
│  ├─ Margem_pct = 723.165 / 5.773.165 = 12,5%
│  └─ Status_margem = AMARELO (10% < 12,5% ≤ 15%)
│
└─ SKILL-07+
   ├─ Analisa sensibilidade ±5%, ±10%, ±15%
   ├─ Recomenda ajustes de cronograma ou composição
   └─ Output: Relatório final + Excel + PDF
```

---

**Versão**: 1.0  
**Data**: 2026-08-13
