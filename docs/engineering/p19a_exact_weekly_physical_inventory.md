# P19-A — Livro físico semanal do estoque (pré-certificação)

## Fonte e identidade

A fonte de demanda é exclusivamente `AcquisitionEvidenceLine` da fronteira
P18-B, com `physical_quantity` e `physical_unit` declarados. Não se
recalcula produtividade `F(m)`, não se converte dinheiro em massa e não se
interpreta o lançamento monetário `CONSUMABLE_ACQUISITION` como recebimento
logístico de material. Uma compra física tem prova própria de entrega.

O identificador de origem é único em **consumo, entrega externa e geração
interna**. Para a mesma atividade, bem e semana, não é permitido somar o plano
e a medição observada da mesma utilização. Mais de uma medição da mesma classe
ainda exige identidades distintas.

## Conservação de massa (Fraction)

Para bem `g` e semana `j`, com entradas declaradas:

```text
A[g,j] = S[g,j-1] + E[g,j] + G[g,j]
O[g,j] = max(0, A[g,j] - capacidade[g])  # se houver limite
F[g,j] = min(A[g,j]-O[g,j], D[g,j])
D[g,j] = F[g,j] + deficit[g,j]
S[g,j] = A[g,j] - O[g,j] - F[g,j] >= 0
```

`E` é recebimento externo com pedido, semana de entrega e *lead time*;
`G` é geração interna documentada; `D` é consumo físico solicitado.
`O` representa descarte por extrapolação de capacidade, nunca consumo
fictício; `F` é quantidade efetivamente disponível para atender à demanda.
Toda grandeza é `Fraction` e a conversão usa `concilium.domain.units`.

A chegada ocorre antes do consumo e o excedente de armazenamento é descartado
**antes** de atender à demanda: é a mesma convenção semanal do atual
`replenishable.py`. Sem entregas reais, `D>S` gera **déficit explícito**,
não estoque negativo mascarado ou abastecimento implícito. O horizonte semanal
é ordenado e os pedidos externos do cenário devem estar dentro dele; entregas
de pedidos anteriores pertencem ao estoque inicial ou a uma futura modelagem
com ordens anteriores identificadas.

## Limites de autoridade

Esta camada fornece `StockProjection.feasible`, `total_shortage`,
`total_overflow`, linhas e evidências, **não** um certificado GO. A API
retorna `PHYSICAL_INVENTORY_PREVIEW_NOT_FINANCIAL_GO` e preserva indicação
de demanda planejada versus observada.

P19-B deverá calcular posse `C_inv` somente sobre uma base temporal
especificada e P19-C deverá integrar déficit/reabastecimento ADR184 e gates,
sem duplicar `C_cons` do P18-B. P20 precisará conciliar fontes contratuais,
consumo, mobilização, estoque e indiretos antes da precificação #21/#23.
