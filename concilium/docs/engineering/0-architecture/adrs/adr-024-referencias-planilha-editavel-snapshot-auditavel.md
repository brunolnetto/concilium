# ADR-024 — Referências em Planilha Editável com Snapshot Auditável, Cache Local e Detecção de Mudanças

**Status:** Implementado  
**Data:** 2026-05-04  
**Data Implementado:** 2026-05-04  
**Implementadores:** models/catalog_snapshot.py (CatalogSnapshot, CatalogDiff, compute_catalog_diff), catalog/catalog_loader.py (CatalogLoader, backends LOCAL_JSON/GOOGLE_SHEETS, TTL cache)  
**Contexto:** MendesLobo Construtora — Concilium

---

## Contexto

### Estado Atual (AS-IS)

Os dados de referência do Concilium — catálogos de CPUs, produtividades e insumos — residem como arquivos JSON estáticos versionados em `config/catalogos/`. A atualização desses dados requer acesso ao repositório git, execução de scripts de importação (`import_rfi_catalog.py`) e um commit manual.

**Problemas críticos deste modelo:**

| ID  | Problema                                         | Impacto                                                                                  |
|-----|--------------------------------------------------|------------------------------------------------------------------------------------------|
| R1  | Edição requer acesso ao repositório git          | Engenheiros de domínio não conseguem atualizar produtividades sem suporte de TI           |
| R2  | Sem histórico versionado do catálogo por projeto | Impossível saber qual versão do catálogo foi usada para produzir uma proposta específica  |
| R3  | Sem detecção de mudanças entre execuções         | Pipeline reusa dados desatualizados silenciosamente entre execuções consecutivas          |
| R4  | Sem auditoria temporal das referências           | Revisões contratuais (DNIT/ANTT) exigem provar que o BDI e produtividades eram vigentes  |
| R5  | Planilha .xlsm como única fonte compartilhável   | Formato binário com macros; não suporta edição colaborativa, controle de permissões nem histórico nativo |
| R6  | Round-trip por execução desnecessário            | Se o catálogo não mudou, buscar os dados remotos a cada run é latência sem benefício      |

### Casos de Uso que Motivam a Mudança

1. **Atualização mensal de insumos** — Preço de diesel, explosivos e aço variam mensalmente. Um engenheiro de planejamento precisa atualizar no Google Sheets e refletir nos próximos orçamentos sem deploy.
2. **Auditoria de proposta** — Para defender um preço em licitação DNIT, precisamos provar que os valores de CPUs e BDI estavam em vigor em determinada data.
3. **Divergência de cenário** — Projeto A usou catálogo v1.2, Projeto B usou v1.3 com diesel reajustado. O relatório de cada projeto deve carregar a versão correta.
4. **Execuções consecutivas no mesmo dia** — A pipeline roda `00-escopo` → `14-plan-space-explorer`. Se o catálogo não mudou desde o run anterior, o carregamento dos dados de referência não deve gerar latência nem round-trip.

---

## Decisões

### D1 — Fonte de Verdade: Google Sheets como Catálogo Editável

Adotar **Google Sheets** como interface de edição dos dados de referência, substituindo a planilha `.xlsm` como fonte operacional.

**Alternativas consideradas:**

| Alternativa | Prós | Contras |
|-------------|------|---------|
| A — JSON no git (atual) | Simples, versionado por commit | Requer TI para edição; sem colaboração em tempo real |
| B — Google Sheets | Editável por não-TI; API pública; histórico de versão nativo | Requer autenticação OAuth2; dependência de serviço externo |
| C — Notion / Airtable | Interface amigável | API proprietária; custo; portabilidade limitada |
| D — SharePoint / OneDrive xlsx | Familiar para o time | API menos madura; conflitos de edição; sem hash de conteúdo confiável |

**Decisão:** Alternativa B — Google Sheets com autenticação via Service Account (sem OAuth interativo na pipeline).

A estrutura de abas espelha o modelo atual:

| Aba Google Sheets   | Entidade               | Arquivo JSON atual                  |
|---------------------|------------------------|-------------------------------------|
| `CPUs`              | `CPU`                  | `config/catalogos/*/cpus.json`      |
| `Insumos_MO`        | `Insumo` (mao_obra)    | `config/catalogos/*/insumos/mao_obra.json` |
| `Insumos_MAT`       | `Insumo` (material)    | `config/catalogos/*/insumos/material.json` |
| `Insumos_EQ`        | `Insumo` (equipamento) | `config/catalogos/*/insumos/equipamento.json` |
| `BDI`               | `TabelaBdi`            | `config/perfis/*/bdi.yaml`          |
| `Encargos`          | `TabelaEncargos`       | `config/perfis/*/encargos.yaml`     |
| `Produtividades`    | `FaixaProducao`        | `config/catalogos/*/producoes/`     |

