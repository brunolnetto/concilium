# NEP-030: Injeção mínima honesta na validação de benchmark

**Status:** Em Andamento  
**Prioridade:** 🔴 Crítico  
**Área:** Arquitetura e Skills  
**Tipo:** Governança + Bug  
**Esforço:** L  
**Identificado em:** 2026-05-24

---

## Contexto

O subsistema de benchmark valida o pipeline comparando sua saída com valores de referência
de planilhas reais (AGIS, SICRO, etc.). A expectativa é que fornecer apenas os dados mínimos
de entrada produza os mesmos valores finais que a planilha de referência.

Durante auditoria (2026-05-24) identificou-se que o `BenchmarkSpecLoader` e o
`BenchmarkInferenceService` injetam valores intermediários extraídos da referência
diretamente nas entradas de skills de cálculo, circularizando a validação.

---

## Problema Observado

### P1 — `tabela_bdi` injetada da referência no skill-06

**Arquivo:** `spec_loader.py` linhas 184–186

```python
bdi_ref = ref.get("bdi", {})
if bdi_ref:
    extra_inputs = self._lfd_build_bdi_section(extra_inputs, ref, bdi_ref)
    # injeta extra_inputs["06-precificacao-unitaria"]["tabela_bdi"]
```

A `tabela_bdi` contém as alíquotas de BDI por categoria (ac, df, r, cr, l, cofins, iss, pis,
cssl, ir) extraídas da planilha de referência. Ao injetar isso no skill-06, a marcação (markup)
que o algoritmo aplica é a mesma que a planilha usou — não é derivada do perfil/jurisdição
do projeto.

**Efeito:** O δ no custo s/BDI pode ser alto, mas o δ no preço de venda é artificialmente
baixo porque o BDI foi copiado da própria referência.

### P2 — `bdi_indireto_efetivo` injetado no skill-08 (override circular)

**Arquivo:** `inference.py` linhas 56–59, 147–186

```python
# Formula (linha 178):
value = (preco_venda_ref - sum(planejamento.com_bdi)) / custo_indireto_ref - 1
pack.skill_inputs["08-consolidacao-financeira"]["bdi_indireto_efetivo"] = value
```

Esta é a taxa de BDI sobre custos indiretos que matematicamente **garante** que o preço de
venda total feche com a referência. É um resíduo, não um parâmetro do projeto.

**Efeito:** O δ em `preco_venda` é sempre próximo de zero — não porque o algoritmo está
correto, mas porque o valor final foi engenhado para fechar.

### P3 — `planejamento_item_overrides` injetado da referência no skill-06

**Arquivo:** `spec_loader.py` linhas 188–192

```python
ref_item_overrides = ref.get("planejamento_item_overrides")
if isinstance(ref_item_overrides, dict) and ref_item_overrides:
    extra_inputs["06-precificacao-unitaria"]["planejamento_item_overrides"] = ref_item_overrides
```

Se a referência contiver overrides de preço por item, eles sobrescrevem os preços calculados
pelo algoritmo. O pipeline não calcula — ele copia os preços da planilha.

**Efeito:** Subtotais por item batem exatamente com a referência independentemente da
qualidade do catálogo ou do algoritmo.

### P4 — `benchmark_mode=True` injetado nos skills 06 e 08

**Arquivo:** `inference.py` linhas 31–33

Este flag desativava o ADR-038 (já bloqueado pela NEP-029) e ativava o caminho `sbdi`
(agora padrão para todos os modos). Em skill-08 é usado para pular algumas validações.
Ao injetá-lo em skills de cálculo, o pipeline assume comportamento diferente do modo de
produção, ocultando discrepâncias.

---

## Causa Raiz

Ausência de separação clara entre:
1. **Parâmetros de entrada** (o que o projeto precisa informar)
2. **Valores intermediários** (o que o algoritmo deve derivar)
3. **Alvos de validação** (com o que comparar o resultado)

A referência serve como as três coisas ao mesmo tempo, e o código não distingue os papéis.

---

## Definição de Injeção Mínima Honesta

```
┌────────────────────────────────────────────────────────────────────┐
│  ENTRADAS BRUTAS — injetadas pelo spec_loader                     │
│  Definem o que o projeto é, não o que ele deve custar             │
├────────────────────────────────────────────────────────────────────┤
│  • itens_eap[].{cpu_id, quantitativo, unidade}                    │
│  • indiretos_detalhamento.CAT.custo_fixo_mensal (estrutura equipe)│
│  • regime_trabalho, localizacao, data_inicio, data_termino        │
│  • cronograma.atividades (duração e precedência)                  │
│  • rcpsp_spec (restrições de recursos — quando disponível)        │
└────────────────────────────────────────────────────────────────────┘

┌────────────────────────────────────────────────────────────────────┐
│  DERIVADO PELO ALGORITMO — não deve vir da referência             │
├────────────────────────────────────────────────────────────────────┤
│  • Preços unitários (catálogo + pu_calculator)                    │
│  • tabela_bdi (perfil/jurisdição do contexto)                     │
│  • bdi_indireto_efetivo (consolidação normal em skill-08)         │
│  • Schedules, equipes, alocações                                  │
└────────────────────────────────────────────────────────────────────┘

┌────────────────────────────────────────────────────────────────────┐
│  ALVOS DE VALIDAÇÃO — extraídos da referência para comparação     │
│  Não entram em nenhum cálculo                                     │
├────────────────────────────────────────────────────────────────────┤
│  • resultado.benchmark_confronto_referencia.{custo_direto,        │
│    custo_indireto, custo_total, preco_venda}                      │
│  • planejamento_detalhado[i].subtotal.sem_bdi.total (por item)    │
└────────────────────────────────────────────────────────────────────┘
```

