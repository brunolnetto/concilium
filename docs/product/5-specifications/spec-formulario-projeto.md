# Especificação: Formulário de Criação de Projeto (QQP/EAP)

**Versão:** 1.0  
**Data:** 2026-06-11  
**Relacionado:** ADR-092 (Formulário QQP/EAP), ADR-091 (Pool Mínimo), ADR-101 (MCP Apps)  
**Schema canônico:** `config/schemas/projeto_spec.schema.json`  
**Ponto de entrada MCP:** `criar_projeto_formulario` em `mcp/tools/formulario.py`  
**App interativo:** `mcp/apps/formulario-qqp/index.html`

---

## Visão Geral

O formulário de criação de projeto traduz a linguagem natural do engenheiro de campo (QQP — Quem, Quanto, Por quê) em uma estrutura canônica (EAP com CPUs mapeadas) pronta para execução do pipeline de planejamento.

```
Engenheiro digita          →   Formulário        →   ProjetoSpec          →   Pipeline
"Escavar 380k m³ 1ª cat."  →   Busca semântica   →   {cpu_id: "CPU-...",  →   01→...→09
                                por CPU_ID        →    quantitativo: 380k}
```

O formulário tem **5 seções** e **uma etapa de mapeamento** intermediária quando CPUs não são resolvidas automaticamente.

---

## Seção 1 — Identificação do Projeto

**Todos os campos são obrigatórios exceto `coordenadas`, `data_termino` e `regime_tributario`.**

| Campo | Tipo | Obrigatório | Restrições | Exemplo |
|---|---|---|---|---|
| `meta.nome` | string | ✅ | minLength: 1 | `"Ferrovia Transnordestina — Lote 09/10"` |
| `meta.contexto_id` | string | ✅ | minLength: 1 | `"mendeslobo"` |
| `meta.tipo_obra` | enum | ✅ | ver §Enums | `"terraplenagem"` |
| `meta.localizacao` | string | ✅ | formato "Cidade, UF" | `"Quixadá, CE"` |
| `meta.data_inicio` | date | ✅ | ISO 8601 `YYYY-MM-DD` | `"2026-08-01"` |
| `meta.data_termino` | date | — | ISO 8601 `YYYY-MM-DD` | `"2027-04-30"` |
| `meta.coordenadas.lat` | number | ✅* | −90 ≤ lat ≤ 90 | `−4.98` |
| `meta.coordenadas.lng` | number | ✅* | −180 ≤ lng ≤ 180 | `−39.02` |

> \* `coordenadas` é um objeto required no schema mas aceita `{lat: 0, lng: 0}` como default quando não informado. O pipeline de clima usa as coordenadas reais para Open-Meteo; default degrada para sem ajuste climático.

### Enums: `tipo_obra`

| Valor | Descrição |
|---|---|
| `"terraplenagem"` | Movimentação de terra, escavações, compactação |
| `"pavimentacao"` | Base, sub-base, revestimento asfáltico/concreto |
| `"saneamento"` | Água, esgoto, resíduos |
| `"drenagem"` | Canais, bueiros, galerias |
| `"obras_arte"` | Pontes, viadutos, muros de arrimo |
| `"diversos"` | Tipos combinados ou não classificados |

---

## Seção 2 — Regime de Trabalho

| Campo | Tipo | Obrigatório | Range | Default | Notas |
|---|---|---|---|---|---|
| `meta.regime_trabalho.dias_semana` | int | — | 1–7 | **6** | Dias trabalhados por semana |
| `meta.regime_trabalho.horas_dia` | int | — | 1–24 | **8** | Horas produtivas por dia |

> `horas_semana = dias_semana × horas_dia` é o multiplicador principal de produtividade. Altera duração de todas as atividades e `C_r^{sem}` (custo semanal de recursos).

### Parâmetro de Otimização de Pool

| Campo | Tipo | Obrigatório | Valores | Default |
|---|---|---|---|---|
| `objetivo_pool` | enum | — | `"balanceado"` · `"minimizar_prazo"` · `"minimizar_custo"` | `"balanceado"` |

- `minimizar_prazo` → pool = pico de demanda concorrente (maior makespan mínimo, maior custo)
- `minimizar_custo` → pool = mínimo viável serial (menor custo, maior makespan)
- `balanceado` → bissecção com `prazo_maximo_semanas = data_termino − data_inicio`

