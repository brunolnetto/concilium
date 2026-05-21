# PRIVATE_LOG discrepancy summary

## Benchmark reference totals

- Custo direto: 14,885,785.22
- Custo indireto: 6,882,876.35
- Custo total: 21,768,661.57
- Preco de venda: 25,944,479.43

## Mapping 1:1

- is_1to1: True
- EAP items: 8
- Cronograma activities: 8

## Team composition gaps

- Items with any gap: 2
- Items materialized only in Concilium: 1
- Items zero in both sides: 4

- eap-1_4: issues=custo_total | ref=1,467,101.25 | concilium=1,547,491.66
- eap-1_5: issues=funcoes, equipamentos, custo_total, funcoes_materializadas_apenas_no_concilium, equipamentos_materializados_apenas_no_concilium | ref=0.00 | concilium=5,527,407.75

## Planning gaps

- Items with sem BDI gap: 3
- Items with com BDI gap: 3

- eap-1_5: ref=0.00 | concilium=1,105,525.77 | delta=1,105,525.77
- eap-1_1: ref=922,504.75 | concilium=1,043,641.69 | delta=121,136.94
- eap-1_4: ref=489,053.31 | concilium=515,851.19 | delta=26,797.88
- eap-1_2: ref=0.00 | concilium=0.00 | delta=0.00
- eap-1_3: ref=0.00 | concilium=0.00 | delta=0.00

## Aggregate cost gaps

- Custo direto vs benchmark ref: -12,029,043.94 (-80.81)
- Custo indireto vs benchmark ref: 21,206.29 (0.31)
- Direct authority gap (equipes - catalogo): 6,348,105.51

## Skill warnings

- 05-equipes-e-alocacao: CPU 'CPU-TERRA-ATI-011' com producao_id='PROD-ATI-011' sem equipe local. Normalize o catálogo (materializar equipe na CPU).; CPU 'CPU-TERRA-ATI-014' com producao_id='PROD-ATI-014' sem equipe local. Normalize o catálogo (materializar equipe na CPU).; CPU 'CPU-TERRA-ATI-011' com producao_id='PROD-ATI-011' sem equipe local. Normalize o catálogo (materializar equipe na CPU).; Equipamento 'EQ-E0016': consumo_litros_hora não encontrado em nenhuma fonte; custo_combustivel_mensal=0; Equipamento 'EQ-ESTACAO-TOTAL': consumo_litros_hora não encontrado em nenhuma fonte; custo_combustivel_mensal=0; CPU 'CPU-TERRA-ATI-011' com producao_id='PROD-ATI-011' sem equipe local. Normalize o catálogo (materializar equipe na CPU).
- 07-custos-indiretos: Razão indireto/direto 76.2% fora da faixa [10.0%, 50.0%]
- 08-consolidacao-financeira: Margem consolidada -33.67% | status=VERMELHO
- 14-explorador-cenarios: Repair incompleto: margem projetada -27.29% em 2 passo(s).
