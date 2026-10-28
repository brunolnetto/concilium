# Matriz de 13 issues × pacotes × PRs — Ondas 1 a 3

**Referência:** epic #8, `formalism_execution_dag.json`. Gerado com o estado consultado em 2026-10-27. **Não é prova de merge, aceite ou certificado.** O foco de 13 issues inclui #22 (CLOSED) e 12 issues ainda OPEN (#14–#21, #23–#26, #25).

## Matriz de cobertura

| Issue | Onda | Issue | Predecessoras canônicas | PRs de pacote registrados no DAG | Registro PLAN_ONLY / PR de origem |
| --- | ---: | --- | --- | --- | --- |
| [#22](https://github.com/brunolnetto/concilium/issues/22) | 1 | CLOSED | #9, #10, #11, #12, #13 | `P22-A`: #29; `P22-B`: #95; `P22-C`: #96 | — |
| [#25](https://github.com/brunolnetto/concilium/issues/25) | 1 | OPEN | #22 | `P25-A`: #30; `P25-B`: #30; `P25-C`: #99+#100 | — |
| [#14](https://github.com/brunolnetto/concilium/issues/14) | 2 | OPEN | #12, #22 | `P14-A`: #50; `P14-B`: #52 | — |
| [#15](https://github.com/brunolnetto/concilium/issues/15) | 2 | OPEN | #14 | `P15-A`: #54; `P15-B`: #61; `P15-C`: #63+#64+#65+#66+#67 | — |
| [#16](https://github.com/brunolnetto/concilium/issues/16) | 2 | OPEN | #15, #13 | `P16-A`: #68; `P16-B`: #70+#71; `P16-C`: #72+#73 | — |
| [#17](https://github.com/brunolnetto/concilium/issues/17) | 2 | OPEN | #16, #18 | `P17-A`: #74; `P17-B`: #77; `P17-C`: — | `P17-C` [#108](https://github.com/brunolnetto/concilium/pull/108) |
| [#18](https://github.com/brunolnetto/concilium/issues/18) | 2 | OPEN | #13, #22 | `P18-A`: #76; `P18-B`: #79 | — |
| [#19](https://github.com/brunolnetto/concilium/issues/19) | 2 | OPEN | #18 | `P19-A`: #80; `P19-B`: #81; `P19-C`: — | `P19-C` [#109](https://github.com/brunolnetto/concilium/pull/109) |
| [#20](https://github.com/brunolnetto/concilium/issues/20) | 2 | OPEN | #17, #19 | `P20-A`: #84; `P20-B`: —; `P20-C`: — | `P20-B` [#110](https://github.com/brunolnetto/concilium/pull/110), `P20-C` [#111](https://github.com/brunolnetto/concilium/pull/111) |
| [#21](https://github.com/brunolnetto/concilium/issues/21) | 2 | OPEN | #20 | `P21-A`: —; `P21-B`: — | `P21-A` [#112](https://github.com/brunolnetto/concilium/pull/112), `P21-B` [#113](https://github.com/brunolnetto/concilium/pull/113) |
| [#23](https://github.com/brunolnetto/concilium/issues/23) | 3 | OPEN | #21, #22, #25, #14, #15, #16, #17, #18, #19, #20 | `P23-A`: #55; `P23-B`: —; `P23-C`: — | `P23-B` [#114](https://github.com/brunolnetto/concilium/pull/114), `P23-C` [#115](https://github.com/brunolnetto/concilium/pull/115) |
| [#24](https://github.com/brunolnetto/concilium/issues/24) | 3 | OPEN | #23 | `P24-A`: —; `P24-B`: — | `P24-A` [#116](https://github.com/brunolnetto/concilium/pull/116), `P24-B` [#117](https://github.com/brunolnetto/concilium/pull/117) |
| [#26](https://github.com/brunolnetto/concilium/issues/26) | 3 | OPEN | #24, #25 | `P26-A`: —; `P26-B`: — | `P26-A` [#118](https://github.com/brunolnetto/concilium/pull/118), `P26-B` [#119](https://github.com/brunolnetto/concilium/pull/119) |

O campo **“PRs registrados”** reproduz literalmente `packages[].prs` do manifesto; pode incluir vários PRs por pacote e **não** informa se foram integrados nem se a issue foi aceita. O campo “Registro PLAN_ONLY / PR de origem” identifica o contrato de planejamento e seu PR histórico; o PR pode ser aberto como draft ou aposentado fechado sem merge. O pacote continua fora de `packages[].prs` até uma implementação real.

## Arestas e fila de integração

1. **W1:** #22 aceita, #25 ainda OPEN, bloqueada por controles obrigatórios de branch protection e GitHub Actions. O gate da onda 1 deve estar concluído antes de permitir merges futuros de W2/W3.
2. **W2:** #14 → #15 → #16; #18 em paralelo após W1; #16 e #18 → #17; #18 → #19; #17 e #19 → #20; #20 → #21.
3. **W3:** #23 depende de #21 e demais requisitos físicos/econômicos; #23 → #24 → #26, com #25 também como antecessora de #26.
4. Os planos `P17-C` e `P19-C` são bifurcações, e `P20-B` exige **ambos**. Os branches linearmente empilhados modelam uma aresta cada; as arestas de junção e aceites de issues são verificações adicionais.

## Exceções já auditadas

- PR [#102](https://github.com/brunolnetto/concilium/pull/102): código P14-C em draft, **além** dos slots P14-A/B do DAG; deve ter revisão de governança antes de contá-lo.
- PR [#103](https://github.com/brunolnetto/concilium/pull/103): código P18-C1 em draft, **além** de P18-A/B; não substitui integralmente #18.
- PRs [#105](https://github.com/brunolnetto/concilium/pull/105) → [#106](https://github.com/brunolnetto/concilium/pull/106) têm relação técnica real de base/ancestralidade, mas não equivalem aos slots P20-B/C ou P21-A/B.
- O PR [#120](https://github.com/brunolnetto/concilium/pull/120) guarda este índice e o fluxo de aposentadoria em revisão; seu merge não satisfaz gate de onda.

**Não usar `Closes` em nenhum draft PLAN ONLY.** Converter em implementação exige alteração real de código, testes adversariais, oráculo independente, rebase/integração dos predecessores e CI do HEAD com branch protection.
