# P20-A — reconciliação de fontes financeiras exclusivas

Escopo: **Refs #20**, parte da epic #8. Consome o mesmo diário P17-A
(`ExclusiveCostLedger`) ampliado pela aquisição física P18-B e, quando
disponível, pelo custo de posse P19-B. Não existe uma nova origem monetária.

## Contrato executável

`reconcile_financial_sources(pool, consumption, holding=None)` exige:

1. O snapshot P17 contém apenas K ativo/idle e MOB/DEMOB indireto. O mesmo
   `event_id` mantém a linha integral (natureza, categoria, valor, semana,
   origem) imutável nos snapshots seguintes.
2. O delta P18 contém **exatamente** uma linha `CONSUMABLE/evidence_id` para
   cada evidência física precificada com quantidade positiva; o custo bate com
   `PhysicalPurchaseMeasure.exact_cost`. A classificação MAT/COMB vem do
   **contrato de origem P18**, persistido em `AcquisitionEvidenceLine.category`:
   nunca usar a categoria do lançamento auditado como sua própria prova.
   Evidência legada sem categoria explícita **não é certificável em P20**.
   Quantidade zero não é compra.
3. Se o snapshot P19 for fornecido, seu delta contém **exatamente** as linhas
   `STOCK_HOLDING/good_id/week` de valor positivo, categoria IND e base
   de inventário física auditada. Uma tarifa não fornecida não equivale
   a holding igual a zero: `holding_evidence_present=False`.
4. Eventos inexistentes, removidos, mudados de semana/categoria ou duplicados
   rejeitam a conciliação ainda que `C_total` aparente fechar.
5. Cada evento exige proveniência semanal explícita. A projeção derivada
   por semana separa `C_K`, `C_V`, `C_ind` com `Fraction` exato.

Identidades verificadas sobre o conjunto exclusivo:

```text
C_D   = C_K + C_V
C_ind = C_MOB + C_DEMOB + C_HOLDING   [para as fontes cobertas em P20-A]
C_tot = C_D + C_ind
sum(weekly C_x) = C_x, para x em {K, V, ind, tot}
```

O diário P17 ainda aceita outras naturezas indiretas, mas P20-A exige
exclusivamente eventos do pool na sua entrada e só acrescenta os deltas P18/P19
tipados. Demais indiretos (administração da obra, provisionamento etc.) e suas
fontes não estão nesta prova.

## Falsificadores

- Exemplo analítico independente: K ativo 10 + idle 4, MOB 3,
  MAT 2,50 e holding 6 → direto 16,50, indireto 9, total 25,50.
- Deslocar a semana de uma compra mantendo 25,50 **falha**.
- Trocar a compra MAT por MO **ou COMB** de mesmo valor **falha**.
- Omitir MOB, compra, holding, ou forjar uma compra adicional **falha**.
- P18-B e P19-B reais: K 4 + V 2 + holding 1,50 = 7,50.

## Limites de autoridade

`FINANCIAL_SOURCES_RECONCILED_PREVIEW_NOT_PROJECT_GO` **não é certificado GO**.
Este PR não integra ainda os cálculos autoritativos da Skill 06,
não aplica BDI, não precifica entrega externa/provisionamento nem substitui
o certificado material do #23. P17-C/P19-C/P20-B/C devem vincular fontes reais
de custos do pipeline e rejeitar ausência de evidência, antes do preço #21.
