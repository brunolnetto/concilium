# ADR-063: Discriminador de Tipo de Projeto e Página de Criação Tipada

**Status:** Implementado  
**Data:** 2026-05-19  
**Autor:** Engenheiro Sênior  
**Relacionado:** ADR-031 (Escopos e Planos), ADR-040 (Master vs. Project Layer), ADR-048 (API + UI Iteração Rápida), ADR-050 (CLI Unificada), ADR-053 (CPU × Produtividade), ADR-062 (Versionamento de Contextos)

---

## 1. Contexto

### 1.1 O problema de dois mundos

O sistema hoje opera integralmente no modo **`hot_project`**: o benchmark fornece a EAP completa com quantidades e CPUs resolvidas, e o pipeline processa essa estrutura pré-populada. O usuário calibra parâmetros (BDI, equipes, praticabilidade), mas nunca compõe estrutura.

O modo **`project`** — projeto construído do zero — é a lacuna central. Nele:

- A EAP é composta item a item pelo engenheiro, sem benchmark como origem
- Quantidades e CPUs são definidas manualmente ou extraídas de catálogo via pesquisa
- A predecessão entre atividades é explícita (necessária para que o MILP de scheduling tenha um grafo dirigido acíclico)
- O pipeline não pode rodar até que a estrutura atinja um estado mínimo de coerência

### 1.2 Consequências da ausência de discriminação

Sem um discriminador de tipo:

| Problema | Manifestação |
|---|---|
| Pipeline assume EAP pré-populada | `hot_project` funciona; `project` falha silenciosamente |
| UI assume benchmark como origem | Não há formulário de composição gradual de EAP |
| `meta.json` não carrega intenção | Impossível tratar os dois tipos diferentemente em runtime |
| Criação de projeto está na sidebar | Mistura navegação com fluxo de criação, bloqueia expansão |

### 1.3 A sidebar como bottleneck de UI

A sidebar atual combina três responsabilidades:

1. **Navegação** — seleção de projeto ativo e versão
2. **Ação** — formulário de criação de projeto
3. **Status** — indicadores de pipeline

Essa concentração impede que a criação de projeto evolua para um fluxo tipado (com etapas distintas por tipo) sem transformar a sidebar em um painel complexo e ilegível.

---

## 2. Forças em tensão

| Força | Descrição |
|---|---|
| **Paridade de tipos** | `project` e `hot_project` devem ser cidadãos de primeira classe; não há tipo "inferior" |
| **Reutilização de `CanonicalModel`** | O modelo canônico deve permanecer agnóstico ao tipo de origem; a diferença está na rota de entrada, não na representação de saída |
| **Progressividade** | Um `project` é construído gradualmente; o pipeline deve aceitar estados parciais sem travar |
| **Predecessão como dado de entrada** | Para scheduling (MILP, ADR-046), o grafo de dependências precisa vir do usuário, não ser inferido |
| **Separação de preocupações na UI** | Criação e navegação são fluxos distintos; misturá-los aumenta a carga cognitiva e dificulta testes |
| **Compatibilidade retroativa** | Projetos existentes (todos `hot_project`) não devem ser afetados pela introdução do discriminador |

---

## 3. Decisão

### D1 — Campo `tipo_projeto` em `meta.json`

O arquivo `meta.json` de cada projeto recebe o campo discriminador:

```python
tipo_projeto: Literal["project", "hot_project"] = "hot_project"
```

Ausência do campo → interpretado como `"hot_project"` (compatibilidade retroativa).

O campo é escrito na criação e é **imutável após o primeiro run**. A promoção de `project` para `hot_project` (tornar-se referência benchmark) é um caso separado, fora do escopo desta ADR.

### D2 — `hot_project` mantém o fluxo atual

Nenhuma mudança no pipeline, nas skills nem na UI de gerência de `hot_project`. O discriminador apenas torna explícito o que hoje é implícito.

### D3 — `project` requer composição explícita de EAP antes do pipeline

Para `project`, a criação segue três etapas mínimas antes de qualquer skill poder rodar:

```
Etapa 1 — Composição de EAP
  Para cada item:
    - item_id, descricao, unidade, quantidade
    - cpu_id (resolvida via catálogo ou livre)
    - predecessores: list[str]  ← IDs de outros item_id no mesmo projeto

Etapa 2 — Atribuição de equipes
  Por item ou por grupo de itens:
    - funcoes_diretas, equipamentos
    - (reutiliza o fluxo atual de composição de equipes)

Etapa 3 — Validação mínima de coerência
  - EAP não vazia
  - Nenhum ciclo no grafo de predecessão
  - Todas as CPUs resolvidas ou marcadas como "provisórias"
  → estado: "RASCUNHO_PRONTO" → pipeline pode rodar
```

A progressividade é modelada por um `status_eap` no `meta.json`:

| Status | Significado | Pipeline pode rodar? |
|---|---|---|
| `RASCUNHO` | EAP em composição | Não |
| `RASCUNHO_PRONTO` | Etapas 1–3 completas | Sim (skills 00–06) |
| `ATIVO` | Pelo menos um run completo | Sim |

