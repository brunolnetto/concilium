# Memorial de Calculo BDI

**Projeto:** AGIS - Ferrovia Nova Transnordestina (Supressao e Terraplanagem)
**Versao:** ?
**Gerado em:** 2026-06-05 10:47:30
**Vigencia encargos:** 2026-04-01
**Vigencia BDI:** 2026-04-01
**Regime tributario:** pre_reforma

---

## Encargos Sociais

| Grupo | Horista CLT | Mensalista CLT |
|-------|------------:|---------------:|
| GRUPO A | 37.80% | 37.80% |
| GRUPO B | 47.84% | 9.94% |
| GRUPO C | 40.53% | 40.30% |
| GRUPO D | 19.07% | 4.74% |
| GRUPO E | 10.22% | 10.22% |
| GRUPO F | 19.24% | 0.00% |
| JUDICIAL | 3.00% | 3.00% |
| **TOTAL** | **177.70%** | **106.00%** |

*Fonte: domain/constants.py + domain/models/bdi.py DEFAULT_ENCARGOS (rfi_catalog.xlsm)*

---

## BDI por Categoria

| Categoria | AC | DF | R | Lucro | Overhead | Tributos | BDI Total |
|-----------|---:|---:|---:|------:|---------:|---------:|----------:|
| mao_obra * | 5.00% | 1.50% | 1.00% | 9.00% | 16.50% | 9.73% | **29.98%** |
| material * | 0.00% | 0.00% | 0.00% | 4.00% | 4.00% | 0.00% | **4.00%** |
| servicos * | 5.00% | 1.50% | 1.00% | 9.00% | 16.50% | 9.73% | **29.98%** |
| indireto * | 5.00% | 1.50% | 1.00% | 5.00% | 12.50% | 9.73% | **25.21%** |
| diesel * | 0.00% | 0.00% | 0.00% | 4.00% | 4.00% | 0.00% | **4.00%** |

*Categorias marcadas com * tiveram override aplicado.*

---

## Decomposicao Percentual do Preco de Venda

| Categoria | Custo Direto | AC | DF | R | Lucro | ISS | CSSL | IR |
|-----------|-------------:|---:|---:|---:|------:|----:|-----:|---:|
| mao_obra | 77.48% | 3.87% | 1.16% | 0.77% | 6.97% | 5.00% | 1.99% | 2.74% |
| material | 96.15% | 0.00% | 0.00% | 0.00% | 3.85% | 0.00% | 0.00% | 0.00% |
| servicos | 77.48% | 3.87% | 1.16% | 0.77% | 6.97% | 5.00% | 1.99% | 2.74% |
| indireto | 80.24% | 4.01% | 1.20% | 0.80% | 4.01% | 5.00% | 1.99% | 2.74% |
| diesel | 96.15% | 0.00% | 0.00% | 0.00% | 3.85% | 0.00% | 0.00% | 0.00% |

---

## Aplicacao por Item

| Item | Descricao | Qtd | Un | PU s/BDI | BDI | PU c/BDI | Subtotal c/BDI |
|------|-----------|----:|----|----------:|----:|----------:|---------------:|
| eap-1_0 | Desmatamento e limpeza de area vegetada | 2,400,000 | m2 | R$ 0.8767 | 17.76% | R$ 1.0324 | R$ 2,477,673.16 |
| eap-1_1 | Esc/carg/transp 1aCat DMT<=2000m | 107,463 | m3 | R$ 7.6583 | 20.59% | R$ 9.2349 | R$ 992,406.46 |
| eap-1_2 | Esc/carg/transp 1aCat DMT<=3000m | 336,915 | m3 | R$ 8.4612 | 20.72% | R$ 10.2145 | R$ 3,441,418.84 |
| eap-1_3 | Esc/carg/transp 2aCat DMT<=2000m | 105,311 | m3 | R$ 10.0939 | 20.42% | R$ 12.1553 | R$ 1,280,091.96 |
| eap-1_4 | Esc/carg/transp 2aCat DMT<=3000m | 585,946 | m3 | R$ 10.7574 | 20.53% | R$ 12.9657 | R$ 7,597,204.52 |
| eap-1_5 | Esc/carg/transp 3aCat DMT<=2000m | 304,634 | m3 | R$ 14.8713 | 20.37% | R$ 17.9001 | R$ 5,452,981.76 |
| eap-1_6 | Esc/carg/transp 3aCat DMT<=3000m | 676,519 | m3 | R$ 18.2248 | 20.61% | R$ 21.9805 | R$ 14,870,246.89 |
| eap-1_7 | Compactacao aterros 100% Proctor Normal | 1,135,635 | m3 | R$ 9.1313 | 17.23% | R$ 10.7048 | R$ 12,156,798.29 |
| eap-1_8 | Compactacao aterros 100% Proctor Intermediario | 29,411 | m3 | R$ 11.9393 | 17.23% | R$ 13.9967 | R$ 411,657.26 |
| eap-1_9 | Construcao corpo aterro material 3a categoria | 981,154 | m3 | R$ 5.8730 | 17.00% | R$ 6.8713 | R$ 6,741,771.10 |
| eap-1_10 | Compactacao camada final aterro sobre rocha | 24,721 | m3 | R$ 14.4369 | 16.31% | R$ 16.7922 | R$ 415,123.69 |

---

## Resumo Financeiro

| Componente | Valor |
|------------|------:|
| Custo Direto Total | R$ 46,843,791.49 |
| Overhead Total | R$ 10,846,796.89 |
| Tributos Total | R$ 10,438,168.67 |
| Margem Total | R$ 9,884,461.68 |
| **Venda Total c/ BDI** | **R$ 78,013,218.73** |
| Margem % | 12.67% |
