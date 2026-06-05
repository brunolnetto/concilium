# ADR-045 — Pipeline de Ingestão de Preços SINAPI / SICRO / ANP por Estado

**Status:** Implementado  
**Data:** 2026-05-11  
**Atualizado:** 2026-05-15  
**Contexto:** MendesLobo Construtora — Concilium

---

## Estado de Implementação (2026-05-15)

| Critério | Status | Arquivo |
|---|---|---|
| AC1 `sinapi_fetch.py` download + parse | ✅ | `scripts/sinapi_fetch.py` |
| AC2 `sicro_fetch.py` gera insumos.json | ✅ | `scripts/sicro_fetch.py` (pré-existente) |
| AC3 `anp_fetch.py` gera diesel.json | ✅ | `scripts/anp_fetch.py` — seed verificado + API fallback |
| AC4 `price_resolver.py` injeta regionalizacao + cobertura | ✅ | `scripts/price_resolver.py` — auto-map por Jaccard |
| AC5 `generate_pesquisa.py` gera xlsx 7 abas | ✅ | `scripts/generate_pesquisa.py` |
| AC6 Variação >40% suspende atualização | ✅ | Implementado em `price_resolver.py` |
| AC7 `run_price_update.py` pipeline end-to-end | ✅ | `scripts/run_price_update.py` |
| AC8 `RepositorioInsumo` aceita regionalizacao dict | ✅ | `src/.../repositories/insumo.py` — compat list+dict |

### Resultados na primeira execução (BR-CE, 2026-05-15)

- **36 insumos** atualizados via SICRO (preço + regionalizacao.BR-CE)
- **74 MAO_OBRA** com regionalizacao.BR-CE injetada (custo horário SICRO totalmente carregado)
- **4 suspensos** aceitos manualmente (erros de catálogo confirmados: betoneira R$3/h → R$63/h, vibroacabadora R$33/h → R$430/h, guindaste 40t R$78/h → R$505/h)
- **90/467** insumos com regionalizacao.BR-CE populada
- Diesel CE atualizado: R$7,35/L (ANP semana 2026-W19)
- `pesquisa_CE_2026-01.xlsx` gerada em `config/referencias/pesquisas/`
- `price_source_policy.yaml` criado com 36 mapeamentos auto-gerados

### Execução mensal

```bash
python scripts/run_price_update.py --uf CE --fontes sicro anp --apply --auto-map
python scripts/run_price_update.py --uf CE --fontes all --apply   # com SINAPI quando disponível
```

### Limitações conhecidas

| Limitação | Impacto | Mitigação |
|---|---|---|
| MAO_OBRA: SICRO em R$/h, catálogo em R$/mes | regionalizacao contém custo totalmente carregado, não o salário base | Para cálculo de PU usar `pu_calculator.py` que aplica α por contrato; regionalizacao.BR-CE é referência informativa |
| SINAPI: download requer xlsx do portal CEF | Sem automação full do download | `sinapi_fetch.py --arquivo /path/local/sinapi.xlsx` funciona com arquivo local |
| 148 insumos ainda STALE (pré-2026) | Precisam de pesquisa manual ou extensão do mapeamento | Adicionar entradas em `price_source_policy.yaml` para expandir cobertura |

---

## Contexto

### Problema

O catálogo Concilium (`config/catalogos/mendeslobo/`) usa preços de insumos para gerar
orçamentos, planejamento de execução e benchmarks. Atualmente, esses preços são mantidos
**manualmente**: um engenheiro abre a planilha SINAPI ou SICRO do portal do governo, copia
os valores para os JSONs do catálogo e comita. Isso gera os seguintes problemas:

**P1 — Defasagem sistemática:** O SINAPI publica atualizações mensais; o SICRO, trimestralmente
(pela política mais recente do DNIT). Em ambos, o intervalo médio entre publicação e atualização
no catálogo tem sido de 60–180 dias. Orçamentos baseados em preços defasados geram margens
fictícias que só são percebidas na fase contratual.

