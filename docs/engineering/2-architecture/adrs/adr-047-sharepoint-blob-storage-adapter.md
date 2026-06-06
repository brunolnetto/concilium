# ADR-047 — SharePoint como Backend de Armazenamento via BlobStoragePort

**Status:** Implementado  
**Data:** 2026-05-12  
**Contexto:** MendesLobo Construtora — Concilium  
**Dependências:** ADR-033 (BlobStorage Port), ADR-024 (CatalogLoader), ADR-040 (Master vs. Project Layer), ADR-041 (SCD Type 2)

---

## Contexto

### Situação atual

O Concilium usa `LocalBlobStorage` (ADR-033) como único backend de armazenamento em produção. Catálogos, projetos e artefatos vivem no sistema de arquivos local da máquina onde o CLI ou MCP server está rodando. O stub `CloudBlobStorageAdapter` foi criado como placeholder para backends remotos, mas nunca implementado.

### Problema

- **P1 — Catálogo fora do ecossistema corporativo:** O catálogo Master (`config/catalogos/mendeslobo/`) é gerenciado via commits git por um subconjunto da equipe de engenharia. Engenheiros de campo e gestores não têm visibilidade nem acesso colaborativo — eles operam via planilha Excel no SharePoint de qualquer forma.

- **P2 — Projetos isolados por máquina:** Um projeto iniciado no laptop de um engenheiro não é visível para outro colega ou para o agente LLM em outra sessão. Não há repositório central de projetos versionados.

- **P3 — Auditoria externa exige localização conhecida:** Auditorias de contratos públicos requerem que os artefatos aprovados (canonical.json, resultado.xlsx) estejam em repositório corporativo auditável, não em diretório local.

- **P4 — M365 já é a infraestrutura corporativa existente:** A MendesLobo usa Microsoft 365. SharePoint/OneDrive for Business já é o DMS (Document Management System) em uso para contratos, planilhas e laudos de obra. Adicionar um armazenamento paralelo é fricção desnecessária.

### Oportunidade Técnica

A abstração `BlobStoragePort` (ADR-033) já existe e é implementada por `LocalBlobStorage`. O contrato público é mínimo:

```python
class BlobStoragePort(ABC):
    def ler_blob(self, path: str) -> bytes
    def gravar_blob(self, path: str, content: bytes) -> None
    def listar_blobs(self, prefix: str) -> list[str]
    def blob_existe(self, path: str) -> bool
```

O Microsoft Graph API expõe o SharePoint como um sistema de arquivos endereçável por caminho relativo (`/drives/{drive-id}/root:/{path}:/content`), com download URLs, upload sessions e versionamento nativo — um mapeamento natural para o contrato acima.

---

## Decisão

### D1 — `SharePointBlobStorage` implementando `BlobStoragePort`

Criar `src/concilium/infrastructure/adapters/sharepoint_blob_storage.py` como nova implementação concreta de `BlobStoragePort`. Todos os consumidores existentes (`CatalogLoader`, `ProjectStore`, `FileSystemArtifactStore`) continuam usando o port — a troca de backend é transparente.

```python
class SharePointBlobStorage(BlobStoragePort):
    def __init__(
        self,
        drive_id: str,           # ID do Drive SharePoint (documentLibrary)
        root_path: str,          # Caminho base dentro do drive (ex: "Concilium/producao")
        credential: SharePointCredential,  # Ver D2
        *,
        cache_dir: Path | None = None,     # Cache local (None = sem cache)
        cache_ttl_minutes: int = 60,
        read_only: bool = False,
    ) -> None
```

**Mapeamento de operações:**

| `BlobStoragePort` | Microsoft Graph API |
|---|---|
| `ler_blob(path)` | `GET /drives/{id}/root:/{root_path}/{path}:/content` → bytes via `@microsoft.graph.downloadUrl` |
| `gravar_blob(path, content)` | `PUT /drives/{id}/root:/{root_path}/{path}:/content` (< 4 MB) ou upload session (≥ 4 MB) |
| `listar_blobs(prefix)` | `GET /drives/{id}/root:/{root_path}/{prefix}:/children` → recursivo com paginação `@odata.nextLink` |
| `blob_existe(path)` | `GET /drives/{id}/root:/{root_path}/{path}` → 200 OK ou 404 |

**Separador de caminho:** O contrato do `BlobStoragePort` usa `/` como separador lógico — mapeamento direto para a hierarquia de pastas do SharePoint.

