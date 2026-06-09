# Plano de Implementação: Engine de Custo Unificado

**Data:** 2026-06-08  
**Derivado de:** Auditoria de débito técnico (sessão 2026-06-08)  
**Documentos relacionados:** NEP-029, NEP-030, NEP-031, NEP-032, NEP-037, ADR-105, ADR-106

---

## Contexto

Investigação da divergência entre custo operacional (pool) e PUxQ de catálogo revelou
uma cadeia de débito técnico interligado. Este plano define a sequência mínima e correta
de implementação, respeitando dependências e garantindo que cada sprint entregue valor
observável nos benchmarks.

**Situação atual (pós-sessão 2026-06-08):**
- AGIS: pool Σ = 47.3M vs PUxQ 46.8M (+1%) após correção de `custo_hora_total_referencia`
- Benchmarks verdes: AGIS, CTC, LUNDIN, MARA_ROSA
- ROSH/PRIVATE_LOG INVIÁVEL por dois motivos legítimos:
  1. `custo_hora_total_referencia = 0` nas CPUs (dado faltante no catálogo)
  2. Schedule genuinamente ineficiente (gap de 210 semanas entre usos do mesmo recurso)

---

## Grafo de dependências

```
NEP-032 ──────────────────────────────────────────────────────────┐
  (expurgar precos_unitarios_sbdi como fonte primária de preço)   │
         │                                                        │
         ▼                                                        │
NEP-029 ──────────────────────────────────────────────────────── ┐│
  (custo_hora_total_referencia como base autoritativa)            ││
         │                                                        ││
         ├──────────────────┐                                     ││
         ▼                  ▼                                     ││
NEP-031                  NEP-037                                  ││
(lacunas modelo custo:   (encargos sociais → BDI)                 ││
 L2 ocioso, L3 eventos,        │                                  ││
 D4 SS/FF em EapItem)          │                                  ││
         │                     │                                  ││
         ▼                     │                                  ││
ADR-105 ────────────────────── ┘                                  ││
(janelas mob/demob para equipes diretas:                          ││
 leadtime_mob + lag_demob no catálogo)                            ││
         │                     │                                  ││
         └─────────────────────┴────────────────┐                ││
                                                 ▼               ││
                                          ADR-106 F1–F3 ◄────────┘│
                                          (EquipeCustoEngine core, │
                                           DirectTeamCostStrategy) │
                                                 │                 │
                                                 ▼                 │
                                          ADR-106 F4    ◄──────────┘
                                          (IndirectTeamCostStrategy)
                                                 │
                                                 ▼
                                          ADR-106 F5–F6
                                          (early dismissal EQ +
                                           janelas mob no engine)
                                                 │
                                                 ▼
                                             NEP-030
                                         (benchmark limpo:
                                          remover injeções circulares
                                          como bdi_lucro_impostos)
```

---

## Sprints

### S1 — Base de preço correta (NEP-032 + NEP-029)

**Objetivo:** Garantir que toda a pipeline usa `custo_hora_total_referencia` como base
de custo, não `precos_unitarios_sbdi`. Sem isso, qualquer engine construído
em cima usa a base errada.

**NEP-032:** Expurgar `precos_unitarios_sbdi` como caminho de preço
- Remover leitura de `precos_unitarios_sbdi` em skills 05/06/08 como fonte de custo operacional
- Manter apenas como referência diagnóstica (comparação de mercado)
- Arquivo principal: `src/concilium/application/skills/manifests/06-precificacao-unitaria/`

**NEP-029:** `custo_hora_total_referencia` como base autoritativa
- Estender a correção do pool (commit `edccb3f`) para todos os caminhos
- `custo_unit_semanal = custo_hora_total_referencia × horas_semana`
- Verificar que todas as CPUs usadas em benchmarks verdes têm o campo preenchido
- Para CPUs sem o campo (ex: CPUs do ROSH): popular no catálogo ou documentar como bloqueador

**Critério de aceite:** Σ pool ≈ PUxQ (delta < 5%) para AGIS, CTC, LUNDIN, MARA_ROSA.

---

### S2 — Modelo de custo completo (NEP-031 + NEP-037, paralelo)

**Objetivo:** Corrigir as lacunas do modelo que ADR-106 vai consumir.

**NEP-031:** Lacunas do modelo de custo operacional
- **L2:** `custo_ocioso_equipamentos` — locação nos gaps entre atividades (já parcial)
- **L3:** Mob/demob como evento de transição — contar corretamente n_mob/n_desmob
- **D4:** Suporte a precedências SS/FF em `EapItem` (atualmente só FS)
- Arquivo principal: `src/concilium/domain/models/canonical.py` + skill-05 helpers

**NEP-037:** Encargos sociais do custo direto para BDI
- Criar `custo_encargos_mensal` separado em `EquipeDireta`
- Decomposição: `custo_mao_obra_mensal` = salário base; `custo_encargos_mensal` = CLT
- Pré-requisito para engine ter decomposição limpa de MO base vs. encargos

