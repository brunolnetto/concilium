# ADR-031 — Escopos Múltiplos e Planos de Trabalho Paralelos por Projeto

**Status:** Implementado 
**Data:** 2026-05-05  
**Contexto:** MendesLobo Construtora — Concilium

---

## Modelo de Dados Implementado

> Extrato exato do código-fonte. Referência canônica para leitura do ADR.

### Hierarquia de entidades

```
Projeto  (container — meta.json, não porta pipeline)
└── Escopo  (unidade de pipeline — escopo.json)
    └── PlanoTrabalho  (instância de planejamento — plano.json + canonical.json)
```

### Filesystem

```
projetos/{projeto_id}/
├── meta.json                          ← ProjectStore.meta
├── snapshots/
└── escopos/
    └── {escopo_id}/
        ├── escopo.json                ← EscopoStore.meta / Escopo
        └── planos/
            └── {plano_id}/
                ├── plano.json         ← PlanoStore.meta / PlanoTrabalho
                ├── canonical.json     ← CanonicalModel (pipeline completo)
                ├── invocations.log    ← JSONL, uma entrada por skill
                └── outputs/           ← Excel, relatórios gerados
```

Projetos pré-ADR-031 com estrutura `vN/` continuam funcionando via `_LegacyEscopoShim` (§D9).

### `Escopo` — `src/concilium/domain/models/escopo.py`

| Campo | Tipo | Padrão | Descrição |
|---|---|---|---|
| `escopo_id` | `str` | — | Slug único dentro do projeto. Ex.: `"lote-a"`, `"default"` |
| `projeto_id` | `str` | — | UUID do projeto pai |
| `nome` | `str` | — | Ex.: `"Lote A — Terraplenagem"` |
| `tipo_obra` | `Literal` | — | `"terraplenagem"` \| `"pavimentacao"` \| `"saneamento"` |
| `localizacao` | `str` | — | Localização textual |
| `coordenadas_lat` | `float` | — | [-90, 90] |
| `coordenadas_lng` | `float` | — | [-180, 180] |
| `dias_semana` | `int` | `6` | [1, 7] |
| `horas_dia` | `int` | `8` | [1, 24] |
| `data_inicio` | `date` | — | |
| `data_termino` | `date` | — | |
| `status` | `Literal` | `"RASCUNHO"` | `RASCUNHO` \| `EM_VALIDACAO` \| `APROVADO` \| `EM_EXECUCAO` \| `CONCLUIDO` |
| `criado_em` | `datetime` | `now()` | |
| `snapshot_catalogo_id` | `str` | `""` | Pode diferir entre escopos do mesmo projeto |
| `snapshot_perfil_id` | `str` | `""` | |
| `bdi_perfil_id` | `str \| None` | `None` | |
| `revisao` | `int` | `1` | ≥ 1 |

### `PlanoTrabalho` — `src/concilium/domain/models/escopo.py`

| Campo | Tipo | Padrão | Descrição |
|---|---|---|---|
| `plano_id` | `str` | `uuid4()` | UUID gerado ou slug descritivo |
| `escopo_id` | `str` | — | |
| `projeto_id` | `str` | — | |
| `nome` | `str` | — | Ex.: `"Plano Agressivo — 4 equipes"` |
| `status` | `StatusPlano` | `"RASCUNHO"` | `RASCUNHO` → `EM_ANALISE` → `APROVADO` \| `ARQUIVADO` |
| `criado_em` | `datetime` | `now()` | |
| `hipotese` | `str \| None` | `None` | Hipótese principal que diferencia o plano |
| `versao_iteracao` | `int` | `1` | ≥ 1; incrementa em `new_iteration()` |

**Restrição:** no máximo **1** plano `APROVADO` por escopo. `approve_plan(id)` arquiva automaticamente todos os demais `RASCUNHO`/`EM_ANALISE`.

### `CanonicalModel.meta` — `src/concilium/domain/models/canonical.py`

| Campo | Tipo | Padrão | Descrição |
|---|---|---|---|
| `versao_schema` | `str` | `"1.0.0"` | |
| `gerado_em` | `datetime` | — | |
| `framework` | `Literal` | `"concilium"` | |
| `contexto_id` | `str` | — | |
| `escopo_id` | `str` | `"default"` | **ADR-031** — escopo que gerou este canônico |
| `plano_id` | `str \| None` | `None` | **ADR-031** — plano que gerou este canônico |

