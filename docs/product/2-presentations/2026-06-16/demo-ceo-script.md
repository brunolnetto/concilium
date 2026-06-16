# Script de Demo — CEO (2026-06-11 v3)

**Duração:** 20–25 min  
**Objetivo:** Mostrar Claude como engenheiro de planejamento autônomo — o usuário fala como em obra, o sistema entende e entrega resultado financeiro com análise interativa e exploração paramétrica formal  
**Perfil:** Engenheiro civil sênior — entende EAP, BDI, cronograma. Quer ver o agente **funcionando**, não explicações técnicas.

> **O que há de novo (v3):** corrige inconsistências da v2 — what-if usa campanha paramétrica real (não simulação linear), abertura confirma infra, AGIS backup abre com shortlist Pareto, Pergunta 3 conecta ao framework O/EF de decisão, novas cenas de catálogo e auditabilidade.

---

## Parte 0 — Abertura (30s)

Antes de digitar qualquer prompt:

```
ping()
```

Claude responde:

```
Sistema: SAUDÁVEL
  ✓ Catálogo mendeslobo-rfi  —  75 CPUs · 81 funções · mai/2026
  ✓ Contexto mendeslobo      —  ativo
  ✓ 3 projetos existentes
  ✓ Worker pool              —  4 workers disponíveis
```

**Por que importa:** em demos ao vivo com conectividade instável, confirmar infra antes de criar projeto elimina o risco de falha por timeout.

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

**Cena adicional — o catálogo tem rastreabilidade:**

Após a criação, Claude mostra automaticamente:

```
listar_versoes_catalogo("mendeslobo-rfi")
```

```
Catálogo: mendeslobo-rfi
  v1  —  2026-05-08  Importado da Planilha Padrão RFI R02
          75 CPUs · 81 funções MO · 54 equipamentos
          Calibrado: frotas ferrovia AGIS + diesel de campo Nordeste (R$ 5,80/L)
  v0  —  2025-08-01  Catálogo base (SICRO-CE)
```

*"Cada orçamento registra qual versão do catálogo usou. Se o TCU pedir, sabemos exatamente o preço de referência que estava vigente nessa data."*

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

### Pergunta 2 — A que mostra o what-if paramétrico formal *(corrigido v3)*

> "E se eu colocar mais equipes para fechar no prazo?"

**Errado (v2):** `simular_cenario_replan` — modelo linear que subestima mudanças >15%. Apropriado só para feedback imediato de ballpark.

**Correto (v3):** campanha parametrizada:

```
explorar_configuracoes_go(
  project_id = "ferrovia-tnt-lote09",
  parametros_sweep = [
    { "campo": "n_max", "valores": [0.75, 1.0, 1.25], "scope": "global" },
    { "campo": "horas_dia", "valores": [8, 10], "scope": "global" }
  ],
  top_k = 5
)
```

Claude roda **6 cenários** (3 × 2) em paralelo — ~45s — e retorna:

```
Shortlist Pareto — 3 cenários na fronteira O ∩ EF:

  Rank 1 ★  n_max × 1,25 · 8h/dia
            Prazo: 38 sem.  ✅ dentro do contrato (−1 sem.)
            Margem: 14,8%  ATENÇÃO  (abaixo da meta 8%, mas cobertura garantida)
            Classificação O: IDEAL  · Classificação EF: ATENÇÃO

  Rank 2    n_max × 1,25 · 10h/dia
            Prazo: 36 sem.  ✅ folga de 3 sem.
            Margem: 11,9%  ATENÇÃO  (custo MO +18% pelo regime intensivo)
            Classificação O: IDEAL  · Classificação EF: ATENÇÃO

  Rank 3    n_max × 1,0 · 10h/dia
            Prazo: 40 sem.  ⚠️ estoura 1 sem.
            Margem: 16,1%  VERDE
            Classificação O: ATENÇÃO  · Classificação EF: IDEAL
```

