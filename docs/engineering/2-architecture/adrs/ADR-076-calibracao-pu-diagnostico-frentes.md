# ADR-076 — Calibração de PU e Diagnóstico Quantitativo de Frentes em `ponto_equilibrio`

**Status:** Implementado  
**Data:** 2026-05-26  
**Autores:** Bruno Peixoto, Claude Sonnet 4.6  
**Contexto:** ADR-060 (Ponto Equilíbrio), ADR-071 (Pool Contracts), ADR-072 (Productive Duration), ADR-075 (Multi-Algo Compare)

---

## 1. Contexto

Após ADR-071 e ADR-072, o `ponto_equilibrio` (skill-08) acumulou duas fontes de custo
que não eram visíveis ao gestor no entregável:

1. **Custo de escala de equipes** — RCPSP (skill-04) aloca N equipes simultâneas por
   item para comprimir o prazo; o catálogo assume 1 equipe × taxa teórica. A diferença
   aparecia opaca no total consolidado.

2. **Overhead de pool contracts** — skill-05 adiciona custo de ociosidade por contratos
   compartilhados entre itens (`custo_pool_overhead`). O impacto por item não era visível.

O PU de venda continuava sendo o PU de catálogo, sem uma indicação do ajuste mínimo
necessário para atingir margem zero dado o custo operacional real.

---

## 2. Decisão

Implementar **Opção C** (diagnóstico quantitativo de frentes) e **Opção D** (calibração
de PU) como extensão do modelo `PontoEquilibrio` existente, sem criar novo skill.

### 2.1 Opção C — Diagnóstico Quantitativo de Frentes

Novos campos em `PontoEquilibrio`:

| Campo | Fórmula | Descrição |
|-------|---------|-----------|
| `frentes_equivalentes_necessarias` | `custo_total_autonomo / (pu_sem_bdi × Q)` | Razão execução real / receita catálogo |
| `gap_pool_overhead` | `custo_operacional_real − custo_total_autonomo` | Overhead de pool isolado |
| `status_frentes` | `OK ≤ 1.25, AVISO ≤ 1.5, CRITICO > 1.5` | Semáforo de risco de margem |

Validator `VAL-FRENTES-NECESSARIAS-ALTA` (skill-08):
- `AVISO` quando `frentes_equivalentes_necessarias > 1.25`
- `ERRO` quando `frentes_equivalentes_necessarias > 1.5`

### 2.2 Opção D — Calibração de PU

| Campo | Fórmula | Descrição |
|-------|---------|-----------|
| `pu_catalogo_unitario` | `subtotal.sem_bdi.total / Q` | PU auditável pelo catálogo |
| `pu_calibrado_unitario` | `max(pu_catalogo, custo_total_autonomo / Q)` | PU mínimo para margem zero |
| `ajuste_minimo_pct` | `(pu_calibrado − pu_catalogo) / pu_catalogo × 100` | Ajuste percentual sobre catálogo |
| `gap_praticabilidade_abs` | `custo_total_autonomo − (custo_fixo_mensal × permanencia_nominal)` | Efeito praticabilidade |
| `gap_pool_abs` | alias de `gap_pool_overhead` | Overhead de pool (alias semântico) |

### 2.3 Justificativa de Lesão de Produtividade Horária

Campos derivados de `ScheduledActivityCanonical.distribuicao_semanal`:

| Campo | Descrição |
|-------|-----------|
| `n_equipes_efetivo` | Número de equipes ponderado por semanas-equipe |
| `semanas_ativas` | Semanas com ≥ 1 equipe alocada |
| `fator_clima_medio` | Média ponderada de `fator_clima` por semana-equipe |
| `fator_calendario_medio` | Média ponderada de `fator_calendario` por semana-equipe |
| `semanas_lesadas_clima` | Semanas com `fator_clima < 0.90` |
| `gap_escala_abs` | `custo_total_autonomo − (pu_catalogo × Q)` |
| `diagnostico_lesao` | String auto-gerada descrevendo cada fonte de lesão |

Formato do `diagnostico_lesao`:
```
"N equipes simultâneas (compressão de prazo): +X% custo sobre 1 equipe. | Y sem. de Z com clima < 90% (f_clima=W, lesão L%). | Overhead de pool: R$ P."
```

---

## 3. Alternativas Rejeitadas

### Opção A — Novo skill entre skill-06 e skill-07
Exigiria reestruturar o grafo de dependências e o scheduler de skills. Overhead
arquitetural excessivo para o que é essencialmente um enriquecimento de campos
de um modelo já existente.

### Opção B — Mostrar gap no Markdown sem campo no modelo
Sem persistência no modelo `PontoEquilibrio`, o campo não estaria disponível para
validação automática, análise downstream ou serialização em JSON/banco. Rejeitado
por violar o princípio de _computable fields over derived display_.

---

## 4. Consequências

### 4.1 Positivas

