# NEP-031: Lacunas do modelo de custo operacional frente ao enunciado de planejamento

**Status:** Parcialmente Implementado ⚠️ _(Sprint S2 — 2026-06-09)_  
**Prioridade:** 🟠 Alto  
**Área:** Domínio + Skills  
**Tipo:** Feature + Bug + Dados  
**Esforço:** XL  
**Identificado em:** 2026-05-24  
**Referência:** `docs/product/4-research/enunciado.md`

---

## Contexto

O documento `enunciado.md` descreve o modelo conceitual completo de planejamento de obras:
particionamento semanal, política de mobilização, custo de equipamentos por unidade de
locação, estado de ociosidade, e custo por evento de mobilização/desmobilização.

Uma comparação sistemática entre o enunciado e a implementação atual identificou cinco
lacunas que afetam a corretude do custo calculado e a coerência do modelo.

---

## Problemas Observados

### L1 — `rental_unit` ausente no cadastro de equipamentos (§6.1 do enunciado)

O enunciado define três modos de cobrança de aluguel:

```
custo_aluguel_j =
  rental_rate × horas_semana_j        se rental_unit = hora_produtiva
  rental_rate × d_j                   se rental_unit = dia_calendario
  rental_rate / (52/12)               se rental_unit = mes  (proporcional)
```

O sistema atual trata **todos os equipamentos como `hora_produtiva`**. Não existe campo
`rental_unit` no schema de insumo de equipamento.

**Impacto:** Equipamentos cobrados por mês (guindaste, usina de asfalto, britador) ou por
dia (caminhões fora-de-estrada no SICRO) são sistematicamente **subprecificados** quando
o custo mensal/diário é fornecido mas o sistema divide como se fosse horário.

---

### L2 — Estado de equipamento ocioso não rastreado (§6.3 do enunciado)

O enunciado define três estados para um equipamento ao longo do cronograma:

| Estado | Descrição |
|--------|-----------|
| `produtivo` | Semana com atividade alocada e produção efetiva |
| `ocioso_mobilizado` | Mobilizado mas sem atividade (ramp-down, gap entre atividades) |
| `desmobilizado` | Fora do canteiro — sem custo de aluguel |

**Regra:** O custo de aluguel incide nos estados `produtivo` **e** `ocioso_mobilizado`.
Apenas `desmobilizado` zera o custo.

O sistema atual calcula custo de equipamento apenas sobre as semanas com `num_equipes > 0`
no cronograma. Semanas de ramp-down final ou gaps entre atividades reutilizando o mesmo
equipamento **não geram custo de aluguel**.

**Impacto:** Subestimação sistemática do custo de equipamentos em projetos com ramp-down
prolongado ou equipamentos compartilhados com lacunas entre atividades.

---

### L3 — Custo de mobilização/desmobilização como lump sum em vez de por evento (§8 do enunciado)

O enunciado modela mob/desmob como **custo fixo por evento de transição de estado** de
cada recurso (mão de obra ou equipamento):

```
para cada recurso R:
  se estado[j-1] = desmobilizado  AND  estado[j] = mobilizado:
      custo += custo_mobilizacao[R]
  se estado[j-1] = mobilizado     AND  estado[j] = desmobilizado:
      custo += custo_desmobilizacao[R]
```

O principal benefício modelado é: **compartilhar recursos entre atividades não-concorrentes
reduz o número de eventos e, portanto, o custo de mob/desmob**.

O sistema atual tem uma categoria `MOB` nos custos indiretos com `custo_fixo_total`
configurado manualmente. Não há:
- Cadastro de `custo_mobilizacao` e `custo_desmobilizacao` por recurso
- Detecção de transições de estado no cronograma
- Cálculo dinâmico do custo total de mob/desmob a partir das transições reais

**Impacto duplo:**
1. O custo de MOB não reflete o cronograma real — é um número fixo independente de
   quantas mobilizações ocorrem.
2. O otimizador não tem incentivo financeiro para compartilhar recursos entre atividades
   (o benefício do compartilhamento não está monetizado).

---