---

### D2 — Snapshot Imutável por Versão de Catálogo

Cada vez que a pipeline detectar mudança nos dados remotos, ou quando o operador solicitar explicitamente, é gerado um **`CatalogSnapshot`** — registro imutável e datado do estado completo do catálogo.

```python
class CatalogSnapshotMeta(BaseModel):
    snapshot_id: str          # UUID v4
    catalog_name: str         # ex: "agis"
    version_hash: str         # SHA-256 do conteúdo normalizado
    created_at: datetime
    source_url: str           # URL da planilha Google Sheets
    source_tab: str           # nome da aba
    created_by: str           # service account ou usuário
    project_ids: list[str]    # projetos que referenciaram este snapshot

class CatalogSnapshot(BaseModel):
    meta: CatalogSnapshotMeta
    cpus: list[CPU]
    insumos: dict[str, list[Insumo]]   # chave: "mao_obra" | "material" | "equipamento"
    produtividades: list[FaixaProducao]
    tabela_bdi: TabelaBdi | None = None
    tabela_encargos: TabelaEncargos | None = None
```

**Regra de imutabilidade:** Um snapshot com `version_hash` já existente **não** é regravado. Apenas o campo `project_ids` é atualizado com append.

---

### D3 — Databook de Projeto no Google Drive

Cada projeto no Concilium possui um **databook** — pasta estruturada no Google Drive que consolida todos os artefatos auditáveis de uma obra.

```
Google Drive / MendesLobo / Projetos / {project_id} /
    databook /
        catalog_snapshots /
            {snapshot_id}.json     ← CatalogSnapshot imutável
        artifacts /
            {skill}-{run_id}.json  ← ArtifactEnvelope (ADR-018)
        reports /
            proposta-v{n}.pdf
```

O `snapshot_id` é gravado no `ArtifactMeta` de cada artefato gerado pela pipeline, criando rastreabilidade bidirecional: dado um artefato, encontro o catálogo exato; dado um snapshot, listo todos os projetos e runs que o usaram.

```python
class ArtifactMeta(BaseModel):  # extensão ao modelo existente (ADR-018)
    ...
    catalog_snapshot_id: str | None = None
```

---

### D4 — Cache Local com TTL e Invalidação por Hash

Para evitar round-trips à API do Google Sheets a cada execução, a pipeline mantém um **cache local** em disco.

```
.concilium/
    catalog_cache/
        {catalog_name}/
            latest.json        ← CatalogSnapshot mais recente (conteúdo completo)
            latest_meta.json   ← apenas CatalogSnapshotMeta (para checagem rápida de hash)
```

**Política de invalidação:**

| Condição                                    | Ação                                               |
|---------------------------------------------|----------------------------------------------------|
| Cache ausente                               | Fetch remoto; grava `latest.json` e `latest_meta.json` |
| Cache presente, `created_at` < TTL (1 hora) | Usa cache local sem chamada remota                 |
| Cache presente, TTL expirado                | Fetch apenas do hash remoto; compara com `latest_meta.json`; fetch completo só se hash diferente |
| `--force-refresh` passado na CLI            | Ignora cache; fetch completo sempre                |
| `--offline` passado na CLI                  | Usa cache local mesmo com TTL expirado; falha se ausente |

O TTL padrão de 1 hora é configurável em `concilium.yaml`:

```yaml
catalog:
  remote_ttl_minutes: 60
  offline_fallback: true
```

---

### D5 — Detecção de Mudanças entre Execuções Consecutivas

Antes do início de cada run da pipeline (pré-`00-escopo`), o `CatalogLoader` compara o hash do catálogo atual com o hash do catálogo usado no run anterior do mesmo projeto.

```python
class CatalogDiff(BaseModel):
    previous_snapshot_id: str
    current_snapshot_id: str
    changed: bool
    added_cpus: list[str]      # códigos adicionados
    removed_cpus: list[str]    # códigos removidos
    modified_cpus: list[str]   # códigos com campos alterados
    added_insumos: list[str]
    removed_insumos: list[str]
    modified_insumos: list[str]
    summary: str               # ex: "3 CPUs modificadas, 1 insumo adicionado"
```

**Comportamento na pipeline:**

| Resultado do diff | Comportamento padrão                                                     |
|-------------------|--------------------------------------------------------------------------|
| `changed = False` | Pipeline continua normalmente; log de nível DEBUG                        |
| `changed = True`  | Log de nível WARNING com `summary`; pipeline continua (não bloqueia)     |
| `changed = True` + `--strict-catalog` | Pipeline abortada; operador deve confirmar com `--confirm-catalog-change` |

O `CatalogDiff` é salvo como artefato de nível `ArtifactKind.CATALOG_DIFF` no databook do projeto.

