# ADR-106: EquipeCustoEngine — Lifecycle Unificado para Equipes Diretas e Indiretas

**Status:** Implementado ✅ _(F1-F4, F6, F7 entregues; F2-bis fecha gap de mob/demob real de F2; F4-bis corrige bug de unidade de F4; F5 bloqueado por dado de catálogo; F8 → ADR-086. Reconciliado 2026-06-20, F2-bis/F4-bis 2026-07-10)_  
**Data:** 2026-06-08  
**Autores:** Engenharia de Plataforma  

> **Reconciliação de status (2026-06-20):** a nota de 2026-06-09 ficou defasada. Estado real verificado no código:
> - ✅ `equipe_custo_engine.py` (F1): `LifecycleEngine` + `CustoEquipeDecomposicao` implementados e testados (`test_adr106_f1_lifecycle_engine.py`).
> - ✅ `DirectTeamCostStrategy` (F2) e `IndirectTeamCostStrategy` (F4): implementados e testados — **F4 tinha um bug de unidade não detectado por fixtures artificiais, corrigido em F4-bis (2026-07-10), ver nota abaixo.**
> - ✅ `_fill_custo_inst_sem_pool` (F3): integrado em skill-05 (skill.py:322); invariante IC-3 (Σ custo_inst_* ≈ custo_total) garantido por rescaling.
> - ✅ **F6 (early dismissal EQ)**: funcional no pipeline — `economia_desmobilizacao_antecipada` computado em `_skill_helpers_a.py:2539`; 21 testes passando (`test_adr106_f6_early_dismissal.py`). **Antes marcado deferred; rótulo corrigido.**
> - ✅ F7: skill-08 usa `custo_inst_*` diretamente.
> - ⏳ **F5 (mob window)**: engine PRONTO (`leadtime_mob_semanas`/`lag_demob_semanas` em `LifecycleEngine.calcular`) e constantes PRONTAS (`DEFAULT_LEADTIME_MOB_SEMANAS=2`, `DEFAULT_LAG_DEMOB_SEMANAS=1`). Bloqueio é **ausência de dado**: 0 CPUs do catálogo têm `mob_policy.leadtime_mob_semanas`. Ver nota de não-implementação abaixo.
> - 💡 F8 (face de ocupação no cubo): aguarda extensão do ADR-086.
**Relacionados:** ADR-079, ADR-080, ADR-085, ADR-104, ADR-105, NEP-040, NEP-031

> **Por que F5 NÃO foi implementado agora (decisão consciente):** conectar o read-path com fallback 0
> seria código inerte (nenhum benchmark mudaria, pois nenhuma CPU tem `mob_policy`); aplicar os
> DEFAULT constants automaticamente a todas as equipes (a) quebraria o baseline calibrado do AGIS
> (16,5M) e (b) **duplicaria o custo MOB**, que já é contabilizado nos indiretos (categoria MOB,
> ADR-105). F5 deve ser ativado quando o catálogo for populado com `mob_policy` por CPU, junto de
> uma análise de não-dupla-contagem MOB-direto × MOB-indireto. Engine e constantes ficam prontos.

> **F4-bis — correção de bug de unidade (2026-07-10):** a reconciliação de 2026-06-20 marcou F4
> como "implementado e testado", mas os testes usavam apenas fixtures artificiais
> (`test_adr106_f4_indirect_strategy.py`) que nunca expuseram um bug real: `IndirectTeamCostStrategy`
> tratava `Indireto.custo_mao_obra`/`custo_equipamentos` como **taxas mensais** (dividindo por
> `SEMANAS_POR_MES`), quando na verdade são **totais já escalados para a permanência inteira** — ver
> o invariante documentado no próprio modelo `Indireto`
> (`custo_total ≈ custo_mao_obra + custo_equipamentos + custo_combustivel + custo_verba + custo_mobilizacao`,
> `domain/models/canonical/_financeiro_resultado.py`). Com um `Indireto` de formato real, o bug
> inflava o custo em ~5-6× (ex.: R$ 120.000 → R$ 607.946 para um projeto de 26 semanas). Corrigido:
> a taxa semanal agora é derivada dividindo por `semanas_projeto` (não por `SEMANAS_POR_MES`), e
> `custo_verba` (componente que faltava) foi adicionado a `CustoEquipeDecomposicao`/`LifecycleEngine`.
>
> **Ainda não conectado à produção** — skill-06 continua calculando indiretos via
> `_process_mob_categoria`/`_resolucao.py`/`_sub_custos_indireto`, um modelo de **alocação
> proporcional** de um custo total já calculado entre MO/EQ/verba (com regra de resíduo para
> composição parcial), estruturalmente diferente do modelo **taxa × semanas** do
> `LifecycleEngine`. Unificar os dois exigiria reescrever o modelo de cálculo de ADM/TOP/LAB/QSMS,
> não só corrigir `IndirectTeamCostStrategy` — avaliado e descartado por ora (ver Alternativas
> Rejeitadas). Esta correção deixa a estratégia **correta e segura de usar** caso um consumidor real
> apareça no futuro (ex.: quando/se o split de fase MOB do ADR-105 §6.6 for retomado), em vez de um
> bug latente esperando alguém confiar nela.

