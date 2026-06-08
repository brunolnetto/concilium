# Recomendações de Melhorias - Estrutura referencia.json

## Otimizações Identificadas (Post-Achievement)

Após completar a migração para schema v2 minimalista e alcançar 12/12 benchmarks APROVADO, identificamos oportunidades para simplificar ainda mais a estrutura:

### 1. **meta.localizacao**: Melhorar especificação geográfica

**Status atual:**
```json
"localizacao": "Brasil"
```

**Recomendação:**
```json
"localizacao": {
  "tipo": "coordenadas|endereco",
  "valor": {
    "lat": -15.5, "lng": -48.5  // ou
    "endereco": "Brasília, DF, Brasil"
  }
}
```

**Benefício:** Permite georreferenciamento automático, relevante para resolução de clima e jurisdição.

---

### 2. **spec.eap.item.ordem**: Remover (redundante com predecessores)

**Status atual:**
```json
{
  "item_id": "1.1",
  "ordem": 1,
  "predecessores": []
}
```

**Recomendação:** Remover campo `ordem`. Pode ser computado a partir da DAG de predecessores.

**Benefício:** Menos dados para manter sincronizados, menos redundância.

---

### 3. **spec.eap.item.{descricao, unidade}**: Inferir do catálogo

**Status atual:**
```json
{
  "item_id": "1.1",
  "cpu_id": "CPU-TERRA-ESCO-CARGA-3CAT-DMT3000",
  "descricao": "REMOÇÃO DO SOLO VEGETAL...",
  "unidade": "m2"
}
```

**Recomendação:**
```json
{
  "item_id": "1.1",
  "cpu_id": "CPU-TERRA-ESCO-CARGA-3CAT-DMT3000",
  "quantitativo": 330133.0
  // descricao e unidade buscados de catalogo[cpu_id]
}
```

**Benefício:** Fonte única de verdade (catálogo), elimina duplicação, reduz tamanho do arquivo.

---

### 4. **spec.eap.item.producao_diaria**: Inferir do catálogo

**Status atual:**
```json
{
  "item_id": "1.1",
  "cpu_id": "CPU-TERRA-ESCO-CARGA-3CAT-DMT3000",
  "producao_diaria": 3883.92
}
```

**Recomendação:** Remover. Computado como:
```
producao_diaria = quantitativo / (cronograma[item_id].semanas_alocadas * 5_dias_por_semana)
```

**Benefício:** Derivado, não primitivo. Garante consistência entre EAP, cronograma e catálogo.

---

### 5. **spec.bdi.bdi_lucro_impostos**: Mover para spec.resultado ou inputs

**Status atual:**
```json
"spec": {
  "bdi": {
    "mao_obra": {...},
    "material": {...},
    "bdi_lucro_impostos": 0.15  // ← avulso aqui
  }
}
```

**Recomendação:**
```json
"spec": {
  "bdi": {
    "mao_obra": {...},
    "material": {...}
    // sem bdi_lucro_impostos aqui
  }
},
"resultado": {
  "bdi_lucro_impostos": 0.15  // ou aqui
}
```

**Benefício:** Clareza semântica. `bdi_lucro_impostos` é um parâmetro de cálculo, não um componente de BDI.

---

### 6. **spec.cenarios**: Investigar remoção

**Status atual:**
```json
"spec": {
  "cenarios": [...]  // Nunca usado na pipeline
}
```

**Recomendação:** 
- Se não está sendo usado, remover do schema v2
- Se há planos para cenários, documentar claramente e implementar skill de suporte
- Atualmente skills 14 (explorador-cenarios) parece gerar, não consumir

**Benefício:** Simplificação, clareza de escopo.

---

### 7. **resultado.bdi_lucro_impostos vs. inputs**: Desambiguar

**Questão:** Qual é a fonte de verdade para `bdi_lucro_impostos`?

**Cenários:**
- **Opção A:** Em `referencia.json` → override de projeto específico
- **Opção B:** Em `inputs` via skill-01 → padrão da jurisdição
- **Opção C:** Em catálogo contexto → padrão do contexto

**Recomendação:** 
```
Implementar precedência:
1. resultado.bdi_lucro_impostos (se presente, override do projeto)
2. inputs['06-consolidar'].bdi_lucro_impostos (se presente, override da execução)
3. contexto.bdi_lucro_impostos (padrão do contexto)
```

**Benefício:** Transparência sobre precedência de valores.

---

## Arquitetura Minimalista Proposta (v3)

```json
{
  "meta": {
    "projeto": "CTC",
    "data_inicio": "2026-01-15",
    "data_termino": "2027-03-30",
    "localizacao": {
      "tipo": "endereco",
      "valor": "São Paulo, SP, Brasil"
    },
    "regime_trabalho": {
      "horas_dia": 8,
      "dias_semana": 6
    }
  },
  "spec": {
    "eap": [
      {
        "item_id": "1.1",
        "cpu_id": "CPU-TERRA-ESCO-CARGA-3CAT-DMT3000",
        "quantitativo": 330133.0,
        "predecessores": []
      }
      // descricao, unidade, ordem, producao_diaria → inferidos
    ],
    "cronograma": [
      {
        "item_id": "1.1",
        "semanas": {
          "2026-W01": {"num_equipes": 1},
          "2026-W02": {"num_equipes": 1}
        }
      }
      // producao_diaria → inferido
    ],
    "bdi": {
      "mao_obra": {"ac": 0.04, "df": 0.08, ...},
      "material": {...},
      "servicos": {...},
      "diesel": {...},
      "indireto": {...}
      // sem bdi_lucro_impostos (parámetro, não componente)
    },
    "indiretos": [
      {"tipo": "ADM", "custo_fixo_mensal_total": 384000},
      {"tipo": "MOB", "custo_fixo_total": 2442000}
    ]
    // sem cenarios (não usado)
  },
  "resultado": {
    "benchmark_confronto_referencia": {
      "custo_direto": 46867333.35,
      "custo_indireto": 19584539.37,
      "custo_total": 66451872.72,
      "preco_venda": 76961261.88
    }
    // bdi_lucro_impostos aqui (se override de projeto)
  }
}
```

---

## Plano de Implementação

### Phase 1: Validação (próxima revisão)
- [ ] Implementar validador de schema v3 em paralelo
- [ ] Testar em 1-2 benchmarks como proof-of-concept
- [ ] Documentar impacto em spec_loader

### Phase 2: Migração Gradual
- [ ] Converter AGIS para schema v3
- [ ] Atualizar spec_loader para inferir campos removidos
- [ ] Validar que todos 12 benchmarks continuam APROVADO

### Phase 3: Limpeza
- [ ] Remover campos redundantes de todos os referencia.json
- [ ] Reduzir tamanho médio do arquivo
- [ ] Atualizar documentação

---

## Benefícios Esperados

| Aspecto | Ganho |
|---------|-------|
| **Tamanho arquivo** | ~30% redução (menos duplicação) |
| **Manutenibilidade** | Fonte única de verdade (catálogo + primitivos) |
| **Clareza semântica** | Distinção clara: dados vs. parâmetros vs. resultados |
| **Robustez** | Menos pontos de inconsistência |
| **Flexibilidade** | Fácil evoluir specs de CPU sem quebrar referências |

---

## Notas

- Este documento assume que a pivô minimalista (EAP + cronograma + BDI + indiretos) foi validada como suficiente
- Conversão de schema v2 → v3 pode ser não-destrutiva (manter v2, ler como v3)
- Requer testes de regressão completos antes de deprecação de v2