**P2 — Cobertura parcial por estado:** O `sicro_concilium_mapping.yaml` mapeia insumos
para o SICRO mas os preços regionalizados no catálogo existem apenas para os estados onde
a empresa fez obras recentes (CE, SP, GO, MT). Para uma licitação no PA ou no RJ, o time
precisa fazer pesquisa manual ad hoc — sem rastreabilidade nem histórico.

**P3 — Diesel sem fonte estruturada:** O preço do diesel é o insumo de maior sensibilidade
em obras de terraplenagem e pavimentação (representa até 18% do custo direto de projetos
rodoviários). A ANP publica pesquisa semanal por município. Hoje, o diesel entra como
estimativa do engenheiro sem vínculo com dados reais de mercado.

**P4 — Manutenção divergente entre SINAPI e SICRO:** Para o mesmo insumo (ex: cimento
CP-II, brita graduada), o SINAPI e o SICRO publicam preços que podem divergir ±15%.
Sem um pipeline que unifique e registre a escolha de fonte, o catálogo mistura origens
de forma inconsistente, tornando auditorias impossíveis.

**P5 — Ausência de pesquisa_ESTADO.xlsx estruturada:** O processo atual de licitação
exige como documento de instrução uma planilha de pesquisa de preços de mercado por UF
(`pesquisa_CE.xlsx`, `pesquisa_GO.xlsx` etc.). Hoje essa planilha é preenchida
manualmente a cada nova proposta, replicando o problema P1 e P3.

### Oportunidade Técnica

A infraestrutura de referências já está parcialmente montada:
- `config/referencias/SICRO/BR-{UF}/insumos.json` existe para todas as 27 UFs (SICRO 4 / Jan-2026).
- `scripts/sicro_inject.py` já lê o mapeamento YAML e injeta `regionalizacao` nos insumos.
- `config/referencias/SICRO/sicro_concilium_mapping.yaml` define o de-para SICRO → Concilium.

O que falta é: (a) automação do download, (b) pipeline equivalente para SINAPI e ANP,
(c) lógica de resolução de conflitos entre fontes, e (d) geração da planilha de saída.

---

## Decisão

### Visão Geral da Arquitetura

```
┌──────────────────────────────────────────────────────────────────────────┐
│                     PIPELINE DE INGESTÃO DE PREÇOS                       │
│                                                                          │
│  Fontes Externas         Fetch Layer          Transform Layer   Saída    │
│  ─────────────────   ──────────────────   ──────────────────   ──────── │
│  portal SINAPI/CEF ──► sinapi_fetch.py ──►                              │
│  portal SICRO/DNIT ──► sicro_fetch.py  ──► price_resolver.py ──► catál. │
│  portal ANP        ──► anp_fetch.py   ──►                      pesquisa │
│                                             mapping.yaml                 │
└──────────────────────────────────────────────────────────────────────────┘
```

O pipeline é composto de três stages independentes (um por fonte) mais uma stage de
resolução e saída. Cada stage produz um artefato JSON imutável versionado por `{UF}-{AAAA-MM}`.

---

### D1 — Fontes de Dados e Responsabilidades

| Fonte | Mantenedor | Cadência | Cobertura | Insumos relevantes |
|---|---|---|---|---|
| **SINAPI** | Caixa Econômica Federal | Mensal | Todos os 27 estados | Materiais de construção civil, mão de obra não-desonerada e desonerada |
| **SICRO 4** | DNIT | Trimestral (meta) | Todos os 27 estados | Equipamentos, materiais rodoviários, mão de obra especializada em infraestrutura, composições unitárias |
| **ANP** | Agência Nacional do Petróleo | Semanal | Por município | Diesel S-10 e S-500 (combustível de obra), óleo lubrificante |

**Prioridade de fonte por categoria de insumo:**

