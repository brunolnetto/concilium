# Especificação: Formulário de Criação de Projeto (QQP/EAP)

**Versão:** 3.0  
**Data:** 2026-06-11  
**Schema canônico:** `config/schemas/projeto_spec.schema.json`  
**Ponto de entrada MCP:** `criar_projeto_formulario`  
**App interativo:** `mcp/apps/formulario-qqp/index.html`

---

## Princípio de Design

O formulário serve um engenheiro civil que conhece obras mas não conhece o sistema. Ele sabe o que é EAP, BDI e custo indireto; não sabe o que é `completion_threshold_pct`, `n_max` ou `tipo_recurso`.

O agente age como **intérprete**: transforma respostas em linguagem de obra em campos técnicos. Nenhum parâmetro técnico de implementação deve aparecer na conversa.

```
Engenheiro fala           →  Agente interpreta  →  Schema interno
"2 semanas de mobilização" → leadtime_mob = 2   → cronograma[].leadtime_mob_semanas
"Só tem 2 escavadeiras    → restricoes_mercado  → {EQUIPE-CPU-TERRA-...: 2}
 disponíveis aqui"           = {tipo: 2}
"Lucro de 8%"             → bdi_lucro.todos = 8% → bdi_lucro.{mao_obra:0.08,...}
```

---

## Interface do Engenheiro: Perguntas do Formulário

O agente conduz uma conversa com estas perguntas — em ordem, pulando as que têm defaults aceitáveis para o contexto da obra.

### Bloco 1 — Identificação (obrigatório, sem default)

| Pergunta | Campo interno | Exemplo de resposta |
|---|---|---|
| "Qual o nome da obra?" | `meta.nome` | "Rodovia CE-040 Lote 09/10" |
| "Que tipo de obra é?" | `meta.tipo_obra` | "Terraplenagem" → `"terraplenagem"` |
| "Onde fica? (Cidade, UF)" | `meta.localizacao` | "Aracoiaba, CE" |
| "Quando começa?" | `meta.data_inicio` | "setembro de 2026" → `"2026-09-01"` |
| "Qual o prazo contratual?" | `meta.data_termino` | "12 meses" → `"2027-09-01"` |

### Bloco 2 — Regime de trabalho (perguntar só se diferente do padrão)

Padrão MendesLobo: **6 dias/semana, 8h/dia**. Perguntar apenas se a obra tiver regime diferente.

| Pergunta | Campo interno | Default |
|---|---|---|
| "A obra roda em regime diferente de 6×8?" | `regime_trabalho.dias_semana` / `horas_dia` | 6 dias, 8h |

### Bloco 3 — Serviços (obrigatório, sem default)

"Quais são os serviços do escopo? Me informe descrição, quantidade e unidade."

O engenheiro lista em linguagem natural. O agente resolve `cpu_id` via busca semântica. Se não encontrar, pergunta com opções — nunca expõe o código CPU diretamente.

> **Regra do agente:** Nunca perguntar "qual o cpu_id?". Perguntar "o serviço 'Carga e transporte 3km' se encaixa melhor em escavação com carga ou em transporte puro?"

### Bloco 4 — Custos de canteiro (perguntar se disponível; aceita "não sei")

"Você tem os custos mensais do canteiro? (ADM, supervisão, laboratório, segurança, mobilização)"

Se sim: coleta em R$/mês por categoria. Se não: usa defaults derivados dos benchmarks da MendesLobo.

| O que o engenheiro informa | Campo interno |
|---|---|
| "ADM custa ~R$ 1M/mês" | `indiretos.ADM.custo_fixo_mensal` |
| "Supervisão R$ 70k/mês" | `indiretos.TOP.custo_fixo_mensal` |
| "Mobilização total R$ 3.5M" | `indiretos.MOB[fase=mobilizacao].custo_fixo_total` |
| "Não tenho esse dado" | Agente usa defaults do contexto mendeslobo |

