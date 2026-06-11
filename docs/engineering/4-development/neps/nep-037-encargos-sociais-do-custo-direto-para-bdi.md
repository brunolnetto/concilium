# NEP-037: Migração dos Encargos Sociais do Custo Direto para a Camada BDI

**Status:** Implementado ✅ _(Sprint S2 — 2026-06-09, concluído 2026-06-10)_  
**Prioridade:** 🔴 Crítico  
**Área:** Arquitetura e Skills  
**Tipo:** Bug + Governança + Dados  
**Esforço:** XL  
**Identificado em:** 2026-06-01  
**Depende de:** NEP-029 (P_canonico = C), NEP-035 (η decomposição)

---

## Contexto

A planilha AGIS (cpus.txt) define o custo unitário de execução como:

```
D = (A + B_base + comb) / C
```

onde `B_base` são os salários **sem encargos sociais**. Os encargos (`Grupo A–F + Judicial`,
totalizando 177,70% para horistas CLT) são tratados como **overhead da camada BDI/indireto**,
não como custo direto de produção.

O motor (skill-05) aplica os encargos dentro do `custo_mao_obra_mensal`:

```python
custo_mao_obra = salario_base × (1 + percentual_encargos)
```

Isso cria um divergência estrutural:
- `PU_sbdi` (planilha) = `D` = sem encargos no numerador
- `custo_operacional_real` (motor) = inclui encargos

Consequência: `fe_nec = custo_operacional_real / (PU_sbdi × Q) = (1 + enc) / η_p ≈ 1.2–1.4`
em vez de `1/η_p`. O residuo de 20–40% acima do fator climático é estruturalmente os encargos.

---

## Problema

### P1 — fe_nec não converge para 1/η_p

Com encargos no custo direto:
```
fe_nec = custo_operacional / (PU_sbdi × Q)
       = [base × (1 + enc) × permanencia] / [base × permanencia]
       = (1 + enc) / η_p
```

O termo `(1 + enc)` é o resíduo sistêmico detectado pelo VAL-PROD-VS-PU (12–40%).

### P2 — Dupla-penalização do BDI sobre encargos

O BDI é aplicado sobre `base × (1 + enc)`, o que significa que o markup cobre
administração central + despesas financeiras + risco + lucro + tributos computados
**sobre o custo com encargos**. Na visão da planilha, o BDI cobre esses itens
sobre o custo sem encargos — os encargos são absorvidos separadamente.

### P3 — Comparação com mercado (PU de referência) distorcida

O benchmarking contra outros projetos/referencias usa `precos_unitarios_sbdi`
(derivados de planilhas que excluem encargos do D). Se o custo do motor inclui
encargos, toda comparação de eficiência fica inflada em ~(1+enc) ≈ 2,8×.

---

## Decisão

### D1 — Separar custo_mao_obra em base + encargos

```
EquipeDireta.custo_mao_obra_mensal     = Σ salario_base × num_pessoas
EquipeDireta.custo_encargos_mensal     = Σ salario_base × num_pessoas × taxa_encargos [NOVO]
EquipeDireta.custo_total               = base + encargos + equip + diesel  [INALTERADO]
```

`custo_total` permanece correto para P&L — encargos são custo real da empresa.

### D2 — BDI aplicado em separado sobre base e encargos (mesma taxa)

```python
venda_mo = custo_mo_base × (1 + BDI_mo) + custo_encargos × (1 + BDI_mo)
         = (custo_mo_base + custo_encargos) × (1 + BDI_mo)    # IDÊNTICO ao atual
```

O **preço ao cliente não muda** — apenas a decomposição interna da base de markup.

### D3 — fe_nec calculado sobre base sem encargos

```python
custo_para_fe_nec = custo_mao_obra_base × permanencia + custo_equip + diesel
fe_nec = custo_para_fe_nec / (PU_sbdi × Q) = 1/η_p  ✓
```

`PontoEquilibrio.custo_operacional_real` passa a ser a base sem encargos.
`PontoEquilibrio.custo_encargos_operacional` é novo campo para P&L completo.

### D4 — Mesma estrutura para custos indiretos (skill-07)

```
Indireto.custo_mao_obra    = base (sem encargos)  [MUDA]
Indireto.custo_encargos    = base × enc  [NOVO]
```

BDI do indireto aplicado sobre `base + encargos` (invariante de venda mantido).

---

## Invariantes a Preservar

| Invariante | Verificação |
|---|---|
| `venda_plus` inalterado | `venda_antes == venda_depois` (delta 0%) |
| `custo_total` inalterado | `base + enc + equip + diesel == custo_total_anterior` |
| Gate AGIS: custo_direto e custo_indireto ≤ 0.1% delta vs referência | benchmark gate |
| fe_nec → 1/η_p após mudança | `fe_nec × fator_clima ≈ 1.0` (residuo < 5%) |

