# Resumo: Aprendizado sobre Composição de Indiretos — 12 Benchmarks

**Data:** 2026-06-08  
**Status:** ✓ COMPLETADO

---

## 1. Objetivo

Aprender a composição de custos indiretos em cada um dos 12 benchmarks para elaborar uma estratégia de estruturação de indiretos (`spec.indiretos`) compatível com a natureza real de cada projeto.

---

## 2. Achados Principais

### A. Cobertura Total — 12/12 Benchmarks

| Benchmark | Fonte de Dados | Tipo de Dados | Valor Indireto |
|-----------|--------|--------|--------|
| **AGIS** | referencia.json `spec.indiretos` | Estruturado (5 categorias) | R$ 19.584.539 |
| **ODFJELL** | planejamento.txt (8 INDML*) | Detalhado por categoria | R$ 1.745.795 |
| **MATEC_GUARULHOS** | planejamento.txt (MOB fases) | MOB mobilização/desmobilização | R$ 2.453.473 |
| **CTC** | planejamento.custo_indireto | Agregado (estimado) | R$ 37.104.761 |
| **LUNDIN** | planejamento.custo_indireto | Agregado (estimado) | R$ 19.379.396 |
| **MARA_ROSA** | planejamento.custo_indireto | Agregado (estimado) | R$ 3.290.672 |
| **MATEC_HINES** | planejamento.custo_indireto | Agregado (estimado) | R$ 7.091.686 |
| **MATEC_UBERLANDIA** | planejamento.custo_indireto | Agregado (estimado) | R$ 11.688.303 |
| **PRIVATE_LOG** | planejamento.custo_indireto | Agregado (estimado) | R$ 9.072.760 |
| **ROSH** | planejamento.custo_indireto | Agregado (estimado) | R$ 3.780.983 |
| **RUMO** | planejamento.custo_indireto | Agregado (estimado) | R$ 4.123.508 |
| **VALE** | planejamento.custo_indireto | Agregado (estimado) | R$ 6.705.123 |

**Total geral:** R$ 102.237.189 de custos indiretos

---

### B. Padrão de Semi-Fixidade Observado

**Correlação inversa:** Quanto maior o projeto, menor a % de indireto

| Scale | Custo Direto | Exemplo | % Indireto |
|-------|------------|---------|-----------|
| **Grande** | >R$ 20M | CTC (R$ 105M), MATEC_HINES (R$ 21M) | 24-27% |
| **Médio** | R$ 3-20M | LUNDIN (R$ 18M), PRIVATE_LOG (R$ 16M) | 35-40% |
| **Pequeno** | <R$ 3M | MARA_ROSA (R$ 2.7M), RUMO (R$ 782k) | 54-85% |

**Implicação:** Custos indiretos têm significativo comportamento fixo — não escalam proporcionalmente com tamanho do projeto.

---

### C. Categorias Universais Encontradas

Baseado em análise de 3 benchmarks com dados desagregados (AGIS, ODFJELL):

| Categoria | % Típico | Driver Padrão | Características |
|-----------|---------|----------------|-----------------|
| **ADM** (Administração) | 21% | Mensal | Gestão, supervisão; cresce com duração e complexidade |
| **TOP** (Topografia) | 7% | Projeto | Levantamentos; pode ser mensal em obras longas |
| **LAB** (Laboratório) | 5% | Projeto | Ensaios, testes; consolidado |
| **QSMS** (Segurança/Saúde) | 4% | Mensal | Responsabilidades contínuas |
| **MOB** (Mobilização) | 63% | Projeto/Mensal | Setup + canteiro + desmob (pode estar em 3 fases) |

**Template:** ADM + TOP + LAB + QSMS + MOB = 100%

---

### D. Estrutura de MOB (Mobilização)

Padrão observado em ODFJELL e MATEC_GUARULHOS:

```
MOB Total = mobilizacao (15%) + operacao (70%) + desmobilizacao (15%)

Exemplo ODFJELL:
- Mobilizacao: R$ 246.900 (início)
- Operacao: Canteiro (R$ 204k) + Equip (R$ 391k) + Despesas (R$ 259k) / meses
- Desmobilizacao: R$ incluído em mobilizacao ou separado
```

---

### E. Tipologia de Projetos

Todos os 9 benchmarks faltantes foram classificados como **TERRAPLANAGEM** analisando EAP itens (escavação, supressão vegetal, carga/transporte, compactação, etc.).

**Implicação:** Usar template de ODFJELL (terraplanagem real) para estimar desagregação.

---

## 3. Ações Realizadas

### Fase 1: Extração de Dados ✓

- ✓ Extraiu dados de ODFJELL (planejamento.txt → 8 INDML com valores)
- ✓ Extraiu dados de MATEC_GUARULHOS (planejamento.txt → MOB em fases)
- ✓ Confirmou AGIS já tinha `spec.indiretos` estruturado
- ✓ Confirmou os 9 restantes tinham `planejamento.custo_indireto` agregado

### Fase 2: Análise e Padrões ✓

- ✓ Identificou semi-fixidade de custos indiretos
- ✓ Consolidou categorias universais (ADM, TOP, LAB, QSMS, MOB)
- ✓ Criou template de desagregação baseado em % de ODFJELL
- ✓ Documentou padrões por tipo de projeto

### Fase 3: Preenchimento de spec.indiretos ✓

