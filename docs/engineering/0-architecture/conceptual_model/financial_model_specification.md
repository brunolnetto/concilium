# Especificação do Modelo Financeiro: Graus de Liberdade & Composição de BDI

**Documento**: Camada de Modelagem Financeira Concilium  
**Data**: 2026-05-12  
**Escopo**: Benchmark AGIS + Pipeline Concilium Geral  
**Status**: Especificação (Implementação Pendente)

---

## Resumo Executivo

O pipeline Concilium atualmente opera com 4 graus de liberdade interconectados que existem na planilha origem mas não foram ainda formalizados rigorosamente:

1. **Assincronia de Custo CPU vs EQUIPE**: Precificação unitária baseada em catálogo diverge da costing específica do projeto por equipe
2. **Dualidade da Estrutura de Atividades**: 52 atividades financeiras ≠ 8 entregáveis de cronograma (+ itens apenas de planejamento)
3. **Impacto de Composição de BDI**: Aplicação per-componente com decomposição de lucro (provisionado vs real)
4. **Estratégia de Agrupamento de Equipes**: Agregação de custos entre atividades evitando explosão conservadora

Este documento formaliza cada grau de liberdade, especifica os limites de código atuais e define as extensões de modelagem necessárias.

---

## Parte 1: Assincronia de Custo CPU vs EQUIPE

### 1.1 Estado Atual

**Precificação CPU (Baseada em Catálogo):**
- Origem: `config/catalogos/` e `spec.cpus.itens_eap` em referencia.json
- Tipo: Custos unitários genéricos do catálogo competitivo
- Parâmetros: CPU-ID → (preco_unitario, unidade, produtividade_base)
- Aplicação: Costing por-atividade na camada financeira
- Autoritária: Catálogo (potencialmente atualizado de feeds SICRO)

**Costing EQUIPE (Específica do Projeto):**
- Origem: `spec.equipes` em referencia.json (extraída da planilha origem)
- Tipo: Pacotes de custo de equipe específicos do projeto
- Parâmetros: EQUIPE-ID → (custo_fixo_mensal, permanencia, roster de mão_obra, lista de equipamentos)
- Aplicação: Alocação por-semana na camada de execução
- Autoritária: Planilha (override de nível do projeto)

**Assincronia Atual:**
```
Custo Financeiro (CPU):     C_fin = Σ(CPU_i.preco × qtd_i) + ajustes_BDI
Custo de Execução (EQUIPE): C_exec = Σ(EQUIPE_j.custo_fixo × semanas_j) + variáveis_j
Divergência:                ΔC = |C_fin - C_exec|
```

### 1.2 Regras de Reconciliação (A FORMALIZAR)

**Regra 1.2.1: Autoridade de Fonte de Custo**
Para cada atividade, especificar a fonte de custo autoritária:
```json
{
  "atividade_id": "eap-01",
  "cost_authority": "CPU | EQUIPE | BOTH_WITH_DELTA_AUDIT",
  "cpu_cost": 15000.00,
  "equipe_cost": 14200.00,
  "delta": -800.00,
  "delta_pct": -5.3,
  "reconciliation_note": "EQUIPE suborçada; usar CPU como base"
}
```

**Regra 1.2.2: Limiar de Divergência**
Definir divergência aceitável para cada atividade:
- Se |ΔC / C_fin| < 5% → usar CPU (catálogo é autoritário)
- Se 5% ≤ |ΔC / C_fin| < 20% → sinalizar para revisão, documentar decisão
- Se |ΔC / C_fin| ≥ 20% → DEVE reconciliar antes da aprovação

**Regra 1.2.3: Artefato de Reconciliação**
Gerar mapeamento para cada atividade:
```
atividade_id | descricao | cpu_cost | equipe_cost | delta_pct | authority | reason
eap-01       | Mobilização | 15000    | 14200       | -5.3      | CPU       | Mobilização padrão
eap-03       | MVP         | 45000    | 41000       | -8.9      | EQUIPE    | Override equipe projeto
...
```

### 1.3 Pontos de Implementação

**Arquivo**: `src/concilium/application/benchmarks/spec_loader.py`
- Atual: _extract_bdi_rates (L316)
- Adicionar: método _reconcile_cpu_equipe_costs()
- Saída: dict cost_authority em ProjectSpec