```yaml
prioridade_fontes:
  EQUIPAMENTO:
    - SICRO      # Custo horário de equipamento com depreciação e operação
    - SINAPI     # Fallback para equipamentos não listados no SICRO
  MAO_OBRA:
    - SICRO      # Salários + encargos conforme tabela DNIT
    - SINAPI     # Fallback (inclui salário sem encargos sociais detalhados)
  MATERIAL_RODOVIARIO:
    - SICRO      # Brita, CBUQ, solos, insumos de pavimentação
    - SINAPI     # Fallback
  MATERIAL_CIVIL:
    - SINAPI     # Cimento, aço, madeira, tubos de PVC, esquadrias
    - SICRO      # Fallback quando o item existe no SICRO
  COMBUSTIVEL:
    - ANP        # Sempre — preço real de mercado por UF (média estadual da semana mais recente)
    - SICRO      # Fallback se ANP não disponível para a UF no período
```

> **Nota:** A prioridade é configurável por insumo no arquivo `price_source_policy.yaml`
> (ver D3). Para insumos com divergência > 15% entre SINAPI e SICRO, o pipeline sinaliza
> conflito e usa a fonte prioritária — mas registra o conflito no artefato de saída.

---

### D2 — Stage 1: Fetch por Fonte

#### 2a. `sinapi_fetch.py` — SINAPI/CEF

O SINAPI publica tabelas em `.xlsx` no portal `caixa.gov.br`. O script realiza download
programático via URL parametrizada por UF e mês:

```
https://www.caixa.gov.br/Downloads/sinapi-custo-ref-insumos-{uf}/{ANO}/{MES}/SINAPI_ref_insumos_{UF}_{AAAA}{MM}_NaoDesonerado.xlsx
```

**Estrutura de saída (`config/referencias/SINAPI/BR-{UF}/insumos.json`):**

```json
{
  "$schema": "https://concilium.framework/schemas/v1/tabela_referencia",
  "provedor": "SINAPI",
  "versao": "2026-01",
  "jurisdicao": "BR-CE",
  "data_vigencia": "2026-01-01",
  "url_fonte": "https://www.caixa.gov.br/Downloads/...",
  "imutavel": true,
  "insumos": [
    {
      "codigo_referencia": "00001",
      "descricao": "ADITIVO ACELERADOR DE PEGA E RESISTENCIA, PARA CONCRETO",
      "tipo": "MATERIAL",
      "unidade": "KG",
      "preco_publicado": 3.07,
      "origem": "FABRICADO"
    }
  ]
}
```

**Parâmetros CLI:**
```bash
python scripts/sinapi_fetch.py --uf CE --mes 2026-01
python scripts/sinapi_fetch.py --uf all --mes 2026-01      # todas as 27 UFs
python scripts/sinapi_fetch.py --uf SP --mes latest        # mês mais recente publicado
```

#### 2b. `sicro_fetch.py` — SICRO 4/DNIT

O SICRO 4 publica relatórios em `.xlsx` por categoria (Equipamentos, Materiais, Mão de Obra)
num arquivo `.7z` por UF e trimestre no portal `gov.br/dnit`. O script baixa, extrai e
parseia os três relatórios, produzindo `insumos.json`, `cpus.json` e `producoes.json`
(formato já existente em `config/referencias/SICRO/BR-{UF}/`).

> **Nota:** Para o SICRO, o fetch já está parcialmente implementado (os JSONs existem
> para Jan/2026). O `sicro_fetch.py` formaliza o processo que hoje é manual.

#### 2c. `anp_fetch.py` — ANP

A ANP publica resultados da Pesquisa de Preços de Combustíveis em `.csv` na plataforma
de dados abertos (`dados.gov.br`). O endpoint REST retorna dados semanais por município:

```
https://dados.gov.br/dados/conjuntos-dados/serie-historica-de-precos-de-combustiveis-por-revenda
```