> Este campo é passado via `inputs_cronograma.rcpsp_spec.pool_config.objetivo` na spec.

---

## Seção 3 — Regime Tributário

Todos os campos são **opcionais**. Se omitidos, o sistema deriva alíquotas padrão a partir de `jurisdicao_id` (via SINAPI/jurisdição do contexto).

| Campo | Tipo | Range | Descrição |
|---|---|---|---|
| `meta.regime_tributario.jurisdicao_id` | string | código IBGE/ISO | Jurisdição para derivar alíquotas; ex: `"BR-CE"` |
| `meta.regime_tributario.iss` | number | 0–1 | ISS — Imposto Sobre Serviços |
| `meta.regime_tributario.pis` | number | 0–1 | PIS/Pasep |
| `meta.regime_tributario.cofins` | number | 0–1 | COFINS |
| `meta.regime_tributario.cprb` | number | 0–1 | Contribuição Previdenciária sobre Receita Bruta |

> Estes campos alimentam o `BDI.tributacao` em skill-06. ISS não se aplica à locação de equipamentos (ADR-090/SV-31).

---

## Seção 4 — QQP / Serviços (EAP)

Mínimo de **1 item** por escopo; mínimo de **1 escopo**.

### 4.1 Escopo

| Campo | Tipo | Obrigatório | Notas |
|---|---|---|---|
| `escopos[].escopo_id` | string | ✅ | minLength: 1; ex: `"esc-lote09-10"` |
| `escopos[].nome` | string | ✅ | ex: `"Escopo Principal"` |
| `escopos[].eap` | array | ✅ | minItems: 1 |

### 4.2 Item EAP

| Campo | Tipo | Obrigatório | Restrições | Notas |
|---|---|---|---|---|
| `item_id` | string | ✅ | minLength: 1 | ex: `"eap-1_1"` |
| `cpu_id` | string | ✅ | código válido no catálogo | ex: `"CPU-TERRA-ESCO-CARGA-1CAT-DMT2000"` |
| `quantitativo` | number | ✅ | > 0 | ex: `380000.0` |
| `predecessores` | array | — | default `[]` | ver §4.3 |

> Na entrada via formulário (linguagem natural), `cpu_id` pode ser omitido. O sistema sugere via busca semântica. Para criação do projeto, `cpu_id` deve ser confirmado.

### 4.3 Predecessores (Dependências entre Atividades)

| Campo | Tipo | Obrigatório | Valores / Range | Default |
|---|---|---|---|---|
| `predecessores[].item_id` | string | ✅ | item_id de um outro item EAP | — |
| `predecessores[].tipo` | enum | — | `"FS"` · `"SS"` · `"FF"` | `"FS"` |
| `predecessores[].lag` | int | — | ≥ 0 (dias) | `0` |
| `predecessores[].completion_threshold_pct` | float | — | 0–1 | `1.0` |

**Tipos de dependência:**

| Tipo | Significado | Quando usar |
|---|---|---|
| `FS` | Finish-to-Start — B começa após A terminar | padrão sequencial |
| `SS` | Start-to-Start — B começa após A começar | atividades paralelas com precedência |
| `FF` | Finish-to-Finish — B termina após A terminar | encerramento coordenado |

**`completion_threshold_pct`:** fração de conclusão do predecessor necessária para o sucessor poder iniciar. Ex: `0.35` significa que B pode começar quando A completar 35% de sua produção (RCPSP com threshold parcial, ADR-081).

---

## Seção 5 — Hints de Cronograma por Item (opcional)

Se omitidos, skill-04 usa `AUTO_SCHEDULE` com `n_max` do catálogo.

| Campo | Tipo | Obrigatório | Range | Default | Notas |
|---|---|---|---|---|---|
| `cronograma[].item_id` | string | ✅* | ref para `eap[].item_id` | — | |
| `cronograma[].n_equipes.n_inicial` | int | — | ≥ 1 | `1` | Frentes na mobilização (início do ramp) |
| `cronograma[].n_equipes.n_max` | int | — | ≥ 1 | `1` | Pico de frentes simultâneas (pool irrestrito) |
| `cronograma[].producao_diaria` | number | — | > 0 | catálogo | Override da produtividade do catálogo |

> \* `item_id` é obrigatório dentro do objeto `cronograma[]`, mas o array inteiro é opcional.

