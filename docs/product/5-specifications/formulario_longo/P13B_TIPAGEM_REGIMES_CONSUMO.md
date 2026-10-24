# P13-B — Seletores tipados de contrato e consumo físico

**Issue:** #13; **épico:** #8; **onda:** W0.
**Natureza:** diagnóstico read-only com estado NOT_PROJECT_GO, sem certificação financeira ou emissão de GO.

## Contratos de presença

O seletor 'RecursoContrato.regime_economico_p13' é tipado, opcional e exclusivamente:
- FULL_RATE_STANDBY: c_idle = c_active >= 0.
- DISCOUNTED_STANDBY: 0 <= c_idle < c_active.
- EXPLICIT_OFF_HIRE: semanas de desligamento, presença física zero e transições de mobilização comprovadas.

Os outros campos canônicos obrigatórios para validar uma projeção são 'origem_regime_p13' e 'moeda_regime_p13'. O valor padrão None significa NOT_EVALUATED; campos monetários legados como 'rho_idle_eq=1.0' ou custo ocioso 0.0 não demonstram regime válido. UNKNOWN_CONTRACT não é um fallback financeiro.

Uma 'ContractRegimeEvidence' traz contrato, resource_type, fonte contratual, moeda, tariff ResourceTariff (Fraction exato) e semanas off_hire_weeks. 'witness_contract_regime' reconcilia a declaração contra identidade e proveniência canônicas e 'ExactPoolResult' P16:

- demanda física d_gj, presença paga x_gj >= d_gj, standby s_gj=x_gj-d_gj;
- K_active=sum(d_gj*c_active), K_idle=sum(s_gj*c_idle);
- MOB/DEMOB em IND, cada evento com propriedade exclusiva P17;
- off-hire significa ausência de contrato, NÃO standby grátis;
- o baseline K=c_active*sum(x) somente é válido se c_idle=c_active.

A comparação keep/split usa gap*c_idle e c_mob+c_demob com verificação de viabilidade. Em empate viável, KEEP é o desempate determinístico canônico.

## Consumo físico — independente da presença contratual

O campo 'RecursoConsumivelCanonical.regime_consumo_p13' é opcional e exclusivamente:
- OUTPUT_PROPORTIONAL: U=kappa_out*Q; taxa/preço físicos fixos, sem perdas/idle. Nestas hipóteses, V(Q) é invariante à repartição semanal.
- OUTPUT_WITH_MEASURED_LOSS: U=kappa_out*Q+L, com L fisicamente medido, unidade e origem; delta monetário p*L, sem alegar invariância universal.
- HOURLY_WITH_MEASURED_IDLE: U=kappa_hour*H_real+I+L; horas operadas, idle e perdas declarados, nunca inferidos de Q/F(m).

O consumo deve carregar 'origem_taxa_consumo_p13' e 'origem_preco_consumo_p13'. Falta de seletor, fonte, preço ou medida é NOT_EVALUATED; zero deve ser comprovado. 'MeasuredExtra' contém quantidade Fraction, unidade física e source_id; origem duplicada é rejeitada. 'PhysicallyPricedGood' P18 converte unidades apenas entre dimensões compatíveis. Proxy R$/h nunca se converte silenciosamente em volume.

As testemunhas P13-B não geram 'PhysicalPurchase' nem lançamentos P17. O ledger autoritativo mantém: CONTRACTUAL_ACTIVE e CONTRACTUAL_IDLE em MO/EQ (K); CONSUMABLE_ACQUISITION em MAT/COMB (V); MOBILIZATION_EVENT, DEMOBILIZATION_EVENT, INVENTORY_HOLDING em IND. Um evento financeiro possui um único event_id e uma única natureza/categoria. Não criar custo duplicado, não ratear K de pool arbitrariamente, não reescrever margem histórica.

## Exemplos exatos e fronteiras

1. d=(1,0,0,1), x=(1,1,1,1), c_act=100, c_idle=25, mob=demob=40: K_act=200, K_idle=50, IND=80, total=330. A regra baseline daria o resultado errado K=400.
2. Off-hire em semana sem presença: duas cadeias implicam dois pares MOB/DEMOB. Standby e off-hire não são sinônimos.
3. kappa_out=2 L/m3, Q=100 m3, p=5 R$/L: U=200 L e V=1000, tanto em uma entrega como em 40+60. Perda medida de 20 L gera delta V=100 e custo total V=1100.
4. kappa_hour=3 L/h, H_real=10h, idle=2L, perdas=1L: U=33L, V=165 e delta adicional V=15. Sem H_real, sem fonte ou sem unidade => rejeição.
5. Integração P16+P17+P18: K=250, V=1100, IND=80, total=1430, proveniência exclusiva. Não emitir GO.

Os testes operacionais estão em 'tests/unit/application/scheduling/test_p13b_typed_economic_regimes.py' e a paridade LONGO/RESUMIDO/TeX está em 'tests/reference_formalism/test_p13b_normative_parity.py'. Aceite de #13 é local; #22, #17-#21 e #23/#24/#26 ainda requerem validações independentes para GO.