> **F2-bis — mob/demob real para equipes diretas sem pool (2026-07-10):** `DirectTeamCostStrategy`/
> `_fill_custo_inst_sem_pool` (F2/F3) sempre chamavam `LifecycleEngine.calcular()` com `c_mob=c_demob=0.0`
> — os campos `EquipeDireta.custo_mobilizacao_mensal`/`.custo_desmobilizacao_mensal` estavam declarados
> no modelo mas nunca eram atribuídos em produção, então `custo_inst_mob_demob` vinha inteiramente do
> resíduo de arredondamento do fechamento IC-3, não de um custo de mob/demob real. Corrigido: nova
> `_calc_custo_mob_desmob_split` (skill-05, `_dimensionamento_itens.py`) separa o cálculo existente de
> custo por evento de transição de recurso em `(custo_mob, custo_demob)`, populando os dois campos;
> `_fill_custo_inst_sem_pool` agora lê esses valores reais em vez do default 0.0. Retrocompatível —
> equipes sem esses campos (default 0.0) mantêm o comportamento anterior. Testes: `test_l3bis_*` em
> `test_nep031_lacunas_modelo.py`, `TestFillCustoInstSemPoolMobDemobReal` em
> `test_adr106_f3_custo_inst_sem_pool.py`.

---

## Contexto

### Situação atual

O cálculo de custos de equipes está fragmentado em três lugares com lógicas parcialmente duplicadas e inconsistências:

**Skill-05** (`_skill_helpers_a.py`, ~2.600 linhas):
- Computa `EquipeDireta` a partir de insumos do catálogo
- Implementa lifecycle de pool (late hire, early dismissal, idle/off) via ADR-085
- Não aplica lifecycle a equipes sem pool contract
- Mob/demob como evento pontual (`n_transições × c_unit`), sem janela temporal

**Skill-07** (`_skill_helpers_b.py`):
- Computa `Indireto` a partir de configuração (custo fixo mensal por categoria)
- Lifecycle implícito: span do projeto inteiro, sem late hire, sem early dismissal
- MOB como categoria separada com driver `one_time` (semana 0 + semana final)
- Sem idle/off — distribuição uniforme independente de atividades

**Skill-08** (`_skill_helpers_a.py`):
- Recomputa decomposição de custo via heurística `custo_total / custo_fixo_mensal` quando `custo_inst_*` é None (equipes sem pool)
- Diverge de skill-05 por não ter acesso à decomposição original

### Investigação realizada (2026-06-08)

**Diagnóstico do custo operacional vs PUxQ:** O campo `valor_horario` na produção é **produtividade** (unidade/h), não custo. O custo real é `custo_hora_total_referencia` (R$/h). O `custo_unit_semanal` do pool estava usando o proxy `custo_total_item / machine_weeks`, que era distorcido pelo schedule. Corrigido para usar `custo_hora_total_referencia × horas_semana` do catálogo (commit `edccb3f`), fazendo o pool reconciliar com PUxQ (47.3M vs 46.8M, delta +1%).

**MO durante standby para equipes diretas:** O custo de MO em gaps internos é cobrado como custo fixo mensal × permanência — correto em valor total, mas opaco (não distingue semanas produtivas de ociosas). O modelo do pool via `calcular_custo_instancia_composicional` (ADR-085 D3) já trata isso corretamente:
- MO integral durante idle (CLT — não dispensável por semana)  
- EQ à taxa de locação reduzida `ρ` durante idle
- COMB e MAT zerados durante idle (sem operação)

**Janela de mobilização para equipes diretas:** Atualmente inexistente. A equipe "nasce" na primeira semana produtiva e "some" na última. O custo de mob/demob existe apenas como evento pontual (`n_transições × c_unit`). Não há janela pré-atividade (leadtime de mob) nem pós-atividade (lag de demob) para equipes diretas.

**Early dismissal para CLT:** A política de early dismissal do pool aplica-se **apenas ao componente de equipamento** para equipes CLT:
```
economia_desmob_direta = c_locacao_semanal × trailing_weeks - c_desmob_eq
```
A MO é compromisso firme (aviso prévio + rescisão) — não redutível via early dismissal semanal.

