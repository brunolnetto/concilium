# P20-C — exact category-specific BDI, once only

Issue: #20. Package PR: #152.

P20-C applies explicitly supplied BDI rates to the existing P20 ledger, once per exclusive category: MO, EQ, MAT, COMB, and IND. Every rate must be an exact nonnegative Fraction; missing, extra, floating-point, or negative rates fail closed. A zero rate is valid only when explicitly supplied.

For each category c: C_c is the sum of source ledger events; BDI_c = C_c × rate_c; P_c = C_c + BDI_c; P is the sum of P_c. No category is recursively marked up. MOB/DEMOB and inventory holding remain in IND as classified by the source ledger. Calculations remain exact fractions.

The independent reconciliation compares the existing Skill 04 realized projection with the P20 category calculation. A forged attribution trace, missing rate, unclassified event, or weekly discrepancy fails closed. The result remains preview-only and does not certify a proposal price or PROJECT_GO.

Focused tests have not been run on this exact head; GitHub Actions remains disabled by maintainer decision.