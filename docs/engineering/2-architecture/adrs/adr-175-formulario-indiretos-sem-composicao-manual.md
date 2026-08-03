# ADR-175 — Formulário Não Pede Composição de Indiretos: Bottom-Up por Recursos É a Fonte, Não Input Manual

**Status:** ✅ Implementado
**Data:** 2026-08-03
**Contexto:** MendesLobo Construtora — Concilium
**Dependências:** ADR-165, ADR-166, ADR-167, ADR-168, ADR-169, ADR-170 (padrão bottom-up que esta ADR passa a refletir corretamente no formulário)

---

## Contexto

### Problema

P1. O Bloco 4 do formulário de criação de projeto (`docs/product/5-specifications/formulario-criacao-projeto.md`) foi redesenhado nesta sessão para pedir ao engenheiro a composição detalhada dos indiretos (mão de obra mensal, equipamentos mensal, verbas mensais, verbas únicas) por categoria (ADM/TOP/LAB/QSMS), sob a justificativa de que um valor lump mascararia o que está incluso. O usuário apontou que isso é ruim para usabilidade e, mais que isso, contradiz um padrão já estabelecido no próprio sistema: as ADR-165 a ADR-170 já resolveram esse exato problema — derivando a composição automaticamente a partir do catálogo (itens RH: EPI/treinamento/exame/benefício, ADR-165) e do headcount de `equipes_diretas` do projeto (produzido pelo dimensionamento em skill-04/05 a partir da composição de recursos de cada atividade/CPU) — sem que o engenheiro precise digitar composição nenhuma.

P2. Achado ao investigar `_dimensionamento.py`: qualquer valor preenchido em `indiretos.<categoria>` no `ProjetoSpec` (lido como override por `composicoes_indireto`) **substitui integralmente** a composição bottom-up daquela categoria — não é somado, não é combinado. Ou seja, pedir ao engenheiro para preencher a composição manual no formulário não é só ruim para UX: quando preenchido, desliga a derivação automática de ADR-166 (QSMS), ADR-167 (ADM/TOP via `funcao_id` real), ADR-168/ADR-170 (Alojamento) e ADR-169 (LAB) para aquela categoria — mesmo quando o catálogo tem dado real mais preciso que qualquer estimativa manual do engenheiro no momento de preencher o formulário.

P3. Cada uma dessas ADRs já estabeleceu, de forma independente, a mesma hierarquia de prioridade: **override explícito (perfil/formulário) > derivação bottom-up via catálogo > lump hardcoded** como último fallback (ver ADR-170 D3, por exemplo). O Bloco 4 redesenhado, ao expor colunas de composição, incentivava o preenchimento no nível errado dessa hierarquia — o correto é o engenheiro só preencher algo aqui quando tiver um número real e específico do contrato que precise sobrepor deliberadamente o cálculo automático (ex.: acordo já fechado com um fornecedor terceirizado de QSMS por valor fixo diferente do catálogo), não como prática padrão de preenchimento.

P4. Referência à ADR-010 (`IndiretoAlocacao`/`custo_indireto_atribuido`): o rateio por atividade distribui um indireto **já agregado no projeto** ao longo da duração de cada atividade, proporcionalmente às semanas — é uma alocação temporal, não uma derivação de "quais indiretos uma atividade específica requer" a partir da sua composição de recursos. Essa segunda coisa já existe, só que em outro ponto do pipeline: a composição de recursos (funções/equipamentos) de cada atividade já determina `equipes_diretas` (headcount agregado do projeto, calculado em skill-04/05 a partir da EAP+CPU), que por sua vez alimenta a derivação bottom-up de ADM/TOP/LAB/QSMS/Alojamento em skill-06. Não existe lacuna de "atividade não gera grupo de indiretos" — a lacuna real era o formulário pedir manualmente, na criação do projeto, o que o pipeline já deriva automaticamente mais adiante, quando a composição de recursos é conhecida.

## Decisão

D1. O Bloco 4 do formulário deixa de pedir composição (mão de obra/equipamentos/verbas por categoria). Passa a expor, por categoria (ADM/TOP/LAB/QSMS) e por fase de MOB (mobilização/desmobilização), um único campo opcional de override: valor mensal (ou total, para MOB) — preenchido só quando há um número contratual/negociado que deva substituir o cálculo automático. Vazio = deriva automaticamente via catálogo + composição de recursos do projeto (padrão ADR-165–170), com fallback lump apenas quando o catálogo não tiver o item correspondente.

