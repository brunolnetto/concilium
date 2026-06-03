# ADR-069: Cubo Analitico Navegavel por Faces, Medidas e Granularidades para UX Analitica

**Status:** Implementado (Iteracao 1 + Iteracao 2)
**Data:** 2026-05-22
**Autor:** Engenheiro Senior
**Relacionado:** ADR-058, ADR-059, ADR-060, ADR-061, ADR-068, NEP-024

---

## 1. Contexto

O dominio ja possui um cubo analitico 4D (categoria x atividade x tempo x componente_BDI),
com agregacoes temporais e de natureza de custo.

Apesar disso, a experiencia no produto ainda estava restrita a:
- KPIs resumidos
- visualizacoes finais em planilha Excel

Faltava um contrato de exploracao interativa para a UI iterar rapidamente em filtros,
sem precisar expor celulas brutas do cubo ou acoplar a interface ao formato interno.

Com a Iteracao 1 entregue, observou-se uma necessidade adicional:
- varios entregaveis desejados (curvas ABC por granularidade, contagem de mao de obra,
  contagem de equipamentos ativos no tempo, S-curve) sao "sabores" do mesmo cubo,
  mas nao podem ser modelados apenas como variacao de face.

Em alinhamento com ADR-058, esta ADR evolui para separar:
- projeção semantica (face)
- definicao de medida (measure profile)
- operador analitico (ex.: ABC, acumulado, contagem distinta)
- regra de agregacao dependente do grao temporal.

---

## 2. Problema

### P1 - Nao havia contrato de consulta por face
A API retornava apenas resumo consolidado, sem projeções navegaveis por dimensao.

### P2 - UX sem capacidade de iteracao guiada
Nao existia no frontend um explorador de face + granularidade + filtros contextuais.

### P3 - Risco de visualizacoes inconsistentes
Sem regras explicitas por face, filtros podiam gerar leituras ambíguas
(ex.: litros de diesel misturados com componentes financeiros).

### P4 - Face sozinha nao cobre analiticidade derivada
ABC, S-curve e metricas de recursos ativos sao transformacoes sobre faces base,
nao apenas novos "rows shapes" independentes.

### P5 - Ausencia de taxonomia formal de medidas
Sem declarar tipo de medida (R$, litro, contagem), agregacoes e graficos podem
misturar unidades e produzir leitura incorreta.

---

## 3. Decisao

### D1 - Definir "face" como contrato de projeção semantica
Cada face representa eixos (dimensoes) e restricoes semanticas do cubo.

Classificacao de faces:
- **Base faces**: projeções diretas do cubo (sem operador derivado)
- **Derived faces**: projeções com operador analitico aplicado sobre uma base face

Faces iniciais:
1. `tempo_natureza`
2. `tempo_componente`
3. `categoria_componente`
4. `atividade_componente`
5. `diesel_temporal`

Faces derivadas alvo da Iteracao 2 (sobre base faces):
1. `abc_curva` (Pareto acumulado por entidade)
2. `s_curve_custo` (acumulado temporal)
3. `recursos_ativos_tempo` (contagens por periodo)

### D2 - Granularidade temporal multipla na API
Para faces temporais, suportar: `semana`, `mes`, `bimestre`, `trimestre`, `semestre`, `ano`.

### D3 - Filtros comuns
Aplicar filtros opcionais em todas as faces quando aplicavel:
- `categoria`
- `componente_bdi`
- `atividade_id`
- `top_n`

### D3.1 - Introduzir medida como primeiro-class no contrato
Adicionar no contrato (Iteracao 2) parametros opcionais:
- `measure_profile` (ex.: `financial_default`, `abc_custo_direto`, `recursos_ativos`)
- `aggregation_mode` (ex.: `sum`, `count_distinct`, `cumulative`, `pareto`)

Regra: `face` define o *onde olhar*; `measure_profile` define *o que medir*;
`aggregation_mode` define *como agregar*.

### D4 - Regra semantica obrigatoria para diesel fisico
Na face `diesel_temporal`, forcar:
- `categoria = diesel`
- `componente_bdi = custo_direto`

Objetivo: garantir que a medida seja volume fisico (litros), nao markup financeiro.

### D4.1 - Regras de compatibilidade unidade x agregador
Toda medida deve declarar `unit_type`:
- `currency_brl`
- `volume_liter`
- `count`
- `fte`

E declarar agregadores permitidos por tipo.
Exemplos:
- `currency_brl`: `sum`, `cumulative`, `pareto`
- `count`: `count_distinct`, `sum` (quando semantica for numero de entidades)
- `volume_liter`: `sum`, `cumulative`

### D5 - Entrega incremental no Overview
Adicionar expander beta no Overview para validar:
- filtros
- shape de tabela
- comportamento de paginacao

antes de investir em biblioteca de charting dedicada.