---

## Objetivo

Remover os overrides circulares do pipeline de benchmark de modo que o δ final meça
genuinamente a qualidade do algoritmo, não a fidelidade da cópia.

---

## Decisão

### D1 — Remover `tabela_bdi` da injeção de referência

O BDI deve vir do **perfil do contexto** (lido pelo runtime normal de skill-06 via
`DEFAULT_BDI_TABELA` ou via perfil versionado). A referência não injeta mais BDI.

Consequência: se o `DEFAULT_BDI_TABELA` divergir do BDI da referência, o δ aumenta
— e isso é correto, pois indica que o perfil precisa de calibração.

### D2 — Remover `bdi_indireto_efetivo` da inferência

`_derive_bdi_indireto_efetivo()` não deve ser chamada nem o resultado injetado.
Skill-08 usa a taxa `bdi_rates.get("indireto", 0.0)` do perfil normalmente.

### D3 — Remover `planejamento_item_overrides` da injeção de referência

A cadeia de injeção de overrides de custo por item da referência é removida.
Se futuramente for necessário, deve ser um mecanismo explícito e documentado separado
do arquivo de referência.

### D4 — Restringir `benchmark_mode=True` ao skill-09 (reporting)

`benchmark_mode=True` é injetado **apenas no skill-09** para habilitar o relatório
de comparação com a referência. Skills 06 e 08 executam em modo normal (como produção).

### D5 — Documentar `reference_projection` como dado somente de leitura

A extração de `reference_projection` é mantida — ela é a fonte dos alvos de comparação
para skill-09. Nenhum campo de `reference_projection` deve alimentar cálculos de skill.

---

## Escopo

### Incluído

1. Remoção das injeções P1, P2, P3, P4 no `spec_loader.py` e `inference.py`.
2. Atualização dos testes afetados.
3. Documentação de quais campos da referência são entradas vs. alvos.

### Excluído

1. Migração de BDI para perfil versionado (depende de NEP futura sobre BDI governance).
2. Mudança de critérios de qualidade do benchmark (APROVADO/INVIÁVEL).
3. Refatoração do `BenchmarkInputDeriver`.

---

## Plano de Implementação

### Fase 1 — Remover injeções circulares (D1–D4)

1. `spec_loader.py`: remover blocos de `tabela_bdi` e `planejamento_item_overrides`.
2. `inference.py`: remover chamada e injeção de `_derive_bdi_indireto_efetivo`; remover
   `benchmark_mode` de skills 06 e 08.
3. Atualizar testes afetados.

### Fase 2 — Observar e calibrar

1. Rodar benchmarks com injeção mínima honesta.
2. Registrar o δ real por indicador e por item.
3. Identificar se divergência vem do BDI, catálogo, ou lógica de skill.

### Fase 3 — BDI governance (NEP futura)

1. Mover configuração de BDI para perfil versionado do contexto.
2. Derivar `tabela_bdi` automaticamente do perfil em vez do DEFAULT.

---

## Critério de Aceite

1. `BenchmarkSpecLoader` não injeta `tabela_bdi` nem `planejamento_item_overrides`.
2. `BenchmarkInferenceService.derive()` não injeta `bdi_indireto_efetivo` nem
   `benchmark_mode` para skills 06 e 08.
3. Skills 06 e 08 executam com o mesmo código de produção (sem fork de comportamento).
4. `reference_projection` continua disponível para skill-09 (comparação final).
5. Benchmark AGIS executa sem erro; δ pode ser > 0.5% (aceitável nesta fase).
6. Testes de unidade refletem o novo contrato de injeção mínima.

---

## Riscos

1. δ aumenta significativamente após remover injeções — isso é esperado e desejado.
   O risco é que seja interpretado como regressão.
2. Skills 06/08 sem `benchmark_mode=True` podem emitir validações que antes eram
   silenciadas — ruído temporário.

## Mitigações

1. Atualizar critério de APROVADO/INVIÁVEL no benchmark para aceitar δ ≤ 5% na fase
   de calibração pós-NEP-030.
2. Adicionar log explícito no runner: "Executando com injeção mínima honesta (NEP-030)".

---

## Evidências Técnicas

1. `src/concilium/application/benchmarks/spec_loader.py` (linhas 184–192)
2. `src/concilium/application/benchmarks/inference.py` (linhas 29–59, 147–186)
3. `src/concilium/application/skills/manifests/08-consolidacao-financeira/_skill_helpers_a.py`
4. `benchmarks/data/AGIS/artifacts/inputs/referencia.json`
5. Diagnóstico completo em conversa de engenharia de 2026-05-24

---

## Resultado Esperado

O benchmark passa a medir genuinamente o quanto o algoritmo reproduz o racional da
planilha de referência. O δ real — honesto — guia iterações de melhoria no catálogo,
perfil de BDI e lógica de skills.
