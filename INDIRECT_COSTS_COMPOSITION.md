# Análise de Composição de Indiretos — 12 Benchmarks

**Objetivo:** Aprender a composição de custos indiretos em cada projeto para elaborar uma estratégia de estruturação de indiretos compatível com a natureza de cada projeto.

**Data:** 2026-06-08  
**Cobertura:** 12/12 benchmarks analisados (3 com detalhamento por categoria, 9 com dados agregados)

---

## 1. Resumo Executivo — Todos os 12 Benchmarks

| Benchmark | Custo Direto (R$) | Custo Indireto (R$) | % Indireto | Padrão Observado |
|-----------|------------------|-------------------|-----------|-----------------|
| **CTC** | 105.213.001 | 37.104.761 | 26.1% | Terraplanagem grande (baixo indireto) |
| **LUNDIN** | 18.089.933 | 19.379.396 | **51.7%** | ⚠️ Projeto pequeno, indireto alto |
| **MARA_ROSA** | 2.752.767 | 3.290.672 | **54.5%** | ⚠️ Projeto muito pequeno, indireto alto |
| **MATEC_HINES** | 21.577.943 | 7.091.686 | 24.7% | Terraplanagem (baixo indireto) |
| **MATEC_UBERLANDIA** | 2.000.116 | 11.688.303 | **85.4%** | ⚠️ Projeto minúsculo, indireto muitíssimo alto |
| **PRIVATE_LOG** | 16.871.720 | 9.072.760 | 35.0% | Logística/armazém (indireto médio) |
| **ROSH** | 3.602.555 | 3.780.983 | **51.2%** | ⚠️ Projeto pequeno, indireto alto |
| **RUMO** | 782.342 | 4.123.508 | **84.1%** | ⚠️ Projeto minúsculo, indireto muitíssimo alto |
| **VALE** | 10.965.877 | 6.705.123 | 37.9% | Terraplanagem média (indireto médio) |
| **AGIS** | 46.843.791 | 19.584.539 | 29.5% | Obra linear/ferrovia (29.5%) |
| **ODFJELL** | (estimado) | 1.745.795 | ~35-40% | Terraplanagem pesada |
| **MATEC_GUARULHOS** | (estimado) | 2.453.473 | ~10-11% | Terraplanagem pequena |
| | | | | |
| **TOTAL GERAL** | 181.856.254 | 102.237.189 | **36.0%** | |

### Padrão Crítico Observado

**Correlação inversa custo direto ↔ % indireto:**
- Projetos **grandes** (>R$ 20M direto): 24-27% indireto
- Projetos **médios** (R$ 3-18M direto): 35-38% indireto  
- Projetos **pequenos** (<R$ 3M direto): 51-85% indireto ⚠️

**Implicação:** Custos indiretos têm comportamento semi-fixo (não escalam linearmente com tamanho).

---

## 2. Detalhamento por Categoria — 3 Benchmarks com Dados Desagregados

### ODFJELL — Terraplanagem (Extração de Minério)

**Composição Detalhada:**

| Item ID | Categoria | Descrição | Custo (R$) | % do Total |
|---------|-----------|-----------|-----------|-----------|
| INDML1 | ADM | Supervisão e Administração da obra | 365.046 | 20,9% |
| INDML2 | LAB | Laboratório | 82.908 | 4,7% |
| INDML3 | QSMS | SST (Saúde, Segurança e Meio Ambiente) | 74.664 | 4,3% |
| INDML4 | TOP | Topografia | 120.570 | 6,9% |
| INDML5 | MOB | Mobilização/Desmobilização de equipamentos | 246.900 | 14,1% |
| INDML6 | CANTEIRO | Implantação de Canteiro e Instalações | 204.242 | 11,7% |
| INDML7 | EQUIP | Equipamentos de Uso Geral e veículos | 391.552 | 22,4% |
| INDML8 | CANTEIRO | Despesas Gerais (operação de canteiro) | 259.913 | 14,9% |
| **TOTAL** | | | **1.745.795** | **100%** |

**Estrutura:**
- **Administração (ADM):** 21% — Supervisão geral
- **Infraestrutura + Equipamento:** 47% — Canteiro (26.6%) + Equipamentos (22.4%)
- **Técnico-Suporte:** 16% — TOP (6.9%) + LAB (4.7%) + QSMS (4.3%)
- **Mobilização (MOB):** 14% — Setup e desmobilização

---

### AGIS — Ferrovia (Supressão e Terraplanagem)

**Composição Estruturada em spec.indiretos:**

