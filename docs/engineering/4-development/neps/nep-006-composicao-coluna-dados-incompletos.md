# NEP-006: Coluna Composição no catálogo ignora equipe e mostra dados parciais

**Status:** Concluído  
**Prioridade:** 🟠 Alto  
**Área:** Catálogo  
**Tipo:** UX + Dados  
**Esforço:** M  
**Identificado em:** 2026-05-20  

---

## Contexto

A coluna "Composição" na tabela do catálogo master exibe apenas as categorias de `composicao_itens` (insumos diretos), ignorando a composição de **equipe** (`equipe.funcoes`, `equipe.equipamentos`) que muitas CPUs possuem.

**Exemplos:**
- CPU-TERRA-ESCO-CARGA-1CAT: `composicao_itens=[{DIESEL}]` mas deveria mostrar `MO + EQ + DIESEL`
- CPUs que têm mão de obra e equipamentos via `equipe` mas composicao_itens vazio → exibem "—"

A composição de equipe está em estrutura diferente:
```json
"equipe": {
  "funcoes": [{"funcao_id": "MO-OPERADOR", "num_pessoas": 2, ...}],
  "equipamentos": [{"equip_id": "EQ-ESCAVADEIRA", ...}]
}
```

## Impacto

O engenheiro não consegue distinguir visualmente na tabela:
- Uma CPU que genuinamente não tem composição registrada
- Uma CPU que tem equipe completa mas zero insumos diretos
- Uma CPU com composição mista (equipe + insumos)

## Critério de Aceite

Coluna "Composição" exibe badges combinados das fontes disponíveis:

| Situação | Badge exibido |
|---|---|
| Só equipe (funcoes + equipamentos) | `MO + EQ` |
| Equipe + diesel | `MO + EQ + DIESEL` |
| Só insumos materiais | `MAT` |
| Misto completo | `MO + EQ + MAT + DIESEL` |
| Genuinamente vazio | `(sem composição)` em cinza |

No detalhe da CPU (abaixo da tabela), separar em duas seções:
- **"⚙️ Composição de Equipe"** — funcoes e equipamentos com quantidades
- **"🧱 Insumos Diretos"** — composicao_itens com coeficientes

## Notas Técnicas

- `Runtime.load_catalogo()` via `CatalogResolver._enrich_cpus_with_producao()` já carrega o catálogo completo incluindo `equipe`
- A função `_comp_badge` em `catalogo_master_page.py` precisa ser atualizada para inspecionar `cpu.get("equipe")` além de `composicao_itens`
- `MO` presente se `cpu.get("equipe", {}).get("funcoes")` não-vazio
- `EQ` presente se `cpu.get("equipe", {}).get("equipamentos")` não-vazio
