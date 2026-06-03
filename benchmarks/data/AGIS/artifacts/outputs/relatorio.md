# Relatorio Analitico -- AGIS - Ferrovia Nova Transnordestina (Supressao e Terraplanagem)

**Gerado em:** 2026-05-13 19:18:54  
**Framework:** concilium  

---

## Resumo do Projeto

| Campo | Valor |
|-------|-------|
| Projeto | AGIS - Ferrovia Nova Transnordestina (Supressao e Terraplanagem) |
| Tipo Obra | terraplenagem |
| Localizacao | Ceara, Brasil |
| Periodo | 2026-06-01 -> 2027-06-27 |
| Status | RASCUNHO |

---

## Resultado Financeiro

| Indicador | Valor |
|-----------|-------|
| Preco de venda (c/ BDI) | R$ 76,753,980.59 |
| Custo direto | R$ 46,771,429.82 |
| Custo indireto | R$ 19,504,530.03 |
| **Custo total** | **R$ 66,275,959.85** |
| **Resultado bruto** | **R$ 10,478,020.74** |
| Margem bruta | 13.65% |
| Status | **VERDE** |

---

## Planejamento por EAP

| Item | Descricao | Un. | Qtd | s/BDI (R$) | c/BDI (R$) | Criticidade |
|------|-----------|-----|----:|----------:|-----------:|:-----------:|
| eap-1_0 | Desmatamento e limpeza de area vegetada | m2 | 2,400,000 | 2,096,707.20 | 2,529,041.14 | B |
| eap-1_1 | Esc/carg/transp 1aCat DMT<=2000m | m3 | 107,463 | 822,985.02 | 935,297.84 | C |
| eap-1_2 | Esc/carg/transp 1aCat DMT<=3000m | m3 | 336,915 | 2,850,672.98 | 3,242,006.35 | C |
| eap-1_3 | Esc/carg/transp 2aCat DMT<=2000m | m3 | 105,311 | 1,063,003.74 | 1,207,022.27 | C |
| eap-1_4 | Esc/carg/transp 2aCat DMT<=3000m | m3 | 585,946 | 6,237,825.13 | 7,077,172.20 | C |
| eap-1_5 | Esc/carg/transp 3aCat DMT<=2000m | m3 | 304,634 | 4,530,378.01 | 5,107,452.52 | A |
| eap-1_6 | Esc/carg/transp 3aCat DMT<=3000m | m3 | 676,519 | 12,329,175.32 | 13,912,325.19 | A |
| eap-1_7 | Compactacao aterros 100% Proctor Normal | m3 | 1,135,635 | 10,370,271.78 | 11,620,268.05 | B |
| eap-1_8 | Compactacao aterros 100% Proctor Intermediario | m3 | 29,411 | 351,159.75 | 393,487.32 | C |
| eap-1_9 | Construcao corpo aterro material 3a categoria | m3 | 981,154 | 5,762,346.88 | 6,435,973.88 | B |
| eap-1_10 | Compactacao camada final aterro sobre rocha | m3 | 24,721 | 356,904.01 | 425,538.27 | C |

---

## Custos Indiretos

| Categoria | Descricao | Custo Total (R$) |
|-----------|-----------|----------------:|
| ADM | Administracao de obra | R$ 13,695,825.36 |
| TOP | Topografia | R$ 858,758.32 |
| LAB | Laboratorio de solos e materiais | R$ 139,568.24 |
| QSMS | Qualidade, Saude, Seguranca e Meio Ambiente | R$ 755,777.68 |
| MOB | Mobilizacao e desmobilizacao | R$ 4,054,600.43 |

---

## Ponto de Equilibrio: Estrutural vs Operacional

