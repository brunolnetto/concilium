# ADR-021 — Plan Space Explorer: Repair e Otimização de Margem

**Status:** Implementado  
**Data:** 2026-05-03  
**Data Implementado:** 2026-05-04  
**Implementadores:** models/canonical.py (Lever, RepairPath, RepairStep, PlanSpaceResult), skills/14-plan-space-explorer  
**Contexto:** MendesLobo Construtora — Concilium

---

## Problema

Quando o orçamento chega a AMARELO ou VERMELHO, o `13-replan-advisor` gera sugestões
*independentes* — cada uma move um único parâmetro isoladamente. Isso ignora dois fatos:

1. **Efeitos cruzados**: reduzir duração reduz indiretos mas pode aumentar custo direto
   (mais equipes trabalhando em ritmo acelerado); expandir pool elimina BUY mas exige
   mobilização. As melhorias interagem.

2. **Espaço combinatorial**: existe um conjunto de sequências de intervenção que levam
   ao VERDE com custo mínimo. O `13-replan-advisor` não explora esse espaço.

Simetricamente, para planos VERDE:

3. **Oportunidade inexplorada**: um plano VERDE pode ter margem abaixo do máximo
   possível. Existe uma fronteira Pareto de (margem, confiança-prazo, folga-recurso)
   que o engenheiro pode navegar.

---

## Decisão

Nova skill `14-plan-space-explorer` que consome o estado canônico pós-06A e produz:

- **Para AMARELO/VERMELHO**: `RepairPath` — sequência greedy de intervenções ordenadas
  por `delta_margem / custo_aplicacao_normalizado` até cruzar `faixa_alvo.min`.
- **Para VERDE**: `OportunidadeVerde` list — intervenções de melhoria ordenadas por
  `margem_adicional_estimada`, classificadas por risco.

### Levers (intervenções parametrizadas)

| Tipo | Checkpoint | Origem dos dados | Estimativa delta_margem |
|------|------------|-----------------|------------------------|
| `EXPAND_POOL` | `01A-declarar-recursos` | `resultado_reconciliado.delta_custo_total` | `delta_custo × 0.80 / venda` |
| `REDUCE_DURATION` | `02-cronograma` | `indiretos`, `cronograma.data_termino` | `(Δsemanas / semanas_total) × indiretos_total / venda` |
| `ADD_TEAMS` | `03-equipes-diretas` | A+ activities (09) | `0.10 × cost_share_A+ × 0.20 × venda_share` |
| `REVIEW_BDI` | `05-indiretos` | `resultado.custo` | heurística: 0.015–0.025 de margem |

### Algoritmo de Repair (greedy)

```
levers ← build_levers(canonical)
levers ← sort by ratio_beneficio DESC
margem_atual ← margem_entrada
passos ← []
for lever in levers:
    if margem_atual >= faixa_alvo.min: break
    passo = RepairStep(lever, margem_acumulada_apos = margem_atual + lever.delta_margem)
    margem_atual += lever.delta_margem
    passos.append(passo)
viavel = margem_atual >= faixa_alvo.min
```

### Otimização de VERDE (scan de sensibilidade)

Para cada lever, computar `margem_adicional_estimada` assumindo plano já VERDE.
Classificar risco por confiança do lever:
- BAIXO: confiança ALTA + tipo REDUCE_DURATION ou EXPAND_POOL
- MEDIO: confiança MEDIA, qualquer tipo
- ALTO: confiança BAIXA ou tipo ADD_TEAMS (risco de produtividade)

Retornar lista ordenada por `margem_adicional_estimada DESC`.

---

## Modelo Canônico

```python
class Lever(BaseModel):
    tipo: Literal["EXPAND_POOL", "REDUCE_DURATION", "ADD_TEAMS", "REVIEW_BDI"]
    checkpoint_skill: str
    parametros: dict
    delta_margem_estimado: float
    custo_aplicacao: float
    ratio_beneficio: float
    confianca: Literal["ALTA", "MEDIA", "BAIXA"]
    justificativa: str

class RepairStep(BaseModel):
    ordem: int; lever: Lever
    margem_acumulada_apos: float; status_apos: StatusMargem

class RepairPath(BaseModel):
    viavel: bool; passos: list[RepairStep]
    margem_projetada: float; status_projetado: StatusMargem

class OportunidadeVerde(BaseModel):
    lever: Lever; margem_adicional_estimada: float
    risco: Literal["BAIXO", "MEDIO", "ALTO"]

class PlanSpaceResult(BaseModel):
    status_entrada: StatusMargem; margem_entrada: float
    repair_path: RepairPath | None
    oportunidades: list[OportunidadeVerde]
```

Campo em `CanonicalModel`: `plan_space_result: PlanSpaceResult | None = None`

---

## Limites e Pressupostos

- As estimativas são **heurísticas de primeira ordem** — não substituem re-execução
  real da pipeline. O RepairPath indica *qual checkpoint usar* com `concilium replan plan`.
- `EXPAND_POOL` assume que 80% do delta_custo_reconciliado pode ser evitado com
  pool próprio (20% residual = mobilização e manutenção).
- `REDUCE_DURATION` assume indiretos proporcionais ao tempo (válido para ADM/TOP/LAB).
- `ADD_TEAMS` tem confiança BAIXA por padrão — ganho de prazo não é linear com equipes.
- `REVIEW_BDI` é sempre gerado como oportunidade de última instância, confiança BAIXA.

---

## Validações

| Código | Skill | Significado |
|--------|-------|-------------|
| VAL-PSE-01 | 14 | `plan_space_result` populado |
| VAL-PSE-02 | 14 | `repair_path.viavel` coerente com levers disponíveis |
| VAL-PSE-PRECONDICAO | 14 | `resultado` ou `resultado_reconciliado` presente |

## Definition of Done

- [x] `Lever` model: `tipo`, `checkpoint_skill`, `parametros`, `delta_margem_estimado`, `custo_aplicacao`, `ratio_beneficio`, `confianca`, `justificativa`
- [x] `RepairStep` model: `ordem`, `lever`, `margem_acumulada_apos`, `status_apos`
- [x] `RepairPath` model: `viavel`, `passos`, `margem_projetada`, `status_projetado`
- [x] `OportunidadeVerde` model: `lever`, `margem_adicional_estimada`, `risco`
- [x] `PlanSpaceResult` model: `status_entrada`, `margem_entrada`, `repair_path`, `oportunidades`
- [x] `plan_space_result: PlanSpaceResult | None` field in `CanonicalModel`
- [x] Skill `14-plan-space-explorer` implemented
- [x] Greedy repair algorithm: levers sorted by `ratio_beneficio DESC`; stops when `margem >= faixa_alvo.min`; marks `viavel` based on reachability
- [x] VERDE optimization: sensitivity scan producing `OportunidadeVerde` list sorted by `margem_adicional_estimada DESC`, classified by risk
- [x] Four lever types implemented: `EXPAND_POOL`, `REDUCE_DURATION`, `ADD_TEAMS`, `REVIEW_BDI`
- [x] VAL-PSE-01: `plan_space_result` populated
- [x] VAL-PSE-02: `repair_path.viavel` coherent with available levers
- [x] VAL-PSE-PRECONDICAO: `resultado` or `resultado_reconciliado` present