### `ResultadoConsolidadoProjeto` — `src/concilium/domain/models/resultado_consolidado.py`

Calculado on-the-fly por `resumo_projeto()`. Não persiste em disco.

**Limiares de `StatusMargem`:** `VERDE` ≥ 8 pp · `AMARELO` ≥ 4 pp · `VERMELHO` < 4 pp

| Campo | Tipo | Descrição |
|---|---|---|
| `projeto_id` | `str` | |
| `escopos_incluidos` | `list[str]` | IDs com pipeline completo |
| `escopos_excluidos` | `list[str]` | IDs sem canonical/resultado |
| `venda_total_com_bdi` | `float` | Soma dos escopos incluídos |
| `custo_total` | `float` | |
| `resultado_financeiro` | `float` | `venda_total - custo_total` |
| `margem_pct` | `float` | `resultado / venda_total` |
| `status_margem` | `StatusMargem` | Agregado do projeto |
| `breakdown` | `list[BreakdownEscopo]` | Um item por escopo incluído |
| `avisos` | `list[str]` | Ex.: escopos excluídos por pipeline incompleto |

**`BreakdownEscopo`:**

| Campo | Tipo | Descrição |
|---|---|---|
| `escopo_id` | `str` | |
| `nome` | `str` | |
| `plano_id` | `str` | Plano usado na consolidação |
| `status_plano` | `str` | `APROVADO`, `EM_ANALISE`, etc. |
| `venda_com_bdi` | `float` | |
| `custo_total` | `float` | |
| `resultado_financeiro` | `float` | |
| `margem_pct` | `float` | |
| `status_margem` | `StatusMargem` | |
| `peso_relativo` | `float` | `venda_com_bdi / venda_total_projeto` ∈ [0, 1] |

---

## Contexto

### Problema

O modelo atual trata um `Projeto` como a unidade mínima de pipeline: um projeto possui exatamente uma EAP, um cronograma, um planejamento e um resultado. Versões (`v1`, `v2`, `v3`) expressam iterações **sequenciais** sobre esse planejamento único — aprovadas uma a uma via `aprovar_versao`.

Essa estrutura é inadequada para dois cenários recorrentes da MendesLobo:

#### P1 — Projeto com múltiplas obras independentes

Uma licitação de rodovia pode conter sub-obras com tipos e cronogramas distintos:
- Lote A: terraplenagem (6 meses)
- Lote B: pavimentação asfáltica (4 meses, inicia em semana 12)
- Lote C: obras de arte correntes (paralelo ao Lote B)

Cada obra tem sua própria EAP, suas equipes diretas, seu BDI e seu cronograma. O resultado financeiro do projeto é a composição dos três. No modelo atual, não há como representar isso — forçando o engenheiro a criar três projetos artificialmente separados, perdendo a visão consolidada e a capacidade de análise cruzada (ex.: pool de recursos compartilhado entre lotes).

#### P2 — Múltiplos planejamentos alternativos em paralelo para a mesma obra

Antes de aprovar, o engenheiro quer comparar simultaneamente:
- Plano "Agressivo": 4 equipes, DMT 1500 m, prazo 5 meses
- Plano "Conservador": 2 equipes, DMT 2000 m, prazo 8 meses
- Plano "Referência BDI": com BDI da jurisdição federal vs. estadual

No modelo atual, explorar alternativas exige criar versões sequenciais (`v1`, `v2`, `v3`) com copy-on-write, mas **apenas uma pode estar "ativa"** por vez (campo `current_version`). Não há semântica para "plano candidato" distinto de "versão de trabalho".

#### P3 — CLI e MCP sem granularidade de escopo/plano

Todos os comandos CLI e ferramentas MCP operam em `project_id` + `version`. Não há como endereçar:
- "Execute a skill 03 **apenas no Lote B**"
- "Compare a margem do plano Agressivo vs. plano Conservador **na obra de terraplenagem**"
- "Qual o resultado consolidado do projeto somando os três lotes aprovados?"

