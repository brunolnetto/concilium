# ADR-126 — Project Ownership: Responsável por Projeto e Autorização por Ownership

**Status:** 💡 Proposta
**Data:** 2026-07-02
**Contexto:** MendesLobo Construtora — Concilium
**Dependências:** ADR-099 (RBAC role↔tool), ADR-117 (decorator tags), ADR-118 (tool invocation audit), ADR-119 (multi-actor project management), ADR-094 (padrão de convite/revoke pendente reaproveitado no handover)

---

## Contexto

### Problema

P1. **Não existe "dono" de projeto no modelo de dados.** O ADR-119 introduziu `criado_por`/`role_criador` por *versão* — ótimo para rastrear quem gerou cada RFI/RFP, mas não responde "quem responde por este projeto como um todo". Hoje a única aproximação é olhar `criado_por` da v1, o que é frágil: a v1 pode ter sido criada por `service-ci`, por import de benchmark, ou por um analista júnior que só fez a exploração inicial antes de passar o projeto ao engenheiro responsável.

P2. **RBAC atual é por role global, não por projeto — e a lacuna é maior do que "role global demais": hoje não há checagem de role alguma nesses handlers.** `permission_guard.py` (ADR-099/117) define `PROJECT_READ`/`PROJECT_CREATE`, mas não existe uma permissão `project:delete` ou equivalente. Os handlers `DELETE /api/projects/{project_id}` (`delete_project`) e `PATCH /api/projects/{project_id}/config` (`patch_project_config`), em `presentation/api/routes/projects.py`, não têm decorator `@permission` — a única barreira hoje é a autenticação JWT do middleware (qualquer usuário autenticado, de qualquer role, pode deletar ou reconfigurar **qualquer** projeto do sistema). Este ADR propõe fechar essa lacuna em duas camadas: adicionar `@permission` de role nesses handlers (fora de escopo direto deste ADR, mas pré-requisito) e, sobre essa base, adicionar a checagem de ownership (D3).

P3. **Sem ownership, "meus projetos" não é uma consulta confiável.** Qualquer filtro de UI/API do tipo "meus projetos" hoje só pode se basear em heurísticas sobre `criado_por` de versões, que mistura autoria pontual de RFI/RFP com responsabilidade de longo prazo pelo projeto.

P4. **Responsabilidade pode mudar ao longo da vida do projeto sem que isso seja um evento de negócio registrado.** Um projeto pode começar com um analista júnior (RFI de exploração) e ser assumido por um engenheiro sênior (RFP definitivo, aprovação com cliente) — hoje essa "passagem de bastão" não tem representação no domínio, só é inferível indiretamente pela sequência de versões do ADR-119.

P5. **Remoção de usuário via CLI não se propaga para ownership de projeto.** O comando `remove_user` (`src/concilium/presentation/cli/commands_auth.py`, comando `concilium auth remove-user`) revoga dispositivos e chama `AuthStore.remove_client(client_id)` sem verificar se esse `client_id` é `owner_id` de algum projeto. Sem essa checagem, introduzir `owner_id` (D1) cria um novo tipo de referência quebrada: o client é removido do auth store, mas o projeto continua apontando para um `owner_id` que não existe mais — órfão silencioso, sem aviso no momento da remoção.

---

## Decisão

### D1 — Campo `owner_id` no `ProjectMeta`

`meta.json` do projeto passa a ter um campo de primeira classe:

```python
@dataclass
class ProjectMeta:
    ...
    owner_id: str | None       # JWT sub do responsável atual; None só para projetos legados sem migração
    owner_assigned_at: datetime | None
```

No `create_project`, `owner_id` é inicializado com o `actor_id` atual (mesmo valor de `criado_por` da v1 no momento da criação) — mas, diferente de `criado_por`, é um campo **do projeto**, não da versão, e pode ser alterado sem reescrever histórico.

### D2 — Ownership é distinto de autoria de versão

`owner_id` (quem responde pelo projeto) e `criado_por`/`role_criador` por versão (ADR-119, quem gerou cada RFI/RFP) são conceitos ortogonais e coexistem. Um projeto pode ter `owner_id = "maria.santos"` mesmo que a versão mais recente tenha sido criada por `criado_por = "joao.silva"` (ex.: João rodou um RFI exploratório num projeto que Maria possui).

