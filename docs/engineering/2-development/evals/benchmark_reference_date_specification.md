# Benchmark Reference Data Specification & Pipeline Phase Evaluation

**Objetivo**: Definir dados de referência obrigatórios e critérios de avaliação por fase da pipeline de planejamento.

**Escopo**: Estrutura Concilium v1.0.0+ | MATEC Framework  
**Última Atualização**: 2026-05-10  
**Status**: DRAFT → PRODUCTION

---

## PARTE 1: DADOS DE REFERÊNCIA OBRIGATÓRIOS

### 1.1 Baseline de Custos Diretos

**Origem Autorizada**: `referencia.json.resultado.canonical.custo.direto_referencia_planilha`

**O que É**: Custo direto extraído de planilha de orçamento detalhada (item × quantidade × preço unitário).

**Formato Esperado**:
```json
{
  "direto_referencia_planilha": 19737601.15,
  "baseline_source": "benchmark_confronto_referencia",
  "status": "NORMALIZADO: usa direto_referencia_planilha como verdade única",
  "data_extracao": "2025-01-XX",
  "revisor": "Engenheiro Responsável"
}
```
BENCHMARK_REFERENCE_DATA_SPECIFICATION
**Validação**:
- ✓ Valor numérico > 0
- ✓ Não pode vir de derivação (equipes × custo/mês)
- ✓ Deve ter fonte documental rastreável
- ✓ Deve estar marcado como "NORMALIZADO"

**Por Que Importa**: É a âncora de toda avaliação. Sem isso, impossível validar deltas ferramenta vs realidade.

---

### 1.2 Custos Indiretos (ADR-009)

**Origem Autorizada**: `referencia.json.resultado.canonical.custo.indireto`

**O que É**: Custos de estrutura, administração, laboratório, QSMS, mobilização etc.

**Formato Esperado**:
```json
{
  "indireto": 5667419.90,
  "componentes": {
    "administracao": 2100000,
    "topografia": 800000,
    "laboratorio": 650000,
    "qsms": 1200000,
    "mobilizacao": 917419.90
  },
  "pct_custo_direto": 0.287,
  "baseline_source": "budget_item_aggregation"
}
```

**Validação**:
- ✓ Soma dos componentes = indireto total
- ✓ % sobre direto entre 20-40% (norma Mendes Lobo)
- ✓ Componentes desagregados (rastreabilidade)
- ✓ Fonte documentada

**Por Que Importa**: Diferencia custos de permanência (ADR-009). Crítico para replanejamento.

---

### 1.3 Regime de Trabalho (Dias/Semana, Horas/Dia)

**Origem Autorizada**: `canonical.regime`

**O que É**: Jornada e calendário contratuais da obra.

**Formato Esperado**:
```json
{
  "dias_semana": 6,
  "horas_dia": 8,
  "horas_semana": 48,
  "calendario_observancia": "BR_2025",
  "data_inicio": "2025-01-01",
  "data_termino": "2025-06-30",
  "semanas_uteis": 26,
  "dias_uteis": 156
}
```

**Validação**:
- ✓ horas_semana = dias_semana × horas_dia
- ✓ semanas_uteis × dias_semana = dias_uteis
- ✓ data_termino > data_inicio
- ✓ Calendário documentado (feriados, paralisações)

**Por Que Importa**: Base de todas as cálculos de produtividade e alocação de equipes.

---

### 1.4 Cronograma de Atividades (EAP)

**Origem Autorizada**: `referencia.json.cronograma.atividades[]`

**O que É**: Estrutura analítica de projeto com semanas, equipes, e durações.

**Formato Esperado**:
```json
{
  "cronograma": {
    "atividades": [
      {
        "id": "eap-1_2",
        "descricao": "Aterro compactado - Camadas progressivas",
        "unidade": "m³",
        "quantidade": 850000,
        "semanas": [
          {
            "numero": 1,
            "num_equipes": 2,
            "producao_semana": 32692.31,
            "status": "planejado"
          }
        ],
        "data_inicio": "2025-01-06",
        "data_termino": "2025-05-30"
      }
    ]
  }
}
```

**Validação**:
- ✓ Todas atividades têm id, descricao, unidade, quantidade
- ✓ Semanas contíguas de data_inicio até data_termino
- ✓ num_equipes > 0 para cada semana
- ✓ Quantidade total ≈ Σ(producao_semana)
- ✓ Unidades consistentes (não misturar m³ com un)

