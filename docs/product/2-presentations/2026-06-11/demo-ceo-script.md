# Script de Demo — CEO (2026-06-11 v2)

**Duração:** 15–18 min  
**Objetivo:** Mostrar Claude como engenheiro de planejamento autônomo — o usuário fala como em obra, o sistema entende e entrega resultado financeiro com análise interativa  
**Perfil:** Engenheiro civil sênior — entende EAP, BDI, cronograma. Quer ver o agente **funcionando**, não explicações técnicas.

> **O que há de novo:** o agente conduz a criação do projeto em conversa natural — sem formulário técnico, sem códigos, sem JSON. O engenheiro fala como fala com um colega de planejamento.

---

## Parte 1 — O Prompt de Abertura

Cole exatamente no Claude (MCP Concilium conectado):

```
Preciso fazer o orçamento de planejamento da Ferrovia Nova Transnordestina,
Lote 09 e 10, em Quixadá, CE. Terraplenagem e supressão vegetal.

Começa em agosto de 2026, prazo contratual de 9 meses.
Regime de 6 dias × 8 horas.
Lucro objetivo de 8%, Lucro Presumido.

Os serviços são:
- Desmatamento e limpeza: 450 mil m²
- Escavação 1ª categoria com carga e transporte até 2km: 380 mil m³
- Escavação 2ª categoria com carga e transporte até 2km: 120 mil m³
- Compactação PN: 310 mil m³
- Corpo de aterro 3ª categoria: 95 mil m³
- Escavação de vala para drenagem: 8.200 m

Não tenho os custos do canteiro na mão. Use os padrões da MendesLobo.
Mobilização estimada em 3 semanas.
```

---

## Parte 2 — O Que Claude Faz

**Criação do projeto em conversa:**
```
Claude: "Vou usar os padrões MendesLobo para canteiro:
         ADM ~R$ 1M/mês, supervisão ~R$ 67k, lab ~R$ 11k, QSMS ~R$ 59k.
         Mobilização: R$ 4M (padrão AGIS). Confirma ou ajusto?"

Eng:    "Confirma."

Claude: "Para 'Escavação de vala para drenagem' encontrei dois enquadramentos:
         (1) Escavação vala 1ª cat. com bota-fora — R$ 6,43/m
         (2) Escavação mecanizada para drenos — R$ 8,53/m
         Qual se encaixa melhor?"

Eng:    "A primeira."

Claude: "Projeto criado ✅  6 atividades · 9 meses · ID: ferrovia-tnt-lote09"
```

**Pipeline autônomo (11 skills, ~90s):**
```
01 → EAP validada
02 → Clima Quixadá CE: jan–mai são os meses críticos (período chuvoso)
03 → Catálogo de recursos
04 → RCPSP: 42 semanas calculadas; alerta: prazo contratual é 39 semanas ⚠️
05 → Equipes dimensionadas; encargos CLT por grupo A–F calculados
06 → BDI 8% aplicado — locação de equipamentos isenta de ISS (SV-31/STF)
     Mobilização faseada: R$ 4M entrada + operação + R$ 408k saída
09 → Relatório PDF + Gantt gerados
10 → Criticidade ABC: 3 atividades classe A identificadas
```

**Resultado financeiro entregue:**
```
Custo direto (preço mercado):  R$ 48.7M
Custo execução com pool:       R$ 43.8M   ← executa 10% abaixo do mercado
Custo indireto (canteiro):     R$ 19.6M
Preço de venda:                R$ 76.9M
Margem operacional:            17.6%      ✅ VERDE
```

**Tempo estimado:** 90–120 s.

---

## Parte 3 — Perguntas-Gancho Para o CEO

### Pergunta 1 — A que abre o Gantt no chat

> "Posso ver o cronograma visualmente?"

Claude abre o **Gantt interativo** no chat. O CEO passa o mouse sobre uma barra:  
*"Escavação 3ª cat. · 01/Out → 15/Jan · 15 semanas · 3 frentes simultâneas"*

**Por que impacta:** Gantt aparece dentro do Claude. Sem download, sem abrir outro programa.

---

### Pergunta 2 — A que mostra os levers em tempo real

> "E se eu colocar mais equipes para fechar no prazo?"

Claude abre o **Diagnóstico PE** no chat com sliders. O CEO desliza "Fator de equipes" de 1.0× para 1.3×:

- Frentes críticas (fe_nec > 1.25): **3 → 0**
- Δ custo estimado: **+R$ 8.3M**
- Margem estimada: **17.6% → 14.2%**

