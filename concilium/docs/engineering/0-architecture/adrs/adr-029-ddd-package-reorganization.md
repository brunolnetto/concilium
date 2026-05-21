# ADR-029 — Reorganização de Pacotes em Camadas DDD

**Status:** Implementado
**Data:** 2026-05-05  
**Contexto:** MendesLobo Construtora — Concilium

---

## Contexto

### Problema

O pacote `src/concilium/` cresceu organicamente durante as fases de prototipagem. A estrutura atual agrupa módulos por *tipo técnico* (models, repositories, clients, adapters, storage) em vez de por *responsabilidade de domínio*. Isso produz dependências cruzadas silenciosas — por exemplo, `skills/` importa diretamente de `storage/`, `clients/` é referenciado em skill 03 para o preço do diesel, e `mcp_server/tools/` chama `repositories/` sem passar por nenhuma camada de aplicação.

Consequências observadas:
| ID | Sintoma |
|----|---------|
| P1 | Skill 03 importa `FuelPriceClient` diretamente (infraestrutura → domínio) |
| P2 | `mcp_server/tools/catalogo.py` lê arquivos JSON diretamente (presentation → infrastructure) |
| P3 | `models/` não distingue value objects de domain services |
| P4 | Testes unitários precisam mockar storage e clients mesmo para lógica pura |
| P5 | Impossível substituir o backend de storage (filesystem → banco) sem alterar código de domínio |

### Estrutura atual vs DDD

```
src/concilium/          Camada DDD atual
─────────────────────────────────────────────────────────────────
adapters/               Infrastructure  (renderizadores Excel, templates)
catalog/                Infrastructure  (loader, updater, completeness)
cli/                    Presentation    (Typer commands)
clients/                Infrastructure  (OpenMeteo, FuelPriceClient)
config.py               Infrastructure  (leitura de YAML)
main.py                 Presentation    (entrypoint CLI)
mcp_server/             Presentation    (MCP tools / server FastMCP)
models/                 Domain          (entities, value objects, models BDI/canonical)
optimizer/              Application     (replanning loop)
progress/               Application     (tracker de progresso)
replanning/             Application     (generator de replanning)
repositories/           Domain (port) + Infrastructure (impl)  ← mixed
resolution/             Domain          (matching semântico)
runtime.py              Presentation    (entrypoint MCP)
scenarios/              Application     (runner de cenários)
scheduling/             Domain          (algoritmos de schedule)
semantic/               Domain          (layer semântica)
skills/                 Application     (pipeline de skills)
storage/                Infrastructure  (filesystem, copy-on-write)
validations/            Domain          (validadores)
```

---

## Decisão

Adotar a estrutura de quatro camadas DDD fisicamente no sistema de arquivos, com módulos-shim de retrocompatibilidade para permitir migração incremental sem quebrar testes existentes.

### D1 — Estrutura alvo

```
src/concilium/
├── domain/
│   ├── models/           ← atual models/
│   ├── validations/      ← atual validations/
│   ├── repositories/     ← ports (ABCs): RepositorioInsumoPort, ArtifactStorePort
│   ├── resolution/       ← atual resolution/
│   ├── scheduling/       ← atual scheduling/
│   └── semantic/         ← atual semantic/
│
├── application/
│   ├── skills/           ← atual skills/
│   ├── scenarios/        ← atual scenarios/
│   ├── replanning/       ← atual replanning/
│   ├── optimizer/        ← atual optimizer/
│   └── progress/         ← atual progress/
│
├── infrastructure/
│   ├── storage/          ← atual storage/
│   ├── clients/          ← atual clients/
│   ├── adapters/         ← atual adapters/
│   ├── catalog/          ← atual catalog/
│   ├── repositories/     ← implementações concretas dos ports de domain/repositories/
│   └── config.py         ← atual config.py
│
└── presentation/
    ├── cli/              ← atual cli/ + main.py
    ├── mcp_server/       ← atual mcp_server/ + runtime.py
    └── __init__.py
```

### D2 — Regras de dependência (Dependency Rule)

A dependência só flui para dentro — nunca para fora:

```
Presentation  →  Application  →  Domain
     ↓                ↓
Infrastructure  (serve todos; não conhece camadas acima)
```

| Camada | Pode importar de | NÃO pode importar de |
|--------|-----------------|----------------------|
| domain | — (nenhuma dependência interna) | application, infrastructure, presentation |
| application | domain | infrastructure, presentation |
| infrastructure | domain (ports), stdlib | application, presentation |
| presentation | application, domain | infrastructure (direto) |

**Exceção controlada:** Skills dentro de `application/skills/manifests/*/skill.py` podem injetar dependências de infrastructure via parâmetros (catalog dict, inputs dict) — mantendo o padrão atual de skill como função pura de `(canonical, inputs, catalogo, perfil) → SkillResult`.

### D3 — Migração incremental em três fases

#### Fase 1 — Shim layer (não quebra nada)
Criar `domain/`, `application/`, `infrastructure/`, `presentation/` com `__init__.py` que re-exporta tudo do módulo original:

```python
# src/concilium/domain/models/__init__.py
from concilium.models import *  # re-export para retrocompatibilidade
```

