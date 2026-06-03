# ADR-040 — Hierarquia de Camadas de Catálogo: Master vs. Project Layer

**Status:** Implementado  
**Data:** 2026-05-08  
**Atualizado:** 2026-05-15  
**Contexto:** MendesLobo Construtora — Concilium

---

## Estado de Implementação (2026-05-15)

| Fase | Item | Status |
|---|---|---|
| F1 — Estrutura | `projetos/{id}/overrides/` criado automaticamente | ✅ |
| F1 | Schemas Pydantic: `InsumoOverride`, `CPUOverride`, `BDIOverride`, `ProjectOverrides` | ✅ `domain/models/overrides.py` |
| F2 — Resolução | `resolver_preco()` cascata 4 camadas: PROJECT_OVERRIDE → SICRO_REGIONAL → HISTORICO_SCD2 → MASTER_BASE | ✅ `infrastructure/repositories/insumo.py` |
| F2 | Retorno com `FontePreco` literal para rastreabilidade | ✅ |
| F2 | Compatibilidade `regionalizacao` list + dict | ✅ (atualizado 2026-05-15 — AC8 ADR-045) |
| F3 — Survey | Comando `catalog survey --target project\|master` | ✅ `commands_manage.py` |
| F4 — Promote | Comando `catalog promote --force` com registro SCD-2 | ✅ `commands_manage.py` |
| F4 | **Bloqueio de aprovação com overrides pendentes** (`--allow-pending-overrides`) | ✅ `commands_run.py approve` |

### Itens resolvidos na auditoria 2026-05-15

- **`approve` com override listing**: O comando `project approve` já bloqueia a aprovação quando existem overrides não promovidos, listando os IDs afetados. Flag `--allow-pending-overrides` para bypass explícito.
- **Cascata completa**: `PROJECT_OVERRIDE > SICRO_REGIONAL > HISTORICO_SCD2 > MASTER_BASE` implementada com suporte a ambos os formatos de `regionalizacao` (list legado e dict novo).

### Limitação documentada

As Skills 01–07 usam `resolver_preco()` via `RepositorioInsumo` carregado pelo `LifecycleCoordinator`. A auditoria de cada skill individualmente foi mapeada — o padrão é consistente mas não há teste automatizado cobrindo todos os pontos de entrada.

---

## Contexto

### Problema

O catálogo Master da MendesLobo (`config/catalogos/`) concentra os benchmarks corporativos de CPUs, insumos e produtividades — referência histórica que deve ser estável e auditável. No entanto, a prática de orçamentação revelou uma tensão crônica:

- **P1 — Calibrações oportunísticas contaminam benchmarks:** Um engenheiro que recebe um desconto agressivo de fornecedor (ex: cimento 20% abaixo do mercado para fechar volume) ou registra produtividade excepcionalmente alta num trecho favorável não deveria inserir esses valores diretamente no Master. Fazê-lo distorce os benchmarks para todos os projetos futuros.
- **P2 — Sem isolamento entre projetos concurrent:** Um orçamento em andamento para a Obra A pode ter sua base de custos alterada por uma edição no Master feita para a Obra B, gerando inconsistências retroativas silenciosas.
- **P3 — Ausência de pipeline de curadoria:** Dados de campo valiosos (produtividades reais medidas, preços negociados que se tornam mercado) nunca chegam ao Master sistematicamente porque não há um workflow de promoção seguro.
- **P4 — `survey` sobrescreve o Master diretamente:** O comando `concilium manage catalog survey` atualiza preços do catálogo sem distinção de camada, tornando impossível desfazer uma calibração de projeto específico que "escapou" para o Master.

---

## Decisão

### D1 — Hierarquia de Duas Camadas

O sistema adota uma separação explícita de camadas de dados:

```
Camada Master  →  config/catalogos/             ← Benchmark corporativo estável
Camada Project →  projetos/{id}/overrides/      ← Calibrações específicas do projeto
```

A camada Project sempre sobrepõe a Master para o projeto em questão, sem alterar o Master.

### D2 — Estrutura de Override por Projeto

O diretório `projetos/{id}/overrides/` contém arquivos JSON espelho da estrutura do catálogo, com apenas os itens que foram calibrados:

```
projetos/{id}/overrides/
  insumos_override.json      ← Preços calibrados de insumos
  cpus_override.json         ← CPUs com produtividades ou composições ajustadas
  bdi_override.json          ← Parâmetros BDI específicos do contrato
```

Exemplo de override de insumo:

```json
{
  "M0089": {
    "preco_calibrado": 4.20,
    "motivo": "Acordo de fornecimento volume 500t com Votorantim",
    "data_calibracao": "2026-03-15",
    "calibrado_por": "Bruno Lobo",
    "vigencia_ate": "2026-12-31"
  }
}
```

### D3 — Resolução em Cascata no `RepositorioInsumo`

A resolução de preço segue prioridade decrescente: Override de Projeto → Regionalização SICRO → Master Base:

