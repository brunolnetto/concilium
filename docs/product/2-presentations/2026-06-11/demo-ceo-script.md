# Script de Demo — CEO (2026-06-11)

**Duração:** 15–18 min  
**Objetivo:** Mostrar Claude planejando obra autônoma via MCP — do zero ao resultado financeiro com análise interativa de cenários em tempo real  
**Perfil:** Engenheiro civil sênior — entende EAP, BDI, RCPSP, cronograma. Não precisa de explicação de termos; quer ver o agente **funcionando e aprendendo sobre o pool**.

> **O que mudou desde 2026-06-10:** pipeline agora tem 11 skills (antes 15), prazo AGIS saiu de 67 para 42 semanas, benchmark APROVADO em todos os gates, simulação de levers é real e interativa, Gantt integrado no chat.

---

## Parte 1 — O Prompt Inicial

Cole exatamente no Claude (MCP Concilium conectado):

```
Preciso de um orçamento de planejamento para o seguinte empreendimento:

Obra: Terraplenagem e drenagem — Lote 09 e 10 (Ferrovia Nova Transnordestina)
Localização: Quixadá, CE
Tipo: ferrovia
Regime: 6 dias/semana, 8h/dia
Início: 2026-08-01   Término: 2027-04-30

EAP (resumida):
- 1.1 | Desmatamento e limpeza | m² | 450.000
- 1.2 | Escavação 1ª cat. DMT ≤ 2000m | m³ | 380.000
- 1.3 | Escavação 2ª cat. DMT ≤ 2000m | m³ | 120.000
- 1.4 | Compactação PN | m³ | 310.000
- 1.5 | Corpo de aterro 3ª cat. | m³ | 95.000
- 1.6 | Drenagem — escavação de vala | m | 8.200

Catálogo: mendeslobo (versão mais recente)
Perfil BDI: usar padrão ferrovia com lucro 8% e impostos padrão

Execute o pipeline completo e me entregue:
1. Resultado financeiro consolidado
2. As 3 atividades mais críticas para prazo e custo
3. Margem projetada e status de viabilidade
```

---

## Parte 2 — O Que Claude Faz (sequência autônoma esperada)

Claude executa **11 skills sem intervenção** — eram 15 antes de ontem:

```
1. iniciar_orcamento(...)
   → Skill-01: EAP validada, project_id criado

2. disparar_pipeline(project_id, "02-produtividade-climatica")
   → Open-Meteo Quixadá CE: jan–mai são meses críticos (período chuvoso)
   ✓ fator_calendario_semanal calculado semana a semana

3. disparar_pipeline(project_id, "03-catalogo-de-recursos")
   ✓ Pool de recursos declarado do catálogo mendeslobo

4. disparar_pipeline(project_id, "04-cronograma")
   → RCPSP com n_max irrestrito por atividade:
     cada atividade recebe o máximo de frentes que o planejador planeja
     (NÃO o mínimo para caber no prazo — isso resolvia mal o problema)
   ✓ Makespan determinístico alinhado ao contrato; sem atraso estrutural

5. disparar_pipeline(project_id, "05-equipes-e-alocacao")
   → Dimensiona equipes: salário + encargos CLT pela tabela all-in do catálogo
     (encargos não são mais duplicados — bug corrigido esta semana)
   ✓ custo_execucao_pool ≈ 0.90 × PU_cat (era 0.45 — half the reality)

6. disparar_pipeline(project_id, "06-resultado-financeiro")
   → Orquestra precificação + indiretos (ADM/TOP/LAB/QSMS/MOB) +
     consolidação financeira em 1 skill (eram 3: skills 06+07+08)
   → BDI de equipamentos usa fração locação/manutenção (SV-31/STF) —
     não mais 70/30 hardcoded
   → Indiretos MOB com fases: mobilização (one-time) + operação (mensal) +
     desmobilização (one-time no encerramento)
   ✓ Resultado financeiro: custo_direto + custo_indireto + margem

7. disparar_pipeline(project_id, "09-relatorio-e-artefatos")
   ✓ Relatório PDF + Excel + Gantt (novo)

8. auditar_plano(project_id)
   → Retorna resultado, 3 atividades ABC-A, status de viabilidade

9. disparar_pipeline(project_id, "10-diagnostico-criticidade")
   ✓ Ranking ABC custo × prazo

10. disparar_pipeline(project_id, "13-replanejamento-e-cenarios")
    ✓ Assessor + explorador em 1 skill (eram 2: skills 13+14)

11. disparar_pipeline(project_id, "11-avaliacao-intervencoes")
    ✓ Relatório de sensibilidade — alavancas de melhoria
```

**Tempo estimado:** 90–120 s. Pipeline 26% mais rápido que ontem (11 vs 15 skills).

---

## Parte 3 — Perguntas-Gancho Para o CEO

### Pergunta 1 — A que vai abrir o Gantt no chat

> "Posso ver o cronograma de forma visual?"

Claude chama `listar_artefatos(project_id)` — o app de artefatos abre no chat e automaticamente exibe o **Gantt interativo** com as atividades. O CEO pode passar o mouse sobre cada barra e ver: nome da atividade, data início → fim, duração em semanas, número de frentes e CPU usada.

**Por que impacta:** o CEO nunca viu um Gantt aparecer dentro do Claude. Sem download, sem abrir programa.

---

### Pergunta 2 — A que vai mostrar os levers

> "E se eu quiser aumentar o ritmo da obra — mais horas por dia ou mais equipes?"

Claude responde: *"Posso simular agora"* e abre o **app de Diagnóstico de Ponto de Equilíbrio**.

