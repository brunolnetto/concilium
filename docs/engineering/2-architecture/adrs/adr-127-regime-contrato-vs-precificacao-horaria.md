# ADR-127 — Regime de Contrato (Contínuo/Mensal) vs. Precificação Horária: Consolidação

**Status:** ✅ Implementado (consolidação de decisão já implementada, sem código novo)
**Data:** 2026-07-02
**Contexto:** MendesLobo Construtora — Concilium
**Dependências:** ADR-080 (custo diferenciado de permanência/taxa ociosa), ADR-132 (rental_unit, regime de revezamento), ADR-125 (hierarquia C_prod/C_pool), NEP-031 (L1 — rental_unit)

---

## Contexto

### Problema

P1. **O PU final de todo recurso/atividade é sempre expresso em R$/hora produtiva**, mas os contratos reais de aquisição de recursos (locação de equipamento, mão de obra CLT/PJ) têm naturezas de faturamento distintas: hora produtiva, diária, mensal. Essa distinção já está **implementada**, mas em **dois campos distintos e não sinônimos**, nunca consolidados numa ADR central:
   - `rental_unit: Literal["hora_produtiva", "dia_calendario", "mes"]` — em `AtributosInsumo` (`domain/models/catalog/versioned.py:66`) e em `canonical.py:378` (mesmo domínio de valores). Representa a unidade de faturamento **do insumo/composição de catálogo**, consumida pela conversão de PU.
   - `unidade_faturamento: str = "hora_prod"` (valores `"hora_prod" | "dia_cal" | "mes"`, **abreviados**, distintos dos valores de `rental_unit`) — em `RecursoContrato` (`canonical.py:847`), sempre pareado com `custo_idle_semanal_unit` (`canonical.py:846`). Representa a mesma ideia conceitual, mas no domínio do **contrato de pool de recurso** (ADR-071/125), consumido pelo cálculo de custo idle em `application/skills/manifests/05-equipes-e-alocacao/_skill_helpers_pre.py`.
   - `tipo_contrato: Literal["CLT", "PJ"]` para mão de obra em `AtributosInsumo` (`catalogo.py`).
   - Conversão de PU para R$/hora em `pu_calculator._converter_rental_unit()` (usa `rental_unit`).
   - Formalização matemática do impacto no custo idle em `docs/product/4-research/recursos.md` (não é ADR).
   - Menções incidentais em ADR-078, ADR-080, ADR-088, ADR-132 — nenhuma delas é a decisão canônica, e nenhuma esclarece a relação entre os dois campos.

P2. **Os dois campos (`rental_unit` e `unidade_faturamento`) usam vocabulários de valores diferentes para a mesma taxonomia conceitual** (`"hora_produtiva"` vs. `"hora_prod"`, `"dia_calendario"` vs. `"dia_cal"`), sem nenhum ponto do código ou documentação que explicite que são o mesmo conceito em dois domínios (catálogo vs. contrato de pool). Isso é uma fonte real de confusão para quem lê o código pela primeira vez.

P3. **Falta um documento único que explique por que hora produtiva é a unidade canônica** e como as demais unidades de faturamento convertem para ela — hoje um engenheiro precisa ler `pu_calculator.py`, `_skill_helpers_pre.py` e `recursos.md` para entender a regra, sem uma decisão arquitetural rastreável.

> Nota: a política de saída/rescisão de contrato (período mínimo, multa por rescisão antecipada) foi avaliada e **descartada de escopo** — ver A2 em Alternativas Rejeitadas. Ramificaria o modelo sem caso de uso comprovado hoje.

---

## Decisão

### D1 — Consolidação: taxonomia oficial de regime de faturamento, em dois campos com o mesmo significado

Confirma-se (não altera) a implementação existente como decisão arquitetural formal. Dois campos, dois domínios, **mesmo conceito**:

```python
# Catálogo — AtributosInsumo (versioned.py:66) / composição (canonical.py:378)
rental_unit: Literal["hora_produtiva", "dia_calendario", "mes"] = "hora_produtiva"

# Contrato de pool — RecursoContrato (canonical.py:846-847)
custo_idle_semanal_unit: float = 0.0
unidade_faturamento: str = "hora_prod"  # "hora_prod" | "dia_cal" | "mes"
```

Mapeamento formal entre os dois vocabulários (documentado aqui pela primeira vez):

| `rental_unit` (catálogo) | `unidade_faturamento` (contrato de pool) |
|---|---|
| `"hora_produtiva"` | `"hora_prod"` |
| `"dia_calendario"` | `"dia_cal"` |
| `"mes"` | `"mes"` |

Hora produtiva é a **unidade canônica de cálculo interno** (PU de toda composição/atividade). `dia_calendario`/`dia_cal` e `mes` são unidades de **origem contratual**: no catálogo, convertidas em `pu_calculator._converter_rental_unit()` usando `producao_horaria` (η_p) e `horas_dia`/`horas_mes` do recurso; no contrato de pool, o discriminador `unidade_faturamento` decide como `custo_idle_semanal_unit` é aplicado (D2).

