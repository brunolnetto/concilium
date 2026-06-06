# ADR-077 — Recurso Instancial: Mapa de Utilização de Equipamento e Mão-de-Obra

**Status:** Implementado  
**Data:** 2026-05-26  
**Autores:** Bruno Peixoto, Claude Sonnet 4.6  
**Contexto:** ADR-071 (Pool Contracts), ADR-073 (Perpetuação), ADR-076 (Calibração PU / Diagnóstico Frentes)

---

## 1. Contexto

ADR-071 introduziu pool contracts: o contrato cobre `N × custo_unit_semanal × semanas_contrato`,
onde N é o pico de demanda simultânea. ADR-076 identificou que o overhead de ociosidade chega a
R$42,9M no benchmark AGIS antes da otimização de pools — e R$9,8M após.

O que faltava era **rastreabilidade instancial**: saber, para cada slot numerado do pool (ex:
"ESC-3CAT-03"), em quais semanas ele estava trabalhando (ATIVO) vs. ocioso (STANDBY) e quais
atividades específicas ele cobriu ao longo do projeto. Sem esse mapa:

- O gestor não consegue identificar *quais instâncias específicas* têm alto custo de standby.
- Não é possível rastrear a composição real de cada equipe de atividade (quais slots do pool
  a alimentaram).
- Não há um resumo de utilização por contrato (OEE simplificado de frota).

---

## 2. Decisão

Implementar três novos modelos de domínio que representam o recurso em nível instancial:

### 2.1 InstanciaRecurso

Representa **um slot numerado** do contrato de pool (ex: "ESC-3CAT-03"). Rastreia:
- Entrada e saída no projeto (semana_entrada / semana_saida)
- Semanas ativas (com atividade atribuída) vs. standby
- Taxa de utilização individual
- Custo de standby imputável ao slot
- Lista de atividades que usaram este slot

### 2.2 ComposicaoEquipeAtividade

Liga uma **atividade** ao seu conjunto de slots instanciais. Responde:
- "Quais instâncias do pool ESC-3CAT foram usadas pela atividade eap-1_5?"
- Quantas (n_instancias), quais números (instancias_numeros), por quanto tempo (machine_weeks)

### 2.3 ResumoUtilizacaoContrato

Agrega a utilização por contrato:
- `machine_weeks_disponiveis` = N × semanas_contrato
- `machine_weeks_usados` = Σ semanas_ativas por instância
- `taxa_utilizacao_pct` = usados / disponíveis × 100
- `custo_standby_total` = custo_unit_semanal × machine_weeks_standby
- `status_utilizacao`: OK ≥ 65%, AVISO 35-65%, CRITICO < 35%

---

## 3. Modelo de Identidade dos Slots

### 3.1 Slot Contratual vs. Ativo Físico

O contrato de pool compra **capacidade**, não equipamentos específicos. "ESC-3CAT-03" é uma
**posição contratual** — o ativo físico que ocupa esse slot pode variar ao longo do projeto
(por substituição, manutenção, etc.). O modelo ADR-077 rastreia a posição contratual, não o
ativo físico. Para rastrear ativos físicos individuais (numeração de série, OEE real), seria
necessário um sistema de gestão de ativos fora do escopo do concilium.

### 3.2 Regra de Atribuição de Slots

Para determinar quais slots cobrem qual atividade, usa-se uma **atribuição gulosa por prioridade
de span** (duração calendária da atividade):

1. Em cada semana, ordenar atividades por `span` (end_idx − start_idx) decrescente — atividades
   com maior duração calendária têm prioridade. Isso minimiza reassignações de slot (ativos físicos
   de longa permanência ficam no mesmo slot durante todo o projeto).
2. Atribuir slots 1..demand_1 à atividade de maior span, slots (demand_1+1)..(demand_1+demand_2)
   à segunda, etc.
3. Slots restantes (cursor..N) = STANDBY na semana.

Exemplo (ESC-3CAT, pool=6):
| span | eap-1_9 (48w) | eap-1_6 (25w) | eap-1_5 (12w) |
|------|:-------:|:-------:|:-------:|
| Prioridade | 1ª | 2ª | 3ª |

| Semana | eap-1_9 (2u, span=47) | eap-1_6 (4u, span=24) | eap-1_5 (4u, span=11) | Standby |
|--------|:---------------------:|:---------------------:|:---------------------:|:-------:|
| W1-25  | slots 1-2 | slots 3-6 | — | 0 |
| W26-37 | slots 1-2 | — | slots 3-6 | 0 |
| W38-48 | slots 1-2 | — | — | slots 3-6 |

Resultado:
- Instâncias 1-2: 48w ativas (100% utilização), cobertas [eap-1_9]
- Instâncias 3-6: 37w ativas + 11w standby (77% utilização), cobertas [eap-1_6, eap-1_5]

---

## 4. Alternativas Rejeitadas

### 4.1 Rastreio Semana a Semana no Canônico
Armazenar um dicionário `{week: estado}` por instância geraria um campo muito grande (pool de
10 × 48 semanas = 480 entradas). O modelo ADR-077 armazena apenas os **agregados**
(`semanas_ativas`, `semanas_standby`), suficientes para análise de custo e auditoria.

### 4.2 Novo Skill entre skill-04 e skill-05
O cálculo instancial só é possível após o pool contract (skill-05). Adicionar um novo skill
seria overhead arquitetural — o cálculo é uma extensão natural do `_build_contratos_recurso`
existente. Optou-se por adicionar `_build_instancias_recurso` em `_skill_helpers_a.py` e
chamá-lo ao final de `run_equipes_e_alocacao`.