### D2 — Autenticação via Service Principal (MSAL)

O servidor MCP e o CLI rodam como processo de servidor, não como sessão interativa de usuário. A autenticação usa **client credentials flow** (app-only):

```python
@dataclass
class SharePointCredential:
    tenant_id: str
    client_id: str
    client_secret: str   # ou certificate_path: Path para produção

    def acquire_token(self) -> str:
        """Retorna Bearer token via MSAL ConfidentialClientApplication."""
```

**Configuração via variáveis de ambiente** (sem segredo em disco):

```bash
CONCILIUM__SP_TENANT_ID=<tenant-uuid>
CONCILIUM__SP_CLIENT_ID=<app-registration-uuid>
CONCILIUM__SP_CLIENT_SECRET=<secret>          # dev/CI
CONCILIUM__SP_CERT_PATH=/path/to/cert.pem     # produção (preferido)
CONCILIUM__SP_DRIVE_ID=<drive-id>
CONCILIUM__SP_ROOT_PATH=Concilium/producao
```

**Permissões mínimas necessárias (Microsoft Graph):**

| Escopo | Tipo | Finalidade |
|---|---|---|
| `Files.Read.All` | Application | Leitura de catálogos e projetos |
| `Files.ReadWrite.All` | Application | Gravação de projetos e resultados |
| `Sites.Read.All` | Application | Descoberta do Drive por site |

### D3 — Cache Local com TTL (Leitura)

`ler_blob` e `listar_blobs` consultam um cache local antes de chamar a API. O cache usa a mesma estrutura de TTL do `CatalogLoader` (ADR-024):

```
{cache_dir}/
  {sha256(path)[:16]}_{filename}.blob     ← conteúdo
  {sha256(path)[:16]}_{filename}.meta     ← ETag + last_modified + cached_at
```

**Política de invalidação:**
- ETag do Graph API comparado ao `meta` local: se diferente, baixa novamente.
- TTL expirado (padrão 60 min): força re-validação via `If-None-Match` (304 = cache válido).
- `blob_existe()` nunca usa cache — sempre consulta o Graph para garantir consistência.

**Modo offline:** Se `cache_dir` está configurado e a API está inacessível, o cache é usado mesmo com TTL expirado (comportamento idêntico ao `CatalogLoader(offline=True)`).

### D4 — Aprovação: Versionamento Major no SharePoint

O padrão de aprovação do `ProjectStore` (ADR-033) usa `chmod 444` para tornar `canonical.json` imutável. No SharePoint, o equivalente é **check-in de versão major com bloqueio**:

```python
def aprovar_versao(self, path: str) -> None:
    """Faz check-in de versão major e retira checkout — equivalente ao chmod 444."""
    # 1. Check in como versão major (não minor):
    POST /drives/{id}/root:/{path}:/checkin
    {"checkInAs": "majorVersion", "comment": "Aprovado via Concilium"}
    # 2. O arquivo passa a ser somente-leitura para edições diretas
    # 3. Novas versões só via nova operação de checkout — auditável no histórico nativo
```

O histórico de versões do SharePoint (`/versions` relationship) complementa o SCD Type 2 (ADR-041): qualquer arquivo no SharePoint tem trilha de versões nativa, visível no portal M365.

### D5 — Extensão do `CatalogLoader` para Backend SharePoint

`CatalogLoader` ganha o enum `SHAREPOINT` como novo backend:

```python
class CatalogBackend(str, Enum):
    LOCAL_JSON  = "local_json"
    SHAREPOINT  = "sharepoint"    # novo
    # GOOGLE_SHEETS = "google_sheets"  # futuro

class CatalogLoader:
    def __init__(
        self,
        config_root: Path | str,
        backend: CatalogBackend = CatalogBackend.LOCAL_JSON,
        sharepoint_storage: SharePointBlobStorage | None = None,
        ...
    )
```

Quando `backend=SHAREPOINT`, o loader substitui as leituras de `config_root/catalogos/{name}/` por chamadas ao `SharePointBlobStorage` usando o mesmo esquema de caminhos relativos. O bundle cache (`.catalog_bundle.json`) continua funcionando como camada de otimização.

### D6 — Estrutura de Pastas no SharePoint

O `root_path` configurado mapeia para a hierarquia existente do `BlobStoragePort`:

```
{Drive}/{root_path}/
├── config/
│   ├── catalogos/
│   │   └── mendeslobo/
│   │       ├── cpus/
│   │       ├── insumos/
│   │       └── producoes/
│   ├── contextos/
│   └── jurisdicoes/
└── projetos/
    └── {uuid}/
        ├── meta.json
        ├── overrides/
        └── escopos/{escopo_id}/
            └── planos/{plano_id}/
                ├── canonical.json
                └── outputs/
```

A estrutura é idêntica ao filesystem local — nenhum consumidor precisa saber qual backend está ativo.

---

## Alternativas Rejeitadas

| ID | Alternativa | Motivo |
|---|---|---|
| X1 | Azure Blob Storage (ADR-033 Fase 4 original) | Requer infraestrutura adicional (Storage Account); a MendesLobo já tem M365 e SharePoint licenciados — adicionar Azure Blob seria overlap sem necessidade. |
| X2 | SharePoint como filesystem montado (WebDAV) | WebDAV da Microsoft tem suporte inconsistente em ambientes sem Windows Explorer. Não funciona em CI Linux. Perda do acesso programático ao versioning e metadata. |
| X3 | Sincronização unidirecional (SharePoint → Local apenas) | Impede que o agente LLM grave projetos diretamente no repositório central; elimina a proposta de valor principal. |
| X4 | Graph SDK Python (`msgraph-sdk`) | O SDK oficial Python está em beta e muda breaking em minor versions. Usar `httpx` diretamente contra a REST API é mais estável e audito. |

---

## Consequências

### Positivas

| ID | Consequência |
|---|---|
| C1 | **Colaboração nativa:** Múltiplos engenheiros e o agente LLM operam sobre o mesmo repositório central de projetos sem sincronização manual. |
| C2 | **Auditoria M365:** Histórico de versões do SharePoint + logs de acesso do M365 Compliance Center — visíveis para TI sem infraestrutura adicional. |
| C3 | **Zero fricção para usuário final:** O engenheiro continua vendo os arquivos no SharePoint que já usa; o Concilium só adiciona automação sobre essa estrutura. |
| C4 | **Fallback local transparente:** Troca de `LocalBlobStorage` para `SharePointBlobStorage` é uma mudança de configuração, não de código. |
| C5 | **Catálogo colaborativo:** O Master pode ser editado diretamente no SharePoint por usuários não-técnicos (Excel, JSON via web editor), com o Concilium consumindo as atualizações automaticamente via TTL/delta. |

### Negativas / Riscos

| ID | Risco | Mitigação |
|---|---|---|
| R1 | Latência da API vs. filesystem local (50–300 ms/operação). | Cache local obrigatório para catálogos; projetos ativos em cache até `aprovar_versao`. |
| R2 | Rate limiting do Graph API (10.000 req/10 min por app por tenant). | Backoff exponencial; bundle cache reduz reads a 1 req por catálogo; `listar_blobs` paginado. |
| R3 | Secret de Service Principal exposto em variáveis de ambiente. | Usar certificado em produção (não `client_secret`); rotação via Key Vault ou Azure Managed Identity se disponível. |
| R4 | Permissões `Files.ReadWrite.All` são amplas. | Escopar o App Registration ao site/drive específico via SharePoint App-Only via `sites/{id}/drives`; não usar permissões tenant-wide. |
| R5 | Conflito de escrita concorrente (dois agentes gravando o mesmo projeto). | `gravar_blob` usa `If-Match: {etag}` para otimistic concurrency; conflito retorna 412 → erro de pré-condição visível no MCP. |
| R6 | Renomeação de pastas no SharePoint quebra caminhos salvos. | `drive_id` + caminho relativo ao `root_path` é estável se o root não for movido; documentar como invariante de operação. |

---

## Plano de Implementação

| Fase | Entregas | Status |
|---|---|---|
| **F1 — Credencial e token** | `SharePointCredential` + MSAL client credentials flow; teste de autenticação isolado | ✅ Concluído |
| **F2 — Adapter read-only** | `SharePointBlobStorage.ler_blob`, `blob_existe`, `listar_blobs`; cache local com TTL + ETag | ✅ Concluído |
| **F3 — Adapter write** | `gravar_blob` com upload session para arquivos grandes; If-Match para concorrência | ✅ Concluído |
| **F4 — CatalogLoader backend** | `CatalogBackend.SHAREPOINT` integrado ao `CatalogLoader` | ✅ Concluído |
| **F5 — ProjectStore backend** | `StorageProjectHandle` + `StorageProjectRepository` via `BlobStoragePort` | ✅ Concluído |
| **F6 — Aprovação** | `aprovar_versao()` na `BlobStoragePort` + SharePoint checkin major version | ✅ Concluído |
| **F7 — CLI e MCP config** | `concilium health` verifica conectividade SharePoint quando `CONCILIUM__SP_DRIVE_ID` presente | ✅ Concluído |

