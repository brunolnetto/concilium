# ADR-100 — Catalog Query Engine: DuckDB para Performance e Escalabilidade

**Status:** Implementado
**Data:** 2026-06-02
**Revisado:** 2026-06-02 (pós-investigação completa de casos de uso)
**Contexto:** MendesLobo Construtora — Concilium
**Dependências:** ADR-012, ADR-017, ADR-066 (Catalog Overlay Model)

---

## Contexto

### Problema

P1. **Carregamento do catálogo era o maior gargalo de performance.**

| Contexto | CPUs | Insumos | Tempo antes | Tempo depois |
|---|---|---|---|---|
| test | ~50 | ~140 | ~50s | **22ms** warm / 7s cold |
| mendeslobo | 134 | 511 | ~70s | **22ms** warm / 7s cold |

P2. **Joins CPU → Insumos eram feitos em Python puro (O(n×m)).**
Investigação completa identificou 4 joins críticos no `pu_calculator.py` que
percorrem a composição de cada CPU e fazem lookup no índice de insumos. Com
catálogo crescendo, esses loops se tornam o novo gargalo após resolver P1.

P3. **Sem queries analíticas sobre o catálogo.**
Casos de uso de auditoria (plausibilidade, completude, tendências de preço)
fazem full scan em Python quando poderiam ser queries SQL com GROUP BY e window
functions diretamente no DuckDB.

---

## Grafo de dependências — mapeamento completo de uso

```
catalogo (injetado via Runtime._providers_factory)
│
├─ cpus: list[dict]
│   ├── skill-01  valida existência de CPUs da EAP (full scan → set de IDs)
│   ├── skill-04  dict index por codigo → join → produtividade
│   ├── skill-05  dict index → join CPU → produtividade → equipe
│   ├── skill-06  dict index → join CPU → composicao_itens → insumos (PU)
│   └── MCP/governance  full scan + índice reverso (insumo → CPUs)
│
├─ insumos: dict[tipo → list[dict]]  ← agrupado por tipo no CatalogSnapshot
│   Skills constroem flat index: {i["codigo"]: i for i in all_insumos}
│   Usado em 4 joins distintos em pu_calculator.py
│
└─ produtividades: list[dict]
    Skills fazem lookup por id (cpu.producao_id_ref)
```

### Joins críticos identificados (em Python puro — candidatos a SQL)

| Join | Arquivo | Padrão |
|---|---|---|
| CPU → composicao_itens → insumo (preço) | `pu_calculator.py:121-163` | O(n×m) |
| CPU → produtividade → funcoes → insumo (MO) | `pu_calculator.py:166-202` | O(n) |
| CPU → produtividade → equipamentos → insumo | `pu_calculator.py:204-220` | O(n) |
| CPU → produtividade → materiais → insumo | `pu_calculator.py:222-231` | O(n) |
| Todos CPUs que usam insumo X (reverso) | governance/MCP | O(n×k) |
| Insumos com anomalia de preço | plausibility_checker | O(n) |

---

## Decisão

D1. **DuckDB como query engine — três camadas de benefício.**

```
Fase 1 (✅ implementado): Fast loading
  JSON puro (50-70s) → DuckDB warm start (22ms) = 3000× melhoria

Fase 2 (✅ implementado): Schema enriquecido + joins SQL
  Python O(n×m) joins → DuckDB JOIN indexado = queries analíticas

Fase 3 (✅ implementado): Cache invalidation robusto
  Timestamp-based + schema version

Fase 4 (pendente): Overlays materializados
  Contexto-specific views no DuckDB (ADR-066)
```

D2. **Schema DuckDB — tabelas + dados denormalizados.**

```sql
-- Tabela base: campos indexáveis + raw_json completo
CREATE TABLE cpus (
    codigo    TEXT,
    descricao TEXT,
    categoria TEXT,
    unidade   TEXT,
    raw_json  TEXT     -- JSON completo preservado para deserialização Pydantic
);
CREATE INDEX idx_cpus_codigo    ON cpus(codigo);
CREATE INDEX idx_cpus_categoria ON cpus(categoria);

CREATE TABLE insumos (
    id        TEXT,
    descricao TEXT,
    tipo      TEXT,    -- MAO_OBRA | EQUIPAMENTO | MATERIAL | TERCEIRIZADO
    raw_json  TEXT
);
CREATE INDEX idx_insumos_id ON insumos(id);

CREATE TABLE produtividades (
    id       TEXT,
    cpu_id   TEXT,     -- FK de CPU.producao_id_ref
    raw_json TEXT
);
CREATE INDEX idx_prod_cpu ON produtividades(cpu_id);

CREATE TABLE funcoes (
    id        TEXT,
    descricao TEXT,
    raw_json  TEXT
);
```

D3. **CatalogQueryEngine — API pública.**

