# P19-B — custo de posse de estoque, por lançamento indireto exclusivo

O custo de aquisição do bem (g), (C^{cons}_g=p_g U_g), decorre do consumo
físico P18-B. Ele **não** é o custo de posse do mesmo bem. O P19-B utiliza
apenas saldos auditados e sem déficits do P19-A e não reconstrói Q, horas ou
produtividade física.

**Convenção temporal normativa desta implementação**: saldo de **fim da
semana após recebimentos, geração, descarte e consumo**. A taxa declarada
(h_g) tem unidade **R$/unidade_física/semana**. A fórmula exata é

[
C^{inv}=sum_{g,j}h_g^{END},
operatorname{convert}(S_{g,j}^{END},unid_g,unid_{h_g}).
]

`StockHoldingPolicy` não foi introduzida; a entidade explícita é
`HoldingTariff(good_id,amount_per_unit_week,physical_unit,basis)` e
`basis=END_OF_WEEK` é obrigatória. Todos os valores são `Fraction`;
a conversão usa o registro físico comum. Falta de tarifa, unidade
incompatível, débito negativo, fonte duplicada ou estoque inviável produz
erro explícito, **não** supressão de custo.

**Titularidade financeira:** cada linha
`("STOCK_HOLDING",good_id,week)` é `PostingNature.HOLDING`, categoria
`IND`, e será lançada exatamente uma vez no diário P17-A. Assim:

[
C^D_{novo}=C^D_{base},qquad
C^I_{novo}=C^I_{base}+C^{inv}.
]

O valor do consumível `MAT/COMB` não muda com a política de posse quando
a quantidade física consumida é a mesma, mas `C^{inv}` pode mudar com
o tempo de recebimento. A base temporal é versionável no contrato, não
escolhida a posteriori para reduzir custo.

**Fronteira:** `HOLDING_PREVIEW_NOT_PROJECT_GO` permanece preview; o
fingerprint de tarifa, recibos, composição/cenário, observabilidade,
replanejamento e BDI indireto serão validados em P19-C/P20/P23. Sem
comprovação física, não se cria lucro ou aprovação regulatória.