**Arquivo**: `scripts/audit_cpu_equipe_divergence.py` (NOVO)
- Propósito: Gerar matriz de reconciliação
- Entrada: referencia.json
- Saída: CSV com decisões de autoridade + log de auditoria

---

## Parte 2: Dualidade da Estrutura de Atividades

### 2.1 Estado Atual

**Camada Financeira (52 Atividades):**
- Origem: `spec.cpus.itens_eap` (52 itens, cada um com custo independente)
- Característica: Todos têm precificação explícita de CPU; alguns têm 0 semanas em cronograma
- Atividades Executadas (8): eap-01 a eap-07, eap-09 (has_cronograma: true)
- Atividades Planejamento (44): eap-08, eap-10 a eap-52 (has_cronograma: false)

**Camada de Execução (8 Entregáveis de Cronograma):**
- Origem: `spec.cronograma.atividades` com num_equipes > 0
- Característica: Alocação semanal em 30 semanas; vinculado a equipes
- Entregáveis AGIS: 1 MVP + 3 Drenagem = 4 primários; outros sintéticos/fallback

**Desalinhamento Atual:**
```
Financeira: eap-01 (MVP) ... eap-52 (52 itens)
            ↓ agrupar por fase projeto
Execução:   eap-01 (MVP semanal) + eap-10, eap-11, eap-12 (drenagem) + sintéticos
            ↓ 8 programados, 44 apenas planejamento
```

### 2.2 Estratégia de Agrupamento de Atividades (A FORMALIZAR)

**Estratégia 2.2.1: Definição de Entregável**
Agrupar 52 atividades em N entregáveis por fase/escopo do projeto:
```json
{
  "deliverables": [
    {
      "deliverable_id": "D-MVP",
      "name": "Mobilização e Campanha Preliminar",
      "atividades_ids": ["eap-01", "eap-02", "eap-03"],
      "has_cronograma": true,
      "weeks": [1, 2, 3],
      "primary_equipes": ["EQUIPE-1"],
      "financial_cost": 125000.00,
      "execution_cost": 120000.00
    },
    {
      "deliverable_id": "D-DRENAGEM-1",
      "name": "Drenagem Superficial",
      "atividades_ids": ["eap-10", "eap-11", "eap-12"],
      "has_cronograma": true,
      "weeks": [5, 6, 7, 8],
      "primary_equipes": ["EQUIPE-6"],
      "financial_cost": 280000.00,
      "execution_cost": 275000.00
    },
    {
      "deliverable_id": "D-PLANNING-RESERVED",
      "name": "Itens Planejamento & Reserva",
      "atividades_ids": ["eap-08", "eap-13" ... "eap-52"],
      "has_cronograma": false,
      "weeks": null,
      "primary_equipes": [],
      "financial_cost": 450000.00,
      "execution_cost": null,
      "treatment": "costed_unexecuted"
    }
  ]
}
```

**Estratégia 2.2.2: Regras de Agrupamento**
```
Regra 1: Mesma fase + mesma equipe primária → mesclar em um entregável
Regra 2: Equipes diferentes → entregáveis separados (pode ser paralelo)
Regra 3: Apenas planejamento (44 itens) → agregar a entregável "reservado" (costed mas unscheduled)
Regra 4: Validação cruzada: Σ(custos entregável) = Σ(custos atividade)
```

**Estratégia 2.2.3: Artefato de Mapeamento**
```
atividade_id | deliverable_id | sequence | weeks    | primary_equipe | grouping_rule | reconciliation
eap-01       | D-MVP          | 1        | [1,2,3]  | EQUIPE-1       | Regra 1       | grouped
eap-02       | D-MVP          | 2        | [1,2,3]  | EQUIPE-1       | Regra 1       | grouped
eap-03       | D-MVP          | 3        | [1,2,3]  | EQUIPE-1       | Regra 1       | grouped
eap-08       | D-PLANNING     | null     | null     | null           | Regra 3       | planning_only
eap-10       | D-DRENAGEM-1   | 1        | [5,6,7]  | EQUIPE-6       | Regra 1       | grouped
eap-11       | D-DRENAGEM-1   | 2        | [5,6,7]  | EQUIPE-6       | Regra 1       | grouped
```

