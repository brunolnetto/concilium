# ADR-070: Exploracao Deterministica do Espaco de Configuracao Operacional para Viabilidade de GO

**Status:** Implementado ✅ _(auditado 2026-06-09)_

> **Nota:** `plan_space` e exploração determinística presentes no código.
**Data:** 2026-05-23
**Autor:** Engenheiro Senior
**Relacionado:** ADR-004, ADR-005, ADR-006, ADR-020, ADR-021, ADR-022, ADR-051, ADR-060, ADR-061

---

## 1. Contexto

A operacao precisa encontrar configuracoes viaveis de GO a partir de um baseline tecnico consistente.

Hoje, o sistema executa planejamento e classificacao com qualidade de benchmark, mas nao possui um mecanismo canonico para:

1. explorar sistematicamente variacoes controladas de entrada,
2. classificar alternativas em escala,
3. curar um conjunto final auditavel de melhores configuracoes.
4. versionar uma campanha de pesquisa que consolide ranges, composicoes e expectativas de avaliacao.

A ausencia desse mecanismo limita a descoberta de solucoes operacionais melhores quando o baseline inicial nao atende simultaneamente prazo, custo e viabilidade de execucao.

---

## 2. Problema

### P1 - Falta de motor de busca de alternativas
Nao existe um servico dedicado para gerar e avaliar multiplos cenarios de GO por projeto.

### P2 - Ajustes manuais pouco escalaveis
A calibracao por tentativa manual depende de especialista e nao escala com numero de atividades.

### P3 - Risco de exploracao sem governanca
Sem contrato formal, uma busca automatica pode variar parametros sensiveis sem trilha de auditoria.

### P4 - Conhecimento tacito de composicao de equipes
Composicao de times nao pode ser variada livremente em grid-search puro sem degradar semantica de negocio.

### P5 - Ausencia de curadoria formal
Mesmo com varios cenarios avaliados, nao ha regra deterministica padrao para selecionar top alternativas.

### P6 - Metrica objetivo unica mascara trade-offs
Combinar todas as saidas em um unico escalar tende a esconder conclusoes composicionais entre dimensoes operacionais e economico-financeiras/fidelidade.

---

## 3. Decisao

### D1 - Introduzir um motor de exploracao deterministica
Criar um servico de aplicacao para explorar espaco de configuracao operacional com entrada tipada e reproducivel.

Nome proposto:
`GoConfigurationSearchService`

### D2 - Separar parametros por nivel de risco semantico
A busca v1 variara somente parametros controlaveis de baixo risco:

1. `ramp_up_rate`
2. `ramp_down_rate`
3. `team_max_count`
4. `productivity_boost_pct`

### D3 - Tratar composicao de equipes como escolha discreta governada
Em vez de variacao livre da composicao, a v1/v2 deve usar:

1. catalogo de templates de equipe aprovados,
2. selecao discreta entre templates,
3. bloqueio de combinacoes fora de politica.

### D4 - Reusar semaforo oficial de viabilidade
A classificacao de cada cenario deve usar o mesmo contrato de decisao do pipeline:

1. `APROVADO`
2. `APROVADO_COM_RESSALVAS`
3. `BLOQUEADO_COM_INVESTIGACAO`
4. `BLOQUEADO`

No nivel de item, manter classes existentes (`IDEAL`, `ATENCAO`, `PREOCUPANTE`, `CRITICO`) para explainability.

### D5 - Definir curadoria deterministica e auditavel
A selecao final sera feita por algoritmo deterministico:

1. filtrar cenarios viaveis,
2. construir fronteira de Pareto,
3. aplicar tie-break estavel por risco operacional, custo e hash do cenario,
4. retornar `top_k` com justificativa explicita.

### D6 - Persistir trilha de auditoria por execucao
Cada run devera persistir:

1. espaco de busca solicitado,
2. constraints aplicadas,
3. resultado por cenario,
4. ranking final,
5. versao da politica de curadoria.

### D7 - Instituir o conceito de Campanha de Pesquisa
Toda exploracao deve ocorrer dentro de uma entidade versionada:

`GoResearchCampaignBundle`

Esse bundle versiona, no minimo:

1. parametros de entrada (intervalos e discretizacoes),
2. politicas de composicao (templates e restricoes),
3. constraints operacionais,
4. definicao dos espacos de avaliacao,
5. perfil de expectativas para categorizacao,
6. politica de curadoria e desempate.

### D8 - Avaliar em dois espacos multidimensionais sem colapso em escalar unico
A avaliacao da campanha deve separar explicitamente:

1. Espaco O (Operacional),
2. Espaco EF/F (Economico-Financeiro e Fidelidade).

No espaco EF/F, cada metrica deve ser categorizada por expectativa:

1. `DENTRO_EXPECTATIVA`,
2. `ATENCAO`,
3. `FORA_EXPECTATIVA`.

A decisao final nao deve depender de uma metrica agregada unica.

---

## 4. Modelo Operacional

### 4.1 Entradas

`GoResearchCampaignBundle` (proposto):

1. identificacao do projeto/escopo/plano,
2. versao da campanha (`campaign_version`),
3. baseline de referencia,
4. ranges/discretizacoes por parametro,
5. politicas de composicao (templates aprovados),
6. constraints operacionais,
7. definicao de espaco O,
8. definicao de espaco EF/F,
9. perfil de expectativas EF/F por metrica,
10. politica de curadoria,
11. `top_k`.