O CEO vê os **sliders interativos** em tempo real:
- Desliza "Fator de equipes" de 1.0× para 1.5×
- Vê instantaneamente: `fe_nec_médio: 1.38 → 0.92`, `itens críticos: 4 → 0`, `Δ custo: +R$ 8.3M`
- Desliza "Horas/dia" de 8 para 10 → custo sobre, prazo encurta

Depois clica **"Aplicar via Pipeline"** — o sistema re-executa o cronograma com os parâmetros escolhidos.

**Por que impacta:** iteração de cenário que levaria 2 horas de planilha acontece em 15 segundos sem sair do chat.

---

### Pergunta 3 — A que vai revelar as três camadas de custo

> "O que é esse 'custo do pool' que aparece no diagnóstico? É diferente do preço unitário?"

Claude explica as três camadas — e o sistema mostra numericamente para o projeto do CEO:

| Camada | O que é | Valor AGIS (referência) |
|---|---|---|
| **PU_cat × Q** | Preço de mercado — o que você cobra | R$ 48.7M |
| **PU_op × Q** | Custo real de execução via pool | R$ 43.8M |
| **PU_op_autônomo × Q** | Se cada atividade tivesse equipe dedicada | R$ 73.8M |

A diferença entre executar com pool próprio (R$ 43.8M) versus subcontratar ao preço de mercado (R$ 48.7M) é a **margem bruta do trabalho direto — R$ 4.9M antes do BDI**.

O sistema prova, numericamente, por que ter frota própria vence a subcontratação.

---

### Pergunta 4 — A que vai revelar People & Finance

> "E os encargos? O sistema calcula o custo real de cada funcionário com INSS, IRRF, tudo?"

Claude chama:

```
calcular_custo_empregador_clt(salario_base=9000, categoria="horista")
```

Retorna breakdown auditável por grupo:
- Grupo A (INSS patronal 20% + FGTS 8% + RAT 3% + Sal-Ed 2.5% + Sistema S 4.3%)
- Grupos B–F (férias, 13º, DSR, rescisão, benefícios, VT+VR) por SINTRACON-SP
- Judicial (provisão passivo trabalhista)
- **Total: R$ 9.000 × 2.777 = R$ 24.993/mês**

E IRRF:
```
calcular_irrf(base_calculo=7500)
→ R$ 312,40 (desconto progressivo Lei 15.270/2025)
```

**Por que impacta:** qualquer RH da obra pode simular cenários salariais dentro do planejamento, com base legal citada por grupo. Nenhuma planilha de mercado faz isso.

---

### Pergunta 5 — A que vai revelar combustível generalizado

> "E quando a frota é mista — escavadeiras elétricas e diesel?"

Resposta ideal:

> *"Isso já está implementado. O catálogo agora tem `tipo_combustivel` como campo de primeira classe: DIESEL_S10, CNG, BIODIESEL, ELETRICO. O custo de cada tipo de combustível entra na precificação com sua própria taxa de BDI — material para todos — e aparece como dimensão separada no cubo analítico. Migrar uma frota de diesel para elétrico é trocar o campo `tipo_combustivel` no insumo do catálogo."*

Isso mostra que a equipe **não só antecipou o problema como já resolveu**.

---

## Parte 4 — Fechamento (o que mostrar por último)

Abra o relatório PDF diretamente no chat (via app de artefatos). Aponte apenas:

1. **Seção RESULTADO** — três linhas: `PU_cat × Q`, `custo_execucao_pool`, `margem`
2. **Seção CRONOGRAMA** — Gantt com fator climático visível (semanas em cinza = sem produção)
3. **Seção PE por atividade** — fe_nec por item, cores verde/amarelo/vermelho

Frase final:

> *"Cada R$ deste resultado é rastreável até o insumo do catálogo — coeficiente, preço unitário, encargo por grupo, BDI por sub-categoria. Se um fiscal do TCU pedir a memória de cálculo, o sistema a gera em segundos."*

---

## Parte 5 — Backup se Algo Falhar

| Problema | Solução |
|---|---|
| Pipeline trava | `consultar_status(project_id)` mostra qual skill e o código de validação. Diga: *"Esse gate detectou uma inconsistência — em produção ele bloqueia antes do dado errado entrar no orçamento"* |
| Margem sai VERMELHO | **Melhor cenário** — abre os sliders ao vivo, ajusta equipes, mostra margem subindo em tempo real |
| CPU não no catálogo | Use AGIS diretamente: `consultar_status("AGIS")` → `auditar_plano("AGIS")` — resultado calibrado, zero surpresa |

### Projeto Backup — AGIS Pré-Calibrado

Se quiser zero risco de erro ao vivo:

```
"Mostre o planejamento atual do projeto AGIS e me dê o diagnóstico completo,
incluindo análise de cenários e o Gantt do cronograma"

→ listar_projetos()
→ consultar_status("AGIS")
→ auditar_plano("AGIS")         ← abre diagnostico-pe com dados reais
→ listar_artefatos("AGIS")      ← abre Gantt interativo
→ simular_cenario_replan("AGIS", "lever_adjust",
    {"fator_equipes": 1.3, "meta_margem_pct": 0.12})
```

Gates do AGIS atual: **+3.83% custo_direto · -0.00% custo_indireto · -0.13% preço_venda** — tudo IDEAL S0.

---

## O que NÃO Dizer

- Não mencione "NEPs", "ADRs", "benchmarks", "testes" espontaneamente
- Não abra código-fonte
- Se perguntar sobre segurança: *"Dados do projeto ficam no SharePoint da MendesLobo — o Claude acessa via MCP server na infraestrutura de vocês; nada sai para a Anthropic"*
- Se perguntar "quanto tempo levou?": *"O planejamento que você viu levou 2 minutos. Em planilha seriam 2 semanas de engenharia."*