### 2.3 Pontos de Implementação

**Arquivo**: `scripts/generate_deliverable_structure.py` (NOVO)
- Propósito: Gerar agrupamento de entregáveis de referencia.json
- Entrada: spec.atividades, spec.cronograma, spec.grupos_execucao
- Saída: deliverables.json com validação de reconciliação

**Arquivo**: `src/concilium/application/benchmarks/input_derivation/activity_grouping.py` (NOVO)
- Propósito: Motor formal de agrupamento para 52 → N entregáveis
- Métodos: _apply_grouping_rules(), _validate_cost_reconciliation()

---

## Parte 3: Impacto de Composição de BDI & Decomposição de Lucro

### 3.1 Estado Atual

**Tabela de BDI na Planilha Origem:**
```
{
  "bdi": {
    "material": 0.15,           # 15% markup sobre material
    "mao_obra": 0.28,           # 28% markup sobre mão de obra
    "servicos": 0.22,           # 22% markup sobre serviços
    "indireto": 0.12,           # 12% markup sobre indireto
    "diesel": 0.18              # 18% markup sobre diesel
  }
}
```

**Aplicação de BDI Atual (Skills 04/06):**
```python
# abordagem skill 06 (atual)
bdi_material = composition_pct['material'] * bdi_rate['material']
bdi_mao_obra = composition_pct['mao_obra'] * bdi_rate['mao_obra']
# ... per category
total_bdi = Σ(bdi_component)
final_cost = base_cost × (1 + total_bdi)
```

**Problema: Decomposição de Lucro Pouco Clara**
- Taxas de BDI são markups empíricos; elas embutem:
  - Lucro provisionado (lucro esperado do projeto)
  - Tarifas (trabalho, compensação, overhead operacional)
  - Margem de risco
- Código atual não separa estes; usuário quer:
  - Lucro provisionado: o que foi originalmente orçado como lucro
  - Lucro real: lucro real após remover tarifas de compensação/operacionais

### 3.2 Semântica de Composição de BDI (A FORMALIZAR)

**Modelo 3.2.1: Decomposição de BDI Baseada em Composição**

Para cada atividade com composição C = {material: x%, mao_obra: y%, servicos: z%, ...}:

```
Passo 1: Custo Base Por Componente
  C_material = base_cost × material_pct
  C_mao_obra = base_cost × mao_obra_pct
  C_servicos = base_cost × servicos_pct
  C_indireto = base_cost × indireto_pct
  C_diesel = base_cost × diesel_pct

Passo 2: Aplicação de BDI Por Componente
  BDI_material = C_material × bdi_rate['material']
  BDI_mao_obra = C_mao_obra × bdi_rate['mao_obra']
  BDI_servicos = C_servicos × bdi_rate['servicos']
  BDI_indireto = C_indireto × bdi_rate['indireto']
  BDI_diesel = C_diesel × bdi_rate['diesel']
  
  BDI_Total = Σ(BDI_component)

Passo 3: Custo com BDI
  Custo_com_BDI = base_cost + BDI_Total

Passo 4: Decomposição de Lucro (NOVO)
  BDI_bruto = BDI_Total
  
  Tarifas_decompostas = {
    'labor_tax': BDI_mao_obra × 0.15,          # ~15% de BDI trabalho é imposto/comp
    'operational': (BDI_material + BDI_servicos + BDI_indireto) × 0.08,  # ~8% overhead
    'diesel_tax': BDI_diesel × 0.12            # ~12% imposto combustível
  }
  
  Tarifas_total = Σ(Tarifas_decompostas)
  
  Lucro_provisionado = BDI_bruto × 0.40        # 40% de BDI é margem lucro
  Lucro_real = Lucro_provisionado - Tarifas_total
```

**Modelo 3.2.2: Artefato de Composição**