*"O sistema não diz qual escolher — diz quais trade-offs existem. Rank 1 fecha no prazo mas come 3 pontos de margem. Rank 3 salva a margem mas estoura 1 semana. Qual é mais crítico para o contrato?"*

**Por que impacta:** o CEO vê que não há resposta única — há fronteira de trade-offs. Isso é planejamento real, não slider de planilha.

---

### Pergunta 3 — A que revela as três camadas de custo *(expandida v3)*

> "Por que o custo do pool é menor que o preço de catálogo?"

```
explorar_pool_recursos(
  project_id = "ferrovia-tnt-lote09",
  face = "economia_pool"
)
```

```
Espaço O — desempenho operacional:
  Prazo calculado:     42 sem.
  Folga contratual:   −3 sem.  ⚠️ ATENÇÃO
  fe_nec médio:        0,94    IDEAL (frentes bem calibradas)
  Itens críticos:      1/6     ATENÇÃO (escavação 3ª cat. com fe_nec = 1,28)
  Utilização pool:    78%
  Idle pool:          22%

Espaço EF — desempenho econômico-financeiro:
  Margem:             17,6%    VERDE
  Ratio pool/catálogo: 0,90    IDEAL (pool 10% abaixo do PU de mercado)
  Concentração HHI:   0,31    aceitável (3 atividades = 68% do custo)
```

| | Valor |
|---|---|
| **Preço de mercado** (o que você cobra) | R$ 48.7M |
| **Custo de execução com pool próprio** | R$ 43.8M |
| **Economia vs subcontratar** | **R$ 4.9M** |
| **Custo se fosse equipe dedicada por atividade** | R$ 73.8M |

*"O espaço O diz que operacionalmente estamos ATENÇÃO — tem 1 atividade sobrecarregada. O EF diz VERDE — a margem está boa. A decisão é: aceitar a pressão operacional nessa atividade ou ajustar frentes e ver o Rank 1 da campanha."*

**Por que impacta:** o CEO aprende que a linguagem do sistema é O × EF — operação e finanças em dois eixos separados, não um número só.

---

### Pergunta 4 — A que revela People & Finance

> "Como o sistema calcula o encargo do operador?"

```
calcular_custo_empregador_clt(salario_base=9000, categoria="horista")
```

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

### Pergunta 6 — A que mostra comparação de cenários aprovados *(nova v3)*

> "Esse cenário de 10 horas que vocês avaliaram — ficou descartado ou arquivado?"

```
comparar_planos(
  project_id = "ferrovia-tnt-lote09",
  plano_a = "plano-6dx8h",
  plano_b = "plano-6dx10h"
)
```

```
                      Plano 8h/dia     Plano 10h/dia
  Status:             APROVADO ✅      ARQUIVADO 📁
  Prazo:              42 sem.          36 sem.
  Custo direto:       R$ 48,7M         R$ 51,2M
  Margem:             17,6%            14,4%
  Itens críticos:     1                0
  Decisão:  "Margem de 3,2pp compensa 6 semanas de folga?"
            "Não. Aprovamos o 8h/dia."
```

*"Nenhum cenário é deletado. Se o prazo apertar no contrato, a decisão de qual plano usar está documentada com o raciocínio."*

---

## Parte 4 — Fechamento

**Cena adicional — auditabilidade para o TCU:**

```
baixar_bundle_zip(project_id = "ferrovia-tnt-lote09")
```

*"Aqui está o pacote completo: PDF do relatório, memória de cálculo por insumo, base legal dos encargos, versão do catálogo usada, histórico de skills. Se o fiscal do TCU pedir, o sistema entrega em 3 segundos — não em 3 dias de consultoria."*

**Abra o relatório PDF no chat. Aponte apenas:**

1. **Resultado financeiro** — três linhas: custo de mercado, custo de execução, margem
2. **Gantt** — fator climático visível (semanas cinza = sem produção)
3. **PE por atividade** — verde/amarelo/vermelho por viabilidade de frentes

