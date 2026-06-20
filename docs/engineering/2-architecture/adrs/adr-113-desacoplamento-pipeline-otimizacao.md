# ADR-113 — Tiers de Execução de Skills: OLTP (Planejamento) e OLAP (Análise/Artefatos)

**Status:** Implementado ✅ _(F1–F4 2026-06-19 · 14 testes · renumeração 09→10/10→07/11→08/12→09/13→11)_  
**Data:** 2026-06-19  
**Contexto:** MendesLobo Construtora — Concilium  
**Dependências:** ADR-022 (Wave Execution & Gate Propagation), ADR-036 (CLI Reorganização), ADR-050 (CLI Unificada), ADR-102 (Pipeline Jobs)

---

## Contexto

### Problema

**P1. Pipeline monolítico sem separação entre computação e apresentação.**

O pipeline de skills executa sequencialmente 01→…→13, misturando duas naturezas radicalmente
diferentes de trabalho:

| Categoria | Skills atuais | Característica |
|---|---|---|
| Planejamento (core) | 01–06 | Determinísticas, < 5s cada, produzem canonical |
| Análise/Artefatos | 09–13 | Computacionalmente pesadas, 10–60s, geram Excel/PDF/gráficos |

Toda execução — incluindo exploração paramétrica de campanha (ADR-070) que pode rodar centenas de
vezes — paga o custo das skills pesadas mesmo quando só o resultado de planejamento é relevante.

**P2. Numeração das skills não reflete ordem de execução real.**

```
Execução atual (runner.py):
  01 → 02 → 03 → 04 → 05 → 06 → 10 → 11 → 12 → 09 → 13
                                   ↑                 ↑
                           skill 10 roda antes     skill 09 roda DEPOIS
                           de skill 09             de 10, 11, 12
```

`09-relatorio-e-artefatos` roda por último porque depende dos outputs de `10-diagnostico-criticidade`,
`11-avaliacao-intervencoes` e `12-registro-decisoes` para gerar o Excel completo. O número `09` não
reflete isso. Skills `07` e `08` simplesmente não existem (lacuna).

**P3. Sem definição explícita de quais skills são obrigatórias para um "resultado de planejamento".**

O campo `gate=true` nos toml indica que falha bloqueia downstream, mas não existe distinção
formal entre "skill necessária para tomada de decisão" e "skill necessária para relatório final".
Isso dificulta:
- Expor resultado de planejamento em tempo real via MCP/API sem esperar artefatos
- Rodar campanhas de exploração sem gerar Excel/PDF desnecessários
- Configurar job ACI "leve" vs "completo" por tipo de uso

---

## Decisão

### D1 — Classificação formal em dois tiers: OLTP e OLAP

**Tier 1 — OLTP (Online Transaction Processing):**
Skills que produzem o canonical de planejamento. Rápidas, determinísticas, obrigatórias para qualquer
operação útil do sistema.

| Número novo | Número antigo | Nome | Fase | Descrição |
|---|---|---|---|---|
| 01 | 01 | escopo-e-eap | Inicialização | EAP, atividades, DAG de precedências |
| 02 | 02 | produtividade-climatica | Definição | Praticabilidade semanal, fatores climáticos |
| 03 | 03 | catalogo-de-recursos | Definição | Pool de recursos, catálogo de insumos |
| 04 | 04 | cronograma | Planejamento | RCPSP/scheduling, distribuição semanal |
| 05 | 05 | equipes-e-alocacao | Planejamento | Dimensionamento, mob/demob, custos de pool |
| 06 | 06 | resultado-financeiro | Planejamento | PU×Q, BDI, consolidação financeira |

**Saída do tier OLTP**: canonical completo com `cronograma`, `equipes_diretas`, `resultado` (venda,
custo, margem). Suficiente para responder: "qual o prazo e custo desta configuração?"

**Tier 2 — OLAP (Online Analytical Processing):**
Skills que enriquecem o canonical com análise e geram artefatos de saída. Pesadas, opcionais para
exploração, obrigatórias para entrega final.

| Número novo | Número antigo | Nome | Fase | Descrição |
|---|---|---|---|---|
| 07 | 10 | diagnostico-criticidade | Análise | Curva ABC, pontos de equilíbrio por item |
| 08 | 11 | avaliacao-intervencoes | Decisão | Matriz ROI×Effort×Risk de intervenções |
| 09 | 12 | registro-decisoes | Decisão | Registro estruturado de decisão técnica |
| 10 | 09 | relatorio-e-artefatos | Saída | Excel auditável, PDF, gráficos (depende de 07-09) |
| 11 | 13 | replanejamento-e-cenarios | Análise | Assessor de replanejamento, exploração de planos |

**Saída do tier OLAP**: relatórios, planilhas, gráficos, registros — entregáveis para cliente/equipe.

### D2 — Renumeração das skills OLAP para refletir ordem de execução

Skills 07–11 substituem a numeração desconexa atual (09, 10, 11, 12, 13) com sequência que reflete
dependências reais:
- `07-diagnostico-criticidade` (era `10`) — precisa apenas do canonical de 01-06
- `08-avaliacao-intervencoes` (era `11`) — precisa do diagnóstico (07)
- `09-registro-decisoes` (era `12`) — precisa das intervenções (08)
- `10-relatorio-e-artefatos` (era `09`) — precisa de tudo (07-09) para gerar Excel completo
- `11-replanejamento-e-cenarios` (era `13`) — usa canonical completo (01-09)