**Por Que Importa**: Insumo primário de cronograma.py. Erros aqui cascateiam para equipes e custos.

---

### 1.5 Declaração de Recursos (ADR-006)

**Origem Autorizada**: `canonical.recursos.equipes[]`

**O que É**: Composição, custo/mês e skills de cada equipe.

**Formato Esperado**:
```json
{
  "recursos": {
    "equipes": [
      {
        "id": "eq-terraplenagem-padrao",
        "nome": "Terraplenagem Padrão",
        "composicao": {
          "encarregado": 1,
          "operadores": 3,
          "serventes": 2
        },
        "custo_mes_brl": 45000,
        "custo_hora": 234.38,
        "produtividade": {
          "m3_hora": 12.5,
          "source": "historico_empresa"
        },
        "skills": ["terraplenagem", "compactacao"]
      }
    ]
  }
}
```

**Validação**:
- ✓ Todas equipes têm id, nome, composicao, custo_mes_brl
- ✓ custo_hora = custo_mes_brl / (horas_mes)
- ✓ Produtividade referenciada (não derivada)
- ✓ Skills mapeadas para EAP

**Por Que Importa**: Valida alocação de pessoas e custos de mão-de-obra (maior item em terraplenagem).

---

### 1.6 Perfil BDI (ADR-023)

**Origem Autorizada**: `canonical.perfil_bdi`

**O que É**: Taxa de Beneficiário Direto + Indireto + Lucro + Impostos aplicada a custo direto.

**Formato Esperado**:
```json
{
  "perfil_bdi": {
    "tributario": {
      "regime": "LUCRO_REAL",
      "municipio": "GUARULHOS_SP",
      "iss_aliquota_municipal": 0.05,
      "mao_obra": {
        "inss": 0.20,
        "fgts": 0.08,
        "contribuicao_sindical": 0.015
      },
      "material": {
        "icms": 0.18,
        "pis": 0.0165
      }
    },
    "lucro": {
      "mao_obra": 0.12,
      "material": 0.12,
      "servicos": 0.12,
      "indireto": 0.10
    },
    "bdi_efetivo": 0.15,
    "data_validacao": "2025-01-01"
  }
}
```

**Validação**:
- ✓ Regime tributário válido (LUCRO_REAL, LUCRO_PRESUMIDO, SIMPLES)
- ✓ Alíquotas dentro de range legais por município
- ✓ BDI efetivo = Σ(componentes) com coerência
- ✓ Data de validação registrada

**Por Que Importa**: Transforma custo direto em preço venda. 15% padrão Mendes Lobo, variável por projeto.

---

### 1.7 Ponto de Equilíbrio Operacional

**Origem Autorizada**: `referencia.json.ponto_equilibrio.canonical`

**O que É**: Break-even entre custo total com BDI e receita mínima viável.

**Formato Esperado**:
```json
{
  "ponto_equilibrio": {
    "canonical": {
      "custo_total_operacional": 25405681.52,
      "bdi_aplicado": 0.15,
      "preco_venda_operacional_com_bdi_15pct": 29216533.75,
      "margem_operacional_pct": 0.15,
      "resultado_balanco_ponto_equilibrio": 29216533.75
    },
    "benchmark_referencia": {
      "custo_total_referencia": 25405681.52,
      "margem_minima_aceitavel": 0.10,
      "preco_minimo_viavel": 27946249.67
    }
  }
}
```

**Validação**:
- ✓ custo_total_operacional = direto + indireto
- ✓ preco_venda = custo_total × (1 + bdi_aplicado)
- ✓ margem_operacional = bdi_aplicado
- ✓ Margem mínima ≥ 10% (Mendes Lobo target)

**Por Que Importa**: Define piso de negociação e viabilidade. Se preço mercado < ponto_equilibrio, projeto é inviável.

---

## PARTE 2: PIPELINE DE AVALIAÇÃO POR FASE

### 2.1 Fase 01: Praticabilidade

**Objetivo**: Validar que quantidade planejada é executável no regime contratado.

**Insumos Obrigatórios**:
- `canonical.regime` (dias, horas, calendário)
- `referencia.json.cronograma.atividades[]` (quantidades, durações)
- `canonical.recursos.equipes[].produtividade` (m³/hora ou equivalente)

