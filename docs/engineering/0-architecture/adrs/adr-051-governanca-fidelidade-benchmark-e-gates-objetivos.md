# ADR-051 — Governanca de Fidelidade de Benchmark com Gates Objetivos e Relatorio de Acao Granular

**Status:** Implementado  
**Data:** 2026-05-10  
**Contexto:** MendesLobo Construtora - Concilium

---

## Contexto

A avaliacao de benchmark vinha sofrendo com subjetividade na leitura de deltas entre referencia e engine, especialmente em fases criticas de custo, margem e consolidacao.

Mesmo com modelagem operacional e financeira aderente a fonte, sem gates objetivos:

- Decisoes de aprovacao variavam por analista.
- Acoes corretivas eram descritas de forma pouco comparavel entre projetos.
- Escalonamento de incidentes criticos nao era consistente.
- Nao havia padrao unico para relatorio de acao por severidade/fase/causa.

Os documentos de avaliacao em [docs/engineering/evals/BENCHMARK_REFERENCE_DATA_SPECIFICATION.md](docs/engineering/evals/BENCHMARK_REFERENCE_DATA_SPECIFICATION.md) e [docs/engineering/evals/BENCHMARK_QUALITY_THRESHOLDS.md](docs/engineering/evals/BENCHMARK_QUALITY_THRESHOLDS.md) ja consolidam conteudo tecnico suficiente para formalizar a governanca como decisao arquitetural.

---

## Decisao

Adotar uma politica obrigatoria de fidelidade com gates objetivos para benchmark, composta por:

1. Gate universal de desvio percentual para classificacao primaria.
2. Gate complementar por metrica/fase para indicadores criticos.
3. Regras deterministicas de aprovacao, bloqueio e escalonamento.
4. Relatorio de acao granular categorizado por fase, severidade, causa e owner.

### D1 - Gate Universal de Desvio (obrigatorio)

Para qualquer metrica com valor de referencia > 0:

$$
\Delta\% = \frac{|V_{calc} - V_{ref}|}{|V_{ref}|} \times 100
$$

Classificacao primaria:

| Faixa de Delta | Classe | Severidade | Acao padrao |
|---|---|---|---|
| $\pm 0\%$ ate $\pm 5\%$ | IDEAL | S0 | Aprovar |
| $\pm 5\%$ ate $\pm 15\%$ | ATENCAO | S1 | Revisao obrigatoria |
| $\pm 15\%$ ate $\pm 30\%$ | PREOCUPANTE | S2 | Investigacao formal |
| acima de $\pm 30\%$ | CRITICO | S3 | Bloquear pipeline |

### D2 - Gate Complementar por Metrica Critica

As seguintes metricas usam limites mais estritos para decisao final (quando aplicavel):

- Custo Direto
- Custo Total
- Preco de Venda
- Margem
- BDI efetivo

Regra: prevalece sempre o pior status entre Gate Universal (D1) e Gate Complementar.

### D3 - Regras de Decisao Anti-Subjetividade

A decisao final de um benchmark passa a ser deterministica:

1. Se existir qualquer S3: BLOQUEADO.
2. Se nao houver S3 e existir S2 em metrica critica: BLOQUEADO COM INVESTIGACAO.
3. Se nao houver S2/S3 e existir S1: APROVADO COM RESSALVAS.
4. Se todas metricas estiverem em S0: APROVADO.

Regra adicional de protecao:

- Se houver divergencia em Custo Direto ou Custo Total acima de 10%, a aprovacao automatica e vedada, mesmo que score agregado pareca alto.

### D4 - Score Global de Fidelidade

O score global segue media ponderada por fase, com pesos definidos no documento de thresholds.

Uso do score:

- Instrumento de tendencia e comparacao historica.
- Nao substitui gate critico por metrica.
- Nao pode anular bloqueio S3.

### D5 - Relatorio de Acao Granular Obrigatorio

Todo benchmark executado gera relatorio estruturado com taxonomia fixa:

- Projeto
- Versao/plano
- Fase
- Metrica
- Referencia
- Calculado
- Delta
- Classe (IDEAL/ATENCAO/PREOCUPANTE/CRITICO)
- Severidade (S0/S1/S2/S3)
- Causa categoria
- Acao recomendada
- Owner
- SLA
- Evidencia
- Status da acao

