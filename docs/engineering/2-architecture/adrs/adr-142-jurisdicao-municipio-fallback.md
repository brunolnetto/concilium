# ADR-142 — Jurisdição por Município: Formato de Identificador e Fallback Gracioso

**Status:** ✅ Implementado (infraestrutura) — sem dado real de município populado (ver limitação)
**Data:** 2026-07-16
**Contexto:** MendesLobo Construtora — Concilium
**Dependências:** ADR-038 (motor tributário por jurisdição), ADR-055 (Reforma Tributária CBS/IBS), ADR-066 (CatalogResolver — camadas Master/Jurisdição/Projeto), ADR-129 (cotação por proximidade geográfica — precedente de granularidade municipal para diesel)

---

## Contexto

### Problema

P1. **A resolução de alíquotas tributárias (`AliquotasBdi` = ISS/PIS/COFINS/CPRB) hoje só existe até o nível de UF**, via `Escopo.jurisdicao_id` → `config/jurisdicoes/BR-{UF}.json`. Isso já é uma imprecisão para ISS, que por lei (LC 116/2003) é municipal, não estadual — dois municípios da mesma UF podem ter alíquotas de ISS diferentes, e o sistema hoje resolve os dois para o mesmo valor.

P2. **A Reforma Tributária (EC 132/2023, ADR-055) torna essa lacuna mais visível.** IBS é *destination-based* por desenho — a alíquota efetiva depende de onde o serviço é executado/consumido, incluindo o município de destino, não só o estado. A Seção 7 (Q1) do ADR-055 já registra isso como questão aberta, sem decisão de formato.

P3. **Não existe fonte de dado real de alíquota tributária por município no sistema.** O único precedente de granularidade municipal (`MunicipioReferenceClient`, ADR-129) cobre só as 27 capitais estaduais e resolve "qual UF de referência usar por proximidade geográfica" para preço de diesel — não fornece alíquota tributária real por município. Com ~5.570 municípios brasileiros, cada um com legislação de ISS própria, popular dado real para todos é um problema de aquisição de dado (fonte CNM/prefeituras), não de engenharia — está fora do alcance desta ADR.

P4. **Três pontos do código assumem `jurisdicao_id` com no máximo 2 segmentos** (`BR-{UF}`): os patterns de `Jurisdicao.codigo` (`jurisdicao.py`) e `JurisdicaoVersionada.id` (`versioned.py`), e o parser `_uf_de_jurisdicao()` (`geo_diesel_resolver.py`), que usa `.partition("-")` — quebraria silenciosamente (extrairia UF errada) se um 3º segmento de município fosse introduzido sem correção.

---

## Decisão

### D1 — Formato de 3 segmentos: `BR-{UF}-{MUNICIPIO}`

`jurisdicao_id` ganha um 3º segmento opcional, slug legível em maiúsculas com `_`
como separador de palavras (evita colisão com o `-` que já separa os segmentos):

```
BR-CE                 (hoje, inalterado)
BR-CE-FORTALEZA        (novo, opcional)
BR-RJ-RIO_DE_JANEIRO
```

Escolhido em vez de código IBGE (ex. `BR-CE-2304400`) por legibilidade em
diffs/config JSON versionados em git, consistente com o estilo já usado para UF
(`BR-CE`, não um código numérico de estado). O UF-pai no próprio identificador já
desambigua nomes de município duplicados entre estados.

### D2 — Reaproveitamento total do merge hierárquico existente

`ConfigMixin.load_jurisdicao` (`application/runtime/mixins/config.py`) já faz
merge recursivo por `parent_id`. Um arquivo `BR-CE-FORTALEZA.json` com
`"parent_id": "BR-CE"` é mesclado em cadeia BR ← BR-CE ← BR-CE-FORTALEZA **sem
nenhuma mudança nesse método** — só overrides parciais (ex.: só `ISS`) são
necessários no arquivo de município. O overlay de catálogo por diretório
(`CatalogResolver._load_jurisdiction_overlay`, ADR-066 §F6) também já trata
`jurisdicao_id` como nome de diretório opaco — compatível sem mudança.

### D3 — Correção dos 3 pontos que assumiam 2 segmentos

- `Jurisdicao.codigo` (`jurisdicao.py`): pattern estendido para
  `^[A-Z]{2}(-[A-Z]{2})?(-[A-Z0-9_]{2,40})?$` — mantém toda rejeição existente
  (`"brasil"`, `"BR-CEA"`, `"BR-"`) e aceita o 3º segmento opcional.
- `JurisdicaoVersionada.id` (`versioned.py`): mesma extensão,
  `^[A-Z]{2,15}(-[A-Z]{2,15})?(-[A-Z0-9_]{2,40})?$`.
- `_uf_de_jurisdicao()` (`geo_diesel_resolver.py`): trocado `.partition("-")`
  (só quebra na 1ª ocorrência, extrairia `"CE-FORTALEZA"` como "UF" de um
  identificador de 3 segmentos) por `.split("-")` com acesso a `partes[1]` —
  extrai a UF correta independente do número de segmentos.

### D4 — Fallback gracioso município→UF, nunca falha por município desconhecido