## Arquivos criados/modificados

| Arquivo | Papel |
|---------|-------|
| `infrastructure/adapters/sharepoint_blob_storage.py` | `SharePointCredential`, `SharePointBlobStorage`, `StorageConcurrencyError` |
| `infrastructure/storage/storage_project_repository.py` | `StorageProjectHandle`, `StorageProjectRepository` |
| `domain/repositories/blob_storage_port.py` | `aprovar_versao()` noop adicionado |
| `infrastructure/adapters/local_blob_storage.py` | `aprovar_versao()` via chmod 444 |
| `infrastructure/catalog/catalog_loader.py` | `CatalogBackend.SHAREPOINT`, `_load_sharepoint()` |
| `presentation/cli/commands_health.py` | Verificação de conectividade SharePoint |
| `pyproject.toml` | `[project.optional-dependencies] sharepoint = [msal, httpx]` |
| `tests/unit/test_adr047_sharepoint.py` | 40 testes com mock do Graph API |

---

## Definition of Done

### Fase 1 — Credencial
- [ ] `SharePointCredential.acquire_token()` retorna token válido dado as env vars.
- [ ] Token renovado automaticamente antes da expiração (60 min padrão).
- [ ] Teste de integração isolado: autenticar e listar drives do site.

### Fase 2 — Leitura
- [ ] `ler_blob("config/catalogos/mendeslobo/cpus/cpu_001.json")` retorna os bytes corretos.
- [ ] Cache hit evita chamada à API após TTL não expirado.
- [ ] Modo offline funciona com cache existente quando API inacessível.
- [ ] `listar_blobs("config/catalogos/mendeslobo/cpus/")` retorna lista completa (paginação).

### Fase 3 — Escrita
- [ ] `gravar_blob` para arquivo < 4 MB funciona via PUT direto.
- [ ] `gravar_blob` para arquivo ≥ 4 MB usa upload session corretamente.
- [ ] Conflito de escrita (412 Precondition Failed) lança `StorageConcurrencyError`.

### Fase 4 — CatalogLoader
- [ ] `CatalogLoader(backend="sharepoint", sharepoint_storage=...)` carrega catálogo mendeslobo sem erro.
- [ ] Bundle cache (`.catalog_bundle.json`) gerado localmente após primeira carga.
- [ ] `concilium catalog manage quality --contexto mendeslobo` executa via SharePoint backend.

### Fase 5 — ProjectStore
- [ ] `ProjectStore.init(...)` cria estrutura de pastas no SharePoint.
- [ ] Pipeline completo (Skills 00→06) executado com `ProjectStore` sobre SharePoint.
- [ ] `canonical.json` gravado e relido corretamente via SharePoint.

### Fase 6 — Aprovação
- [ ] `aprovar_versao()` faz checkin de versão major; arquivo aparece como somente-leitura no portal M365.
- [ ] Tentativa de sobrescrever versão aprovada retorna erro de pré-condição.

### Fase 7 — Integração
- [ ] `concilium health` exibe linha "SharePoint conectividade" com ✅/❌.
- [ ] `ping` MCP retorna `"backend": "sharepoint"` quando configurado.
- [ ] Sem variáveis de ambiente SharePoint → fallback silencioso para `LocalBlobStorage`.

---

## Referências

- Microsoft Graph API — OneDrive Resources: https://learn.microsoft.com/en-us/graph/api/resources/onedrive?view=graph-rest-1.0
- Microsoft Graph API — Drive Resource: https://learn.microsoft.com/en-us/graph/api/resources/drive?view=graph-rest-1.0
- Microsoft Graph API — DriveItem Resource: https://learn.microsoft.com/en-us/graph/api/resources/driveitem?view=graph-rest-1.0
- MSAL Python: https://github.com/AzureAD/microsoft-authentication-library-for-python
- ADR-033 — Blob Storage + Excel Ingestion (BlobStoragePort)
- ADR-024 — Referências em Planilha Editável + Snapshot Auditável (CatalogLoader)
- ADR-040 — Hierarquia Master vs. Project Layer
- ADR-041 — SCD Type 2 para Rastreabilidade Histórica
