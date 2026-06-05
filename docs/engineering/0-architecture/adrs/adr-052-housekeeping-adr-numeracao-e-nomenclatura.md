# ADR-052 — Housekeeping de ADRs: Numeracao e Nomenclatura para Automacao

**Status:** Implementado  
**Data:** 2026-05-14  
**Contexto:** MendesLobo Construtora - Concilium

---

## Contexto

### Problema

A automacao de governanca documental encontrava dois bloqueios estruturais:

- P1 - Duplicidade de numeracao em ADR-043 (dois arquivos com o mesmo numero).
- P2 - Inconsistencia de nomenclatura de arquivo (`adr_` e `adr-`), incluindo padding numerico irregular.

Esses pontos elevavam risco para:

- descoberta automatica por glob;
- ordenacao lexicografica x semantica;
- tooling de lint e validacao de referencias cruzadas;
- scripts de relatorio e DAG.

---

## Decisao

### D1 - Normalizar padrao de nome de arquivo

Padrao oficial aplicado para todos os ADRs:

- `adr-XXX-slug-kebab-case.md`
- prefixo `adr-`
- numero com 3 digitos (`001`, `043`, `052`)
- slug em kebab-case lowercase

### D2 - Eliminar duplicidade de numeracao

A duplicidade do antigo ADR-043 foi resolvida com renumeracao:

- `adr-043-benchmark-application-layer.md` permanece ADR-043.
- antigo `adr-043-governanca-fidelidade-benchmark-e-gates-objetivos.md` renumerado para `adr-051-governanca-fidelidade-benchmark-e-gates-objetivos.md`.

### D3 - Sincronizar index e DAG

O arquivo `INDEX.md` foi atualizado para refletir:

- nomes normalizados;
- novo ADR-051;
- fechamento dos debitos S4 e S5;
- DAG atualizado ate ADR-052.

---

## Alternativas Rejeitadas

| ID | Alternativa | Motivo |
|---|---|---|
| X1 | Manter aliases permanentes com nomes antigos | Mantem ambiguidade e aumenta custo de manutencao. |
| X2 | Corrigir apenas o INDEX sem renomear arquivos | Nao resolve automacao por descoberta em filesystem. |
| X3 | Renumerar ADR-043 principal em vez do secundario | Quebra historico de referencias mais difundidas. |

---

## Consequencias

### Positivas

| ID | Consequencia |
|---|---|
| C1 | Indexacao e descoberta deterministicas por padrao unico. |
| C2 | Eliminacao de colisao numerica na serie de ADRs. |
| C3 | Base pronta para lint automatizado de ADRs. |
| C4 | Menor risco de erro humano em links e DAG. |

### Negativas / Riscos

| ID | Risco | Mitigacao |
|---|---|---|
| R1 | Links externos antigos podem quebrar | Atualizacao de links internos no INDEX e rastreio por grep em ciclo posterior. |
| R2 | Scripts legados podem apontar para nomes antigos | Introduzir verificador de referencias no pipeline de docs. |

---

## Plano de Implementacao

| Fase | Entregas | Status |
|---|---|---|
| F1 | Renomear arquivos `adr_` para `adr-XXX-...` | ✅ Implementado |
| F2 | Renumerar antigo ADR-043b para ADR-051 | ✅ Implementado |
| F3 | Atualizar INDEX e DAG | ✅ Implementado |
| F4 | Fechar debitos S4/S5 no quadro de assincronia | ✅ Implementado |

---

## Definition of Done

### Fase 1
- [x] Nao existe arquivo ADR com prefixo `adr_`.
- [x] Nao existe duplicidade de numeracao na faixa 001-052.
- [x] `INDEX.md` referencia apenas caminhos existentes.
- [x] Quadro de debitos marca S4 e S5 como fechados.

---

## Evidencia de Execucao

- Renomeacao em lote aplicada no diretorio de ADRs.
- Titulo interno do ADR-051 atualizado para refletir nova numeracao.
- `INDEX.md` atualizado com serie 034-052 e DAG consistente.