```python
def resolver_preco(
    self,
    codigo: str,
    jurisdicao_id: str | None = None,
    overrides: dict | None = None
) -> tuple[float, str]:
    """Retorna (preço, fonte) com trilha de qual camada resolveu."""
    # 1. Project Override Layer
    if overrides and codigo in overrides:
        return overrides[codigo]["preco_calibrado"], "PROJECT_OVERRIDE"
    
    # 2. Regional Layer (SICRO)
    insumo = self._insumos[codigo]
    if jurisdicao_id and jurisdicao_id in insumo.get("regionalizacao", {}):
        return insumo["regionalizacao"][jurisdicao_id]["preco"], f"SICRO/{jurisdicao_id}"
    
    # 3. Master Base
    return insumo["preco_base"], "MASTER_BASE"
```

### D4 — Promotion Workflow

Um workflow de promoção manual ou assistido por IA avalia overrides ao final de uma obra e decide se devem atualizar o Master:

```
1. ANÁLISE: Comparar override vs. Master atual (delta %)
2. CONTEXTO: Verificar se é preço oportunístico ou novo preço de mercado
3. DECISÃO: Promover (atualiza Master com SCD Type 2 — ADR-041) ou Arquivar
4. REGISTRO: Override arquivado em `overrides/historico/` para auditoria futura
```

Exemplo de comando CLI:

```
concilium manage catalog promote --projeto {id} --insumo M0089 --justificativa "Preço negociado tornou-se referência de mercado"
```

### D5 — `survey` Opera Apenas na Camada Project

O comando `concilium manage catalog survey` passa a salvar cotações na camada Project por padrão. A promoção ao Master é um ato separado e explícito:

```
concilium manage catalog survey --output project   ← Default (salvo em overrides/)
concilium manage catalog survey --output master    ← Requer flag explícito + confirmação
```

---

## Alternativas Rejeitadas

| ID | Alternativa | Motivo da Rejeição |
|---|---|---|
| X1 | Versionar o Master inteiro a cada edição (commit git-like) | Overhead de storage; o ADR-041 (SCD Type 2) resolve o versionamento de forma mais granular. |
| X2 | Permissões de escrita por papel (apenas o gestor de catálogo pode editar o Master) | Mitiga P1 mas não cria o isolamento de P2; engenheiros ainda não têm onde salvar calibrações de projeto. |
| X3 | Catálogos totalmente separados por projeto (cópia completa) | Propagação de atualizações do Master exige sincronização complexa em dezenas de projetos abertos simultaneamente. |

---

## Plano de Implementação

| Fase | Entregas | Status |
|---|---|---|
| **F1 — Estrutura** | Criação de `projetos/{id}/overrides/` na inicialização de projeto; schemas de override | ✅ Implementado |
| **F2 — Resolução** | `RepositorioInsumo.resolver_preco()` com cascata 3 camadas | ✅ Implementado |
| **F3 — Survey** | `survey` com flag `--output project/master`; default para Project | ⏳ Pendente |
| **F4 — Promotion** | Comando `catalog promote`; integração com check-out do `LifecycleCoordinator` | ⏳ Pendente |

---

## Consequências

### Positivas

| ID | Consequência |
|---|---|
| C1 | Proteção total da base histórica: nenhuma calibração de projeto afeta outros projetos em andamento. |
| C2 | Liberdade operacional: engenheiros calibram livremente sem risco de "quebrar" o catálogo corporativo. |
| C3 | Pipeline de curadoria formal: overrides valiosos têm um caminho claro para promoção ao Master. |
| C4 | Rastreabilidade completa: toda resolução de preço registra qual camada foi usada (`PROJECT_OVERRIDE` / `SICRO_REGIONAL` / `MASTER_BASE`). |

### Negativas / Riscos

| ID | Risco | Mitigação |
|---|---|---|
| R1 | Proliferação de overrides não curados ao final das obras. | Lifecycle: ao `aprovar_versao`, o Coordenador lista overrides pendentes de revisão. |
| R2 | Complexidade adicional no `RepositorioInsumo`. | Resolução encapsulada em método único com retorno de tupla `(preco, fonte)`. |

---

## Definition of Done

### Fase 1 — Estrutura (✅)
- [x] `projetos/{id}/overrides/` criado automaticamente em `ProjectStore.init()`.
- [x] Schemas Pydantic `InsumoOverride`, `CPUOverride`, `BDIOverride` em `domain/models/overrides.py`.
- [ ] `LifecycleCoordinator` carrega overrides ao construir o contexto de execução.

### Fase 2 — Resolução (✅)
- [x] `resolver_preco()` implementado com prioridade `PROJECT_OVERRIDE → SICRO_REGIONAL → HISTORICO_SCD2 → MASTER_BASE`.
- [x] Retorno inclui `fonte` (`FontePreco` literal) para auditoria.
- [ ] Skills 01-07 usam `resolver_preco()` em todos os pontos de acesso a preços.

### Fase 3 — Survey e Promotion
- [ ] `concilium manage catalog survey` salva em `overrides/` por padrão.
- [ ] `concilium manage catalog promote` implementado com confirmação obrigatória.
- [ ] Ao `aprovar_versao`, coordenador lista overrides não curados e pede decisão.