### D3 — Nova permissão granular e autorização combinada

Nova permissão RBAC (ADR-099): `project:manage-ownership`, exigida para iniciar transferência de ownership.

Pré-requisito: `delete_project` e `patch_project_config` (`presentation/api/routes/projects.py`) hoje não têm `@permission` nenhum (P2) — este ADR introduz `project:delete` e `project:manage-config` em `permission_guard.py` e decora ambos os handlers, fechando a lacuna de RBAC que precede a de ownership.

Sobre essa base, ações destrutivas ou estruturais passam a exigir **autorização combinada**: role global compatível (via `@permission`, ADR-117, com as novas permissões) **E** (`owner_id == actor_id` **OU** role `admin`). Ou seja, ownership restringe a superfície de ação de roles não-admin ao próprio projeto, sem remover a capacidade de override administrativo.

### D4 — Handover híbrido: admin transfere unilateralmente, dono precisa de aceite do destinatário

Dois caminhos distintos para `project:manage-ownership`, dependendo de quem inicia:

1. **Admin (override administrativo):** `POST /api/projects/{id}/transfer-ownership {owner_novo}` — troca `owner_id` **imediatamente**, sem necessidade de confirmação do destinatário. Cobre o caso de saída de funcionário/reorganização, onde esperar aceite não é viável.
2. **Dono atual (transferência voluntária):** `POST /api/projects/{id}/transfer-ownership {owner_novo}` cria um convite **pendente** (não altera `owner_id` ainda) — mesmo padrão já usado para `revoke_pending` em `auth_store.py`. O destinatário precisa confirmar via `POST /api/projects/{id}/transfer-ownership/{token}/accept` (ou rejeitar via `/reject`) antes que `owner_id` seja atualizado. Convite pendente expira após um TTL configurável (default alinhado ao já usado em `revoke_pending`, ADR-094).

```python
@dataclass
class OwnershipTransferPending:
    token: str
    project_id: str
    owner_atual: str
    owner_proposto: str
    criado_em: datetime
    expira_em: datetime
```

Enquanto o convite está pendente, `owner_id` permanece o dono atual — ele continua responsável (e autorizado a agir) até o aceite. Se o destinatário rejeitar ou o convite expirar, nada muda.

### D5 — Filtro `mine=true` baseado em ownership

`GET /api/projects?mine=true` filtra por `owner_id == actor_id atual`, substituindo qualquer heurística anterior baseada em `criado_por` de versão.

### D6 — Transferência de ownership é evento auditável

Cada etapa do handover (D4) emite uma `VersionAction`-like entry no audit trail (ADR-118/119):

```python
@dataclass
class OwnershipTransferAction:
    ts: datetime
    actor_id: str            # quem executou a ação
    project_id: str
    action: Literal["transfer_forced", "invite_created", "invite_accepted", "invite_rejected", "invite_expired"]
    owner_anterior: str | None
    owner_proposto_ou_novo: str
```

Isso permite reconstruir a narrativa completa do handover (quem convidou, quando foi aceito/rejeitado, ou se foi um override de admin) — mesmo padrão de rastreabilidade do ADR-119.

### D7 — `remove-user` propaga para ownership de projeto

`remove_user` (CLI) e o futuro equivalente via API passam a checar, antes de remover o client: `find_projects_by_owner(client_id)`.

- **Se não há projetos:** remoção segue como hoje, sem mudança de comportamento.
- **Se há projetos:** a remoção é **bloqueada por padrão**, listando os projetos afetados, a menos que o operador informe explicitamente `--reassign-to <novo_owner_id>` — que executa a transferência forçada (D4.1, mesmo caminho de admin) para cada projeto **antes** de remover o client, na mesma operação.

```
$ concilium auth remove-user --id joao.silva
✗ joao.silva é owner de 3 projeto(s): proj-a1b2, proj-c3d4, proj-e5f6.
  Use --reassign-to <owner_id> para transferir antes de remover, ou --force para remover mesmo assim
  (projetos ficarão com owner_id órfão até reatribuição manual).
```

