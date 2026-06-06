# ADR-066: Catálogo com Fonte Única de Verdade + Composição por Overlay

**Status:** Implementado  
**Data:** 2026-05-19  
**Autor:** Engenheiro Sênior  
**Relacionado:** ADR-040 (Master vs. Project Layer), ADR-032 (CPU × Insumo × Jurisdição), ADR-041 (SCD Type 2), ADR-018 (Typed Artifact System), ADR-043 (Benchmark Application Layer)

---

## 1. Contexto

### 1.1 O modelo atual

O sistema opera com uma cadeia de resolução parcialmente implementada (ADR-040):

```
Master catalog (config/catalogos/{id}/)
    ↓
Project overlay (projects/{id}/overrides/cpus_override.json)
```

**O que já funciona:** `FileProjectHandle.resolve_cpu()` implementa a precedência master → override de projeto com fallback para snapshot. `SnapshotStore` persiste o catálogo completo no momento da criação do projeto identificado por SHA-256.

**O que está incompleto ou incorreto:**

| Problema | Manifestação |
|---|---|
| Overlay cobre apenas CPUs | `insumos_override.json` e `bdi_override.json` existem nos diretórios mas não têm resolução dinâmica correspondente no Runtime |
| Jurisdição não é overlay | É uma configuração estática em `config/jurisdicoes/` com herança por `parent_id`, mas sem estrutura de overlay formal sobre o master |
| Snapshot integral por projeto | `snapshots/catalogo-{hash}.json` contém o catálogo completo. Deduplicação por hash mitiga duplicação, mas o arquivo ainda cresce com o catálogo |
| Imutabilidade de runs frágil | Runs antigos dependem do snapshot integral; se o snapshot for movido ou corrompido, o run perde reprodutibilidade |
| Benchmarks globais desacoplados | `GET /api/benchmarks` lista artefatos sem contexto de projeto; artefatos fazem sentido apenas em relação ao projeto que os gerou |

### 1.2 A visão

```
Master Catalog  ──────────────────────────────────────────────────────
    ↓ (base canônica — nunca editada diretamente via projeto)
JurisdictionOverlay  ─────────────────────────────────────────────────
    ↓ (ajustes regionais: preços SINAPI/SICRO, encargos locais, BDI regional)
ProjectCatalogOverlay  ───────────────────────────────────────────────
    ↓ (customizações do projeto: CPUs novas, preços específicos, desativações)
Resolved Catalog  ────────────────────────────────────────────────────
    (resultado da composição, materializado apenas no momento do run)
```

---

## 2. Forças em tensão

| Força | Descrição |
|---|---|
| **Fonte única de verdade** | O master nunca deve ser copiado; customizações vivem em overlays |
| **Imutabilidade de runs** | Um run de 6 meses atrás deve ser reproduzível mesmo após atualização do master |
| **Eficiência de armazenamento** | Evitar duplicar catálogos inteiros por projeto |
| **Auditabilidade** | Quem sobrescreveu qual campo, em qual nível, quando e por quê |
| **Backward compatibility** | Projetos existentes têm snapshots integrais — eles não podem quebrar |
| **Transparência de resolução** | O usuário deve conseguir entender de onde veio cada valor no catálogo resolvido |

---

## 3. Decisão

### D1 — Três camadas de overlay com precedência explícita

```
Base: Master  →  Level 1: JurisdictionOverlay  →  Level 2: ProjectOverlay
```

**Regra:** último nível vence no mesmo campo. Cada override é um **delta** — contém apenas os campos que diferem da camada anterior.

```python
class OverlayEntry:
    """Um campo sobrescrito em um overlay."""
    item_id: str          # ID do item (cpu_id, insumo_id, etc.)
    item_type: Literal["cpu", "insumo", "producao"]
    field: str            # campo sobrescrito (ex: "preco_unitario", "producao_horaria")
    value: Any            # novo valor
    op: Literal["set", "disable"]  # set = substituir; disable = marca como não-disponível
    actor: str
    motivo: str
    timestamp: str
```

**Estrutura de arquivos:**