### Enunciado formal do problema

O espaço de decisão atual é:

$$\text{Pipeline}(p) \rightarrow v_N$$

onde $p$ é um projeto monolítico e $v_N$ é a versão sequencial corrente. Precisamos de:

$$\text{Pipeline}(e_{i}, q_{j}) \rightarrow r_{ij}$$

onde $e_i \in \text{Escopos}(p)$ é uma obra e $q_j \in \text{Planos}(e_i)$ é um plano de trabalho candidato para essa obra, com múltiplos $j$ coexistindo em paralelo.

---

## Decisão

### D1 — `Escopo`: nova entidade de domínio, unidade de pipeline

Introduzir `Escopo` como a entidade que **porta o pipeline** (EAP → cronograma → planejamento → resultado). O `Projeto` torna-se um **container organizacional** de um ou mais escopos.

```python
# src/concilium/domain/models/escopo.py
class Escopo(BaseModel):
    """Unidade de pipeline dentro de um projeto (ADR-031 §D1).

    Representa uma obra específica (lote, fase, subdivisão contratual) com sua
    própria EAP, tipo de obra, datas e cronograma independente. O pipeline
    (skills 00→11) opera sobre um Escopo + PlanoTrabalho, não sobre o Projeto.
    """
    model_config = ConfigDict(extra="ignore")

    escopo_id: str                          # slug único dentro do projeto. Ex.: 'lote-a', 'default'
    projeto_id: str                         # UUID do projeto pai
    nome: str                               # Ex.: 'Lote A — Terraplenagem'
    tipo_obra: Literal["terraplenagem", "pavimentacao", "saneamento"]
    localizacao: str
    coordenadas_lat: float = Field(ge=-90, le=90)
    coordenadas_lng: float = Field(ge=-180, le=180)
    dias_semana: int = Field(default=6, ge=1, le=7)
    horas_dia: int = Field(default=8, ge=1, le=24)
    data_inicio: date
    data_termino: date
    status: Literal["RASCUNHO", "EM_VALIDACAO", "APROVADO", "EM_EXECUCAO", "CONCLUIDO"] = "RASCUNHO"
    criado_em: datetime = Field(default_factory=lambda: datetime.now())
    # Snapshots do catálogo e perfil BDI — podem diferir entre escopos do mesmo projeto
    snapshot_catalogo_id: str = ""
    snapshot_perfil_id: str = ""
    bdi_perfil_id: str | None = None
    revisao: int = Field(default=1, ge=1)
```

O `Projeto` passa a conter apenas metadados organizacionais (campo `CanonicalModel.projeto`, inalterado até ADR-032):

```python
# src/concilium/domain/models/projeto.py (existente — não alterado neste ADR)
class Projeto(BaseModel):
    """Container organizacional. Não porta pipeline diretamente (ADR-032 adia split)."""
    id: UUID | str
    nome: str
    localizacao: str
    coordenadas: Coordenadas
    tipo_obra: Literal["terraplenagem", "pavimentacao", "saneamento"]
    data_inicio: date
    data_termino: date
    status: StatusProjeto = "RASCUNHO"
    snapshot_catalogo_id: str
    snapshot_perfil_id: str
    revisao: int = Field(default=1, ge=1)
```

**Regra de herança:** ao criar um `Escopo`, os campos `snapshot_catalogo_id`, `snapshot_perfil_id`, `bdi_perfil_id`, `regime_trabalho` e `coordenadas` herdam do `Projeto` por padrão e podem ser sobrescritos individualmente.

**Retrocompatibilidade:** projetos existentes com estrutura `v1/canonical.json` são lidos como se tivessem um escopo implícito `escopo_id = "default"` com `plano_id = "v1"` (D9 §shim).

---

### D2 — `PlanoTrabalho`: unidade de planejamento nomeada, paralela

Introduzir `PlanoTrabalho` como o contêiner de um pipeline completo executado para um dado escopo. Múltiplos planos podem coexistir **em paralelo** para o mesmo escopo.