### D4 — `EAPItem` recebe campo `predecessores`

No domínio, `EAPItem` (ou equivalente em `CanonicalModel`) recebe:

```python
predecessores: list[str] = []
# IDs de outros EAPItems que devem ser concluídos antes deste começar.
# Tipo padrão: Finish-to-Start (FS). Outros tipos (SS, FF) são extensão futura.
```

Para `hot_project`, o campo permanece vazio (scheduling atual infere sequência por recurso, não por predecessão).  
Para `project`, o MILP de scheduling (ADR-046) usa o grafo dirigido formado por `predecessores` como restrição rígida adicional.

### D5 — Página `Projetos` com tabs substituindo o formulário da sidebar

A sidebar reduz sua responsabilidade para **navegação pura**: projeto ativo, versão ativa, e indicadores de status. O fluxo de criação migra para uma página dedicada `Projetos` com dois tabs:

```
┌─────────────────────────────────────────────────────────┐
│  Projetos                                               │
├───────────────────┬─────────────────────────────────────┤
│  ✚ Novo Projeto   │  📋 Meus Projetos                   │
├───────────────────┴─────────────────────────────────────┤
│                                                         │
│  Tab "Novo Projeto"                                     │
│  ┌─────────────────────┐  ┌──────────────────────────┐  │
│  │  🔥 Hot Project     │  │  📐 Projeto              │  │
│  │  A partir de um     │  │  Composição              │  │
│  │  benchmark          │  │  gradual de EAP          │  │
│  │  (fluxo atual)      │  │  + predecessão           │  │
│  └─────────────────────┘  └──────────────────────────┘  │
│                                                         │
│  Tab "Meus Projetos"                                    │
│  Lista com badge de tipo, status de pipeline,          │
│  data do último run, acesso direto à versão atual       │
└─────────────────────────────────────────────────────────┘
```

**Formulário `hot_project`** (tab Novo → Hot Project):  
Idêntico ao formulário atual da sidebar: nome, contexto, catálogo base, benchmark de referência.

**Formulário `project`** (tab Novo → Projeto):  
```
Passo 1 — Identificação
  Nome, contexto, tipo de obra, localização

Passo 2 — EAP inicial
  Editor tabular: adicionar itens, definir unidades e quantidades
  Botão "Buscar no catálogo" por item → resolve cpu_id
  Campo "Predecessores" por item (multi-select dos outros item_ids)

Passo 3 — Revisão e criação
  Validação de ciclos, cobertura de CPUs, resumo
  Botão "Criar Projeto" → cria diretório, meta.json com tipo_projeto="project"
```

### D6 — Runtime despacha por tipo (padrão Strategy)

O `Runtime` recebe um método `get_pipeline_entry(project: ProjectHandle) -> PipelineStrategy`:

```python
class HotProjectStrategy:
    """Pipeline atual — EAP pré-populada vinda de benchmark."""
    def validate_preconditions(self, project): ...
    def skill_sequence(self): return PIPELINE_SKILLS  # existente

class ProjectStrategy:
    """Pipeline para projeto de composição gradual."""
    def validate_preconditions(self, project):
        # Exige status_eap == "RASCUNHO_PRONTO"
        ...
    def skill_sequence(self): return PROJECT_PIPELINE_SKILLS
    # PROJECT_PIPELINE_SKILLS omite skills que dependem de benchmark
    # e acrescenta skill de validação de grafo de predecessão
```

Isso elimina `if tipo_projeto == "hot_project":` espalhados pelo código: cada ramo vive em sua estratégia.

---

## 4. Alternativas Rejeitadas

| ID | Alternativa | Motivo da Rejeição |
|---|---|---|
| A1 | Campo booleano `is_hot` em `meta.json` | Não extensível; um terceiro tipo (ex: `imported`) exigiria refatoração |
| A2 | Dois `CanonicalModel` distintos por tipo | Duplica toda a camada de domínio; downstream (benchmark, relatório) precisaria tratar dois tipos |
| A3 | Manter criação na sidebar, adicionar switch de tipo | Sidebar já sobrecarregada; formulário de `project` em múltiplos passos não cabe lateralmente |
| A4 | `predecessores` como campo do `CanonicalModel.cronograma` (não da EAP) | Predecessão é propriedade da atividade, não do cronograma calculado; misturar input com output dificulta auditoria |
| A5 | Inferir tipo pelo conteúdo do `meta.json` | Frágil; um projeto `project` com benchmark acidentalmente associado seria classificado errado |

---

## 5. Consequências

### Positivas

| Consequência | Benefício |
|---|---|
| Tipo explícito em `meta.json` | Runtime, UI e CLI podem se comportar corretamente sem heurísticas |
| Sidebar simplificada | Navegação sem formulário reduz carga cognitiva; testes de UI ficam focados |
| Página de Projetos como hub | Ponto único de criação e gerência; facilita onboarding de novos usuários |
| `predecessores` no domínio | Scheduling com MILP (ADR-046) pode usar restrições de predecessão sem workarounds |
| Strategy no Runtime | Extensão para um terceiro tipo é uma nova classe, não edição de código existente |
| Compatibilidade retroativa zero-custo | `"hot_project"` como default não afeta projetos existentes |

