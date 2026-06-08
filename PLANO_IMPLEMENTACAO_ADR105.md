# Plano de Implementação ADR-105 — Mobilização e Desmobilização

**Status:** Em Execução  
**Data Início:** 2026-06-08  
**Fases:** 2-5 (Fase 1 Design ✅ completa)

---

## FASE 2: Skills Update (Skill-04, Skill-07)

### 2.1 Skill-04 (Cronograma)

**Objetivo:** Inferir automaticamente `mob_schedule` (mobilização, operação, desmobilização) a partir de:
- `meta.data_inicio` e `meta.data_termino`
- `spec.eap` com `predecessores` (para calcular data de primeira e última atividade)

**Mudanças Necessárias:**

1. **Nova função: `infer_mob_windows(meta, spec_eap)`**
   ```python
   def infer_mob_windows(meta: dict, spec_eap: list[dict]) -> dict:
       """Calcula janelas de mobilização baseado em datas de projeto e EAP.
       
       Returns:
           {
               "mobilizacao": {"inicio": date, "duracao_dias": int},
               "operacao": {"inicio": date, "duracao_dias": int},
               "desmobilizacao": {"inicio": date, "duracao_dias": int}
           }
       """
       project_start = parse_date(meta["data_inicio"])
       project_end = parse_date(meta["data_termino"])
       
       # Calcular datas de EAP via topological sort de predecessores
       dag = build_dag(spec_eap)
       first_eap_date = min_date(dag)  # Primeira atividade
       last_eap_date = max_date(dag)   # Última atividade
       
       # Janelas
       mob_start = project_start
       mob_end = first_eap_date - timedelta(days=7)  # 1 semana antes
       
       op_start = project_start
       op_end = last_eap_date + timedelta(days=7)    # 1 semana depois
       
       demob_start = last_eap_date
       demob_end = project_end
       
       return {
           "mobilizacao": {"inicio": mob_start, "fim": mob_end},
           "operacao": {"inicio": op_start, "fim": op_end},
           "desmobilizacao": {"inicio": demob_start, "fim": demob_end}
       }
   ```

2. **Integração com saída de skill-04:**
   - Adicionar campo `resultado.mob_schedule` ao output de Cronograma
   - Manter compatibilidade com `spec.cronograma` (distribuição semanal de EAP)

**Testes a Implementar:**
- [ ] Test_infer_mob_windows_basic: projeto 2025-01-15 a 2027-03-30, EAP com datas inferidas
- [ ] Test_infer_mob_windows_overlap: mobilização deve estar antes de operação
- [ ] Test_infer_mob_windows_all_phases: três fases presentes e sem gaps

---

### 2.2 Skill-07 (Custos Indiretos)

**Objetivo:** Distribuir custos de MOB (mobilização, operação, desmobilização) conforme janelas e drivers.

**Mudanças Necessárias:**

1. **Nova lógica: `calcular_custo_indireto_mob(indiretos, mob_schedule, duracao_meses)`**
   ```python
   def calcular_custo_indireto_mob(
       indiretos: list[dict],
       mob_schedule: dict,  # {"mobilizacao": {...}, "operacao": {...}, "desmobilizacao": {...}}
       duracao_meses: float
   ) -> dict:
       """Distribui custos de indiretos MOB segundo driver (projeto vs mensal).
       
       Returns:
           {
               "mob": {
                   "mobilizacao": {"custo_total": float, "semana": str},
                   "operacao": {"custo_mensal": float, "duracao_meses": float, "total": float},
                   "desmobilizacao": {"custo_total": float, "semana": str}
               },
               "resumo": {"custo_mob_total": float}
           }
       """
       resultado_mob = {}
       
       for indireto in indiretos:
           if indireto["tipo"] != "MOB":
               continue
           
           fase = indireto.get("fase")  # "mobilizacao", "operacao", "desmobilizacao"
           driver = indireto.get("driver")
           
           if driver == "projeto":
               # Custo incorre na primeira/última semana
               resultado_mob[fase] = {
                   "custo_total": indireto["custo_fixo_total"],
                   "semana": _iso_week_key(mob_schedule[fase]["inicio"])
               }
           elif driver == "mensal":
               # Custo distribuído ao longo da janela
               meses = (mob_schedule[fase]["fim"] - mob_schedule[fase]["inicio"]).days / 30.5
               total = indireto["custo_fixo_mensal"] * meses
               
               resultado_mob[fase] = {
                   "custo_mensal": indireto["custo_fixo_mensal"],
                   "duracao_meses": meses,
                   "total": total
               }
       
       return {"mob": resultado_mob, "resumo": {"custo_mob_total": sum_all_mob(resultado_mob)}}
   ```

2. **Integração com cálculo total de indiretos:**
   - ADM, TOP, LAB, QSMS: manter lógica existente (mensal)
   - MOB: usar nova lógica acima
   - Total indireto = ADM + TOP + LAB + QSMS + MOB

