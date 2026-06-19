# ADR-114 — Golden Example de Avaliação: Projeto de Referência para Invariantes do Sistema

**Status:** Proposta  
**Data:** 2026-06-19  
**Contexto:** MendesLobo Construtora — Concilium  
**Dependências:** ADR-043 (Benchmark Application Layer), ADR-085 (Custo Instancial), ADR-044 (Planilha-First PU), ADR-090 (BDI Sistemático)

---

## Contexto

### Problema

**P1. Sem ground truth numérico para o sistema.**  
Os benchmarks existentes (AGIS, RUMO, SERRA_VERDE) são projetos reais com 50–200 itens cada.
Nenhum é pequeno o suficiente para verificação manual. Um desvio de 7% no `custo_direto` do AGIS
(detectado em 2026-06-19) só foi identificado porque um teste guardava um valor hardcoded — não
porque existia uma cadeia de invariantes verificável desde os inputs.

**P2. Ausência de invariantes matemáticos formalizados nos testes de integração.**  
O `tests/samples/01-terraplenagem-feliz.json` tem 3 itens e verifica apenas estrutura JSON.
Não há testes que verifiquem:
- `subtotal_sem_bdi[i] = Q[i] × PU[i]` (relação fundamental PU×Q)
- `Σ(subtotal_com_bdi) = venda.total_com_bdi` (consistência de BDI)
- `margem_pct = (venda - custo_total) / venda` (definição de margem)

**P3. Discrepância não documentada entre custo_catálogo e custo_instancial.**  
No sample existente: `custo.direto_equipes` = 900.000 ≠ `Σ(subtotal_sem_bdi)` = 1.070.800.
A diferença é real e esperada (ADR-085: custo instancial ≤ custo catálogo), mas não está
documentada como invariante. Um desenvolvedor não sabe se essa diferença é correto ou bug.

**P4. Sem política de atualização de valores de referência.**  
Quando uma decisão arquitetural muda os números esperados (ex: inclusão de BDI por sub-categoria,
ADR-090), não há procedimento definido para atualizar os valores golden com justificativa auditável.

---

## Decisão

**D1 — Criar benchmark sintético mínimo `GOLDEN` com valores verificáveis analiticamente.**  
Localização: `benchmarks/data/GOLDEN/referencia.json` (formato v2 — auto-contido).

3 atividades de terraplanagem com:
- Quantitativos em números redondos (divisíveis sem resto)
- PU com decomposição explícita (mao_obra, equipamentos, diesel, material)
- BDI declarado por categoria (uniform para simplicidade)
- Indiretos fixos (custo_mensal × n_meses conhecido)

**D2 — Definir explicitamente a hierarquia de custos e de onde vem cada número.**

```
GOLDEN invariantes matemáticos (verificáveis com calculadora):

1. PU×Q check:
   subtotal_sem_bdi[i] = round(quantitativo[i] × preco_unitario[i].total, 2)

2. BDI check:
   subtotal_com_bdi[i] = round(subtotal_sem_bdi[i] × (1 + bdi_direto), 2)

3. Venda check:
   venda.total_com_bdi = Σ subtotal_com_bdi + Σ(indireto × (1 + bdi_indireto))

4. Margem check (CLARIFICAÇÃO ADR-085):
   custo_catálogo = Σ subtotal_sem_bdi        # benchmark baseline
   custo_instancial = custo.direto_equipes     # custo real do pool (≤ custo_catálogo)
   custo_total = custo_instancial + custo_indireto_total
   margem_pct = (venda.total_com_bdi - custo_total) / venda.total_com_bdi

5. Invariante ADR-085 (custo instancial ≤ custo catálogo):
   custo.direto_equipes ≤ Σ subtotal_sem_bdi

6. Invariante de margem mínima (ADR-060):
   margem_pct ≥ MARGEM_MINIMA  (5%)
```

**D3 — `tests/integration/test_golden_evaluation.py` verifica dois tipos de invariantes:**

- **Invariantes algébricos** (falha = bug de fórmula; tolerância: 0.01%)
- **Invariantes de regressão** (falha = mudança arquitetural; tolerância: 0.5%)

