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
C_i^{K,k}=\sum_{c:\,cat(c)=k}\Big(\tau_c^{ativo}\cdot\big|\{j:\ \text{semana ativa de }c\text{ possuída por }i\}\big|\;+\;\sum_{h\in H_c}L_h\,\frac{n_{hi}}{\sum_{i'}n_{hi'}}\Big),\qquad L_h=\tau_c^{ocioso}\,s_h+c_c^{mob}+c_c^{demob},
\]

onde \(\tau_c^{ativo}\) e \(\tau_c^{ocioso}\) são as tarifas semanais ativa e ociosa, \(H_c\) as cadeias da testemunha P16 (cada cadeia = uma contratação de uma unidade), \(s_h\) as semanas ociosas da cadeia, \(n_{hi}\) as semanas ativas que a cadeia trabalhou para \(i\) (`activity_by_week`) e \(L_h\) o custo de ciclo de vida da cadeia. **Propriedade por cadeia (#206):** o standby e a mobilização/desmobilização de cada contratação vão às atividades que ela serviu, na proporção das semanas trabalhadas — evidência tipada instância/atividade (P11B), sem partições de custo persistidas. As cadeias devem reproduzir exatamente \(S_c=\sum_h\tau_c^{ocioso}s_h\) e \(M_c=|H_c|(c^{mob}+c^{demob})\) da testemunha; caso contrário a atividade não é avaliável. A alocação conserva o total do pool (\(\sum_i C_i^{K}=C^{pool}\)). Evidência: oráculo `activity_cost_reference.py` (protocolo `formalism-activity-cost/2`) e vetor `activity_cost_reconciliation_v2.json`, com paridade de produção. É a grandeza reconciliada pelo P17-C. O resumo de utilização do contrato reporta as semanas-máquina ativas e de standby e o custo de standby da testemunha (auditados por [V3]). Cobertura parcial **não** é completada nem zerada: a atividade mantém o modelo legado e o P17-C permanece NOGO.

## N5 — diagnóstico [D2] sobre razões exatas

Para atividades cobertas por N4, \(R_i=C_i^{op}/C_i^{cat}\) usa \(C_i^{op}=C_i^{K}\) (N4) \(+\) custo exato de consumo P18 da atividade, e \(C_i^{cat}\) de N2. O alerta de "frentes necessárias" usa \(R_i\) com os mesmos limiares (AVISO > 1,25; ERRO > 1,5); a estimativa legada "autônoma" só vale para atividades não cobertas.

## N6 — atividade sem consumíveis (P18)

O custo variável exato \(C_i^{V,op}=\sum_{g,j}p_gU_{gij}\) exige evidência por bem. Uma atividade **sem** linhas de consumo por unidade entregue só é certificável se a CPU declarar explicitamente `consumiveis_declarados = {status: "NENHUM", justificativa, fonte}`; então \(C_i^{V,op}=0\) por declaração auditável (registrada em `declared_no_consumables` do registro P18 e usada em \(R_i\), N5). A declaração é rejeitada se contradita por linhas de consumo da CPU ou por consumo horário (`consumo_litros_hora`) ou materiais na equipe da produção. Ausência de BOM sem declaração permanece fail closed: "não informado" nunca equivale a "não consome".

Consumo **horário** continua exigindo horas de operação observadas (`OBSERVED_OPERATION`, §IX): não se converte L/h em coeficiente por unidade via \(q/\rho\) nem pelo tempo inferido de \(F(m)\). Em planejamento (RFP), CPUs com consumo só horário não são certificáveis até que o catálogo traga coeficientes por unidade entregue com fonte.

## N7 — frentes a partir da composição da equipe

Com a composição de **uma** frente conhecida (equipe padrão da produção, \(a_{ig}^{front}\)), o número de frentes que uma alocação \(x_g\) sustenta é \(m=\min_g\lfloor x_g/a_{ig}^{front}\rfloor\) sobre os recursos da equipe presentes na alocação, coerente com \(a_{ig}(m)=m\,a_{ig}^{front}\) e \(d_{gj}=\sum_i a_{ig}(m_{ij})\) (CAPACIDADE_E_RECURSOS). Somar unidades heterogêneas (ex.: 1 usina + 2 carregadeiras + 1 gerador + 3 serventes = 7) é proibido: programaria a vazão de sete frentes sobre uma usina contratada (capacidade fictícia). Recursos fixos da atividade (infraestrutura compartilhada) não escalam com \(m\). Sem composição conhecida mantém-se o legado (tipos-equipe somados). Evidência: vetor `per_front_team_units_scale_with_fronts` em `physical_calendar_v1.json`; o E2E ouro verifica \(m_{ij}\,a_{ig}^{front}=d_{gj}\) contra a testemunha P16.

**N7.1 — a mesma regra a jusante do cronograma (#206).** O número de frentes de uma atividade fora do Skill04 é o pico \(\max_j m_{ij}\) materializado no cronograma (semanas de rampa com \(n_{max}\cdot f\) arredondam para \(n_{max}\)); nunca \(\sum_g x_g\) das unidades atribuídas. Isso vale para o dimensionamento do Skill05 (`num_equipes_base`) e para a inferência de pool do Skill04 (\(e_{ir}=m_i\,a_{ir}^{front}\), ADR-091 D4), cuja demanda era inflada por \(\sum_g a_g^{front}\) (ex.: 7 usinas para uma frente). A demanda do pool é \(d_{gj}=\sum_i m_{ij}\,a_{ig}^{front}\) por tipo. Evidência: vetor `pool_demand_from_fronts_v1.json` (oráculo independente `pool_demand_reference.py`) com paridade de produção. Pendente sob #206: o fallback do Skill04 que soma tipos-equipe quando a composição da produção é desconhecida — pela decisão de não manter legado, passa a não avaliável.

## N8 — tarifa P16 de todo projeto: taxa de catálogo + termos contratuais declarados (#206)

Não existe caminho financeiro estimado: o custo contratual de um recurso só existe pela testemunha P16, e a tarifa dessa testemunha tem duas origens, nunca misturadas com inferência.

**Taxa ativa (derivada, exata).** \(\tau_g^{ativo}=c_g\,d\,h\), com \(c_g\) a mesma taxa horária de catálogo do envelope \(C^{cat}\) (§XIV.2): preço mensal \(V_g^{mensal}/s_{mes}\) (\(s_{mes}=1461/336\)) ou preço horário \(\times\,d\,h\). É um racional exato; **não** se arredonda a centavos antes da agregação (CONVENCOES §5) — as tarifas P16 aceitam decimal finito ou racional `a/b`, nunca ponto flutuante. Unidade de preço diferente de `mes`/`h`, recurso ausente do catálogo ou tipo não contratual (≠ EQ/MO) ⇒ contrato desconhecido.

**Termos contratuais (declarados).** Regime de standby, mobilização, desmobilização e gap ocioso máximo não constam do catálogo e não se inferem (P13-A). O projeto declara um **padrão** e, onde diferir, **sobreposições por tipo de recurso**, mescladas campo a campo: `regime` ∈ {`FULL_RATE_STANDBY` (\(\tau^{ocioso}=\tau^{ativo}\)), `DISCOUNTED_STANDBY` (exige `idle_week` declarada \(<\tau^{ativo}\))}, `mobilize`, `demobilize` (racionais exatos; zero só quando declarado), `max_idle_gap` (inteiro ≥ 0) e `source` (procedência). Uma sobreposição pode declarar `active_week` (tarifa contratada), que substitui a taxa de catálogo com sua procedência. `EXPLICIT_OFF_HIRE` ainda não é suportado ⇒ desconhecido.

**Falha fechada.** Qualquer campo ausente, inexato (float) ou inconsistente torna o recurso `UNKNOWN_CONTRACT`: não se produz tarifa, e toda grandeza que dependa do custo desse recurso é `NOT_EVALUATED` — nunca zero, nunca estimativa.

Evidência: oráculo independente `contract_tariff_reference.py` e vetor `pool_contract_tariff_v1.json`; paridade de produção (`p16_tariff_derivation.py`); as tarifas declaradas à mão nos projetos ouro são exatamente o arredondamento a centavos (half-even) da taxa derivada, para os 9 recursos.

**N8.1 — `rcpsp_spec` por recurso derivado dos dados do projeto (#206).** Quando o chamador não fornece `rcpsp_spec` (nem contagens manuais de equipes), os Skills 04 e 05 derivam a especificação por tipo de recurso do que o projeto já declara: `required_resources` de cada atividade = equipe padrão da produção por frente (\(a_{ig}^{front}\), N7); `duration_weeks` = duração nominal de uma frente \(\lceil Q_i/(\rho_i\,d\,h)\rceil\); `resource_pool` = disponibilidade física **explicitamente configurada** (Skill03), restrita aos tipos usados, que deve cobrir ao menos uma frente de cada atividade. As precedências vêm da EAP. As tarifas P16 dessa especificação são as de N8 (taxa de catálogo + `contract_terms` declarados do projeto). Nada é inferido: CPU, produção, composição, taxa ou cobertura de pool ausentes impedem a derivação (motivos reportados em `VAL-RCPSP-NAO-DERIVAVEL`); tipos sem termos contratuais completos ficam sem tarifa (`VAL-P16-CONTRATO-DESCONHECIDO`) e o custo não é avaliado. Enquanto o caminho legado existir, a derivação por "família de equipe" só permanece quando a derivação por recurso não é possível.

Evidência: oráculo `pool_spec_reference.py` e vetor `pool_spec_from_project_v1.json` com paridade de produção; a especificação derivada é idêntica à escrita à mão nos dois projetos ouro (equipe por frente, durações, pool); E2E `test_formalism_golden_derived_inputs.py`: com os termos declarados o projeto ouro certifica GO sem `rcpsp_spec` escrito à mão e com todas as fases conferidas pelos oráculos; com tarifas só derivadas certifica com racionais exatos; sem termos declarados nada é estimado.

## N9 — preço exato de todo projeto: termos de precificação declarados no perfil (#206)

O P21 precifica o livro exato P20 apenas com entradas declaradas. Quando o projeto não fornece `p21_pricing_evidence`, a declaração vem do bloco `precificacao_exata` do perfil da construtora (padrão do projeto), e do envelope de catálogo derivado:

- **Markup por categoria** \(\beta^k\): cada linha da `tabela_bdi` declara as parcelas \(AC, R{+}S{+}G, DF, L\) e os tributos \(T\) como decimais exatos, e \(\beta\) é a fórmula do Acórdão TCU 2622/2013-Plenário em racionais exatos,
\[
\beta=\frac{\big(1+(AC+R+S+G)\big)(1+DF)(1+L)}{1-T}-1 ,
\]
com \(R{+}S{+}G\) **somado** a \(AC\) (não multiplicado) e \(T<1\). Linhas: MO ← `mao_obra`; EQ ← `servicos` (equipamento operando dentro de um serviço recebe o BDI do serviço; BDI reduzido só para mero fornecimento, Súmula TCU 253 — não há mistura locação/manutenção); MAT ← `material`; COMB ← `diesel`; IND ← `indireto`.
- **Piso de BDI do gate V2**: `piso_bdi_regulatorio.por_tipo_obra[tipo_obra]`, com fonte. No perfil Mendes Lobo, o 1º quartil da Tabela 2 do Acórdão 2622/2013 (rodovias e ferrovias 19,60%; saneamento 20,76%) — política da empresa que referencia o TCU; o acórdão define faixas referenciais, não mínimo legal.
- **Margem mínima**: `faixa_margem_aceitavel.min` do perfil.
- **Escopo de estoque**: `escopo_estoque` (`NO_INVENTORY` no perfil Mendes Lobo: material orçado como consumido).
- **Base de catálogo e base regulatória**: \(C^{cat}\) derivado (N2), com a impressão digital do envelope como base comum.

O livro de consumo exato (P18) roda sempre que todo contrato do pool tem testemunha P16 (um booleano explícito do chamador é respeitado). **Falha fechada:** bloco ausente, linha ou campo faltando, número em ponto flutuante, tipo de obra sem piso declarado, tributos ≥ 100% ou \(C^{cat}\) não derivável ⇒ nenhuma declaração é produzida e o preço fica não avaliado (`VAL-P21-NAO-AVALIADO`), nunca estimado. Não há tabela padrão no código para o caminho exato.

Evidência: oráculo `bdi_tcu_reference.py` e vetor `economic_bdi_tcu_v1.json` (inclui o caso que distingue soma de produto); paridade de produção; E2E `test_profile_prices_the_exact_ledger_with_nothing_hand_written`: o projeto ouro sem `rcpsp_spec`, sem evidência P21 e sem flag P18 chega a uma decisão exata e atribuível (com a tabela declarada — material e diesel a 4% — o escopo, dominado por material, fica abaixo do piso e da margem: NOGO só por V2 e PROFITABILITY, com custo, preço e BDI conferidos pelos oráculos).