```
config/catalogos/{catalogo_id}/               ← Master (imutável via projeto)
    cpus/                                       ← itens individuais
    insumos/
    producoes/
    produtividades/

config/jurisdicoes/{jurisdicao_id}/
    overlay.json                               ← JurisdictionOverlay (delta)
    versions/                                  ← versionado via ADR-062

projects/{project_id}/overrides/
    cpus_overlay.json          ← renomeia cpus_override.json → overlays explícitos
    insumos_overlay.json       ← novo
    producoes_overlay.json     ← novo
    overlay_audit.jsonl        ← trilha de todas as operações de overlay
```

### D2 — `CatalogResolver` como serviço único de composição

```python
class CatalogResolver:
    """Implementa a resolução em três camadas: Master → Jurisdiction → Project."""

    def resolve_cpu(self, cpu_id: str, jurisdiction_id: str, project: ProjectHandle) -> dict | None:
        """Resolve CPU com precedência: project overlay > jurisdiction overlay > master."""

    def resolve_insumo(self, insumo_id: str, jurisdiction_id: str, project: ProjectHandle) -> dict | None:
        """Resolve insumo com mesma cadeia de precedência."""

    def resolve_producao(self, producao_id: str, jurisdiction_id: str, project: ProjectHandle) -> dict | None:
        """Resolve produção."""

    def resolve_catalog(self, catalogo_id: str, jurisdiction_id: str, project: ProjectHandle) -> dict:
        """Resolve catálogo completo como dict — usado apenas no momento do run."""
```

O `Runtime.load_catalogo()` e `Runtime.resolve_cpu()` passam a delegar para `CatalogResolver`. O cache existente em `_config_cache` permanece, aplicado ao resultado resolvido.

**Transparência:** `CatalogResolver` também produz `CatalogResolutionTrace` — para cada campo no resultado, de qual camada ele veio.

### D3 — Imutabilidade de runs via `resolved_catalog.json` (não snapshot integral)

Ao invés de persistir o catálogo completo, cada run persiste apenas o catálogo **efetivamente utilizado** — o conjunto de CPUs, insumos e produções referenciados pela EAP do projeto.

```
projects/{project_id}/{version}/
    canonical.json              ← canônico do run (existente)
    resolved_catalog.json       ← NOVO: snapshot compacto do catálogo resolvido para este run
    canonical.meta.json         ← sidecar ADR-018 (existente)
```

**`resolved_catalog.json` contém:**
```json
{
  "run_id": "run_abc123",
  "catalogo_id": "mendeslobo",
  "jurisdicao_id": "BR-CE",
  "project_id": "...",
  "resolved_at": "2026-05-19T10:00:00Z",
  "resolution_trace": {
    "CPU-ESCO-1CAT": "master",
    "CPU-COMPACT": "project_overlay",
    "INSUMO-MA-001": "jurisdiction_overlay"
  },
  "items": {
    "cpus": [...],     ← apenas CPUs usados pela EAP deste run
    "insumos": [...],  ← apenas insumos usados
    "producoes": [...]
  }
}
```

**Por que é menor:** um projeto típico usa 15–50 CPUs de um catálogo de 500+. O resolved_catalog tem 3–10% do tamanho de um snapshot integral.

**Backward compatibility:** projetos existentes com `snapshots/catalogo-*.json` continuam funcionando. O `FileProjectHandle.resolve_cpu()` mantém o fallback para snapshot quando `resolved_catalog.json` não existe.

### D4 — Benchmarks: templates globais, artefatos escopados ao projeto

Benchmarks permanecem como **templates de entrada globais** — eles existem antes de qualquer projeto e são referências canônicas.

```
GET  /api/benchmarks                           ← lista templates disponíveis (mantém)
GET  /api/benchmarks/{slug}                    ← metadados do template (novo)

GET  /api/projects/{id}/benchmarks             ← benchmarks usados por este projeto
GET  /api/projects/{id}/benchmarks/{slug}/download  ← artefatos no contexto do projeto
POST /api/projects/{id}/benchmarks/{slug}/pack      ← empacotar no contexto do projeto
```

