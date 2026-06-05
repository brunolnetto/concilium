# NEP-034 — Convenção de prefixo `_xx_` em funções helper de nível de módulo

**Status**: Proposto  
**Autores**: Equipe de Engenharia  
**Data**: 2025-07  
**ADR relacionado**: —

---

## Contexto

Durante refatorações incrementais do codebase, um padrão emergiu organicamente: funções
auxiliares que assistem uma classe específica foram definidas no escopo de módulo (module-level)
em vez de dentro da própria classe. Para sinalizá-las como "privadas ao contexto X", receberam
um prefixo de duas letras seguido de underscore — `_xx_` — onde `xx` é uma sigla do contexto
de origem (e.g., `_rp_` para "run pipeline", `_lm_` para "live model", `_xl_` para "excel
adapter").

Esse padrão introduz vários problemas:

1. **Acoplamento implícito**: A função usa parâmetros que mimetizam `self`, tornando sua
   relação com a classe opaca para o leitor e para ferramentas de análise.
2. **Namespace poluído**: Funções com nomes como `_rp_execute_node` ficam visíveis no escopo
   do módulo, aumentando a superfície de possíveis importações acidentais.
3. **Circular imports latentes**: `_rp_execute_node` em `executor.py` continha
   `from concilium.application.skills.executor import ExecutionRecord` — um auto-import
   circular eliminado apenas ao mover a função para dentro da classe.
4. **Prefixos duplicados entre módulos**: `_rp_` foi usado tanto em `executor.py` (run
   pipeline) quanto em `insumo.py` (resolve price), gerando ambiguidade semântica.
5. **Impossibilidade de herança/override**: Funções module-level não participam da MRO e
   não podem ser sobrescritas em subclasses.

---

## Inventário de ocorrências (estado em 2025-07)

| Arquivo | Prefixo | Quantidade | Classe-alvo | Observação |
|---|---|---|---|---|
| `application/skills/executor.py` | `_rp_` | 3 | `SkillExecutor` | **Resolvido em NEP-034** (migrado p/ instância) |
| `infrastructure/repositories/insumo.py` | `_rp_` | 3 | `RepositorioInsumo` | Conflito de sigla com executor; pendente |
| `application/runtime/deliverables/reports/excel/excel_live_model.py` | `_lm_` | ~20 | `ExcelLiveModel` (inferido) | Pendente |
| `application/runtime/deliverables/reports/excel/excel_adapter.py` | `_xl_`, `_rg_` | ~30 | `ExcelAdapter` / funções de relatório | Pendente |
| `domain/builders/memorial_bdi_builder.py` | `_ba_`, `_mb_` | 5 | `MemorialBdiBuilder` | Pendente |
| `presentation/cli/_commands_manage_helpers_a.py` | `_cq_` | 2 | helpers CLI | Pendente |
| `presentation/cli/_commands_manage_helpers_b.py` | `_cs_`, `_cp_` | 5 | helpers CLI | Pendente |

---

## Decisão

### Regra geral

Funções auxiliares privadas que operam sobre o estado de uma classe **devem ser métodos da
própria classe**:

- Se precisam de `self`: método de instância normal.
- Se não precisam de `self` mas pertencem semanticamente à classe: `@staticmethod`.
- Se são utilitários genéricos sem vínculo de estado: permanecem module-level mas **sem o
  prefixo `_xx_`** — usam um nome descritivo simples (e.g., `_clean_series_label`).

### Migração incremental (não big-bang)

Cada migração é feita junto à tarefa que já toca o arquivo em questão. Não é necessário
criar uma PR exclusiva de limpeza se o esforço não for justificável.

Ordem de prioridade sugerida:

1. `executor.py` — **Concluído** (esta NEP motivou a refatoração).
2. `insumo.py` — Alta prioridade (prefixo `_rp_` conflita com executor; 3 funções curtas).
3. `excel_live_model.py` / `excel_adapter.py` — Média prioridade; alto volume, refatorar
   quando o módulo precisar de outra modificação.
4. `memorial_bdi_builder.py` — Baixa prioridade; 5 funções simples.
5. CLI helpers — Baixa prioridade; já estão em arquivos `_helpers_*` separados.

### Convenção de nomenclatura pós-migração

Após mover para a classe, o prefixo `_xx_` é **removido** — o `_` simples é suficiente para
indicar privacidade e a classe fornece o namespace:

```python
# Antes (module-level, padrão _xx_)
def _rp_build_topology(meta: dict) -> object: ...

# Depois (método de instância)
class SkillExecutor:
    def _build_topology(self) -> object: ...
```

---

## Consequências

### Positivas

- Elimina auto-imports circulares.
- Funções participam da MRO e podem ser sobrescritas em testes/subclasses.
- IDEs/type checkers resolvem corretamente o contexto de `self`.
- Namespace de módulo fica limpo.

### Negativas / Riscos

- Migração incremental cria uma janela onde o padrão coexiste com o novo estilo.
- Módulos com muitas funções `_lm_`/`_xl_` precisarão de revisão cuidadosa para garantir
  que o `ExcelLiveModel`/`ExcelAdapter` seja a classe-alvo correta.

---

## Alternativas consideradas

**Manter o padrão `_xx_` documentado como "convention"**: Rejeitado. Não resolve os
problemas de circular import e acoplamento opaco, e introduz convenção não-padrão Python.

**Refatorar tudo de uma vez (big-bang)**: Rejeitado. Alto risco de regressão em módulos
complexos como `excel_adapter.py`; migração incremental é mais segura.
