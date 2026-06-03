# NEP-032: Expurgo de precos_unitarios_sbdi — precificação bottom-up canônica

**Status:** Em Andamento  
**Prioridade:** 🔴 Crítico  
**Área:** Arquitetura e Skills  
**Tipo:** Refactor + Governança  
**Esforço:** L  
**Identificado em:** 2026-05-25

---

## Contexto

O campo `precos_unitarios_sbdi` nos arquivos JSON de CPU surgiu como atalho de validação:
os valores da planilha AGIS foram copiados para o catálogo como "preço de referência" e
depois usados pelo skill-06 como fonte primária de precificação (NEP-029 D1).

Isso cria o mesmo problema que buscamos eliminar em NEP-030: **uma fonte hard-coded que
diverge silenciosamente quando o catálogo de insumos é atualizado**, e que impede medir
se o algoritmo de composição está correto.

---

## Problema

### P1 — Dois caminhos de custo com valores divergentes

```
precos_unitarios_sbdi  →  skill-06 (precificação) → N1 (Bridge)
composicao_padrao_equipe × producao_horaria → skill-05 (equipes) → N4 (Bridge)
```

Quando N1 vem de `sbdi` (SICRO) e N4 vem da composição da equipe, o Bridge sempre
diverge — não porque há ineficiência operacional, mas porque as duas fontes representam
bases de cálculo diferentes. O Bridge VERMELHO persistente do AGIS (N1=R$47M, N4=R$143M)
é sintoma direto disso.

### P2 — precos_unitarios_sbdi é dado imutável em arquivo JSON

SICRO/SINAPI fornecem preços de insumos individuais (salário de operador, hora de
escavadeira, preço de diesel). O preço unitário da CPU é uma **grandeza derivada**:

```
PU_categoria = custo_categoria_hora / producao_horaria

custo_mo_hora    = Σ (salario_mensal_funcao / horas_mes × alpha × num_pessoas)
custo_diesel_hora = consumo_L_h × preco_diesel × num_equip
custo_equip_hora  = preco_unitario_equip × num_unidades
```

Hard-codar esse resultado impede que o algoritmo seja validado. Se os preços de insumos
forem atualizados, `precos_unitarios_sbdi` fica desatualizado silenciosamente.

### P3 — Impossibilidade de rastrear qual insumo causa desvio

Com `sbdi` hard-coded, qualquer desvio no preço de venda final é opaco — não sabemos
se vem do diesel, do salário do operador ou da produtividade da escavadeira.
Com bottom-up canônico, cada componente é rastreável individualmente.

---

## Decisão

### D1 — Remover precos_unitarios_sbdi como fonte de precificação em skill-06

Skill-06 calculará preço unitário exclusivamente via:

```
1. derivar_precos_unitarios_sbdi(producao, insumo_index, params)
   → lê composicao_padrao_equipe + valor_horario da produção da CPU
   → resolve preços via RepositorioInsumo (SICRO/SINAPI atualizado)
   → retorna {mo, diesel, equipamentos, material} por unidade de serviço

2. Fallback: composicao_itens × preco_insumo  [CPUs sem producao_id_ref]
```

### D2 — precos_unitarios_sbdi no JSON vira campo de auditoria, não de cálculo

O campo permanece nos JSONs das CPUs como **valor de referência histórica** para
comparação, não como entrada de cálculo. Emitir `VAL-PLAN-SBDI-LEGADO` quando presente
para indicar que o valor não está sendo usado.

### D3 — N1 e N4 no Bridge passam a ter a mesma base de cálculo

Com D1 em vigor:
- N1 = Σ(PU_derivado × Q) onde PU_derivado = f(composição, insumos, produtividade)
- N4 = Σ(custo_equipe_total) onde custo_equipe = mesmo f(composição, insumos) × duração

A diferença entre N1 e N4 passa a refletir apenas:
- **quantização** (arredondamento de frentes inteiras — N2)
- **praticabilidade** (perdas climáticas — N3)
- **delta real** de eficiência/ineficiência operacional (N4)

---

## Escopo

### Incluído

1. `_process_eap_item` em skill-06: usar `derivar_precos_unitarios_sbdi` como fonte primária
2. Passar `preco_diesel` e parâmetros de encargos do contexto para a função
3. Deprecar caminho `sbdi` hard-coded com aviso `VAL-PLAN-SBDI-LEGADO`
4. Verificar benchmark AGIS com nova abordagem (delta deve ser próximo de 0% para direto)

### Excluído

1. Remoção física dos campos `precos_unitarios_sbdi` dos JSONs (preservar como histórico)
2. Atualização do custo_direto_unitario_planilha nos JSONs

---

## Critério de Aceite

1. Skill-06 não lê `precos_unitarios_sbdi` para calcular `preco_cat`
2. Benchmark AGIS: δ custo_direto ≤ 2% após mudança (vs. referência)
3. N1 e N4 convergem: Bridge δreal < 10% (VERDE ou AMARELO)
4. EQ e Diesel aparecem com valores não-zero no planejamento AGIS
5. PE passa de ERRO para OK/AVISO na maioria dos itens

## Evidências Técnicas

1. `src/concilium/application/catalog/pu_calculator.py` — `derivar_precos_unitarios_sbdi()`
2. `src/concilium/application/skills/manifests/06-precificacao-unitaria/_skill_helpers_a.py`
3. `config/catalogos/mendeslobo/cpus/` — CPUs com campo `precos_unitarios_sbdi` a deprecar
4. `benchmarks/data/AGIS/artifacts/audit/benchmark_report.json` — Bridge VERMELHO atual
