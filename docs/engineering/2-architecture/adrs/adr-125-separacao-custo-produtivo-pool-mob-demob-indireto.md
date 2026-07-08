# ADR-125 — Hierarquia de Custo: C_prod / C_pool / Contrato; Mob/Demob como Custo Indireto

**Status:** ✅ Implementado  
**Data:** 2026-06-28  
**Contexto:** MendesLobo Construtora — Concilium  
**Dependências:** ADR-085, ADR-106, ADR-124, NEP-028

---

## Contexto

### Modelo anterior (incorreto)

O ADR-106 (LifecycleEngine) materializou a equação de custo como:

```
total_i = (c_mo + c_eq) · n_p  +  (c_mo + κ · c_eq) · n_s  +  c_mob  +  c_dem
```

tratando a expressão inteira como o custo de ciclo de vida da equipe — sem distinguir
as três camadas semânticas que ela contém.

### Problema identificado

A expressão mistura três categorias conceitualmente distintas:

| Categoria | Componentes | Natureza |
|---|---|---|
| **Custo produtivo** | `γ_i · n_p` | Custo do contrato lockado para execução da atividade |
| **Custo ocioso** | `(γ_i^{mo} + κ · γ_i^{eq}) · n_s` | Custo de manter o pool disponível entre atividades |
| **Mob/demob** | `c_mob + c_dem` | Overhead de canteiro — custo **indireto** |

κ é o fator de custo de equipamento em standby (taxa de locação sem combustível). Ele
pertence ao período ocioso, **não** ao produtivo — durante a produção o equipamento
opera à taxa plena `c_eq`.

Consequências do modelo antigo:
- `p_i^o = total_i / Q_i` inflaciona o preço operacional com mob/demob (custos indiretos)
- `γ_i = total_i^{sem} / h_sem` incluiria indiretamente mob/demob se o total fosse usado
- Não havia distinção entre "o que custa produzir" e "o que custa manter o contrato ativo"

---

## Decisão

### D1 — Hierarquia de três camadas

```
γ_i = Σ_{r ∈ R_i} n_r · γ_r        (taxa semanal da equipe i, ADR-106 / slide)

C_prod_i  =  γ_i · n_p
          →  custo produtivo: contrato lockado do pool para a atividade

C_pool_i  =  C_prod_i + (γ_i^{mo} + κ · γ_i^{eq}) · n_s
          →  custo direto: agregação do contrato do início ao fim (incl. ociosidade)
          →  base de p_i^o = C_pool_i / Q_i

total_i   =  C_pool_i + c_mob + c_dem  +  mob_window + demob_window
          →  custo contratual completo (informativo para o caso operacional)

C_prod_i  ≤  C_pool_i  ≤  total_i   (idle ≥ 0; mob/demob ≥ 0 por construção)
```

onde `γ_i^{mo}` e `γ_i^{eq}` são as componentes MO e EQ de `γ_i = γ_i^{mo} + γ_i^{eq} + ...`
(MO: taxa integral durante idle por CLT; EQ: reduzida por κ = taxa locação/taxa ativa).

**Mob/demob** — alojamento de mão-de-obra, storage de equipamentos em área reservada,
logística de transporte — são **custos indiretos de campo (BDI/DI)**. Não integram
`C_pool_i`, mas são rastreados no `total` por serem informativos no caso operacional
(diagnóstico de onde vem o custo).

### D2 — γ_i usa C_prod_i como base semanal

A taxa horária `γ_i = C_prod_i^{sem} / h_sem` é derivada do custo produtivo, que usa
`c_eq` à taxa plena durante as semanas ativas. Consequência: `p_i^c = γ_i / ρ_i`
reflete o custo real de produção, sem overhead de ociosidade ou canteiro.

### D3 — p_i^o usa C_pool_i como custo direto

O preço operacional `p_i^o = C_pool_i / Q_i` inclui ociosidade porque a ociosidade é
um custo direto da duração do contrato — não pode ser eliminada sem rescindir o contrato.
mob/demob são excluídos porque são custos de campo (BDI), não de produção.

### D4 — Mob/demob integram a parcela DI do BDI, mas são informativos

`c_mob + c_dem` compõem Despesas Indiretas (DI) de campo no memorial de BDI. Embora
sejam custos indiretos, precisam ser rastreados no `total` para:

- Diagnóstico do custo total do pool por projeto
- Validação de que `C_pool ≤ total` (mob/demob não foram absorvidos indevidamente)
- Análise de sensibilidade: projetos com muitas atividades curtas têm mob/demob elevado

### D5 — Adicionar custo_produtivo e custo_pool como propriedades de CustoEquipeDecomposicao

```python
@property
def custo_produtivo(self) -> float:
    """C_prod_i — semanas ativas: base de γ_i (taxa horária)."""
    return round(self.ativo_mo + self.ativo_eq + self.ativo_comb + self.ativo_mat, 2)

@property
def custo_pool(self) -> float:
    """C_pool_i — ativo + ocioso, sem mob/demob: base de p_i^o."""
    return round(
        self.ativo_mo + self.ativo_eq + self.ativo_comb + self.ativo_mat
        + self.idle_mo + self.idle_eq,
        2,
    )
```

