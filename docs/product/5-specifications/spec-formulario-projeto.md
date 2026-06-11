# Especificação: Formulário de Criação de Projeto (QQP/EAP)

**Versão:** 2.0  
**Data:** 2026-06-11  
**Relacionado:** ADR-092, ADR-091, ADR-101, ADR-055, ADR-090, ADR-105, ADR-106  
**Schema canônico:** `config/schemas/projeto_spec.schema.json`  
**Ponto de entrada MCP:** `criar_projeto_formulario` em `mcp/tools/formulario.py`  
**App interativo:** `mcp/apps/formulario-qqp/index.html`

---

## Visão Geral

O formulário traduz a linguagem natural do engenheiro de campo (QQP) em uma estrutura canônica (EAP com CPUs) pronta para o pipeline de planejamento.

```
Engenheiro digita          →  Formulário QQP   →  ProjetoSpec          →  Pipeline 01→...→09
"Escavar 380k m³ 1ª cat."  →  Busca semântica  →  {cpu_id, quantity}  
```

O formulário tem **7 seções** (2 novas vs v1.0) mais uma etapa de mapeamento de CPUs.

---

## Seção 1 — Identificação do Projeto

Todos obrigatórios exceto `coordenadas`, `data_termino` e `regime_tributario`.

| Campo | Tipo | Obrigatório | Restrições | Exemplo |
|---|---|---|---|---|
| `meta.nome` | string | ✅ | minLength: 1 | `"Ferrovia Transnordestina — Lote 09/10"` |
| `meta.contexto_id` | string | ✅ | minLength: 1 | `"mendeslobo"` |
| `meta.tipo_obra` | enum | ✅ | §Enums | `"terraplenagem"` |
| `meta.localizacao` | string | ✅ | "Cidade, UF" | `"Quixadá, CE"` |
| `meta.data_inicio` | date | ✅ | ISO 8601 | `"2026-08-01"` |
| `meta.data_termino` | date | — | ISO 8601 | `"2027-04-30"` |
| `meta.coordenadas.lat` | number | ✅* | −90 ≤ lat ≤ 90 | `−4.98` |
| `meta.coordenadas.lng` | number | ✅* | −180 ≤ lng ≤ 180 | `−39.02` |

> \* `{lat: 0, lng: 0}` é aceito como default. Com coordenadas reais, skill-02 consulta Open-Meteo para fator climático semanal; sem elas, `fator_clima = 1.0` em todas as semanas.

### Enums: `tipo_obra`

| Valor | Quando usar |
|---|---|
| `"terraplenagem"` | Escavação, compactação, supressão, terraplenagem geral |
| `"pavimentacao"` | Base, sub-base, CBUQ, concreto de cimento |
| `"saneamento"` | Água, esgoto, drenagem pluvial urbana |
| `"drenagem"` | Canais, bueiros, galerias fluviais |
| `"obras_arte"` | Pontes, viadutos, muros de arrimo, fundações |
| `"diversos"` | Combinação de tipos ou não classificado |

---

## Seção 2 — Regime de Trabalho

| Campo | Tipo | Obrigatório | Range | Default |
|---|---|---|---|---|
| `meta.regime_trabalho.dias_semana` | int | — | 1–7 | **6** |
| `meta.regime_trabalho.horas_dia` | int | — | 1–24 | **8** |

> `horas_semana = dias_semana × horas_dia` determina `C_r^{sem}` (custo semanal de todos os recursos) e a duração de cada atividade. Uma mudança de 8→10 h/dia reduz duração em 20% e aumenta custo semanal em 25%.

### Objetivo de Otimização do Pool

| Campo | Valores | Default | Descrição |
|---|---|---|---|
| `objetivo_pool` | `"balanceado"` · `"minimizar_prazo"` · `"minimizar_custo"` | `"balanceado"` | Critério do RCPSP solver |

- **`minimizar_prazo`** → pool = pico de demanda concorrente (máximo paralelismo, maior custo)
- **`minimizar_custo`** → pool = mínimo serial (menor custo, maior makespan)
- **`balanceado`** → bissecção entre os dois extremos, respeitando `data_termino − data_inicio` como prazo máximo

---

## Seção 3 — BDI e Regime Tributário _(elaborado)_