`tipo_contrato` (CLT/PJ) é **ortogonal** a essa taxonomia: governa o fator de encargos aplicado em `pu_calculator.calcular_pu()` (`ParametrosCalculo.alpha_clt`/`alpha_pj`, `pu_calculator.py`, com defaults `ENCARGOS_CLT`/`ENCARGOS_PJ` importados de `domain/constants.py`), não a unidade de faturamento. Um recurso PJ pode ser faturado por hora, dia ou mês, assim como um CLT.

### D2 — Custo idle é função de `unidade_faturamento` (formalização de decisão já implementada)

Reafirma-se, agora como ADR, a regra já presente em `docs/product/4-research/recursos.md` e implementada em `application/skills/manifests/05-equipes-e-alocacao/_skill_helpers_pre.py` (consumindo `RecursoContrato.custo_idle_semanal_unit`/`unidade_faturamento`):

```
c_r^idle(j) = 0                    se unidade_faturamento == "hora_prod"
            = ρ_r · d_j             se unidade_faturamento == "dia_cal"  (ρ_r = taxa diária, d_j = dias ociosos)
            = ρ_r / (52/12)         se unidade_faturamento == "mes"     (prorrateio semanal do mês)
```

Um recurso faturado por hora produtiva não gera custo de ociosidade direto (só custo de oportunidade/mobilização, tratado em ADR-125); recursos por dia/mês geram custo idle proporcional ao tempo parado dentro do período já contratado. A tabela de mapeamento em D1 é o elo entre essa regra (nível de contrato de pool) e `rental_unit` (nível de catálogo).

### D3 — Documento de referência único

`docs/product/4-research/recursos.md` passa a ser referenciado nesta ADR como a fonte formal da matemática de custo idle por unidade de faturamento; esta ADR é o registro arquitetural correspondente, evitando que a decisão continue existindo só como pesquisa não-ADR — e é o primeiro lugar a documentar explicitamente a relação `rental_unit` ↔ `unidade_faturamento` (D1).

---

## Alternativas Rejeitadas

| ID | Alternativa | Motivo |
|---|---|---|
| A1 | Modelar todo contrato só em hora, ignorando dia/mês | Já rejeitado pela implementação existente (`rental_unit`) — perderia rastreabilidade com o contrato real de locação/fornecedor |
| A2 | Modelar período mínimo contratual e multa de rescisão antecipada | Rejeitado — nenhum contrato atual (SV-31, AGIS) tem cláusula de rescisão explícita hoje; ramificaria o modelo de custo (nova camada em `AtributosInsumo` + motor de custo + cubo analítico) sem caso de uso comprovado. Revisitar se/quando um contrato real exigir |

---

## Consequências

### Positivas

| Efeito | Descrição |
|---|---|
| Decisão rastreável | `rental_unit`/`unidade_faturamento`/custo idle deixam de existir só em código e pesquisa dispersa, ganham registro arquitetural único |
| Confusão terminológica esclarecida | Mapeamento explícito entre `rental_unit` (catálogo) e `unidade_faturamento` (contrato de pool), inexistente antes desta ADR |
| Sem risco de regressão | Nenhuma mudança de código — só documentação de decisão já implementada |

### Negativas / Riscos

| Risco | Mitigação |
|---|---|
| Confusão entre `tipo_contrato` (CLT/PJ) e a taxonomia de faturamento (`rental_unit`/`unidade_faturamento`) | Documentar explicitamente a ortogonalidade nesta ADR e no docstring de `AtributosInsumo`/`RecursoContrato` |
| Dois campos com vocabulários distintos para o mesmo conceito podem divergir no futuro (ex.: novo valor adicionado a um mas não ao outro) | Tabela de mapeamento (D1) como referência única; ao adicionar um novo valor de unidade de faturamento, atualizar ambos os `Literal`/comentário e a tabela |

---

## Plano de Implementação

| Fase | Entregas | Status |
|---|---|---|
| F1 | Esta ADR consolida a decisão já implementada (D1, D2, D3) — sem mudança de código | ✅ Concluído |

## Definition of Done

### Fase 1
- [x] `rental_unit`, `unidade_faturamento`, mapeamento entre os dois, custo idle e ortogonalidade com `tipo_contrato` documentados nesta ADR
- [x] Escopo de política de rescisão/período mínimo avaliado e explicitamente descartado (A2)

---

## Relacionados

- ADR-080: Custo diferenciado de permanência / taxa ociosa — base do cálculo de custo idle por `rental_unit`
- ADR-132: Regime de revezamento e `rental_unit` — primeira implementação da taxonomia de faturamento
- ADR-125: Hierarquia C_prod/C_pool/Contrato — camada de custo onde `rental_unit` se insere
- `docs/product/4-research/recursos.md` — formalização matemática de custo idle por unidade de faturamento