**Outputs Esperados**:
```json
{
  "praticabilidade": {
    "status": "VIAVEL",
    "producao_semanal_media": 32692.31,
    "producao_mensal_media": 130769.23,
    "producao_total_planejada": 850000,
    "duracao_meses": 6.5,
    "utilization_media": 0.85,
    "bottleneck": "semana 4-5 (compactacao camada 3)",
    "margem_seguranca_pct": 15.2
  }
}
```

**Critérios de Avaliação**:
| Métrica | Alerta | Crítico | Esperado |
|---------|--------|---------|----------|
| `utilization_media` | < 60% | < 40% | 75-95% |
| `margem_seguranca_pct` | < 10% | < 5% | >15% |
| `duracao_meses` | > planejado + 2m | > planejado + 4m | = planejado ±1m |

**Red Flags** 🚩:
- Produtividade derivada (não referenciada)
- Número de equipes constante (ignora sazonalidade)
- Sem identificação de gargalos
- Cronograma com lacunas ou overlaps

**Recomendação**: Se utilization < 50%, considerar paralelização de atividades ou redução de escopo.

---

### 2.2 Fase 01A: Declarar Recursos

**Objetivo**: Registrar imutavelmente as equipes que serão alocadas.

**Insumos Obrigatórios**:
- `referencia.json.cronograma.atividades[].semanas[].num_equipes`
- `canonical.recursos.equipes[]` (composição, custo, skills)

**Outputs Esperados**:
```json
{
  "declaracao_recursos": {
    "equipes_alocadas": 3,
    "equipes_simultaneas_max": 2,
    "pessoas_max": 15,
    "lista_equipes": [
      {
        "id": "eq-terraplenagem-padrao",
        "semanas_alocacao": "1-26",
        "custo_total_brl": 1170000,
        "status": "declarado"
      }
    ]
  }
}
```

**Critérios de Avaliação**:
- ✓ Todas equipes usadas existem no catálogo
- ✓ Semanas de alocação são contíguas
- ✓ Não há sobreposição conflitante com outros projetos
- ✓ Custo total = Σ(equipes.custo_mes × meses_alocacao)

**Red Flags** 🚩:
- Equipe não catalogada
- Alocação com lacunas sem justificativa
- Custo divergente do esperado

---

### 2.3 Fase 02: Cronograma

**Objetivo**: Estruturar EAP e validar timeline viável.

**Insumos Obrigatórios**:
- `referencia.json.cronograma.atividades[]` (completo)
- `canonical.regime` (calendário)

**Outputs Esperados**:
```json
{
  "cronograma_validado": {
    "atividades_total": 4,
    "duracao_dias": 180,
    "data_inicio": "2025-01-01",
    "data_termino": "2025-06-30",
    "caminho_critico": ["eap-1_2", "eap-1_3"],
    "folga_max_dias": 45,
    "status": "VIAVEL"
  }
}
```

**Critérios de Avaliação**:
| Métrica | Alerta | Crítico |
|---------|--------|---------|
| Folga do caminho crítico | < 10 dias | < 5 dias |
| Atividades sem predecessoras | >2 | >3 |
| Duração vs regime | ±10% | ±20% |

**Red Flags** 🚩:
- Atividades com duração 0
- Sem identificação clara de caminho crítico
- Datas descontinuas
- Regime não validado

---

### 2.4 Fase 03: Equipes e Alocação

**Objetivo**: Validar que equipes alocadas suportam produção planejada.

**Insumos Obrigatórios**:
- `declaracao_recursos.equipes_alocadas`
- `cronograma_validado.atividades`
- `canonical.recursos.equipes[].produtividade`

**Outputs Esperados**:
```json
{
  "equipes_alocacao": {
    "status": "VIAVEL",
    "mapeamento_equipe_atividade": [
      {
        "atividade": "eap-1_2",
        "equipe": "eq-terraplenagem-padrao",
        "semanas_alocadas": 20,
        "producao_esperada": 640000,
        "producao_necessaria": 850000,
        "suficiencia_pct": 75.3
      }
    ],
    "deficit_equipamento": "None",
    "recomendacao": "Aumentar equipes na semana 4-8 ou renegociar prazo"
  }
}
```