O BDI (Benefícios e Despesas Indiretas) é calculado pela fórmula TCU (Acórdão 2622/2013):

```
BDI_categoria = [(1+AC)(1+DF)(1+R)(1+CR)(1+L)] / (1 − T) − 1
```

onde `AC` = administração central, `DF` = despesas financeiras, `R` = risco, `CR` = canteiro/residencial, `L` = lucro, `T` = soma das alíquotas tributárias.

### 3.1 Regime Tributário

| Campo | Tipo | Default | Notas |
|---|---|---|---|
| `meta.regime_tributario.regime` | enum | `"lucro_presumido"` | `"lucro_presumido"` · `"simples_nacional"` · `"lucro_real"` |
| `meta.regime_tributario.jurisdicao_id` | string | derivado de `localizacao` | código IBGE/ISO ex: `"BR-CE"` — determina ISS municipal |
| `meta.regime_tributario.iss` | float | jurisdição | 0–0.05 (max legal 5%) — varia por município |
| `meta.regime_tributario.pis` | float | regime | 0–1 — `lucro_presumido`: 0.65%; `simples`: 0% |
| `meta.regime_tributario.cofins` | float | regime | 0–1 — `lucro_presumido`: 3.0%; `simples`: 0% |
| `meta.regime_tributario.cprb` | float | regime | 0–1 — varia por atividade; padrão: 0% |

**Impacto no BDI por categoria:**

| Categoria | T padrão (lucro_presumido, ISS=5%) | BDI padrão |
|---|---|---|
| `mao_obra` | ISS=5%, CSSL=1.99%, IR=2.74% ← MO isenta COFINS/PIS | ~29.97% |
| `servicos` | ISS=5%, CSSL=1.99%, IR=2.74% | ~29.97% |
| `material` | isento (ADR-090: diesel = material, BDI=4%) | 4.00% |
| `diesel` | isento (SV-31: locação → material, não serviço) | 4.00% |
| `indireto` | ISS=5%, CSSL=1.99%, IR=2.74% | ~25.21% |

> ISS não incide sobre locação de equipamentos (SV-31/STF) — apenas sobre serviços de operação.

### 3.2 Lucro Objetivo por Categoria

Se omitido, o sistema usa os defaults do perfil do contexto (mendeslobo: 9% direto, 5% indireto).

| Campo | Tipo | Range | Default |
|---|---|---|---|
| `meta.bdi_lucro.mao_obra` | float | 0–1 | 0.09 |
| `meta.bdi_lucro.material` | float | 0–1 | 0.04 |
| `meta.bdi_lucro.servicos` | float | 0–1 | 0.09 |
| `meta.bdi_lucro.indireto` | float | 0–1 | 0.05 |
| `meta.bdi_lucro.diesel` | float | 0–1 | 0.04 |

### 3.3 Reforma Tributária CBS/IBS (ADR-055)

Para projetos com previsão de vigência pós-reforma (2026+):

| Campo | Tipo | Default | Notas |
|---|---|---|---|
| `meta.regime_tributario.regime_version` | enum | `"PRE_REFORMA"` | `"PRE_REFORMA"` · `"CBS_IBS_2026"` |

Em `"CBS_IBS_2026"`, o sistema usa `resolver_bdi_cbs_ibs()` que aplica créditos de CBS/IBS e recalcula a componente `DF`. A alíquota efetiva líquida é menor para empresas que aproveitam créditos integrais.

---

## Seção 4 — Custos Indiretos _(novo — padrão mendeslobo)_

Os custos indiretos cobrem a infraestrutura de canteiro, supervisão, mobilização e segurança da obra. São **monetizados por permanência**: `custo_total = custo_mensal × permanencia_meses` (exceto MOB, que tem estrutura de fases).

**Padrão mendeslobo derivado dos benchmarks AGIS, MARA_ROSA e ROSH:**

| Categoria | O que cobre | Driver | Padrão/mês (ref. AGIS 12.93m) |
|---|---|---|---|
| **ADM** | Gerência, engenharia, infra de escritório, geradores, veículos leves | mensal | R$ 1.06M/mês |
| **TOP** | Topografia, técnicos de campo, veículo de levantamento | mensal | R$ 67k/mês |
| **LAB** | Laboratorista de solos/materiais | mensal | R$ 11k/mês |
| **QSMS** | Técnico de segurança, sinalização, programa PGR | mensal | R$ 59k/mês |
| **MOB** | Transporte de máquinas + mobilização de mão-de-obra | fases | R$ 4.05M (total único) |

