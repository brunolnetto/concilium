# ADR-036 — Reorganização da CLI: Gestão vs. Operação

**Status:** Implementado  
**Data:** 2026-05-07  
**Contexto:** MendesLobo Construtora — Concilium

---

## Contexto

### Problema

A CLI do Concilium cresceu organicamente até acumular 17 comandos de nível raiz (`concilium <comando>`), o que gerou problemas sérios de usabilidade e arquitetura:

- **P1 — Flat hierarchy saturada:** Comandos de naturezas completamente distintas — configuração de dados (`catalog`), execução de cálculos (`run`), exportação de planilhas (`excel`) — viviam todos no mesmo nível, sem agrupamento semântico.
- **P2 — Ausência de intenção arquitetural:** Não havia distinção explícita entre "operações que configuram inputs de gestão" e "operações que executam cálculos de planejamento". Qualquer novo desenvolvedor precisa ler o código para entender o propósito de cada comando.
- **P3 — `LifecycleCoordinator` sem reflexo na CLI:** O ADR-035 introduziu a separação formal entre Gestão e Operação na camada de aplicação, mas a CLI continuou com estrutura plana — inconsistência arquitetural visível ao usuário.
- **P4 — Startup lento:** Todos os módulos pesados (Pydantic, openpyxl, etc.) eram importados na inicialização da CLI, causando latência perceptível mesmo em comandos simples como `concilium status`.

---

## Decisão

### D1 — Sub-Aplicações Typer por Responsabilidade

Reorganização da hierarquia de comandos usando o padrão de Sub-apps (`typer.Typer`) nomeadas:

```
concilium
├── init                 ← Inicialização de projeto
├── status               ← Diagnóstico de estado
├── run <skill_id>       ← Execução via LifecycleCoordinator (ADR-035)
├── audit                ← Análise de gargalos e viabilidade
├── approve              ← Aprovação/congelamento de versão
├── manage               ← Sub-app: Gestão de dados
│   ├── catalog          ← CRUD de CPUs e Insumos
│   ├── structure        ← Escopos e EAP
│   └── bdi              ← Parâmetros de BDI por categoria
└── export               ← Sub-app: Adaptadores de saída
    └── excel            ← Geração de planilhas
```

### D2 — Camada Raiz: Operação Pura

Os 5 comandos raiz representam o **ciclo de vida operacional** de um projeto. São os únicos que o gerente de planejamento precisa conhecer para operar o Concilium:

```python
app.command("init")(commands_basic.init)
app.command("status")(commands_basic.status)
app.command("run")(commands_run.run)
app.command("audit")(commands_basic.audit)
app.command("approve")(commands_run.approve)
```

### D3 — `manage`: Camada de Gestão de Dados

Agrupa tudo que configura os **inputs de cálculo** sem executar cálculos:

```python
manage_app = typer.Typer(name="manage", help="Gestão de dados, estrutura e BDI do projeto.")
manage_app.add_typer(commands_manage.app_catalog, name="catalog")
manage_app.add_typer(commands_manage.app_structure, name="structure")
manage_app.add_typer(commands_bdi.app, name="bdi")
app.add_typer(manage_app)
```

### D4 — `export`: Camada de Adaptadores de Saída

Isolamento dos adaptadores de formato (Excel, PDF futuro) em sub-app `export`, desacoplando a lógica de serialização da lógica de planejamento:

```python
export_app = typer.Typer(name="export", help="Adaptadores de saída.")
export_app.add_typer(commands_adapter.app, name="excel")
app.add_typer(export_app)
```

### D5 — Lazy Loading para Startup Rápido

Módulos pesados (`commands_run`, `commands_manage`, `commands_bdi`, `commands_adapter`) são importados apenas quando necessários, via `_lazy_load_heavy_commands()`. Comandos leves (`init`, `status`) respondem instantaneamente:

```python
def _lazy_load_heavy_commands() -> None:
    from concilium.presentation.cli import commands_run, commands_manage, commands_bdi, commands_adapter
    app.command("run")(commands_run.run)
    # ...
_lazy_load_heavy_commands()
```

---

## Alternativas Rejeitadas

| ID | Alternativa | Motivo da Rejeição |
|---|---|---|
| X1 | Click em vez de Typer | Typer já estava consolidado no projeto; migração traria reescrita sem ganho funcional. |
| X2 | Agrupamento por domínio (ex: `concilium cpu list`, `concilium cpu add`) | Proliferação de sub-apps de domínio atomizaria a CLI; o usuário precisaria conhecer o modelo de domínio para usar a ferramenta. |
| X3 | Prefixos por convenção (sem Sub-apps) | Sem agrupamento real do Typer, `--help` não reflete a hierarquia e `no_args_is_help` não funciona recursivamente. |

---

## Consequências

### Positivas

| ID | Consequência |
|---|---|
| C1 | CLI auto-documentada: `concilium manage --help` lista apenas comandos de gestão; `concilium --help` mostra apenas operações de ciclo de vida. |
| C2 | Startup rápido: comandos leves (status, init) iniciam sem carregar Pydantic/openpyxl. |
| C3 | Extensibilidade clara: novos adaptadores de saída entram em `export`, sem poluir a raiz. |
| C4 | Alinhamento arquitetural com ADR-035: a separação Gestão/Operação é agora visível na interface do usuário. |

### Negativas / Riscos

| ID | Risco | Mitigação |
|---|---|---|
| R1 | Breaking change: scripts de automação que chamavam `concilium catalog` precisam migrar para `concilium manage catalog`. | Documentar migração no CHANGELOG; considerar aliases de compatibilidade por 1 versão. |
| R2 | Curva de aprendizado para novos usuários descobrirem que `catalog` está sob `manage`. | `concilium --help` e `no_args_is_help=True` recursivo tornam a descoberta imediata. |

---

## Plano de Implementação

| Fase | Entregas | Status |
|---|---|---|
| **F1 — Estrutura** | `manage_app` e `export_app` criados; comandos raiz definidos; `no_args_is_help` recursivo | ✅ Implementado |
| **F2 — Migração** | Todos os comandos movidos para seus grupos; remoção de comandos raiz obsoletos | ✅ Implementado |
| **F3 — Lazy Loading** | `_lazy_load_heavy_commands()` implementado; startup < 200ms para `status` | ✅ Implementado |

---

## Definition of Done

- [x] Sub-apps `manage` e `export` criadas com `no_args_is_help=True`.
- [x] Nível raiz: apenas `init`, `status`, `run`, `audit`, `approve`.
- [x] `manage`: `catalog`, `structure`, `bdi`.
- [x] `export`: `excel`.
- [x] Lazy loading implementado para módulos com importações pesadas.
- [x] `concilium --help` reflete a nova hierarquia sem sub-comandos verbosos.
