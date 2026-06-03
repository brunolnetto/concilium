# ADR-056: Remediação de Débito Técnico — Lacunas de Planejamento Temporal e Financeiro

**Status:** Implementado  
**Data:** 2026-05-16  
**Autor:** Engenheiro Sênior  
**Relacionado:** ADR-004 (Scheduling), ADR-005 (Replanning), ADR-010 (Activity Cost Breakdown), ADR-019 (Reconciliation), ADR-023 (BDI), ADR-033 (BlobStorage)

---

## 1. Contexto

Varredura sistemática do codebase em 2026-05-16 revelou seis categorias de débito técnico crítico que bloqueiam o objetivo central do Concilium: **planejamento temporal e financeiro de projetos de construção civil**.

Os achados foram classificados em:
- **Crítico (T):** Bloqueia o objetivo de planejamento
- **Alto (A):** Degrada confiabilidade em cenários reais
- **Médio (M):** Débito acumulado, aumenta custo de manutenção

---

## 2. Achados e Decisões

### T1 — `intervalos_atividade` nunca populado *(Crítico)*

**Problema:** `CanonicalModel.intervalos_atividade: list[AtividadeIntervalo]` é declarado com factory method `from_scheduled_activity()` em `canonical.py:232`. Nenhuma skill chama esse método. A rastreabilidade semana × atividade é a granularidade mínima para controle de progresso real vs. planejado.

**Decisão:** Skill 04 (`cronograma`) popula `intervalos_atividade` imediatamente após construir `scheduled_activities_out`, usando o factory method já definido no modelo.

---

### T2 — `custos_atividades` nunca populado *(Crítico)*

**Problema:** `AtividadeCustoCompleto` agrega custo direto + indireto + mobilização por atividade. Nenhuma skill escrevia esse campo. Relatórios de skills 09 e 15 reportam apenas totais agregados.

**Decisão:** Skill 08 (`consolidacao-financeira`) adiciona `_build_custos_atividades()` que une `equipes_diretas`, `planejamento` e `cronograma.scheduled_activities` em `custos_atividades`. Indireto é alocado proporcionalmente por duração.

---

### T3 — Três valores de `HORAS_MES` coexistindo *(Crítico)*

**Problema:** Três constantes para horas/mês em uso simultâneo em 7+ arquivos: `208.0` (regime 6×8h), `220.0` (CLT 44h/sem), `4.33` (semanas/mês). Dependendo do caminho de execução, custo mensal de MO varia até ~5.8% sem razão documentada.

**Decisão:** Criar `domain/constants.py` como fonte canônica. Cada consumidor importa a constante correta para seu contexto. `conversor_unidades.py` mantém `220.0` apenas para conversão de preços de mercado (SMM). Skills de custo usam `HORAS_MES_REGIME_6x1 = 208.0`.

---

### T4 — Skill 05 expande custo para todo o projeto quando `distribuicao_semanal` está vazia *(Crítico)*

**Problema:** `skills/05:491` usa `projeto.data_inicio / data_termino` como fallback quando não há cronograma, inflando custos de equipe sem emitir nenhum aviso. Projetos com WMP configurado mas sem run executado são afetados.

**Decisão:** Emitir `VAL-EQUIP-SEM-CRON` com status `AVISO` e usar duração mínima de 1 semana em vez do span completo do projeto.

---

### T5 — `replanning_history` nunca escrito *(Crítico)*

**Problema:** Skill 13 gera `replan_suggestions` e os escreve no canonical, mas nunca adiciona entrada em `replanning_history`. A trilha de auditoria de decisões de replanejamento (ADR-005) está sempre vazia.

**Decisão:** Skill 13 appends um entry em `replanning_history` em cada execução que gera sugestões.

---

### T6 — Domínio importa infraestrutura *(Crítico)*

**Problema:** `domain/services/validador_pu_catalogo.py:14` importa `from concilium.infrastructure.repositories.insumo import RepositorioInsumo`. Viola Clean Architecture — domínio deve ser independente de infraestrutura.

**Decisão:** Usar `TYPE_CHECKING` guard — importação ocorre apenas para type checkers (mypy, IDEs), não em runtime. Função já aceita `repo: RepositorioInsumo | None = None` como parâmetro; o caller (application layer) injeta a dependência.

---

### A3 — `StorageProjectHandle.create_escopo()` bloqueia multi-escopo em cloud *(Alto)*

**Problema:** `raise NotImplementedError` em `storage_project_repository.py:249` bloqueia ADR-031 (Escopos e Planos Paralelos) em deployments SharePoint.

**Decisão:** Implementar escopo básico via caminhos de storage: `{project_id}/escopos/{escopo_id}/meta.json`.

---

### M1 — Constantes de encargos hardcoded em múltiplos skills *(Médio)*

**Problema:** `1.777` (CLT) e `1.06` (PJ) hardcoded em Skills 05, 07 e `pu_calculator.py`. Mesmo problema que T3.

**Decisão:** Centralizar em `domain/constants.py` com `ENCARGOS_CLT = 1.777` e `ENCARGOS_PJ = 1.06`. Skills leem de lá como default, ainda sobrescrevíveis por `inputs`.

---

### M7 — `sidecar` writes falham silenciosamente *(Médio)*

**Problema:** Três locations com `pass  # best-effort` quando sidecar writes falham, sem log.

**Decisão:** Substituir `pass` por `logger.warning(...)` com contexto suficiente para diagnóstico.

---

## 3. O Que Não Muda

- Estrutura de skills (01–15) — adições são implementadas dentro dos skills existentes, não como skills novas
- `CanonicalModel` fields — apenas population, sem schema change
- API contracts e UI — transparente para consumidores externos

---

## 4. Plano de Implementação

| ID | Entrega | Arquivo(s) alterado(s) |
|----|---------|----------------------|
| T3+M1 | `domain/constants.py` + atualizar consumers | `constants.py`, skills 05/07, `pu_calculator.py`, `canonical.py` |
| T1 | `intervalos_atividade` em Skill 04 | `04-cronograma/skill.py` |
| T2 | `custos_atividades` em Skill 08 | `08-consolidacao-financeira/skill.py` |
| T4 | Warn + fallback correto em Skill 05 | `05-equipes-e-alocacao/skill.py` |
| T5 | `replanning_history` em Skill 13 | `13-assessor-replanejamento/skill.py` |
| T6 | TYPE_CHECKING guard em `validador_pu_catalogo` | `validador_pu_catalogo.py` |
| A3 | `create_escopo` em `StorageProjectHandle` | `storage_project_repository.py` |
| M7 | Logs em sidecar writes | `project.py`, `escopo_store.py`, `executor.py` |

## Definition of Done

- [x] `domain/constants.py` com `HORAS_MES_REGIME_6x1`, `HORAS_MES_CLT`, `ENCARGOS_CLT`, `ENCARGOS_PJ`, `SEMANAS_POR_MES`
- [x] `canonical.intervalos_atividade` populado após cada run de Skill 04 com cronograma
- [x] `canonical.custos_atividades` populado após Skill 08 com breakdown por atividade
- [x] Skill 05 emite `VAL-EQUIP-SEM-CRON` em vez de fallback silencioso
- [x] Skill 13 appends em `replanning_history` ao gerar sugestões
- [x] `validador_pu_catalogo.py` sem import de infraestrutura em runtime
- [x] `StorageProjectHandle.create_escopo()` funcional
- [x] Sidecar failures logadas como WARNING
- [x] Suite completa de testes passando (zero regressões)