O script filtra por `PRODUTO = "ÓLEO DIESEL S10"` e `ESTADO = {UF}`, calcula a média
ponderada pelo volume por município e persiste por semana de referência:

**Estrutura de saída (`config/referencias/ANP/BR-{UF}/diesel.json`):**

```json
{
  "$schema": "https://concilium.framework/schemas/v1/tabela_referencia",
  "provedor": "ANP",
  "versao": "2026-W10",
  "jurisdicao": "BR-CE",
  "data_vigencia": "2026-03-07",
  "imutavel": true,
  "combustiveis": [
    {
      "produto": "DIESEL_S10",
      "unidade": "l",
      "preco_medio_ponderado": 5.397,
      "preco_min": 5.19,
      "preco_max": 5.69,
      "n_postos": 312,
      "municipio_mais_barato": "Fortaleza",
      "municipio_mais_caro": "Crateús"
    },
    {
      "produto": "DIESEL_S500",
      "unidade": "l",
      "preco_medio_ponderado": 5.241,
      ...
    }
  ]
}
```

**Parâmetros CLI:**
```bash
python scripts/anp_fetch.py --uf CE --semana latest
python scripts/anp_fetch.py --uf all --semana 2026-W10
```

---

### D3 — Mapeamento de Códigos (Catálogo ↔ Fontes)

O arquivo `sicro_concilium_mapping.yaml` é estendido para cobrir SINAPI e ANP:

```yaml
# config/referencias/price_source_policy.yaml

meta:
  versao: "2.0"
  atualizado_em: "2026-05-11"
  nota: "Única fonte de verdade para de-para entre códigos externos e Concilium"

mappings:

  # Cada entrada define um insumo Concilium e suas fontes por prioridade
  - concilium_id: "MA-DIESEL-S10"
    descricao: "Óleo diesel S-10"
    categoria: "COMBUSTIVEL"
    unidade_concilium: "l"
    fontes:
      - provedor: "ANP"
        produto: "DIESEL_S10"
        unidade_fonte: "l"
        fator_conversao: 1.0
        prioridade: 1
      - provedor: "SICRO"
        codigo: "M0043"
        unidade_fonte: "l"
        fator_conversao: 1.0
        prioridade: 2

  - concilium_id: "MA-CIMENTO-CPII-50KG"
    descricao: "Cimento Portland CP-II-E-32"
    categoria: "MATERIAL_CIVIL"
    unidade_concilium: "kg"
    fontes:
      - provedor: "SINAPI"
        codigo: "00379"
        unidade_fonte: "KG"
        fator_conversao: 1.0
        prioridade: 1
      - provedor: "SICRO"
        codigo: "M0178"
        unidade_fonte: "kg"
        fator_conversao: 1.0
        prioridade: 2

  - concilium_id: "MA-BRITA-1"
    descricao: "Brita 1 (9,5–19 mm)"
    categoria: "MATERIAL_RODOVIARIO"
    unidade_concilium: "m3"
    fontes:
      - provedor: "SICRO"
        codigo: "M0191"
        unidade_fonte: "m3"
        fator_conversao: 1.0
        prioridade: 1
      - provedor: "SINAPI"
        codigo: "00009"
        unidade_fonte: "M3"
        fator_conversao: 1.0
        prioridade: 2

  - concilium_id: "EQ-ESCAVADEIRA-20T"
    descricao: "Escavadeira hidráulica 20t — custo horário"
    categoria: "EQUIPAMENTO"
    unidade_concilium: "h"
    fontes:
      - provedor: "SICRO"
        codigo: "E9058"
        unidade_fonte: "h"
        fator_conversao: 1.0
        prioridade: 1
      # Sem fallback SINAPI — equipamentos são cobertos pelo SICRO apenas
```

**Regras de mapeamento:**