**Critérios de Avaliação**:
| Métrica | Alerta | Crítico |
|---------|--------|---------|
| `suficiencia_pct` | < 85% | < 70% |
| Equipes não alocadas | >1 | >2 |
| Ociosidade média | > 30% | > 50% |

**Red Flags** 🚩:
- Suficiência < 70% sem plano de mitigação
- Equipes alocadas sem atividade mapeada
- Produtividade desatualizada

---

### 2.5 Fase 04: Planejamento BDI

**Objetivo**: Aplicar impostos, lucro e overhead ao custo direto.

**Insumos Obrigatórios**:
- `canonical.resultado.canonical.custo.total` (custo direto + indireto)
- `canonical.perfil_bdi` (tributação + lucro)

**Outputs Esperados**:
```json
{
  "bdi_aplicado": {
    "custo_direto": 19737601.15,
    "custo_indireto": 5667419.90,
    "custo_total": 25405681.52,
    "bdi_efetivo": 0.15,
    "preco_venda_bruto": 29216533.75,
    "margem_bruta": 3810851.23,
    "taxa_efetiva": "15.0%",
    "status": "CONSISTENTE"
  }
}
```

**Critérios de Avaliação**:
- ✓ BDI entre 12-18% (Mendes Lobo range)
- ✓ preco_venda = custo_total × (1 + bdi)
- ✓ Tributação validada contra município
- ✓ Lucro alinhado com diretrizes estratégicas

**Red Flags** 🚩:
- BDI < 12% (margem apertada) ou > 20% (questionável)
- Inconsistência tributária
- Prefixo sem documentação

---

### 2.6 Fase 05: Indiretos (ADR-009)

**Objetivo**: Detalhar e validar custos de permanência e overhead.

**Insumos Obrigatórios**:
- `referencia.json.resultado.canonical.custo.indireto` (com componentes)
- `canonical.regime.semanas_uteis`
- Histórico de alocação por mês

**Outputs Esperados**:
```json
{
  "indiretos_validado": {
    "indireto_total": 5667419.90,
    "indireto_mes_medio": 867297.68,
    "componentes": {
      "administracao": 2100000,
      "topografia": 800000,
      "laboratorio": 650000,
      "qsms": 1200000,
      "mobilizacao": 917419.90
    },
    "indireto_pct_direto": 0.287,
    "status": "DENTRO_PARAMETRO"
  }
}
```

**Critérios de Avaliação**:
| Componente | Range Normal | Mendes Lobo Target |
|------------|--------------|-------------------|
| Administração | 8-12% direto | 10.6% |
| Topografia | 2-4% | 3.2% |
| Laboratório | 2-3% | 2.6% |
| QSMS | 3-5% | 4.8% |
| Mobilização | 2-4% | 3.7% |
| **Total** | **20-35% direto** | **28.7%** |

**Red Flags** 🚩:
- Indireto > 35% direto (overhead excessivo)
- Indireto < 20% direto (subestimado)
- Componentes desagregados sem fonte

---

### 2.7 Fase 06: Consolidação Financeira

**Objetivo**: Conciliar custos diretos, indiretos, BDI e gerar resumo final.

**Insumos Obrigatórios**:
- Todas as fases anteriores

**Outputs Esperados**:
```json
{
  "consolidacao": {
    "custo_direto": 19737601.15,
    "custo_indireto": 5667419.90,
    "custo_total_sem_bdi": 25405681.52,
    "bdi_15pct": 3810851.23,
    "preco_venda": 29216533.75,
    "resultado_financeiro": 3810851.23,
    "margem_pct": 0.1288,
    "status_margem": "VERDE",
    "viabilidade": "PROJETO_VIAVEL"
  }
}
```

**Critérios de Avaliação**:
- ✓ Soma de componentes = total
- ✓ Margem ≥ 10% (mínimo Mendes Lobo)
- ✓ Status de viabilidade coerente com margem
- ✓ Não há valores negativos

**Red Flags** 🚩:
- Margem < 10%
- Viabilidade "INVIAVEL" sem recomendação
- Custos descontinuos entre fases

---

### 2.8 Fase 09: Diagnóstico de Criticidade (ADR-020)

**Objetivo**: Identificar atividades críticas, gargalos de equipes e riscos de margem.