`--force` existe como escape hatch (ex.: projeto será arquivado/descartado mesmo assim) mas exige confirmação explícita adicional — nunca é o comportamento default. Cada reatribuição forçada por `--reassign-to` emite o mesmo `OwnershipTransferAction` (`action="transfer_forced"`) do D6, com `actor_id` = quem rodou o comando CLI.

---

## Alternativas Rejeitadas

| ID | Alternativa | Motivo |
|---|---|---|
| A1 | Inferir owner a partir de `criado_por` da v1, sem campo dedicado | Frágil: v1 pode ser de `service-ci`/import; não suporta transferência sem reescrever histórico de versão |
| A2 | Ownership em nível de organização/tenant (multi-tenant completo) | Fora de escopo — sistema hoje é single-tenant (MendesLobo); revisitar se houver onboarding de múltiplos clientes |
| A3 | Tratar role como proxy de ownership (ex.: todo `admin` é "dono" implícito) | Não captura responsabilidade individual dentro do mesmo role; dois `engineer`s continuariam indistinguíveis |
| A4 | Ownership múltiplo (lista de co-donos) desde o início | Adiciona complexidade de resolução de conflito sem caso de uso comprovado; se necessário, evolução natural de D1 é trocar `owner_id: str` por `owner_ids: list[str]` |
| A5 | Transferência sempre unilateral (sem aceite), mesmo quando iniciada pelo dono | Rejeitado — atribuir responsabilidade (incl. poder de deletar o projeto) sem consentimento do destinatário é indesejável quando há alternativa simples (convite pendente) |
| A6 | Transferência sempre com aceite, mesmo para admin | Rejeitado — bloquearia o caso de saída de funcionário/reorganização, onde não há como obter aceite do dono anterior nem sentido em esperar aceite do novo se a decisão já é administrativa |
| A7 | `remove-user` remove o client silenciosamente, deixando `owner_id` órfão para limpeza posterior (job assíncrono) | Rejeitado — favorece descoberta tardia do problema (ex.: só na próxima tentativa de `delete_project`); bloquear no momento da remoção é mais barato e é quando o operador tem mais contexto para decidir o reassign correto |
| A8 | `remove-user` reatribui automaticamente para um owner default (ex.: `admin` global) sem flag explícita | Rejeitado — reatribuição silenciosa para um dono "errado" é pior que bloquear; decisão de para quem transferir deve ser explícita do operador |

---

## Consequências

### Positivas

| Efeito | Descrição |
|---|---|
| Responsabilidade explícita | Todo projeto tem um responsável claro, independente de quem gerou a última versão |
| Autorização mais fina | Ações destrutivas exigem relação com o projeto, não apenas role global |
| Base para features futuras | Notificação ao dono (ex.: ADR-123 email) em eventos relevantes do projeto passa a ter destinatário natural |
| Consulta "meus projetos" confiável | Filtro direto por campo, sem heurística sobre histórico de versões |
| Consentimento preservado no caso comum | Handover voluntário (dono → dono) exige aceite explícito, evitando atribuir responsabilidade sem consentimento |
| Remoção de usuário nunca cria owner órfão silencioso | `remove-user` força uma decisão explícita (reassign ou `--force` confirmado) no momento da remoção |

### Negativas / Riscos

| Risco | Mitigação |
|---|---|
| Migração de projetos existentes sem `owner_id` | Backfill com `criado_por` da v1; fallback `"system"` quando ausente |
| Dono deixa a empresa/time e projeto fica "orfão" | `admin` sempre pode transferir ownership de forma forçada (D4.1), independente do dono atual, sem esperar aceite |
| Confusão entre `owner_id` e `criado_por` de versão | Documentar claramente a distinção na API (`GET /api/projects/{id}` retorna ambos com nomes distintos) |
| Aumento de complexidade em `ProjectMeta` | Campos opcionais com fallback gracioso, seguindo o padrão já usado em ADR-119 |
| Dois fluxos de transferência (forçado vs. convite) aumentam superfície de teste | Mesmo endpoint (`transfer-ownership`), ramificação simples por role do actor (admin vs. dono); reaproveita padrão já existente de `revoke_pending` (ADR-094) |
| Convite pendente esquecido/nunca respondido | TTL de expiração, mesmo padrão de `revoke_pending`; dono atual permanece responsável até resolução |
| `--force` em `remove-user` deixa projetos com `owner_id` órfão de propósito | Aceitável como escape hatch explícito (não default); `GET /api/projects` pode sinalizar `owner_ativo: false` quando o client referenciado não existe mais no auth store |

