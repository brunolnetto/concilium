# ADR-129 — Cotação por Proximidade Geográfica: Municípios de Referência, Distância e População

**Status:** ✅ Implementado (2026-07-08) — ver nota de implementação abaixo
**Data:** 2026-07-02
**Contexto:** MendesLobo Construtora — Concilium
**Dependências:** ADR-032 (CPU/Insumo/Jurisdição v2), ADR-066 (CatalogResolver — camadas Master/Jurisdição/Projeto), ADR-107 (tipo_combustivel)

---

## Contexto

### Problema

P1. **A granularidade máxima de preço regional hoje é UF (`jurisdicao_id`, ex.: `"BR-CE"`), nunca município.** `CatalogResolver` (ADR-066) resolve preço em três camadas — Master → JurisdictionOverlay → ProjectOverlay — mas `JurisdictionOverlay` nunca é mais fino que estado. Não existe conceito de município, CEP, ou distância no pipeline de precificação.

P2. **O projeto já tem coordenadas geográficas do sítio de obra, mas elas não influenciam preço.** `Escopo.coordenadas_lat`/`coordenadas_lng` (`domain/models/project/escopo.py`) existem e têm validação de range — mas seu único consumidor real é a skill de produtividade climática (`02-produtividade-climatica`), via `OpenMeteoClient`. Não há nenhuma ponte entre coordenadas e resolução de preço, jurisdição, ou fonte de referência.

P3. **`FuelPriceClient` existe mas está desconectado.** `infrastructure/clients/fuel.py` já consulta preço de diesel por UF via API externa (`combustivelapi.com.br`), mas nenhuma skill/serviço o chama — o preço de diesel usado no cálculo real é a constante nacional única `PRECO_DIESEL_REFERENCIA = 6.50` (`domain/constants.py`), sem qualquer variação regional.

P4. **Não existe client de dados municipais (IBGE, população, distância) no repositório.** Para cotar por proximidade — "usar o preço do município mais próximo com dado disponível, ponderado por população/relevância econômica" — falta a própria fonte de dados municipais, não só a lógica de proximidade.

P5. **Nenhuma ADR ou documento de pesquisa aborda esse tema hoje** — é um espaço em branco confirmado na exploração do codebase, não uma decisão revisitada.

---

## Decisão

### D1 — Novo client de referência municipal (IBGE)

Introduzir `infrastructure/clients/municipios.py` (`MunicipioReferenceClient`), consultando a API de localidades do IBGE (municípios por UF, coordenadas do centróide, população do Censo/estimativa mais recente). Cache em disco por município (mesmo padrão TTL longo já usado em `openmeteo.py`, já que população/coordenadas mudam pouco).

### D2 — Resolução de preço por município mais próximo com dado disponível

Nova camada de resolução entre `JurisdictionOverlay` (UF) e `ProjectOverlay` no `CatalogResolver` (ADR-066): dado `Escopo.coordenadas_lat/lng`, calcular distância (haversine) aos municípios do dataset de referência (D1) e usar o mais próximo dentro de um raio configurável; se nenhum município estiver dentro do raio, cai no comportamento atual (preço por UF).

**Importante sobre a fonte de dado municipal de diesel:** o `FuelPriceClient` (`infrastructure/clients/fuel.py`) hoje só expõe preço médio por **UF** (mapa `fuel -> state -> price`, sem granularidade de município ou ponto de venda) — ele **não** fornece pontos de venda por município, ao contrário do que uma leitura apressada desta ADR poderia sugerir. A resolução por proximidade real depende de uma fonte de dado municipal que ainda não existe no sistema. O piloto tem duas opções: (a) obter esse dado de uma fonte externa nova (ANP publica abertura por município em alguns relatórios — viabilidade de API a confirmar antes da Fase 3), ou (b) usar `MunicipioReferenceClient` (D1, dados IBGE) apenas para coordenadas/população, mantendo o preço em si por UF (`FuelPriceClient`, D3) até uma fonte municipal real ser integrada — nesse cenário, "município mais próximo" ajuda a decidir *qual UF de referência* usar quando o sítio de obra está na borda entre estados, não produz um preço município-específico.