**Compat temporário (deprecated):**
```
GET  /api/benchmarks/{slug}/download  →  redireciona para /api/projects/{id}/download
POST /api/benchmarks/{slug}/pack      →  redireciona para /api/projects/{id}/pack
```

A relação `projeto ↔ benchmark` já existe em `meta.json` via `benchmark_slug`. O novo endpoint `GET /api/projects/{id}/benchmarks` retorna os benchmarks referenciados pelo projeto (hoje sempre 0 ou 1, extensível para múltiplos).

### D5 — Escrita de overlays substitui `extend_cpu()` ponto-a-ponto

Hoje `extend_cpu()` escreve um objeto CPU completo no override. Com overlays, a escrita é declarativa e auditada campo a campo:

```python
# Antes (snapshot total do objeto):
project.extend_cpu("CPU-X", {"codigo": "CPU-X", "producao_horaria": 45.0, ...})

# Depois (overlay de campo):
project.set_overlay("cpu", "CPU-X", field="producao_horaria", value=45.0, motivo="Ajuste pós-medição")
```

O overlay é aplicado **em cima** do master, não substitui o objeto inteiro. Campos não mencionados no overlay continuam vindo do master.

`extend_cpu()` permanece disponível como conveniência — internamente, decompõe o dict em campos individuais e chama `set_overlay()` para cada um. **Sem breaking change.**

### D6 — Regra de precedência para `disable`

Um overlay pode marcar um item como `op: "disable"` — o item existe no master mas não está disponível para este projeto/jurisdição. O resolver retorna `None` para itens desabilitados, e as skills tratam isso como "CPU não encontrada".

---

## 4. Alternativas Rejeitadas

| ID | Alternativa | Motivo |
|---|---|---|
| A1 | Manter snapshot integral por projeto | Cresce com o catálogo; deduplicação por hash mitiga mas não resolve o problema de escopo |
| A2 | Overlay apenas no nível de projeto (sem jurisdição) | Jurisdição já implementa herança por `parent_id` — formalizar como overlay evita dois sistemas diferentes |
| A3 | `resolved_catalog.json` com catálogo completo | Perde a vantagem de compactação; o valor está em persistir só o subconjunto usado |
| A4 | Remover backward compat dos snapshots existentes | Projetos em produção perderiam reprodutibilidade de runs históricos |
| A5 | Benchmarks completamente dentro de `/projects` | Benchmarks são templates que existem antes de qualquer projeto; mover a entidade quebraria o fluxo de criação via `hot_project` |

---

## 5. Consequências

### Positivas

| Consequência | Benefício |
|---|---|
| Master como fonte única | Atualizações de preço no master propagam para todos os projetos que não sobrescreveram |
| Overlays auditados campo a campo | `overlay_audit.jsonl` responde "quem mudou qual campo e quando" |
| `resolved_catalog.json` compacto | 3–10% do tamanho do snapshot atual; deduplicação por SHA-256 mantida |
| Transparência de resolução | `resolution_trace` mostra a origem de cada valor — útil para auditoria de divergências |
| Benchmarks desacoplados de projeto | Template global + artefatos contextualizados por projeto |
| `CatalogResolver` testável isoladamente | Serviço puro sem acesso ao sistema de arquivos nas camadas superiores |

### Negativas / Riscos

| Risco | Mitigação |
|---|---|
| Migração de `cpus_override.json` → `cpus_overlay.json` | Script de migração que lê o override atual e cria o overlay equivalente; backward compat mantida por 2 releases |
| Resolução mais lenta (3 lookups ao invés de 1) | Cache por session em `CatalogResolver._cache`; hot path: project overlay já tem o item em 80% dos casos |
| `set_overlay()` com muitos campos = granularidade excessiva | `extend_cpu()` como açúcar sintático decompõe o objeto — o desenvolvedor não precisa chamar `set_overlay()` diretamente |
| `resolved_catalog.json` desatualiza se master muda e run é re-executado | O run sempre resolve na hora da execução e persiste o novo resultado; runs históricos mantêm seu `resolved_catalog.json` imutável |