| Situação | Comportamento |
|---|---|
| `sicro_codigo: null` | Insumo pulado (skipped); registrado em `relatorio_cobertura.json` |
| Insumo presente na fonte mas ausente no mapeamento | Ignora (pull nunca puxa sem de-para explícito) |
| Unidades divergentes (ex: "sc" vs "kg") | `fator_conversao` obrigatório; erro se ausente |
| Preço diverge > 15% entre fontes de mesma prioridade | Sinaliza `conflito = true`; usa fonte de maior prioridade |
| Preço negativo ou zero | Invalida entrada; mantém preço anterior no catálogo |

---

### D4 — Stage 2: Resolução e Injeção no Catálogo

O script `price_resolver.py` é o orquestrador da stage de transformação. Para cada
insumo Concilium com mapeamento definido, ele:

1. Lê os artefatos de cada fonte para a UF/mês especificados.
2. Resolve o preço pela prioridade de fonte definida no mapeamento.
3. Aplica `fator_conversao` para normalização de unidade.
4. Faz upsert do bloco `regionalizacao` no JSON do insumo do catálogo.
5. Persiste metadados de rastreabilidade (fonte, data de referência, código externo).

**Estrutura atualizada no JSON do insumo (output):**

```json
{
  "codigo": "MA-DIESEL-S10",
  "descricao": "Óleo diesel S-10",
  "tipo": "MATERIAL",
  "unidade": "l",
  "preco_base": 5.40,
  "regionalizacao": {
    "BR-CE": {
      "preco": 5.397,
      "fonte_provedor": "ANP",
      "fonte_codigo_externo": "DIESEL_S10",
      "data_referencia": "2026-03-07",
      "versao_tabela": "2026-W10",
      "conflito_detectado": false,
      "preco_fonte_secundaria": null,
      "atualizado_em": "2026-05-11T14:32:00Z"
    },
    "BR-SP": {
      "preco": 5.612,
      "fonte_provedor": "ANP",
      "fonte_codigo_externo": "DIESEL_S10",
      "data_referencia": "2026-03-07",
      "versao_tabela": "2026-W10",
      "conflito_detectado": false,
      "preco_fonte_secundaria": null,
      "atualizado_em": "2026-05-11T14:32:00Z"
    }
  }
}
```

> A estrutura `regionalizacao` muda de lista (formato atual do `sicro_inject.py`)
> para dict com chave `jurisdicao_id`. O `sicro_inject.py` existente será deprecado
> e substituído pelo `price_resolver.py`.

**Parâmetros CLI:**
```bash
# Atualiza catálogo para uma UF com a tabela mais recente disponível
python scripts/price_resolver.py --uf CE

# Atualiza todas as UFs para uma data de referência específica
python scripts/price_resolver.py --uf all --data-ref 2026-01

# Dry-run: exibe o diff sem gravar
python scripts/price_resolver.py --uf SP --dry-run

# Relatório de cobertura apenas (sem atualizar catálogo)
python scripts/price_resolver.py --uf GO --relatorio-apenas
```

---

### D5 — Stage 3: Geração de `pesquisa_ESTADO.xlsx`

O script `generate_pesquisa.py` lê os dados já injetados no catálogo (e as tabelas
de referência brutas) e gera a planilha de pesquisa de preços usada como documento
de instrução de licitação.

**Estrutura da planilha `pesquisa_{UF}_{AAAA-MM}.xlsx`:**

| Aba | Conteúdo |
|---|---|
| `Resumo` | Metadata (UF, data referência, fontes utilizadas, versão do catálogo) |
| `SINAPI` | Insumos com origem SINAPI — código, descrição, unidade, preço, data publicação |
| `SICRO` | Insumos com origem SICRO — idem + código SICRO, produção associada |
| `ANP` | Combustíveis — produto, preço médio, min, max, n_postos, semana referência |
| `Conflitos` | Insumos com divergência > 15% entre fontes, com ambos os preços |
| `Sem_cobertura` | Insumos sem mapeamento ou sem tabela disponível para a UF |