> **n_max determina o pool:** desde ADR-091 (fix 2026-06-11), `n_max` define a capacidade do pool para aquela atividade. Um `n_max` menor que o necessário para o prazo contratual resulta em makespan inflado. Quando omitido, skill-04 deriva do catálogo pela fórmula `ceil(dur_1frente / deadline_semanas)`.

---

## Mapeamento CPU (Resolução de cpu_id)

O formulário resolve `descricao → cpu_id` em dois níveis:

| Nível | Score | Mecanismo | Confiança |
|---|---|---|---|
| 1 | 2 — "alta" | Todas as palavras-chave de `cpu_mapping_rules.json` coincidem | Automático |
| 2 | 1 — "media" | ≥ 2 palavras (>3 chars) coincidem com descrição do catálogo | Requer confirmação |
| 3 | 0 — "nenhuma" | Sem correspondência | Requer `cpu_id` explícito |

Quando há itens com confiança < "alta", o sistema retorna `status: "pendente_mapeamento"` com sugestões — o engenheiro confirma ou corrige antes da criação.

---

## Fluxo de Criação

```
1. Preencher Seções 1–3 (Identificação + Regime + Tributação)
2. Informar serviços em linguagem natural (QQP)
   → sistema sugere cpu_id por busca semântica
3. Confirmar ou corrigir mapeamentos
   → status: "pendente_mapeamento" se cpu_ids incompletos
4. Criar projeto
   → status: "criado" — retorna project_id, escopo_id, plano_id
   → skill-01 executada automaticamente
5. Avançar pipeline skill por skill ou de uma vez
```

---

## Gaps Atuais (Parâmetros Não Expostos no Formulário)

| Campo | Onde existe | Por que não está no formulário | Prioridade |
|---|---|---|---|
| Indiretos (ADM/TOP/LAB/QSMS/MOB) | Benchmark `referencia.json` | Vêm do perfil de contexto; engenheiro não parametriza | Média |
| BDI custom por categoria | `inputs_06` | Usa perfil padrão do contexto; override requer expertise | Baixa |
| `restricoes_mercado: {tipo_recurso: N_max}` | `inputs_cronograma.rcpsp_spec.pool_config` | Restraint de disponibilidade de frota no mercado local | Alta |
| `leadtime_mob_semanas` / `lag_demob_semanas` | ADR-106 F5 | Aguarda campo no catálogo por CPU; implementado em código, sem dado | Alta |
| `perfil_bdi_id` override | `perfil_id` no contexto | Requer seleção de perfil pré-cadastrado | Média |

---

## Exemplos

### Exemplo Mínimo (só obrigatórios)

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
      { "item_id": "eap-1_1", "cpu_id": "CPU-TERRA-ATI-003",            "quantitativo": 180000 },
      { "item_id": "eap-1_2", "cpu_id": "CPU-TERRA-ESCO-CARGA-1CAT-DMT2000", "quantitativo": 95000 },
      { "item_id": "eap-1_3", "cpu_id": "CPU-TERRA-COMPAC-PN",           "quantitativo": 85000 }
    ]
  }]
}
```

### Exemplo Completo (todos os parâmetros)

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
    "regime_tributario": { "jurisdicao_id": "BR-CE", "iss": 0.02 }
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
      },
      {
        "item_id": "eap-1_5",
        "cpu_id": "CPU-TERRA-ESCO-CARGA-3CAT-DMT2000",
        "quantitativo": 304634
      }
    ],
    "cronograma": [
      { "item_id": "eap-1_0", "n_equipes": { "n_inicial": 1, "n_max": 6 } },
      { "item_id": "eap-1_5", "n_equipes": { "n_inicial": 1, "n_max": 3 } }
    ]
  }]
}
```

---

## Referências

- `config/schemas/projeto_spec.schema.json` — JSON Schema canônico (validação runtime)
- `src/concilium/application/services/formulario_service.py` — lógica de mapeamento CPU
- `src/concilium/application/services/project_input_builder.py` — construção de inputs do pipeline
- `src/concilium/presentation/mcp/tools/formulario.py` — tool MCP `criar_projeto_formulario`
- `src/concilium/presentation/mcp/apps/formulario-qqp/index.html` — app interativo
- ADR-092 — decisão arquitetural do formulário
- ADR-091 — pool mínimo como variável de otimização (n_max)
- ADR-081 — predecessência EAP com threshold de conclusão parcial
