# ADR-080: Custo Diferenciado de Permanência — Mobilização Tardia por Instância, Taxa Ociosa por Componente e Desmobilização Antecipada Efetiva

**Status:** Supersedido por [ADR-085](ADR-085-custo-instancial-composicional-temporal.md)
**Data:** 2026-05-26
**Autores:** Bruno Peixoto / Concilium
**Dependências:** ADR-071, ADR-073, ADR-077, ADR-079

> **Nota de supersessão (2026-05-29):** O ADR-085 absorve e generaliza este ADR. As três
> mecânicas aqui propostas (A. mobilização tardia, B. taxa ociosa, C. desmobilização antecipada
> efetiva) nunca foram implementadas no cálculo de custo — apenas os campos de modelo
> `mobilizacao_por_instancia` e `desmob_antecipada_aplicada` foram pré-adicionados. O ADR-085
> implementa essas mecânicas e generaliza a "taxa ociosa" escalar (§B) para **taxa ociosa por
> componente** (MO integral por CLT, EQ a taxa de locação reduzida, combustível e material zerados),
> além de conectar o custo instancial à base bottom-up de precificação (BDI). Use o ADR-085 como
> fonte de verdade.

---

## 1. Contexto

### 1.1 O que o modelo atual faz

O ADR-071 estabeleceu o modelo de contrato de pool. A fórmula central de custo é:

```
custo_total_contrato = quantidade_contratada × custo_unit_semanal × semanas_contrato
```

Onde:
- `quantidade_contratada` = pico de demanda simultânea observada no cronograma
- `custo_unit_semanal` = média ponderada de `EquipeDireta.custo_total / machine_weeks` — inclui
  mão-de-obra CLT + aluguel de equipamento + combustível
- `semanas_contrato` = da semana da **primeira atividade** à semana da **última atividade**
  de qualquer atividade do tipo de recurso (span monolítico para todas as unidades do pool)

O ADR-079 calculou a economia de desmobilização antecipada (`InstanciaRecurso.economia_desmobilizacao_antecipada`)
e armazenou nos campos de diagnóstico, **mas não alterou `custo_total_contrato`**. Portanto o N4
(`bridge_analysis.nivel_4_operacional = Σ EquipeDireta.custo_total`) continua superestimado.

### 1.2 Três lacunas estruturais

| # | Lacuna | Efeito em N4 |
|---|---|---|
| L1 | Todas as `quantidade_contratada` unidades do pool são contratadas desde `semana_inicio`, mesmo que algumas só sejam necessárias muito depois (**ausência de mobilização tardia**) | Sobrecarrega N4 com semanas de contrato desnecessárias para instâncias de uso tardio |
| L2 | `custo_unit_semanal` (taxa ativa plena: salário + aluguel + combustível) é cobrado de **standby** entre atividades e no trailing (**ausência de taxa ociosa diferenciada**) | Equipamento parado custa o mesmo que equipamento trabalhando |
| L3 | A economia de desmobilização antecipada calculada pelo ADR-079 não reduz `custo_total_contrato` (**desmobilização antecipada apenas diagnóstica**) | N4 inclui semanas de trailing standby que deveriam ser eliminadas |

### 1.3 Por que mão-de-obra e equipamento diferem

A legislação trabalhista brasileira impede "taxa reduzida" para mão-de-obra CLT durante
ociosidade: o salário é idêntico quer o trabalhador esteja ativo ou aguardando. A rescisão
antecipada tem custo próprio (aviso prévio, multa FGTS 40%, parcelas proporcionais).

Equipamentos alugados, por outro lado, frequentemente possuem:
- **Taxa ativa** (`custo_unit_semanal`): inclui operador, combustível, desgaste, manutenção
- **Taxa de standby/locação mínima** (`custo_idle_semanal_unit`): apenas aluguel do ativo
  físico, sem operador nem combustível — tipicamente 20–40% da taxa ativa

`custo_idle_semanal_unit` (disponível em `rcpsp_spec.resource_costs`) captura exatamente
essa taxa de standby de equipamento. O ADR-079 §A documentou que o campo já existe,
mas é usado apenas para o `custo_standby` diagnóstico das instâncias.

---

## 2. Decisão

### A. Mobilização Tardia por Instância (`late_mobilization`)

Substituir o span monolítico do contrato por spans individuais por instância.
Cada unidade `i` do pool passa a ter seu próprio ciclo de vida:

```
semana_mobilizacao_i  = primeira semana em que a instância i é atribuída a uma atividade
semana_desmobilizacao_i = última semana ativa + semanas_retencao_i (ver §B e §C)
```

O custo da instância `i` é computado com base em `semanas_mobilizacao_i .. semana_desmobilizacao_i`,
não no span do contrato inteiro.

