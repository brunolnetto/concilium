# P17-B — Auditoria de titularidade de custos instanciais da Skill 05

A Skill 05 mantém, por compatibilidade, um `custo_instancia_total` que agrega
MO/EQ, MAT/COMB e eventos de mobilização. Isto **não** corresponde ao
diário autoritativo K/V/indireto do formalismo.

A auditoria executada após `_processar_instancias_recurso()` decompõe:

- `K = ativo_MO + ativo_EQ + idle_MO + idle_EQ`;
- `V_legacy = MAT + COMB` **sem volume físico comprovado**;
- `I_mob = MOB + DEMOB`, exclusivamente indireto.

Ela rejeita valores inválidos, duplicação de identificação instancial e
divergência de total por instância ou contrato. Emite
`VAL-P17-CONSUMO-LEGADO` como aviso impeditivo de certificação GO futura,
sem alterar o cálculo financeiro legado nesta fase. Essa separação é
`PREVIEW_ONLY_LEGACY_MONETARY_COMPONENTS`; **não** é um certificado,
não prova consumo por quantidade física e não estabelece paridade Skill 06.

Os custos financeiros reais deverão ser reconstruídos pelo diário
exclusivo P17-A, com volume físico P18-B, tarifas ativas/idle explícitas
P13, e reconciliação P17-C/P20. Não inferir compras a partir da
taxa média de `custo_inst_mat/comb`.