### D3 — Ativação do `FuelPriceClient` como fonte real de preço de diesel

`PRECO_DIESEL_REFERENCIA` deixa de ser a única fonte: `pu_calculator.py` passa a consultar `FuelPriceClient` pela UF (ou município mais próximo, via D2) quando disponível, com fallback para a constante nacional em caso de indisponibilidade da API externa — preservando o comportamento atual como rede de segurança.

### D4 — População como critério de desempate/confiança, não de peso direto no preço

Quando múltiplos municípios de referência estão a distância comparável, usa-se população (via D1) como critério de desempate — prioriza o município mais populoso (maior probabilidade de ter posto de referência estável/mercado líquido) em vez de simplesmente o mais próximo em linha reta. Não se propõe uma fórmula de ponderação preço×população — isso é decisão de negócio a validar com o time antes de qualquer cálculo automático.

### D5 — Campo explícito de raio de busca por projeto

`Escopo` ganha campo opcional `raio_cotacao_km: float | None` (default do sistema, ex.: 100km, sobrescrevível por projeto) — permite ao engenheiro de orçamento calibrar o quão "próximo" é aceitável para aquele sítio de obra específico (zona urbana densa vs. obra remota).

---

## Alternativas Rejeitadas

| ID | Alternativa | Motivo |
|---|---|---|
| A1 | Regionalizar preço só por UF de forma mais fina (mesorregião/microrregião IBGE) sem usar coordenadas | Rejeitado — o sistema já coleta lat/lng do sítio de obra; ignorar esse dado e usar uma divisão administrativa intermediária perde precisão sem necessidade |
| A2 | Ponderar preço diretamente por população (fórmula automática) | Rejeitado por ora — decisão de negócio não validada; risco de introduzir viés não solicitado pelo engenheiro de orçamento (D4 usa população só como desempate) |
| A3 | Buscar preço em tempo real por distância exata a todo posto de combustível (dado privado/pago) | Rejeitado — custo/complexidade de integração com fonte de dados de postos individuais não se justifica frente ao ganho sobre granularidade por município |
| A4 | Deixar `FuelPriceClient` desconectado e regionalizar só material via IBGE | Rejeitado — reconectar o client de combustível é o menor esforço com maior ganho imediato (dado já existe, só falta o fio) |

---

## Consequências

### Positivas

| Efeito | Descrição |
|---|---|
| Precisão de custo de diesel | Preço regional real em vez de constante nacional única |
| Aproveita dado já coletado | `Escopo.coordenadas_lat/lng` ganha um segundo uso além de clima |
| Extensível a outras fontes | A camada de resolução por proximidade (D2) não é específica de diesel — pode acomodar outras referências regionais de preço no futuro |

### Negativas / Riscos

| Risco | Mitigação |
|---|---|
| Dependência de disponibilidade da API do IBGE e da `combustivelapi.com.br` | Cache agressivo (D1) + fallback para constante nacional (D3) em caso de indisponibilidade |
| Ambiguidade quando há empate de distância entre municípios | Critério de desempate por população (D4), documentado explicitamente |
| Nova camada de resolução aumenta a complexidade do `CatalogResolver` | Camada é opt-in por regra objetiva, não por "presença" de coordenadas — `Escopo.coordenadas_lat`/`coordenadas_lng` são campos **obrigatórios** hoje (`Field(ge=-90,le=90)`/`Field(ge=-180,le=180)`, sem default `None`) e várias rotas/tools já preenchem `(0.0, 0.0)` como valor padrão quando o usuário não informa localização real. O opt-in correto é vinculado ao novo campo `raio_cotacao_km` (D5): se ausente/`None`, a camada de proximidade nunca ativa: comportamento por UF é preservado como default. Como salvaguarda adicional, coordenadas `(0.0, 0.0)` (ponto no meio do Atlântico, claramente um placeholder) são tratadas como "sem localização real" mesmo que `raio_cotacao_km` esteja preenchido |
| Escopo de "cotação por proximidade" pode crescer para além de diesel sem controle | Esta ADR restringe D2/D3 a diesel como piloto; expansão a outros insumos requer nova decisão |