---

### D6 — Rollout em Fases: Compatibilidade com JSON Local

A migração para Google Sheets **não remove** o suporte ao JSON local. O `CatalogLoader` opera com dois backends:

```python
class CatalogBackend(str, Enum):
    LOCAL_JSON = "local_json"     # comportamento atual (padrão enquanto Google Sheets não estiver configurado)
    GOOGLE_SHEETS = "google_sheets"
```

A chave `catalog.backend` em `concilium.yaml` controla o backend ativo. Se `google_sheets` estiver configurado mas a API for inacessível, o loader faz fallback para `local_json` com aviso — desde que `offline_fallback: true`.

Isso garante que **projetos existentes não quebram** durante a migração.

---

## Rationale

- **SHA-256 de conteúdo normalizado** (JSON com chaves sorted, floats arredondados a 6 casas) garante determinismo do hash — mesmos dados, mesmo hash, independente de whitespace ou ordem de inserção.
- **Snapshot por versão de conteúdo** (não por data) evita duplicatas quando o catálogo não mudou entre dois acessos remotos.
- **Cache local com TTL** é o padrão para CLIs que acessam APIs externas (ex: `pip`, `helm`, `terraform`). O round-trip do Google Sheets Sheets API v4 é ~200-400ms; em pipelines com múltiplos skills isso acumula.
- **`CatalogDiff` como artefato** segue o padrão do ADR-018: toda informação relevante para auditoria é um `ArtifactEnvelope`.
- **Sem bloqueio por padrão** — engenheiro pode querer rodar com dados atualizados intencionalmente; o aviso é suficiente. O modo `--strict-catalog` é opt-in para ambientes de produção/licitação.

---

## Alternativas Descartadas

| Alternativa | Razão da descarte |
|-------------|-------------------|
| Git LFS para binários de catálogo | Não resolve edição colaborativa por não-TI |
| Webhook Google Sheets → CI/CD para gerar JSON | Acoplamento com infraestrutura CI; latência; não resolve cache local |
| Versão manual no nome do arquivo (`cpus_v1.3.json`) | Frágil; sem detecção automática; sem auditoria |
| DynamoDB / banco de dados para snapshots | Overhead de infraestrutura excessivo para o volume atual |

---

## Consequências

**Positivas:**
- Engenheiros de planejamento atualizam CPUs, produtividades e BDI sem acesso ao repositório.
- Toda proposta emitida tem rastreabilidade direta ao catálogo exato em vigor.
- Execuções consecutivas sem mudança de catálogo não adicionam latência de rede.
- Detecção de mudança previne uso acidental de dados desatualizados em runs encadeados.

**Negativas / Riscos:**
- Dependência de conectividade com Google APIs (mitigada por `offline_fallback`).
- Gerenciamento de credenciais (Service Account JSON) precisa de processo seguro — **nunca commitado no repositório**.
- Custo operacional de manter o schema das abas do Google Sheets sincronizado com os modelos Pydantic.

---

## Definition of Done

- [ ] `CatalogSnapshotMeta`, `CatalogSnapshot`, `CatalogDiff` definidos em `models/catalog_snapshot.py`
- [ ] `ArtifactMeta` extendido com `catalog_snapshot_id: str | None`
- [ ] `ArtifactKind.CATALOG_DIFF` adicionado ao enum existente
- [ ] `CatalogBackend` enum e configuração em `concilium.yaml` (`catalog.backend`, `catalog.remote_ttl_minutes`, `catalog.offline_fallback`)
- [ ] `CatalogLoader` com suporte a `LOCAL_JSON` e `GOOGLE_SHEETS` backend em `config/loaders.py` ou `config/catalog_loader.py`
- [ ] Cache local em `.concilium/catalog_cache/` com TTL e invalidação por hash
- [ ] Diff engine: `compute_catalog_diff(prev: CatalogSnapshot, curr: CatalogSnapshot) -> CatalogDiff`
- [ ] Integração com pipeline: diff executado em pré-`00-escopo`; resultado salvo como artefato
- [ ] `SnapshotStore` com backend `google_drive` para salvar/buscar snapshots no databook do projeto
- [ ] Flags CLI: `--force-refresh`, `--offline`, `--strict-catalog`, `--confirm-catalog-change`
- [ ] Testes: `test_cache_hit_no_roundtrip`, `test_hash_change_triggers_diff`, `test_same_hash_no_diff`, `test_offline_fallback`, `test_snapshot_immutable_on_same_hash`
- [ ] Documentação de setup da Service Account no `docs/engineering/setup/google-sheets-credentials.md`
- [ ] Credenciais **nunca** no repositório — path configurado via variável de ambiente `CONCILIUM__GOOGLE_CREDENTIALS`