```python
# src/concilium/domain/models/escopo.py
StatusPlano = Literal["RASCUNHO", "EM_ANALISE", "APROVADO", "ARQUIVADO"]

class PlanoTrabalho(BaseModel):
    """Instância de planejamento para um escopo (ADR-031 §D2).

    Múltiplos planos coexistem em paralelo para o mesmo escopo. Cada plano tem
    seu próprio pipeline independente (canonical isolado).
    """
    model_config = ConfigDict(extra="ignore")

    plano_id: str = Field(
        default_factory=lambda: str(uuid4()),   # UUID gerado ou slug descritivo
        description="UUID gerado automaticamente ou slug descritivo.",
    )
    escopo_id: str
    projeto_id: str
    nome: str                                   # Ex.: 'Plano Agressivo — 4 equipes'
    status: StatusPlano = "RASCUNHO"
    criado_em: datetime = Field(default_factory=lambda: datetime.now())
    hipotese: str | None = None                 # hipótese principal que diferencia o plano
    versao_iteracao: int = Field(default=1, ge=1)  # incremental dentro do mesmo plano
```

**Ciclo de vida dos planos:**

| Estado | Semântica |
|---|---|
| `RASCUNHO` | Pipeline em andamento, qualquer skill pode ser re-executada |
| `EM_ANALISE` | Pipeline completo, aguardando decisão de aprovação |
| `APROVADO` | `canonical.json` imutável (chmod 444); exatamente **um** plano aprovado por escopo |
| `ARQUIVADO` | Descartado após decisão; mantido para histórico de auditoria |

**Restrição:** cada escopo admite no máximo **um** plano `APROVADO`. Aprovar um plano arquiva automaticamente todos os demais `EM_ANALISE`.

---

### D3 — Reestruturação do filesystem (`ProjectStore`)

```
projetos/{projeto_id}/
├── meta.json                                ← metadados do Projeto (D1)
├── snapshots/                               ← compartilhado entre todos os escopos
│
└── escopos/
    ├── {escopo_id}/                         ← ex.: "lote-a", "lote-b"
    │   ├── escopo.json                      ← metadados do Escopo (D1)
    │   └── planos/
    │       ├── {plano_id}/                  ← ex.: UUID ou slug "plano-agressivo"
    │       │   ├── canonical.json           ← canônico do plano
    │       │   ├── invocations.log          ← log de skills executadas
    │       │   ├── plano.json               ← metadados do PlanoTrabalho (D2)
    │       │   └── outputs/                 ← Excel, relatórios gerados
    │       └── {plano_id_2}/                ← plano alternativo paralelo
    │
    └── {escopo_id_2}/
        ├── escopo.json
        └── planos/
            └── {plano_id}/
                └── ...
```

**Operações adicionadas ao `ProjectStore`:**

```python
# src/concilium/infrastructure/storage/project.py (extensão)
class ProjectStore:
    def _is_legacy(self) -> bool: ...                    # True se usa vN/ sem escopos/
    def create_escopo(self, escopo_id: str, nome: str, tipo_obra: str,
                      localizacao: str, coordenadas_lat: float, coordenadas_lng: float,
                      data_inicio: str, data_termino: str,
                      dias_semana: int = 6, horas_dia: int = 8,
                      snapshot_catalogo_id: str = "",
                      snapshot_perfil_id: str = "",
                      bdi_perfil_id: str | None = None) -> EscopoStore: ...
    def list_escopos(self) -> list[str]: ...             # ordenado; ['default'] em legado
    def escopo(self, escopo_id: str = "default") -> EscopoStore: ...  # ou shim

# src/concilium/infrastructure/storage/escopo_store.py (novo)
class EscopoStore:
    """Gerencia diretório de um escopo: planos, aprovação."""
    ESCOPO_FILE = "escopo.json"

    def __init__(self, root: Path): ...

    @property
    def escopo_id(self) -> str: ...
    @property
    def meta(self) -> dict: ...                          # conteúdo de escopo.json
    def update_meta(self, **changes) -> None: ...
    def to_escopo(self) -> Escopo | None: ...

    def create_plan(self, nome: str, hipotese: str | None = None,
                    plano_id: str | None = None) -> PlanoStore: ...
    def list_plans(self) -> list[str]: ...
    def plan(self, plano_id: str) -> PlanoStore: ...
    def approved_plan(self) -> PlanoStore | None: ...
    def active_plan(self) -> PlanoStore | None: ...      # aprovado, ou rascunho mais recente
    def approve_plan(self, plano_id: str) -> list[str]: ... # retorna lista de arquivados

class PlanoStore:
    """Gerencia diretório de um plano: canonical, invocations, outputs."""
    CANONICAL_FILE  = "canonical.json"
    INVOCATIONS_LOG = "invocations.log"
    PLANO_FILE      = "plano.json"

    def __init__(self, root: Path): ...

    @property
    def plano_id(self) -> str: ...
    @property
    def meta(self) -> dict: ...                          # conteúdo de plano.json
    @property
    def status(self) -> StatusPlano: ...

    def load_canonical(self) -> CanonicalModel | None: ...
    def save_canonical(self, model: CanonicalModel,
                       trace_id: str | None = None,
                       created_by: str = "runtime",
                       parent_refs: list | None = None) -> None: ...
    def write_canonical_raw(self, content: dict) -> None: ...
    def approve(self) -> None: ...                       # chmod 444 + status=APROVADO
    def archive(self) -> None: ...                       # status=ARQUIVADO
    def set_em_analise(self) -> None: ...
    def new_iteration(self, base_plano: PlanoStore | None = None) -> PlanoStore: ...

    def log_invocation(self, entry: dict) -> None: ...
    def read_invocations(self) -> list[dict]: ...
    def save_output_file(self, data: bytes, filename: str = "resultado.xlsm") -> Path: ...
    def load_output_file(self, filename: str = "resultado.xlsm") -> bytes | None: ...
    def list_output_files(self) -> list[str]: ...
```