### 4.1 Estrutura por Categoria ADM / TOP / LAB / QSMS

Cada categoria aceita decomposição em três componentes mensais:

| Campo | Tipo | Default | Notas |
|---|---|---|---|
| `indiretos.{CAT}.mao_obra_mensal` | number | benchmark | Salários + encargos CLT/PJ do time indireto |
| `indiretos.{CAT}.equipamentos_mensal` | number | benchmark | Locação de veículos, geradores, computadores |
| `indiretos.{CAT}.verbas_mensais` | number | benchmark | Alimentação, hospedagem, telecom, energia, água |
| `indiretos.{CAT}.verbas_unicas` | number | 0 | Setup inicial: containers, EPIs, mobiliário (amortizado no primeiro mês) |
| `indiretos.{CAT}.custo_fixo_mensal` | number | Σ acima | Override total — quando os sub-campos não estão disponíveis |

> `custo_fixo_mensal = mao_obra_mensal + equipamentos_mensal + verbas_mensais` é derivado automaticamente quando sub-campos fornecidos. Ou informar diretamente `custo_fixo_mensal` como total.

### 4.2 Estrutura MOB — Fases (ADR-105 F4-F5)

MOB tem três fases com semântica distinta:

```json
"indiretos": {
  "MOB": [
    {
      "fase": "mobilizacao",
      "driver": "projeto",
      "custo_fixo_total": 4054600.43,
      "descricao": "Transporte de equipamentos + mobilização de mão-de-obra + alimentação estadia inicial",
      "categorias": ["equipamentos", "mao_obra", "verbas"]
    },
    {
      "fase": "operacao",
      "driver": "mensal",
      "custo_fixo_mensal": 0.0,
      "descricao": "Canteiro de obras permanente — quando não classificado em ADM"
    },
    {
      "fase": "desmobilizacao",
      "driver": "projeto",
      "custo_fixo_total": 0.0,
      "descricao": "Retorno de equipamentos e encerramento do canteiro"
    }
  ]
}
```

| Campo | Tipo | Notas |
|---|---|---|
| `fase` | enum | `"mobilizacao"` · `"operacao"` · `"desmobilizacao"` |
| `driver` | enum | `"projeto"` (one-time) · `"mensal"` (recorrente) |
| `custo_fixo_total` | number | Para `driver="projeto"` — incorre na 1ª / última semana |
| `custo_fixo_mensal` | number | Para `driver="mensal"` — distribuído pelas semanas de operação |

### 4.3 Defaults do Contexto Mendeslobo

Quando `indiretos` é omitido, o sistema usa os defaults derivados dos benchmarks calibrados:

| Categoria | Default por mês | Base empírica |
|---|---|---|
| ADM | proporcional ao porte da obra | média AGIS + MARA_ROSA |
| TOP | 6.3% do ADM | padrão observado |
| LAB | 1.0% do ADM | padrão observado |
| QSMS | 5.5% do ADM | padrão observado |
| MOB | 38% da soma ADM × permanência | padrão observado |

> Os defaults são substituídos integralmente quando qualquer campo de `indiretos` é fornecido.

---

## Seção 5 — QQP / Serviços (EAP)

Mínimo de **1 item** por escopo; mínimo de **1 escopo**.

### 5.1 Escopo

| Campo | Tipo | Obrigatório | Notas |
|---|---|---|---|
| `escopos[].escopo_id` | string | ✅ | ex: `"esc-lote09-10"` |
| `escopos[].nome` | string | ✅ | ex: `"Supressão e Terraplenagem"` |
| `escopos[].eap` | array | ✅ | minItems: 1 |

### 5.2 Item EAP

| Campo | Tipo | Obrigatório | Restrições | Notas |
|---|---|---|---|---|
| `item_id` | string | ✅ | minLength: 1 | ex: `"eap-1_1"` |
| `cpu_id` | string | ✅ | código válido no catálogo | ex: `"CPU-TERRA-ESCO-CARGA-1CAT-DMT2000"` |
| `quantitativo` | number | ✅ | > 0 | ex: `380000.0` |
| `predecessores` | array | — | default `[]` | ver §5.3 |

