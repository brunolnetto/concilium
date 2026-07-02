# ADR-129 — Cotação por Proximidade Geográfica: Municípios de Referência, Distância e População

**Status:** 💡 Proposta
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
| F1 | `MunicipioReferenceClient` (IBGE) com cache em disco | ⬜ Não iniciado |
| F2 | Reconexão do `FuelPriceClient` ao `pu_calculator` (preço por UF, sem proximidade ainda) | ⬜ Não iniciado |
| F3 | Camada de resolução por município mais próximo no `CatalogResolver`, com `raio_cotacao_km` | ⬜ Não iniciado |
| F4 | Critério de desempate por população | ⬜ Não iniciado |

## Definition of Done

### Fase 1-2
- [ ] `MunicipioReferenceClient` retorna coordenadas/população por município com cache válido
- [ ] `pu_calculator` usa `FuelPriceClient` por UF, com fallback para `PRECO_DIESEL_REFERENCIA` documentado e testado

### Fase 3-4
- [ ] `raio_cotacao_km` em `Escopo`, com default de sistema configurável
- [ ] Resolução por proximidade testada com cenário de sítio de obra remoto (sem município dentro do raio → fallback UF)
- [ ] Desempate por população coberto por teste com dois municípios equidistantes

---

## Relacionados

- ADR-032: CPU/Insumo/Jurisdição v2 — modelo de jurisdição que esta ADR estende com uma camada de proximidade
- ADR-066: CatalogResolver — camadas de resolução Master/Jurisdição/Projeto, onde a nova camada de proximidade se insere
- ADR-107: Generalização do tipo de combustível — `TipoCombustivel` usado pelo `FuelPriceClient`