**Regra de isolamento:** nenhum plano lê ou grava no diretório de outro plano. Pool de recursos compartilhado entre escopos do mesmo projeto é endereçado pela camada de Application (não pelo filesystem).

---

### D4 — `CanonicalModel.meta`: adição de `escopo_id` e `plano_id`

```python
# src/concilium/domain/models/canonical.py — classe Meta (implementado)
class Meta(BaseModel):
    model_config = ConfigDict(extra="ignore")

    versao_schema: str = "1.0.0"
    gerado_em: datetime
    framework: Literal["concilium"] = "concilium"
    contexto_id: str
    escopo_id: str = "default"      # ADR-031 §D4: escopo que gerou este canônico
    plano_id: str | None = None     # ADR-031 §D4: plano que gerou este canônico
```

O `CanonicalModel` **não muda sua estrutura de pipeline** — continua tendo `eap`, `cronograma`, `planejamento`, `equipes_diretas`, etc. A diferença é que agora esses dados são **de um escopo específico**, identificado por `meta.escopo_id`.

---

### D5 — `CanonicalModel.projeto` mantém escopo embutido para retrocompatibilidade

O campo `projeto` em `CanonicalModel` é mantido sem alterações nesta versão. Em canônicos gerados com a nova estrutura, `projeto.id` continua referenciando o projeto-pai, e os campos de escopo (`tipo_obra`, `data_inicio`, `data_termino`, `regime_trabalho`, `coordenadas`) são populados com os valores do `Escopo` que gerou o canônico.

> **Decisão de escopo**: a criação de um `EscopoModel` separado dentro de `CanonicalModel` (substituindo `projeto`) é adiada para ADR-032. Neste ADR apenas o filesystem e as camadas de apresentação evoluem; o domínio interno do canônico permanece estável.

---

### D6 — Interface CLI: novos grupos `escopo` e `plano`

#### Novos grupos de comandos

```bash
# Escopos
concilium escopo criar <projeto> --nome "Lote A" --tipo-obra terraplenagem \
    --data-inicio 2026-06-01 --data-termino 2026-12-31
concilium escopo listar <projeto>
concilium escopo status <projeto> <escopo_id>

# Planos
concilium plano criar <projeto> <escopo_id> --nome "Plano Agressivo" \
    --hipotese "4 equipes, DMT 1500m"
concilium plano listar <projeto> <escopo_id>
concilium plano aprovar <projeto> <escopo_id> <plano_id>
concilium plano arquivar <projeto> <escopo_id> <plano_id>
concilium plano comparar <projeto> <escopo_id> <plano_id_a> <plano_id_b>
```