Para cada atividade, gerar relatório detalhado de impacto de BDI:
```json
{
  "atividade_id": "eap-01",
  "description": "Mobilização",
  "base_cost": 10000.00,
  "composition": {
    "material": 0.25,
    "mao_obra": 0.50,
    "servicos": 0.15,
    "indireto": 0.08,
    "diesel": 0.02
  },
  "component_costs": {
    "material": 2500.00,
    "mao_obra": 5000.00,
    "servicos": 1500.00,
    "indireto": 800.00,
    "diesel": 200.00
  },
  "bdi_by_component": {
    "material": 375.00,    # 2500 × 0.15
    "mao_obra": 1400.00,   # 5000 × 0.28
    "servicos": 330.00,    # 1500 × 0.22
    "indireto": 96.00,     # 800 × 0.12
    "diesel": 36.00        # 200 × 0.18
  },
  "bdi_total": 2237.00,
  "tariffs": {
    "labor_tax": 210.00,        # BDI_mao_obra × 0.15
    "operational": 212.96,      # (375 + 330 + 96) × 0.08
    "diesel_tax": 4.32          # 36 × 0.12
  },
  "tariffs_total": 427.28,
  "profit": {
    "lucro_provisionado": 894.80,    # 2237 × 0.40
    "lucro_real": 467.52             # 894.80 - 427.28
  },
  "final_cost": 12237.00,      # base_cost + bdi_total
  "final_cost_net_of_tariffs": 11809.72
}
```

### 3.3 Pontos de Implementação

**Arquivo**: `src/concilium/application/benchmarks/spec_loader.py`
- Atual: _extract_bdi_rates (L316)
- Adicionar: método _apply_bdi_composition_impact() com decomposição de lucro
- Saída: artefato de BDI detalhado em ProjectSpec

**Arquivo**: `src/concilium/application/skills/manifests/06-bdi/skill.py`
- Atual: Aplica BDI por categoria, sem breakdown de lucro
- Adicionar: Usar modelo de BDI decompostos de spec_loader
- Saída: Projeções de custo atualizadas com separação de lucro em saída de skill

**Arquivo**: `scripts/analyze_bdi_composition_impact.py` (NOVO)
- Propósito: Gerar relatório de composição de BDI para todas atividades
- Entrada: referencia.json com taxas de BDI + composições
- Saída: CSV/JSON com decomposição de BDI por atividade + artefatos de lucro

---

## Parte 4: Agrupamento de Composição de Equipes & Mitigação de Explosão Conservadora

### 4.1 Estado Atual

**Definições de EQUIPE (7 Equipes):**
```json
{
  "EQUIPE-1": {
    "custo_fixo_mensal": 50000,
    "permanencia": 3,           # meses
    "mão_obra": [{"funcao": "Engenheiro", "qtd": 2}, ...],
    "equipamentos": [{"tipo": "Escavadeira", "modelo": "CAT 320"}, ...]
  },
  "EQUIPE-2": { ... },
  ... (7 total)
}
```

**Mapeamento de Atividade-para-EQUIPE (Atual):**
```
eap-01, eap-02, eap-03 → EQUIPE-1
eap-10, eap-11, eap-12 → EQUIPE-6
eap-13 a eap-16        → EQUIPE-1, EQUIPE-2, EQUIPE-3 (agrupadas)
... (bandeiras requires_merge_schedule em referencia.json)
```

**Problema de Explosão Conservadora:**
Se custearmos cada atividade independentemente com suas equipes atribuídas, arriscamos:
- Duplicar custos da EQUIPE-1 se eap-01, eap-02, eap-03 todas reivindicam 100% da EQUIPE-1
- Não contabilizar compartilhamento de equipamento/trabalho entre atividades
- Subestimar ganhos de eficiência de agendamento consolidado

### 4.2 Estratégia de Agrupamento de Composição de Equipes (A FORMALIZAR)

**Estratégia 4.2.1: Níveis de Agrupamento**

**Nível 1: Atividade Individual (Sem Agrupamento)**
```
eap-01: {
  "primary_equipe": "EQUIPE-1",
  "cost_allocation": 1.0,        # 100% de custo EQUIPE-1 para duração
  "requires_grouping": false
}
```

**Nível 2: Agrupamento de Fase (Mesmas Equipes, Atividades Sequenciais)**
```
Fase "Mobilização" (eap-01, eap-02, eap-03):
  "equipes": ["EQUIPE-1"],
  "duration": 3,                 # semanas
  "cost_allocation": 1.0,        # Custo equipe completo (não duplicado 3x)
  "efficiency_factor": 1.05      # Ganho de eficiência 5% de agrupamento
```