---

## Plano de Implementação

| Fase | Entregas | Status |
|---|---|---|
| F1 | `MunicipioReferenceClient` (IBGE) com cache em disco | ✅ Implementado (cache em memória sobre dataset estático — ver nota) |
| F2 | Reconexão do `FuelPriceClient` ao `pu_calculator` (preço por UF, sem proximidade ainda) | ✅ Implementado (`resolver_preco_diesel_uf`) |
| F3 | Camada de resolução por município mais próximo, com `raio_cotacao_km`, integrada ao call site real de precificação de diesel | ✅ Implementado — `geo_diesel_resolver.py` integrado a `06-resultado-financeiro/_precificacao/skill.py::_resolve_preco_diesel_catalogo`, opt-in via `inputs["raio_cotacao_km"]` (ver nota) |
| F4 | Critério de desempate por população | ✅ Implementado |

## Definition of Done

### Fase 1-2
- [x] `MunicipioReferenceClient` retorna coordenadas/população por município com cache válido
- [x] `pu_calculator` usa `FuelPriceClient` por UF, com fallback para `PRECO_DIESEL_REFERENCIA` documentado e testado

### Fase 3-4
- [x] `raio_cotacao_km` em `Escopo`, com default de sistema configurável
- [x] Resolução por proximidade testada com cenário de sítio de obra remoto (sem município dentro do raio → fallback UF)
- [x] Desempate por população coberto por teste com dois municípios equidistantes

### Fase 5 — Integração ao call site real
- [x] `_resolve_preco_diesel_catalogo` (skill de precificação) usa `geo_diesel_resolver` quando `raio_cotacao_km` está em `inputs`, opt-in
- [x] Precedência testada: `preco_diesel` explícito > catálogo > resolução regional > `PRECO_DIESEL_REFERENCIA`
- [x] Regressão zero testada: sem `raio_cotacao_km`, comportamento idêntico ao pré-ADR-129
- [x] Falha da API externa durante a resolução regional não propaga exceção para o pipeline (testado)

## Nota de Implementação (2026-07-08)

Implementado ponta a ponta em nível de **serviço/domínio**, com TDD e cobertura completa:

- `infrastructure/clients/municipios.py` (`MunicipioReferenceClient`, `MunicipioReferencia`,
  `haversine_km`) — D1. **Diferença em relação ao texto original da decisão:** em vez de um
  client HTTP para a API de localidades do IBGE, o dataset de referência (coordenadas de
  centróide + população das capitais estaduais) é estático e embutido
  (`infrastructure/clients/data/municipios_referencia.json`), com cache em memória por
  instância. A API pública de localidades do IBGE não expõe coordenadas nem população num
  único endpoint simples (exigiria compor localidades + malhas geográficas + agregados do
  Censo) — fora do escopo do piloto. A interface isola a fonte via `dataset_path`,
  permitindo trocar por uma integração ao vivo depois sem alterar consumidores.
- `application/catalog/pu_calculator.resolver_preco_diesel_uf` — D3. Reconecta o
  `FuelPriceClient` por UF, com fallback documentado e testado para
  `PRECO_DIESEL_REFERENCIA` quando `uf`/`fuel_client` são `None` ou a API externa falha.
- `Escopo.raio_cotacao_km: float | None` (default `None`) — D5. Constante
  `RAIO_COTACAO_KM_PADRAO_SISTEMA = 100.0` em `domain/constants.py` documenta o valor
  sugerido para novos escopos, sem forçar ativação automática (mantém o opt-in explícito
  descrito em §Riscos).