### 5.3 Predecessores

| Campo | Tipo | Default | Valores / Range |
|---|---|---|---|
| `predecessores[].item_id` | string | — | item_id de outro item EAP |
| `predecessores[].tipo` | enum | `"FS"` | `"FS"` · `"SS"` · `"FF"` |
| `predecessores[].lag` | int | `0` | ≥ 0 (dias) |
| `predecessores[].completion_threshold_pct` | float | `1.0` | 0–1 |

**`completion_threshold_pct`:** fração de produção do predecessor necessária para o sucessor iniciar. Ex: `0.35` = B pode começar quando A atingir 35% de sua produção (ADR-081 threshold parcial).

---

## Seção 6 — Cronograma por Item (hints + parâmetros de mob)

Se omitida, skill-04 usa `AUTO_SCHEDULE` derivando `n_max` do catálogo.

| Campo | Tipo | Range | Default | Notas |
|---|---|---|---|---|
| `cronograma[].item_id` | string | ref EAP | — | |
| `cronograma[].n_equipes.n_inicial` | int | ≥ 1 | `1` | Frentes na abertura do ramp (mobilização) |
| `cronograma[].n_equipes.n_max` | int | ≥ 1 | catálogo | Pico de frentes simultâneas — **determina o pool** |
| `cronograma[].producao_diaria` | number | > 0 | catálogo | Override de produtividade do catálogo |
| `cronograma[].leadtime_mob_semanas` | int | ≥ 0 | `2` | Semanas de mobilização antes da produção (§6.1) |
| `cronograma[].lag_demob_semanas` | int | ≥ 0 | `1` | Semanas de desmobilização após última produção (§6.1) |

### 6.1 Leadtime de Mobilização e Lag de Desmobilização _(elaborado — ADR-106 F5)_

**`leadtime_mob_semanas`** = semanas entre a mobilização da equipe/equipamento e o início da produção efetiva. Cobre: transporte de máquinas, chegada da equipe, treinamentos, regularizações de segurança.

**`lag_demob_semanas`** = semanas entre a última semana produtiva e o encerramento completo do contrato de locação. Cobre: retorno de equipamentos, limpeza final do sítio, inspeções de devolução.

**Custo da janela de mob (ADR-106 F5):**
```
custo_mob_window  = (C_r_mo + C_r_locacao) × leadtime_mob_semanas
custo_demob_window = (C_r_mo + C_r_locacao) × lag_demob_semanas
```
Combustível **não** entra na janela — não há produção (e portanto não há consumo de combustível) durante mobilização/desmobilização.

**Hierarquia de resolução:**

```
1. spec.cronograma[item].leadtime_mob_semanas  ← override por item (este campo)
2. CPU.mob_policy.leadtime_mob_semanas         ← catálogo por tipo de CPU
3. DEFAULT_LEADTIME_MOB_SEMANAS = 2            ← constante global
```

**Defaults calibrados pelo porte de obra:**

| Tipo de obra | `leadtime_mob` sugerido | `lag_demob` sugerido |
|---|---|---|
| Terraplenagem ferrovia (grande porte) | 3–4 semanas | 2 semanas |
| Terraplenagem urbana (médio porte) | 1–2 semanas | 1 semana |
| Drenagem / obra arte (pequeno porte) | 1 semana | 1 semana |

> Quando omitido: `leadtime=2, lag=1` (constantes `DEFAULT_LEADTIME_MOB_SEMANAS` e `DEFAULT_LAG_DEMOB_SEMANAS` em `constants.py`).

---

## Seção 7 — Restrições de Mercado de Recursos _(elaborado — ADR-091)_

**Default: `{}` (irrestrito)** — o pool pode alocar tantos recursos quanto necessário para cumprir o prazo. Esta é a postura correta para que o solver RCPSP possa branch-prune pela heurística de pool mínimo (ADR-091).

Quando especificadas, as restrições **cap** a disponibilidade máxima de um tipo de recurso, modelando escassez regional de equipamentos ou mão-de-obra especializada.