### L4 — Tipos de precedência SS e FF não implementados como contratos distintos (§4 do enunciado)

O enunciado especifica três tipos de relação de precedência com lag:

| Tipo | Semântica |
|------|-----------|
| FS (Finish-to-Start) | B começa após A terminar |
| SS (Start-to-Start) | B começa `lag` semanas após A iniciar |
| FF (Finish-to-Finish) | B termina `lag` semanas após A terminar |

O `activity_dag` do canônico existe e suporta FS. Os tipos SS e FF com lag não aparecem
como contratos distintos no schema de `EapItem` nem são tratados diferentemente no
solver de cronograma (skill-04).

**Impacto:** Obras com relações SS (ex.: fundação e estrutura que podem se sobrepor) ou FF
(ex.: duas frentes que terminam juntas) são modeladas como FS puro, o que pode gerar
cronogramas mais conservadores ou impossíveis de fechar.

---

### L5 — Dupla aplicação de encargos e BDI de mão de obra sem clareza de escopo (§7 do enunciado)

O enunciado colapsa encargos trabalhistas e BDI em uma fórmula única (fórmula TCU).
O Concilium usa dois mecanismos separados com semânticas distintas:

| Mecanismo | Onde | O que cobre |
|-----------|------|-------------|
| Fator `α` (`ENCARGOS_CLT = 1.777`) | skill-05 (`_alpha()`) | Encargos trabalhistas diretos: INSS, FGTS, férias, 13º, SESI, SENAI, etc. Converte salário mensal bruto em custo real do trabalhador para a empresa |
| `TabelaBdi.mao_obra.bdi_total` | skill-06 | BDI de mão de obra na precificação do serviço: administração central, seguros, risco, lucro, tributos sobre o faturamento |

Esses dois mecanismos cobrem escopos **complementares** e **não se sobrepõem** quando
usados corretamente (encargos = custo do insumo; BDI = markup do serviço). Mas o
enunciado e a documentação atual não tornam isso explícito, gerando risco de:
- Cadastrar um insumo de MO com `preco_unitario` já incluindo encargos **e** aplicar `α`
  em cima (dupla contagem)
- Questionar se um item que já tem `BDI_TCU` embutido no `precos_unitarios_sbdi` deve
  sofrer nova aplicação de BDI no skill-06

---

### L6 — Fórmula exata de ramp-up não auditada (§5 do enunciado)

O enunciado especifica:

```
m_j = round(m_max × j/r)           se j ≤ r    [ramp-up]
    = m_max                         se r < j ≤ n-d
    = round(m_max × (n-j+1)/d)     se j > n-d   [ramp-down]
```

O sistema tem o conceito (curvas_forca, ADR-054, `use_mobilizacao_policy`), mas o código
interno de geração da curva não foi comparado com esta fórmula.

**Risco:** Arredondamentos ou interpolações diferentes podem produzir `m_j` distintos,
afetando o quantitativo produzido em cada semana e o fechamento Σ q_ij = Q_i.

---

## Causa Raiz

O modelo de custo operacional foi desenvolvido de forma incremental (ADR-023, ADR-030,
ADR-038, ADR-053, ADR-054) sem uma especificação formal unificada como guia. O enunciado
de brainstorming (maio/2026) é o primeiro documento que consolida o modelo completo.
As lacunas são as diferenças entre o modelo idealizado e a implementação acumulada.

---

## Objetivo

Alinhar a implementação ao modelo formal descrito no enunciado, priorizando os gaps que
afetam corretude financeira (L1, L2, L3) antes dos que afetam corretude de cronograma
(L4, L6) e documentação/clareza (L5).

---

## Decisão

### D1 — Adicionar `rental_unit` ao schema de equipamento (L1)

Introduzir campo `rental_unit: "hora_produtiva" | "dia_calendario" | "mes"` no schema
de insumo de equipamento (`config/catalogos/.../insumos/equipamento/`).

Atualizar `_calcular_custo_equipamento` em skill-05 para aplicar a fórmula correta:

```python
if rental_unit == "hora_produtiva":
    custo = rental_rate * horas_semana
elif rental_unit == "dia_calendario":
    custo = rental_rate * dias_calendario
elif rental_unit == "mes":
    custo = rental_rate / (52 / 12)   # proporcional por semana
```

Default retrocompatível: `rental_unit = "hora_produtiva"` para equipamentos sem o campo.

### D2 — Rastrear estado de equipamento e cobrar aluguel no estado ocioso (L2)

Introduzir nos `EquipamentoEquipeDireta` um campo `rental_unit` refletindo o cadastro.

Em `_calc_custo_cron` (skill-05), distinguir semanas produtivas de semanas ociosas
mobilizadas para o equipamento, e aplicar o custo de aluguel em ambas.

Critério de `ocioso_mobilizado`: recurso está entre a primeira e a última semana de sua
janela de mobilização, mas `num_equipes = 0` naquela semana específica.

### D3 — Implementar custo de mob/desmob por evento de recurso (L3)

1. Adicionar ao schema de produção/equipe os campos:
   ```
   custo_mobilizacao_mo:   R$ por evento por função de MO
   custo_desmobilizacao_mo: R$ por evento por função de MO
   custo_mobilizacao_eq:   R$ por evento por equipamento
   custo_desmobilizacao_eq: R$ por evento por equipamento
   ```

2. Em skill-05 (ou skill-07), percorrer o cronograma semanal de cada recurso e detectar
   transições `desmobilizado → mobilizado` e `mobilizado → desmobilizado`.

3. Acumular o custo total de mob/desmob por atividade/recurso.

4. Substituir (ou complementar) o campo `custo_fixo_total` da categoria `MOB` em
   indiretos pelo valor calculado dinamicamente.

**Benefício colateral:** O otimizador de cronograma em skill-04 passa a ter incentivo
financeiro mensurável para maximizar compartilhamento de recursos.

### D4 — Adicionar tipos SS e FF ao schema de precedência (L4)

1. Ampliar `EapItem.precedencias` para suportar:
   ```
   { "item_id": "eap-1_3", "tipo": "SS" | "FF" | "FS", "lag": 0 }
   ```

2. Atualizar skill-01 para construir o DAG com semântica correta para SS e FF.

3. Atualizar skill-04 (scheduler) para respeitar janelas de início/fim derivadas do
   tipo de relação.

### D5 — Documentar e validar a separação encargos vs. BDI de MO (L5)

1. Adicionar seção de referência na documentação do skill-05 e skill-06 explicitando
   os dois mecanismos e seus escopos.

2. Criar validação `VAL-PLAN-ENCARGOS-DUPLA` que detecta insumos de MO cujo
   `preco_unitario` parece já incluir encargos (heurística: `preco_unitario ≥ salario × 1.5`)
   e alerta sobre risco de dupla contagem.

### D6 — Auditar e alinhar fórmula de ramp-up ao enunciado (L6)

1. Localizar o código que gera `m_j` para cada semana do cronograma.
2. Comparar com a fórmula `round(m_max × j/r)` do enunciado.
3. Corrigir se diferente; documentar se a variante escolhida for intencional.

---

## Escopo

### Incluído

1. Campo `rental_unit` no schema de equipamento e cálculo de aluguel por modo (D1).
2. Custo de aluguel em estado ocioso (D2).
3. Custo de mob/desmob por evento (D3) — ao menos o cadastro e a detecção de transições.
4. Tipos SS e FF no DAG (D4) — ao menos o schema; o solver pode ser incremental.
5. Documentação e validação de encargos vs. BDI (D5).
6. Auditoria da fórmula de ramp-up (D6).

### Excluído

1. Otimização do scheduler para minimizar custo de mob/desmob (requer D3 concluído primeiro).
2. Suporte a `fuel_unit = km` (caso de uso raro; diferido).
3. Múltiplos modos de mobilização por atividade (ex.: parcial de equipes).

---

## Dependências

| Esta NEP depende de | Motivo |
|---------------------|--------|
| NEP-029 (precificação canônica) | D1 altera como o custo do equipamento entra no PU |
| NEP-030 (injeção mínima honesta) | D3 afeta o custo de MOB que antes era lump sum |

---