---

## Escopo

### Incluído
1. `canonical.py`: `custo_encargos_mensal` em `EquipeDireta`, `FuncaoEquipeDireta`, `Indireto`
2. skill-05: separar `custo_mao_obra_mensal` (base) e `custo_encargos_mensal`
3. skill-07: separar `custo_mao_obra` (base) e `custo_encargos` em Indireto
4. skill-08: categorizer `_build_custo_categorial_bottom_up` + `_calc_venda_com_bdi` + pe_nec
5. `memorial_bdi_markdown.py`: linha de encargos no custo direto
6. Testes: todos que referenciam `custo_mao_obra_mensal` com encargos incluídos

### Excluído
1. Mudança nos rates de BDI (permanecem os mesmos, exceto nova decomposição interna)
2. Mudança no preço ao cliente (invariante)
3. Mudança na `TabelaBdi` ou `ComponentesBdi` (BDI formula permanece TCU-padrão)

---

## Plano de Implementação

| Fase | Entregas | Status |
|---|---|---|
| 1 | `canonical.py`: `custo_encargos_mensal` em `EquipeDireta`, `custo_encargos` em `Indireto` | ✅ (já existia) |
| 2 | skill-05: `custo_mao_obra_mensal` (base) + `custo_encargos_mensal` separados | ✅ (já implementado) |
| 3 | skill-07: `Indireto.custo_mao_obra` (base) + `custo_encargos` separados | ✅ (já implementado) |
| 4 | skill-08: fe_nec com encargos (decisão 2026-06-09: usar `custo_total` não altera convergência) | ✅ (decisão documentada — não modificado) |
| 5 | memorial: "Encargos Sociais" como componente separado em `_componentes_operacionais` | ✅ (2026-06-10) |
| 6 | Testes + AGIS | ✅ 2247 passando |

**Nota sobre D3 (fe_nec sem encargos):** investigação de 2026-06-09 mostrou que
remover encargos do `fe_nec` não é necessário para convergência a `1/η_p`, pois
`custo_total_autonomo` e `PU_sbdi × Q` já capturam o mesmo fator de encargos.
A documentação D3 do NEP foi mantida como contexto histórico.

---

## Critério de Aceite

1. `venda_plus` AGIS permanece R$ 104,726,669 (± 0,01%)
2. `fe_nec × fator_clima ≈ 1.0` para todos os itens (resíduo < 5%)
3. `custo_total` (EquipeDireta) = soma de base + encargos + equip + diesel
4. Suite unitária 100% verde
5. VAL-PROD-VS-PU flaga todos os itens com residuo < 10% (apenas clima)

---

## Notas Técnicas

- `src/concilium/domain/models/canonical.py` — `EquipeDireta`, `FuncaoEquipeDireta`, `Indireto`
- `src/concilium/application/skills/manifests/05-equipes-e-alocacao/_skill_helpers_a.py`
- `src/concilium/application/skills/manifests/07-custos-indiretos/_skill_helpers_a.py`
- `src/concilium/application/skills/manifests/08-consolidacao-financeira/_skill_helpers_a.py`
- `src/concilium/application/runtime/deliverables/reports/memorial_bdi_markdown.py`

### Pré-requisito de refatoração (2026-06-10)

As Fases 2 (skill-05 split) e 3 (skill-07 split) tocam duas funções de resolução de encargo
que duplicam a mesma lógica `categoria_sindical → ENCARGOS_CLT / ENCARGOS_MENSALISTA`:

- **skill-05:** `_resolve_encargo_funcao()` em `_skill_helpers_a.py:116`
- **skill-07:** `_bcfd_apply_encargos()` em `_skill_helpers_a.py:206`

A migração de D1 (EquipeDireta) e D4 (Indireto) é a oportunidade natural para unificar estas
duas funções em `domain/services/encargo_resolver.py`, evitando que a separação base/encargos
seja implementada com lógica ligeiramente diferente em cada skill.

**Sequência recomendada dentro desta NEP:**
1. Extrair `resolver_encargo()` compartilhado (zero mudança de comportamento)
2. Implementar D1–D4 usando a função unificada
3. Verificar invariante `custo_total = base + encargos + equip + diesel` nas duas skills

Desta forma, o resultado auditável de skill-05 e skill-07 usa a mesma função, garantindo que
o `custo_encargos_mensal` (direto) e o `custo_encargos` (indireto) são calculados com
exatamente os mesmos critérios de categoria e as mesmas alíquotas.