Tudo em tempo real, sem re-executar o pipeline. Clica **"Aplicar via Pipeline"** para confirmar.

**Por que impacta:** o CEO vê o trade-off prazo × custo em 15 segundos. Em planilha seriam 2 horas.

---

### Pergunta 3 — A que revela as três camadas de custo

> "Por que o custo do pool é menor que o preço de catálogo?"

| | Valor |
|---|---|
| **Preço de mercado** (o que você cobra) | R$ 48.7M |
| **Custo de execução com pool próprio** | R$ 43.8M |
| **Economia vs subcontratar** | **R$ 4.9M** |
| **Custo se fosse equipe dedicada por atividade** | R$ 73.8M |

*"Ter frota própria vale R$ 4.9M de margem bruta só em custo direto — antes do BDI."*

---

### Pergunta 4 — A que revela People & Finance

> "Como o sistema calcula o encargo do operador?"

Claude chama `calcular_custo_empregador_clt(salario_base=9000, categoria="horista")`:

```
INSS patronal 20%:       R$  1.800
FGTS 8%:                 R$    720
RAT + Sal-Educ + Sist.S: R$    880
Férias + 13º + DSR:      R$  2.880   (SINTRACON-SP Grupo B)
Rescisão + substituição: R$    540   (Grupo C+D)
VT + VR + saúde + EPI:   R$  1.890   (Grupo E+F)
─────────────────────────────────
Total mensal:            R$ 24.993   (= R$ 9.000 × 2,777)
```

*"Cada operador custando R$ 9k nominalmente custa R$ 25k à empresa. O sistema usa a convenção SINTRACON-SP para cada função, com base legal citada grupo a grupo."*

---

### Pergunta 5 — A que revela combustível generalizado

> "Quando a frota for elétrica ou GNV, o sistema vai funcionar?"

*"Já está pronto. O catálogo tem tipo de combustível como campo de primeira classe: diesel S10, GNV, biodiesel, elétrico. O custo de combustível segue a categoria material (4% de BDI) independente do tipo — só o preço/L muda. Migrar uma escavadeira para elétrica é trocar um campo no insumo do catálogo."*

---

## Parte 4 — Fechamento

Abra o relatório PDF no chat. Aponte apenas:

1. **Resultado financeiro** — três linhas: custo de mercado, custo de execução, margem
2. **Gantt** — fator climático visível (semanas cinza = sem produção)
3. **PE por atividade** — verde/amarelo/vermelho por viabilidade de frentes

Frase final:
> *"Cada R$ deste resultado é rastreável até o insumo do catálogo — coeficiente, hora, encargo por grupo legal, BDI por sub-categoria. Se o fiscal do TCU pedir a memória de cálculo, o sistema gera em 3 segundos."*

---

## Parte 5 — Backup se Algo Falhar

| Problema | Solução |
|---|---|
| Claude pede esclarecimento | Normal — o agente está coletando o que falta. Responder naturalmente |
| CPU não mapeado | Claude apresenta opções descritivas → engenheiro escolhe em português |
| Pipeline trava | `consultar_status(project_id)` — mostrar o gate que detectou a inconsistência |
| Margem VERMELHO | **Melhor cenário** — abre sliders, ajusta equipes, vê margem subir ao vivo |

### Projeto Backup — AGIS Calibrado

Para zero risco de erro ao vivo:

```
"Mostre o planejamento do projeto AGIS e me dê o diagnóstico completo"

→ consultar_status("AGIS")
→ auditar_plano("AGIS")
→ listar_artefatos("AGIS")      ← Gantt interativo abre automaticamente
→ simular_cenario_replan("AGIS", "lever_adjust",
    {"fator_equipes": 1.3, "meta_margem_pct": 0.12})
```

Gates AGIS: **+3.83% custo_direto · 0.00% custo_indireto · -0.13% preço_venda — APROVADO S0**

---

## O que NÃO Dizer

- Não mencione "NEPs", "ADRs", "benchmarks", "json", "schema", "cpu_id"
- Não abra código-fonte ou terminal
- Se perguntar "quanto tempo de desenvolvimento?": *"Construído iterativamente — o importante é que hoje está em produção"*
- Se perguntar sobre segurança: *"Dados ficam no SharePoint da MendesLobo — Claude acessa via MCP server na infraestrutura de vocês"*
- Se perguntar "e quando a IA errar?": *"Há gates de validação em cada etapa — um erro é capturado antes de chegar ao orçamento, com a causa específica identificada"*