**Equipes indiretas:** Estrutura distinta — custo fixo mensal por categoria (ADM, TOP, LAB, QSMS, MOB), project-scoped (span do projeto inteiro), sem lifecycle por instância. A parte de lifecycle (idle vs off, mob windows) é compartilhável com diretas, mas a parameterização de custo é diferente.

---

## Decisão

### Engine unificado com estratégias especializadas

Criar `src/concilium/domain/services/equipe_custo_engine.py` com interface única para cálculo de custo de equipes. O engine centraliza o **lifecycle** (que é idêntico para diretas e indiretas) e delega a **parameterização de custo** para estratégias especializadas.

```
EquipeCustoEngine
├── lifecycle: LifecycleEngine         ← compartilhado (ADR-085 D3)
│   ├── calcular_custo_instancia_composicional()
│   ├── _compute_adr085_gaps()
│   └── _compute_desmob_antecipada()
│
├── DirectTeamCostStrategy             ← equipes diretas + pool
│   ├── Parameterização: custo_hora_total_referencia × horas_semana
│   ├── Escopo: activity-scoped (schedule da atividade)
│   ├── Mob window: leadtime_mob + lag_demob por CPU
│   └── Early dismissal: apenas componente EQ (c_locacao × trailing > c_desmob_eq)
│
└── IndirectTeamCostStrategy           ← equipes indiretas
    ├── Parameterização: custo_fixo_mensal / SEMANAS_POR_MES
    ├── Escopo: project-scoped (span do projeto)
    ├── MOB: driver "one_time" (semana 0 + semana final)
    └── Early dismissal: N/A (indiretos vinculados ao projeto, não ao recurso)
```

### Saída padronizada: `CustoEquipeDecomposicao`

Ambas as estratégias produzem o mesmo tipo de saída:

```python
@dataclass
class CustoEquipeDecomposicao:
    # Custo ativo (semanas produtivas)
    ativo_mo: float     # MO integral
    ativo_eq: float     # EQ + manutenção
    ativo_comb: float   # Diesel (apenas diretas)
    ativo_mat: float    # Material (apenas diretas)
    
    # Custo ocioso (semanas idle — mobilizado sem produzir)
    idle_mo: float      # MO integral CLT
    idle_eq: float      # EQ à taxa de locação reduzida ρ
    
    # Mob/demob
    mob: float          # Custo de entrada no pool/projeto
    demob: float        # Custo de saída (early dismissal ou fim normal)
    
    # Janelas de mob (novo — ADR-106)
    mob_window: float   # (c_mo + c_eq_locacao) × leadtime_mob
    demob_window: float # (c_mo + c_eq_locacao) × lag_demob
    
    # Semanas off (custo zero — antes do mob ou depois do demob)
    semanas_off: int
    
    # Total
    total: float  # Σ de todos os componentes acima
```

### Política de lifecycle para equipes diretas

A política ADR-080/ADR-085 (atualmente só para pool) passa a aplicar-se a **todas** as equipes:

**1. Janela de mobilização (leadtime)**

Definida por `leadtime_mob_semanas` no catálogo (campo novo em `CPU.mob_policy` ou default por categoria):

```
custo_mob_window = (c_mo + c_locacao) × leadtime_mob_semanas
                   ← MO na folha + aluguel de EQ, sem combustível nem produção
```

O `leadtime_mob` padrão pode ser:
- Derivado da `composicao_padrao_equipe` (distância de origem, tipo de EQ)
- Ou definido como constante por categoria de obra (e.g., 2 semanas para terraplenagem)

**2. Lag de desmobilização**

Simétrico ao leadtime:

```
custo_demob_window = (c_mo + c_locacao) × lag_demob_semanas
```

**3. Early dismissal — apenas EQ (CLT)**

```python
economia_eq = c_locacao_semanal × trailing_weeks - c_desmob_eq
if economia_eq > 0:
    # Devolver EQ antecipadamente
    custo_desmob_eq += c_desmob_eq
    # MO continua sendo paga no aviso prévio (tratada separadamente — ver §Aviso Prévio)
```

**4. Aviso prévio (CLT) — escopo futuro**

O custo de rescisão/aviso prévio não é modelado nesta versão. Decisão: registrar `semanas_aviso_previo` como campo informativo no `CustoEquipeDecomposicao`, sem impacto nos gates de viabilidade atual. ADR separado quando a política trabalhista precisar de modelagem completa.

**5. Gaps internos (idle vs off)**