Todos os imports existentes continuam funcionando. Nenhum teste quebra.

#### Fase 2 — Migração de imports (arquivo por arquivo)
Mover módulos fisicamente e atualizar imports. Prioridade:
1. `models/` → `domain/models/` (zero dependências externas)
2. `validations/` → `domain/validations/`
3. `storage/` + `clients/` + `adapters/` → `infrastructure/`
4. `skills/` → `application/skills/`
5. `cli/` + `mcp_server/` → `presentation/`

Usar `git mv` para preservar histórico. Manter shim `__init__.py` por **1 sprint** após mover.

#### Fase 3 — Remover shims e enforce linting
Adicionar regra `import-linter` (ou `pylint` plugin) que recusa imports que violam a Dependency Rule:

```toml
# pyproject.toml
[tool.importlinter]
root_packages = ["concilium"]
[[tool.importlinter.contracts]]
name = "Domain must not import from Application or Infrastructure"
type = "forbidden"
source_modules = ["concilium.domain"]
forbidden_modules = ["concilium.application", "concilium.infrastructure", "concilium.presentation"]
```

### D4 — Onde cada módulo atual fica

| Módulo atual | Novo caminho |
|---|---|
| `models/` | `domain/models/` |
| `validations/` | `domain/validations/` |
| `repositories/insumo.py`, `repositories/producao.py` | `infrastructure/repositories/` (implementações) |
| `resolution/` | `domain/resolution/` |
| `scheduling/` | `domain/scheduling/` |
| `semantic/` | `domain/semantic/` |
| `skills/` | `application/skills/` |
| `scenarios/` | `application/scenarios/` |
| `replanning/` | `application/replanning/` |
| `optimizer/` | `application/optimizer/` |
| `progress/` | `application/progress/` |
| `storage/` | `infrastructure/storage/` |
| `clients/` | `infrastructure/clients/` |
| `adapters/` | `infrastructure/adapters/` |
| `catalog/` | `infrastructure/catalog/` |
| `config.py` | `infrastructure/config.py` |
| `cli/` | `presentation/cli/` |
| `main.py` | `presentation/main.py` |
| `mcp_server/` | `presentation/mcp_server/` |
| `runtime.py` | `presentation/runtime.py` |

### D5 — Port interfaces a criar em `domain/repositories/`

```python
# domain/repositories/insumo_port.py
from abc import ABC, abstractmethod
from concilium.domain.models.catalogo import Insumo

class RepositorioInsumoPort(ABC):
    @abstractmethod
    def buscar(self, codigo: str) -> Insumo | None: ...
    @abstractmethod
    def listar(self, tipo: str | None = None) -> list[Insumo]: ...

# domain/repositories/artifact_port.py
from abc import ABC, abstractmethod
from concilium.domain.models.artifact import ArtifactRecord

class ArtifactStorePort(ABC):
    @abstractmethod
    def save(self, record: ArtifactRecord) -> None: ...
    @abstractmethod
    def load(self, artifact_id: str) -> ArtifactRecord: ...
```

As implementações concretas (`RepositorioInsumo`, `ArtifactStore`) ficam em `infrastructure/repositories/`.

---

## Consequências

### Positivas
- Testabilidade: domínio pode ser testado sem filesystem, sem HTTP
- Substituibilidade: trocar storage/filesystem por banco de dados requer apenas nova implementação de port
- Onboarding: estrutura autodocumenta responsabilidades
- Enforce via linter previne regressão de dependências

### Negativas / Riscos
- Migração é grande (800+ arquivos de importação a atualizar) — deve ser faseada
- Fase 2 exige atenção especial em skills que injetam `FuelPriceClient` e `storage/` diretamente
- `main.py` e `runtime.py` têm imports espalhados que devem ser concentrados em `presentation/`

---

## ADRs Relacionados

- ADR-013, ADR-014: MCP facade — reclassificado em `presentation/`
- ADR-007, ADR-012: Catalog lifecycle — `infrastructure/catalog/`
- ADR-018: Typed artifact system — `domain/models/artifact.py` → `domain/models/`

---

## Definition of Done

- [x] `domain/`, `application/`, `infrastructure/`, `presentation/` criados com `__init__.py` (Fase 1)
- [x] Port interfaces `RepositorioInsumoPort` e `ArtifactStorePort` definidos em `domain/repositories/`
- [x] Dependency Rule documentada em `pyproject.toml` (`import-linter` contract)
- [x] Nenhum import de `domain/` aponta para `application/` ou `infrastructure/` (CI gate — ativo após Fase 3)
- [x] Fase 2: `domain/models/` e `domain/validations/` migrados com shims em `models/` e `validations/`
- [x] Fase 3: todos os consumidores migrados para `concilium.domain.models.*`; shims `models/` e `validations/` removidos; `import-linter` 3/3 contratos KEPT; 1061 passed, 1 skipped
- [x] Fase 4: todos os módulos físicos migrados para as 4 camadas DDD; `src/concilium/` contém apenas `domain/`, `application/`, `infrastructure/`, `presentation/` mais shims de compatibilidade; circular imports corrigidos em todas as camadas; `_tools_root()` e `load_manifest()` atualizados para novos caminhos; 1061 passed, 1 skipped
