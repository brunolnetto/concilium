# ADR-132 — Regime de Revezamento, Turnos Noturnos e Precificação de Equipamentos por Atividade

**Status:** Implementado ✅ _(2026-06-18)_  
**Data:** 2026-06-18  
**Contexto:** MendesLobo Construtora — Concilium  
**Depende de:** ADR-029 (calibração C_ref), ADR-091 (n_frentes), ADR-106 (lifecycle equipe)  
**Relacionado:** NEP-029, NEP-031 L1 (rental_unit), ADR-034 (encargos CLT)

---

## 1. Contexto

### 1.1 Problema: Equipes de Obra em Revezamento Contínuo (12×36)

Obras de mineração, indústria e infraestrutura crítica operam **24 horas por dia** com escalas de
revezamento. A CLT regula estas situações em dois regimes distintos:

| Regime | Jornada | Adicional | Referência Legal |
|--------|---------|-----------|-----------------|
| **Turno fixo diurno** | 8h/dia, 44h/sem | — | CLT art. 58 |
| **Turno fixo noturno** | 8h/dia, 44h/sem | ≥ 20% sobre hora diurna | CLT art. 73 |
| **Turnos ininterruptos de revezamento** | 6h/dia máx. (ou 8h por ACT) | + adicional noturno proporcional | CF art. 7º XIV, CLT art. 611-A |
| **Escala 12×36** | 12h trabalho / 36h descanso | + adicional noturno se parte da jornada cair entre 22h–5h | OJ-SBDI-360 TST |

Na escala **12×36** amplamente utilizada em obras de Serra Verde:
- Equipe **diurna** (ex.: 7h–19h): encargos CLT padrão, sem adicional noturno.
- Equipe **noturna** (ex.: 19h–7h): CLT art. 73 — adicional de ≥ 20% sobre a hora diurna, redução
  ficta da hora para 52,5 minutos (OJ-TST-360), e encargos sobre o salário majorado.

O custo mensal por pessoa difere entre turnos para o **mesmo** código de função P00XX:
- P0046 diurno: R$ 7.658,77/pessoa-mês
- P0046 noturno: R$ 8.501,16/pessoa-mês (+11% ≈ adicional 20% × proporcionalidade da jornada noturna)

### 1.2 Problema: Proliferação de Insumos de Equipamento por Fase

Equipamentos alugados têm preços que variam por fase de obra (descontos por volume à medida que a
operação escala). O modelo anterior gerava **4 variantes** por código de equipamento:

```
SV-EQ1-E0027.json   R$138,89/h  (50.000/mês ÷ 360h)
SV-EQ2-E0027.json   R$104,17/h  (37.500/mês ÷ 360h)
SV-EQ3-E0027.json   R$  84,03/h  (30.250/mês ÷ 360h)
SV-EQ4-E0027.json   R$  69,79/h  (25.125/mês ÷ 360h)
```

Para 8 tipos de equipamento × 4 equipes = **32 arquivos de insumo** com código artificial
(`SV-EQ1-*`) que não corresponde a nenhum código de catálogo externo (SICRO, SINAPI, planilha).

---

## 2. Decisões

### D1 — Variantes de Turno como Insumos Separados de Mão de Obra

**Decisão:** Cada função (código P00XX) recebe dois insumos distintos no catálogo:
- `SV-P0046-D` — taxa horária all-in do turno **diurno**
- `SV-P0046-N` — taxa horária all-in do turno **noturno**

**Formato:** `unidade: "h"` com `preco_unitario = custo_total_mensal_planilha / 360h`.

O campo `preco_unitario` já inclui: salário base + HE 25% + alimentação + encargos CLT completos
(INSS, FGTS, férias, 13°, SESI/SENAI, seguro acidente). O `pu_calculator.calcular_pu()` usa a taxa
diretamente **sem aplicar** fator alpha adicional (convenção `unidade = "h"` estabelecida no ADR-034).

**Racionalidade:**
- Mantém rastreabilidade direta com a linha correspondente na planilha da obra.
- Evita lógica condicional de turno no engine (seria necessário saber o horário de início da jornada).
- Permite que auditorias verifiquem a conformidade CLT art. 73 diretamente pelo insumo.
- O impacto do adicional noturno é capturado automaticamente no custo total: o engenheiro de
  planejamento define a proporção `num_pessoas-D` vs `num_pessoas-N` na composição.