### Negativas / Riscos

| Risco | Mitigação |
|---|---|
| EAP builder é fluxo novo e complexo | Implementar editor tabular incremental; não bloquear pipeline para itens "provisórios" |
| Grafo de predecessores pode ter ciclos inseridos pelo usuário | Validação de DAG (Directed Acyclic Graph) antes de mudar `status_eap` para `RASCUNHO_PRONTO` |
| Skills do pipeline `project` podem divergir das skills `hot_project` | Definir `PROJECT_PIPELINE_SKILLS` como subconjunto + extensão, não fork; skills compartilhadas não se duplicam |
| Migração da sidebar pode quebrar fluxo atual | Manter formulário da sidebar funcional durante transição; remover somente após página Projetos validada |

---

## 6. Plano de Implementação

| Fase | Entregas | Dependências |
|---|---|---|
| **F1 — Discriminador** | Campo `tipo_projeto` em `meta.json`; `ProjectHandle` expõe `tipo_projeto`; compatibilidade retroativa | — |
| **F2 — Domínio** | `predecessores: list[str]` em `EAPItem`; validação de DAG no domínio | F1 |
| **F3 — Runtime Strategy** | `PipelineStrategy` base; `HotProjectStrategy` (wraps pipeline atual); `ProjectStrategy` (stub com validação de `status_eap`) | F1 |
| **F4 — UI: Página Projetos** | Tab "Meus Projetos" (lista com badge de tipo); Tab "Novo Projeto" com seleção de tipo | F1 |
| **F5 — UI: EAP Builder** | Editor tabular de itens; busca de CPU no catálogo; campo predecessores com multi-select e validação de ciclos | F2, F4 |
| **F6 — Pipeline `project`** | `PROJECT_PIPELINE_SKILLS` definida e testada; `ProjectStrategy.skill_sequence()` ativo | F3, F5 |
| **F7 — Sidebar** | Remoção do formulário de criação da sidebar; sidebar vira navegação pura | F4 |

---

## 7. Definition of Done

### Fase 1 — Discriminador
- [x] `meta.json` aceita e persiste `tipo_projeto` + `status_eap`
- [x] `ProjectHandle` expõe `tipo_projeto` e `status_eap` como propriedades
- [x] Projetos sem campo → `"hot_project"` por default (backward-compat com `project_kind`)
- [x] Teste unitário: criação com tipo explícito; legacy project_kind resolve corretamente

### Fase 2 — Domínio
- [x] `EapItem.predecessores: list[str] = []` em `canonical.py`
- [x] `eap_dag_validator.py`: `validar_dag_predecessores()` + `CicloPredecessaoError`
- [x] Testes: ciclo simples, ciclo longo, auto-loop, diamante DAG válido, predecessores desconhecidos

### Fase 3 — Runtime Strategy
- [x] `pipeline_strategy.py`: `PipelineStrategy` (Protocol), `HotProjectStrategy`, `ProjectStrategy`, `get_pipeline_strategy()`
- [x] `HotProjectStrategy` passa todos os testes existentes (1401 testes, zero regressão)
- [x] `ProjectStrategy` valida `status_eap in {RASCUNHO_PRONTO, ATIVO}` antes de rodar
- [x] Integrado em `PipelineService._execute_run()` antes de `runtime.run_pipeline()`

### Fase 4 — UI: Página Projetos
- [x] Nav "Projetos" sem projeto selecionado → `render_projetos_page()` (hub com tabs)
- [x] Tab "Meus Projetos": badges 🔥/📐, indicadores de status EAP, botão Abrir
- [x] Tab "Novo Projeto": cards de seleção de tipo + formulários tipados por tipo
- [x] Formulário `hot_project` funcional (nome, contexto, benchmark, tipo_obra, datas)

### Fase 5 — UI: EAP Builder
- [x] Editor tabular: adicionar/remover/editar itens (id, descrição, cpu, qtd, unidade, predecessores)
- [x] Busca de CPU via expander com campo de pesquisa + fallback ao catálogo do projeto
- [x] Feedback em tempo real: detecção de ciclo (`_detect_cycle_in_memory`) + aviso de itens sem CPU
- [x] Botão "Salvar EAP" desabilitado quando ciclo detectado; label explicativo

### Fase 6 — Pipeline `project`
- [x] `PROJECT_PIPELINE_SKILLS` definida em `pipeline_strategy.py`
- [x] 8 testes de integração: create→upsert_eap→status_eap→strategy dispatch (A→B→C linear, ciclo, sem CPU, hot_project rejeita)
- [x] `GET /api/projects/{id}/eap` e `PUT /api/projects/{id}/eap` implementados

### Fase 7 — Sidebar
- [x] `render_create_project_form_organism()` removida da sidebar
- [x] `create_project_mode` removido do `UIState` e `StateManager`
- [x] Botão "➕ Novo" redireciona via `StateManager.set_nav("Projetos")`
- [x] Sidebar exibe: badge de tipo, versão ativa e status EAP do projeto selecionado
- [x] 1401 testes passando, zero regressões