`total` permanece como custo contratual completo (IC-3 inalterado). As propriedades
são derivadas, não campos — sem risco de inconsistência.

---

## Alternativas Rejeitadas

| ID | Alternativa | Motivo |
|---|---|---|
| A1 | Incluir idle em custo_produtivo | Idle não é produção: κ < 1 para equipamento em standby reflete isso. Idle é custo de manter contrato, não custo de produzir |
| A2 | Incluir mob/demob em C_pool | Mob/demob são overhead de canteiro (alojamento, storage, transporte). Não variam com n_p ou n_s — são eventos de entrada/saída do pool |
| A3 | Remover rastreamento de mob/demob | Perda de informação operacional: diagnóstico de projetos com muitas atividades curtas depende de mob/demob visíveis |
| A4 | Renomear total → custo_contrato | Quebra retrocompatibilidade; `total` semanticamente correto como soma de todos os componentes (IC-3) |

---

## Consequências

### Positivas

| Efeito | Descrição |
|---|---|
| γ_i correto | Taxa horária derivada do custo produtivo puro — sem ociosidade ou canteiro |
| p_i^o semanticamente preciso | Custo direto real inclui idle (inevitável), exclui mob/demob (BDI) |
| Diagnóstico de ociosidade | `C_pool - C_prod = custo idle` — explicitamente quantificável |
| Rastreabilidade preservada | `total` auditável; mob/demob visíveis para diagnóstico operacional |

### Negativas / Riscos

| Risco | Mitigação |
|---|---|
| Relatórios que usam `total` para pricing estão inflados | Migrar para `custo_pool` onde o denominador é usado para derivar p_i^o |
| Comparações históricas de p_i^o podem divergir | Registrar data de vigência; projetos anteriores não são recalculados |

---

## Plano de Implementação

| Fase | Entregas | Status |
|---|---|---|
| F1 — Domínio | `custo_produtivo` (ativo) e `custo_pool` (ativo+ocioso) em `CustoEquipeDecomposicao`; `total` documentado | ✅ Concluído |
| F2 — Slides | Corrigir `s_regras_custo`: C_prod / C_pool / mob-demob indireto | ✅ Concluído |
| F3 — Testes | 5 testes cobrindo a hierarquia C_prod ≤ C_pool ≤ total | ✅ Concluído |

---

## Definition of Done

- [x] `custo_produtivo` (C_prod) e `custo_pool` (C_pool) implementados como `@property`
      derivadas em `CustoEquipeDecomposicao` (`src/concilium/domain/services/financial/equipe_custo_engine.py`)
- [x] `total` permanece inalterado (IC-3: `total == soma dos componentes`) — sem
      quebra de retrocompatibilidade para GOLDEN/AGIS/Serra Verde
- [x] Invariante `C_prod ≤ C_pool ≤ total` coberta por teste (idle ≥ 0, mob/demob ≥ 0)
- [x] 5 testes unitários em `tests/unit/test_adr106_f1_lifecycle_engine.py`
      (`TestCustoProdutivo`): custo produtivo isolado, C_pool inclui idle, C_pool
      exclui mob/demob, hierarquia completa, C_pool exclui mob/demob window
- [x] Slide `s_regras_custo` (`docs/product/2-presentations/2026-06-26/build_slides.py`)
      corrigido para refletir C_prod / C_pool / total e `p_i^o = C_pool_i / Q_i`
      (estava desatualizado com a fórmula antiga do ADR-106 antes desta entrega)
- [x] Suíte de regressão completa (`uv run pytest`) verde após a mudança —
      nenhuma alteração de campo/lógica existente, apenas propriedades derivadas
      novas; benchmarks GOLDEN/AGIS/Serra Verde não recalculados nem alterados
- [ ] D2/D3 (γ_i com base em C_prod; p_i^o com base em C_pool) permanecem como
      contrato conceitual para consumidores futuros — nenhum call site de
      precificação em produção hoje consome `CustoEquipeDecomposicao.custo_produtivo`
      ou `.custo_pool` diretamente (o cálculo de PU/pool operacional em
      `06-resultado-financeiro/_ponto_equilibrio.py` usa uma rota de particionamento
      de contrato separada — NEP-042/ADR-084 — não `LifecycleEngine`). Migrar esses
      consumidores é trabalho futuro, fora do escopo desta ADR conforme seu próprio
      Plano de Implementação (F1-F3).

**Nota de honestidade:** F1 (domínio) e F3 (testes) já estavam implementados e
mesclados em `main` antes desta entrega (commit `cf56ff47`). Esta entrega fechou
a lacuna real remanescente: F2 (slide desatualizado) e a correção do `Status`
deste documento, que ainda dizia "Decidido" apesar do código já implementado.

---

## Relacionados

- ADR-085 — Custo diferenciado de permanência e mob: introduziu `c_mob`/`c_dem` como eventos
- ADR-106 — LifecycleEngine: materializou `CustoEquipeDecomposicao` com `total` atual
- ADR-124 — Reformulação do modelo de eficiência: η_plan = η_clima · δ
- NEP-028 — Invariantes IC-1 a IC-6: IC-3 (`total == soma de componentes`) inalterado
