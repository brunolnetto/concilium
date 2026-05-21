# ADR-035 — Lifecycle & Data Governance Orchestrator

**Status:** Implementado  
**Data:** 2026-05-07  
**Contexto:** MendesLobo Construtora — Concilium

---

## Contexto

### Problema

O Concilium havia evoluído para uma separação clara entre **Gestão** (Catálogos, BDI, Escopos) e **Operação** (Pipeline de Skills). No entanto, a execução do pipeline permanecia "crua":

- **P1 — Sem Quality Gate:** Era possível acionar `concilium run skill-03` com um catálogo degradado (CPUs com insumos inexistentes, coeficientes negativos, etc.), gerando planilhas de orçamento numericamente incoerentes sem qualquer aviso.
- **P2 — Sem controle de estado de lifecycle:** Um projeto `APROVADO` podia ser re-executado retroativamente sem revisão, corrompendo versões congeladas. Não havia transições formais de estado (`RASCUNHO → EM_VALIDACAO → APROVADO`).
- **P3 — Governança dispersa:** Cada comando CLI (`run`, `approve`) implementava verificações ad hoc e redundantes. Com o crescimento de skills (00-07), a lógica de pré-condição se duplicou em pelo menos 4 pontos.
- **P4 — Sem auditabilidade:** Não havia registro de qual estado do catálogo foi usado para gerar qual versão do plano — impossível rastrear retroativamente "este orçamento foi gerado com o catálogo de Janeiro ou Fevereiro?".

---

## Decisão

### D1 — `LifecycleCoordinator` na Camada de Aplicação

Criação do `LifecycleCoordinator` em `concilium.application.orchestrators.lifecycle_coordinator`. Ele é o único ponto de entrada para execução de skills, substituindo chamadas diretas ao `Runtime`:

```python
# src/concilium/application/orchestrators/lifecycle_coordinator.py

class LifecycleCoordinator:
    """Orquestrador de Lifecycle e Governança de Dados (ADR-035).
    
    'Abraça' a execução do runtime, garantindo que o avanço do planejamento
    respeite os Quality Gates de dados e as regras de transição de estado.
    """
    def __init__(self, runtime: Runtime):
        self.runtime = runtime
```

### D2 — Fluxo de Avanço em 4 Fases

Para cada acionamento de skill, o coordenador executa sequencialmente:

```
1. DATA GATE → Valida integridade do catálogo (ValidadorCPUInsumo)
2. PRE-FLIGHT → Verifica coerência dos inputs com o estado do projeto
3. EXECUTE → Chama o Runtime
4. CHECK-OUT → Avalia transição de estado do projeto
```

### D3 — Quality Gate com `ValidadorCPUInsumo`

O Data Gate executa as regras `VAL-CPU-INS-01` a `07` (ADR-032) sobre todas as CPUs do catálogo vinculado ao escopo. CPUs com status `ERRO` bloqueiam o avanço:

```python
def _perform_catalog_audit(self, catalogo_id: str, catalogo: dict):
    validador = ValidadorCPUInsumo(RepositorioInsumo(catalogo))
    erros_fatais = []
    for cpu in catalogo.get("cpus", []):
        for res in validador.validar_cpu_completa(cpu):
            if res.status == "ERRO":
                erros_fatais.append(f"CPU {cpu.get('codigo')}: {res.mensagem}")
    if erros_fatais:
        raise RuntimeDomainError(
            f"Bloqueio de Governança: catálogo '{catalogo_id}' possui erros críticos. "
            f"Primeiros: {erros_fatais[:3]}"
        )
```

### D4 — `force_data_gate=False` para Testes e Overrides Explícitos

Para testes de integração que não precisam de um catálogo completo, o flag `force_data_gate=False` desativa a auditoria sem alterar o fluxo de execução:

```python
result = coordinator.avancar_plano(
    "skill-03", project, plano_store,
    force_data_gate=False  # Apenas em testes
)
```

### D5 — CLI `run` Refatorado para Usar o Coordenador

O comando `concilium run <skill_id>` instancia o `LifecycleCoordinator` e delega, eliminando a lógica de validação inline que existia no handler CLI anterior.

---

## Alternativas Rejeitadas

| ID | Alternativa | Motivo da Rejeição |
|---|---|---|
| X1 | Validação diretamente no `Runtime` | O `Runtime` é uma camada de infraestrutura de execução; injetar governança de negócio nele violaria a separação de camadas (ADR-029 DDD). |
| X2 | Decorators de validação em cada skill | Acoplamento frágil; as skills não devem conhecer as políticas de governança da empresa; difícil de testar em isolamento. |
| X3 | Microsserviço de governança separado | Prematuridade arquitetural; o overhead de rede e a complexidade operacional não se justificam para o porte atual do Concilium. |

---

## Consequências

### Positivas

| ID | Consequência |
|---|---|
| C1 | Centralização da lógica de governança: CLI e MCP passam a chamar apenas o Coordenador. |
| C2 | Orçamentos com catálogos degradados são bloqueados na origem, antes de qualquer cálculo. |
| C3 | Simplificação da CLI — o comando `run` é reduzido a instanciar o Coordenador e exibir resultados. |
| C4 | Base para auditabilidade: o Coordenador pode injetar metadados de snapshot de catálogo nos artefatos de saída. |

### Negativas / Riscos

| ID | Risco | Mitigação |
|---|---|---|
| R1 | Latência adicional: a auditoria de catálogo percorre todas as CPUs a cada execução. | Para catálogos grandes (>500 CPUs), implementar cache de resultado de auditoria com TTL por sessão. |
| R2 | `force_data_gate=False` pode ser usado em produção por engano. | Emitir `UserWarning` quando o flag for desativado fora de contexto de teste. |

---

## Plano de Implementação

| Fase | Entregas | Status |
|---|---|---|
| **F1 — Core** | `LifecycleCoordinator` com `avancar_plano()` e `avancar_projeto()` | ✅ Implementado |
| **F2 — Quality Gate** | `_perform_catalog_audit()` integrando `ValidadorCPUInsumo` | ✅ Implementado |
| **F3 — CLI** | Refatoração do comando `run` em `commands_run.py` | ✅ Implementado |
| **F4 — Testes** | Testes de integração: bloqueio em catálogo degradado + bypass com flag | ✅ Implementado |

---

## Definition of Done

### Fase 1 — Core
- [x] `LifecycleCoordinator` criado em `application/orchestrators/lifecycle_coordinator.py`.
- [x] Métodos `avancar_plano()` e `avancar_projeto()` (suporte legado) implementados.
- [x] Fluxo de 4 fases (Data Gate → Pre-Flight → Execute → Check-Out) estruturado.

### Fase 2 — Quality Gate
- [x] `_perform_catalog_audit()` invoca `ValidadorCPUInsumo` com todas as regras `VAL-CPU-INS`.
- [x] `RuntimeDomainError` lançada com mensagem descritiva ao detectar erros fatais no catálogo.
- [x] `force_data_gate` flag implementado para contextos de teste.

### Fase 3 — CLI e MCP
- [x] Comando `run` da CLI refatorado para utilizar o Coordenador.
- [x] Ferramenta `avancar_pipeline` do MCP (ADR-037) delegando ao Coordenador.

### Fase 4 — Testes
- [x] Teste: skill bloqueada com catálogo contendo CPU com insumo inexistente.
- [x] Teste: skill avança normalmente com catálogo válido.
- [x] Teste: `force_data_gate=False` ignora erros e executa skill.