**Parâmetros CLI:**
```bash
python scripts/generate_pesquisa.py --uf CE --data-ref 2026-01
python scripts/generate_pesquisa.py --uf GO --data-ref 2026-03 --output-dir ./pesquisas/
```

**Onde o arquivo é salvo:**
```
config/referencias/pesquisas/
  pesquisa_CE_2026-01.xlsx
  pesquisa_SP_2026-01.xlsx
  pesquisa_GO_2026-03.xlsx
```

---

### D6 — Tratamento de Erros e Resiliência

| Categoria | Falha | Comportamento |
|---|---|---|
| **Download** | Timeout / HTTP 5xx | Retry com backoff exponencial (3 tentativas, 10s/30s/60s) |
| **Download** | HTTP 404 (tabela não publicada para o mês) | Sinaliza no log; usa tabela do período anterior com aviso |
| **Download** | Formato inesperado do xlsx (colunas renomeadas pelo governo) | Abort + alerta explícito; nunca silencia parsing incorreto |
| **Mapeamento** | `concilium_id` sem mapeamento para a fonte | Skip silencioso + registro em `relatorio_cobertura.json` |
| **Preço** | Variação > 40% vs mês anterior para o mesmo insumo/UF | Suspende a atualização desse insumo; requer confirmação manual |
| **Catálogo** | JSON de insumo corrompido ou schema inválido | Abort + não atualiza outros insumos; mantém estado anterior |
| **ANP** | Dados de menos de 30 postos para a UF | Usa média estadual da semana anterior + aviso de baixa amostragem |

**Artefato de rastreabilidade (`relatorio_cobertura.json`):**

```json
{
  "uf": "CE",
  "data_referencia": "2026-01",
  "executado_em": "2026-05-11T14:32:00Z",
  "resumo": {
    "mapeamentos_totais": 87,
    "atualizados": 74,
    "sem_preco_na_fonte": 8,
    "conflitos_detectados": 3,
    "variacao_anomala": 2,
    "erros_parse": 0
  },
  "skipped": [
    { "concilium_id": "MA-BGTC-MIX", "motivo": "composicao_sicro_sem_codigo_material" }
  ],
  "conflitos": [
    {
      "concilium_id": "MA-AREIA-MEDIA",
      "preco_sinapi": 68.50,
      "preco_sicro": 59.20,
      "divergencia_pct": 15.7,
      "fonte_usada": "SICRO",
      "motivo_prioridade": "MATERIAL_RODOVIARIO"
    }
  ],
  "variacoes_anomalas": [
    {
      "concilium_id": "EQ-ROLO-COMPACTADOR",
      "preco_anterior": 120.50,
      "preco_novo": 198.30,
      "variacao_pct": 64.6,
      "acao": "suspenso_aguarda_confirmacao"
    }
  ]
}
```

---

### D7 — Execução Programada (Automação)

O pipeline completo é orquestrado pelo script `run_price_update.py`, projetado para
ser executado via agendador (Windows Task Scheduler ou GitHub Actions):

```bash
# Execução mensal completa (todas as UFs, fontes, gera planilhas)
python scripts/run_price_update.py --uf all --fontes sinapi sicro anp --mes latest

# Execução emergencial para uma UF (ex: nova licitação no PA)
python scripts/run_price_update.py --uf PA --fontes all --mes 2026-03
```

**Ordem de execução:**
1. `sinapi_fetch.py` → artefato SINAPI por UF
2. `sicro_fetch.py` → artefato SICRO por UF (se nova versão disponível)
3. `anp_fetch.py` → artefato ANP por UF (semana mais recente)
4. `price_resolver.py` → injeta no catálogo
5. `generate_pesquisa.py` → gera planilha Excel
6. Log de cobertura salvo em `config/referencias/pesquisas/logs/`

---

### D8 — Estrutura de Arquivos (Estado Final)

