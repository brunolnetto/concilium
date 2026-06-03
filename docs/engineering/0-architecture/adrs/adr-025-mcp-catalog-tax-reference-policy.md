# ADR-025 — Política MCP para Mutações de Catálogo, Tributação por Jurisdição e Consultas a Referências

**Status:** Implementado  
**Data:** 2026-05-04  
**Data Implementado:** 2026-05-04  
**Implementadores:** models/catalog_draft.py (CatalogDraft, TaxProfile, ReferenciaItem), mcp_server/guards/catalog_guard.py (CatalogMutationGuard), mcp_server/tools/catalogo.py (get_tax_profile, query_referencia, propose_cpu_upsert, commit_catalog_draft)  
**Contexto:** MendesLobo Construtora — Concilium

---

## Contexto

### Problema

O MCP server do Concilium expõe ferramentas de execução de pipeline (ADR-013, ADR-022), mas não define um protocolo para as três classes de operações de **gestão de dados** que surgem dos ADRs recentes:

1. **Mutações de catálogo** — adicionar/atualizar CPUs, insumos e fichas de produtividade (ADR-017, ADR-024, ADR-025)
2. **Configuração tributária por jurisdição** — ler e atualizar alíquotas por município/regime fiscal (ADR-023 §D6)
3. **Consultas a tabelas de referência** — buscar preços unitários SICRO, SINAPI ou GoInfra sem acesso direto ao JSON (ADR-024)

Sem uma política explícita, essas operações tendem a ser feitas manualmente (edição de JSON), sem validação, sem trilha de auditoria e sem disparo automático de snapshot.

### Catálogo atual (config/)

```
catalogos/{cliente}/
    cpus.json              ← definições de CPUs (lean, sem composicao_padrao_equipe)
    produtividades.json    ← fichas de produtividade calibradas
    insumos/
        mao_obra.json | material.json | equipamento.json
jurisdicoes/
    BR.json                ← provedores, motor_encargos, regime CLT
referencias/
    SICRO_2024_CE.json     ← stub; itens reais a importar
```

---

## Decisões

### D1 — Três Classes de MCP Tools com Permissões Explícitas

```python
class CatalogPermission(str, Enum):
    READ       = "read"        # qualquer agente autenticado
    PROPOSE    = "propose"     # cria draft; requer aprovação HiL
    COMMIT     = "commit"      # aplica draft aprovado; requer papel catalog_editor
    ADMIN      = "admin"       # deleta, renomeia, muda schema; requer diretoria_operacoes
```

| Tool MCP | Permissão mínima | Dispara snapshot? | Requer HiL? |
|---|---|---|---|
| `get_cpu(codigo)` | READ | — | — |
| `list_cpus(filtro?)` | READ | — | — |
| `get_produtividade(id)` | READ | — | — |
| `query_referencia(provedor, codigo)` | READ | — | — |
| `get_tax_profile(jurisdicao_id, municipio?)` | READ | — | — |
| `propose_cpu_upsert(cpu)` | PROPOSE | — | Sim — revisão antes de commit |
| `propose_insumo_upsert(insumo)` | PROPOSE | — | Sim |
| `propose_produtividade_upsert(prod)` | PROPOSE | — | Sim |
| `commit_catalog_draft(draft_id)` | COMMIT | **Sim** | — (já aprovado) |
| `update_tax_profile(jurisdicao_id, patch)` | COMMIT | **Sim** (BDI snapshot) | Sim |
| `import_referencia(provedor, arquivo)` | ADMIN | **Sim** | Sim |

---

### D2 — Fluxo de Mutação de Catálogo (Proposta → Aprovação → Commit)

Toda mutação de dado de catálogo (CPU, insumo, produtividade) segue um fluxo de dois estágios para evitar alterações acidentais durante pipeline ativa:

```
Agent / Engenheiro
        │
        ▼
 propose_*_upsert()
        │ retorna draft_id + diff_preview
        ▼
 CatalogDraft (ArtifactKind.CATALOG_DRAFT)
        │ salvo no databook; status = PENDING_REVIEW
        ▼
  ★ HiL: engenheiro revisa diff_preview ★
        │
   [aprova]          [rejeita]
        │                │
        ▼                ▼
commit_catalog_draft  draft.status = REJECTED
        │
        ▼
  Arquivo JSON atualizado
  CatalogSnapshot criado (ADR-024 §D2)
  BdiPerfilDiff emitido se encargos mudaram (ADR-023 §D6)
```