---

## Plano de Implementação

| Fase | Entregas | Status |
|---|---|---|
| F1 | `owner_id`/`owner_assigned_at` em `ProjectMeta`; `create_project` inicializa a partir do actor atual | ⬜ Não iniciado |
| F2 | `project:manage-ownership` em `permission_guard.py`; endpoint `POST /api/projects/{id}/transfer-ownership` com ramificação admin (forçado) vs. dono (convite) | ⬜ Não iniciado |
| F3 | `OwnershipTransferPending` + endpoints `/accept` e `/reject`; TTL de expiração | ⬜ Não iniciado |
| F4 | `project:delete`/`project:manage-config` em `permission_guard.py`; decorar `delete_project`/`patch_project_config` (pré-requisito, P2); autorização combinada (role + ownership) sobre essa base | ⬜ Não iniciado |
| F5 | `GET /api/projects?mine=true` via `owner_id`; migração/backfill de projetos existentes | ⬜ Não iniciado |
| F6 | `OwnershipTransferAction` no audit trail (ADR-118), cobrindo todos os sub-eventos do handover | ⬜ Não iniciado |
| F7 | `remove-user` (CLI) checa `find_projects_by_owner`; bloqueia por padrão, suporta `--reassign-to`/`--force` | ⬜ Não iniciado |

## Definition of Done

### Fase 1
- [ ] `ProjectMeta.owner_id`/`owner_assigned_at` definidos e persistidos em `meta.json`
- [ ] `create_project` inicializa `owner_id` com o actor atual

### Fase 2-3
- [ ] Admin: `transfer-ownership` troca `owner_id` imediatamente, sem aceite
- [ ] Dono: `transfer-ownership` cria `OwnershipTransferPending`; `owner_id` só muda após `/accept`
- [ ] `/reject` e expiração por TTL mantêm `owner_id` inalterado
- [ ] Testes cobrindo os dois caminhos (forçado vs. convite) e expiração

### Fase 4
- [ ] `project:delete`/`project:manage-config` definidos em `permission_guard.py` e aplicados via `@permission` em `delete_project`/`patch_project_config`
- [ ] Sobre essa base, `delete_project`/`patch_project_config` exigem também `owner_id == actor_id` ou role `admin`
- [ ] Testes cobrindo: usuário sem a permissão de role (403), e usuário com a permissão mas não-dono/não-admin (403)

### Fase 5
- [ ] `mine=true` retorna somente projetos com `owner_id == actor_id`
- [ ] Backfill de projetos legados sem `owner_id`

### Fase 6
- [ ] `OwnershipTransferAction` registrado em cada sub-evento do handover, best-effort (não propaga exceção)

### Fase 7
- [ ] `remove-user` sem `--reassign-to`/`--force` e com projetos possuídos: bloqueia com mensagem listando os projetos
- [ ] `--reassign-to`: transfere ownership (D4.1) para cada projeto e só então remove o client
- [ ] `--force`: remove o client mesmo com projetos possuídos, exige confirmação explícita adicional
- [ ] `find_projects_by_owner(client_id)` coberto por teste; comportamento sem projetos possuídos permanece idêntico ao atual

---

## Relacionados

- ADR-099: RBAC — define roles e permissões; este ADR adiciona autorização combinada por ownership
- ADR-117: RBAC por decorator — `@permission` continua sendo a checagem de role; ownership é checagem adicional no handler
- ADR-118: Tool Invocation Audit — `OwnershipTransferAction` reaproveita o mesmo audit trail
- ADR-119: Multi-Actor Project Management — define autoria por versão; este ADR define responsabilidade pelo projeto como um todo, conceito ortogonal
- ADR-094: JWT/Auth — `revoke_pending` é o precedente direto para `OwnershipTransferPending` (convite com TTL, aceite/rejeição explícitos)
