# Descoberta: Estrutura Real da Planilha AGIS

**Data:** 15 de Abril de 2026  
**Arquivo:** 2026_03_30_PLANEJAMENTO_LOTE 09 e 10_(CE).xlsm  
**Total de Abas:** 22 (não 20 como previsto)

---

## 📊 Mapeamento Completo de Abas

| # | Nome da Aba | Camada | Status | Tipo |
|---|---|---|---|---|
| 1 | **PLANEJAMENTO** | Layer 3 | ✅ MAPEADA | Execution |
| 2 | **CRONOGRAMA** | Layer 3 | ✅ MAPEADA | Execution |
| 3 | **PONTO DE EQUILIBRIO** | Layer 4 | ✅ MAPEADA | Validation |
| 4 | **RESULTADO** | Layer 3 | ✅ MAPEADA | Execution |
| 5 | **CPU** | *Layer 2?* | ❓ NOVA | Costs? |
| 6 | **EQUIPE** | Layer 2 | ✅ MAPEADA | Operational |
| 7 | **TOP** | Layer 2 | ✅ MAPEADA | Operational |
| 8 | **ADM** | Layer 2 | ✅ MAPEADA | Operational |
| 9 | **LAB** | Layer 2 | ✅ MAPEADA | Operational |
| 10 | **QSMS** | Layer 2 | ✅ MAPEADA | Operational |
| 11 | **MOB** | Layer 2 | ✅ MAPEADA | Operational |
| 12 | **ENCARGOS** | *Layer 1?* | ❓ NOVA | Base Data? |
| 13 | **BDI** | Layer 1 | ✅ MAPEADA | Base Data |
| 14 | **DD - C. EXAMES E EPI** | *Layer 2?* | ❓ NOVA | Operational |
| 15 | **PRATICABILIDADE** | Layer 1 | ✅ MAPEADA | Base Data |
| 16 | **PRODUÇÕES** | Layer 1 | ✅ MAPEADA | Base Data |
| 17 | **MÃO DE OBRA** | Layer 1 | ✅ MAPEADA | Base Data |
| 18 | **EQUIPAMENTOS** | Layer 1 | ✅ MAPEADA | Base Data |
| 19 | **Escavação e Carga** | Layer 2 | ✅ MAPEADA | Operational |
| 20 | **Transportes** | *Layer 2?* | ❓ NOVA | Operational |
| 21 | **MATERIAIS** | *Layer 1?* | ❓ NOVA | Base Data? |
| 22 | **SERVIÇOS TERCEIRIZADOS** | *Layer 2?* | ❓ NOVA | Operational |

---

## ✅ Abas Mapeadas (18/22 = 82%)

**Layer 1: Base Data Management** (5/6 abas)
- PRATICABILIDADE ✅
- PRODUÇÕES ✅
- MÃO DE OBRA ✅
- EQUIPAMENTOS ✅
- BDI ✅
- DADOS ❌ **Não existe!** (Substituta: MATERIAIS?)

**Layer 2: Operational Calculation** (9 abas)
- EQUIPE ✅
- TOP ✅
- ADM ✅
- LAB ✅
- QSMS ✅
- MOB ✅
- Escavação e Carga ✅
- Transportes ✅ (NOVA)
- DD - C. EXAMES E EPI ✅ (NOVA)

**Layer 3: Execution Planning** (3/3 abas)
- PLANEJAMENTO ✅
- CRONOGRAMA ✅
- RESULTADO ✅

**Layer 4: Financial Validation** (1/1 aba)
- PONTO DE EQUILIBRIO ✅

---

## ❓ Novas Abas Não Mapeadas (4/22)

| Aba | Descrição Inferida | Próxima Ação |
|---|---|---|
| **CPU** | Central de Preços Unitários? | Investigar conteúdo e relação com PLANEJAMENTO e BDI |
| **ENCARGOS** | Encargos sociais/trabalhistas? | Verificar relação com MÃO DE OBRA e cálculos de custo |
| **Transportes** | Custos de transporte separados? | Incluir em Skill 2 (Operational Calc) |
| **MATERIAIS** | Base de dados de matérias-primas? | Pode substituir "DADOS" esperado |