**Insumos Obrigatórios**:
- `cronograma_validado` (caminho crítico)
- `equipes_alocacao` (suficiência)
- `consolidacao` (margem)

**Outputs Esperados**:
```json
{
  "diagnostico": {
    "atividades_criticas": ["eap-1_2", "eap-1_3"],
    "gargalos_identificados": [
      {
        "tipo": "EQUIPES",
        "semana": 4,
        "deficit": 1,
        "impacto": "atraso_14_dias",
        "severidade": "ALTA"
      }
    ],
    "margem_operacional_buffer": "12.88%",
    "risco_global": "MEDIO",
    "recomendacoes": [
      "Aumentar equipes na semana 4-8",
      "Validar produtividade em campo na semana 2"
    ]
  }
}
```

**Critérios de Avaliação**:
- ✓ Caminho crítico identificado
- ✓ Gargalos priorizados por impacto
- ✓ Recomendações acionáveis
- ✓ Margem de segurança documentada

---

### 2.9 Fase 10: Intervention & ROI

**Objetivo**: Analisar cenários de replanejamento e simular impacto financeiro.

**Insumos Obrigatórios**:
- Diagnóstico de criticidade
- Parâmetros de replanejamento (estender prazo, adicionar equipes, reduzir escopo)

**Outputs Esperados**:
```json
{
  "intervention": {
    "cenarios_simulados": [
      {
        "id": "cenario_add_equipes",
        "descricao": "Adicionar 1 equipe na semana 4-8",
        "custo_adicional": 234000,
        "impacto_prazo": "-7_dias",
        "margem_nova": 0.1245,
        "roi": "positivo_economia_atraso"
      }
    ],
    "cenario_recomendado": "cenario_add_equipes",
    "economia_potencial": 450000
  }
}
```

**Critérios de Avaliação**:
- ✓ Mínimo 2 cenários simulados
- ✓ ROI calculado (economia vs custo adicional)
- ✓ Impacto prazo documentado
- ✓ Margem recalculada

---

### 2.10 Fase 07: Adapter & Saída

**Objetivo**: Transformar canonical em outputs para diferentes stakeholders (relatórios, dashboards, APIs).

**Insumos Obrigatórios**:
- Todas fases anteriores (estado final consolidado)

**Outputs Esperados** (por canal):

**Canal 1: Relatório PDF Executivo**
```
RESUMO FINANCEIRO
├─ Custo Total: R$ 25.4M
├─ Preço Venda: R$ 29.2M
├─ Margem: 12.88% (VERDE)
└─ Status: VIAVEL

TIMELINE
├─ Duração: 6 meses
├─ Caminho Crítico: 2 atividades
└─ Risco: MÉDIO
```

**Canal 2: Dashboard BI**
```
KPIs
├─ Utilização Média: 85%
├─ Suficiência Equipes: 75%
├─ Margem vs Target: +2.88pp
└─ Viabilidade Score: 78/100
```

**Canal 3: API JSON** (consumido por ferramenta de portfólio)
```json
{
  "project_id": "matec-guarulhos",
  "financial_summary": {...},
  "timeline": {...},
  "resource_plan": {...},
  "risk_profile": {...}
}
```

**Critérios de Avaliação**:
- ✓ Todos stakeholders recebem dados apropriados
- ✓ Sem contradições entre canais
- ✓ Timestamps de atualização registrados
- ✓ Auditoria de acesso ativada

---

## PARTE 3: MATRIZ DE VALIDAÇÃO CRUZADA

### 3.1 Checklist de Integridade Pré-Benchmark

Antes de executar benchmark, validar:

```markdown
□ REFERÊNCIA
  □ direto_referencia_planilha > 0
  □ status = "NORMALIZADO"
  □ baseline_source documentado
  □ indireto > 0 com componentes desagregados
  □ ponto_equilibrio.preco_venda preenchido

□ CRONOGRAMA
  □ Todas atividades têm datas válidas
  □ Sem sobreposição de datas
  □ Semanas contíguas
  □ EAP mapeado para catálogo (CPUs)

□ RECURSOS
  □ Todas equipes existem em catálogo
  □ Composição validada
  □ Custo/mês > 0
  □ Produtividade referenciada (não derivada)

□ REGIME
  □ Dias/semana e horas/dia consistentes
  □ Calendário definido
  □ Semanas úteis > 0

□ BDI
  □ Percentual entre 12-18%
  □ Tributação coerente com município
  □ Lucro documentado

□ PIPELINE
  □ cronograma.py prioriza _derive_from_reference_schedule()
  □ spec_loader.py injeta baseline
  □ projection.py consome direto_referencia_planilha
```

