# NEP-005: Categoria "DIVERSOS" é genérica demais para usabilidade

**Status:** Concluído  
**Prioridade:** 🟡 Médio  
**Área:** Catálogo  
**Tipo:** Dados + Governança  
**Esforço:** L  
**Identificado em:** 2026-05-20  

---

## Contexto

O catálogo mendeslobo tem 17 CPUs classificadas como "DIVERSOS" — a análise das descrições revela que são itens bem definidos que se enquadram em subcategorias específicas:

| CPU | Descrição | Categoria sugerida |
|---|---|---|
| CPU-DIVER-ATI-068 | Aceiro | TERRAPLANAGEM_ESPECIAL |
| CPU-DIVER-ATI-067 | Remoção de cerca | INFRAESTRUTURA_GERAL |
| CPU-DIVER-ATI-009 | Corte/destocamento | TERRAPLANAGEM_ESPECIAL |
| CPU-DIVER-ATI-070 | Implantação de eixo | INFRAESTRUTURA_GERAL |
| CPU-DIVER-ATI-069 | Instalação manta geotêxtil | INFRAESTRUTURA_GERAL |
| CPU-DIVER-ATI-063 | Piso intertravado | PAVIMENTACAO |

**Impacto da categoria genérica:**
- Filtros por categoria no catálogo são inúteis para esses itens
- Análise de custo por tipo de serviço fica distorcida
- Equipe não consegue encontrar CPUs relevantes por contexto

## Proposta de Novas Categorias

| Categoria | Descrição | CPUs estimadas |
|---|---|---|
| `TERRAPLANAGEM_ESPECIAL` | Serviços auxiliares de terraplanagem (aceiros, destocamento) | ~5 |
| `INFRAESTRUTURA_GERAL` | Cercas, geotêxtil, implantação de eixo | ~6 |
| Realocar para existentes | Piso → PAVIMENTACAO, etc. | ~3 |

## Critério de Aceite

1. Script `scripts/reclassificar_diversos.py` que:
   - Analisa cada CPU em DIVERSOS e sugere nova categoria via keyword matching
   - Gera relatório de propostas para aprovação humana
   - Executa a reclassificação em lote após aprovação

2. Nenhuma CPU com `categoria == "DIVERSOS"` restante (ou justificativa explícita para as exceções)

3. Filtro por categoria no catálogo master retorna resultados significativos para as novas categorias

## Notas Técnicas

- Reclassificação = editar campo `categoria` no arquivo JSON via `upsert_catalog_cpu` (ADR-067)
- Cada reclassificação gera entrada no `.catalog_audit.jsonl`
- As novas categorias devem ser adicionadas ao `CATEGORIAS_CUSTO` em `form_contracts.py` e validadas pelo schema de CPU
- Script pode usar keyword matching simples (destoc, aceiro → TERRAPLANAGEM_ESPECIAL; geotêxtil, cerca → INFRAESTRUTURA_GERAL)