```
config/referencias/
  SINAPI/
    BR-CE/
      insumos_2026-01.json      ← artefato imutável por mês
      insumos_2026-02.json
    BR-SP/
      insumos_2026-01.json
    ...
  SICRO/
    BR-CE/
      insumos.json              ← artefato existente (Jan/2026)
      cpus.json
      producoes.json
    ...
    sicro_concilium_mapping.yaml   ← DEPRECADO em favor de price_source_policy.yaml
  ANP/
    BR-CE/
      diesel_2026-W10.json
      diesel_2026-W11.json
    ...
  pesquisas/
    pesquisa_CE_2026-01.xlsx
    pesquisa_SP_2026-01.xlsx
    logs/
      cobertura_CE_2026-01.json
  price_source_policy.yaml    ← de-para unificado (substitui sicro_concilium_mapping.yaml)
```

---

## Alternativas Consideradas

### A1 — Serviço de scraping em tempo real (pull-on-demand)
Buscar preços em tempo real a cada orçamento, sem persistir artefatos.

**Rejeitada:** Dependência de disponibilidade dos portais em horário de orçamento.
Portal SINAPI tem instabilidade conhecida em dias de publicação. Sem artefato imutável,
auditoria retroativa impossível (viola ADR-041 / SCD Type 2). Latência inaceitável
para uso interativo no Concilium.

### A2 — Banco de dados relacional para preços
Substituir os JSONs por tabelas PostgreSQL.

**Rejeitada para este ciclo:** Os JSONs são suficientes para a escala atual
(~27 UFs × ~2.000 insumos × 12 meses = ~648K registros). A adoção de banco introduziria
dependência de infra sem benefício imediato. Pode ser revisitado via ADR separado quando
o volume justificar.

### A3 — API paga (ex: PINI, Volare)
Contratar serviço comercial de inteligência de preços.

**Rejeitada:** Custo recorrente sem vantagem competitiva para uma construtora que já
tem acesso direto às fontes públicas. Além disso, dependência de terceiro para dado
que é público e gratuito. Pode ser acrescentada como fonte adicional (`prioridade: 3`)
sem alterar esta arquitetura.

---

## Consequências

### Positivas

| # | Benefício | Impacto estimado |
|---|---|---|
| C1 | Preços sempre atualizados (máximo 30 dias de defasagem para SINAPI) | Margens orçamentárias mais precisas |
| C2 | Cobertura de 27 UFs para diesel via ANP | Habilita licitações em qualquer estado sem pesquisa manual |
| C3 | Rastreabilidade total (fonte + data + código externo por insumo por UF) | Conformidade com requisitos de auditoria de licitação pública |
| C4 | `pesquisa_ESTADO.xlsx` gerada automaticamente | Reduz de ~4h para <5min o tempo de preparação de documento de instrução |
| C5 | Conflitos entre fontes explicitados | Decisões de fonte documentadas, não implícitas |
| C6 | Histórico imutável por mês/UF | Integra com ADR-041 (SCD Type 2) — reprocessamento histórico de orçamentos possível |

### Negativas / Riscos

| # | Risco | Mitigação |
|---|---|---|
| R1 | Governo altera estrutura das colunas do xlsx sem aviso | Parser com validação de schema + alertas imediatos; não silencia erros de parsing |
| R2 | Portal fora do ar na data de atualização | Retry + fallback para tabela anterior com aviso explícito de defasagem |
| R3 | Mapeamento desatualizado (insumo novo no catálogo sem de-para) | `relatorio_cobertura.json` lista todos os gaps; revisão mensal do mapeamento como checklist obrigatório |
| R4 | Divergência SINAPI vs SICRO > 15% em insumo crítico | Conflito registrado + decisão de fonte documentada; revisão manual requerida |
| R5 | Preço ANP representa média estadual, não o município da obra | Para obras em regiões remotas (AM interior, PA Norte), o preço real pode ser 20–30% superior; aplicar fator de logística via ADR-032 (regionalizacao) |