A mesma decisão do pool aplica-se a equipes diretas:

```
custo_manter_ocioso = (c_mo + c_locacao) × gap_weeks
custo_liberar       = c_demob_eq + c_mob_eq (EQ apenas — MO não é liberável)

→ IDLE  se custo_manter ≤ custo_liberar (EQ permanece alugado)
→ OFF   se custo_manter >  custo_liberar (EQ devolvido e recontratado)
```

Nota: para equipes CLT, `c_mo` no gap é **sempre** pago independente da classificação IDLE/OFF (não há "off" para MO — apenas "menos ocioso"). A classificação IDLE/OFF determina o custo de EQ, não de MO.

### Política de lifecycle para equipes indiretas

Equipes indiretas têm um modelo simplificado compatível com o engine:

| Conceito | Equipe Direta | Equipe Indireta |
|---|---|---|
| Escopo | Activity-scoped | Project-scoped |
| Lifecycle start | `semana_mobilizacao` (late hire) | `data_inicio` do projeto |
| Lifecycle end | `semana_desmobilizacao` (early dismissal EQ) | `data_termino` do projeto |
| Mob window | `leadtime_mob_semanas` × (c_mo + c_locacao) | `custo_mob` (categoria MOB, one_time) |
| Idle weeks | Gaps entre atividades | Não aplicável — indiretos são contínuos |
| Early dismissal | EQ liberável, MO não | Não aplicável — projeto-scoped |

A categoria MOB existente em skill-07 (`driver: "one_time"`) é a representação de mob/demob para indiretos. O engine reconhece essa categoria como evento de entrada/saída e popula `mob` e `demob` no `CustoEquipeDecomposicao` adequadamente.

---

## Consequências

### Diretas

1. **`calcular_custo_instancia_composicional`** (atualmente em `_05_equipes_custo_helpers.py`) migra para `equipe_custo_engine.py` e passa a ser a função canônica para ambos os tipos.

2. **`_calc_custo_cron`** em skill-05 é refatorado para chamar o engine, preenchendo `custo_inst_*` também para equipes sem pool contract (resolve o gap do NEP-040 Fase 4).

3. **Skill-07** passa a chamar `IndirectTeamCostStrategy`, preenchendo `IndiretoSemanal` com decomposição `ativo_mo`, `idle_mo` etc. — mesma estrutura do direto. Melhora auditabilidade.

4. **Skill-08** usa `custo_inst_*` (já preenchidos pelo engine para todos os casos) — elimina a heurística `custo_total / custo_fixo_mensal`.

5. **Cubo do pool** (`CuboPoolInstancial`) pode ser estendido com uma face de ocupação de recursos (timeline de entrada/saída, utilização por tipo) sem necessidade de nova estrutura — dados já existem em `InstanciaRecurso`.

### Positivas

- Eliminação da heurística de decomposição em skill-08
- Late hire / early dismissal unificados com política do pool
- Mob/demob como janela temporal (não evento pontual) para diretas
- `CustoEquipeDecomposicao` como fonte única de verdade para skill-05, 07 e 08
- Cubo analítico reconciliado: direto ≈ PUxQ (custo operacional) + BDI = preço de venda

### Negativas / Riscos

- Refatoração de ~800 linhas em skill-05 (`_build_dimensionamento` e chain)
- `leadtime_mob_semanas` e `lag_demob_semanas` precisam ser populados no catálogo (dados novos)
- Benchmarks ROSH/PRIVATE_LOG têm `custo_hora_total_referencia = 0` nas CPUs usadas — necessário popular o catálogo antes que o engine produza custos corretos para esses projetos
- Aviso prévio CLT não está modelado — custo de rescisão pode ser subestimado para projetos com dispensa antecipada de equipe

### Não alteradas

- Política de perpetuation chains (ADR-073) para pool — permanece no pool contract
- Shapley allocation de custo de pool por item (ADR-071) — permanece
- BDI application (ADR-023, ADR-090) — permanece em skill-08

---

## Alternativas rejeitadas

### A1: Engines separados por tipo

Manter `DirectCostEngine` e `IndirectCostEngine` completamente independentes.

Rejeitado porque: a lógica de lifecycle (idle vs off, early dismissal, mob windows) é idêntica para ambos e seria duplicada. A experiência com ADR-085 mostra que manter duas implementações paralelas diverge ao longo do tempo.

### A2: Engine único sem estratégias

Um único engine monolítico com branches `if tipo == "direto" else tipo == "indireto"`.

Rejeitado porque: a parameterização de custo é genuinamente diferente (unit price vs fixed monthly) e teria que ser codificada como condicionais espalhados, dificultando extensão para novos tipos (por ex. subcontratados).