Categorias obrigatorias de causa:

- DADOS_REFERENCIA
- DERIVACAO_PIPELINE
- CATALOGO
- PARAMETRIZACAO_BDI
- CONSOLIDACAO
- ADAPTER_SAIDA
- OUTROS

SLA por severidade:

- S0: sem acao corretiva obrigatoria
- S1: ate 2 dias uteis
- S2: ate 1 dia util
- S3: imediato (bloqueio e escalonamento)

### D6 - Artefato Minimo do Relatorio

Formato minimo por linha de acao (JSON):

```json
{
  "project_id": "matec-guarulhos",
  "escopo_id": "default",
  "plano_id": "v1",
  "fase": "06-consolidacao",
  "metrica": "custo_total",
  "valor_referencia": 25405681.52,
  "valor_calculado": 27100000.00,
  "delta_pct": 6.67,
  "classe": "ATENCAO",
  "severidade": "S1",
  "causa_categoria": "DERIVACAO_PIPELINE",
  "acao_recomendada": "Revalidar fonte de custo direto e recomputar consolidacao",
  "owner": "engenharia-benchmarks",
  "sla_horas": 48,
  "evidencia": "logs skill 06 + referencia.json",
  "status_acao": "ABERTA"
}
```

---

## Consequencias

### Positivas

- Elimina subjetividade na aprovacao de benchmark.
- Torna escalonamento de incidentes reproduzivel.
- Permite comparacao entre projetos por severidade e causa raiz.
- Cria trilha auditavel de acao corretiva por fase.
- Acelera melhoria continua da engine via backlog categorizado.

### Riscos / Custos

- Aumento inicial de rigor pode elevar volume de bloqueios.
- Times precisam aderir ao preenchimento completo de relatorio.
- Pode exigir ajuste de automacoes para emitir taxonomia padrao.

Mitigacoes:

- Adocao progressiva em 2 ondas (piloto + escala).
- Templates e validadores automatizados no pipeline.
- Treinamento rapido para engenheiros e revisores.

---

## Plano de Implementacao

| Fase | Entrega | Status |
|---|---|---|
| F1 | Publicar ADR-043 e alinhar semaforo oficial | Proposto |
| F2 | Gerar relatorio granular padrao ao fim do benchmark | Proposto |
| F3 | Aplicar bloqueio automatico para S3 e regra de metrica critica | Proposto |
| F4 | Dashboard de severidade por fase/causa/owner | Proposto |

---

## Definition of Done

- [ ] ADR aprovado pelo time de engenharia.
- [ ] Gates D1-D3 implementados no fluxo de avaliacao.
- [ ] Relatorio granular (D5/D6) emitido automaticamente por benchmark.
- [ ] Bloqueio automatico para S3 ativo.
- [ ] Evidencia de uso em pelo menos 5 projetos.
- [ ] Indicador semanal de distribuicao S0/S1/S2/S3 publicado.

---

## Referencias

- [docs/engineering/evals/BENCHMARK_REFERENCE_DATA_SPECIFICATION.md](docs/engineering/evals/BENCHMARK_REFERENCE_DATA_SPECIFICATION.md)
- [docs/engineering/evals/BENCHMARK_QUALITY_THRESHOLDS.md](docs/engineering/evals/BENCHMARK_QUALITY_THRESHOLDS.md)
- [docs/engineering/architecture/adrs/adr-009-indirect-costs-as-first-class.md](docs/engineering/architecture/adrs/adr-009-indirect-costs-as-first-class.md)
- [docs/engineering/architecture/adrs/adr-020-criticidade-multidimensional.md](docs/engineering/architecture/adrs/adr-020-criticidade-multidimensional.md)
- [docs/engineering/architecture/adrs/adr-023-bdi-diferenciado-por-categoria.md](docs/engineering/architecture/adrs/adr-023-bdi-diferenciado-por-categoria.md)

---

## Politica de Vigencia

Este ADR entra em vigor na data de aprovacao e substitui criterios ad-hoc de avaliacao de deltas para benchmark no contexto MendesLobo/Concilium.