### D2 — Normalização por Frente (n_frentes)

**Decisão:** A composição da produção (`composicao_padrao_equipe`) representa **1 frente** do total de
`n_frentes` simultâneas (ADR-091). Cada campo `num_pessoas` e `num_unidades` divide a contagem total
pelo número de frentes:

```
num_pessoas_por_frente = total_pessoas / n_frentes
```

**Exemplo (EQ1, n=3 frentes, diurno P0046):**
- Total planilha: 12 operadores diurnos
- Por frente: 12 / 3 = **4 operadores-D**

A `pu_calculator.calcular_pu()` computa: `custo_mo_h = 21.275 R$/h × 4 = 85.10 R$/h/frente`.
O PU final: `(885.10 + custo_eq_h) / vh_por_frente` = resultado correto para 1 frente.

O custo total real do projeto = PU × Q (independente de n_frentes, pois ambos escalam juntos).

### D3 — Precificação de Equipamentos por Atividade via `preco_h_unitario`

**Decisão:** Equipamentos no catálogo permanecem com um **único insumo por tipo** (ex.: `E0027`).
O preço de aluguel **por atividade** é declarado diretamente no campo `preco_h_unitario` (R$/h)
na entrada de equipamento da composição `composicao_padrao_equipe`:

```json
{
  "equip_id": "E0027",
  "num_unidades": 2.0,
  "consumo_litros_hora": 0,
  "preco_h_unitario": 138.8889,
  "custo_mobilizacao": 6500.0,
  "custo_desmobilizacao": 6500.0
}
```

O campo armazena o valor **já convertido para R$/h** (= aluguel_mensal / horas_efetivas_regime),
evitando ambiguidade sobre qual `horas_mes` usar nas diferentes chamadas do pipeline.

O `pu_calculator.calcular_pu()` prioriza `preco_h_unitario` do entry de composição sobre
`preco_unitario` do insumo de catálogo:

```python
preco_h_override = eq.get("preco_h_unitario")
if preco_h_override is not None and float(preco_h_override) > 0:
    preco_h = float(preco_h_override)   # já em R$/h, sem divisão por horas_mes
else:
    preco_h = _converter_rental_unit(preco_raw, rental_unit, ...)  # fallback catálogo
```

O `skill-05._processar_equipamentos_item` converte de volta para `custo_mensal` usando
as horas efetivas do regime (`horas_dia × dias_uteis`) do projeto em execução:

```python
_preco_h_comp = e.get("preco_h_unitario")
_custo_mensal_comp = float(_preco_h_comp) * horas_dia * dias_uteis if _preco_h_comp else None
custo_mensal_override = equip_custom.get("custo_mensal") or _custo_mensal_comp
```

**Racionalidade:**
- O preço de aluguel é um dado **do contrato/proposta**, não uma propriedade permanente do equipamento.
  Um E0027 em Serra Verde (fase 1) custa R$50.000/mês; o mesmo modelo em Serra Verde (fase 4) custa
  R$25.125/mês por desconto de volume. Ambas as situações **são o mesmo equipamento** catalogado.
- Armazenar em R$/h elimina ambiguidade: `pu_calculator` usa `params.horas_mes=208h` (6×1 padrão);
  skill-05 usa `horas_dia × dias_uteis` do regime real. Ambos convergem sem divisão errada.
- Elimina a proliferação de variantes `SV-EQ*-E*` (32 arquivos → 0).
- Preserva rastreabilidade: o campo `preco_h_unitario` é derivável da planilha por `aluguel_mensal / horas_regime`.
- O catálogo de insumos reflete propriedades **do equipamento** (consumo padrão, manutenção, desconto
  base de mercado); o contrato/proposta reflete propriedades **do acordo comercial**.

### D4 — Mob/Demob como Custo de Transição por Composição

**Decisão:** Os campos `custo_mobilizacao` e `custo_desmobilizacao` são declarados nas entradas de
composição (funcoes e equipamentos), não nos insumos:

- **Pessoa:** R$800 por trabalhador (transporte pessoal, one-way, baseado em 500 km × R$1,60/km)
- **Equipamento:** R$6.500 por unidade (transporte em carreta, 500 km × R$13/km, one-way)

