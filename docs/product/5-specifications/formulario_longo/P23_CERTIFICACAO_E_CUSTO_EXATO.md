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

## N9 — preço exato de todo projeto: camadas de markup declaradas no perfil (#206)

O P21 precifica o livro exato P20 apenas com entradas declaradas. Quando o projeto não fornece `p21_pricing_evidence`, a declaração vem do bloco `precificacao_exata` do perfil da construtora (padrão do projeto) e do envelope de catálogo derivado.

**Camadas, não uma taxa.** Cada linha da `tabela_bdi` declara, em decimais exatos, as três camadas do markup da sua categoria e a sua `natureza` (`servico` ou `fornecimento`): *overhead* (\(AC\), \(R{+}S{+}G\), \(DF\)), *lucro* (\(L\)) e *tributos* sobre o preço (\(t_x\), \(T=\sum_x t_x<1\)). O preço de um custo \(C\) segue a estrutura do Acórdão TCU 2622/2013-Plenário,
\[
P=\frac{C\,\big(1+(AC+R{+}S{+}G)\big)(1+DF)(1+L)}{1-T},
\]
e decompõe-se exatamente, na ordem em que a fórmula o constrói:
\[
O^{AC}=C\,AC,\quad O^{RSG}=C\,(R{+}S{+}G),\quad O^{DF}=C\,(1+AC+R{+}S{+}G)\,DF,\quad
\Lambda=C\,(1+AC+R{+}S{+}G)(1+DF)\,L,\quad \Theta_x=t_x\,P,
\]
com a identidade \(C+O^{AC}+O^{RSG}+O^{DF}+\Lambda+\sum_x\Theta_x=P\). O markup da categoria é consequência das camadas, \(\beta=P/C-1\); `bdi_by_category` deve coincidir exatamente com ele. Linhas: MO ← `mao_obra`; EQ ← `servicos` (equipamento operando dentro de um serviço recebe as camadas do serviço — não há mistura locação/manutenção; BDI reduzido só para mero fornecimento, Súmula TCU 253); MAT ← `material`; COMB ← `diesel`; IND ← `indireto`.

**Instancial e agregado.** Todas as parcelas são lineares em \(C\): as mesmas taxas decompõem um lançamento do livro P20 (nível instancial) ou qualquer agregado de lançamentos — contrato, atividade, semana, categoria, projeto — por simples soma. O resultado traz a decomposição por categoria e total em `resultado.markup_layers`, e ela deve reconstruir o custo P20 e o preço P21.

**Margem mínima como critério construtivo.** \(P-C\) contém overhead, tributos e lucro; compará-lo a uma margem mínima mistura camadas. Com as camadas identificadas, o mínimo do perfil (`faixa_margem_aceitavel.min`) é um critério sobre a **contribuição da camada de lucro ao preço**, \(\Lambda^{tot}/P\ge m_{min}\), com \(\Lambda^{tot}\) somado sobre o custo operacional direto e indireto. O gate PROFITABILITY usa essa razão sempre que o preço é construído por camadas; uma declaração plana (sem camadas) continua avaliada por \((P-C)/P\) enquanto existir.

**Piso de BDI por categoria e agregado ponderado.** O perfil declara o piso por natureza, com fonte — no perfil Mendes Lobo, o 1º quartil da Tabela 2 do Acórdão 2622/2013: serviços por tipo de obra (rodovias e ferrovias 19,60%; saneamento 20,76%) e mero fornecimento 11,10% — política da empresa que referencia o TCU; o acórdão define faixas referenciais, não mínimo legal. Cada categoria é comparada ao piso da sua natureza (categorias abaixo do piso são reportadas em `bdi_below_category_floor`), e o piso agregado do gate V2 é a média ponderada pela composição de catálogo,
\[
\underline{\beta}=\frac{K^{cat}\,\underline{\beta}^{MO/EQ}+V^{cat}\,\underline{\beta}^{MAT/COMB}}{C^{cat}},
\]
com \(K^{cat}\) e \(V^{cat}\) os blocos contratual e consumível do envelope (N2); MO/EQ e MAT/COMB devem partilhar o piso, pois o envelope não os separa.