**Critério de aceite:** `EquipeDireta` tem `custo_encargos_mensal` preenchido; gaps
internos de EQ cobrados corretamente via `custo_ocioso_equipamentos`.

---

### S3 — Engine unificado (ADR-105 + ADR-106 F1–F4)

**Objetivo:** Centralizar cálculo de custo em `equipe_custo_engine.py` e implementar
janelas de mobilização.

**ADR-105:** Janelas de mobilização para equipes diretas
- Definir `leadtime_mob_semanas` e `lag_demob_semanas` por CPU no catálogo
- `custo_mob_window = (c_mo + c_locacao) × leadtime_mob`
- Default: sem janela (backward compatible)

**ADR-106 F1–F3:** Engine core + DirectTeamCostStrategy
- Criar `src/concilium/domain/services/equipe_custo_engine.py`
- Mover `calcular_custo_instancia_composicional` para o engine
- `DirectTeamCostStrategy`: usa `custo_hora_total_referencia × h_sem` como base
- Preencher `custo_inst_*` para equipes sem pool contract (eliminar heurística skill-08)

**ADR-106 F4:** IndirectTeamCostStrategy
- `IndirectTeamCostStrategy`: `custo_fixo_mensal / SEMANAS_POR_MES`
- Skill-07 passa a chamar o engine; `IndiretoSemanal` tem mesma decomposição que direto

**Critério de aceite:** Skill-08 usa `custo_inst_*` sem heurística fallback para todos
os itens. 4 benchmarks verdes mantêm status.

---

### S4 — Early dismissal, janelas e benchmark limpo (ADR-106 F5–F6 + NEP-030)

**Objetivo:** Completar o engine com política de lifecycle e remover injeções circulares
do benchmark.

**ADR-106 F5–F6:** Early dismissal para EQ + janelas no engine
- Early dismissal para equipes diretas: `c_locacao × trailing > c_demob_eq`
- MO não é liberável via early dismissal (CLT — aviso prévio separado)
- Integrar `leadtime_mob_semanas` do catálogo na `DirectTeamCostStrategy`

**NEP-030:** Injeção mínima honesta no benchmark
- Remover `bdi_lucro_impostos` de `resultado` na referência — é injeção ineficaz
  (skill-08 o calcula internamente, não usa o valor injetado)
- Remover campo `mob_schedule` de nível raiz na referência — redundante (skill-04
  infere automaticamente via `infer_mob_windows`; spec_loader não o lê)
- Revisar outras injeções em `spec_loader.py` e `inference.py`

**Critério de aceite:** `pytest tests/` sem regressão; benchmark AGIS sem campos
fora-de-spec em `referencia.json`.

---

## Limpeza imediata no AGIS referencia.json

Independente do roadmap, dois campos podem ser removidos agora:

| Campo | Localização | Motivo |
|---|---|---|
| `mob_schedule` | raiz de `referencia.json` | Fora de spec. Skill-04 infere automaticamente via `infer_mob_windows`; `spec_loader.py` não lê este campo da referência. É artefato de exportação, não input. |
| `resultado.bdi_lucro_impostos` | `resultado{}` | Injeção circular ineficaz. `spec_loader.py` lê e injeta em skill-08, mas skill-08 calcula `bdi_lucro` internamente (`venda_catalogo_plus / custo_operacional_real - 1`) sem usar o valor injetado. Pertence ao escopo de NEP-030. |

---

## Estado do débito técnico (snapshot 2026-06-08)

| Item | Tipo | Sprint | Bloqueado por |
|---|---|---|---|
| NEP-032 | Débito alto | S1 | — |
| NEP-029 | Débito alto | S1 | NEP-032 |
| NEP-031 | Débito médio | S2 | NEP-029 |
| NEP-037 | Débito médio | S2 | NEP-029 |
| ADR-105 | Débito alto | S3 | NEP-031, NEP-037 |
| ADR-106 F1–F3 | Débito alto | S3 | NEP-029, NEP-031, NEP-037 |
| ADR-106 F4 | Débito alto | S3 | ADR-106 F1 |
| ADR-106 F5–F6 | Débito alto | S4 | ADR-105, ADR-106 F1–F3 |
| NEP-030 | Débito médio | S4 | ADR-106 F1–F3 |
| NEP-033 | Débito baixo | Manutenção | — |
| NEP-034 | Débito baixo | Manutenção | — |

**Documentação desatualizada (resolvida em 2026-06-08):**
NEP-035, NEP-036, NEP-038, NEP-039, NEP-040 (parcial), ADR-101, ADR-104 → status atualizados.

---

## Benchmark como indicador de progresso

| Sprint | Indicador |
|---|---|
| S1 | Pool Σ / PUxQ < 1.05× para todos os benchmarks verdes |
| S2 | `custo_inst_*` preenchido para 100% das equipes (pool + direto) |
| S3 | Skill-08 sem heurística fallback; `equipe_custo_engine.py` presente |
| S4 | `referencia.json` sem campos fora-de-spec; 0 injeções circulares |
