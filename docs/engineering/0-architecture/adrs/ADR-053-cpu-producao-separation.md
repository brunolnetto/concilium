# ADR-053: Separação de CPU e Produtividade — Eliminação de Redundância

**Status**: Proposal  
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

## Próximas Etapas

1. Atualizar `cpus.json` em catálogos com `producao_id_ref`
2. Adicionar referência reversa `cpu_ids` em Produtividades
3. Atualizar loaders (`CatalogLoader`, etc.)
4. Validar contra benchmarks (AGIS, CTC, etc.)
5. Comunicar deprecação a stakeholders
