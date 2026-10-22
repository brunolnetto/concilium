# Contrato normativo de notação, unidades e intervalos — P09-A

**Status:** convenções transversais aceitas para revisão; não certifica, por si só, as equações de produtividade, custo ou preço.
**Escopo:** [FORMALISMO_LONGO.md](FORMALISMO_LONGO.md) (§0, I, II, IX, XIV), espelhado nos documentos [resumido](FORMALISMO_RESUMIDO.md) e [LaTeX](formulario_longo.tex).
**Base auditada:** main `f8e5b65f7bc708894489fe52a528df6cd34e0b94`.
**Governança:** issue #9 (P09-A); a paridade automatizada pertence a P09-B. A resolução de equações estruturalmente inconsistentes pertence a #10–#13.

## 1. Classes de enunciados

- **NORMATIVO:** unidade, domínio, significado do índice temporal, identidade de balanço e convenção da interface entre etapas.
- **HIPÓTESE-BASE:** contrato homogêneo, standby cobrado integralmente, ausência de perdas, consumo proporcional a Q. Deve ser identificada no cálculo; não é lei física universal.
- **VARIANTE CONTRATUAL:** política de custos e consumo que depende de contrato real (standby descontado, perdas, combustível ocioso). Deve ter parâmetro explícito e saída separada.
- **PENDENTE:** expressão sem demonstração ou com contraexemplo em #10–#13. Não pode servir como sinal GO/NOGO até corrigida e ensaiada.

## 2. Dicionário dimensional mínimo

| Símbolo | Dimensão | Observação / restrição |
|---|---|---|
| `Q_i`, `q_ij` | unidade física da atividade `u_i` | `Q_i>0` no regime de atividade produtiva; `q_ij>=0`; soma semanal deve fechar Q |
| `rho_i^front`, `rho_i^peak`, `F_i(m)` | `u_i/(h·frente)`, `u_i/h`, `u_i/h` | `F_i(m)` incorpora as frentes; `rho_i^peak=F_i(m_i^max)`; validade de extrapolação linear é hipótese condicionada em #10 |
| `j`, `j_i^0`, `N_i`, `tau` | contagem inteira de semanas | `N_i>=1`, `tau=j-j_i^0`, `0<=tau<N_i` |
| `m_i^0`, `m_i^1`, `m_i^max`, `m_ij` | frentes (inteiro, adimensional) | `1<=m_i^0,m_i^1<=m_i^max` durante atividade |
| `mu_i^+`, `mu_i^-` | frentes/semana | inteiros **não negativos**; valor zero é válido |
| `h_i`, `d_i` | `h/dia`, `dia/semana` | `h_i*d_i` tem dimensão `h/semana` |
| `alpha=F/Fmax` (diagnóstico), `eta_p`, `eta_w`, `epsilon_exog`, `phi`, `theta` | razão adimensional | `alpha` é capacidade relativa, **não** perda; `eta_p` e `eta_w` são fatores físicos exógenos; `phi` é fechamento |
| `kappa_r`, `p_g` | `unidade_g/h_operacional`, `R$/unidade_g` | produto `kappa_r*p_g` tem dimensão `R$/h_operacional` |
| `V_r^mensal`, `s_mes` | `R$/mês`, `semanas/mês` | `V_r^mensal/(s_mes*d_i*h_i)` tem dimensão `R$/h` |
| `gamma^K`, `gamma^V`, `gamma^cat` | `R$/h_operacional` | a soma só é válida na mesma base horária |
| `C`, `P` | `R$` | moedas não podem ser somadas se diferentes |
| `beta`, `R`, `delta`, `zeta`, `pi`, `mu` (margem) | razão | porcentagens são armazenadas como frações, não pontos percentuais |

