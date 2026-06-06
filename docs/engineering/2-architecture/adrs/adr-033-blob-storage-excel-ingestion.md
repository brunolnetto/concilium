# ADR-033 — Abstração de Blob Storage e Arbitragem Temporal via Excel

**Status:** Implementado  
**Data:** 2026-05-07  
**Contexto:** MendesLobo Construtora — Concilium

---

## Contexto

### Problema

Atualmente, o sistema Concilium lê o catálogo diretamente do Filesystem local (`infrastructure/storage/`), o que traz limitações em um ambiente corporativo e colaborativo:

1. **Storage Engessado:** O modelo atual assume um sistema de arquivos local. Queremos acoplar o Concilium a provedores de Blob Storage da MendesLobo (como Google Drive, SharePoint ou AWS S3) para garantir que a equipe inteira consuma a mesma base centralizada de dados corporativos.
2. **Ciclo de Vida do Catálogo (Entrypoint):** A engenharia de custos utiliza rotineiramente planilhas Excel como "Source of Truth" (SoT) humana para a manutenção de insumos e composições. O framework precisa aceitar e ingerir essas planilhas com segurança.
3. **Arbitragem Temporal:** Como os insumos e composições variam de preço periodicamente, os engenheiros precisam de um mecanismo dentro do projeto/escopo para definir *qual versão do catálogo* (qual snapshot temporal) servirá como base para as estimativas. Isso permite realizar análises retroativas, reajustamentos e congelar preços para licitações de longa duração.

---

## Decisão

Para resolver esses pontos, definimos um novo fluxo de ingestão e armazenamento de catálogo:

### D1 — Abstração do Blob Storage (`BlobStoragePort`)

Substituiremos a dependência rígida de sistema de arquivos por uma interface (`Port`) na camada de Domínio, seguindo o padrão de injeção de dependência do ADR-029:

```python
# src/concilium/domain/repositories/blob_storage_port.py
from abc import ABC, abstractmethod

class BlobStoragePort(ABC):
    @abstractmethod
    def ler_blob(self, path: str) -> bytes: ...
    
    @abstractmethod
    def gravar_blob(self, path: str, content: bytes) -> None: ...
    
    @abstractmethod
    def listar_blobs(self, prefix: str) -> list[str]: ...
```

A camada `infrastructure/adapters/` abrigará as implementações concretas:
- `LocalBlobStorage` (Filesystem padrão, usado para dev e testes).
- `SharePointBlobStorage` / `GoogleDriveBlobStorage` (Integração corporativa via APIs).

### D2 — Excel como Entrypoint de Ingestão de Catálogo

A camada de infraestrutura (`infrastructure/catalog/`) conterá um *Ingestion Pipeline*. Ele fará o parsing da planilha mestre corporativa de custos (Excel), aplicará todas as validações pesadas definidas no ADR-032 e no `ValidadorCPUInsumo`, e então gerará os arquivos JSON versionados (instâncias de `InsumoVersionado` e `CPUVersionada`). 

Esses artefatos finais JSON (agora auditados e garantidos sem ciclos) serão "commitados" no Blob Storage.

### D3 — Arbitragem Temporal no Escopo do Projeto

O modelo `Projeto` (ou `Escopo` do ADR-031) passará a deter a propriedade de arbitragem temporal — um *timestamp* ou *tag* oficial:

```python
class Escopo(BaseModel):
    # ...
    data_base_orcamento: date | None = None
    tag_versao_catalogo: str | None = None
```

Quando o pipeline de engenharia (Skills 00 a 07) for acionado, ele injetará o catálogo inteiro, mas ao ler o custo de um insumo, exigirá a leitura do preço *restrito ao período do escopo*:

`preco = insumo.preco_em(escopo.data_base_orcamento)`

Isso isola o cálculo de flutuações futuras do catálogo corporativo, viabilizando o congelamento exigido em licitações.

---

## Consequências

### Positivas

- **Desacoplamento de infraestrutura:** O código core das Skills não precisará saber se está operando no disco local ou em nuvem.
- **Aderência Orgânica aos Processos:** Mantém-se o Excel como ferramenta para atualização e manutenção cadastral (curva de aprendizado zero para cadastro), mas delega ao software a responsabilidade por rigor, integridade e versionamento imutável.
- **"Time-Travel" e Reprodutibilidade:** Capacidade total de reprocessar orçamentos gerados há 2 anos resultando exatamente no mesmo valor do passado.

### Negativas / Riscos

- **Overhead de Rede:** Leitura sistemática de Blobs em nuvem é consideravelmente mais lenta que I/O SSD. **Mitigação:** Criação de um cache em memória (ou disco temporário local) dentro da camada de infraestrutura ao fazer o download do snapshot do catálogo.
- **Fragilidade do Excel:** O pipeline de ingestão precisará ser rígido. Se a engenharia alterar a estrutura das colunas na planilha mestre, o parser pode quebrar. **Mitigação:** Template bloqueado e feedback imediato via CLI caso a validação do esquema da planilha falhe.

---

## Plano de Implementação Sugerido

1. **Fase 1 (Abstração):** Criação da interface `BlobStoragePort` e do adapter `LocalBlobStorage`. Injeção da porta no código existente.
2. **Fase 2 (Ingestão):** Desenvolvimento do `ExcelIngestionPipeline` conectando o parsing da planilha às validações de domínio (ADR-032).
3. **Fase 3 (Arbitragem):** Atualização dos modelos de `Escopo`/`Projeto` para incorporar o controle temporal, e refatoração das *Skills* para que consumam a função `preco_em(data)`.
4. **Fase 4 (Nuvem):** Implementação e plug-in do Adapter para Google Drive ou SharePoint.

---

## Definition of Done

### Fase 1 — Abstração de Storage
- [x] `BlobStoragePort` criado em `domain/repositories/`.
- [x] `LocalBlobStorage` criado em `infrastructure/adapters/`.
- [x] Pontos de acesso ao filesystem migrados para a porta abstrata.

### Fase 2 — Ingestão de Excel
- [x] Pipeline de parsing de Excel criado em `infrastructure/catalog/excel_ingestion.py`.
- [x] Ingestão passa pelas regras `VAL-CPU-INS` e DFS de ciclos antes de salvar.
- [x] Saída do pipeline salva blobs JSON válidos usando `BlobStoragePort`.

### Fase 3 — Arbitragem Temporal
- [x] Modelo `Escopo` atualizado com `data_base_orcamento`.
- [x] Repositórios e Skills 00 a 07 atualizados para consultar versão pontual com fallback (Finaliza Fase 4 do ADR-032).
- [x] Testes validando snapshot temporal fixo passando.

### Fase 4 — Integração Nuvem
- [x] Adapters para provedores de nuvem (SharePoint/GDrive) funcionais.
- [x] Credenciais e configs suportadas via environment/secrets.