**Demais termos.** Escopo de estoque: `escopo_estoque` (`NO_INVENTORY` no perfil Mendes Lobo: material orçado como consumido). Base de catálogo e base regulatória: \(C^{cat}\) derivado, com a impressão digital do envelope como base comum. O livro de consumo exato (P18) roda sempre que todo contrato do pool tem testemunha P16 (um booleano explícito do chamador é respeitado).

**Falha fechada.** Bloco ausente, linha, camada ou natureza faltando, número em ponto flutuante, tipo de obra sem piso declarado, \(T\ge1\), markup diferente do das camadas, camadas que não reconstroem custo e preço, ou \(C^{cat}\) não derivável ⇒ o preço fica não avaliado (`VAL-P21-NAO-AVALIADO`), nunca estimado. Não há tabela padrão no código para o caminho exato.

Evidência: oráculos `bdi_tcu_reference.py` / `economic_bdi_tcu_v1.json` (fórmula, incluindo o caso que distingue soma de produto) e `markup_layers_reference.py` / `economic_markup_layers_v1.json` (decomposição, participação do lucro, piso ponderado), com paridade de produção e a prova de linearidade (instancial = agregado); testes do gate para o critério da camada de lucro; E2E `test_profile_prices_the_exact_ledger_with_nothing_hand_written`: o projeto ouro sem nada escrito à mão chega a uma decisão exata e atribuível por camada — com as camadas declaradas (material e diesel: só 4% de lucro) o preço é 94,23% custo, 0,62% overhead, 4,14% lucro e 1,02% tributos; MAT e COMB ficam abaixo do piso de fornecimento, o BDI (9,35%) abaixo do piso ponderado (≈11,6%) e a camada de lucro abaixo de 6%: NOGO só por V2 e PROFITABILITY.

