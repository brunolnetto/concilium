# Certificação P23 e custo contratual exato por atividade (normas complementares)

**Estado:** decisões normativas aprovadas pelo proprietário em 2026-11-13 (#23), registradas como suplemento de §XIII/§XIV sem alterar o texto de `FORMALISMO_LONGO.md`. Exigem revisão no PR que as introduz. Oráculos independentes: `tests/reference_formalism/catalog_envelope_reference.py`, `tests/reference_formalism/activity_cost_reference.py`; vetores: `catalog_envelope_v1.json`, `activity_cost_reconciliation_v1.json`.

## N1 — [V6] calendário viável

[V6] de §XIV.9 ("a busca de \(N_i\) convergiu sem sinalização de inviabilidade") é satisfeita por **uma** testemunha P15 auditada (status e auditoria PASS, ao menos uma tentativa) vinculada à impressão digital do cronograma corrente. A exaustão do domínio de inícios declarado é exigida **somente** para provar inviabilidade: busca inviável incompleta é UNKNOWN; busca inviável exaurida é FAIL; testemunha não vinculada ao cronograma corrente é UNKNOWN.

## N2 — [V2] base do BDI é \(C^{cat}\) derivado

\(\mathrm{BDI}=P/C^{cat}-1\) (§XIV.8) é taxa derivada. \(C^{cat}=\sum_i Q_i\gamma_i^{cat}/\rho_i\) é calculado do catálogo resolvido:

\[
c_r=\frac{V_r^{mensal}}{s_{mes}\,d_i\,h_i}\ \ (\text{EQ/MO mensal}),\qquad c_r=\text{preço horário}\ \ (\text{EQ/MO por hora}),\qquad s_{mes}=\tfrac{1461}{336},
\]
\[
C_i^{cat}=\frac{Q_i}{\rho_i}\sum_{r\in\text{equipe}} c_r n_r\;+\;Q_i\sum_g \kappa_g^{out}p_g ,
\]

com a equipe e \(\rho_i\) do registro de produção e \(\kappa_g^{out}\) por unidade entregue da CPU. Bases declaradas (catálogo e regulatória) devem ser **iguais** a \(C^{cat}\); qualquer diferença rejeita a evidência de preço (fail closed). O piso regulatório permanece entrada explícita com fonte.

## N3 — GO exige execução sem erro

Um certificado só é GO se, além de todos os gates PASS e fontes presentes em escopo RFP, a execução avaliada não tiver habilidade em ERRO/EXCEPTION. Erros de habilidade não provam violação formal: o resultado é NOT_CERTIFIABLE, com os erros como razões incluídas na impressão digital. FAIL comprovado permanece NOGO.

## N4 — custo contratual exato por atividade

Quando **toda** a equipe padrão de uma atividade (equipamentos e funções) está coberta por contratos com testemunha P16 exata, o custo contratual da atividade por categoria \(k\in\{MO,EQ\}\) é

\[
C_i^{K,k}=\sum_{c:\,cat(c)=k}\Big(\tau_c^{ativo}\cdot\big|\{j:\ \text{semana ativa de }c\text{ possuída por }i\}\big|\;+\;(S_c+M_c)\,\frac{w_{ci}}{\sum_{i'}w_{ci'}}\Big),
\]

onde \(\tau_c^{ativo}\) é a tarifa semanal ativa, \(S_c\) e \(M_c\) os custos de standby e de mobilização/desmobilização da testemunha e \(w_{ci}\) a partição persistida do contrato. É a grandeza reconciliada pelo P17-C. O resumo de utilização do contrato reporta as semanas-máquina ativas e de standby e o custo de standby da testemunha (auditados por [V3]). Cobertura parcial **não** é completada nem zerada: a atividade mantém o modelo legado e o P17-C permanece NOGO.

## N5 — diagnóstico [D2] sobre razões exatas

Para atividades cobertas por N4, \(R_i=C_i^{op}/C_i^{cat}\) usa \(C_i^{op}=C_i^{K}\) (N4) \(+\) custo exato de consumo P18 da atividade, e \(C_i^{cat}\) de N2. O alerta de "frentes necessárias" usa \(R_i\) com os mesmos limiares (AVISO > 1,25; ERRO > 1,5); a estimativa legada "autônoma" só vale para atividades não cobertas.

## N6 — atividade sem consumíveis (P18)

O custo variável exato \(C_i^{V,op}=\sum_{g,j}p_gU_{gij}\) exige evidência por bem. Uma atividade **sem** linhas de consumo por unidade entregue só é certificável se a CPU declarar explicitamente `consumiveis_declarados = {status: "NENHUM", justificativa, fonte}`; então \(C_i^{V,op}=0\) por declaração auditável (registrada em `declared_no_consumables` do registro P18 e usada em \(R_i\), N5). A declaração é rejeitada se contradita por linhas de consumo da CPU ou por consumo horário (`consumo_litros_hora`) ou materiais na equipe da produção. Ausência de BOM sem declaração permanece fail closed: "não informado" nunca equivale a "não consome".

Consumo **horário** continua exigindo horas de operação observadas (`OBSERVED_OPERATION`, §IX): não se converte L/h em coeficiente por unidade via \(q/\rho\) nem pelo tempo inferido de \(F(m)\). Em planejamento (RFP), CPUs com consumo só horário não são certificáveis até que o catálogo traga coeficientes por unidade entregue com fonte.