Frase final:
> *"Cada R$ deste resultado é rastreável até o insumo do catálogo — coeficiente, hora, encargo por grupo legal, BDI por sub-categoria. E cada decisão tomada no caminho está arquivada: qual versão do catálogo, qual cenário foi aprovado, quem assinou. É o mesmo rigor de uma ART, aplicado ao planejamento."*

---

## Parte 5 — Backup se Algo Falhar

| Problema | Solução |
|---|---|
| Claude pede esclarecimento | Normal — o agente está coletando o que falta. Responder naturalmente |
| CPU não mapeado | Claude apresenta opções descritivas → engenheiro escolhe em português |
| Pipeline trava | `consultar_job_pipeline(job_id)` — mostrar o gate que detectou a inconsistência |
| Margem VERMELHO | **Melhor cenário** — abre campanha GO, ajusta n_max, vê shortlist Pareto ao vivo |

### Projeto Backup — AGIS Calibrado *(corrigido v3)*

Para zero risco de erro ao vivo, abrir o AGIS com o fluxo mais impactante:

```
# 1. Status geral
consultar_status("AGIS")

# 2. Resultado de campanha (se campanha já foi rodada)
listar_runs_campanha("AGIS")
obter_resultado_campanha("AGIS")
→ shortlist Pareto: qual cenário equilibra prazo e margem?

# 3. Comparar RFI vs catálogo master
comparar_rfi_catalogo("mendeslobo")
→ "Aqui estão as 3 divergências acima de 20%: escavadeira 22t −46%, compactação PN −59%..."

# 4. Diagnóstico completo
auditar_plano("AGIS")
listar_artefatos("AGIS")      ← Gantt interativo abre automaticamente

# 5. What-if
explorar_configuracoes_go("AGIS",
  [{"campo": "n_max", "valores": [0.75, 1.0, 1.25], "scope": "global"}],
  top_k = 3
)
```

Gates AGIS pós-calibração RFI: **+0.85% custo_direto · 0.00% custo_indireto · −2.96% preço_venda — APROVADO S0**

---

## Mapa de Cobertura de Tools

| Grupo | Tools demonstradas | Status |
|---|---|---|
| 0 — Sistema | `ping` | ✅ |
| 1 — Criação | `criar_projeto_formulario` | ✅ |
| 2 — Ciclo de vida | `consultar_status`, `comparar_planos`, `auditar_plano` | ✅ |
| 3 — Pipeline | `disparar_pipeline`, `consultar_job_pipeline` | ✅ |
| 4 — Catálogo | `listar_versoes_catalogo`, `comparar_rfi_catalogo` | ✅ |
| 5 — Análise | `auditar_plano`, `explorar_pool_recursos` | ✅ |
| 6 — Replanejamento | `simular_cenario_replan` *(apenas ballpark, secundário)* | ℹ️ |
| 7 — Campanha GO | `explorar_configuracoes_go`, `listar_runs_campanha`, `obter_resultado_campanha` | ✅ |
| 9 — Artefatos | `listar_artefatos_projeto`, `baixar_bundle_zip` | ✅ |
| 10 — Tributação | `calcular_custo_empregador_clt` | ✅ |

**Cobertura:** 10 dos 11 grupos · ~22 das 38 tools (58% vs 32% da v2)

---

## O que NÃO Dizer

- Não mencione "NEPs", "ADRs", "benchmarks", "json", "schema", "cpu_id"
- Não abra código-fonte ou terminal
- Se perguntar "quanto tempo de desenvolvimento?": *"Construído iterativamente — o importante é que hoje está em produção"*
- Se perguntar sobre segurança: *"Dados ficam no SharePoint da MendesLobo — Claude acessa via MCP server na infraestrutura de vocês"*
- Se perguntar "e quando a IA errar?": *"Há gates de validação em cada etapa — um erro é capturado antes de chegar ao orçamento, com a causa específica identificada"*
- Não explique o que é "espaço O" ou "espaço EF" — use diretamente como *"operacionalmente"* e *"financeiramente"*
- Não mencione `simular_cenario_replan` como principal what-if — é linear e limitado; a campanha GO é o argumento correto