| Item | PE Estrutural (R$) | PE Operacional (R$) | Venda (R$) | Frentes Eq. | Criticidade |
|------|--------------------:|---------------------:|-----------:|:-----------:|:-----------:|
| eap-1_0 | R$ 2,838,678.40 | R$ 14,192,824.30 | R$ 2,529,041.14 | 5.00 | ERRO |
| eap-1_1 | R$ 1,056,080.98 | R$ 1,056,038.74 | R$ 935,297.84 | 1.00 | AVISO |
| eap-1_2 | R$ 1,056,080.98 | R$ 1,056,038.74 | R$ 3,242,006.35 | 1.00 | OK |
| eap-1_3 | R$ 2,082,662.79 | R$ 4,165,158.97 | R$ 1,207,022.27 | 2.00 | AVISO |
| eap-1_4 | R$ 2,082,662.79 | R$ 4,165,158.97 | R$ 7,077,172.20 | 2.00 | OK |
| eap-1_5 | R$ 4,047,324.44 | R$ 16,188,650.20 | R$ 5,107,452.52 | 4.00 | OK |
| eap-1_6 | R$ 4,047,324.44 | R$ 16,188,650.20 | R$ 13,912,325.19 | 4.00 | OK |
| eap-1_7 | R$ 4,204,093.70 | R$ 12,611,776.56 | R$ 11,620,268.05 | 3.00 | OK |
| eap-1_8 | R$ 251,536.26 | R$ 503,052.39 | R$ 393,487.32 | 2.00 | OK |
| eap-1_9 | R$ 2,145,389.70 | R$ 4,290,607.77 | R$ 6,435,973.88 | 2.00 | OK |
| eap-1_10 | R$ 122,439.44 | R$ 122,434.54 | R$ 425,538.27 | 1.00 | OK |

---

## Analise Composicional de Custo

| Item | Venda (R$) | Operacional (R$) | Gap (R$) | Gap % | Dominante | Acao Sugerida |
|------|-----------:|-----------------:|---------:|------:|-----------|---------------|
| eap-1_0 | R$ 2,529,041.14 | R$ 14,192,824.30 | R$ -11,663,783.16 | -461.19% | mao_obra | Aumentar preco de venda ou reduzir a base operacional |
| eap-1_1 | R$ 935,297.84 | R$ 1,056,038.74 | R$ -120,740.90 | -12.91% | mao_obra | Aumentar preco de venda ou reduzir a base operacional |
| eap-1_2 | R$ 3,242,006.35 | R$ 1,056,038.74 | R$ 2,185,967.61 | 67.43% | mao_obra | Enxugar equipe, remover integrantes menos relevantes ou aumentar produtividade |
| eap-1_3 | R$ 1,207,022.27 | R$ 4,165,158.97 | R$ -2,958,136.70 | -245.08% | mao_obra | Aumentar preco de venda ou reduzir a base operacional |
| eap-1_4 | R$ 7,077,172.20 | R$ 4,165,158.97 | R$ 2,912,013.23 | 41.15% | mao_obra | Enxugar equipe, remover integrantes menos relevantes ou aumentar produtividade |
| eap-1_5 | R$ 5,107,452.52 | R$ 16,188,650.20 | R$ -11,081,197.68 | -216.96% | mao_obra | Aumentar preco de venda ou reduzir a base operacional |
| eap-1_6 | R$ 13,912,325.19 | R$ 16,188,650.20 | R$ -2,276,325.01 | -16.36% | mao_obra | Aumentar preco de venda ou reduzir a base operacional |
| eap-1_7 | R$ 11,620,268.05 | R$ 12,611,776.56 | R$ -991,508.51 | -8.53% | mao_obra | Aumentar preco de venda ou reduzir a base operacional |
| eap-1_8 | R$ 393,487.32 | R$ 503,052.39 | R$ -109,565.07 | -27.84% | mao_obra | Aumentar preco de venda ou reduzir a base operacional |
| eap-1_9 | R$ 6,435,973.88 | R$ 4,290,607.77 | R$ 2,145,366.11 | 33.33% | mao_obra | Enxugar equipe, remover integrantes menos relevantes ou aumentar produtividade |
| eap-1_10 | R$ 425,538.27 | R$ 122,434.54 | R$ 303,103.73 | 71.23% | mao_obra | Enxugar equipe, remover integrantes menos relevantes ou aumentar produtividade |

---

## Insights Acionaveis

- **criticidade**: total=0, A+=0, A=0, B=0, C=0
- **sensibilidade**: status=VERDE, repair_steps=0, oportunidades=0, margem_entrada=0.00%
- **intervencao**: recomendacao=Oportunidade REDUCE_DURATION, eixos=2

---

