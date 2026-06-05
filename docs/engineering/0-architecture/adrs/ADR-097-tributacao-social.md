# ADR-097 — Modelagem de Tributação Social sobre Salário Base (Brasil, 2026)

**Status:** Aceito
**Data:** 2026-06-01
**Contexto:** MendesLobo Construtora — Concilium
**Dependências:** ADR-056 (constantes de domínio), ADR-009 (custos indiretos), ADR-023 (BDI)

---

## Contexto

### Problema

**P1 — Fator 2,777 parece errado, quando o "comum" para CLT é ~1,8:**

O `pu_calculator.py` usa `(1 + ENCARGOS_CLT) = (1 + 1.777) = 2.777` como multiplicador
total do custo de MO. O fator 1.777 (177,7%) provém da tabela SINTRACON-SP / rfi_catalog.xlsm
e cobre grupos A–F + Judicial para horistas de campo/obra. Não é erro: é o custo real
completo de um horista CLT em obras de construção pesada, que inclui DSR, provisões de
aviso prévio, multas rescisórias, substitutos por acidente/doença, vale-transporte e
vale-refeição — itens ausentes nas tabelas simplificadas (~80%) comumente citadas.

**P2 — Modelo de tributação não é auditável por item:**

`ENCARGOS_CLT = 1.777` é uma constante opaca derivada da planilha interna. Não expõe:
- Quais encargos compõem cada grupo (A–F + Judicial)
- Cálculo progressivo do INSS do trabalhador (tabela 2026: 7,5%–14%)
- Isenção efetiva de IRRF até R$ 5.000 (Lei 15.270/2025)
- Diferença por regime tributário da empresa (Simples I–V vs Lucro Presumido/Real)
- RAT/SAT variável por grau de risco e setor

**P3 — O "~80%" é correto como modelo estatutário, mas a base importa:**

A soma estatutária pura é **~73–74%** (arredonda para "~80%"):
- Grupo A (INSS+FGTS+RAT+SistS+SalEdu): 36,8%
- Provisões legais (férias+abono+13º+aviso+multa): 30,2%
- Reincidências (INSS+FGTS sobre férias/13º): 6,5%
- **Total: ~73,5%** → multiplicador 1,735

O SINTRACON-SP adiciona ~90% a mais (DSR, provisões de substituição, benefícios, transporte)
chegando a 177,7%. Ambas as SOMAS estão matematicamente corretas — a diferença é **quais
itens** incluir e **sobre qual base** aplicar.

**Bug crítico detectado:** os insumos `AGIS-FN-*` (ex: `42,70 R$/h` para operador de
escavadeira) são taxas horárias **all-in negociadas**, que já incorporam os encargos:
`42,70 / (1 + 0,80 implícito) ≈ 23,72 R$/h base pura`. Aplicar `(1+1,777)` sobre elas
é **dupla contagem** — o engine inflava o custo real em **2,777×**. Corrigido neste ADR.

---

## Decisão

### D1 — `ENCARGOS_CLT = 1.777` aplica-se sobre **salário-base puro** (mensal), não sobre taxas horárias all-in

O SINTRACON-SP 177,7% é correto para empregados cujos contratos especificam o **salário-base
puro** (ex: R$ 3.200/mês bruto), sobre o qual a empresa calcula INSS, FGTS, provisões, DSR,
benefícios e transporte separadamente.

**Insumos `AGIS-FN-*` são diferentes:** a taxa 42,70 R$/h já é all-in (negociada pela CCT).
Aplicar `(1+1.777) = 2.777` sobre ela é dupla contagem; o multiplicador correto é `1.0` (uso
direto). Ambos — `pu_calculator.py` e `skill-05` — foram corrigidos para verificar a nota
`"já inclui encargos"` antes de aplicar o multiplicador.

Fontes legais subjacentes aos grupos:
- **Grupo A (37,8%):** INSS patronal 20% (Lei 8.212/91 art. 22) + FGTS 8% (Lei 8.036/90) +
  RAT/SAT 3% + Sal.Educ 2,5% + Sistema S 4,3% (SEBRAE + SENAI + SESI + INCRA + SECONCI)
- **Grupo B horista (47,84%):** Férias 11,11% + abono férias 3,70% + 13º 8,33% + **DSR 18,70%**
  — horistas recebem por hora produtiva; DSR compensa domingos/feriados não trabalhados
- **Grupo C (40,53%):** aviso prévio 8,33% + multa FGTS rescisória 5% + indenização adicional
  5% + salário substituto acidente/doença 18,33% + repouso dias parados 3,87%
- **Grupo D (19,07%):** reincidência de B sobre C (encargos do Grupo A incidem sobre B e C)
- **Grupo E (10,22%):** plano saúde, seguro vida, EPI, cesta básica
- **Grupo F (19,24%):** vale-transporte + vale-refeição (obrigatório para campo)
- **Judicial (3,00%):** provisão para passivo trabalhista

### D2 — Manter `ENCARGOS_MENSALISTA = 1.060` (106,0%) para administrativos

Mensalistas (engenheiros, gestores, supervisores) não têm DSR (já embutido no salário
mensal fixo), têm Grupo B reduzido e Grupo F zero. Multiplica­dor = 2,060.