```json
"restricoes_mercado": {
  "EQUIPE-CPU-TERRA-ESCO-CARGA-3CAT-DMT2000": 2,
  "EQUIPE-CPU-TERRA-ATI-003": 3
}
```

| Campo | Tipo | Default | Notas |
|---|---|---|---|
| `restricoes_mercado` | dict `{string: int}` | `{}` | Chave = `tipo_recurso`; Valor = máximo disponível no mercado local |

### Semântica e Impacto

| Situação | Comportamento |
|---|---|
| `restricoes_mercado = {}` | Pool irrestrito — solver usa peak demand ou n_max, sem cap |
| `restricao[r] ≥ pool_inferido[r]` | Sem impacto — restrição não vincula |
| `restricao[r] < pool_inferido[r]` | Pool capiado em `restricao[r]` → makespan aumenta |
| `restricao[r] < serial_min[r]` | Projeto **inviável** com essa restrição — sinalizado em `diagnostico.notas` |

### Como o tipo_recurso é formado

O `tipo_recurso` é o campo `EQUIPE-{cpu_id}` gerado pelo catálogo para cada CPU. Pode ser verificado via `listar_recursos_pool(project_id)` após executar skill-03.

### Quando usar

| Contexto | Exemplo |
|---|---|
| Equipamento escasso na região | Somente 1 escavadeira 48T disponível em Quixadá |
| Mão-de-obra especializada limitada | Máximo 3 operadores de motoniveladora na praça |
| Compartilhamento entre lotes | 2 escavadeiras compartilhadas com obra adjacente |
| Demo / análise de sensibilidade | Simular impacto de restrição de mercado no prazo |

---

## Mapeamento CPU (Resolução de cpu_id)

O formulário resolve `descricao → cpu_id` em dois níveis:

| Nível | Score | Mecanismo | Confiança |
|---|---|---|---|
| 1 | 2 — "alta" | Todas as palavras-chave de `cpu_mapping_rules.json` coincidem | Automático |
| 2 | 1 — "media" | ≥ 2 palavras (>3 chars) coincidem com descrição do catálogo | Requer confirmação |
| 3 | 0 — "nenhuma" | Sem correspondência | Requer `cpu_id` explícito |

Quando há itens com confiança `< alta`, o sistema retorna `status: "pendente_mapeamento"` com sugestões.

---

## Fluxo de Criação

```
1. Seções 1–3: Identificação + Regime + BDI/Tributação
2. Seção 4: Indiretos (ou aceitar defaults do contexto mendeslobo)
3. Seção 5: QQP em linguagem natural → busca semântica de CPUs
4. Confirmar/corrigir mapeamentos → status: "pendente_mapeamento" se incompleto
5. Seção 6: Cronograma (n_max, leadtime, lag) — opcional
6. Seção 7: Restrições de mercado — opcional, default irrestrito
7. Criar projeto → status: "criado" → project_id + escopo_id + plano_id
   → skill-01 executada automaticamente
```

---

## Exemplos

### Mínimo (só obrigatórios)

```json
{
  "meta": {
    "nome": "Estrada Vicinal AL-112",
    "contexto_id": "mendeslobo",
    "tipo_obra": "terraplenagem",
    "localizacao": "Arapiraca, AL",
    "coordenadas": { "lat": -9.75, "lng": -36.66 },
    "data_inicio": "2026-09-01",
    "data_termino": "2027-03-31"
  },
  "escopos": [{
    "escopo_id": "esc-al112",
    "nome": "Lote Único",
    "eap": [
      { "item_id": "eap-1_1", "cpu_id": "CPU-TERRA-ATI-003",                 "quantitativo": 180000 },
      { "item_id": "eap-1_2", "cpu_id": "CPU-TERRA-ESCO-CARGA-1CAT-DMT2000", "quantitativo": 95000 },
      { "item_id": "eap-1_3", "cpu_id": "CPU-TERRA-COMPAC-PN",               "quantitativo": 85000 }
    ]
  }]
}
```

### Completo (todos os parâmetros)