**Efeito prático (exemplo AGIS):** ATERRO-04 está ocioso durante as semanas 1–35 servindo
apenas eap-1_10 nas semanas 36–41. Com mobilização tardia, seu contrato começa na semana 36,
eliminando 35 semanas de custo de contrato para essa instância.

**Novo campo em `RecursoContrato`:**
```python
mobilizacao_por_instancia: dict[int, str] = {}
# instancia_numero → semana_iso de início do contrato individual
```

Preenchido em `_build_instancias_recurso` (após a atribuição gulosa de slots), usando
`instance_active_weeks[i][0]` como `semana_mobilizacao`.

### B. Taxa Ociosa Diferenciada por Componente (`idle_rate_split`)

Quando `custo_idle_semanal_unit > 0` está disponível no `rcpsp_spec.resource_costs`,
reescrever o custo do pool por instância como:

```
custo_instancia_i =
    custo_unit_semanal × machine_weeks_ativos_i         ← taxa plena (MO + EQ + comb)
  + custo_idle_semanal_unit × machine_weeks_standby_i   ← apenas EQ (sem MO, sem comb)
  + c_mob + c_demob                                     ← mob/demob uma vez por ciclo
```

Onde `machine_weeks_standby_i` = semanas dentro do span `[mob_i, demob_i]` sem atividade
atribuída (gaps intermediários entre atividades na mesma instância).

**Observação sobre mão-de-obra:** `custo_idle_semanal_unit` deve ser parametrizado como
o custo de **manter o equipamento fisicamente locado sem operar**. Quando o operador CLT
permanece no projeto durante gaps, seu salário deve integrar `custo_unit_semanal` e não
pode ser reduzido. Se o operador é temporariamente realocado ou dispensado durante o gap,
o custo de rescisão/contratação deve ser acrescido separadamente — fora do escopo deste ADR.

**Compatibilidade:** quando `custo_idle_semanal_unit = 0`, o comportamento recai no cálculo
atual (`custo_unit_semanal × todas_as_semanas`), preservando retrocompatibilidade.

### C. Desmobilização Antecipada Efetiva (`early_demob_apply`)

Aplicar a economia calculada pelo ADR-079 diretamente ao custo da instância.

Para a instância `i`, se `economia_desmobilizacao_antecipada_i > 0`:

```
semana_desmobilizacao_efetiva_i = semana_ultima_atividade_i + 1
custo_trailing_evitado_i        = custo_idle × trailing_weeks_i − c_demob_unit
```

A instância é "desmobilizada" na semana logo após sua última atividade, eliminando o
custo de standby trailing e incorrendo apenas `c_demob_unit` (transporte de retorno).

Quando a desmob antecipada é aplicada:
```
semana_desmobilizacao_i = semana_ultima_atividade_i  (contrato encerra na semana seguinte)
custo_standby_trailing_i = 0
custo_desmob_i           = c_demob_unit  (em vez de nunca incorrer em desmob explícita)
```

**Novo campo em `InstanciaRecurso`:**
```python
desmob_antecipada_aplicada: bool = False
# True quando economia > 0 e o custo foi efetivamente reduzido no cálculo
```

---

## 3. Modelo Revisado de Custo de Contrato

O custo total do contrato de um tipo de recurso `r` passa a ser:

```
custo_total_contrato_r = Σᵢ∈pool [
    custo_unit_semanal × Σₛ∈S_ativo_i  (1)
  + c_idle             × Σₛ∈S_standby_i (2)
  + c_mob                               (3)
  + c_demob_efetivo_i                   (4)
]
```

Onde:
- `S_ativo_i` = semanas com atividade atribuída à instância `i`
- `S_standby_i` = semanas dentro de `[mob_i, demob_efetivo_i]` sem atividade
- `c_demob_efetivo_i` = `c_demob` se desmob antecipada aplicada, else `0`
  (instâncias sem early demob não são desmobilizadas explicitamente — custo embutido no contrato)

### 3.1 Atribuição às atividades

A atribuição proporcional (fração por machine-weeks) permanece como mecanismo de distribuição:

```
frac_i_j = machine_weeks(item_j, instancia_i) / Σₖ machine_weeks(item_j, instancia_k)
custo_attr_j = Σᵢ custo_instancia_i × frac_i_j
```

Isso preserva a interface do `atribuicao: {item_id: (custo_atribuido, tipo_id, fracao)}`
existente no ADR-071.

### 3.2 Ordenação de cálculo

O novo cálculo requer que `_build_instancias_recurso` (ADR-077) seja executado
**antes** da finalização de `custo_total_contrato` em `_build_contratos_recurso`. 
A sequência atual já satisfaz essa dependência (instâncias são construídas dentro do
mesmo loop de `_build_contratos_recurso`), mas o custo do contrato agora deve ser
calculado **após** a atribuição de instâncias, não antes.