### 4.3 Granularidade de Insumo Individual (Máquina/Operador)
O ADR-076 trabalha no nível de equipe (1 equipe ESC-3CAT = 1 escavadeira + N caminhões + M
operadores). O ADR-077 mantém essa granularidade — rastrear cada insumo individualmente
exigiria "explodir" a composição do CPU por slot, o que é viável mas desnecessário para o
diagnóstico de ociosidade de contrato. Esta opção fica como extensão futura.

---

## 5. Modelo Formal

### 5.1 Algoritmo de Utilização

Para cada contrato com `tipo_id` e `quantidade_contratada = N`:

```
Para cada semana w ∈ [semana_inicio, semana_fim]:
  demand_w = Σ_atividades demand(atividade, w)
  onde demand(A, w) = round(num_equipes(A, w) × required_r(A) / total_required_peak(A))

Para cada instância i ∈ {1..N}:
  semanas_ativas_i   = |{w : demand_w ≥ i}|
  semanas_standby_i  = semanas_contrato − semanas_ativas_i
  taxa_utilizacao_i  = semanas_ativas_i / semanas_contrato × 100
  custo_standby_i    = custo_unit_semanal × semanas_standby_i
```

### 5.2 Validator VAL-SLOT-STANDBY-ALTO

Emitido quando qualquer instância tem taxa de utilização < 65% (standby > 35%):

```
VAL-SLOT-STANDBY-ALTO:
  AVISO  → status_utilizacao = AVISO  (taxa ∈ [35%, 65%))
  ERRO   → status_utilizacao = CRITICO (taxa < 35%)
```

### 5.3 Thresholds de ResumoUtilizacaoContrato.status_utilizacao

| Taxa de Utilização | Status |
|--------------------|--------|
| ≥ 65% | OK |
| 35% – 65% | AVISO |
| < 35% | CRITICO |

---

## 6. Implementação

### 6.1 Arquivos Modificados

| Arquivo | Mudança |
|---------|---------|
| [canonical.py](../../../../src/concilium/domain/models/canonical.py) | +3 novos modelos após `RecursoContrato`; +3 campos em `CanonicalModel` |
| [_skill_helpers_a.py (skill-05)](../../../../src/concilium/application/skills/manifests/05-equipes-e-alocacao/_skill_helpers_a.py) | Nova função `_build_instancias_recurso` |
| [skill.py (skill-05)](../../../../src/concilium/application/skills/manifests/05-equipes-e-alocacao/skill.py) | Chama `_build_instancias_recurso` após `_build_contratos_recurso` |
| [runtime.py](../../../../src/concilium/application/runtime.py) | Nova seção `_md_utilizacao_recursos` |

### 6.2 Arquivos Criados

| Arquivo | Descrição |
|---------|-----------|
| [tests/unit/test_adr077_recurso_instancial.py](../../../../tests/unit/test_adr077_recurso_instancial.py) | Testes unitários (≥ 20 testes) |

### 6.3 Campos Adicionados a CanonicalModel

```python
instancias_recurso: list[InstanciaRecurso] = Field(default_factory=list)
composicao_equipes_atividade: list[ComposicaoEquipeAtividade] = Field(default_factory=list)
resumo_utilizacao_contratos: list[ResumoUtilizacaoContrato] = Field(default_factory=list)
```

---

## 7. Resultados AGIS (pós ADR-076 Opção E — pools reduzidos)

### 7.1 ResumoUtilizacaoContrato

| Contrato | Pool N | Semanas | MW Disp. | MW Usados | Utilização | Custo Standby | Status |
|----------|:------:|:-------:|:--------:|:---------:|:----------:|:-------------:|--------|
| ESC-3CAT | 6 | 48 | 288 | 244 | 84.7% | ~R$5,3M | OK |
| ESC-2CAT | 2 | 46 | 92 | 92 | 100% | R$0 | OK |
| ESC-1CAT | 1 | 41 | 41 | 41 | 100% | R$0 | OK |
| ATERRO | 5 | varia | — | — | ~76.5% | ~R$4,5M | OK |

### 7.2 InstanciaRecurso — ESC-3CAT

| Instância | Semanas Ativas | Semanas Standby | Utilização | Atividades |
|-----------|:--------------:|:---------------:|:----------:|------------|
| ESC-3CAT-01 | 48 | 0 | 100% | [eap-1_9] |
| ESC-3CAT-02 | 48 | 0 | 100% | [eap-1_9] |
| ESC-3CAT-03 | 37 | 11 | 77.1% | [eap-1_6, eap-1_5] |
| ESC-3CAT-04 | 37 | 11 | 77.1% | [eap-1_6, eap-1_5] |
| ESC-3CAT-05 | 37 | 11 | 77.1% | [eap-1_6, eap-1_5] |
| ESC-3CAT-06 | 37 | 11 | 77.1% | [eap-1_6, eap-1_5] |

O standby residual de 11 semanas nas instâncias 3-6 é **irreducível** dado o modelo de pool
compartilhado: eap-1_9 precisa de 2 unidades durante toda a obra (48 semanas), mas eap-1_5 e
eap-1_6 (combinados) precisam de 4 unidades apenas durante 37 das 48 semanas.

---

## 8. Extensões Futuras

- **Explosão de composição por insumo**: detalhar quais máquinas e operadores específicos dentro
  de cada slot ESC-3CAT estão ociosos (requer CPU composition explosion).
- **Desmobilização antecipada**: identificar semanas em que uma instância pode ser liberada antes
  do fim do contrato para reduzir custo (otimização de contrato, não apenas diagnóstico).


---

## 9. ADRs Relacionados

- **ADR-071**: Pool contracts — origem do `gap_pool_overhead`
- **ADR-073**: Perpetuação de instâncias — mob/demob entre atividades
- **ADR-076**: Calibração PU + diagnóstico frentes — descoberta dos gaps grotescos que motivaram
  este ADR
