# NEP-014: Abas Excel sem distinção semântica + Curva ABC composição ausente

**Status:** Concluído  
**Prioridade:** 🟡 Médio  
**Área:** Projetos  
**Tipo:** Feature  
**Esforço:** L  
**Identificado em:** 2026-05-20  

---

## Contexto

A seção "📦 Saídas do Planejamento" lista toggles para ativar/desativar artefatos, mas não distingue quais são obrigatórios para entrega de engenharia e quais são analíticos/opcionais. Além disso, falta a **Curva ABC de composição** — a Curva ABC atual (`CURVA.ABC`) mostra atividades, mas não discrimina o custo de cada atividade pelos componentes (MO, EQ, MAT, DIESEL).

## Estrutura Proposta

### Fundamentais (sempre ativas, não desativáveis)
| Artefato | Descrição |
|---|---|
| `resultado.xlsx` | Planilha principal com abas: RESULTADO, BDI, FLUXO.CAIXA |
| `relatorio.md` | Relatório executivo em Markdown |

### Analíticas complementares (toggleáveis)
| Artefato | Descrição |
|---|---|
| `MEMORIAL.BDI` | Auditoria de cálculo BDI |
| `CURVA.ABC.ATIVIDADES` | Pareto por atividade (atual CURVA.ABC) |
| `CURVA.ABC.COMPOSICAO` | **NOVA** — Pareto por componente de custo discriminado |
| `S-CURVE` | Curva de desembolso acumulado |
| `CAMPANHA.FROTA` | Permanência de equipamentos |
| `CUBO.COMP` | Composição 4D do preço |
| `memorial_bdi.pdf` | Memorial em PDF para entrega |

### Curva ABC Composição (nova aba)

Para cada atividade na EAP, discriminar o custo por componente:

| Atividade | CPU | Qtd | Custo MO | Custo EQ | Custo MAT | Custo DIESEL | Total |
|---|---|---|---|---|---|---|---|
| Escavação 1ª | CPU-TERRA... | 15.000 m³ | R$ 45k | R$ 80k | — | R$ 12k | R$ 137k |
| Compactação | CPU-TERRA... | 12.000 m³ | R$ 30k | R$ 55k | — | R$ 8k | R$ 93k |
| **% do total** | | | **28%** | **48%** | **0%** | **12%** | **88%** |

Pareto por componente de custo: permite identificar se o projeto é dominado por MO, EQ ou combustível.

## Critério de Aceite

1. Na UI, dois grupos separados visualmente: "Fundamentais (sempre incluídos)" e "Complementares (opcionais)"
2. Toggles fundamentais são `disabled=True` (sempre marcados)
3. Nova toggle `aba_curva_abc_composicao` ativa/desativa a nova aba
4. Aba `CURVA.ABC.COMPOSICAO` gerada no Excel com discriminação por componente
5. Pareto dos componentes no pé da aba

## Notas Técnicas

- A nova aba requer `AtividadeCustoCompleto.custo_por_categoria` já disponível no canonical
- Implementação em `excel_adapter.py` seguindo padrão das abas existentes
- O toggle `aba_curva_abc_composicao` adicionado ao `DEFAULT_DELIVERABLES` em `project_files.py`