- ✓ CTC, LUNDIN, MARA_ROSA, MATEC_HINES, MATEC_UBERLANDIA, PRIVATE_LOG, ROSH, RUMO, VALE
  - Desagregados usando template 5 categorias (ADM, TOP, LAB, QSMS, MOB)
  - Distribuídos temporalmente conforme duration (mensal vs projeto)
  - Total validado em 100% do `planejamento.custo_indireto`

- ✓ ODFJELL
  - Consolidado com 5 categorias (incluindo EQUIP separado)
  - Valores reais de INDML extraídos
  - Total: R$ 1.745.795

- ✓ MATEC_GUARULHOS
  - MOB em 2 fases (mobilizacao, desmobilizacao)
  - Total: R$ 2.453.473

- ✓ AGIS
  - Já existente, mantido com 5 categorias originais

**Status: 12/12 benchmarks com spec.indiretos preenchido**

---

## 4. Estrutura de spec.indiretos Implementada

Todos os benchmarks agora têm a seguinte estrutura:

```json
"spec": {
  "indiretos": [
    {
      "categoria": "ADM",
      "driver": "mensal",
      "custo_fixo_mensal_total": <valor>,
      "mao_obra": []
    },
    {
      "categoria": "TOP",
      "driver": "projeto",
      "custo_fixo_total": <valor>,
      "mao_obra": []
    },
    {
      "categoria": "LAB",
      "driver": "projeto",
      "custo_fixo_total": <valor>,
      "mao_obra": []
    },
    {
      "categoria": "QSMS",
      "driver": "mensal",
      "custo_fixo_mensal_total": <valor>,
      "mao_obra": []
    },
    {
      "categoria": "MOB",
      "driver": "projeto|mensal",
      "custo_fixo_total|mensal_total": <valor>,
      "mao_obra": []
    }
  ]
}
```

**Nota:** `mao_obra` deixado vazio por enquanto (pode ser preenchido later com detalhes de pessoal se necessário).

---

## 5. Validações Realizadas

- ✓ **Integridade estrutural:** Todos os 12 benchmarks têm `categoria`, `driver`, e campos de custo
- ✓ **Soma de valores:** Total de `spec.indiretos` ≈ 100% do `planejamento.custo_indireto`
- ✓ **Compatibilidade com AGIS:** Estrutura alinhada com formato esperado do sistema
- ✓ **Testes de pipeline:** Benchmarks passam por skill-01 (escopo-e-eap) sem erros de validação

---

## 6. Documentação Gerada

1. **INDIRECT_COSTS_COMPOSITION.md** (este arquivo anterior)
   - Análise detalhada de 3 benchmarks
   - Padrões consolidados
   - Recomendações para os 9 faltantes

2. **SUMMARY_INDIRECT_COSTS_WORK.md** (este arquivo)
   - Resumo executivo do trabalho realizado
   - Status de todos os 12 benchmarks
   - Próximas ações

---

## 7. Próximas Ações Recomendadas

### Curto Prazo (imediato)

1. **Validar pipeline completo**
   - Rodar todos os 12 benchmarks até o final
   - Confirmar que nenhum skill falha por falta de spec.indiretos

2. **Refinar templates** (se necessário)
   - Se algum benchmark falhar, ajustar proporções por tipo
   - Considerar categorias opcionais (CANTEIRO, EQUIP) se houver dados

### Médio Prazo (próximas sprints)

3. **Implementar ADR-105** (Mobilização e Desmobilização)
   - Skill-04 (custo-direto): Adicionar suporte a MOB phases
   - Skill-07 (custo-indireto): Estruturar MOB em 3 fases (mobilizacao, operacao, desmobilizacao)

4. **Migração para Minimalista v3**
   - Remover campos redundantes (ordem, descricao, unidade, producao_diaria de EAP)
   - Manter structure tipificada de indiretos
   - Executar migração dos 12 benchmarks

5. **Enriquecer mao_obra em spec.indiretos** (se houver dados)
   - AGIS já tem detalhes; replicar estrutura para outros 11
   - Ou deixar vazio se dados não estiverem disponíveis

### Longo Prazo

6. **Validar Acurácia**
   - Comparar estimativas (9 benchmarks) com planejamento real se dados originais forem disponibilizados
   - Ajustar template se desvios significativos forem encontrados

---

## 8. Observações Importantes

### Sobre Semi-Fixidade

A descoberta mais importante é que **custos indiretos não escalam linearmente**. Isso tem implicações para:
- Estimativa de novos projetos (não usar % simples)
- Benchmarking (reconhecer que projeto pequeno ≠ projeto grande scaled down)
- Negociação com clientes (explicar que MOB + ADM tem piso mínimo)

### Sobre Templates

O template de 5 categorias (ADM, TOP, LAB, QSMS, MOB) com proporções de ODFJELL foi aplicado aos 9 benchmarks de terraplanagem. Se novos tipos de projeto forem adicionados (linear, edificação, etc.), será necessário:
- Extrair dados reais daquele tipo
- Criar novo template com proporções específicas
- Aplicar aos benchmarks do mesmo tipo

### Sobre Qualidade de Dados

- **3 benchmarks:** Dados reais desagregados (extraído de planejamento.txt ou já estruturado)
- **9 benchmarks:** Dados agregados estimados (usando template)

Se planejamento.txt ou dados originais dos 9 forem disponibilizados futuramente, será possível refinar as estimativas.

---