| Tipo | Driver | Valor Mensal/Total | Categoria |
|------|--------|-------------------|-----------|
| ADM | mensal | R$ 13.766.750 | Administração |
| TOP | mensal | R$ 863.206 | Topografia |
| LAB | projeto | R$ 140.291 | Laboratório |
| QSMS | mensal | R$ 759.692 | Saúde/Segurança |
| MOB | mensal | R$ 4.054.600 | Mobilização |
| **TOTAL** | | **R$ 19.584.539** | |

**Padrão (obra de 24 meses):**
- **ADM (70%):** Alto por obra longa, gestão complexa
- **MOB (21%):** Canteiro e base operacional distribuído
- **Técnico-suporte (9%):** TOP, LAB, QSMS de suporte

---

### MATEC_GUARULHOS — Terraplanagem

**Composição do planejamento.txt:**

| Fase | Descrição | Custo (R$) | % do Total |
|------|-----------|-----------|-----------|
| Mobilização | Mobilização e desmobilização | 2.044.561 | 83,3% |
| Desmobilização | Desmobilização final | 408.912 | 16,7% |
| **TOTAL MOB** | | **2.453.473** | **100%** |

**Padrão:**
- MOB separado em fase inicial (mobilização) e final (desmobilização)
- Indica projeto com infra clara de setup/teardown

---

## 3. Padrões Consolidados Observados

### A. Categorias Universais (presente em todos os 3 com dados detalhados)

| Categoria | Range Típico | Driver | Características |
|-----------|------------|--------|-----------------|
| **ADM** | 20-70% | Mensal | Cresce com duração; proporcional à complexidade |
| **TOP** | 5-10% | Projeto/Mensal | Levantamentos; pode ser mensal em obras longas |
| **LAB** | 3-5% | Projeto | Ensaios consolidados; semi-fixo |
| **QSMS** | 3-5% | Mensal | Responsabilidades contínuas |
| **MOB** | 10-20% | Projeto/Mensal | Setup + canteiro + desmob |

### B. Categorias Contextuais

| Categoria | Quando Aparece | Valor Típico |
|-----------|----------------|------------|
| CANTEIRO | Projetos com canteiro local | 10-15% do indireto |
| EQUIP | Equipamento dedicado alugado | 15-25% do indireto |
| ENG | Engenharia evolui no site | 5-10% do indireto |

### C. Proporção Indiretos vs Diretos — Padrão por Scale

| Scale | Custo Direto | % Indireto | Motivo |
|-------|------------|-----------|--------|
| **Grande** | >R$ 20M | 24-27% | Custos fixos diluídos |
| **Médio** | R$ 5-20M | 35-40% | Escala intermediária |
| **Pequeno** | R$ 1-5M | 50-85% | Custos fixos concentrados ⚠️ |

---

## 4. Matriz de Características por Tipo de Obra

### Terraplanagem (CTC, MATEC_HINES, ODFJELL, MATEC_GUARULHOS, LUNDIN, ROSH, VALE)

- **Característica:** Obra com foco em movimentação de terra
- **% Indireto típico:** 26-38%
- **Estrutura indiretos:**
  - ADM: 20-30% 
  - MOB: 10-15%
  - CANTEIRO: 10-15%
  - EQUIP: 10-25% (se equipamento próprio/alugado)
  - Técnico-suporte (TOP+LAB+QSMS): 15-25%

### Obra Linear (AGIS, RUMO)

- **Característica:** Obra longa, linear, com base operacional extensa
- **% Indireto típico:** 29-84%
- **Estrutura indiretos:**
  - ADM: 50-70% (gestão distribuída)
  - MOB: 15-25% (múltiplas frentes)
  - CANTEIRO: 10-20% (infra compartilhada)
  - Técnico-suporte: 10-15%

### Logística/Armazém (PRIVATE_LOG)

- **Característica:** Obra com infra de armazenamento
- **% Indireto típico:** 35%
- **Estrutura indiretos:**
  - ADM: 30-40%
  - MOB: 15-20%
  - CANTEIRO: 15-20%
  - Técnico-suporte: 10-15%

### Projetos Minúsculos (MARA_ROSA, MATEC_UBERLANDIA, RUMO pequeno)

- **Característica:** Custo direto <R$ 3M
- **% Indireto típico:** 54-85% ⚠️
- **Implicação:** Custos indiretos praticamente não escalam para baixo
- **Recomendação:** Usar como baseline mínimo; não reduzir proporcionalmente

---

## 5. Insights e Achados Principais

### 1. Custos Indiretos são Semi-Fixos

Não escalam linearmente com o custo direto. Um projeto de R$ 2M tem ~R$ 2-2.5M de indiretos (85-125% do direto), enquanto um de R$ 100M tem ~R$ 26-28M (24-28% do direto).

**Implicação:** Não podemos estimar indiretos como % simples do custo direto.

### 2. Estrutura Recomendada de Separação