### Bloco 5 — Regime e lucro (perguntar; aceita "padrão")

| Pergunta | Campo interno | Default | Tradução |
|---|---|---|---|
| "A empresa está no Lucro Presumido, Simples ou Lucro Real?" | `meta.regime_tributario.regime` | `"lucro_presumido"` | — |
| "Qual o lucro objetivo da obra?" | `meta.bdi_lucro.*` (todos) | 9% (direto), 5% (indireto) | um número → todos os sub-campos |
| "O ISS é diferente de 2% no município?" | `meta.regime_tributario.iss` | jurisdição/default | só perguntar se cidade fora do padrão |

> **Regra do agente:** "Lucro de 8%" → `bdi_lucro = {mao_obra: 0.08, servicos: 0.08, material: 0.04, diesel: 0.04, indireto: 0.05}`. Material e diesel mantêm 4% (impostos isentos); indireto mantém 5% (convenção TCU).

### Bloco 6 — Ritmo e mobilização (perguntar; aceita "padrão")

| Pergunta | Campo interno | Default |
|---|---|---|
| "Quantas semanas para montar o canteiro antes de começar a produção?" | `cronograma[].leadtime_mob_semanas` | 2 semanas |
| "Quanto tempo para encerrar e devolver equipamentos após a última semana de produção?" | `cronograma[].lag_demob_semanas` | 1 semana |

> **Regra do agente:** Se a obra é grande (>R$50M ou >24 meses), sugerir leadtime=3, lag=2. Se é pequena, manter defaults.

### Bloco 7 — Disponibilidade de equipamentos (perguntar só se relevante)

Perguntar apenas se a localização for remota ou de difícil acesso:

"Tem alguma restrição de equipamento na região? Por exemplo, só consegue mobilizar 2 escavadeiras?"

| O que o engenheiro diz | Campo interno |
|---|---|
| "Só tem 2 escavadeiras grandes aqui" | `restricoes_mercado: {EQUIPE-CPU-TERRA-ESCO-*: 2}` |
| "Sem restrição" ou não perguntado | `restricoes_mercado: {}` (irrestrito) |

> **Regra do agente:** Traduzir a restrição para o tipo de recurso correto consultando o catálogo após skill-03. Por padrão, `restricoes_mercado = {}` (irrestrito) — nunca tornar restrito sem confirmação do engenheiro.

---

## Mapeamento Técnico (Referência para o Agente)

Esta seção é interna — o engenheiro nunca vê estes campos diretamente.

### Parâmetros com defaults fixos (o agente nunca pergunta)

| Campo | Default fixo | Razão |
|---|---|---|
| `objetivo_pool` | `"balanceado"` | Bissecção ótima para obras com prazo definido |
| `completion_threshold_pct` (predecessores) | `1.0` | FS clássico — suficiente para 95% dos casos |
| `meta.regime_tributario.regime_version` | `"PRE_REFORMA"` | Contrato atual; CBS/IBS muda sob orientação jurídica |
| `coordenadas` | geocoding de `localizacao` | Agente resolve via geocoding antes de criar |

### Parâmetros que o agente resolve automaticamente

| Campo | Como o agente resolve |
|---|---|
| `cpu_id` | busca semântica + confirmação se confiança < alta |
| `tipo_recurso` em `restricoes_mercado` | consulta catálogo após skill-03 |
| `meta.regime_tributario.iss` | lookup em tabela de ISS municipal por jurisdicao |
| `indiretos.*` (defaults) | benchmark AGIS/MARA_ROSA proporcional ao porte estimado |

### bdi_lucro: tradução de "X% de lucro"

Quando o engenheiro diz um único número de lucro `L`:

```python
bdi_lucro = {
    "mao_obra": L,          # lucro total sobre MO
    "servicos": L,          # lucro total sobre serviços
    "material": min(L, 0.04),  # material e diesel: cap em 4% (isenção fiscal)
    "diesel":   min(L, 0.04),
    "indireto": min(L, 0.05),  # indireto: cap em 5% (convenção TCU)
}
```

### Indiretos: defaults por porte da obra

Quando o engenheiro não informa (ou diz "não sei"):

| Porte estimado | Base para defaults |
|---|---|
| < 6 meses / < R$20M | MARA_ROSA (4 meses): ADM ~R$308k/mês |
| 6–18 meses / R$20M–R$100M | AGIS (13 meses): ADM ~R$1.06M/mês |
| > 18 meses / > R$100M | AGIS × fator de escala |

O agente informa ao engenheiro qual base usará e confirma antes de criar o projeto.

---

## Schema Interno (v2.0 — preservado para referência)

Ver `config/schemas/projeto_spec.schema.json`. Os campos abaixo são todos os parâmetros que o schema aceita — o formulário expõe apenas os do Bloco 1-7 acima.

| Seção | Campos | Expostos ao usuário |
|---|---|---|
| `meta` | nome, contexto_id, tipo_obra, localizacao, coordenadas, datas, regime_trabalho, regime_tributario, bdi_lucro, objetivo_pool | Blocos 1, 2, 5 (simplificados) |
| `indiretos` | ADM/TOP/LAB/QSMS/MOB com sub-campos | Bloco 4 (em R$, sem sub-campos) |
| `restricoes_mercado` | {tipo_recurso: N_max} | Bloco 7 (em linguagem natural) |
| `escopos[].eap` | item_id, cpu_id, quantitativo, predecessores | Bloco 3 (linguagem natural → cpu) |
| `escopos[].cronograma` | n_equipes, leadtime_mob_semanas, lag_demob_semanas, producao_diaria | Bloco 6 (em semanas) |

---

## Fluxo de Conversa Esperado

```
Agente: "Vou criar o projeto. Me fala o nome da obra e onde fica."
Eng:    "Rodovia CE-040, Aracoiaba/CE, terraplenagem"

Agente: "Qual o período? Começa quando e qual o prazo?"
Eng:    "Setembro de 2026, 12 meses"

Agente: "Regime padrão MendesLobo (6 dias × 8h). Confirma ou é diferente?"
Eng:    "Confirma"

Agente: "Me passa os serviços do escopo com quantidade e unidade."
Eng:    "Supressão 8ha, escavação 3ª cat 450k m³, aterro compactado 120k m³"
        → agente mapeia CPUs, confirma com o engenheiro

Agente: "Tem os custos do canteiro ou uso os padrões da MendesLobo
         (base AGIS, ~R$1,2M/mês entre ADM+TOP+LAB+QSMS)?"
Eng:    "Usa o padrão"

Agente: "Lucro objetivo da obra? Regime tributário?"
Eng:    "8%, Lucro Presumido"

Agente: "Mobilização: quantas semanas para montar o canteiro?"
Eng:    "3 semanas"

Agente: "Tem restrição de equipamento na região?"
Eng:    "Não"

Agente: "Criando projeto... [executa criar_projeto_formulario]"
        "Projeto criado ✅ ID: ce040-lote09 | 3 atividades | EAP confirmada."
        "Posso iniciar o pipeline agora ou prefere revisar a EAP primeiro?"
```

---

## Gaps Residuais

| Gap | Quando resolver |
|---|---|
| `perfil_bdi_id` como referência a perfil pré-cadastrado | Quando existir biblioteca de perfis por tipo_obra |
| `completion_threshold_pct` customizável | Quando engenheiro solicitar sobreposição parcial de atividades |
| `CPU.mob_policy.leadtime_mob_semanas` no catálogo | Quando catálogo for enriquecido por tipo de máquina |
| CBS/IBS_2026 exposto ao engenheiro | Quando reforma tributária entrar em vigor (estimado 2027) |