Refactoring necessário:
1. Calcular `custo_instancia_i` por instância após atribuição de slots
2. Somar para obter `custo_total_contrato_r`
3. Distribuir para atividades via machine-weeks (mantido)

---

## 4. Impacto Estimado (caso AGIS, iter-3 como baseline)

| Melhoria | Instâncias afetadas | Redução estimada em N4 |
|---|---|---|
| Mob tardia — ATERRO-04 (36w antes do uso) | ATERRO-04 | ~R$ 270k |
| Mob tardia — ESC-3CAT-03 a 06 (ativas só na sem. 33+) | 4× ESC-3CAT | ~R$ 1.5M |
| Idle rate p/ standby ESC-3CAT (inter-atividade) | todos ESC-3CAT | ~R$ 1.2M (estimado) |
| Desmob antecipada efetiva (ADR-079 economy aplicada) | ATERRO-04, 4× ESC-3CAT | R$ 665.5k |
| **Total estimado** | | **~R$ 3.6M** |

Bridge projetada: **31.8% → ~26.5%** (≈ limiar AMARELO/VERMELHO de 25%)

---

## 5. Parâmetros de Entrada Novos em `rcpsp_spec.resource_costs`

Nenhum campo novo é necessário. Os campos existentes do ADR-079 são suficientes:

```json
"resource_costs": {
  "ESC-3CAT": {
    "custo_mob_unit": 80000.0,       ← custo de mobilização por unidade
    "custo_demob_unit": 40000.0,     ← custo de desmobilização por unidade
    "custo_idle_semanal_unit": 12000.0,  ← taxa de standby/locação mínima (novo uso efetivo)
    "unidade_faturamento": "dia_cal"
  }
}
```

O campo `custo_idle_semanal_unit` passa de "usado apenas para `gap_max` e diagnóstico"
para "usado efetivamente no cálculo de custo de contrato".

---

## 6. Validações

| Código | Condição | Status |
|---|---|---|
| `VAL-MOB-TARDIA-OK` | Para cada instância, `semana_mobilizacao ≥ semana_inicio_contrato_legado` | INFO |
| `VAL-IDLE-SPLIT-OK` | `c_idle > 0` e `c_idle < custo_unit_semanal` | INFO |
| `VAL-IDLE-SPLIT-WARN` | `c_idle ≥ custo_unit_semanal` (idle ≥ ativo — parametrização suspeita) | AVISO |
| `VAL-DESMOB-EFETIVA-OK` | `economia_desmob > 0` e `desmob_antecipada_aplicada = True` para instâncias elegíveis | INFO |
| `VAL-CUSTO-CONTRATO-POSITIVO` | `custo_total_contrato_r > 0` após refactoring | ERRO |

---

## 7. Rejeições

### R1 — Reduzir salário da mão-de-obra durante standby

Incompatível com CLT brasileira. O salário mensal é obrigatório independente de ociosidade.
Eventuais remanejos de trabalhadores entre frentes (e seus custos operacionais) ficam fora
do escopo deste modelo de pool.

### R2 — Calcular custo de rescisão CLT para early dismissal de mão-de-obra

O custo de rescisão (aviso prévio, multa FGTS, parcelas proporcionais) depende de tempo
de empresa, categoria sindical e negociação — dados não presentes no catálogo atual.
Modelar apenas equipamento (aluguel) via ADR-080; rescisão CLT é candidata a ADR futuro.

### R3 — Span de contrato por instância via campo explícito em `rcpsp_spec`

Exigiria que o planejador especificasse manualmente as semanas de início e fim de cada
instância, duplicando trabalho com o cronograma RCPSP. A derivação automática a partir de
`_build_instancias_recurso` é semanticamente superior e sem custo de especificação.

---

## 8. Testes Planejados

| Classe | Nº testes | O que cobre |
|---|---|---|
| `TestMobilizacaoTardia` | 6 | mob_i posterior ao span_inicio; custo reduzido para instâncias tardias |
| `TestIdleRateSplit` | 8 | custo_ativo × taxa_plena + standby × c_idle; fallback quando c_idle=0 |
| `TestDesmobEfetivaAplicada` | 6 | custo_trailing eliminado; c_demob adicionado; flag desmob_antecipada_aplicada |
| `TestAtribuicaoAposRefactoring` | 5 | frac e custo_attr preservam semântica do ADR-071 após novo custo_total |
| `TestCompatibilidadeRetroativa` | 4 | sem resource_costs → comportamento idêntico ao ADR-079 |

Total planejado: **29 testes**.

---

## 9. Relacionados

[[adr071-resource-contract-model]] [[adr073-instance-matching-perpetuacao]]
[[adr077-recurso-instancial-utilizacao]] [[adr079-ativacao-economica-compartilhamento]]