**Nível 3: Agrupamento Paralelo (Equipes Diferentes, Atividades Concorrentes)**
```
Fase "Drenagem" (eap-10, eap-11, eap-12 paralelo com eap-13):
  "equipes": ["EQUIPE-6", "EQUIPE-1"],
  "parallel_factor": 1.0,        # Sem ganho eficiência (equipes disjuntas)
  "cost_allocation": 1.0 por equipe
```

**Nível 4: Otimização de Equipamento/Trabalho Compartilhado**
```
Atividades eap-13, eap-14, eap-15 (agrupadas como EQUIPE-1-2-3):
  "master_equipes": ["EQUIPE-1", "EQUIPE-2", "EQUIPE-3"],
  "shared_labor": {
    "Engenheiro": {
      "qty": 1,                  # Um engenheiro cobre todas 3 atividades
      "allocation_pct": [40%, 35%, 25%]  # distribuído através
    }
  },
  "shared_equipment": {
    "Escavadeira": {
      "qty": 1,                  # Uma escavadeira, time-shared
      "utilization": 0.95        # 95% utilização média
    }
  },
  "combined_cost": 150000,       # Agregado; evita duplicação
  "individual_allocated": [60000, 55000, 35000]  # Alocado de volta para atividades
}
```

**Estratégia 4.2.2: Algoritmo de Agrupamento**

```python
def group_team_compositions(atividades, equipes, grouping_config):
    """
    Entrada:
      - atividades: lista de {id, equipes[], duration, cost}
      - equipes: dict de {id, custo_fixo_mensal, mao_obra[], equipamentos[]}
      - grouping_config: {requires_merge_schedule[], groups[]}
    
    Saída:
      - grouped_activities: {id, deliverable_id, cost_allocated, efficiency_factor}
      - shared_resources: {activity_ids[], shared_labor{}, shared_equipment{}, total_cost}
    
    Algoritmo:
      1. Identificar limites naturais de agrupamento (fases, equipes, timing)
      2. Para cada limite:
         a. Calcular custo independente (Σ alocações per-atividade)
         b. Calcular custo agrupado (alocação equipe consolidada)
         c. Calcular fator eficiência = custo_agrupado / custo_independente
      3. Para atividades com recurso compartilhado:
         a. Mesclar equipes em pool mestre
         b. Alocar trabalho/equipamento compartilhado por tempo/atividade
         c. Calcular custo combinado
         d. Alocar de volta para atividades proporcionalmente
      4. Validar: Σ(alocado per-atividade) ≈ Σ(custos independentes) ± 5%
      5. Saída artefato de reconciliação
    """
```

**Estratégia 4.2.3: Artefato de Agrupamento**

```json
{
  "grouping_decisions": [
    {
      "group_id": "G-MVP",
      "type": "sequential",
      "atividades_ids": ["eap-01", "eap-02", "eap-03"],
      "equipes": ["EQUIPE-1"],
      "duration_weeks": 3,
      "independent_cost": 75000.00,        # Soma de alocações individuais
      "grouped_cost": 75000.00,            # Alocação consolidada
      "efficiency_factor": 1.00,           # Sem perda eficiência
      "allocated_per_activity": [25000, 25000, 25000]
    },
    {
      "group_id": "G-DRENAGEM-SHARED",
      "type": "shared_labor_equipment",
      "atividades_ids": ["eap-13", "eap-14", "eap-15"],
      "equipes": ["EQUIPE-1", "EQUIPE-2", "EQUIPE-3"],
      "duration_weeks": 8,
      "independent_cost": 240000.00,       # Se alocado separadamente
      "grouped_cost": 225000.00,           # Com otimização compartilhada
      "efficiency_factor": 0.94,           # Ganho eficiência 6%
      "shared_labor": {
        "Engenheiro": {
          "qty": 1,
          "allocation_pct": [0.40, 0.35, 0.25],
          "cost": 45000.00
        }
      },
      "shared_equipment": {
        "Escavadeira": {
          "qty": 1,
          "utilization": 0.95,
          "cost": 95000.00
        }
      },
      "allocated_per_activity": [85000, 74000, 66000]
    },
    {
      "group_id": "G-PLANNING-RESERVED",
      "type": "costed_unexecuted",
      "atividades_ids": ["eap-08", "eap-17", ... "eap-52"],
      "equipes": [],
      "independent_cost": 450000.00,
      "grouped_cost": 450000.00,
      "efficiency_factor": 1.00,
      "note": "Itens planejamento & reservado; sem agendamento execução"
    }
  ],
  "conservative_explosion_report": {
    "potential_duplication": 45000.00,     # Custo se agregado naivemente
    "optimization_savings": 15000.00,      # Economias reais de agrupamento
    "conservative_expansion_factor": 0.96  # Grupos usam 96% de soma naive
  }
}
```