```python
class CatalogDraft(BaseModel):
    draft_id:     str       # UUID v4
    catalog_name: str       # ex: "agis"
    entity_type:  Literal["cpu", "insumo", "produtividade"]
    operation:    Literal["upsert", "delete"]
    proposed_by:  str
    proposed_at:  datetime
    status:       Literal["pending_review", "approved", "rejected", "committed"]

    entity_before: dict | None  # None se criação nova
    entity_after:  dict         # estado proposto
    diff_preview:  str          # resumo legível das mudanças
    reviewed_by:   str | None = None
    reviewed_at:   datetime | None = None
    commit_snapshot_id: str | None = None  # preenchido após commit
```

**Regra de integridade:** `commit_catalog_draft` falha se qualquer pipeline do mesmo projeto estiver em estado `RUNNING` — evita race condition entre catálogo em uso e mutação pendente.

---

### D3 — Consultas a Referências Externas (SICRO/SINAPI/GoInfra)

As tabelas de referência em `config/referencias/` são **imutáveis em runtime** (campo `"imutavel": true` no JSON). O MCP não permite escrita direta. Consultas são sempre leitura.

```python
# MCP tool: query_referencia
def query_referencia(
    provedor: Literal["SICRO", "SINAPI", "GoInfra"],
    codigo_referencia: str,
    versao: str | None = None,   # ex: "2024"; None = mais recente carregada
) -> ReferenciaItem | None:
    """Busca item de tabela de referência pelo código."""
    ...

class ReferenciaItem(BaseModel):
    codigo_referencia: str
    descricao:         str
    unidade:           str
    preco_unitario:    float
    data_referencia:   date
    provedor:          str
    versao:            str
    fonte_url:         str | None
```

**Importação de nova tabela** (`import_referencia` — permissão ADMIN):
1. Valida estrutura do arquivo contra schema `tabela_referencia.schema.json`
2. Marca versão anterior como `superseded_by = nova_versao`
3. A nova versão recebe `imutavel: true` imediatamente após importação
4. Dispara `CatalogSnapshot` incluindo a referência importada
5. Nenhum projeto existente é afetado — referência é lida por `referencia_id` fixo no contexto do projeto

---

### D4 — Configuração Tributária por Jurisdição via MCP

O perfil tributário base de uma jurisdição (`BR.json`) define alíquotas default que inicializam o formulário HiL de criação de projeto (ADR-023 §D6). O MCP expõe leitura e atualização controlada.

```python
# MCP tool: get_tax_profile
def get_tax_profile(
    jurisdicao_id: str,          # ex: "BR"
    municipio: str | None = None,  # ex: "Minaçu/GO"; retorna ISS municipal se cadastrado
) -> TaxProfile:
    ...

class TaxProfile(BaseModel):
    jurisdicao_id: str
    municipio:     str | None
    iss_aliquota:  float           # alíquota ISS local (padrão 5% se município não cadastrado)
    regime_default: Literal["simples_nacional", "lucro_presumido", "lucro_real"]
    cofins:        float
    pis:           float
    cssl:          float
    ir:            float
    encargos_horistas:    float    # ex: 1.777
    encargos_mensalistas: float    # ex: 1.060
    fonte:         str             # ex: "BR.json v2024"
```

**Atualização de perfil tributário** (`update_tax_profile` — permissão COMMIT + HiL):

```python
# Patch parcial: apenas campos alterados
def update_tax_profile(
    jurisdicao_id: str,
    municipio:     str | None,
    patch:         dict,           # ex: {"iss_aliquota": 0.02}
    motivo:        str,            # obrigatório
    aprovado_por:  str,            # obrigatório
) -> TaxProfileUpdateResult:
    ...
```

Alterações de alíquota em `BR.json` disparam automaticamente `BdiPerfilDiff` para **todos os projetos ativos** que referenciam aquela jurisdição e têm `confirmado_em` anterior à mudança — os engenheiros responsáveis recebem notificação de revisão pendente.

---

### D5 — Política de Uso dos Dados: Leitura na Pipeline vs Mutação Isolada

**Regra fundamental:** pipelines de orçamentação são **somente leitura** em relação ao catálogo. Toda mutação é isolada do ciclo de runs.

| Contexto | Operação permitida | Operação proibida |
|---|---|---|
| Pipeline em execução (skill 00–14) | `get_*`, `query_referencia` | `propose_*`, `commit_*`, `update_*` |
| Idle (nenhum run ativo) | Todas | — |
| CI/batch automatizado | `get_*`, `query_referencia` | Mutações (exceto com flag `--allow-catalog-mutation`) |
| `concilium bdi-update` | `update_tax_profile` com HiL | Mutações de CPU/insumo |

