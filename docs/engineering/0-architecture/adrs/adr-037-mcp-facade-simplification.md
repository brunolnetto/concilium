# ADR-037 — MCP Facade: De Micro-Ferramentas a Macro-Operações de Negócio

**Status:** Implementado  
**Data:** 2026-05-07  
**Contexto:** MendesLobo Construtora — Concilium  
**Supersede:** ADR-037-mcp-business-tools (conceito inicial, absorvido por esta decisão)

---

## Contexto

### Problema

O servidor MCP anterior expunha uma superfície de ferramentas muito granular — mais de 25 ferramentas cobrindo micro-operações como `ler_json_catalogo`, `atualizar_campo_cpu`, `listar_arquivos_projeto`:

- **P1 — Confusão de seleção para o modelo de IA:** Com >25 ferramentas de escopo similar, o modelo gasta tokens excessivos na fase de seleção da ferramenta certa, aumentando latência e custo de inferência.
- **P2 — Lógica de negócio no modelo:** Ferramentas de baixo nível forçavam o Claude a tomar decisões de implementação (ex: "devo chamar `validar_cpu` antes ou depois de `salvar_cpu`?"). A responsabilidade de sequenciamento pertence ao servidor, não ao modelo.
- **P3 — Governança inaplicável:** Com acesso direto a JSON cru, o modelo podia contornar as validações do `ValidadorCPUInsumo` e do `LifecycleCoordinator` (ADR-032, ADR-035), corrompendo o catálogo silenciosamente.
- **P4 — Manutenção: 25 funções, 25 pontos de falha:** Cada nova regra de negócio precisava ser replicada em múltiplas ferramentas, criando drift entre elas.

---

## Decisão

### D1 — Consolidação em ~9 Macro-Ferramentas por Concern

Redução de >25 micro-ferramentas para ~9 macro-ferramentas agrupadas por módulo de domínio:

| Módulo | Ferramentas | Intenção |
|---|---|---|
| `tools/projeto.py` | `listar_projetos`, `iniciar_orcamento`, `consultar_status`, `aprovar_versao` | Ciclo de vida do projeto |
| `tools/pipeline.py` | `avancar_pipeline` | Execução via `LifecycleCoordinator` |
| `tools/catalogo.py` | `pesquisar_catalogo`, `consultar_saude_catalogo` | Busca e governança do catálogo |
| `tools/escopo.py` | `consultar_estrutura_projeto`, `gerenciar_plano` | Escopos e Planos (ADR-031) |
| `tools/analise.py` | `auditar_plano`, `consultar_viabilidade_prazo`, `identificar_gargalos` | Análise de engenharia |
| `tools/replan.py` | `simular_cenario_replan`, `aplicar_sugestao_replan` | Simulação e bifurcação de versão |

### D2 — Registro Modular via `register(server)`

Cada módulo de tools exporta uma função `register(server: FastMCP)` que encapsula o bind das ferramentas. O `server.py` apenas os agrega:

```python
# src/concilium/presentation/mcp_server/server.py

def build_server() -> FastMCP:
    server = FastMCP("concilium")
    catalogo.register(server)
    projeto.register(server)
    pipeline.register(server)
    analise.register(server)
    replan.register(server)
    escopo.register(server)
    return server
```

### D3 — `avancar_pipeline` Delega ao `LifecycleCoordinator`

A ferramenta mais crítica do MCP não acessa o `Runtime` diretamente — ela delega ao `LifecycleCoordinator`, garantindo que o Data Gate (ADR-035) seja sempre executado:

```python
# tools/pipeline.py
@server.tool()
def avancar_pipeline(skill_id: str, projeto_id: str, ...) -> dict:
    """Avança o pipeline de planejamento com auditoria de governança automática."""
    coordinator = LifecycleCoordinator(runtime)
    result = coordinator.avancar_plano(skill_id, project, plano_store)
    return result.model_dump()
```

### D4 — Operações Irreversíveis Requerem Confirmação Explícita

Ferramentas como `aprovar_versao` são documentadas com a diretriz de que o modelo **deve apresentar um resumo ao usuário e aguardar confirmação** antes de invocar:

```python
@server.tool()
def aprovar_versao(projeto_id: str, versao: str) -> dict:
    """IRREVERSÍVEL: Congela a versão do orçamento.
    IMPORTANTE: O Claude deve confirmar com o usuário antes de invocar esta ferramenta.
    """
```

### D5 — Ferramentas Orientadas a Negócio, não a Implementação

O contrato das ferramentas usa linguagem de domínio da engenharia civil, não de programação:

```python
# ❌ Antes (micro-tool):
def atualizar_campo_insumo(codigo: str, campo: str, valor: Any) -> dict: ...

# ✅ Depois (macro-tool):
def pesquisar_catalogo(
    contexto_id: str,
    query: str,              # "escavação hidráulica 1m3"
    tipo: str | None = None  # "CPU" | "INSUMO"
) -> dict: ...
```

---

## Alternativas Rejeitadas

| ID | Alternativa | Motivo da Rejeição |
|---|---|---|
| X1 | Manter 25 micro-ferramentas com documentação melhorada | Não resolve P1 (seleção) nem P3 (governança bypassável); documentação extensa não reduz ambiguidade suficientemente. |
| X2 | Uma única ferramenta `executar_comando(payload: dict)` | Cria uma API RPC genérica ilegível; perde os benefícios de tipagem forte e auto-documentação via docstrings. |
| X3 | GraphQL sobre o domínio (em vez de MCP) | Overkill para o ciclo de uso atual; incompatível com o protocolo MCP nativo do Claude Desktop. |

---

## Consequências

### Positivas

| ID | Consequência |
|---|---|
| C1 | Redução de >25 para ~9 ferramentas: menor ruído de seleção para o modelo, menor consumo de tokens no contexto de tools. |
| C2 | Governança garantida: `avancar_pipeline` sempre passa pelo `LifecycleCoordinator` — impossível bypassar o Data Gate via MCP. |
| C3 | Manutenção centralizada: mudanças de regra de negócio impactam um módulo, não 5-10 micro-ferramentas. |
| C4 | Onboarding de novos modelos: um novo agente consegue operar o Concilium com leitura apenas das 9 docstrings. |

### Negativas / Riscos

| ID | Risco | Mitigação |
|---|---|---|
| R1 | Macro-ferramentas ocultam granularidade — o modelo pode não conseguir fazer ajustes cirúrgicos (ex: alterar apenas o BDI de um insumo específico). | Manter ferramentas de inspeção granular (ex: `consultar_saude_catalogo`) para diagnóstico; operações de escrita sempre macro. |
| R2 | Quebra de compatibilidade com prompts/agentes existentes que referenciavam micro-ferramentas pelo nome. | Re-indexar o sistema de memória do agente com os novos nomes após o deploy. |

---

## Plano de Implementação

| Fase | Entregas | Status |
|---|---|---|
| **F1 — Estrutura Modular** | `tools/` com módulos por concern; `register(server)` pattern; `build_server()` | ✅ Implementado |
| **F2 — Macro-Ferramentas Core** | `listar_projetos`, `iniciar_orcamento`, `consultar_status`, `avancar_pipeline`, `aprovar_versao` | ✅ Implementado |
| **F3 — Catálogo e Análise** | `pesquisar_catalogo`, `consultar_saude_catalogo`, `auditar_plano`, `simular_cenario_replan` | ✅ Implementado |
| **F4 — Escopos** | `consultar_estrutura_projeto`, `gerenciar_plano` (ADR-031) | ✅ Implementado |

---

## Definition of Done

- [x] Servidor MCP consolidado em `presentation/mcp_server/` com estrutura modular `tools/`.
- [x] `build_server()` agrega módulos via `register(server: FastMCP)`.
- [x] `avancar_pipeline` delega ao `LifecycleCoordinator` com Data Gate obrigatório.
- [x] `aprovar_versao` documentada como operação irreversível exigindo confirmação humana.
- [x] Ferramentas antigas (>25 micro-tools) depreciadas e removidas.
- [x] Teste de ponta a ponta com o agente utilizando a nova fachada de 9 ferramentas.