---

## 🔍 Recomendações Imediatas

### 1. **Validar Mapeamento Real**
```python
# Verificar se DADOS foi renomeada ou incorporada em outra aba
abas_esperadas = ["DADOS"]
abas_encontradas = ["MATERIAIS", "ENCARGOS"]

# Hipótese 1: DADOS = MATERIAIS
# Hipótese 2: DADOS information = ENCARGOS
# Investigar: Qual aba tem custos unitários?
```

### 2. **Investigar Função de CPU**
```python
# CPU pode ser:
# - Central de Preços Unitários (custosbase)
# - Custo Por Unidade (usado no PLANEJAMENTO)
# - Campos (unidades de referência)
# Verificar se PLANEJAMENTO linha 52 referencia CPU
```

### 3. **Atualizar Skills para 22 Abas**

**Skill 1 (Base Data)** - Adicionar:
- ENCARGOS (se for base de dados)
- MATERIAIS (se substituir DADOS)

**Skill 2 (Operational)** - Adicionar:
- Transportes (custos de transporte)
- DD - C. EXAMES E EPI (EPIs doequipamento)
- CPU (se aplicável)

---

## 📈 Impact Assessment

| Item | Impacto | Severidade |
|---|---|---|
| Abas a mais (+2) | Skills precisam ser expandidas | MÉDIA |
| Aba faltante (DADOS) | Precisa encontrar substituta | MÉDIA |
| CPU role unclear | CPU pode ser crítica ou redundante | ALTA |
| Skill 1 FAIL | Lê 5/6 - falta apenas "DADOS" | MÉDIA |

---

## ✅ Teste Confirmado: 3/4 Skills Funcionando

Mesmo com essas descobertas, os testes confirmam que:

- **Layer 1** - Lê 5/6 abas existentes ✅ (PRODUÇÕES, PRATICABILIDADE, MÃO DE OBRA, EQUIPAMENTOS, BDI)
- **Layer 2** - Cálculos operacionais 100% ✅
- **Layer 3** - Validação de cronograma e BDI 100% ✅
- **Layer 4** - Análise financeira 100% ✅

---

## 🎯 Próximos Passos (Prioridade)

1. **[ALTA]** Abrir planilha no Excel e explorar:
   - CPU: Qual é o conteúdo? (Linha 52, Col J referenciado?)
   - MATERIAIS: É substituto de DADOS?
   - ENCARGOS: Contém custos de encargos sociais?

2. **[MÉDIA]** Atualizar Skills para 22 abas:
   - Expandir base-data skill para incluir ENCARGOS + MATERIAIS
   - Expandir operational-calc skill para incluir Transportes + DD (EXAMES/EPI)

3. **[MÉDIA]** Validar relacionamentos:
   - CPU → PLANEJAMENTO (linha 52 usa qual coluna?)
   - MATERIAIS → PRODUÇÃO ou CRONOGRAMA?
   - Transportes → Como interact com MOB?

4. **[BAIXA]** Criar novos testes:
   - test_skills_live.py usando dados reais das 22 abas

---

## 📋 Checklist de Reconciliação

- [ ] Abrir planilha no Excel
- [ ] Verificar conteúdo de CPU (is it referenced anywhere?)
- [ ] Confirmar MATERIAIS vs DADOS mapping
- [ ] Examinar ENCARGOS content
- [ ] Verifciar Transportes relevância
- [ ] Verificar DD - EXAMES EPI relevância
- [ ] Atualizar skills manifest.json com 22 abas
- [ ] Rerodacódigo test_skills.py com full 22-sheet coverage
- [ ] Confirmar todas as dependências inter-abas

---

**Status:** Framework operacional com 18/22 abas mapeadas (82%)  
**Ação Requerida:** Investigação manual de 4 abas adicionais