#### Comandos existentes: novos parâmetros `--escopo` e `--plano`

```bash
# Antes
concilium run <projeto> --skill 03-equipes-diretas

# Depois  
concilium run <projeto> --escopo lote-a --plano plano-agressivo --skill 03-equipes-diretas
```

**Regra de default:** se o projeto tem exatamente **um** escopo, `--escopo` é inferido automaticamente. Se o escopo tem exatamente **um** plano em estado `RASCUNHO` ou `EM_ANALISE`, `--plano` é inferido automaticamente. Ambiguidade → erro explícito solicitando o parâmetro.

**Retrocompatibilidade CLI:** `concilium run <projeto>` sem `--escopo` e `--plano` continua funcionando em projetos legados via shim D9.

---

### D7 — Interface MCP: nova camada de escopos e planos

#### Novas ferramentas MCP de gerenciamento

```
listar_escopos(project_id)
    → lista escopos com status, tipo_obra, data_termino, planos_ativos

criar_escopo(project_id, escopo_id, nome, tipo_obra, data_inicio, data_termino,
             localizacao?, coordenadas_lat?, coordenadas_lng?, dias_semana?, horas_dia?)
    → escopo_id, caminho

listar_planos(project_id, escopo_id)
    → lista planos com status, hipotese, skills_executadas, margem_pct (se disponível)

criar_plano(project_id, escopo_id, nome, hipotese?)
    → plano_id

aprovar_plano(project_id, escopo_id, plano_id)
    → status, planos_arquivados
```

#### Ferramentas de análise cross-escopo (novas)

```
resumo_projeto(project_id)
    → Agrega resultado financeiro de todos os escopos com plano APROVADO (ou mais avançado).
      Retorna: venda_total, custo_total, resultado_financeiro, margem_pct_ponderada,
               status_margem_geral, breakdown_por_escopo

comparar_planos(project_id, escopo_id, plano_ids: list[str])
    → Tabela comparativa: margem, custo_total, makespan, num_equipes, razao_indireto_direto
      por plano. Identifica o Pareto-dominante (menor custo + maior margem + menor prazo).

comparar_escopos(project_id, escopo_ids?: list[str])
    → Compara escopos do projeto: peso relativo no custo total, risco por margem,
      caminho crítico dominante.
```

#### Ferramentas existentes: adição de `escopo_id` e `plano_id`

```python
# Antes
avancar_pipeline(project_id, skill_id?, inputs?)

# Depois
avancar_pipeline(project_id, escopo_id, plano_id, skill_id?, inputs?)
```

Ferramentas afetadas: `avancar_pipeline`, `consultar_viabilidade_prazo`, `listar_gargalos_recurso`, `simular_impacto_replan`, `iniciar_orcamento` (substituída por `iniciar_planejamento`), `aprovar_versao` (substituída por `aprovar_plano`).

#### `iniciar_orcamento` → `iniciar_planejamento`

```python
# Nova ferramenta principal de início
iniciar_planejamento(
    project_id,            # projeto pai (já existente ou criado on-the-fly)
    escopo_id,             # ID do escopo (criado se não existir)
    plano_id_ou_nome,      # ID ou nome do plano (criado se não existir)
    tipo_obra,
    data_inicio, data_termino,
    eap,
    nome_escopo?,
    hipotese_plano?,
    contexto_id?,          # sobrescreve o padrão do projeto
    dias_semana?, horas_dia?,
) -> project_id, escopo_id, plano_id, skills_executadas, proximas_pendentes
```

`iniciar_orcamento` é mantida como alias de retrocompatibilidade que cria `escopo_id="default"` e `plano_id` automático.

---

### D8 — Análise consolidada: `ResultadoConsolidadoProjeto`

Novo value object de domínio para representar a visão agregada:

```python
# src/concilium/domain/models/resultado_consolidado.py (implementado)
StatusMargem = Literal["VERDE", "AMARELO", "VERMELHO"]
# VERDE   ≥ 8 pp  |  AMARELO ≥ 4 pp  |  VERMELHO < 4 pp

class BreakdownEscopo(BaseModel):
    model_config = ConfigDict(extra="ignore")

    escopo_id: str
    nome: str
    plano_id: str
    status_plano: str                   # status do PlanoTrabalho usado
    venda_com_bdi: float
    custo_total: float
    resultado_financeiro: float
    margem_pct: float
    status_margem: StatusMargem
    peso_relativo: float = Field(ge=0, le=1)  # venda_com_bdi / venda_total_projeto

class ResultadoConsolidadoProjeto(BaseModel):
    model_config = ConfigDict(extra="ignore")

    projeto_id: str
    escopos_incluidos: list[str]        # IDs incluídos nesta consolidação
    escopos_excluidos: list[str] = Field(default_factory=list)  # sem pipeline completo
    venda_total_com_bdi: float
    custo_total: float
    resultado_financeiro: float
    margem_pct: float                   # resultado_financeiro / venda_total_com_bdi
    status_margem: StatusMargem
    breakdown: list[BreakdownEscopo] = Field(default_factory=list)
    avisos: list[str] = Field(default_factory=list)  # escopos parciais, etc.

    @classmethod
    def calcular(
        cls,
        projeto_id: str,
        breakdown: list[BreakdownEscopo],
        escopos_excluidos: list[str] | None = None,
        avisos: list[str] | None = None,
    ) -> "ResultadoConsolidadoProjeto": ...
    # Soma venda/custo, calcula margem, resolve status_margem, normaliza peso_relativo.
    # Não persiste em disco — calculado on-the-fly por resumo_projeto().
```

Este value object é produzido pela ferramenta MCP `resumo_projeto` e pelo comando CLI `concilium projeto resumo <projeto>`. Não é persistido no canônico de nenhum escopo individual — é calculado on-the-fly a partir dos canônicos aprovados.

---

### D9 — Shim de retrocompatibilidade

Projetos com estrutura `v1/canonical.json` (pré-ADR-031) continuam funcionando sem migração:

```python
# src/concilium/infrastructure/storage/project.py (implementado)
class ProjectStore:
    def _is_legacy(self) -> bool:
        """True se o projeto usa estrutura vN/ sem pasta escopos/ (pré-ADR-031)."""
        return not (self.root / "escopos").exists() and bool(self.list_versions())

    def escopo(self, escopo_id: str = "default") -> EscopoStore:
        if self._is_legacy():
            return _LegacyEscopoShim(self)    # lê v1/, v2/ como se fossem planos
        return EscopoStore(self.root / "escopos" / escopo_id)

# src/concilium/infrastructure/storage/escopo_store.py (implementado)
class _LegacyEscopoShim(EscopoStore):
    """Adapta estrutura vN/ como escopo 'default' com interface EscopoStore."""

    def list_plans(self) -> list[str]:         # → ProjectStore.list_versions()
    def plan(self, plano_id: str) -> _LegacyPlanoShim:
    def create_plan(self, nome: str, **_) -> _LegacyPlanoShim:  # cria nova versão vN
    def approved_plan(self) -> _LegacyPlanoShim | None:  # lê approved_versions
    def active_plan(self) -> _LegacyPlanoShim | None:    # lê current_version
    def approve_plan(self, plano_id: str) -> list[str]:  # delega ProjectStore.approve()

class _LegacyPlanoShim(PlanoStore):
    """Adapta versão vN/ para interface PlanoStore."""

    def load_canonical(self) -> CanonicalModel | None:   # → ProjectStore.load_canonical(vN)
    def save_canonical(self, model, **_) -> None:        # → ProjectStore.save_canonical(vN)
    def log_invocation(self, entry: dict) -> None:       # → vN/invocations.log
    def read_invocations(self) -> list[dict]:            # lê vN/invocations.log
    def approve(self) -> None:                           # → ProjectStore.approve(vN)
    def save_output_file(self, data, filename) -> Path:  # → vN/outputs/
```

Propriedades do shim:
- Mapeia `list_plans()` → `list_versions()` (retorna `["v1", "v2", ...]`)
- Mapeia `approved_plan()` → lê `approved_versions` de meta.json
- Mapeia `plan(plano_id).load_canonical()` → `ProjectStore.load_canonical(plano_id)`
- É **somente-leitura** para o novo modelo: novos escopos/planos só podem ser criados na estrutura nova

