# NEP-009: CPUs de terraplenagem com composição de equipe não registrada no catálogo

**Status:** Concluído  
**Prioridade:** 🟠 Alto  
**Área:** Catálogo  
**Tipo:** Dados  
**Esforço:** XL  
**Identificado em:** 2026-05-20  

---

## Contexto

As CPUs de terraplenagem do catálogo mendeslobo têm apenas diesel nos `composicao_itens`, sem os dados de mão de obra (operadores) e equipamentos (escavadeiras, caminhões) que as tornam computáveis:

| CPU | Composição atual | Composição real necessária |
|---|---|---|
| CPU-TERRA-ESCO-CARGA-1CAT-DMT2000 | `[{DIESEL 0.12}]` | MO(operador) + EQ(escavadeira) + EQ(caminhão) + DIESEL |
| CPU-TERRA-COMPAC-FINAL-ROCHA | `[]` | MO(compactador) + EQ(rolo) |
| CPU-TERRA-COMPAC-PI | `[]` | MO(compactador) + EQ(rolo) |
| CPU-TERRA-COMPAC-PN | `[]` | MO(compactador) + EQ(rolo) |
| CPU-TERRA-CORPO-ATERRO-3CAT | `[]` | MO + EQ(empurrador) + DIESEL |

O campo `equipe.funcoes` e `equipe.equipamentos` — que é a estrutura que o sistema usa para calcular custos diretos — não está preenchido nesses JSONs.

## Causa Raiz

Os JSONs do catálogo foram criados com foco na referência de preços (SICRO/SINAPI) mas sem a estrutura de equipe. A composição completa existe nas planilhas de referência da MendesLobo mas não foi migrada para o formato do sistema.

## Critério de Aceite

1. Script `scripts/enrich_cpu_equipe.py` que:
   - Para cada CPU em TERRAPLENAGEM sem `equipe`, sugere composição padrão baseada em templates por tipo (ESCO-CARGA, COMPAC, CORPO-ATERRO)
   - Ou importa composição do canonical mais recente de projetos que usaram essas CPUs
   - Gera proposta em JSON para revisão humana antes de aplicar

2. Após enriquecimento: expander "Composição das CPUs" no Painel de Controle mostra rows de MO, EQ e DIESEL para CPUs de terraplenagem

3. A coluna "Composição" no catálogo master exibe `MO + EQ + DIESEL` para essas CPUs

## Templates Sugeridos por Tipo

| Padrão de código | Funcoes | Equipamentos |
|---|---|---|
| ESCO-CARGA-1CAT | Operador de escavadeira (1) | Escavadeira H 111-204 CV (1), Caminhão basculante 14 t (3) |
| ESCO-CARGA-2CAT | Operador (1) | Escavadeira H 111-204 CV (1), Caminhão (4) |
| ESCO-CARGA-3CAT | Operador (1) | Escavadeira grande >204 CV (1), Caminhão (5) |
| COMPAC-* | Operador rolo (1) | Rolo compactador (1) |
| CORPO-ATERRO | Operador trator (1) | Trator de esteiras (1) |

## Notas Técnicas

- A estrutura `equipe` esperada: `{"funcoes": [...], "equipamentos": [...]}` no JSON da CPU
- Alternativa: usar campo `composicao_completa` que é aceito como fallback pelo sistema
- Cada funcao: `{"funcao_id": str, "num_pessoas": int}`
- Cada equipamento: `{"equip_id": str, "num_unidades": int, "custo_mensal": float}`
- `funcao_id` e `equip_id` devem existir no catálogo de insumos para resolução de preços