O `skill-05._calc_custo_mob_desmob` usa esses valores ao detectar transições de frente ativas no
cronograma (funções `_count_transitions` + `_accum_mob_costs_list`). Mob/demob intermediário
(late evoke / early dismissal entre fases) emerge naturalmente do RCPSP quando atividades têm
sobreposições parciais de equipes.

---

## 3. Consequências

### 3.1 Impacto no Catálogo
| Antes | Depois |
|-------|--------|
| 32 insumos `SV-EQ[1-4]-E[0027..0014]` | 0 insumos per-equipe de equipamento |
| Código artificial sem referência externa | Código canônico `E0027` linkado ao catálogo |
| Variação de preço duplicada em 4 arquivos | Variação declarada 1× no PROD, auditável por fase |
| MO: 1 insumo bundle por equipe | MO: 2 insumos (D/N) × 10 funções = 20 arquivos, reutilizáveis em qualquer obra 12×36 |

### 3.2 Impacto no pu_calculator
Novo caminho de resolução de preço em `calcular_pu()`:
1. Se `eq.preco_h_unitario > 0` → `preco_h = preco_h_unitario` (já R$/h, sem divisão)
2. Senão → fallback para `_converter_rental_unit(ins.preco_unitario, rental_unit, ...)`

Como `preco_h_unitario` já está em R$/h, não há dependência de `params.horas_mes`. A consistência
com o skill-05 é garantida porque ambos usam o mesmo valor horário sem conversão intermediária.

### 3.3 Impacto nos Gráficos de Recursos
Com insumos individuais (D/N separados, equipamentos com código canônico):
- `hist_mao_obra.png`: mostra breakdown por função (P0046-D, P0046-N, P0048-D, etc.)
- `hist_equipamentos.png`: mostra breakdown por equipamento (E0027, E0035, E0021, etc.)
- `linha_recursos_tempo.png`: timeline com todos os tipos de recurso distintos

### 3.4 Limitações e Trabalho Futuro
- O adicional noturno proporcional (quando a jornada 12×36 cruza 22h) não é modelado automaticamente
  — o engenheiro deve usar a taxa all-in correta (`SV-P00XX-N`) para funções noturnas.
- Projetos com turnos variáveis (ex.: parte do ano diurno, parte noturno) requerem insumos adicionais
  ou composições por sub-período.
- A generalização para outros regimes (6×1 noturno, 24×72) segue o mesmo padrão D1: criar variantes
  `SV-P00XX-{TURNO}` com a taxa all-in da planilha correspondente.

---

## 4. Exemplos

### 4.1 Composição Serra Verde EQ1 (extrato)
```json
{
  "composicao_padrao_equipe": {
    "funcoes": [
      {"funcao_id": "SV-P0046-D", "num_pessoas": 4.0, "custo_mobilizacao": 800, "custo_desmobilizacao": 800},
      {"funcao_id": "SV-P0046-N", "num_pessoas": 2.0, "custo_mobilizacao": 800, "custo_desmobilizacao": 800},
      {"funcao_id": "SV-P0048-D", "num_pessoas": 2.0, "custo_mobilizacao": 800, "custo_desmobilizacao": 800},
      {"funcao_id": "SV-P0048-N", "num_pessoas": 2.0, "custo_mobilizacao": 800, "custo_desmobilizacao": 800}
    ],
    "equipamentos": [
      {"equip_id": "E0027", "num_unidades": 2.0, "preco_h_unitario": 138.8889,
       "consumo_litros_hora": 0, "custo_mobilizacao": 6500, "custo_desmobilizacao": 6500},
      {"equip_id": "E0035", "num_unidades": 1.0, "preco_h_unitario": 266.6667,
       "consumo_litros_hora": 0, "custo_mobilizacao": 6500, "custo_desmobilizacao": 6500}
    ]
  }
}
```

### 4.2 PU derivado (por frente, EQ1)
```
custo_mo_h  = (4×21.275 + 2×23.614 + 2×26.911 + 2×29.870 + ...) = 442.96 R$/h
custo_eq_h  = (2×138.89 + 1×266.67 + ...) = 1074.04 R$/h
total_h     = 1517.00 R$/h
vh          = 279.33 m³/h
PU          = 5.43 R$/m³  ≈ planilha 5.44 ✓
```