### D3 — Três modos de execução explícitos no pipeline

```python
class PipelineMode(str, Enum):
    OLTP  = "oltp"   # skills 01-06: resultado de planejamento (< 30s)
    OLAP  = "olap"   # skills 01-11: completo com artefatos  (2-5min)
    LIGHT = "light"  # skills 01-06 + 10: planejamento + relatório sem análise profunda
```

| Modo | Skills | Caso de uso | Tempo estimado |
|---|---|---|---|
| `OLTP` | 01-06 | Exploração paramétrica, campanha GO, MCP interativo | 5–30s |
| `LIGHT` | 01-06, 10 | Benchmark com relatório básico, sem diagnóstico de criticidade | 30–90s |
| `OLAP` | 01-11 | Entrega completa ao cliente, benchmark de referência | 2–5min |

A troca de `skip_artifacts: bool` por `mode: PipelineMode` formaliza semântica que hoje está
implícita na CLI (`--skip-artifacts`) e no `BenchmarkRunner`.

### D4 — `skill.toml` declara tier explicitamente

```toml
[skill]
id = "07-diagnostico-criticidade"
tier = "olap"          # NOVO: "oltp" ou "olap"
phase = "Análise"
gate = false
...
```

O runtime valida que nenhuma skill OLTP depende de skill OLAP (dependência cruzada é erro de
configuração).

### D5 — Renaming de diretórios é feito via migração explícita

Para manter compatibilidade durante a transição:
1. Criar diretório com nome novo (ex: `07-diagnostico-criticidade`)
2. Adicionar alias `id_legado = "10-diagnostico-criticidade"` no `skill.toml` novo
3. Runtime aceita ambos os IDs por 1 release
4. Remover diretório antigo e alias após todos os callers atualizados

---

## Alternativas Rejeitadas

| ID | Alternativa | Motivo |
|---|---|---|
| A1 | Manter numeração atual e apenas documentar | Não resolve a confusão operacional; 09 rodando depois de 12 vai causar erros futuros |
| A2 | Renomear tudo de uma vez sem aliases | Quebra todas as referências em tests, CLI, runner, conftest — risco de regressão elevado |
| A3 | Usar `skip_artifacts=bool` como hoje | Bool binário não expressa as 3 necessidades (exploração, light, completo) |

---

## Consequências

### Positivas

| Efeito | Descrição |
|---|---|
| Campanhas 10-20× mais rápidas | Modo OLTP pula 5 skills pesadas; campanha de exploração paga < 5% do custo atual |
| Numeração reflete execução | `07 → 08 → 09 → 10` segue dependências reais sem surpresas |
| MCP responde em tempo real | Tool MCP pode retornar resultado financeiro em < 30s sem gerar Excel |
| Tier OLTP testável isoladamente | Testes de integração de campanha não precisam de assets de saída |

### Negativas / Riscos

| Risco | Mitigação |
|---|---|
| Callers hardcoded com `"09-relatorio-e-artefatos"` | Alias no skill.toml garante backward compat por 1 release |
| Canonical marcado como "incompleto" pode ser usado indevidamente | Campo `pipeline_mode` no canonical indica quais tiers foram executados |
| Testes que verificam número de skills precisam ser atualizados | Atualizar em conjunto com a renumeração |

---

## Plano de Implementação

| Fase | Entregas | Status |
|---|---|---|
| F1 | Adicionar `tier = "oltp"\|"olap"` a todos os `skill.toml`; runtime valida sem dependência cruzada | ⬜ Pendente |
| F2 | `PipelineMode` enum; `BenchmarkRunner` e CLI aceitam `mode=` em vez de `skip_artifacts=` | ⬜ Pendente |
| F3 | Renomear `10→07`, `11→08`, `12→09`, `09→10`, `13→11` com aliases de compatibilidade | ⬜ Pendente |
| F4 | Remover aliases e referências legadas após testes verdes | ⬜ Pendente |

**Invariante:** `mode="olap"` deve produzir resultado idêntico ao comportamento atual.

---

## Definition of Done

### Fase 1–2
- [ ] Todos os `skill.toml` têm campo `tier`
- [ ] Runtime rejeita skill OLTP com `depends_on.skills` apontando para skill OLAP
- [ ] `BenchmarkRunner.run(spec, mode=PipelineMode.OLTP)` executa apenas 01-06
- [ ] `pytest tests/` verde

### Fase 3–4
- [ ] Skills renumeradas em `07–11`; diretórios antigos removidos
- [ ] AGIS benchmark com `mode=OLAP` produz canonical idêntico ao baseline
- [ ] Campanha AGIS com `mode=OLTP` completa em < 10s
- [ ] `pytest tests/` verde

---

## Relacionados

- ADR-022 — Wave Execution & Gate Propagation (gate=true permanece no tier OLTP)
- ADR-036 — CLI Reorganização (CLI `concilium project run` recebe `--mode`)
- ADR-050 — CLI Unificada (benchmark CLI igualmente)
- ADR-070 — Cardinalidade Espaço GO (campanha beneficia diretamente do modo OLTP)
- ADR-102 — Pipeline Jobs (job ACI usa `mode` para selecionar tier)