```json
{
  "meta": {
    "nome": "Ferrovia Transnordestina — Lote 09/10",
    "contexto_id": "mendeslobo",
    "tipo_obra": "terraplenagem",
    "localizacao": "Quixadá, CE",
    "coordenadas": { "lat": -4.98, "lng": -39.02 },
    "data_inicio": "2026-08-01",
    "data_termino": "2027-04-30",
    "regime_trabalho": { "dias_semana": 6, "horas_dia": 8 },
    "regime_tributario": {
      "regime": "lucro_presumido",
      "jurisdicao_id": "BR-CE",
      "iss": 0.02
    },
    "bdi_lucro": {
      "mao_obra": 0.09,
      "material": 0.04,
      "servicos": 0.09,
      "indireto": 0.05,
      "diesel": 0.04
    }
  },
  "indiretos": {
    "ADM": {
      "mao_obra_mensal": 415101.27,
      "equipamentos_mensal": 271467.37,
      "verbas_mensais": 316504.96,
      "verbas_unicas": 113165.87
    },
    "TOP": {
      "custo_fixo_mensal": 66742.70
    },
    "LAB": {
      "custo_fixo_mensal": 10847.25
    },
    "QSMS": {
      "custo_fixo_mensal": 58739.06
    },
    "MOB": [
      { "fase": "mobilizacao",    "driver": "projeto", "custo_fixo_total": 3646088.26 },
      { "fase": "operacao",       "driver": "mensal",  "custo_fixo_mensal": 0.0 },
      { "fase": "desmobilizacao", "driver": "projeto", "custo_fixo_total": 408512.17 }
    ]
  },
  "escopos": [{
    "escopo_id": "esc-lote09-10",
    "nome": "Supressão e Terraplenagem",
    "eap": [
      {
        "item_id": "eap-1_0",
        "cpu_id": "CPU-TERRA-ATI-003",
        "quantitativo": 2400000,
        "predecessores": []
      },
      {
        "item_id": "eap-1_1",
        "cpu_id": "CPU-TERRA-ESCO-CARGA-1CAT-DMT2000",
        "quantitativo": 107463,
        "predecessores": [
          { "item_id": "eap-1_0", "tipo": "FS", "completion_threshold_pct": 0.05 }
        ]
      }
    ],
    "cronograma": [
      {
        "item_id": "eap-1_0",
        "n_equipes": { "n_inicial": 1, "n_max": 6 },
        "leadtime_mob_semanas": 3,
        "lag_demob_semanas": 2
      },
      {
        "item_id": "eap-1_1",
        "n_equipes": { "n_inicial": 1, "n_max": 1 },
        "leadtime_mob_semanas": 2,
        "lag_demob_semanas": 1
      }
    ]
  }],
  "restricoes_mercado": {}
}
```

---

## Gaps Residuais (v2.0)

| Campo | Status | Quando resolver |
|---|---|---|
| `perfil_bdi_id` override por referência | Não exposto | Quando houver biblioteca de perfis BDI pré-cadastrados por tipo_obra |
| Itemização de verbas de indiretos | Não exposto | Quando integrar parsing de indiretos.*.txt no formulário (NEP-029) |
| `CPU.mob_policy.leadtime_mob_semanas` | Ausente no catálogo | Quando enriquecer o catálogo por CPU (permite defaults por tipo de máquina) |
| Faseamento de indiretos por semana | Parcial (só via ADR-105 driver) | Quando o formulário tiver editor de timeline |

---

## Referências

- `config/schemas/projeto_spec.schema.json` — JSON Schema canônico
- `src/concilium/domain/models/bdi/_profiles.py` — PerfilBdiProjeto, TabelaBdi
- `src/concilium/domain/models/bdi/_components.py` — ComponentesBdi, fórmula TCU
- `src/concilium/domain/constants.py` — DEFAULT_LEADTIME_MOB_SEMANAS, DEFAULT_LAG_DEMOB_SEMANAS
- `src/concilium/application/scheduling/pool_inference.py` — restricoes_mercado
- ADR-055 — Reforma tributária CBS/IBS
- ADR-081 — Predecessência com completion_threshold_pct
- ADR-090 — Diesel como material (SV-31/STF)
- ADR-091 — Pool mínimo como variável de otimização
- ADR-105 — Mobilização/Desmobilização fases
- ADR-106 F5 — mob_window + lag_demob