### 4.2 Avaliacao por cenario

Para cada cenario:

1. aplicar transformacoes controladas sobre baseline,
2. executar pipeline de planejamento,
3. coletar vetor de metricas no espaco O,
4. coletar vetor de metricas no espaco EF/F,
5. categorizar metricas EF/F conforme perfil de expectativas,
6. classificar decisao de viabilidade,
7. armazenar evidencia.

### 4.3 Curadoria

Curadoria em camadas, sem escalar unico:

1. filtro por restricoes duras,
2. fronteira de Pareto no espaco O,
3. fronteira de Pareto no espaco EF/F,
4. intersecao prioritaria entre nao-dominados de ambos os espacos,
5. tie-break deterministico estavel.

Representacao vetorial:

$$
I_O(x)=(prazo, violacao\_capacidade, churn\_equipes, mobilizacao)
$$

$$
I_{EF/F}(x)=(\Delta custo\_direto, \Delta custo\_indireto, \Delta preco\_venda, margem, fidelidade\_gates)
$$

Com restricao dura de viabilidade:

$$
status\_final(x) \in \{APROVADO, APROVADO\_COM\_RESSALVAS\}
$$

Perfil de expectativa (exemplo por metrica EF/F):

1. `DENTRO_EXPECTATIVA`: valor dentro da faixa alvo da campanha,
2. `ATENCAO`: valor em faixa de alerta,
3. `FORA_EXPECTATIVA`: valor fora da tolerancia da campanha.

---

## 5. Alternativas Rejeitadas

| ID | Alternativa | Motivo |
|---|---|---|
| A1 | Grid-search irrestrito incluindo composicao de equipe livre | Alto risco semantico e explosao combinatoria |
| A2 | Curadoria puramente subjetiva por agente sem ranking deterministico | Reduz auditabilidade e reprodutibilidade |
| A3 | Heuristica unica sem exploracao de espaco | Pode perder solucoes viaveis superiores |
| A4 | Otimizacao estocastica sem seed/versionamento | Dificulta replay e governanca |
| A5 | Objetivo combinado unico (soma ponderada de todas as metricas) | Mascara trade-offs e reduz explainability composicional |

---

## 6. Consequencias

### Positivas

1. Padroniza descoberta de configuracoes viaveis de GO.
2. Reduz dependencia de tentativa manual ad hoc.
3. Mantem governanca por trilha auditavel e regra deterministica.
4. Permite acoplamento opcional de agente sobre shortlist qualificada.
5. Preserva leitura composicional ao separar espacos O e EF/F.
6. Versiona integralmente a campanha de pesquisa como bundle reproduzivel.

### Negativas / Riscos

1. Explosao de combinacoes em ranges amplos.
2. Risco de overfitting em cenarios de benchmark.
3. Custo computacional maior em projetos grandes.
4. Complexidade adicional na definicao de perfil de expectativas por metrica.

### Mitigacoes

1. Pruning por constraints e limites de cardinalidade.
2. Busca hierarquica (global -> cluster -> atividade).
3. Politica de amostragem inicial + refinamento local.
4. Seed fixa, versao de politica e artefato de replay.
5. Biblioteca de perfis de expectativa reutilizaveis por tipo de projeto.

---

## 7. Plano de Implementacao

| Fase | Entregas | Status |
|---|---|---|
| F1 | Contrato tipado `GoResearchCampaignBundle` e `GoSearchResult` + persistencia de run versionado | Proposto |
| F2 | Motor de geracao/avaliacao para parametros v1 (sem composicao livre) | Proposto |
| F3 | Curadoria deterministica em dois espacos (Pareto O + Pareto EF/F + tie-break estavel) | Proposto |
| F4 | Catalogo de templates de equipe e selecao discreta | Proposto |
| F5 | Endpoint/API de exploracao e relatorio executivo de alternativas | Proposto |

---

## 8. Definition of Done

### Fase 1
- [ ] Contratos tipados definidos e versionados.
- [ ] Entidade `GoResearchCampaignBundle` persistida com `campaign_version`.
- [ ] Artefato de auditoria persistido por run.

### Fase 2
- [ ] Busca v1 executa para ranges de ramp up/down, team max e produtividade.
- [ ] Classificacao de viabilidade reaproveita semaforo oficial.

### Fase 3
- [ ] Ranking final reprodutivel com intersecao de Pareto entre espacos O e EF/F.
- [ ] Perfil de expectativas EF/F aplicado com categorias `DENTRO_EXPECTATIVA`, `ATENCAO`, `FORA_EXPECTATIVA`.
- [ ] Replay de execucao reproduz top_k identico com mesmos inputs.

### Fase 4
- [ ] Composicao de equipe operando por templates aprovados.
- [ ] Bloqueio de configuracoes fora de politica.

### Fase 5
- [ ] API exposta com filtros e pagina de resultados.
- [ ] Export de shortlist com justificativas e rastreabilidade.

---

## 9. Politica de Governanca

1. Toda variacao de parametro deve declarar fonte, limite e responsavel.
2. Toda mudanca da funcao de ranking deve incrementar versao de politica.
3. Nenhum resultado sem trilha de auditoria pode ser promovido como recomendacao.
4. Curadoria por agente e opcional; curadoria deterministica e obrigatoria.
5. Toda campanha deve explicitar perfil de expectativas EF/F versionado no bundle.