### D3 — Tabelas progressivas INSS/IRRF (2026) para simulação de salário líquido

Para o contexto de **simulação de custo total do trabalhador vs salário líquido**, adotar
as tabelas progressivas legisladas abaixo. Não substituem D1/D2 em estimativas de custo
de projeto — são complementares para relatórios de People & Finance.

**INSS empregado 2026 — Tabela Progressiva (Portaria MPS/MF nº 13/2026):**

| Faixa (R$) | Alíquota | Parcela a Deduzir |
|---|---|---|
| 0,00 – 1.621,00 | 7,5% | R$ 0,00 |
| 1.621,01 – 2.902,84 | 9,0% | R$ 24,32 |
| 2.902,85 – 4.354,27 | 12,0% | R$ 111,41 |
| 4.354,28 – 8.475,55 | 14,0% | R$ 198,26 |
| > 8.475,55 | — | Teto: R$ 988,09 |

**IRRF mensal 2026 — Tabela + isenção Lei 15.270/2025:**

| Base (R$) | Alíquota | Parcela a Deduzir |
|---|---|---|
| 0,00 – 2.428,80 | 0% | — |
| 2.428,81 – 2.826,65 | 7,5% | R$ 182,16 |
| 2.826,66 – 3.751,05 | 15,0% | R$ 394,16 |
| 3.751,06 – 4.664,68 | 22,5% | R$ 675,49 |
| > 4.664,68 | 27,5% | R$ 908,73 |

Isenção efetiva (Lei 15.270/2025): base ≤ R$ 5.000 → IRRF = R$ 0,00.
Desconto progressivo: 5.000,01–7.350,00 → `IRRF = IRRF_bruto − [978,62 − 0,133145 × base]`.

### D4 — Encargos patronais variam por regime tributário

| Encargo | Simples I–III–V | Simples IV | Lucro Pres./Real |
|---|---|---|---|
| INSS Patronal (20%) | No DAS | 20% | 20% |
| RAT/SAT | No DAS | 1–3% | 1–3% |
| Sistema S | No DAS | 4,5–5,8% | 4,5–5,8% |
| FGTS | 8% | 8% | 8% |

> MendesLobo: Lucro Presumido → INSS Patronal 20%, RAT grau 2 (2%), Sistema S Serviços 4,5%.
> Estes valores já estão embutidos no Grupo A do `ENCARGOS_CLT = 1.777`.

---

## Alternativas Rejeitadas

| ID | Alternativa | Motivo |
|---|---|---|
| R1 | Usar ~80% ("modelo simplificado") para todos | Subestima custo real de horistas de campo: omite DSR(18,7%), substitutos(18,33%), multas(5%), benefícios(19,24%). Projeto subprecificado. |
| R2 | Usar tabela progressiva INSS para custo de projeto | O custo de projeto usa salário médio de equipe; cálculo progressivo individual não é prático em estimativa. Progressivo fica para simulação individual (D3). |
| R3 | Fator único para horistas e mensalistas | Mensalistas (106%) têm custo real ≈ 38% menor que horistas (177,7%). Tratar igual distorce custo de equipes indiretas vs equipes de campo. |

---

## Consequências

### Positivas

| Efeito | Descrição |
|---|---|
| Clareza do fator 2,777 | Documentado que é correto para horistas SINTRACON: base × 2,777 = custo total real |
| Rastreabilidade legal | Cada % dos Grupos A–F+Judicial apontado para a norma correspondente |
| Distinção horista/mensalista | 177,7% vs 106,0% usados nos contextos corretos (campo vs gestão) |
| Tabelas progressivas 2026 | INSS e IRRF atualizados disponíveis para simulação People & Finance |

### Negativas / Riscos

| Risco | Mitigação |
|---|---|
| Atualização anual das tabelas | Portaria MPS/MF define tabelas INSS todo janeiro; IRRF atualizado pela RFB. Processo: atualizar `constants.py` + DEFAULT_ENCARGOS no início de cada ano fiscal. |
| FAP (Fator Acidentário) pode variar 0,5×–2,0× o RAT | RAT fixado em 3% (grau médio) no Grupo A. Para refinamento por CNAE específico, expor `rat_factor: float = 1.0` em `ParametrosCalculo`. |
| Convenção Coletiva pode adicionar percentuais | Negociação anual SINTRACON pode alterar Grupos B/F. Manter `rfi_catalog.xlsm` como fonte de verdade dos percentuais. |
| Regime Simples: Grupo A embutido no DAS | Para empresas no Simples I–III–V: INSS patronal, RAT e Sistema S não são calculados separadamente. Modelo de projeto assume Lucro Presumido (cenário MendesLobo). |

---

## Diferença com o TributacaoEngine Atual

Verificado contra `constants.py` + `pu_calculator.py` em jun/2026:

