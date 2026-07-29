# ADR-169 — LAB Condicional a Terraplenagem/Pavimentação

**Status:** ✅ Implementado
**Data:** 2026-07-29
**Contexto:** MendesLobo Construtora — Concilium
**Dependências:** ADR-166 (Wiring de Indiretos — mesmo padrão de degradação segura), ADR-167 (deferiu LAB), ADR-168 (Alojamento — precedente de configuração via `cat`)

---

## Contexto

### Problema

P1. A ADR-167 (D6) deixou a verba LAB ("Ensaios laboratoriais", R$4.000/mês) de fora — sem modelo de negócio para substituir o lump fixo, que hoje se aplica **incondicionalmente** a qualquer projeto com a categoria LAB configurada no perfil de indiretos, independente do tipo de serviço executado.

P2. O usuário relatou (informação do engenheiro de planejamento, ex-engenheiro de campo): laboratório só existe para projetos com atividades de **terraplenagem** ou **pavimentação** — a verba representa aluguel de equipamentos de ensaio (compactação, granulometria etc.), não uma estrutura fixa presente em todo projeto (drenagem, saneamento, obras de arte não usam laboratório de solos/asfalto).

## Decisão

D1. Nova função `_categorias_cpu_do_projeto(canonical_in, catalogo) -> set[str] | None` (`_dimensionamento.py`) — deriva o conjunto de `CategoriaCPU` (`TERRAPLENAGEM`/`PAVIMENTACAO`/`DRENAGEM`/`SANEAMENTO`/`OBRAS_ARTE`/`DIVERSOS`) presentes no projeto, via `canonical_in.eap` (cada `EapItem` tem `cpu_id`) cruzado com `catalogo["cpus"]` (cada CPU tem `categoria`). Retorna `None` quando não é possível determinar (sem catálogo, sem `canonical_in`, ou EAP vazia) — nenhum helper equivalente existia antes desta ADR.

D2. `_composicao_default_por_categoria("LAB", cpu_categorias_presentes=...)` só cobra R$4.000/mês quando `cpu_categorias_presentes` intersecta `{"TERRAPLENAGEM", "PAVIMENTACAO"}`; custo R$0 quando o conjunto é conhecido e não intersecta. `cpu_categorias_presentes=None` (desconhecido) **preserva o comportamento antigo** (sempre cobra) — mesma degradação segura de QSMS/MOB/Alojamento (ADR-166/168): só zera o custo quando se sabe positivamente que o projeto não tem nenhuma das duas categorias, nunca por falta de dado.

D3. Descrição do item atualizada para "Ensaios laboratoriais (aluguel de equipamentos)", refletindo a natureza real do custo (locação, não uma estrutura fixa).

## Alternativas Rejeitadas

| ID | Alternativa | Motivo |
|---|---|---|
| A1 | `cpu_categorias_presentes=None` zera o custo (assume "não se aplica" por padrão) | Rejeitada — inverteria a degradação segura já estabelecida nesta série de ADRs (166/168): dado ausente nunca deve silenciosamente remover um custo que já existia; só uma resposta positiva ("sabemos que não tem terraplenagem/pavimentação") zera. |
| A2 | Resolver categorias via `canonical_in.planejamento` em vez de `eap` | Rejeitada — `eap` é a fonte mais estável/populada cedo no pipeline (confirmado por uso já existente em skill-04/05); `planejamento` também tem `cpu_id` e serviria, mas não haveria ganho, só uma dependência a mais em um estágio posterior do pipeline. |
| A3 | Modelar como uma tool/campo novo de catálogo em vez de checagem via EAP | Rejeitada — a informação (quais categorias de CPU o projeto usa) já existe via EAP+catálogo; não há necessidade de um dado novo, só de uma função que cruze o que já existe. |

## Consequências

### Positivas

| Efeito | Descrição |
|---|---|
| LAB deixa de ser cobrado em projetos que não usam laboratório | Drenagem/saneamento/obras de arte puros não pagam mais R$4.000/mês por um ensaio que nunca acontece. |
| Degradação segura preservada | Perfis/chamadas sem `eap`/`catalogo` disponíveis mantêm o comportamento antigo (sempre cobra) — nenhum caso existente muda de custo por falta de dado. |

### Negativas / Riscos

| Risco | Mitigação |
|---|---|
| R$4.000/mês continua sendo um valor único fixo, não uma composição real de itens de equipamento de ensaio | Fora do escopo desta ADR — o usuário descreveu a condição de aplicabilidade, não uma composição de equipamentos individuais; pode virar uma ADR futura se/quando essa granularidade for necessária. |
| `_categorias_cpu_do_projeto` depende de `EapItem.cpu_id` resolver corretamente contra `catalogo["cpus"]"` — CPUs órfãs/não encontradas são silenciosamente ignoradas na contagem | Mesmo nível de tolerância a dado incompleto já aceito em outros pontos do pipeline (ex.: `cpu_lookup.get(...)` em skill-05); não é uma regressão introduzida aqui. |

## Plano de Implementação

| Fase | Entregas | Status |
|---|---|---|
| F1 | `_categorias_cpu_do_projeto` + condicional de LAB em `_composicao_default_por_categoria` | ✅ Implementado |
| F2 | Wiring em `_resolve_categoria_comp`/`_dimensionar_automatico` | ✅ Implementado |

## Definition of Done

- [x] Teste cobrindo: sem catálogo/canonical/EAP → `None`; EAP com CPU de TERRAPLENAGEM/DRENAGEM → conjunto correto; múltiplas categorias
- [x] Teste cobrindo: `cpu_categorias_presentes=None` aplica lump (retrocompat); com TERRAPLENAGEM/PAVIMENTACAO aplica; sem nenhuma das duas (conjunto conhecido, vazio ou não) → custo zero; ADM não afetado pelo parâmetro novo
- [x] Teste de integração via `_resolve_categoria_comp`: projeto real (EAP+catálogo) com/sem terraplenagem
- [x] Suíte completa verde (só a falha pré-existente do golden test)

---

## Relacionados

- ADR-166 — Wiring de Indiretos + Mapeamento Função→Item (padrão de degradação segura reaplicado aqui)
- ADR-167 — ADM/TOP com Função Real + Paridade de Catálogo (deferiu LAB — D6)
- ADR-168 — Alojamento (ADM) Bottom-Up por Número de Casas (precedente de configuração via `cat`/`regra` no perfil)
