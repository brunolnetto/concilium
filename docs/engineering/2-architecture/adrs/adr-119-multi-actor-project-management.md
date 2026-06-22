# ADR-119 — Gestão Multi-Ator de Projetos: Superfície de Manipulação, Fork por Ator e Auditoria Cross-Ator

**Status:** Proposta  
**Data:** 2026-06-22  
**Contexto:** MendesLobo Construtora — Concilium  
**Dependências:** ADR-099 (RBAC role↔tool), ADR-117 (decorator tags), ADR-118 (tool invocation audit), ADR-031 (escopos e planos), ADR-115 (RFI/RFP procurement)

---

## Contexto

### Problema

P1. **Múltiplos atores, estado compartilhado, sem governança por versão.** Um projeto Concilium pode ser manipulado por vários usuários (engenheiro de orçamentos, gerente de obra, analista sênior, diretor). Hoje todas as versões têm a mesma superfície de manipulação — qualquer usuário autenticado com role `operator` pode rodar RFI e RFP indistintamente. Não existe rastreabilidade de *quem* criou qual versão.

P2. **Superfície de manipulação não reflete o fluxo de aprovação real.** O fluxo canônico do cliente é RFI → RFP → aprovação pelo cliente. Um analista júnior pode gerar somente um RFI (exploração rápida de catálogo); o engenheiro sênior gera o RFP definitivo (análise completa com relatório). Hoje isso não é enforçado — qualquer `operator` pode rodar RFP diretamente.

P3. **Fork existe na API mas não carrega identidade do ator.** O endpoint `POST /api/projects/{id}/versions/{v}/fork` cria um fork, mas a versão derivada não registra quem a criou nem de qual versão veio. Comparações entre versões paralelas de atores distintos (`v2` de João vs `v3` de Maria) são possíveis via `/compare`, mas não há metadados de autoria para contextualizar o diff.

P4. **Auditoria de ações sobre versões é rasa.** O log de auditoria registra invocações de skills mas não distingue *intenção* (RFI vs RFP) nem associa a versão gerada ao ator que a gerou.

---

## Decisão

### D1: Superfície de Manipulação por Role — Pipeline Intent Binding

Cada role tem um conjunto permitido de `ProcurementIntent` que pode acionar:

| Role | Intents permitidos | Descrição |
|---|---|---|
| `viewer` | — | Somente leitura; não pode iniciar pipeline |
| `operator` | `RFI` | Exploração de catálogo; pipeline OLTP rápido |
| `engineer` | `RFI`, `RFP` | Análise completa; pode gerar o relatório técnico-financeiro |
| `admin` | `RFI`, `RFP` | Idem engineer + aprovação e gestão |

A validação acontece no middleware de RBAC antes de `disparar_pipeline`: se o `procurement_intent` solicitado não está na lista de intents permitidos para o role do token, retorna `403 Forbidden` com mensagem clara.

Nova constante em `permission_guard.py`:
```python
ROLE_ALLOWED_INTENTS: dict[str, frozenset[str]] = {
    "viewer":     frozenset(),
    "operator":   frozenset({"rfi"}),
    "engineer":   frozenset({"rfi", "rfp"}),
    "admin":      frozenset({"rfi", "rfp"}),
    "service-ci": frozenset({"rfi"}),
    "auditor":    frozenset(),
}
```

### D2: Identidade do Ator na Versão

Todo evento que cria ou modifica uma versão passa a registrar o `actor_id` (JWT `sub`) e `actor_role` no metadado da versão. O modelo `VersionMeta` é estendido:

```python
@dataclass
class VersionMeta:
    version_id: str
    criado_em: datetime
    criado_por: str | None          # JWT sub — None se service-ci
    role_criador: str | None        # role no momento da criação
    procurement_intent: str | None  # "rfi" | "rfp" | None
    forked_from: str | None         # version_id de origem, se fork
    motivo: str | None              # texto livre de justificativa
```

O `actor_id` vem do contextvar `_current_user_id` (ADR-118), sem necessidade de passar por parâmetro explícito.

### D3: Fork com Rastreamento de Autoria

Ao criar um fork (`fork_version`), o sistema:
1. Registra `forked_from = version_id_origem` na nova versão
2. Registra `criado_por = actor_id_atual` e `role_criador = role_atual`
3. O fork herda o `procurement_intent` da versão de origem como ponto de partida

A árvore de forks de um projeto passa a ser consultável via nova query `GET /api/projects/{id}/versions?tree=true` que retorna a estrutura hierárquica de versões com autores.

### D4: Comparação Cross-Ator

A resposta do endpoint `GET /api/projects/{id}/compare?left=v1&right=v2` (ou `POST /compare`) é enriquecida com metadados de autoria de cada versão:

```json
{
  "left":  { "version": "v1", "criado_por": "joao.silva", "intent": "rfi", "criado_em": "..." },
  "right": { "version": "v2", "criado_por": "maria.santos", "intent": "rfp", "criado_em": "..." },
  "diff": { ... }
}
```

Isso permite que um gerente veja *quem* propôs cada variante e com qual intenção (RFI de exploração vs RFP definitivo).

### D5: Auditoria de Ações Cross-Versão

O log de auditoria (`/api/projects/{id}/audit`) passa a registrar entradas do tipo `VersionAction`:

```python
@dataclass
class VersionAction:
    ts: datetime
    actor_id: str
    actor_role: str
    action: Literal["run_pipeline", "fork", "approve", "reject", "compare"]
    version_afetada: str
    intent: str | None
    detalhes: dict
```

Isso permite reconstruir a narrativa de decisão: *"João rodou RFI (v1), Maria fez fork e rodou RFP (v2), diretor comparou v1 vs v2 e aprovou v2"*.

---

## Alternativas Rejeitadas

| ID | Alternativa | Motivo |
|---|---|---|
| A1 | Branches Git por ator (como Git Flow) | Complexidade operacional excessiva; o modelo de versões atual (plaintext JSON) é mais simples e rastreável sem Git |
| A2 | Permissão de intent no nível de projeto (não de role) | Cria estado por projeto difícil de auditar; preferível manter governança centralizada em roles |
| A3 | Registrar actor apenas no log de auditoria, não na versão | Perde rastreabilidade direta ao abrir uma versão sem consultar o log |
| A4 | Separar `RFI` e `RFP` como escopos distintos (ADR-031) | Escopos são para cenários paralelos dentro de um mesmo projeto; intents são sobre profundidade de análise — conceitos ortogonais |

---

## Consequências

### Positivas

| Efeito | Descrição |
|---|---|
| Governança de fluxo | Analista júnior não pode gerar RFP definitivo por engano |
| Rastreabilidade completa | Toda versão sabe quem a criou, com qual intenção e de onde derivou |
| Narrativa de decisão | Gerente consegue reconstruir a sequência de análises e quem as aprovou |
| Comparação contextualizada | Diff entre versões mostra autores — facilita revisão técnica |

### Negativas / Riscos

| Risco | Mitigação |
|---|---|
| Migração de versões existentes sem `criado_por` | Preencher com `"system"` / `None` nas versões históricas |
| Aumento de complexidade no `VersionMeta` | Campos opcionais com fallback gracioso |
| `service-ci` não tem user_id real | Usar `actor_id = "service-ci"` como constante reservada |
| Role no momento do fork pode mudar depois | Registrar snapshot do role, não referência dinâmica |

---

## Plano de Implementação

| Fase | Entregas | Status |
|---|---|---|
| F1 | `ROLE_ALLOWED_INTENTS` em `permission_guard.py` + validação em `disparar_pipeline` | ⬜ Pendente |
| F2 | Extensão de `VersionMeta` com `criado_por`, `role_criador`, `procurement_intent`, `forked_from` | ⬜ Pendente |
| F3 | Propagação de `_current_user_id` / `_current_tenant_id` (ADR-118) para `fork_version` e `run_project` | ⬜ Pendente |
| F4 | `GET /api/projects/{id}/versions?tree=true` — árvore de forks com autoria | ⬜ Pendente |
| F5 | Enriquecimento do `/compare` com metadados de autoria das versões | ⬜ Pendente |
| F6 | `VersionAction` no log de auditoria + testes | ⬜ Pendente |

## Definition of Done

### Fase 1
- [ ] `ROLE_ALLOWED_INTENTS` definido e testado
- [ ] Tentativa de RFP por `operator` retorna `403` com mensagem clara
- [ ] `service-ci` pode rodar somente RFI

### Fase 2-3
- [ ] `VersionMeta` estendido e migrado
- [ ] `fork_version` registra `criado_por` e `forked_from`
- [ ] `run_project` registra `procurement_intent` na versão criada

### Fase 4-5
- [ ] `/versions?tree=true` retorna árvore hierárquica
- [ ] `/compare` inclui autoria das versões no response

### Fase 6
- [ ] Auditoria registra `VersionAction` para `run_pipeline`, `fork`, `approve`, `compare`
- [ ] Teste: narrativa completa RFI → fork → RFP → compare → approve auditável end-to-end

---

## Relacionados

- ADR-031: Escopos e Planos Paralelos — fork dentro de um escopo; este ADR adiciona fork com identidade de ator
- ADR-099: RBAC — define roles; este ADR adiciona restrições de intent por role
- ADR-115: RFI/RFP procurement semantics — define os intents; este ADR governa quem pode acionar cada um
- ADR-118: Tool Invocation Audit — registra invocações de tools; este ADR adiciona VersionAction ao audit trail
