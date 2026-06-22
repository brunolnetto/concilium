# ADR-115 — Semântica de RFI/RFP/RFQ no Concilium (RFX Procurement Flow)

**Status:** Implementado ✅ _(F1-F3, F5 2026-06-20; F4 parcial; RFQ removido 2026-06-22 — stakeholder confirmou fluxo exclusivo RFI→RFP)_  
**Data:** 2026-06-19  
**Contexto:** MendesLobo Construtora — Concilium  
**Dependências:** ADR-043 (Benchmark Application Layer), ADR-050 (CLI Unificada), ADR-102 (Pipeline Jobs), ADR-113 (PipelineMode OLTP/OLAP), ADR-114 (Golden Example)

---

## Contexto

### Problema

P1. Os termos RFI, RFP e RFQ aparecem em discussões de negócio, mas não estão formalizados no Concilium como etapas operacionais distintas.

P2. Sem definição explícita, diferentes times usam os mesmos artefatos para objetivos distintos (exploração, seleção técnica e negociação de preço), reduzindo rastreabilidade de decisão.

P3. A ferramenta já possui capacidades adequadas para separar intenção (OLTP/OLAP, benchmark, auditoria), mas falta contrato semântico para procurement.

---

## Decisão

### D1 — Adotar RFX como taxonomia oficial de intenção de procurement

No Concilium, os termos significam:

- **RFI (Request for Information):** descoberta de mercado e viabilidade inicial.
- **RFP (Request for Proposal):** comparação técnico-econômica estruturada entre alternativas.
- **RFQ (Request for Quotation):** fechamento comercial com escopo fechado e foco em preço.

### D2 — Mapear cada termo ao estágio e ao modo de execução da plataforma

| Termo | Estágio de compra | Pergunta central | Modo Concilium | Saída principal |
|---|---|---|---|---|
| RFI | Exploração inicial | "O que é viável no mercado para este escopo?" | `PipelineMode.OLTP` | precificação de catálogo (PU x Q), prazo/custo preliminares + riscos de dados |
| RFP | Due diligence e seleção | "Qual solução entrega melhor valor total?" | `PipelineMode.OLAP` | comparação auditável com custo operacional (cronograma, clima e não-produtivo) |
| RFQ | Negociação final | "Qual o melhor preço para escopo fixo?" | `PipelineMode.OLTP` ou `LIGHT` com baseline congelada | pacote de quantitativos, preço unitário e totais para cotação |

### D3 — Definir contratos de artefato por intenção

- **RFI package (informativo, não vinculante):**
  - baseline de escopo (EAP)
  - custo preliminar por catálogo (PU x quantitativo)
  - prazo/custo preliminares
  - alertas de qualidade de dados e premissas

- **RFP package (comparativo, auditável):**
  - tudo do RFI
  - cronograma operacional e efeitos de praticabilidade climática
  - custo com componentes não-produtivos e impactos de alocação
  - diagnóstico de criticidade
  - avaliação de intervenções
  - registro de decisão e bundle de relatórios

- **RFQ package (comercial, vinculável):**
  - escopo congelado (itens, quantidades, unidades)
  - preços unitários e subtotal por item
  - memória de premissas de BDI e indiretos aplicados
  - versão/hash de referência para auditoria

### D4 — Normalizar linguagem interna e externa

Regras de comunicação:

- Não usar RFP para fases de descoberta (usar RFI).
- Não usar RFQ para comparar solução técnica (usar RFP).
- Todo documento RFQ deve apontar para baseline previamente definida (RFI/RFP).

Sequência conceitual obrigatória para organização do trabalho:

1. RFI -> exploração inicial e entendimento de mercado (PU x Q)
2. RFP -> proposta técnico-econômica com método executivo e comparação de alternativas
3. RFQ -> cotação final para fechamento comercial com escopo congelado

Nota de alinhamento: RFQ não vem antes de RFP no fluxo canônico; RFQ sucede RFP quando o escopo já foi definido.

### D5 — Habilitar RFX no núcleo da pipeline (nós, caminhos e entregáveis)

Proposta de enum transversal para o core de orquestração:

```text
procurement_intent ∈ {"rfi", "rfp", "rfq"}
```

Comportamento esperado (perfil nativo de pipeline):