**Unidades heterogêneas:** `u_i` e `unidade_g` não são intercambiáveis. Conversão depende de fator explícito; nunca inferir que `kg`, `t`, `L` e `m³` são equivalentes. Um proxy monetário de MAT não comprova volume físico (ver #18).

## 3. Domínio da mobilização e semana retangular

`W_i=(m_i^0,mu_i^+,m_i^1,mu_i^-,m_i^max)` tem domínio
`N_{>0} × N_{>=0} × N_{>0} × N_{>=0} × N_{>0}`,
com `m_i^0,m_i^1<=m_i^max`. Portanto, `mu_i^+=mu_i^-=0` **não** contradiz o domínio.

O perfil retangular de `m_i^max` frentes é definido com
`mu_i^+=mu_i^-=0` **e** `m_i^0=m_i^1=m_i^max`.
Sem a igualdade adicional, o mínimo das três retas dá `min(m_i^0,m_i^max,m_i^1)`, e não necessariamente `m_i^max`.

**Pendente em #12:** `r+d<=N_i` aparece sem definição de `r,d`. Não confundir `d_i` (dias/semana) com ramp-down. Uma futura condição para exigir platô deve definir ramp-up/down em número de *transições*, inclusive `mu=0`, e distinguir perfis triangulares dos trapezoidais. Não usar a condição indefinida como prova de convergência.

## 4. Índices e intervalos

- `j` é semana absoluta inteira identificada no projeto (o índice inicial deve ser declarado; representação canônica da especificação: primeira semana `j=1`). `tau=0` é a primeira semana relativa da atividade.
- A atividade está ativa nas semanas discretas `j_i^0, ..., j_i^0+N_i-1`. Na álgebra de intervalos do pool, representar a mesma ocupação por **intervalo semiaberto** `[j_i^0, j_i^0+N_i)`.
- A representação inclusiva `[a,b]` de semanas ocupadas converte-se em `[a,b+1)`.
- Duas ocupações inclusivas `[a,b]` e `[c,d]` (com `b<c`) têm `max(0,c-b-1)` semanas vazias. Na representação semiaberta `[a,b+1)`, `[c,d+1)`, o gap é `max(0,c-(b+1))`.
- Portanto semanas imediatamente adjacentes `[1,2]` e `[3,5]` têm **gap zero**, não um.
- A desigualdade econômica de permanência compara `gap*c_sem` com `c_mob+c_demob`; sob custos iguais e viabilidade satisfeita, o **desempate determinístico é manter** a cadeia (menos transições). O regime com tarifa de idle distinta é variante de #13.
- O intervalo de contrato remunera semanas completas no regime-base K, inclusive semana final com `0<phi<1`; consumo V é gerado pelas quantidades fisicamente entregues, não por permanência.

**Importante:** a liberação de sucessores mediante conclusão *ao fim da semana* deve respeitar a fronteira temporal seguinte. A política completa de precedência e solver é tratada em #12/#15.

## 5. Divisão, precisão e falhas

- Quantidade física e custo devem manter precisão de cálculo até a agregação; evitar arredondar células semanais antes de testar `sum(q)=Q`, invariância V ou conciliação de custos.
- Exibir R$ com duas casas **não** significa truncar internamente ou aceitar diferença não auditada de R$0,01.
- Tolerâncias `tol_Q` (em `u_i`) e `tol_C` (em R$) devem ser declaradas e versionadas antes da certificação. Nos vetores decimais exatos do oráculo #22, a tolerância é zero.
- Denominador nulo (`rho<=0`, base de BDI zero, `Q<=0`) é resultado **indefinido/inviável**, nunca substituir silenciosamente por 1, 1000 ou markup 0%.
- Estados `PASS/FAIL/UNKNOWN/NOT_EVALUATED` são distintos. No modo certificado, `UNKNOWN` e `NOT_EVALUATED` não autorizam GO; preview pode apresentar aviso, explicitando que não há certificação.

## 6. Casos de fronteira verificáveis

| Caso | Dados | Resultado normativo |
|---|---|---|
| Rampa de taxa zero | `mu+=mu-=0; m0=m1=mmax=2` | perfil de 2 frentes constante |
| Rampa zero sem identidade | `mu+=mu-=0; m0=1; m1=1; mmax=4` | mínimo algébrico 1; **não** declarar retângulo de 4 |
| Intervalos adjacentes | `[1,2]` e `[3,5]` inclusivos | `gap=0` |
| Uma semana de espera | `[1,2]` e `[4,5]` inclusivos | `gap=1` |
| Empate de permanência | `gap*c_sem=c_mob+c_demob` com `G_viável>=gap` | manter no regime-base, por desempate |
| Fechamento parcial | capacidade nominal=400, `Q=100`, `phi=0,25` | semana K integral, V pela quantidade 100 |
| Produtividade zero | `rho=0`, `Q>0` | inviável/indefinido; sem preço certificado |

## 7. Pendências explícitas (não converter em verdades por convenção)

- #10: a documentação **já** substituiu `rho*eta_s*m` por `F_i(m)` (#31); a migração dos consumidores de runtime e a prova diferencial P10-B seguem pendentes.
- #11: razões e eficiências médias com fechamento fracionário precisam de nova prova.
- #12: início, calendário absoluto, rampas, precedências e RCPSP estão acoplados.
- #13: standby integral e consumível sem perdas são **hipóteses**, não universais.

P09-B acrescenta testes executáveis de paridade entre LONGO/RESUMIDO/TeX e fronteiras exatas, independentes do runtime. #22 mantém o oráculo numérico autônomo. Este anexo não declara o produto certificado.

**Correção P10-A:** [CAPACIDADE_E_RECURSOS.md](CAPACIDADE_E_RECURSOS.md) distingue frentes mobilizadas, capacidade $F_i(m)$, demanda contratual $d_{gj}$ e standby $s_{gj}$; não há eficiência de alocação multiplicativa.

## 9. Unidades separadas de calibragem física (P09-B)

A produtividade **por frente** `rho_i^front` possui unidade `u_i/(h·frente)`; multiplicá-la por `m` [frentes] só é permitido sob hipótese de frentes independentes. A função efetiva `F_i(m)` e a capacidade de pico `rho_i^peak` possuem `u_i/h`, portanto multiplicar novamente por `m` é dimensionalmente incorreto. Para `U_g=κ_g^out·Q_i`, `κ_g^out` tem `unid_g/u_i`, enquanto taxas de consumo horário `κ_g^h` têm `unid_g/h` e requerem horas **reais** de operação. O livro K ativo/idle usa tarifas e semanas na mesma base; o preço `p_g` tem `R$/unid_g`. Os testes [test_normative_boundaries.py](../../../../tests/reference_formalism/test_normative_boundaries.py) executam essa álgebra sem importar módulos de produção.