### Débito Técnico Introduzido

- `scripts/sicro_inject.py` torna-se deprecated mas permanece funcional até que o
  `price_resolver.py` cubra todos os mapeamentos existentes. Período de transição
  estimado: 1 sprint de desenvolvimento.
- A estrutura `regionalizacao` muda de lista para dict. Todos os consumidores
  (`RepositorioInsumo`, skill-04 via `catalog_loader.py`) precisam ser adaptados
  para aceitar ambos os formatos durante a transição.

---

## Critérios de Aceitação (para marcar como Implementado)

| # | Critério |
|---|---|
| AC1 | `sinapi_fetch.py --uf CE --mes 2026-01` baixa e parseia a tabela sem erro |
| AC2 | `sicro_fetch.py --uf CE --mes 2026-01` gera `insumos.json` equivalente ao arquivo manual existente |
| AC3 | `anp_fetch.py --uf CE --semana latest` gera `diesel.json` com preço médio estadual |
| AC4 | `price_resolver.py --uf CE` injeta `regionalizacao` em todos os insumos com mapeamento e gera `relatorio_cobertura.json` |
| AC5 | `generate_pesquisa.py --uf CE` gera `pesquisa_CE_2026-01.xlsx` com abas Resumo, SINAPI, SICRO, ANP, Conflitos |
| AC6 | Insumo com variação > 40% é suspenso e NÃO atualiza o catálogo |
| AC7 | `run_price_update.py --uf all --mes latest` executa pipeline completo sem erros em todos os 27 estados |
| AC8 | `RepositorioInsumo.preco_em(codigo, data, jurisdicao)` retorna preço correto usando a nova estrutura `regionalizacao` dict |

---

## Arquivos a Criar / Modificar

| Ação | Arquivo | Descrição |
|---|---|---|
| CRIAR | `scripts/sinapi_fetch.py` | Stage 1a: download + parse SINAPI por UF/mês |
| CRIAR | `scripts/sicro_fetch.py` | Stage 1b: download + extração SICRO por UF/trimestre |
| CRIAR | `scripts/anp_fetch.py` | Stage 1c: fetch ANP diesel por UF/semana |
| CRIAR | `scripts/price_resolver.py` | Stage 2: resolução de fonte + injeção no catálogo |
| CRIAR | `scripts/generate_pesquisa.py` | Stage 3: geração `pesquisa_ESTADO.xlsx` |
| CRIAR | `scripts/run_price_update.py` | Orquestrador completo (pipeline end-to-end) |
| CRIAR | `config/referencias/price_source_policy.yaml` | De-para unificado (substitui sicro_concilium_mapping.yaml) |
| CRIAR | `config/referencias/pesquisas/` | Diretório de saída das planilhas |
| DEPRECAR | `scripts/sicro_inject.py` | Substituído por `price_resolver.py` |
| MODIFICAR | `src/concilium/infrastructure/catalog/catalog_loader.py` | Adaptar para ler `regionalizacao` como dict |
| MODIFICAR | `config/referencias/SICRO/sicro_concilium_mapping.yaml` | Migrar entradas para `price_source_policy.yaml` |

---

## Referências

- ADR-038 — Catálogo Regionalizado e Tributação por Jurisdição
- ADR-041 — SCD Type 2 para Rastreabilidade Histórica do Catálogo
- ADR-032 — CPU Insumo Jurisdição v2 (fator de logística regional)
- Portal SINAPI: https://www.caixa.gov.br/poder-publico/apoio-poder-publico/sinapi
- Portal SICRO 4: https://www.gov.br/dnit/pt-br/assuntos/planejamento-e-pesquisa/custos-referenciais/sistemas-de-custos/sicro
- Dados Abertos ANP: https://dados.gov.br/dados/conjuntos-dados/serie-historica-de-precos-de-combustiveis-por-revenda