| Aspecto | Engine atual | ADR-097 | Status |
|---|---|---|---|
| `ENCARGOS_CLT` | 1.7770 (177,7%) | Correto para salários-base mensais puros | ✅ Alinhado |
| `ENCARGOS_MENSALISTA` | 1.0600 (106,0%) | Correto para mensalistas | ✅ Alinhado |
| `ENCARGOS_PJ` | 0.06 (6%) | ISS 2–5% + mínimos ≈ 6% | ✅ Conservador, ok |
| **Multiplicador `pu_calculator` (horários all-in)** | ~~`(1+1.777)=2.777`~~ → **`1.0` (direto)** | Taxa all-in: usar sem multiplicador adicional | ✅ **Corrigido** |
| **`skill.py:_calcular_custo_funcao`** | ~~`1+enc=2.777`~~ → **`1.0` via nota** | Verifica `"inclui encargos"` (substring sem acento) | ✅ **Corrigido** |
| **`_skill_helpers_a.py:_calcular_custo_funcao`** | ~~`1+enc=2.777`~~ → **`1.0` via nota** | Implementação duplicada — também corrigida | ✅ **Corrigido** |
| Multiplicador mensal (base puro) | `(1+1.777) = 2.777` | Correto — base × 2,777 = custo total | ✅ Alinhado |
| Grupo A: INSS+FGTS+RAT+SistS | `_ENC_A_TOTAL = 0.3780` (37,8%) | 37,8% — idêntico | ✅ Alinhado |
| `SALARIO_MINIMO_MENSAL` | ~~R$ 1.518,00 (2025)~~ → **R$ 1.621,00** | Vigência 2026 | ✅ **Corrigido** |
| INSS progressivo empregado | Não calculado individualmente | Tabela 7,5–14% (D3) | 🔴 Pendente (Fase 3) |
| IRRF | Não calculado | Tabela + isenção R$ 5.000 (D3) | 🔴 Pendente (Fase 3) |
| Regime tributário | Assume Lucro Presumido embutido no Grupo A | `TaxRegime` enum (D4) | 🔴 Pendente (Fase 4) |
| RAT variável por grau | Fixo 3% (grau 2) no Grupo A | `rat_grade` 1/2/3 + `fap_factor` | 🔴 Pendente (Fase 4) |

**Dívida técnica:** `_calcular_custo_funcao` existe em duplicata (`skill.py:107` e
`_skill_helpers_a.py:134`). Ambas corrigidas com o mesmo check `"inclui encargos"`.
Consolidar em refactor futuro para evitar drift.

**Bug corrigido:** `pu_calculator.py` + ambas as instâncias de `_calcular_custo_funcao`
detectam `"inclui encargos"` e usam a taxa sem multiplicador adicional → elimina dupla
contagem de 2,777× sobre taxas horárias all-in.

---

## Plano de Implementação

| Fase | Entregas | Status |
|---|---|---|
| 1 | Validação e documentação do `ENCARGOS_CLT = 1.777` (Grupos A–F+Judicial) | ✅ Feito (constants.py com tabela comentada) |
| 2 | `pu_calculator.py`: `(1 + alpha)` como multiplicador total correto | ✅ Feito (NEP-029 D2) |
| 3 | Tabelas progressivas INSS/IRRF 2026 (`constants.py` + `TabelaEncargos`) | 🔴 Pendente |
| 4 | `TaxRegime` enum e cálculo diferenciado por regime | 🔴 Pendente |
| 5 | Simulação People & Finance: `calculate_employer_clt`, `calculate_irrf` | 🔴 Pendente |

## Definition of Done

### Fases 1–2 (completas)
- [x] `ENCARGOS_CLT = 1.777` documentado com decomposição por Grupo
- [x] `pu_calculator.py` usa `(1 + alpha_clt) = 2.777` para multiplicador total
- [x] Teste unitário verifica `fe_nec → 1/η_p` com encargos incluídos

### Fase 3
- [ ] `INSS_BRACKETS_2026` e `IRRF_BRACKETS_2026` em `constants.py` ou módulo dedicado
- [ ] `SALARIO_MINIMO_MENSAL` atualizado para R$ 1.621,00 (2026)
- [ ] Teste: `calculate_inss_employee(3000.00)` ≈ R$ 248,61

### Fases 4–5
- [ ] `TaxRegime` enum implementado
- [ ] `calculate_employer_clt(salary)` retorna `TaxationResult` auditável
- [ ] Relatório People & Finance usa `ChargeItem` para rastreabilidade

---

## Referências

| Documento | Descrição |
|---|---|
| Lei 8.212/1991 art. 22 | INSS Patronal (20%) |
| Lei 8.036/1990 | FGTS (8%) |
| Portaria MPS/MF nº 13/2026 | Tabela INSS empregado 2026 |
| Lei 15.270/2025 | Isenção IRRF até R$ 5.000 |
| LC 123/2006 | Simples Nacional — DAS e isenções patronais |
| SINTRACON-SP / rfi_catalog.xlsm | Encargos Grupos A–F+Judicial horistas obra |
| CLT art. 7º CF/88 | Direitos trabalhistas (férias, 13º, FGTS) |

---

## Relacionados

[[adr-056-domain-constants]] [[adr-009-indirect-costs]] [[adr-023-bdi-diferenciado]] [[nep-037-encargos-bdi-tentativa-cancelada]]