## Plano de Implementação

### Fase 1 — Clareza e cadastro (D5, D6, D1 schema)

1. Auditar fórmula de ramp-up; documentar resultado.
2. Esclarecer escopo de `α` vs. `BDI_MO`; adicionar validação de dupla contagem.
3. Adicionar campo `rental_unit` ao schema de equipamento com default retrocompatível.
4. Atualizar catálogo AGIS e outros equipamentos com `rental_unit` correto.

### Fase 2 — Custo de aluguel completo (D1 cálculo, D2)

1. Atualizar `_calcular_custo_equipamento` para usar `rental_unit`.
2. Implementar rastreamento de estado `ocioso_mobilizado` no skill-05.
3. Cobrar aluguel nas semanas ociosas mobilizadas.
4. Regressão benchmark AGIS: δ deve continuar ≤ 5% (fase NEP-030).

### Fase 3 — Mob/desmob dinâmico (D3)

1. Definir schema de custo de mob/desmob por recurso.
2. Implementar detecção de transições no cronograma.
3. Calcular custo total de mob/desmob dinamicamente.
4. Integrar com skill-07 (substituindo/complementando `custo_fixo_total` de MOB).

### Fase 4 — Precedências ricas (D4)

1. Ampliar schema de EapItem para SS e FF com lag.
2. Atualizar skill-01 (DAG) e skill-04 (scheduler).
3. Testes com projetos que usam SS (escavação + estrutura simultâneas).

---

## Critério de Aceite

1. Equipamento com `rental_unit = "mes"` tem custo calculado como `rate / (52/12)` por semana.
2. Semana de ramp-down final de uma atividade gera custo de aluguel para o equipamento
   mesmo sem produção.
3. Dois projetos idênticos exceto pela política de compartilhamento de recursos mostram
   custos de mob/desmob distintos — o que compartilha mais tem custo menor.
4. EAP com relação SS (lag=2 semanas) produz cronograma em que a atividade subsequente
   começa 2 semanas após a anterior, não após o fim.
5. Fórmula de ramp-up auditada e documentada; se diferente do enunciado, variante
   registrada como decisão explícita.

---

## Riscos

1. D2 (equipamento ocioso) aumenta custos calculados — pode elevar δ benchmark inicialmente.
2. D3 requer mudança no schema de dados de referência (`referencia.json`) para incluir
   custos de mob por recurso.
3. D4 (SS/FF) requer mudança no solver de cronograma — risco de regressão em projetos FS.

## Mitigações

1. D2: calibrar catálogo com valores realistas de `rental_unit` antes de rodar benchmark.
2. D3: implementar em modo de leitura (detectar e logar eventos) antes de substituir o
   lump sum.
3. D4: manter suporte a FS como default; SS/FF são opt-in por precedência.

---

## Evidências Técnicas

1. `docs/product/4-research/enunciado.md` — especificação formal do modelo
2. `src/concilium/application/skills/manifests/05-equipes-e-alocacao/_skill_helpers_a.py`
   — `_calcular_custo_equipamento`, `_calc_custo_cron`
3. `src/concilium/application/skills/manifests/04-cronograma-unificado/` — scheduler
4. `src/concilium/domain/models/canonical.py` — `EquipeDireta`, `EapItem`, `activity_dag`
5. `config/catalogos/mendeslobo/insumos/equipamento/` — JSONs de equipamentos sem `rental_unit`
6. `src/concilium/domain/constants.py` — `ENCARGOS_CLT`, `ENCARGOS_PJ`
7. `src/concilium/domain/models/bdi.py` — `TabelaBdi`, `DEFAULT_BDI_TABELA`

---

## Resultado Esperado

Ao final da NEP-031, o custo operacional calculado pelo pipeline reflete:
1. O modo de cobrança real de cada equipamento (hora/dia/mês)
2. O custo de equipamentos mobilizados mesmo em semanas sem produção
3. O custo de mobilização e desmobilização derivado das transições reais do cronograma
4. Relações de precedência SS e FF além de FS
5. Clareza documentada sobre a separação entre encargos trabalhistas e BDI de serviço