Quando um invariante de regressão falha intencionalmente (mudança de decisão), atualizar
`benchmarks/data/GOLDEN/referencia.json` com commit mensagem `golden(update): <razão>`.

**D4 — Documentar a cadeia completa de cálculo no próprio arquivo golden.**  
O `referencia.json` incluirá seção `$golden_audit` com a derivação passo a passo:

```json
{
  "$golden_audit": {
    "versao": "1.0.0",
    "data_calibracao": "2026-06-19",
    "invariantes": {
      "PU_check": "subtotal_sem_bdi = Q × PU.total (tolerância 0.01%)",
      "BDI_check": "subtotal_com_bdi = subtotal_sem_bdi × (1 + bdi_direto)",
      "margem_formula": "(venda.total_com_bdi - custo_total) / venda.total_com_bdi",
      "instancial_vs_catalogo": "custo.direto_equipes ≤ Σ(subtotal_sem_bdi) — ADR-085"
    },
    "valores_esperados": {
      "margem_pct": "± 0.5% de 0.09"
    }
  }
}
```

---

## Alternativas Rejeitadas

| ID | Alternativa | Motivo |
|---|---|---|
| A1 | Usar AGIS como golden | Muito grande (200+ itens); não verificável manualmente |
| A2 | Apenas testes unitários de fórmulas | Não cobre a integração real do pipeline 01-06 |
| A3 | Property-based testing sem golden file | Não documenta valores esperados para novos desenvolvedores |
| A4 | Golden apenas de resultados (sem inputs) | Impossível diagnosticar qual input mudou quando a regressão falha |

---

## Consequências

### Positivas

| Efeito | Descrição |
|---|---|
| Onboarding | Novo desenvolvedor entende o sistema rodando o golden em 30 segundos |
| Regressões detectadas imediatamente | Pipeline muda → golden test falha → motivo identificável |
| Invariantes documentados | A diferença instancial×catálogo deixa de ser confusa |
| Auditoria de mudanças | Cada update no golden tem commit com justificativa |

### Negativas / Riscos

| Risco | Mitigação |
|---|---|
| Golden fica desatualizado | Política explícita de update (`golden(update)` commits) |
| Dependência de catálogo externo | Usar schema v2 auto-contido — sem lookup de catálogo |
| Falsos positivos por tolerância muito apertada | Tolerância algébrica 0.01%, regressão 0.5% |

---

## Plano de Implementação

| Fase | Entregas | Status |
|---|---|---|
| F1 | `benchmarks/data/GOLDEN/referencia.json` — benchmark sintético v2 com 3 itens | ⬜ Pendente |
| F2 | `tests/integration/test_golden_evaluation.py` — invariantes algébricos + regressão | ⬜ Pendente |
| F3 | Executar pipeline GOLDEN e capturar valores de regressão | ⬜ Pendente |
| F4 | Documentar cadeia de cálculo no `$golden_audit` | ⬜ Pendente |

---

## Definition of Done

- [ ] `Q × PU = subtotal_sem_bdi` verificado para cada item do GOLDEN (tolerância 0.01%)
- [ ] `Σ(subtotal_com_bdi) = venda.total_com_bdi` verificado
- [ ] `margem_pct = (venda - custo_total) / venda` verificado
- [ ] `custo_instancial ≤ custo_catálogo` verificado (invariante ADR-085)
- [ ] `margem_pct ≥ 5%` verificado (invariante ADR-060)
- [ ] `pytest tests/integration/test_golden_evaluation.py` verde
- [ ] `$golden_audit` documenta a derivação de cada número

---

## Relacionados

- ADR-085 — Custo Instancial (clarifica custo_equipes ≠ PU×Q)
- ADR-044 — Planilha-First PU (define de onde vem preco_unitario)
- ADR-090 — BDI Sistemático (define bdi por subcategoria)
- ADR-060 — Ponto de Equilíbrio (margem mínima aceitável)
- ADR-043 — Benchmark Application Layer (onde golden vive)