**Testes a Implementar:**
- [ ] Test_calcular_mob_projeto: mobilização com driver="projeto" incorre na semana 1
- [ ] Test_calcular_mob_mensal: operação com driver="mensal" distribuída por meses
- [ ] Test_calcular_mob_total: soma correta de todas fases
- [ ] Test_calcular_mob_com_adm: MOB + ADM juntos calculam corretamente

---

## FASE 3: Migração de Benchmarks (12 benchmarks)

### 3.1 Preparação de Dados

Para cada benchmark, extrair:
1. **De planejamento (ou referencia.json):**
   - `meta.data_inicio` e `meta.data_termino`
   - `spec.eap` com quantitativos

2. **De spec.indiretos atual:**
   - Valores de ADM, TOP, LAB, QSMS (manter como-está)
   - Valores de MOB (separar em mobilizacao/operacao/desmobilizacao)

3. **Popul

ar novo formato:**
   ```json
   "indiretos": [
     {
       "categoria": "ADM",
       "driver": "mensal",
       "custo_fixo_mensal": <valor>,
       "mao_obra": []
     },
     {
       "categoria": "MOB",
       "fase": "mobilizacao",
       "driver": "projeto",
       "custo_fixo_total": <valor>,
       "mao_obra": []
     },
     ...
   ]
   ```

### 3.2 Script de Migração

```bash
python scripts/migrate_adr105.py
```

**O que faz:**
1. Lê todos 12 benchmarks de benchmarks/data/*/referencia.json
2. Para cada um:
   - Calcula mob_windows via `infer_mob_windows()`
   - Separa MOB atual em 3 fases
   - Atualiza `spec.indiretos` com novo formato
   - Remove `spec.rcpsp_spec` (se existir)
3. Escreve benchmarks atualizados
4. Commit com git

**Benchmarks a Migrar:**
- AGIS ✓ (já tem spec.indiretos, só reformatar)
- ODFJELL ✓ (dados de INDML5-8)
- MATEC_GUARULHOS ✓ (dados de 3.5, 3.6)
- CTC, LUNDIN, MARA_ROSA, MATEC_HINES, MATEC_UBERLANDIA, PRIVATE_LOG, ROSH, RUMO, VALE (dados genéricos, desagregar)

---

## FASE 4: Validação

### 4.1 Testes de Pipeline

```bash
python scripts/run_benchmarks.py
```

**Critérios de Sucesso:**
- [ ] 12/12 APROVADO (sem BLOQUEADO ou ERRO)
- [ ] Skill-04 output contém `mob_schedule`
- [ ] Skill-07 output contém `custos.indiretos.mob`
- [ ] Skill-08 integra MOB em `resultado.breakdown.indireto.mob`

### 4.2 Testes de Acurácia

Para cada benchmark, validar:
- [ ] Custo MOB total ≈ 95-105% do esperado
- [ ] Distribuição MOB (mobilizacao + operacao + desmobilizacao) faz sentido
- [ ] MOB operacao distribuída uniformemente ao longo dos meses

### 4.3 Testes de Compatibilidade

- [ ] ADR-071 (pool-based costing) ainda funciona se rcpsp_spec mantido
- [ ] ADR-085 (custo instancial) janelas alinhadas com MOB phases
- [ ] ADR-090 (BDI) aplicado corretamente sobre MOB + diretos

---

## FASE 5: Production

### 5.1 Code Cleanup

- [ ] Marcar `spec.rcpsp_spec` como `@deprecated` em código
- [ ] Adicionar warning em skill-02 se rcpsp_spec fornecido
- [ ] Atualizar docstrings para referenciar ADR-105

### 5.2 Documentation

- [ ] Atualizar docs/engineering/skills/04-cronograma.md
- [ ] Atualizar docs/engineering/skills/07-custos-indiretos.md
- [ ] Criar migration guide: v2 (rcpsp_spec) → v3 (MOB phases)

### 5.3 Release & Deprecation

- [ ] Tag: v3.0-adr105
- [ ] Release notes com migration path
- [ ] Deprecation timeline: v2 schema suportado até [data TBD]

---

## Timeline & Responsabilidades

| Fase | Descrição | Duração | Status |
|------|-----------|---------|--------|
| 2 | Skill-04, Skill-07 updates | 2 sprints | ⏳ TODO |
| 3 | Migrar 12 benchmarks | 1 sprint | ⏳ TODO |
| 4 | Validação pipeline | 1 sprint | ⏳ TODO |
| 5 | Production release | 1 sprint | ⏳ TODO |

**Total:** ~5 sprints (~25 semanas se 5h/week)

---

## Próximos Passos Imediatos

1. ✅ **Fase 1 (Design)**: ADR-105 documento pronto
2. ⏳ **Fase 2 (Skills)**: 
   - [ ] Implementar `infer_mob_windows()` em skill-04
   - [ ] Implementar `calcular_custo_indireto_mob()` em skill-07
   - [ ] Escrever testes unitários
3. ⏳ **Fase 3 (Migração)**:
   - [ ] Criar script `scripts/migrate_adr105.py`
   - [ ] Executar migração dos 12 benchmarks
4. ⏳ **Fase 4-5**: Validação e production

---