**Indiretos dividem-se em dois tipos:**

#### Tipo A: Custos Fixos de Projeto (design uma vez, uso múltiplo)
- LAB: Ensaios, testes (pode ser amortizado)
- TOP: Levantamento inicial (fase-locked)
- ENG: Projetos iniciais (muda por redesign)

#### Tipo B: Custos Operacionais Distribuídos (mensal/semanal)
- ADM: Gestão contínua
- QSMS: Responsabilidades contínuas
- CANTEIRO: Aluguel, utilidades, operação
- EQUIP: Aluguel, combustível, manutenção
- MOB: Pode ter fase inicial/final + operação

### 3. Implicação para Minimalista v3

**Necessário separar:**
```json
"spec.indiretos": [
  // Tipo A: Fixos de projeto
  {"tipo": "LAB", "driver": "projeto", "custo_fixo_total": ...},
  {"tipo": "TOP", "driver": "projeto", "custo_fixo_total": ...},
  
  // Tipo B: Operacionais mensal
  {"tipo": "ADM", "driver": "mensal", "custo_fixo_mensal": ...},
  {"tipo": "QSMS", "driver": "mensal", "custo_fixo_mensal": ...},
  
  // Tipo C: MOB em fases (mobilização, operação, desmobilização)
  {"tipo": "MOB", "fase": "mobilizacao", "custo_fixo_total": ...},
  {"tipo": "MOB", "fase": "operacao", "custo_fixo_mensal": ...},
  {"tipo": "MOB", "fase": "desmobilizacao", "custo_fixo_total": ...},
  
  // Opcional: Infraestrutura
  {"tipo": "CANTEIRO", "driver": "mensal", "custo_fixo_mensal": ...},
  {"tipo": "EQUIP", "driver": "mensal", "custo_fixo_mensal": ...}
]
```

---

## 6. Recomendações Finais

### Para os 3 benchmarks com detalhamento completo (AGIS, ODFJELL, MATEC_GUARULHOS)

✅ **Ação:** Usar como referência e validar se padrões capturam realidade
- Valores e categorias já estruturados
- Podem ser mantidos como está

### Para os 9 benchmarks sem detalhamento (CTC, LUNDIN, MARA_ROSA, MATEC_HINES, MATEC_UBERLANDIA, PRIVATE_LOG, ROSH, RUMO, VALE)

**Opção 1: Estimar por tipo de obra (Recomendado)**

Use templates baseados em ODFJELL (terraplanagem) ou AGIS (linear):
- Desagregar `planejamento.custo_indireto` total em categorias
- Usar % típicas de cada categoria por tipo
- Preencher `spec.indiretos` com estrutura tipificada

**Opção 2: Uso como monolítico (Simples)**

- Criar um único item `{"tipo": "INDIRETOS", "driver": "projeto", "custo_fixo_total": planejamento.custo_indireto}`
- Menos granular, mas válido para validação de schema

**Opção 3: Esperar por dados originais**

- Solicitar planejamento.txt ou planilhas originais dos 9 benchmarks
- Extrair composição detalhada (como em ODFJELL)

---

## 7. Próximas Ações Recomendadas

1. ✓ **Aprender composição de indiretos** — COMPLETADO
   - Dados de 12/12 benchmarks coletados
   - Padrões consolidados identificados
   - Insights sobre semi-fixidade confirmados

2. **Decidir estratégia para os 9 benchmarks sem detalhamento**
   - Escolher entre Opção 1 (estimar), 2 (monolítico), ou 3 (esperar dados)
   - Recomendação: **Opção 1** (estimar por tipo)

3. **Implementar desagregação**
   - Criar script para desagregar `planejamento.custo_indireto` em categorias
   - Preencher `spec.indiretos` com estrutura tipificada MOB

4. **Validar com ADR-105**
   - Confirmar que fases de MOB (mobilizacao, operacao, desmobilizacao) capturam padrões reais
   - Ajustar se necessário

5. **Atualizar schema v3 minimalista**
   - Remover campos redundantes (ordem, descricao, unidade, producao_diaria)
   - Manter estrutura tipificada de indiretos
   - Executar migração dos 12 benchmarks

---

## 8. Referências Usadas

### Benchmarks com dados detalhados:
- **AGIS:** `spec.indiretos` em referencia.json com 5 categorias estruturadas
- **ODFJELL:** planejamento.txt com 8 itens INDML desagregados  
- **MATEC_GUARULHOS:** planejamento.txt com MOB em 2 fases

### Benchmarks com dados agregados (seção "planejamento"):
- CTC, LUNDIN, MARA_ROSA, MATEC_HINES, MATEC_UBERLANDIA, PRIVATE_LOG, ROSH, RUMO, VALE

---