### D6 - Operadores analiticos padrao (Iteracao 2)
Definir operadores reutilizaveis:
1. `pareto_abc`: ordena por valor desc, calcula percentual acumulado e classe A/B/C
2. `cumulative`: serie acumulada por periodo
3. `count_active_resources`: contagem de funcoes/equipamentos ativos por periodo

Formula de acumulado Pareto para item k ordenado:

$$
pct\_acumulado_k = \frac{\sum_{i=1}^{k} v_i}{\sum_{j=1}^{n} v_j}
$$

Classes padrao:
- A: 0% a 80%
- B: 80% a 95%
- C: 95% a 100%

---

## 4. Contrato de API

### 4.1 Iteracao 1 (entregue)

Endpoint:
- `GET /api/projects/{project_id}/cubo-analitico/projecao`

Query params:
- `face`
- `granularidade`
- `categoria` (opcional)
- `componente_bdi` (opcional)
- `atividade_id` (opcional)
- `top_n` (1..2000)

Resposta:
- `face`
- `granularidade`
- `chart_hint`
- `columns`
- `filtros_aplicados`
- `totais`
- `rows`

`rows` depende da face selecionada.

### 4.2 Iteracao 2 (entregue, sem quebrar endpoint)

Endpoint mantido:
- `GET /api/projects/{project_id}/cubo-analitico/projecao`

Endpoint de contrato (matriz analitica):
- `GET /api/projects/{project_id}/cubo-analitico/projecao/contrato`

Novos query params opcionais:
- `measure_profile`
- `aggregation_mode`
- `abc_threshold_a` (default 0.80)
- `abc_threshold_b` (default 0.95)

Extensao de resposta:
- `measure_profile`
- `aggregation_mode`
- `unit_type`
- `operator_meta`

Exemplo resumido de `operator_meta` para ABC:
- `thresholds`: `{ "a": 0.80, "b": 0.95 }`
- `class_counts`: `{ "A": 14, "B": 9, "C": 44 }`
- `coverage_a`: `0.8021`

---

## 5. Consequencias

### Positivas
- API desacoplada do armazenamento interno do cubo.
- UX consegue iterar por filtros com dado real em tempo de desenvolvimento.
- Base pronta para evolucao de graficos sem quebrar o contrato backend.
- Curvas ABC multi-granularidade passam a ser operador padrao, nao excecao.
- Entregaveis de recursos (mao de obra/equipamentos ativos no tempo) entram no mesmo
	pipeline de exploracao analitica.
- Menor risco de erro semantico por mistura de unidades no mesmo grafico.

### Trade-offs
- Shapes de `rows` variam por face (requer renderizacao adaptativa no frontend).
- Esta iteracao e "beta" (tabela + paginação), sem drilldown visual completo.
- Contrato fica mais rico e exige matriz de compatibilidade face x measure_profile x agregador.

---

## 6. Implementacao

### 6.1 Iteracao 1 (concluida)

1. Backend:
- metodo de projeção no service (`get_cubo_analitico_projection`)
- resolucao de faces no service
- novo endpoint de projeção na rota de analise

2. Frontend:
- expander "Cubo analitico (beta)" no Overview
- controles de face, granularidade e filtros
- tabela paginada para validar experiencia

### 6.2 Iteracao 2 (concluida)

1. Backend (contrato):
- aceitar `measure_profile` e `aggregation_mode`
- validar compatibilidade de unidade e agregador
- retornar `operator_meta` para operadores derivados (ABC/cumulative/count)

2. Backend (modelagem):
- implementar operadores reutilizaveis sobre base faces
- adicionar derivacao `abc_curva` e `recursos_ativos_tempo`

3. Frontend:
- presets de visualizacao por measure profile
- legendas semanticas por unidade (`unit_type`)
- comparacao lado a lado entre granularidades para mesma medida

4. Qualidade:
- testes de contrato cobrindo matriz minima
- casos invalidos de compatibilidade (ex.: `pareto` com `count` sem definicao)

---

## 7. Proximos passos

1. Adicionar visualizacao combinada de Pareto (barra + linha acumulada) para `abc_curva`.
2. Evoluir `recursos_ativos_tempo` para separar contagem de funcoes e equipamentos em series dedicadas.
3. Expandir testes de performance para cargas com alto cardinalidade de atividades.
4. Considerar endpoint de exportacao analitica versionada para auditoria historica.

---

## 8. Definition of Done (atualizada)

### DoD Iteracao 1
- [x] Endpoint de projeção por face + granularidade disponivel
- [x] Filtros comuns aplicados
- [x] Metadados de colunas e chart hint no payload
- [x] Expander de exploracao no Overview
- [x] Testes de contrato basicos (faces/granularidades/filtros invalidos)

### DoD Iteracao 2
- [x] Contrato estendido com `measure_profile` e `aggregation_mode`
- [x] Operadores `pareto_abc`, `cumulative`, `count_active_resources` implementados
- [x] Faces derivadas `abc_curva` e `recursos_ativos_tempo` disponiveis
- [x] Validacao de compatibilidade unidade x agregador em runtime
- [x] Testes de contrato da matriz analitica minima