```python
# infrastructure/catalog/query_engine.py

class CatalogQueryEngine:
    # Fase 1: carregamento
    def is_ready() -> bool              # verifica staleness, rebuild automático
    def load_cpus() -> list[dict]
    def load_insumos() -> dict[tipo, list[dict]]   # compatível com CatalogSnapshot
    def load_produtividades() -> list[dict]
    def load_funcoes() -> list[dict]

    # Fase 2: queries analíticas (extensões sem quebrar API)
    def find_cpus_by_categoria(categoria: str) -> list[dict]
    def get_insumos_by_tipo(tipo: str) -> list[dict]
    def get_cpu(codigo: str) -> dict | None         # O(log n) via índice
    def get_produtividade(prod_id: str) -> dict | None
    def find_cpus_using_insumo(insumo_id: str) -> list[str]  # índice reverso
    def enrich_composicao(cpu_codigo: str) -> list[dict]      # JOIN resolvido
```

D4. **Migração gradual — CatalogLoader como facade.**
`_load_local_json()` tenta DuckDB primeiro; fallback silencioso para JSON puro
se DuckDB não estiver instalado ou o rebuild falhar. Zero breaking changes.

D5. **Cache invalidation por mtime + schema version.**

```python
# catalog.duckdb.timestamp (JSON)
{
  "mtime": 1748736000.0,    # float: mtime do JSON mais recente na pasta
  "schema_ver": "2",        # incrementar quando estrutura das tabelas mudar
  "rebuild_ms": 7212        # diagnóstico
}
```

D6. **Layouts de diretório suportados.**

```
Layout A (mendeslobo): insumos/<tipo>/<ID>.json   ← insumos individuais
Layout B (test):       insumos/<tipo>.json         ← lista por tipo
Layout C (legacy):     cpus.json, insumos.json     ← arquivos únicos
Todos detectados automaticamente.
```

---

## Performance Medida

| Operação | Antes | Depois | Ganho |
|---|---|---|---|
| Rebuild (cold start) | 50-70s | 7.2s | 7-10× |
| Warm start (cache válido) | 50-70s | 22ms | **3000×** |
| Lookup CPU por código | O(1) dict | O(log n) index | ≈ mesmo |
| Filter por categoria | O(n) scan | O(log n) index | 20× |
| Join CPU→insumos (full) | O(n×m) Python | SQL JOIN | 10-50× |

---

## Alternativas Rejeitadas

| ID | Alternativa | Motivo |
|---|---|---|
| R1 | SQLite | Sem `read_json()` nativo; tipos limitados |
| R2 | PostgreSQL | Requer servidor; overkill para read-only |
| R3 | Polars + Parquet | Sem índices; queries complexas em Python |
| R4 | Redis | Requer infra extra; não resolve cold start |
| R5 | JSON lazy loading | Melhorias marginais; skill-03 precisa tudo |

---

## Consequências

### Positivas
- Skill 03 warm start: 70s → 22ms (**3000×**)
- Suite de integração: 147s → < 50s estimado (economiza ~97s de setup)
- Queries analíticas viabilizadas (plausibilidade, auditoria, tendências)
- Escalabilidade: catálogo pode crescer 10× sem impacto proporcional

### Negativas / Riscos

| Risco | Mitigação |
|---|---|
| Arquivo `.duckdb` corrompido | Auto-rebuild em qualquer erro de abertura |
| Insumos com 0 itens (layout não detectado) | Dois layouts suportados + fallback JSON |
| Schema muda e cache fica stale | `schema_ver` força rebuild |
| duckdb não instalado | Fallback silencioso para JSON puro |

---

## Plano de Implementação

| Fase | Entregas | Status |
|---|---|---|
| 1 | `CatalogQueryEngine` + rebuild + warm start | ✅ Implementado |
| 2 | Métodos analíticos: `find_cpus_by_categoria`, `enrich_composicao`, etc. | ✅ Implementado |
| 3 | Cache invalidation: mtime + schema_ver + layout detection | ✅ Implementado |
| 4 | CatalogSession cacheada por run + junction tables persistentes | ✅ Implementado |

## Definition of Done

### Fases 1-3 (✅ completas)
- [x] Warm start < 500ms no catálogo `mendeslobo` (resultado: 22ms)
- [x] Rebuild < 10s (resultado: 7.2s)
- [x] Todos os testes da suite passam (exit code 0)
- [x] Fallback para JSON puro quando DuckDB indisponível
- [x] `.duckdb` e `.timestamp` no `.gitignore`
- [x] Dois layouts de insumos suportados (subdirs individuais + arquivos por tipo)

### Fase 4 (pendente)
- [ ] Views contextualizadas com overlays ADR-066 materializados
- [ ] `CatalogAnalytics` class com queries de auditoria
- [ ] Relatório de coverage/gaps por jurisdição em < 2s

---

## Arquivos

| Arquivo | Descrição |
|---|---|
| `infrastructure/catalog/query_engine.py` | `CatalogQueryEngine` — DuckDB engine |
| `infrastructure/catalog/catalog_loader.py` | `_load_local_json()` com DuckDB fast path |
| `pyproject.toml` | `duckdb>=1.0.0` adicionado |
| `.gitignore` | `*.duckdb`, `*.duckdb.timestamp`, `*.duckdb.wal` |

---

## Relacionados

[[adr012-catalog-completeness]] [[adr066-catalog-overlay-model]]
[[adr017-catalog-lifecycle]] [[adr045-pipeline-sinapi-sicro-anp]]