### 4.3 Pontos de Implementação

**Arquivo**: `src/concilium/application/benchmarks/team_composition_grouping.py` (NOVO)
- Propósito: Motor formal de agrupamento de composição de equipes
- Métodos: identify_grouping_boundaries(), calculate_shared_resources(), allocate_costs()
- Saída: Artefato de agrupamento com fatores de eficiência

**Arquivo**: `scripts/analyze_team_grouping_opportunities.py` (NOVO)
- Propósito: Identificar riscos explosão conservadora e oportunidades otimização
- Entrada: referencia.json com equipes + atividades + mapeamentos
- Saída: Recomendações agrupamento + CSV ganhos eficiência

---

## Parte 5: Pontos de Integração & Roteiro de Implementação

### 5.1 Fechamento de Especificação

Cada grau de liberdade requer três artefatos:

| Grau de Liberdade | Especificação | Artefato de Reconciliação | Regra de Validação |
|---|---|---|---|
| Assincronia CPU vs EQUIPE | Regra 1.2.1-3 | cost_authority.json | Δ% < limiar |
| Dualidade Estrutura Atividades | Estratégia 2.2.1-3 | deliverables.json + mapping | Σ(custos del) = Σ(custos ativ) |
| Impacto Composição BDI | Modelo 3.2.1-2 | bdi_composition_report.json | consistência separação lucro |
| Agrupamento Composição Equipes | Estratégia 4.2.1-3 | grouping_decisions.json | validação efficiency_factor |

### 5.2 Sequência de Integração de Código

**Fase 1: Formalização (Scripts)**
1. `audit_cpu_equipe_divergence.py` → gerar cost_authority.json
2. `generate_deliverable_structure.py` → gerar deliverables.json
3. `analyze_bdi_composition_impact.py` → gerar bdi_composition_report.json
4. `analyze_team_grouping_opportunities.py` → gerar grouping_decisions.json

**Fase 2: Atualização de Motores Principais**
1. `spec_loader.py`: Adicionar _reconcile_cpu_equipe_costs(), _apply_bdi_composition_impact()
2. `activity_grouping.py`: Implementar algoritmo de agrupamento
3. `team_composition_grouping.py`: Implementar otimização de recurso compartilhado

**Fase 3: Atualização de Skills**
1. Skill 02 (cronograma): Usar saída de agrupamento de atividades
2. Skill 04 (equipes): Usar artefato de agrupamento de equipes
3. Skill 06 (bdi): Usar modelo de BDI decomposto com separação de lucro

**Fase 4: Relatório & Auditoria**
1. report_builder.py: Integrar agrupamento + decomposição lucro
2. audit_suite.py: Validar todos artefatos de reconciliação

### 5.3 Dependências & Bloqueadores

- **Bloqueador 1**: Planilha origem AGIS deve definir intenção de agrupamento explicitamente (quais atividades agrupam junto, quais equipes são compartilhadas)
- **Bloqueador 2**: Taxas de decomposição de tarifa de BDI precisam validação (que % de BDI é imposto trabalho vs operacional vs lucro)
- **Bloqueador 3**: Composição de atividade (% material/trabalho/etc por atividade) deve estar explícita em referencia.json (atualmente inferida)

---

## Parte 5: Pontos de Integração & Roteiro de Implementação

### 5.1 Fechamento de Especificação

Cada grau de liberdade requer três artefatos:

| Grau de Liberdade | Especificação | Artefato de Reconciliação | Regra de Validação |
|---|---|---|---|
| Assincronia CPU vs EQUIPE | Regra 1.2.1-3 | cost_authority.json | Δ% < limiar |
| Dualidade Estrutura Atividades | Estratégia 2.2.1-3 | deliverables.json + mapping | Σ(custos del) = Σ(custos ativ) |
| Impacto Composição BDI | Modelo 3.2.1-2 | bdi_composition_report.json | consistência separação lucro |
| Agrupamento Composição Equipes | Estratégia 4.2.1-3 | grouping_decisions.json | validação efficiency_factor |

### 5.2 Sequência de Integração de Código

**Fase 1: Formalização (Scripts)**
1. `audit_cpu_equipe_divergence.py` → gerar cost_authority.json
2. `generate_deliverable_structure.py` → gerar deliverables.json
3. `analyze_bdi_composition_impact.py` → gerar bdi_composition_report.json
4. `analyze_team_grouping_opportunities.py` → gerar grouping_decisions.json

**Fase 2: Atualização de Motores Principais**
1. `spec_loader.py`: Adicionar _reconcile_cpu_equipe_costs(), _apply_bdi_composition_impact()
2. `activity_grouping.py`: Implementar algoritmo de agrupamento
3. `team_composition_grouping.py`: Implementar otimização de recurso compartilhado

**Fase 3: Atualização de Skills**
1. Skill 02 (cronograma): Usar saída de agrupamento de atividades
2. Skill 04 (equipes): Usar artefato de agrupamento de equipes
3. Skill 06 (bdi): Usar modelo de BDI decomposto com separação de lucro

**Fase 4: Relatório & Auditoria**
1. report_builder.py: Integrar agrupamento + decomposição lucro
2. audit_suite.py: Validar todos artefatos de reconciliação

### 5.3 Dependências & Bloqueadores

- **Bloqueador 1**: Planilha origem AGIS deve definir intenção de agrupamento explicitamente (quais atividades agrupam junto, quais equipes são compartilhadas)
- **Bloqueador 2**: Taxas de decomposição de tarifa de BDI precisam validação (que % de BDI é imposto trabalho vs operacional vs lucro)
- **Bloqueador 3**: Composição de atividade (% material/trabalho/etc por atividade) deve estar explícita em referencia.json (atualmente inferida)

---

## Parte 6: Critérios de Sucesso

Após conclusão, o modelo financeiro fornecerá:

✅ **Transparência**: Cada custo na projeção final é rastreável para CPU ou plano EQUIPE, com decisões de reconciliação explícitas  
✅ **Acurácia**: 52 atividades financeiras mapeiam sem ambiguidade para N entregáveis com reconciliação custos < 5% delta  
✅ **Clareza de Lucro**: Markup de BDI decomposto em provisionado/real/tarifas com rastreabilidade per-componente  
✅ **Eficiência**: Otimizações de agrupamento de equipes documentadas com fatores de eficiência, evitando explosão conservadora  
✅ **Auditabilidade**: Todos 4 graus de liberdade modelados com artefatos formais (JSON/CSV) apoiando revisão compliance

---

## Apêndice: Artefatos de Referência (Caso AGIS)

**Estrutura de Atividades (Atual):**
- Executadas (8): eap-01 a eap-07, eap-09
- Planejamento (44): eap-08, eap-10 a eap-52
- Entregáveis (Proposto): D-MVP (3 atividades) + D-DRENAGEM-1/2/3 (4×3 atividades) + D-PLANNING (36 atividades)

**Taxas de BDI (Planilha):**
```
material: 15%, mao_obra: 28%, servicos: 22%, indireto: 12%, diesel: 18%
```

**Equipes EQUIPE (7):**
```
EQUIPE-1: Líder MVP + suporte
EQUIPE-2: Suporte drenagem
EQUIPE-3: Suporte drenagem
EQUIPE-4: Contingência
EQUIPE-5: Contingência
EQUIPE-6: Drenagem primária
EQUIPE-7: Reserva
```

**Requisitos de Agrupamento (Proposto):**
- EQUIPE-1, EQUIPE-2, EQUIPE-3: Requer merge_schedule (eap-13-16)
- EQUIPE-6: Requer merge_schedule (eap-10-12)
- Outros: Agendamento independente

---

**Próximo Passo**: Aprovar esta especificação, validar intenção da planilha origem AGIS, depois prosseguir com Fase 1 (geração de script).

