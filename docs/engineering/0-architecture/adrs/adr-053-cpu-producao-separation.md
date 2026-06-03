# ADR-053: Separação de CPU e Produtividade — Eliminação de Redundância

**Status**: Implementado  
**Data**: 2026-05-14  
**Author**: Engenheiro Sênior  
**Issue**: Redundância de composição (mão de obra, equipamentos, diesel, produções) entre CPU e Produtividade

## Contexto

CPUs no catálogo contêm atualmente:
1. **Composição de insumos**: EQUIPAMENTO, DIESEL, MAO_OBRA, MATERIAL (coeficientes)
2. **Produtividade**: `producao_horaria` (produção/hora)
3. **Equipe padrão**: `composicao_padrao_equipe` (funções, quantidade de pessoas, equipamentos)

Produtividades contêm igualmente:
1. **Produtividade**: `valor_horario` (duplica `producao_horaria` de CPU)
2. **Equipe padrão**: `composicao_padrao_equipe` (duplicada)
3. **Histórico**: observações de calibração contra obras reais

### Problema

- **Assincronia**: mudanças em produtividade não refletem automaticamente em CPUs que as referenciam
- **Incoerência**: duas fontes da verdade para a mesma dimensão (produção/hora, equipe)
- **Governança**: não é claro qual domínio (CPU vs Produtividade) é responsável pela manutenção

## Decisão

**Separação clara de responsabilidades:**

### CPU (dimensão de insumos)
Representa a composição de recursos necessários para executar um serviço, ancorada em **custos mensais**, regime semanal 6:1 e 8 horas diárias.

**Mantém:**
- `codigo`, `descricao`, `unidade`, `origem`, `categoria`
- `composicao_itens`: insumos (EQUIPAMENTO, DIESEL, MAO_OBRA, MATERIAL) com coeficientes unitários
- `_cu_planilha` (custo unitário da execução)
- `producao_id_ref`: **referência estrangeira** para Produtividade

**Remove:**
- `producao_horaria` → substituído por `producao_id_ref`
- `composicao_padrao_equipe` → movido para Produtividade

### Produtividade (dimensão de produção e equipes)
Representa a taxa de produção (m3/h, m2/h) e composição padrão de equipe.

**Mantém:**
- `id`, `codigo`, `descricao`, `valor_horario`
- `composicao_padrao_equipe`: funções, quantidade, equipamentos (única fonte)
- `condicoes_calibracao`, `qualidade`, `historico_observacoes`
- `cpu_ids` (opcional, inverso): lista de CPUs que referenciam esta produtividade

**Novo:**
- `aplicacoes`: lista de contextos/tipos de obra (ex.: terraplenagem, pavimentação)

## Benefícios

1. **Sem assincronia**: mudanças em produtividade refletem imediatamente em CPUs
2. **Governança clara**: CPU cuida de insumos, Produtividade cuida de produção
3. **Reutilização**: mesma produtividade pode referenciar múltiplas CPUs de contextos diferentes
4. **Auditoria**: histórico de produtividade fica centralizado e rastreável

## Retrocompatibilidade

**Fase 1 (implementação):**
- CPU mantém `producao_horaria` como fallback legado
- CPU adiciona `producao_id_ref` como nova propriedade
- Loaders preferem `producao_id_ref` quando disponível; fallback para `producao_horaria`
- Validadores aceitam ambas as formas

**Fase 2 (deprecação):**
- Tooling avisa ao usar `producao_horaria` em CPU
- Documentação orienta migração

**Fase 3 (remoção):**
- `producao_horaria` removido de CPU após 2-3 ciclos

## Implementação (Fase 1)

### Schema CPU (nova estrutura, exemplo)
```json
{
  "codigo": "ESCO-CARGA-1CAT-DMT2000",
  "descricao": "ESCAVAÇÃO, CARGA, TRANSPORTE, DESCARGA E ESPALHAMENTO...",
  "unidade": "M3",
  "origem": "PROPRIA",
  "categoria": "TERRAPLENAGEM",
  "composicao_itens": [
    {
      "insumo_id": "ESCAV-HID-38T",
      "coeficiente": 0.00428188,
      "categoria_custo": "EQUIPAMENTO"
    }
  ],
  "producao_id_ref": "ESCO-CARGA-1CAT-PROD-001",
  "producao_horaria": 233.54208,
  "_deprecated": "producao_horaria será removido em v1.0; use producao_id_ref"
}
```

### Schema Produtividade (ref de CPU)
```json
{
  "id": "ESCO-CARGA-1CAT-PROD-001",
  "codigo": "ESCO-CARGA-1CAT",
  "descricao": "Escavação, carga, transporte — 1ª categoria",
  "valor_horario": 233.54208,
  "unidade": "m3",
  "composicao_padrao_equipe": { ... },
  "condicoes_calibracao": { ... },
  "qualidade": { ... },
  "cpu_ids": ["ESCO-CARGA-1CAT-DMT2000", "ESCO-CARGA-1CAT-DMT3000"],
  "aplicacoes": ["terraplenagem"]
}
```

## Impacto

- **Loaders**: atualizar para carregar Produtividade via `producao_id_ref`
- **Validadores**: aceitar ambas as formas em Fase 1
- **UI/Dashboard**: mostrar referência cruzada CPU ↔ Produtividade
- **Benchmarks**: validar que AGIS e outros rodam corretamente com nova estrutura

## Estado de Implementação (Fase 1)

| Componente | Status | Localização |
|-----------|--------|-------------|
| `CPU.producao_id_ref` obrigatório com validator | ✅ | `domain/models/catalogo.py:279` |
| `CPU.composicao_padrao_equipe` **removido** do modelo Pydantic | ✅ (Fase 3) | `domain/models/catalogo.py` — campo excluído, `extra="ignore"` absorve legado |
| Skill 04: resolve produtividade via `producao_id_ref` → `valor_horario` | ✅ | `skills/04-cronograma/skill.py:_resolve_productivity` |
| Skill 05: resolve `composicao_padrao_equipe` via `producao_id_ref` primeiro | ✅ | `skills/05-equipes-e-alocacao/skill.py:260-268` |
| Arquivos produtividade com `valor_horario` + `composicao_padrao_equipe` | ✅ | `config/catalogos/mendeslobo/produtividades/*.json` |
| Scripts de migração | ✅ | `scripts/refactor_cpu_producao_adr053.py`, `heal_adr053_catalogs.py` |
| Validação VAL-PROD-04-PROD-LEGACY ao usar campo legado | ✅ | `skills/04-cronograma/skill.py` |
| Validação VAL-EQUIP-LEGADO-053 ao ler `composicao_padrao_equipe` do CPU | ✅ (Fase 3) | `skills/05-equipes-e-alocacao/skill.py` |
| Catálogo `mendeslobo/cpus/` limpo (134 CPUs) — sem campos legados | ✅ | `config/catalogos/mendeslobo/cpus/` |
| Catálogo `mendeslobo/produtividades/` com `composicao_padrao_equipe` | ✅ | `config/catalogos/mendeslobo/produtividades/` |

## Nota de Retrocompatibilidade

O modelo `CPU` usa `extra="ignore"` — CPUs em catálogos legados que ainda contenham `composicao_padrao_equipe` ou `producao_horaria` têm esses campos silenciosamente ignorados pelo Pydantic. A Skill 05 mantém um fallback deprecated (VAL-EQUIP-LEGADO-053) para ler `composicao_padrao_equipe` do dict raw quando o campo não estiver na Produtividade correspondente. Migrar com `scripts/refactor_cpu_producao_adr053.py`.