---

## 6. Plano de Implementação

| Fase | Entregas | Dependências |
|---|---|---|
| **F1 — CatalogResolver** | `domain/services/catalog_resolver.py` com `resolve_cpu`, `resolve_insumo`, `resolve_producao`, `resolve_catalog`, `CatalogResolutionTrace` | ADR-032, ADR-040 |
| **F2 — Overlays formalizados** | Renomear `cpus_override.json` → `cpus_overlay.json`; criar `insumos_overlay.json`, `producoes_overlay.json`; `overlay_audit.jsonl`; `ProjectHandle.set_overlay()` | F1 |
| **F3 — Runtime migra para CatalogResolver** | `Runtime.load_catalogo()` e `resolve_cpu()` delegam para `CatalogResolver`; cache preservado | F1, F2 |
| **F4 — `resolved_catalog.json` por run** | `PipelineService._execute_run()` persiste catálogo resolvido compacto após resolução; `FileProjectHandle` expõe `load_resolved_catalog(run_id)` | F3 |
| **F5 — API benchmarks escopada** | Novos endpoints `/api/projects/{id}/benchmarks/*`; endpoints legados com header `Deprecated` | F3 |
| **F6 — Jurisdiction como overlay formal** | `config/jurisdicoes/{id}/overlay.json` com estrutura `OverlayEntry`; `JurisdictionVersionService` via ADR-062 | F1, F2 |
| **F7 — Migração + testes** | Script de migração de `cpus_override.json` existente; testes de resolução em 3 camadas; zero regressão | F1–F6 |

---

## 7. Definition of Done

### Fase 1 — CatalogResolver
- [x] `catalog_resolver.py`: `resolve_cpu`, `resolve_insumo`, `resolve_producao` com precedência correta
- [x] `CatalogResolutionTrace`: para cada item, indica de qual camada veio (`"master"`, `"jurisdiction"`, `"project"`)
- [x] Testes: item apenas no master → retorna master; item no project overlay → override vence; item desabilitado → retorna `None`

### Fase 2 — Overlays formalizados
- [x] `ProjectHandle.set_overlay(item_type, item_id, field, value, op, actor, motivo)`
- [x] `overlay_audit.jsonl` recebe entrada auditada a cada `set_overlay()`
- [x] `extend_cpu()` delega para `set_overlay()` campo a campo
- [x] Backward compat: `cpus_override.json` ainda é lido se `cpus_overlay.json` não existe

### Fase 3 — Runtime
- [x] `Runtime.load_catalogo()` usa `CatalogResolver.resolve_catalog()`
- [x] `Runtime.resolve_cpu()` usa `CatalogResolver.resolve_cpu()`
- [x] Nenhum teste existente quebra

### Fase 4 — `resolved_catalog.json`
- [x] Arquivo criado em `{version}/resolved_catalog.json` a cada run
- [x] Contém apenas items da EAP do run + `resolution_trace`
- [x] `FileProjectHandle.load_resolved_catalog(version)` implementado
- [x] Runs antigos sem `resolved_catalog.json` → fallback para snapshot integral

### Fase 5 — API benchmarks
- [x] `GET /api/projects/{id}/benchmarks` retorna benchmarks referenciados pelo projeto
- [x] `GET /api/projects/{id}/benchmarks/{slug}/download` funcional
- [x] Endpoints legados retornam header `Deprecation: true` e documentação de migração

### Fase 6 — Jurisdiction overlay formal
- [x] `overlay.json` em cada diretório de jurisdição com estrutura `OverlayEntry`
- [x] `CatalogResolver` aplica jurisdiction overlay entre master e project
- [x] `JurisdictionVersionService` via `ConfigVersionService`

### Fase 7 — Migração e testes
- [x] Script `scripts/migrate_overlays.py`: converte `cpus_override.json` → `cpus_overlay.json`
- [x] Teste de integração com 3 camadas: item no master, override na jurisdição, override no projeto
- [x] 0 regressões na suite existente
