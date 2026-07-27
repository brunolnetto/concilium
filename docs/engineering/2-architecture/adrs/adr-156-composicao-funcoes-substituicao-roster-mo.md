# ADR-156 — Composição de Funções por Tipo de Pool: Substituição de Custo Real de MO (Fase 1 — Sem Wiring)

**Status:** Proposta
**Data:** 2026-07-26
**Contexto:** MendesLobo Construtora — Concilium
**Dependências:** ADR-154 (Roster Real de Mão-de-Obra), ADR-046 (RCPSP — tipos de equipe fungíveis), ADR-071 (Resource Contract Model)

---

## Contexto

### Problema

P1. ADR-154 entregou `custo_real_mo_total(roster, funcao_id, ...)`, mas conectá-la diretamente a `RecursoContrato.custo_unit_semanal_mo` (como inicialmente planejado) é **inseguro no caso geral**: `RecursoContrato.tipo_id` não representa uma função de MO isolada — é um hash (`_tipo_recurso_fungivel`, `_pool_contrato_construcao.py:196-223`) da **composição inteira de uma equipe**, que pode combinar múltiplas funções de MO **e** equipamentos sob o mesmo `tipo_id`. Confirmado em fixture real: `ESC-3CAT` (benchmark AGIS) é uma equipe mista MO+EQ; `CPU-TERRA-ATI-016` combina 3 funções de MO (`MO-OPER-ESCAV`, `MO-MOTOR-CAM-BASC`×5, `MO-ENCARREG-TERRA`) + 2 equipamentos sob um único `tipo_id`.

P2. Substituir `custo_unit_semanal_mo` de um `RecursoContrato` misto por um roster de **uma única** função corromperia o resultado — o valor calibrado cobre várias funções agregadas, e a informação de quais funções compõem o `tipo_id` (e em que quantidade cada uma) existe apenas dentro do hash SHA1, nunca persistida em `RecursoContrato`.

P3. Esta ADR resolve **só a Fase 1**: expor a composição de funções por trás de cada `tipo_id` (novo campo) e uma função de substituição pura, testada isoladamente, com verificação de cobertura (recusa substituir se o roster não cobre todas as funções da composição com efetivo suficiente). **Não** conecta nada ao orquestrador real de skill-05 (`skill.py`/`instancias.py`) nem adiciona campo em `Escopo` — isso é ADR-157, deliberadamente separada para não misturar validação de lógica pura com risco de tocar o pipeline financeiro ao vivo.

---

## Decisão

### D1 — Novo campo `RecursoContrato.composicao_funcoes_mo: dict[str, int] = {}`

```python
# RecursoContrato ganha:
composicao_funcoes_mo: dict[str, int] = Field(default_factory=dict)
# {funcao_id: num_pessoas} por UMA instância de equipe deste tipo (não multiplicado
# por quantidade_contratada). Default {} preserva comportamento — populado só quando
# o builder (ADR-157, futuro) decidir escrever; nenhum consumidor existente quebra.
```

### D2 — Função pura `extrair_composicao_funcoes_mo`

```python
def extrair_composicao_funcoes_mo(composicao: ComposicaoPadraoEquipe) -> dict[str, int]:
    """Extrai {funcao_id: num_pessoas} de uma ComposicaoPadraoEquipe do catálogo.

    Mesma informação usada por _tipo_recurso_fungivel para gerar o hash do tipo_id
    (_pool_contrato_construcao.py:196-223) — mas aqui exposta como função standalone,
    sem tocar o pipeline real. Funções sem funcao_id são ignoradas.
    """
```

### D3 — Função pura `aplicar_roster_custo_real_mo` (com verificação de cobertura)

```python
def aplicar_roster_custo_real_mo(
    contrato: RecursoContrato,
    roster: list[MembroEquipeReal],
) -> RecursoContrato:
    """Substitui custo_unit_semanal_mo (e custo_unit_semanal/custo_total_contrato
    dependentes) pelo custo real do roster — SOMENTE quando o roster cobre, com
    headcount suficiente, TODAS as funções em contrato.composicao_funcoes_mo.

    Verificação de cobertura (por função): count(indivíduos distintos no roster com
    aquele funcao_id) >= num_pessoas_por_equipe × contrato.quantidade_contratada.
    Se qualquer função não tiver cobertura suficiente, retorna o contrato SEM
    NENHUMA MUDANÇA (fallback seguro para o valor calibrado) — nunca faz
    substituição parcial misturando função real com função calibrada dentro do
    mesmo tipo.

    Quando a cobertura é suficiente:
        custo_real_total = Σ custo_real_mo_total(roster, funcao_id,
                                                    contrato.semana_inicio,
                                                    contrato.semana_fim)
                            para cada funcao_id em composicao_funcoes_mo
        custo_unit_semanal_mo_novo = custo_real_total /
                                      (quantidade_contratada × semanas_contrato)
        custo_unit_semanal_novo = custo_unit_semanal_mo_novo + cus_eq + cus_comb + cus_mat
        custo_total_contrato_novo = quantidade_contratada × custo_unit_semanal_novo
                                     × semanas_contrato

    NÃO recalcula particao_por_item nem os demais campos derivados (custo_mob_desmob_
    contrato, custo_standby_total etc.) — ADR-157 precisará decidir a ordem de chamada
    no pipeline real (antes de particionar_contrato/_aplicar_custo_instancial) para
    que esses campos nasçam já consistentes com o custo substituído, em vez de
    recalculá-los aqui de forma duplicada e possivelmente divergente.
    """
```