### A3: Estender skill-05 para cobrir indiretos

Absorver skill-07 em skill-05.

Rejeitado porque: indiretos são configurados por categoria de projeto, não por CPU de catálogo. O modelo de responsabilidade de skill-07 (receber configuração de indiretos e distribuir temporalmente) é distinto do de skill-05 (calcular equipes a partir de composição de CPU). Mesclar aumentaria acoplamento sem ganho.

### A4 (F4-bis, 2026-07-10): substituir `_resolucao.py`/`_sub_custos_indireto` por `IndirectTeamCostStrategy` na produção

Rejeitado por ora: `_sub_custos_indireto` implementa **alocação proporcional** de um custo total já calculado entre MO/EQ/verba, com regra de resíduo para composição parcial (quando a config só decompõe parte do custo mensal, o resíduo vira verba — correção histórica documentada no próprio código, ADR-090). O `LifecycleEngine` calcula **taxa × semanas**, um modelo bottom-up sem noção de "resíduo de composição parcial". Portar essa regra para o engine é reescrever o modelo de cálculo de ADM/TOP/LAB/QSMS, não uma troca mecânica de chamada — diferente do que aconteceu com o pool de recursos diretos (ADR-136 F5), onde as duas implementações já batiam numericamente antes de qualquer mudança. Reavaliar se/quando houver necessidade de negócio clara de unificar (ex.: split de fase MOB do ADR-105 §6.6, que usa só o subconjunto MOB — mob/demob — onde os dois modelos são comparáveis).

---

## Implementação (fases)

| Fase | Escopo | Pré-requisito |
|---|---|---|
| **F1** | Criar `equipe_custo_engine.py` com `LifecycleEngine` e `CustoEquipeDecomposicao` | ✅ 2026-06-10 |
| **F2** | `DirectTeamCostStrategy`: converte campos mensais de EquipeDireta para taxa semanal e delega para engine | ✅ 2026-06-10 |
| **F2-bis** | Mob/demob real (não 0.0) para equipes diretas sem pool: `_calc_custo_mob_desmob_split` popula `custo_mobilizacao_mensal`/`.custo_desmobilizacao_mensal` | ✅ 2026-07-10 |
| **F3** | `_fill_custo_inst_sem_pool`: preenche `custo_inst_*` para equipes sem pool; integrado em skill-05 | ✅ 2026-06-10 |
| **F4** | `IndirectTeamCostStrategy`: parameteriza indiretos para engine (custo_mobilizacao como mob/demob) | ✅ 2026-06-10 |
| **F5** | Mob window: `leadtime_mob_semanas`/`lag_demob_semanas` no catálogo e CPU | ⏳ Bloqueado por dado — engine+constantes prontos; 0 CPUs com `mob_policy`. Não ativar sem análise de dupla-contagem MOB direto×indireto |
| **F6** | Early dismissal para EQ de equipes diretas | ✅ 2026-06-20 — `economia_desmobilizacao_antecipada` no pipeline (skill-05); 21 testes |
| **F7** | Skill-08 usa `custo_inst_*` diretamente (elimina fallback proporcional) | ✅ 2026-06-10 |
| **F8** | Cubo do pool: face de ocupação de recursos (timeline mob/demob/utilização) | 💡 Pendente — aguarda ADR-086 extensão |

**F1–F3 são o caminho crítico** para reconciliação direta com PUxQ.  
**F4** pode ser paralelo a F2/F3.  
**F5–F6** dependem de dados de catálogo serem populados.

---

## Referências

- [ADR-079](./adr-079-ativacao-economica-compartilhamento.md) — Ativação econômica e early dismissal detection
- [ADR-080](./adr-080-custo-diferenciado-permanencia-mob-tardia-taxa-ociosa.md) — Late hire, idle rate split, early dismissal (supersedido parcialmente pelo ADR-085)
- [ADR-085](./adr-085-custo-instancial-composicional-temporal.md) — Custo instancial composicional: prod/idle/off por componente
- [ADR-104](./adr-104-centralizacao-calculo-custos-equipedireta.md) — Centralização via `custo_inst_*` em EquipeDireta
- [ADR-105](./adr-105-mobilizacao-desmobilizacao-workforce-equipment.md) — Política de janelas de mobilização
- [NEP-040](../4-development/neps/nep-040-implementacao-decomposicao-instancial-custos.md) — Implementação da decomposição instancial
- [NEP-031](../4-development/neps/nep-031-custo-mob-desmob.md) — Custo de mob/demob (L2: ocioso, L3: eventos)
