# NEPs — Notas de Evolução de Produto

**Projeto:** Concilium — MendesLobo Construtora

---

## O que é uma NEP?

Uma **Nota de Evolução de Produto** (NEP) registra gaps, melhorias, inconsistências de UX e requisitos de produto identificados durante uso ou auditoria do sistema.

**Diferença de uma ADR:**

| Dimensão | ADR | NEP |
|---|---|---|
| Natureza | Decisão arquitetural irreversível | Estado de produto a evoluir |
| Gatilho | Necessidade de escolha técnica | Gap identificado em uso/revisão |
| Resultado | Contrato de design | Critério de aceite observável |
| Mutabilidade | Imutável após aceite | Revisada conforme contexto muda |
| Audiência | Engenharia | Produto + Engenharia |

---

## Formato da NEP

```
NEP-{NNN}: {Título conciso}
Status: Backlog | Em Andamento | Concluído | Cancelado
Prioridade: 🔴 Crítico | 🟠 Alto | 🟡 Médio | 🟢 Baixo
Área: Configuração | Catálogo | Projetos | Domínio | Infraestrutura
Tipo: Bug | UX | Feature | Dados | Estilo | Governança
Esforço: XS (<30 min) | S (30 min–2h) | M (2–4h) | L (4–8h) | XL (>8h)
```

---

## Índice

### Área: Configuração

| NEP | Título | Status | Prioridade | Esforço |
|---|---|---|---|---|
| [NEP-001](nep-001-jurisdicoes-artefatos-sinapi-sicro.md) | Jurisdições não expõem provedores SINAPI/SICRO | Concluído | 🟡 Médio | M |
| [NEP-002](nep-002-perfil-parametros-edicao-dashboard.md) | Parâmetros financeiros do perfil não editáveis nem visíveis no dashboard | Concluído | 🟠 Alto | M |
| [NEP-003](nep-003-tabs-configuracao-invertidas.md) | Tabs da página Configuração exibem conteúdo trocado | Concluído | 🔴 Crítico | XS |
| [NEP-004](nep-004-tema-layout-editor.md) | Layout do editor de tema desorganizado e campo com mapeamento errado | Concluído | 🟡 Médio | S |

### Área: Catálogo

| NEP | Título | Status | Prioridade | Esforço |
|---|---|---|---|---|
| [NEP-005](nep-005-categoria-diversos-reclassificacao.md) | Categoria "DIVERSOS" é genérica demais para usabilidade | Concluído | 🟡 Médio | L |
| [NEP-006](nep-006-composicao-coluna-dados-incompletos.md) | Coluna Composição no catálogo ignora equipe e mostra dados parciais | Concluído | 🟠 Alto | M |

### Área: Projetos

| NEP | Título | Status | Prioridade | Esforço |
|---|---|---|---|---|
| [NEP-007](nep-007-overview-dashboard-execucoes-primeiro.md) | Overview deve exibir dashboard de execuções antes do resumo do projeto | Concluído | 🟡 Médio | S |
| [NEP-008](nep-008-eap-cascata-auditavel-por-versao.md) | EAP deve ser cascata de colapsáveis com auditoria por versão | Concluído | 🟠 Alto | L |
| [NEP-009](nep-009-cpus-composicao-equipe-incompleta.md) | CPUs de terraplenagem com composição de equipe não registrada no catálogo | Concluído | 🟠 Alto | XL |
| [NEP-010](nep-010-produtividade-base-zeros.md) | Coluna "Base [un/h]" de produtividade exibe zeros por join incompleto | Concluído | 🔴 Crítico | S |
| [NEP-011](nep-011-custos-indiretos-equipe-editavel.md) | Equipe de apoio nos custos indiretos sem edição de itens | Concluído | 🟠 Alto | M |
| [NEP-012](nep-012-bdi-decomposicao-completa-tcu.md) | BDI pré-reforma não expõe componentes TCU (ac, df, r, cr, l, tributos) | Concluído | 🟡 Médio | M |
| [NEP-013](nep-013-saidas-antes-pipeline.md) | "Saídas do Planejamento" deve preceder botão "Iniciar Pipeline" | Concluído | 🔴 Crítico | XS |
| [NEP-014](nep-014-abas-excel-fundamentais-complementares.md) | Abas Excel sem distinção semântica + Curva ABC composição ausente | Concluído | 🟡 Médio | L |
| [NEP-015](nep-015-botoes-tema-escuro-painel-controle.md) | Botões do Painel de Controle não respeitam tema claro/escuro | Concluído | 🟠 Alto | M |
| [NEP-016](nep-016-eap-vazia-pipeline-feedback.md) | Pipeline falha com "EAP vazia" sem diagnóstico claro ao usuário | Concluído | 🔴 Crítico | S |

---

## Legenda de Status

- **Backlog** — identificado, aguardando priorização
- **Em Andamento** — em implementação ativa
- **Concluído** — critério de aceite verificado
- **Cancelado** — descartado com justificativa

## Legenda de Esforço

| Sigla | Intervalo | Exemplos |
|---|---|---|
| XS | < 30 min | Troca de ordem de elementos, fix de 1–5 linhas |
| S | 30 min – 2h | CSS, lógica simples, campo novo |
| M | 2 – 4h | Nova seção de UI, endpoint + tela |
| L | 4 – 8h | Nova feature completa, migração de dados |
| XL | > 8h | Subsistema, múltiplos domínios, enriquecimento de catálogo |