- `application/services/catalog/geo_diesel_resolver.py` (`resolver_uf_por_proximidade`,
  `resolver_preco_diesel_escopo`) — D2+D4. Resolve o município mais próximo dentro do raio
  (desempate por população quando as distâncias são comparáveis), decidindo qual **UF** de
  referência usar — não um preço município-específico, conforme a ressalva já registrada em
  D2 (o `FuelPriceClient` só expõe preço por UF). Fallback em cascata: proximidade →
  `Escopo.jurisdicao_id` → `PRECO_DIESEL_REFERENCIA`. Trata coordenadas placeholder
  `(0.0, 0.0)` como "sem localização real", mesmo com `raio_cotacao_km` preenchido.

### Integração ao call site real de precificação (2026-07-08, fecha o gap acima)

`06-resultado-financeiro/_precificacao/skill.py::_resolve_preco_diesel_catalogo` — usado por
`run_precificacao_unitaria`, o único ponto de cálculo de PU de diesel em produção — passa a
chamar `geo_diesel_resolver.resolver_preco_diesel` quando `inputs["raio_cotacao_km"]` está
presente. Precedência final (do mais específico ao mais genérico):

```
1. inputs["preco_diesel"]                — override manual explícito (vence sempre)
2. catálogo (MA-DIESEL-S10 / DIESEL-S10) — preço de insumo do catálogo (vence sobre 3-4)
3. geo_diesel_resolver (proximidade → UF → FuelPriceClient)  — só se raio_cotacao_km presente
4. PRECO_DIESEL_REFERENCIA               — comportamento anterior à ADR-129 (default)
```

Decisões de escopo desta integração final:

- **Opt-in explícito via `raio_cotacao_km`**, não automático: reaproveita o mesmo campo de
  opt-in já desenhado em D5, em vez de introduzir uma flag nova. Pipelines/projetos
  existentes que não passam `raio_cotacao_km` em `inputs` continuam com comportamento
  idêntico ao pré-ADR-129 (regressão zero, testada explicitamente) — endereça o risco
  registrado em §Riscos sobre chamadas de rede automáticas sem decisão de produto.
- **Não integrado ao `CatalogResolver` (ADR-066) como camada formal**: o preço de diesel não
  passa hoje pelas camadas Master/Jurisdição/Projeto do `CatalogResolver` — é resolvido
  diretamente na skill de precificação via `PRECO_DIESEL_REFERENCIA`/catálogo. Integrar no
  ponto de cálculo real (skill) é mais direto e testável do que introduzir uma camada nova no
  `CatalogResolver` para um único insumo; a estrutura de `geo_diesel_resolver.py` (função pura,
  sem estado) não impede uma integração futura ao `CatalogResolver` caso o escopo de
  "cotação regional" cresça além de diesel.
- `EscopoGeoLike` (novo `Protocol` estrutural em `geo_diesel_resolver.py`) desacopla
  `resolver_uf_por_proximidade`/`resolver_preco_diesel_escopo` de um `Escopo` completo — a
  skill não tem acesso a um `Escopo` inteiro (só a `inputs`/`canonical_in`), e construir um
  `Escopo` só para isso exigiria preencher campos irrelevantes (`escopo_id`, `data_inicio`,
  etc.). Nova função `resolver_preco_diesel(...)` aceita os 4 valores primitivos relevantes
  diretamente.
- Nenhuma exceção da resolução regional (API externa indisponível, timeout, UF sem preço
  publicado) propaga para o pipeline — já garantido por `resolver_preco_diesel_uf` (D3),
  testado também no novo caminho de integração.

---

## Relacionados

- ADR-032: CPU/Insumo/Jurisdição v2 — modelo de jurisdição que esta ADR estende com uma camada de proximidade
- ADR-066: CatalogResolver — camadas de resolução Master/Jurisdição/Projeto, onde a nova camada de proximidade se insere
- ADR-107: Generalização do tipo de combustível — `TipoCombustivel` usado pelo `FuelPriceClient`