**N9.1 — declaração do projeto sobre as camadas do perfil: tributos e lucro (#206).** A `tabela_bdi` do perfil é o padrão da construtora; a incidência tributária e o lucro são do **projeto** (ADR-023 §D6–D7: regime, município, negociação comercial). O projeto pode declarar, em decimais exatos, a entrada `bdi_projeto_exato` do Skill06:

```json
{"schema": "concilium.projeto.bdi-exato.v1",
 "fonte": "perfil BDI do projeto v2 — ISS 2% (lei municipal)",
 "linhas": {"mao_obra": {"l": "0.08",
                         "tributos": {"iss": {"aplicavel": true, "aliquota": "0.02"},
                                      "cofins": {"aplicavel": false}}}}}
```

*Fusão campo a campo.* Para cada linha \(r\) da `tabela_bdi` e cada campo declarado pelo projeto,
\[
L_r^{ef}=\begin{cases}L_r^{proj} & \text{se o projeto declara } l\\ L_r^{perfil} & \text{caso contrário}\end{cases}
\qquad
t_{x,r}^{ef}=\begin{cases}0 & \text{se o projeto declara } x \text{ não aplicável}\\ t_{x,r}^{proj} & \text{se o projeto declara } x \text{ aplicável}\\ t_{x,r}^{perfil} & \text{caso contrário,}\end{cases}
\]
e \(AC\), \(R{+}S{+}G\), \(DF\) e a `natureza` são **sempre os do perfil**: overhead é da empresa e o piso segue a natureza da linha, nenhum dos dois é sobreponível por projeto. A declaração é esparsa — só os campos nomeados mudam; uma linha ou tributo não nomeado permanece o do perfil, e as linhas são independentes (declarar `mao_obra` não altera `servicos`, logo não altera EQ). O perfil deve estar completo por si: o projeto substitui campos, não preenche lacunas.

*Consequências, não novas entradas.* As camadas efetivas por categoria são as de N9 calculadas sobre as linhas fundidas; `markup_layers`, `bdi_by_category` (\(\beta=P/C-1\) das camadas efetivas), a decomposição instancial/agregada e o critério da camada de lucro derivam delas sem outra regra. Os pisos por categoria e o piso agregado ponderado não mudam com a declaração do projeto.

*Proveniência.* A declaração P21 registra em `markup_layers_provenance`, para cada categoria e cada campo de camada (`ac`, `rsg`, `df`, `l` e cada tributo), a origem `profile` ou `project`, a referência da tabela do perfil e, havendo declaração do projeto, a sua `fonte` e a impressão digital SHA-256 do JSON declarado; o resultado a expõe em `resultado.markup_layers.provenance`. Um campo atribuído ao projeto sem referência do projeto (ou o inverso) é inconsistente.

*Falha fechada.* Linha ou tributo desconhecidos, campo que a linha do perfil não tem, tentativa de sobrepor overhead ou `natureza`, número em ponto flutuante, valor negativo, `aplicavel` não booleano, tributo aplicável sem alíquota, tributo não aplicável com alíquota (seria ignorada), declaração ou linha vazia, `fonte` ausente ou \(T^{ef}\ge 1\) ⇒ não há declaração e o preço fica não avaliado (`VAL-P21-NAO-AVALIADO`, com o motivo). O `PerfilBdiProjeto` legado (ADR-023), que guarda alíquotas e lucro em ponto flutuante, **não é convertido**: se o chamador o fornece (`bdi_perfil`/`perfil_bdi`) sem `bdi_projeto_exato`, o projeto tem termos próprios que o caminho exato não pode ler e o preço exato fica não avaliado, em vez de ser calculado com o padrão da empresa. `bdi_projeto_exato` junto de um `p21_pricing_evidence` escrito à mão (que já declara as suas camadas) ou sem os livros exatos habilitados também é reportado e não é usado.

*Persistência e injeção.* A declaração do projeto é salva em decimais exatos (strings), ao lado do perfil legado e com o mesmo esquema de versões: `bdi/perfil_bdi_exato.json` (cabeça), `bdi/perfil_bdi_exato_v{NNN}.json` (retrato imutável de cada versão, com `versao`, `content_hash` = SHA-256 do JSON declarado, `confirmado_por`, `confirmado_em`, `motivo_revisao`) e, da versão 2 em diante, `bdi/perfil_bdi_exato_diff_v{NNN}.json` (campos alterados; `motivo_revisao` obrigatório). Gravam-na a ferramenta MCP `salvar_perfil_bdi` (parâmetro `declaracao_exata`) e o comando `concilium bdi update --from-file` (arquivo com o schema `concilium.projeto.bdi-exato.v1`), ambos validando com o mesmo código da fusão antes de gravar: declaração inválida não é salva e o motivo é devolvido; a cabeça adulterada (hash divergente) não é sobrescrita e um retrato existente nunca é substituído. O arquivo exato **só** é escrito a partir de strings exatas — nunca a partir do modelo em ponto flutuante (`tributario`/`lucro`), que continua servindo apenas ao estágio legado. Ao preparar as entradas do Skill06, o runtime carrega a cabeça e a entrega como `bdi_projeto_exato`; uma entrada explícita do run (`bdi_projeto_exato` ou um `p21_pricing_evidence` escrito à mão) prevalece. Se o projeto tem apenas o perfil legado em ponto flutuante (`bdi/perfil_bdi.json`), ou se o arquivo exato salvo está danificado, **nada é convertido nem suposto**: o preço exato fica não avaliado (`VAL-P21-NAO-AVALIADO`) com o motivo, que pede para salvar de novo o perfil em forma exata — nunca é calculado com o padrão da empresa. A impressão digital registrada em `markup_layers_provenance.project` coincide com o `content_hash` da versão salva.

Evidência: oráculo independente `project_markup_merge_reference.py` e vetor `economic_project_markup_merge_v1.json` (ISS negociado de 5% para 2%: \(T\) 9,73% → 6,73%, preço de 100 de 1172731/9027 para 1172731/9327; lucro negociado com ISS não aplicável; linha de fornecimento que passa a ter COFINS/PIS; ausência de declaração = perfil; agregação por soma; casos de falha), com paridade de produção em `test_project_markup_merge.py` (fusão, proveniência, consistência `bdi_by_category` = \(\beta\) das camadas fundidas, transporte no Skill06) e em `test_project_bdi_exact_store.py` (validação ao salvar, versões e diff, precedência da injeção, projeto só com perfil em ponto flutuante ⇒ não avaliado, e a declaração salva alterando o resultado por camadas através do Skill06).