- `rfi` -> caminho `RFI_EXPLORACAO_CATALOGO`, nós 01-06 (OLTP), entregável mínimo informativo.
- `rfp` -> caminho `RFP_TECNICO_ECONOMICO`, nós 01-11 (OLAP), pacote analítico completo.
- `rfq` -> caminho `RFQ_COTACAO_FINAL`, nós 01-06+10 (LIGHT), pacote de cotação com baseline fixada.

### D6 — MCP atua como provedor de contexto (não como orquestrador de caminho)

As interações MCP com formulário de projeto devem carregar e retornar explicitamente o contexto RFX,
mas a seleção de nós/caminho/entregáveis ocorre no core da pipeline:

- entrada: `procurement_intent` (`rfi|rfp|rfq`)
- saída: bloco `procurement_context` com fase, método de custo e orientação para o agente
- persistência: metadata do projeto com `procurement_intent`

Objetivo: manter linguagem ubíqua para o planejador sem acoplar decisão de execução às tools.

---

## Alternativas Rejeitadas

| ID | Alternativa | Motivo |
|---|---|---|
| A1 | Manter RFI/RFP/RFQ como sinônimos no produto | Perde rastreabilidade de intenção e aumenta risco de decisão inadequada |
| A2 | Criar apenas documentação comercial sem refletir no tooling | Não resolve ambiguidade operacional em CLI/API/jobs |
| A3 | Forçar sempre OLAP para qualquer RFX | Custo computacional alto para fase exploratória (RFI) |

---

## Consequências

### Positivas

| Efeito | Descrição |
|---|---|
| Clareza de processo | Times distinguem descoberta (RFI), seleção (RFP) e preço final (RFQ) |
| Menor risco de sourcing | Cada etapa usa evidência apropriada ao grau de maturidade da compra |
| Melhor auditabilidade | Decisões passam a ter trilha por intenção e baseline |
| Eficiência computacional | RFI e RFQ podem usar OLTP/LIGHT, reservando OLAP para RFP |

### Negativas / Riscos

| Risco | Mitigação |
|---|---|
| Resistência por mudança de vocabulário | Guia rápido no CLI/API + exemplos padronizados |
| Uso incorreto da intenção no início | Defaults explícitos e validações de pré-condição por intent |
| RFQ sem baseline congelada | Exigir referência de versão/hash para emissão de pacote RFQ |

---

## Plano de Implementação

| Fase | Entregas | Status |
|---|---|---|
| F1 | Padronizar semântica RFI/RFP no contexto Concilium | ✅ 2026-06-19 |
| F2 | `procurement_intent` no core (`ProcurementIntent`, `PipelineProfile`) + CLI `--intent` + `BenchmarkRunner.run(procurement_intent=)` | ✅ 2026-06-20 |
| F3 | Regras de execução: RFI→OLTP, RFP→OLAP | ✅ 2026-06-20 |
| F4 | Bloco `rfx` no report (manifesto: intent, path, mode, deliverables) | ✅ 2026-06-20 · parcial (pacotes físicos por intent deferidos) |
| F5 | Testes: enum, intent→mode, contexto, runner intent | ✅ 2026-06-20 |
| — | **RFQ removido do domínio** — stakeholder confirmou fluxo exclusivo RFI→RFP. `ProcurementIntent` agora tem apenas 2 valores; `PipelineMode.LIGHT` mantido como modo independente | ✅ 2026-06-22 |

---

## Definition of Done

### Fase 1
- [x] Definição oficial de RFI/RFP/RFQ no contexto Concilium
- [x] Mapeamento explícito intent -> estágio -> modo de pipeline -> artefatos

### Fases 2–5
- [x] CLI aceita `--intent {rfi,rfp}` com defaults previsíveis
- [x] `procurement_intent` passado ao `BenchmarkRunner` e registrado no bloco `rfx` do report
- [x] `validate_procurement_baseline` valida pré-condições por intent
- [x] Testes cobrindo seleção de modo, validações e artefatos por intent (18 testes)
- [x] RFQ removido do domínio (2026-06-22) — `ProcurementIntent` ∈ {RFI, RFP}

---

## Relacionados

- ADR-043 — Benchmark Application Layer
- ADR-050 — CLI Unificada
- ADR-102 — Pipeline Jobs assíncronos
- ADR-113 — Tiers OLTP/OLAP
- ADR-114 — Golden Example para regressão