### 3.2 Reconciliação Tripla

Após benchmark, validar convergência:

| Métrica | Referência | Canonical | Ferramenta | Delta |
|---------|-----------|-----------|-----------|-------|
| Custo Direto | 19.74M | ? | ? | <5% |
| Custo Total | 25.41M | ? | ? | <5% |
| Preço Venda | 29.22M | ? | ? | <5% |
| Margem % | 12.88% | ? | ? | <2pp |

**Tolerância**: <5% delta aceitável (arredondamento). Se >5%, investigar root cause.

---

## PARTE 4: GUIA DE TROUBLESHOOTING

### Problema: Delta > 30% em Custo Direto

**Checklist**:
1. Baseline é referência planilha? (não derivação equipes)
2. Todas equipes declaradas?
3. cronograma.py chamando _derive_from_reference_schedule()?
4. spec_loader.py injetando baseline?

**Ação**: Rodar diagnostic skill (09-diagnostico) com verbose=true.

---

### Problema: Margem Divergente Entre Fases

**Checklist**:
1. BDI consistente (fase 04)?
2. Indiretos atualizados (fase 05)?
3. Consolidação recalculou (fase 06)?

**Ação**: Re-rodar skill 06-consolidacao com force-recalculate.

---

### Problema: Cronograma Inviável

**Checklist**:
1. Praticabilidade (fase 01) passou?
2. Equipes suficientes (fase 03)?
3. Gargalos identificados (fase 09)?

**Ação**: Executar simulate_scenario_replan com extend_deadline +2semanas.

---

## PARTE 5: TEMPLATE DE VALIDAÇÃO PÓS-PIPELINE

```markdown
# VALIDAÇÃO BENCHMARK: [PROJECT_ID] - [DATA]

## ✓ GREEN FLAGS
- [ ] Baseline normalizado: referência = R$ X
- [ ] Deltas convergentes: <5%
- [ ] Margem operacional: Z% (VERDE)
- [ ] Cronograma viável: caminho crítico identificado
- [ ] Equipes suficientes: >85%

## ⚠ YELLOW FLAGS
- [ ] Gargalo identificado (semana X)
- [ ] Margem próxima ao limite (10-12%)
- [ ] Produtividade derivada (revalidar em campo)

## ✗ RED FLAGS
- [ ] Margem < 10% (INVIAVEL)
- [ ] Delta baseline > 10% (inconsistência crítica)
- [ ] Equipes < 70% (cobertura insuficiente)

## RECOMENDAÇÕES
- 1. [Ação prioritária]
- 2. [Ação secundária]
- 3. [Monitoramento em campo]

---
Validador: [Nome]  
Data: [Data]  
Status: ✓ APROVADO | ⚠ CONDICIONAL | ✗ REPROVADO
```

---

## PARTE 6: REFERÊNCIAS & DEPENDÊNCIAS

**ADRs Correlatos**:
- [ADR-006](../adrs/adr_006_team_composition.md): Composição de equipes
- [ADR-009](../adrs/adr_009_indirect_costs_as_first_class.md): Custos indiretos como first-class
- [ADR-020](../adrs/adr-020-criticidade-multidimensional.md): Criticidade multidimensional
- [ADR-023](../adrs/adr-023-bdi-diferenciado-por-categoria.md): BDI diferenciado por categoria
- [ADR-042](../adrs/): Structural Derivation (spec_loader)
- [ADR-043](../adrs/): Baseline Governance (em desenvolvimento)

**Sistemas Relacionados**:
- `concilium/benchmarks/data/*/referencia.json` (dados de referência)
- `concilium/src/concilium/application/benchmarks/` (pipeline skills)
- `concilium/config/catalogos/` (CPUs, insumos, equipes)

**Histórico de Normalização**:
- 2026-05-10: MATEC_GUARULHOS normalizado (+267% delta resolvido)
- Próxima: Extensão a 80+ projetos

---

**Próxima Versão**: v2.0 com Machine Learning para detecção automática de anomalias.