**Nenhuma migração automática** de dados ocorre: o shim abstrai a estrutura antiga sem mover arquivos.

---

## Alternativas Rejeitadas

| ID | Alternativa | Motivo da rejeição |
|---|---|---|
| X1 | Tags em versões (`v1#agressivo`, `v2#conservador`) para paralelo | Viola o modelo de cópia sequencial; `current_version` é ponteiro único; não expressa semântica de "candidato" |
| X2 | Lista de sub-EAPs dentro de um único `CanonicalModel` | O canônico cresce proporcionalmente ao número de obras; skills precisariam de índice de escopo em cada chamada; viola isolamento de pipeline |
| X3 | Um projeto separado por obra | Perde visão consolidada do empreendimento; impossibilita análise de pool compartilhado entre lotes; duplica contexto, catálogo, perfil BDI |
| X4 | Campo `planos: list[CanonicalModel]` dentro do `ProjectStore.meta` | Canônicos podem ser grandes (JSON completo); carregar todos para listar planos é inaceitável; viola o princípio de filesystem versionado do ADR-029 |
| X5 | Migração automática da estrutura vN/ para escopos/ | Risco de perda de dados; desnecessário dado que o shim D9 abstrai sem mover arquivos |

---

## Consequências

### Positivas

| ID | Consequência |
|---|---|
| C1 | Licitações multi-lote podem ser orçadas em um único projeto com resultado consolidado (D8) |
| C2 | O engenheiro compara alternativas de planejamento em paralelo sem perder o estado de nenhuma |
| C3 | `aprovar_plano` arquiva automaticamente os demais — rastreabilidade completa de decisões |
| C4 | A CLI e o MCP ganham granularidade sem quebrar workflows existentes (D6, D7, D9) |
| C5 | Pool de recursos compartilhado entre escopos fica endereçável (escopo isolado, análise cross-escopo) |
| C6 | `ResultadoConsolidadoProjeto` viabiliza relatório executivo único para o cliente |

### Negativas / Riscos

| ID | Risco | Mitigação |
|---|---|---|
| R1 | Comandos CLI ficam mais verbosos (`--escopo`, `--plano`) | Default-inference (D6): inferência automática quando único; erro amigável quando ambíguo |
| R2 | Ferramentas MCP ganham parâmetros novos obrigatórios | Adição incremental; `iniciar_orcamento` mantida como alias; `escopo_id="default"` como fallback |
| R3 | `ProjectStore` cresce em complexidade (EscopoStore + PlanoStore) | Encapsulamento estrito; shim isola legacy; testes independentes por camada |
| R4 | `ResultadoConsolidadoProjeto` pode misturar escopos em estados inconsistentes (um aprovado, outro rascunho) | `resumo_projeto` documenta claramente quais escopos foram incluídos e com qual status |

---

## Plano de Implementação

| Fase | Entregas | Pré-requisito |
|---|---|---|
| **F1 — Domínio** | `Escopo`, `PlanoTrabalho`, `ResultadoConsolidadoProjeto` em `domain/models/`; shim `_LegacyEscopoShim` em infrastructure | — |
| **F2 — Storage** | `EscopoStore`, `PlanoStore`, refactor de `ProjectStore.new_version` → `create_plan`; testes unitários de store | F1 |
| **F3 — CLI** | Grupos `escopo` e `plano`; parâmetros `--escopo`/`--plano` com inference em comandos existentes | F2 |
| **F4 — MCP** | Novas ferramentas D7; parâmetros `escopo_id`/`plano_id` em ferramentas existentes; `iniciar_planejamento` | F2 |
| **F5 — Análise** | `resumo_projeto`, `comparar_planos`, `comparar_escopos` | F4 |
| **F6 — Testes** | Testes de integração multi-escopo; teste de shim legado; teste de aprovação com arquivamento | F3, F4 |

---

## Referências

- ADR-013: MCP Server como fachada de operações de negócio
- ADR-018: Sistema de artefatos tipados (snapshot de versão)
- ADR-022: Wave execution e gate propagation (bloqueio de pipeline)
- ADR-029: Reorganização DDD — `ProjectStore` em `infrastructure/storage/project.py`
- ADR-030: Composição tipada de equipes (per-escopo, hereditária)