**Por que verificação por headcount distinto, não por semana-a-semana:** o risco real a evitar é uma função com **zero ou poucas** pessoas reais declaradas ficando silenciosamente contabilizada como custo zero (subestimando o total). Gaps individuais de admissão/desligamento **dentro** do headcount correto não são um risco — são exatamente a proporcionalização real que ADR-154 já entrega corretamente. Portanto, a verificação de cobertura correta é "existem pessoas suficientes declaradas", não "todas as semanas estão cobertas por alguém".

### D4 — Escopo explicitamente fechado nesta ADR

Sem wiring ao orquestrador real (`skill.py`/`_processar_instancias_recurso`/`instancias.py`), sem campo novo em `Escopo`, sem chamada a `extrair_composicao_funcoes_mo` dentro de `_tipo_recurso_fungivel`/`_derive_item_tipo_requerido`. `composicao_funcoes_mo` fica com default `{}` em todo `RecursoContrato` construído pelo pipeline real hoje — **zero mudança de comportamento**. Ambas as funções (D2/D3) são testadas isoladamente com objetos construídos diretamente nos testes, sem depender do pipeline real.

---

## Alternativas Rejeitadas

| ID | Alternativa | Motivo |
|---|---|---|
| A1 | Substituir `custo_unit_semanal_mo` sem verificação de composição (design original) | Rejeitado após investigação — corrompe silenciosamente `RecursoContrato`s de equipe mista, o caso comum nos benchmarks reais |
| A2 | Guarda simples "só aplica quando `custo_unit_semanal_eq==0`" | Rejeitado — descartaria a maioria dos tipos reais (mistos), entregando muito pouco benefício prático; a decomposição por função resolve o caso geral |
| A3 | Verificação de cobertura semana-a-semana (não por headcount distinto) | Rejeitado por enquanto — mais preciso, mas a lacuna que gaps semanais cobrem já é o comportamento correto desejado (proporcionalização real), não um risco; adicionar complexidade sem necessidade demonstrada |
| A4 | Recalcular `particao_por_item`/demais campos derivados dentro desta função | Rejeitado — depende de decisão de ordem de execução no pipeline real, que é escopo de ADR-157, não desta fase pura |
| A5 | Já conectar a `Escopo`/orquestrador nesta mesma ADR | Rejeitado — decisão explícita do usuário de fatiar em duas ADRs sequenciais para não misturar validação de lógica pura com risco de pipeline ao vivo |

---

## Consequências

### Positivas

| Efeito | Descrição |
|---|---|
| Resolve o caso geral (equipe mista) corretamente | Decompõe por função em vez de assumir tipo puro — cobre `ESC-3CAT` e afins |
| Verificação de cobertura evita corrupção silenciosa | Nunca substitui parcialmente; fallback seguro para calibrado quando incompleto |
| Zero risco ao pipeline real | Nenhuma mudança de comportamento hoje — campo novo com default vazio, funções não chamadas por ninguém ainda |

### Negativas / Riscos

| Risco | Mitigação |
|---|---|
| `composicao_funcoes_mo` fica vazio até ADR-157 popular de fato | Aceitável — esta ADR entrega a lógica testada, não o dado populado; ADR-157 decide onde/como popular |
| `particao_por_item` e derivados não recalculados | Documentado como responsabilidade de ADR-157 (ordem de chamada no pipeline real) |
| Verificação por headcount distinto não garante cobertura semana-a-semana perfeita | Aceito deliberadamente — gaps individuais dentro do headcount correto são proporcionalização real, não erro (ver D3) |

---

## Plano de Implementação

| Fase | Entregas | Status |
|---|---|---|
| F1 | `composicao_funcoes_mo` (campo) + `extrair_composicao_funcoes_mo` + `aplicar_roster_custo_real_mo` + testes | ⬜ |
| F2 (ADR-157, futura) | Wiring real: `Escopo.roster_mo`, chamada no orquestrador de skill-05, populamento de `composicao_funcoes_mo` em `_derive_item_tipo_requerido` | ⬜ (não iniciada) |

## Definition of Done

### Fase 1 (TDD — teste antes da implementação)

- [ ] `extrair_composicao_funcoes_mo` extrai `{funcao_id: num_pessoas}` corretamente de uma `ComposicaoPadraoEquipe`, ignorando entradas sem `funcao_id`
- [ ] `aplicar_roster_custo_real_mo` substitui quando o roster cobre TODAS as funções com headcount suficiente (`quantidade_contratada` considerado)
- [ ] `aplicar_roster_custo_real_mo` NÃO substitui (retorna contrato inalterado) quando qualquer função tem headcount insuficiente
- [ ] `aplicar_roster_custo_real_mo` NÃO substitui quando `composicao_funcoes_mo` está vazio (comportamento atual — nenhum contrato real hoje tem esse campo populado)
- [ ] `custo_unit_semanal_mo`/`custo_unit_semanal`/`custo_total_contrato` recalculados consistentemente quando a substituição ocorre (`custo_unit_semanal_eq/_comb/_mat` preservados)
- [ ] Contrato original (`RecursoContrato` de entrada) não é mutado — função pura, retorna nova instância
- [ ] Suíte completa sem regressão

---

## Relacionados

- ADR-154 — Roster Real de Mão-de-Obra (`custo_real_mo_total`, reaproveitada aqui)
- ADR-046 — RCPSP Completo (fundamenta que tipos de pool são "tipos de equipe", não funções isoladas — a origem do risco que motivou esta ADR)
- ADR-071 — Resource Contract Model (`RecursoContrato`, modelo estendido aqui)
- ADR-153 — Identidade Física de Recurso (decisão irmã de escopo — mesma disciplina de "aditivo primeiro, wiring depois")
- ADR-157 (futura, não criada ainda) — Wiring real do roster de MO no orquestrador de skill-05
