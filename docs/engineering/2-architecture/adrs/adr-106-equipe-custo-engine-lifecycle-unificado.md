# ADR-106: EquipeCustoEngine — Lifecycle Unificado para Equipes Diretas e Indiretas

**Status:** Proposto  
**Data:** 2026-06-08  
**Autores:** Engenharia de Plataforma  
**Relacionados:** ADR-079, ADR-080, ADR-085, ADR-104, ADR-105, NEP-040, NEP-031

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

---

## Implementação (fases)

| Fase | Escopo | Pré-requisito |
|---|---|---|
| **F1** | Criar `equipe_custo_engine.py` com `calcular_custo_instancia_composicional` e `LifecycleEngine` | — |
| **F2** | `DirectTeamCostStrategy`: refatorar `_build_dimensionamento` para usar engine | F1 |
| **F3** | Preencher `custo_inst_*` para equipes sem pool (resolve NEP-040 Fase 4) | F2 |
| **F4** | `IndirectTeamCostStrategy`: refatorar skill-07 para usar engine | F1 |
| **F5** | Mob window: adicionar `leadtime_mob_semanas` e `lag_demob_semanas` no catálogo e CPU | F2 |
| **F6** | Early dismissal para EQ de equipes diretas | F2, F5 |
| **F7** | Skill-08 usa `custo_inst_*` sem heurística (elimina fallback) | F3 |
| **F8** | Cubo do pool: face de ocupação de recursos (timeline mob/demob/utilização) | F4 |

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
