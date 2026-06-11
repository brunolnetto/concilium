# Script de Demo — CEO (Eng. Civil Sênior + Foco MCP/Autonomia)

**Duração:** 12–15 min  
**Objetivo:** Mostrar Claude conduzindo o planejamento de obra de forma autônoma via MCP, do zero ao resultado financeiro auditável  
**Perfil do interlocutor:** Entende EAP, BDI, RCPSP, cronograma — não precisa de explicação de termos; quer ver o agente funcionando

---

## Parte 1 — O Prompt Inicial (o que você digita no Claude)

Cole exatamente este texto no Claude (com o MCP Concilium conectado):

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

## Parte 2 — O que Claude faz (sequência autônoma esperada)

Claude deve executar esta cadeia **sem intervenção**:

```
1. iniciar_orcamento(...)
   → project_id criado, Skill-01 executada (EAP validada)

2. disparar_pipeline(project_id, "02-produtividade-climatica")
   → Consulta Open-Meteo para Quixadá, CE
   → Calcula praticabilidade mensal (período chuvoso CE: jan-mai)
   ✓ CONCLUIDO

3. disparar_pipeline(project_id, "03-catalogo-de-recursos")
   ✓ CONCLUIDO — pool de recursos declarado

4. disparar_pipeline(project_id, "04-cronograma")
   → RCPSP solver distribui 6 atividades pelo prazo (ago/26 → abr/27)
   ✓ CONCLUIDO — cronograma com semanas produtivas e fator climático

5. disparar_pipeline(project_id, "05-equipes-e-alocacao")
   → Dimensiona equipes, calcula custo autônomo por item
   ✓ CONCLUIDO

6. disparar_pipeline(project_id, "06-precificacao-unitaria")
   → PU com BDI por categoria (MO, EQ, DIESEL, MATERIAL)
   ✓ CONCLUIDO

7. disparar_pipeline(project_id, "07-custos-indiretos")
   ✓ CONCLUIDO — ADM, TOP, MOB calculados

8. disparar_pipeline(project_id, "08-consolidacao-financeira")
   ✓ CONCLUIDO — resultado.status_margem: VERDE/AMARELO/VERMELHO

9. auditar_plano(project_id)
   → Retorna viabilidade, gargalos, financeiro

10. disparar_pipeline(project_id, "10-diagnostico-criticidade")
    → Ranking ABC de atividades por custo × prazo

11. disparar_pipeline(project_id, "09-relatorio-e-artefatos")
    → Gera Excel auditável + PDF
```

**Tempo estimado:** 90–120 segundos de execução total

---

## Parte 3 — Perguntas-Gancho para o CEO fazer

Após o resultado aparecer, o CEO faz estas perguntas (em ordem de impacto):

### Pergunta 1 — Sensibilidade
> "E se o prazo atrasar 3 semanas por chuvas?"

Claude chama:
```
simular_cenario_replan(project_id, "extend_deadline", {"semanas": 3})
```
Retorna: delta de custo (indiretos aumentam), nova margem estimada.

**Por que impacta:** indiretos (ADM, TOP, LAB) crescem com a permanência — o sistema mostra isso numericamente em segundos. Um engenheiro faria isso em 2 horas de planilha.

---

### Pergunta 2 — Criticidade
> "Qual atividade posso atacar para melhorar a margem sem mexer no prazo?"

Claude lê o `cost_criticality_report` e responde com a atividade ABC-A com maior `custo_share` e menor `duracao_share` (alavanca de custo sem impacto de prazo).

---

### Pergunta 3 — A que vai revelar o pool de recursos
> "Tem algum equipamento ocioso nessa obra?"

Claude chama:
```
explorar_pool_recursos(project_id, face="economia_pool")
```
Retorna: semanas de standby por tipo de equipamento, custo de mobilização vs economia gerada pela perpetuação de recursos entre atividades.

**Isto mostra ADR-086** — algo que não existe em nenhuma ferramenta de mercado.

---

### Pergunta 4 — A que vai revelar a autonomia real
> "Supondo que eu queira uma margem mínima de 12%, o que precisa mudar?"

Claude usa `replan_suggestions` do assessor e diz especificamente: "para fechar o gap de X%, as alavancas disponíveis são: (a) compactar o cronograma 2 semanas = +Y%; (b) renegociar BDI de diesel de Z para W = +T%". Depois oferece criar uma nova versão com a hipótese aplicada.

---

## Parte 4 — Momento ADR-107 (use se o CEO perguntar sobre diesel)

Se ele notar que o sistema só tem diesel:

> "Notei que você calcula combustível como categoria única. E quando a frota é mista — parte elétrica, parte diesel?"

Resposta ideal:
```
"Identificamos isso exatamente. O ADR-107 que acabamos de escrever 
define a generalização: COMBUSTIVEL como categoria com tipo_combustivel 
(DIESEL_S10, CNG, ELETRICO, HVO). A arquitetura atual já tem 
ComponenteCombustivel como abstração — a extensão é cirúrgica, 
não um redesign. Implementação estimada em 3–4 semanas."
```

Isso mostra que a equipe **já está 2 passos à frente** do problema que ele acabou de identificar.

---

## Parte 5 — Fechamento (o que mostrar por último)

Abra o Excel gerado. Aponte apenas:
1. Aba RESULTADO — margem, status, preço de venda
2. Aba CRONOGRAMA — distribuição semanal com fator climático visível
3. "Este arquivo é auditável — cada linha tem rastreabilidade até o insumo do catálogo"

Não navegue além disso. O Excel é evidência, não o produto.

---

## Backup — se algo falhar

| Problema | Solução |
|---|---|
| Pipeline trava em ERRO | `consultar_status(project_id)` mostra qual skill, mensagem de validação. Explique: "o sistema detectou uma inconsistência — em produção isso é tratado automaticamente via gate ADR-022" |
| Margem sai VERMELHO | **Melhor cenário para a demo** — mostra o replan ao vivo com `simular_cenario_replan` |
| CPU não encontrado no catálogo | Use os benchmarks existentes (AGIS, CTC, VALE) como projeto pré-carregado: `listar_projetos()` e selecione um deles |

---

## Projeto Backup (se preferir não criar ao vivo)

Se quiser garantir zero surpresas, use o AGIS que já está calibrado:

```
# No início da demo, em vez de iniciar_orcamento:
"Mostre o planejamento atual do projeto AGIS e me dê o diagnóstico completo"

→ listar_projetos()
→ consultar_status("AGIS")
→ auditar_plano("AGIS")
→ explorar_pool_recursos("AGIS", face="economia_pool")
```

Mesmo impacto, zero risco de erro de execução ao vivo.

---

## Nota sobre o que NÃO dizer

- Não mencione "testes", "benchmarks", "ADRs" espontaneamente
- Não abra código-fonte — o CEO quer ver o produto, não a implementação
- Se ele perguntar sobre segurança/privacidade: "os dados do projeto ficam no seu SharePoint — o Claude acessa via MCP server que roda na sua infraestrutura"