Novo método `ConfigMixin.load_jurisdicao_com_fallback(codigo)`: tenta o
`codigo` exato; se a config não existir (`RuntimeDomainError`) **e** o código
tiver 3 segmentos, remove o último (município) e resolve no nível de UF,
retornando um alerta `VAL-JURISDICAO-MUNICIPIO-01` em vez de lançar. Códigos de
1-2 segmentos continuam idênticos a `load_jurisdicao` (comportamento atual,
zero mudança).

`InputsMixin._apply_defaults_tributos_bdi` (skill 06) passa a usar essa
variante, propagando os alertas para `normalized["avisos_runtime"]`.

### D5 — Nenhum dado real de município populado nesta ADR

Deliberadamente **não** foi criado nenhum arquivo `BR-{UF}-{MUNICIPIO}.json` em
`config/jurisdicoes/` (diretório compartilhado por todos os catálogos,
incluindo `mendeslobo` — dado real de produção). Fabricar uma alíquota que
pareça real para um município específico, sem fonte verificada, alimentaria
cálculo de preço de venda real da empresa com um número inventado — risco
inaceitável. Os testes desta ADR usam fixtures sintéticas via `tmp_path`
(mesmo padrão de `test_config_version_service_jurisdicoes_flat.py`), nunca um
município real.

---

## Alternativas Rejeitadas

| ID | Alternativa | Motivo |
|---|---|---|
| A1 | Código IBGE de 7 dígitos como identificador de município (`BR-CE-2304400`) | Rejeitado por ora — menos legível em diffs/config JSON do que o estilo já usado para UF; pode ser revisitado se/quando houver import automatizado de fonte oficial |
| A2 | Reaproveitar `MunicipioReferenceClient` (ADR-129) para resolver alíquota por proximidade geográfica | Rejeitado — esse client resolve "qual UF de referência usar", não "qual alíquota real deste município exato"; cobre só 27 capitais, não serve como fonte de alíquota tributária |
| A3 | Popular alíquotas reais de um conjunto piloto de municípios (ex.: onde a MendesLobo já opera) já nesta ADR | Rejeitado — exigiria fonte de dado tributário municipal verificada (CNM/prefeitura), que não existe hoje no sistema; ficaria fabricando número que pareceria real |
| A4 | Lançar exceção quando município não tiver config própria, forçando o operador a sempre usar `BR-{UF}` | Rejeitado — pior experiência que o fallback gracioso; um `jurisdicao_id` de município digitado sem querer não deveria quebrar a skill 06 |

---

## Consequências

### Positivas

- Sistema pronto para receber dado real de município assim que uma fonte
  confiável existir, sem exigir nova mudança de schema/parsing.
- Zero regressão: todo `jurisdicao_id` de 1-2 segmentos (100% do uso atual)
  passa pelos mesmos caminhos de código, byte a byte.
- Fallback visível (alerta `VAL-JURISDICAO-MUNICIPIO-01`) em vez de silencioso —
  consistente com o padrão de alertas já usado em `pu_calculator.py`.

### Negativas / Riscos

- Nenhum município tem dado real hoje — a lacuna que motivou esta ADR
  (P1/P2) continua existindo na prática até que dados sejam adquiridos e
  populados; esta ADR resolve a capacidade de representar o dado, não o dado
  em si.
- Convenção nova (`normalized["avisos_runtime"]`) ainda não tem consumidor
  downstream confirmado (skill 09/relatório) — vale checar antes de depender
  dela para exibir o alerta ao usuário final.

---

## Plano de Implementação

1. Estender os 2 patterns (`jurisdicao.py`, `versioned.py`) e corrigir
   `_uf_de_jurisdicao` (`geo_diesel_resolver.py`).
2. Adicionar `ConfigMixin.load_jurisdicao_com_fallback`.
3. Atualizar `InputsMixin._apply_defaults_tributos_bdi` para usar o fallback.
4. Testes novos (`test_adr142_jurisdicao_municipio.py`) + regressão completa da
   suíte de jurisdição/BDI existente.

## Definition of Done

- [x] `Jurisdicao(codigo="BR-CE-FORTALEZA")` aceito; `"BR-CEA"`, `"BR-"`,
      `"brasil"` continuam rejeitados.
- [x] `JurisdicaoVersionada(id="BR-CE-FORTALEZA")` mesma cobertura.
- [x] `_uf_de_jurisdicao("BR-CE-FORTALEZA") == "CE"`.
- [x] `load_jurisdicao_com_fallback`: 3 segmentos com config própria resolve
      normalmente sem alerta; 3 segmentos sem config cai para UF com alerta;
      1-2 segmentos idêntico a `load_jurisdicao`.
- [x] Zero regressão nas suítes existentes de jurisdição/BDI.
- [ ] Dado real de município populado — **fora do escopo**, depende de fonte de
      dado tributário municipal ainda não disponível no sistema.

---

## Relacionados

- ADR-038 (motor tributário por jurisdição, formato `BR-{UF}` original)
- ADR-055 (Reforma Tributária CBS/IBS — Seção 7 Q1 registra esta lacuna)
- ADR-066 (CatalogResolver — camadas Master/Jurisdição/Projeto)
- ADR-129 (cotação por proximidade geográfica — precedente de granularidade
  municipal, para diesel, não reaproveitável diretamente para alíquota
  tributária)