D2. O texto do formulário passa a declarar explicitamente a hierarquia (override > catálogo/bottom-up > hardcoded) e a consequência de preencher um override: ele **substitui** a categoria inteira, não é somado à derivação automática — para que o engenheiro não preencha "para ser completo" achando que está adicionando informação, quando na prática estaria descartando um cálculo mais preciso.

D3. Nenhuma mudança de código nesta ADR. `_composicao_default_por_categoria`/`_dimensionamento.py` já implementam a hierarquia corretamente (ADR-165–170); esta é uma correção da camada de produto (formulário/spec) para não contradizer, na interface com o engenheiro, o mecanismo que já existe no pipeline. Fica fora de escopo: estender o bottom-up a categorias/fases ainda não cobertas — o custo genérico de mobilização/desmobilização (fora do componente BENEFICIO já coberto) segue sem equivalente catalogável, e continua exigindo valor lump por não ter um driver de headcount/função aplicável (é dirigido por logística/distância, não por composição de equipe).

## Alternativas Rejeitadas

| ID | Alternativa | Motivo |
|---|---|---|
| A1 | Manter o Bloco 4 com composição detalhada (decisão anterior desta mesma sessão) | Rejeitada pelo usuário — ruim para usabilidade e, pior, contradiz o mecanismo de derivação automática já implementado: qualquer valor preenchido desliga o bottom-up daquela categoria em vez de complementá-lo. |
| A2 | Remover o Bloco 4 inteiramente, sem nenhum campo de indireto no formulário | Rejeitada — ainda existem casos legítimos de override contratual (ex.: acordo fechado com fornecedor terceirizado) que precisam de uma via de entrada no sistema; eliminar o campo removeria essa via sem substituto. |
| A3 | Combinar (somar) o override do formulário com a derivação bottom-up em vez de substituir | Rejeitada — mudaria o comportamento de `_dimensionamento.py` já estabelecido e testado por cinco ADRs anteriores; fora do escopo de uma correção de formulário, exigiria ADR própria se algum dia for necessário. |

## Consequências

### Positivas

| Efeito | Descrição |
|---|---|
| Formulário alinhado ao mecanismo real | O que o engenheiro vê no formulário corresponde ao que o pipeline realmente faz — nenhuma composição fantasma que o sistema descarta silenciosamente. |
| Menos carga de preenchimento | Nenhuma composição manual por categoria; só um override pontual quando genuinamente necessário. |
| Menor risco de desligar o bottom-up por acidente | Um engenheiro preenchendo "para ser completo" não sobrescreve sem querer um cálculo mais preciso vindo do catálogo. |

### Negativas / Riscos

| Risco | Mitigação |
|---|---|
| Engenheiro pode não perceber que preencher qualquer valor substitui (não soma) a derivação automática | Nota explícita no formulário (D2) e no checklist final de revisão. |
| MOB fora de BENEFICIO continua sem equivalente catalogável — override manual segue sendo a única via | Aceito, fora de escopo (D3); revisitar se a necessidade de um driver catalogável para mobilização aparecer. |

## Plano de Implementação

| Fase | Entregas | Status |
|---|---|---|
| F1 | Bloco 4 do formulário reescrito: campo único de override por categoria/fase MOB + nota de hierarquia | ✅ Implementado |

## Definition of Done

### Fase 1
- [x] Bloco 4 do formulário sem colunas de composição, com campo único de override por categoria e nota de hierarquia (override > catálogo/bottom-up > hardcoded)
- [x] Checklist do formulário revisado para refletir a nova redação

---

## Relacionados

- ADR-165 — Catálogo de Treinamentos, Exames, EPIs e Benefícios de Mão de Obra
- ADR-166 — Wiring de Indiretos + Mapeamento Função→Item (QSMS/MOB bottom-up, hierarquia override > catálogo > hardcoded)
- ADR-167 — ADM/TOP com Função Real + Paridade de Catálogo
- ADR-168 — Alojamento (ADM) Bottom-Up por Número de Casas
- ADR-169 — LAB Condicional a Categoria de CPU (Terraplenagem/Pavimentação)
- ADR-170 — Alojamento como Benefício Catalogado (BEN-ALOJAMENTO)
- ADR-010 — Rateio de indireto por atividade (mecanismo complementar de alocação temporal, não conflitante com a derivação bottom-up)