- `ponto_equilibrio` agora é **auto-explicativo**: cada item carrega sua própria
  justificativa de custo (escala, clima, pool).
- O gestor vê o ajuste mínimo necessário para atingir margem zero sem precisar
  cruzar planilhas manualmente.
- `VAL-FRENTES-NECESSARIAS-ALTA` alerta automaticamente quando o custo autônomo
  supera 1.25× o PU de catálogo × Q.
- O Markdown gerado por `runtime.py` inclui 3 novas seções:
  - `_md_ponto_equilibrio` expandido (Frentes Nec., Gap Pool, Status)
  - `_md_calibracao_pu` (tabela: PU catálogo, PU calibrado, ajuste%, gaps)
  - `_md_lesao_produtividade` (tabela: N Equipes, Sem. Clima, f_clima, Diagnóstico)

### 4.2 Negativas / Atenções

- `PontoEquilibrio` cresce de 7 para 22 campos; o modelo é mais rico mas mais verboso.
- `gap_praticabilidade_abs ≈ 0` por construção matemática quando `permanencia_nominal`
  coincide com a duração planejada — não é um bug, é o comportamento esperado (a
  praticabilidade se manifesta como prazo estendido, não como custo unitário elevado).
- `_build_pe_for_equipe` agora aceita 4 parâmetros opcionais; chamadas legadas sem
  `sched_por_item` produzem valores padrão (sem lesão de clima/escala).

---

## 5. Implementação

### 5.1 Arquivos Modificados

| Arquivo | Mudança |
|---------|---------|
| [canonical.py](../../../../src/concilium/domain/models/canonical.py) | +15 campos em `PontoEquilibrio` (linhas ~473–510) |
| [_skill_helpers_a.py (skill-08)](../../../../src/concilium/application/skills/manifests/08-consolidacao-financeira/_skill_helpers_a.py) | `_lesao_from_sched`, `_build_diagnostico_lesao`, extensão de `_build_pe_for_equipe`, `_validate_frentes_necessarias` |
| [runtime.py](../../../../src/concilium/application/runtime.py) | `_md_calibracao_pu`, `_md_lesao_produtividade`, expansão de `_md_ponto_equilibrio` |

### 5.2 Arquivos Criados

| Arquivo | Descrição |
|---------|-----------|
| [tests/unit/test_adr076_pe_calibracao.py](../../../../tests/unit/test_adr076_pe_calibracao.py) | 33 testes unitários (todos passando) |
| [benchmarks/analysis/adr076_agis_impact.py](../../../../benchmarks/analysis/adr076_agis_impact.py) | Análise de impacto no benchmark AGIS |
| [benchmarks/analysis/adr076_memorial_calculo.py](../../../../benchmarks/analysis/adr076_memorial_calculo.py) | Memorial de cálculo completo com decomposição por item e análise de ociosidade de pool |

### 5.3 Cobertura de Testes

| Suite | Testes | Cobre |
|-------|--------|-------|
| `TestBuildPeForEquipeNewFields` | 10 | gap_pool, frentes_nec, pu_catalogo/calibrado, gap_praticabilidade, regressão legado |
| `TestStatusFrentesThreshold` | 5 | OK ≤ 1.25, AVISO ≤ 1.5, CRITICO > 1.5 |
| `TestValidacaoFrentesNecessarias` | 5 | emissão AVISO/ERRO, mensagem ajuste% |
| `TestLesaoFromSched` | 5 | extração fator_clima ponderado, semanas_lesadas, active_weeks |
| `TestLesaoFieldsInPE` | 6 | n_equipes_efetivo, fator_clima_medio, gap_escala, diagnostico_lesao |
| **Total** | **33** | **100% passando** |

---

## 6. Investigação e Resolução de Gaps Grotescos

### 6.1 Memorial de Cálculo — Identidade de Auditoria

O script `benchmarks/analysis/adr076_memorial_calculo.py` verifica para cada item:

```
custo_base + gap_escala + gap_praticabilidade + gap_pool = custo_total   (residuo ≈ 0)
```

Onde:
- **`custo_base`** = `fixo_mensal × perm_nominal` (1 equipe, catálogo)
- **`gap_escala`** = `custo_base × (N − 1)` (custo de N−1 equipes adicionais para compressão de prazo)
- **`gap_praticabilidade`** = `custo_autonomo − custo_base × N` (residual ≈ 0 para AGIS)
- **`gap_pool`** = `custo_total − custo_autonomo` (ociosidade de contrato compartilhado)

Identidade verificada para todos os 11 itens AGIS com residuo = 0.

### 6.2 Descoberta: Pool Overhead Grotesco (AGIS v13, pools originais)

| Contrato | Pool | MWs Contrat. | MWs Usados | Idle | Overhead |
|----------|------|-------------|------------|------|----------|
| ESC-3CAT | 10 | 480 | 244 | **49.2%** | R$28.6M |
| ESC-2CAT | 4 | 156 | 92 | **41.0%** | R$7.15M |
| ESC-1CAT | 2 | 62 | 41 | 33.9% | R$2.67M |
| ATERRO | 5 | — | — | 23.5% | R$4.52M |
| **TOTAL** | | | | | **R$42.9M** |