**Implementação do bloqueio:** `CatalogMutationGuard` verifica `ProjectSnapshot.pipeline_status` antes de qualquer `propose_*` ou `commit_*`. Se `pipeline_status == RUNNING` → levanta `CatalogMutationConflict`.

---

### D6 — Rastreabilidade: Todos os Artefatos Referenciam a Versão do Catálogo

Complementa ADR-024 §D3. Todo artefato gerado pela pipeline carrega:

```python
class ArtifactMeta(BaseModel):  # extensão (ADR-018 + ADR-024 + ADR-025)
    ...
    catalog_snapshot_id:  str | None  # hash do catálogo no momento do run (ADR-024)
    bdi_perfil_id:        str | None  # versão do PerfilBdiProjeto usado (ADR-023 §D6)
    referencia_ids:       list[str]   # ex: ["SICRO_2024_CE"] — referências consultadas
```

Isso garante que dado qualquer artefato (proposta, relatório, resultado), é possível:
- Reproduzir exatamente o catálogo que estava em vigor
- Comparar com catálogos mais recentes (via `CatalogDiff`)
- Saber quais referências externas foram usadas para validação de preço

---

## Alternativas Consideradas

| Alternativa | Razão para Rejeição |
|---|---|
| Edição direta de JSON pelo engenheiro | Sem validação, sem auditoria, sem snapshot automático |
| API REST separada para catálogo | Overhead de infraestrutura; o MCP server já é o gateway (ADR-013) |
| Mutações em tempo real durante a pipeline | Race condition entre leitura do skill e escrita concorrente |
| Aprovação automática sem HiL para PROPOSE | Risco de dado incorreto propagar para proposta de licitação |

---

## Consequências

### Positivas
- **Imutabilidade de catálogo durante runs**: pipelines são determinísticas — mesmos inputs, mesmos outputs
- **Trilha de auditoria completa**: todo `CatalogDraft`, `commit`, e `update_tax_profile` gera artefato rastreável
- **Jurisdição como config viva**: alíquotas de ISS municipal atualizáveis via MCP sem deploy
- **Referências imutáveis por design**: impossível sobrescrever SICRO_2024_CE acidentalmente

### Negativas / Riscos
- **Latência no ciclo de atualização**: um engenheiro não pode propor e commitar no mesmo turn sem aprovação HiL — intencional
- **`CatalogMutationGuard` como ponto de falha**: se `pipeline_status` não for atualizado corretamente, mutações podem ser bloqueadas desnecessariamente (mitigado por TTL de 24h no status RUNNING)
- **Municípios sem ISS cadastrado** usam 5% (default nacional); engenheiro deve sempre verificar no formulário HiL de `project create`

---

## Definition of Done

- [ ] `CatalogPermission`, `CatalogDraft` definidos em `models/catalog_draft.py`
- [ ] `CatalogMutationGuard` em `mcp_server/guards/catalog_guard.py`
- [ ] MCP tools read: `get_cpu`, `list_cpus`, `get_produtividade`, `query_referencia`, `get_tax_profile`
- [ ] MCP tools write: `propose_cpu_upsert`, `propose_insumo_upsert`, `propose_produtividade_upsert`, `commit_catalog_draft`, `update_tax_profile`, `import_referencia`
- [ ] `ArtifactMeta` extendido com `referencia_ids: list[str]`
- [ ] `TaxProfile` e `update_tax_profile` integrados com `BR.json` (e futuras jurisdições)
- [ ] Notificação de revisão pendente para projetos ativos quando `update_tax_profile` altera alíquota
- [ ] `import_referencia` valida contra `schemas/tabela_referencia.schema.json`; marca versão anterior como `superseded_by`
- [ ] `CatalogMutationGuard` bloqueia mutações quando `pipeline_status == RUNNING`
- [ ] `ArtifactKind.CATALOG_DRAFT` adicionado ao enum existente
- [ ] Testes: `test_propose_requires_hil`, `test_commit_creates_snapshot`, `test_mutation_blocked_during_run`, `test_tax_update_notifies_active_projects`, `test_query_referencia_imutable`

---

## Referências

- **ADR-013:** MCP Facade — gateway architecture
- **ADR-017:** Catalog Lifecycle Management
- **ADR-018:** Typed Artifact System (`ArtifactKind`, `ArtifactMeta`)
- **ADR-022:** Wave Execution e Gate Blocking
- **ADR-023 §D6:** Perfil BDI Snapshot + `update_tax_profile` context
- **ADR-024:** Referências em Planilha Editável com Snapshot Auditável
- **config/loaders.py:** `LoaderInsumoAgnóstico`, `LoaderProdutividades`
- **config/jurisdicoes/BR.json:** motor_encargos_sociais, provedores_referencia