**Causa raiz:** Os pools foram calibrados para atender pico de demanda simultânea
de todos os itens do contrato, mas os itens têm durações diferentes — a capacidade
contratada fica ociosa durante os sub-períodos em que apenas itens menores estão ativos.

### 6.3 Solução: Redução de Pools via Serialização de Atividades

Análise de viabilidade (deadlines AGIS = 56 semanas):

| Contrato | Situação original | Proposta | Viabilidade |
|----------|-------------------|----------|-------------|
| **ESC-3CAT** | eap-1_5(4u×12w) + eap-1_6(4u×25w) + eap-1_9(2u×48w) simultâneos = peak 10 | pool=6: eap-1_6+eap-1_9 paralelos (w1-25), depois eap-1_5+eap-1_9 (w26-37), depois eap-1_9 solo (w38-48) | makespan=48w ≤ 56w ✓ |
| **ESC-2CAT** | eap-1_3(2u×7w) + eap-1_4(2u×39w) simultâneos = peak 4 | pool=2: eap-1_3 (7w) então eap-1_4 (39w) = 46w serial | 46w ≤ 56w ✓ |
| **ESC-1CAT** | eap-1_1(1u×10w) + eap-1_2(1u×31w) simultâneos = peak 2 | pool=1: eap-1_1 (10w) então eap-1_2 (31w) = 41w serial | 41w ≤ 56w ✓ |

**Alteração aplicada em** `benchmarks/data/AGIS/referencia.json`:
```json
"resource_pool": {
  "DESMAT": 6,
  "ESC-1CAT": 1,   // era 2
  "ESC-2CAT": 2,   // era 4
  "ESC-3CAT": 6,   // era 10
  "ATERRO": 5
}
```

### 6.4 Resultados Após Redução de Pools (AGIS v1 novo)

| Contrato | Pool ant. | Pool nov. | Custo ant. | Custo nov. | Economia |
|----------|-----------|-----------|------------|------------|---------|
| ESC-3CAT | 10 | 6 | R$58.15M | R$34.80M | **R$23.35M** |
| ESC-2CAT | 4 | 2 | R$17.43M | R$10.25M | **R$7.18M** |
| ESC-1CAT | 2 | 1 | R$7.89M | R$5.19M | **R$2.70M** |
| **Total** | | | **R$83.47M** | **R$50.24M** | **R$33.23M** |

Custo total do projeto: R$105.77M → **R$72.55M** (−31.4%)

Overhead de pool residual:
- ESC-3CAT: 49.2% → **15.3%** (irreducível: eap-1_9 corre sozinho nas semanas 38-48)
- ESC-2CAT: 41.0% → **0%** ✓
- ESC-1CAT: 33.9% → **0%** ✓

### 6.5 Calibração de PU (após redução de pools)

| Item | PU Catálogo | PU Calibrado | Ajuste Mínimo | Status |
|------|-------------|--------------|---------------|--------|
| eap-1_0 | R$ 0.8767/m³ | R$ 1.2730/m³ | +45.2% | AVISO |
| eap-1_1 | R$ 7.6583/m³ | R$ 10.9947/m³ | +43.5% | AVISO |
| eap-1_2 | R$ 8.4612/m³ | R$ 11.9769/m³ | +41.6% | AVISO |
| eap-1_3 | R$ 10.094/m³ | R$ 13.676/m³ | +35.5% | AVISO |
| eap-1_8 | R$ 11.939/m³ | R$ 19.967/m³ | +67.5% | **CRITICO** |
| eap-1_9 | R$ 5.873/m³ | R$ 7.493/m³ | +27.7% | AVISO |

### 6.6 Diagnóstico de Lesão de Produtividade

| Fonte | Resultado AGIS (novo) |
|-------|-----------------------|
| **Escala de equipes** | R$37.2M (35.2% do total) — RCPSP aloca N>1 equipes por item |
| **Lesão climática** | `gap_praticabilidade ≈ 0` para todos os itens (−R$9 total) |
| **Overhead de pool** | R$9.8M (13.5% do total) — vs R$42.9M antes da otimização |

**Nota:** `gap_praticabilidade_abs ≈ 0` para todos os itens AGIS: a escala captura
todo o sobrepreço; clima impacta custo de combustível (marginal), não duração.

---

## 7. ADRs Relacionados

- **ADR-060**: Modelo original de `ponto_equilibrio` (custo operacional × receita × BDI)
- **ADR-071**: Pool contracts — origem do `gap_pool_overhead`
- **ADR-072**: Productive Duration — duração RCPSP real vs permanência nominal
- **ADR-075**: Multi-algo compare — contexto do benchmark AGIS que revelou a lacuna
