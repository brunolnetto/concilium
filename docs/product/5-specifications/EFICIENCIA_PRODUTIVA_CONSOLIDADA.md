# Eficiência Produtiva no Modelo — Documentação Consolidada

**Propósito**: Explicar como a eficiência produtiva (ρ e β) é modelada e flui através do pipeline  
**Audiência**: Engenheiros, planejadores, analistas  
**Data**: 2026-08-14

---

## 1️⃣ DEFINIÇÕES FUNDAMENTAIS

### Eficiência Produtiva = ρ × β

A eficiência produtiva é decomposta em **dois fatores independentes**:

#### **ρ (Rho) — Produtividade Base Catalogada**

```
ρ = quantidade produzida por hora em condições ideais

Exemplo:
  Atividade: Escavação de 1 categoria
  ρ = 267.47 m³/h (23.87 m³/pessoa/dia = 267.47 m³/h ÷ 8h)
  
Significado:
  - Uma equipe completa produz 267.47 m³ em 1 hora
  - Com condições ideais (sem chuva, sol, temperatura adequada)
  - Sem paradas operacionais ou de manutenção
  
Origem: Artefato de Primeira Classe (versionado)
  → config/catalogos/mendeslobo/produtividades/CPU-TERRA-ATI-044-PROD-001.json
  → Campo: "producao_horaria": 267.47
  
Rastreamento:
  - Criado: Engenheiro calibra contra obra real (histórico)
  - Usado em: Skills 04, 05, 06 (cronograma, equipes, precificação)
  - Auditado: Axioma A3 test_producao_efetiva_formula()
```

---

#### **β (Beta) — Fator de Praticabilidade Climática**

```
β = redução de produtividade por clima, calendário e condições externas

Exemplo:
  Período: Dezembro-Janeiro (chuva intensa, Ouvidor-GO)
  β = 0.61 (61% da produtividade teórica)
  
Significado:
  - Semana chuvosa reduz ρ de 267.47 → 162.96 m³/h
  - Deve-se 30% de chuva + 9% de calendário (feriados)
  
Origem: Calculado em Skill 02 (calendários-e-clima)
  → config/calendarios/global.json + regional calendars
  → Fórmula: β = fator_chuva × fator_calendario
  
Rastreamento:
  - Entrada: Pluviometria histórica (INMET, Google Earth Engine)
  - Skill 02: Calcula β por semana
  - Skill 04: Aplica β no cronograma
  
Faixas de Valor:
  β ∈ [0.4, 1.0] para obras reais
  β = 1.0 → condições ideais (verão, sem chuva)
  β = 0.61 → período chuvoso (dez-jan, GO)
  β = 0.5484 → período crítico (jan-fev, chuvoso)
  β < 0.4 → inviável (não executa)
```

---

### Produtividade Efetiva = ρ × β

```
Fórmula:
  ρ_efetiva = ρ_catálogo × β_praticabilidade
  ρ_efetiva = 267.47 m³/h × 0.61 = 162.96 m³/h (Dec-Jan)

Interpretação:
  - Mesma equipe, mesma atividade
  - Com chuva: trabalha com 61% da velocidade
  - Resultado: 162.96 unidades/hora ao invés de 267.47

Garantia (Axioma A3):
  ρ_efetiva ∈ [0.4 × ρ_catálogo, 1.0 × ρ_catálogo]
  Nunca: ρ_efetiva < 0.4 × ρ_catálogo
  Nunca: ρ_efetiva > 1.0 × ρ_catálogo (impossível superar ideal)
```

---

## 2️⃣ FLUXO ATRAVÉS DO PIPELINE

### Skill 00 — Escopo
```
Input:
  - EAP items com quantitativos
  - Ex: SV-004 = 243.245,76 m³

Uso de Eficiência:
  ❌ Não usa (apenas decompõe quantidade)
  
Output:
  - Lista de atividades com qtd
```

---

### Skill 02 — Calendários e Clima
```
Input:
  - data_inicio: 2026-11-01 (Nov)
  - data_fim: 2027-01-31 (Jan)
  - jurisdicao: BR-GO (Ouvidor)
  - regime: 6×1 (segunda a sexta + sábado opcional)

Lógica:
  1. Busca calendar de Ouvidor-GO
  2. Calcula dias úteis por semana (5-6 dias)
  3. Busca fator_chuva por semana:
     - 2026-W45: fator_chuva = 0.90 (Nov, pouca chuva)
     - 2026-W50: fator_chuva = 0.61 (Dez, muito chuva)
     - 2027-W01: fator_chuva = 0.61 (Jan, muito chuva)
  4. Calcula fator_calendario (feriados, recessos)
  5. Computa: β = fator_chuva × fator_calendario
  
Output:
  planejamento[].distribuicao_semanal[semana]:
    - eta_p: 0.90 (Nov) ou 0.61 (Dec-Jan)
    - dias_uteis: 5-6
    - horas_disponiveis_dia: 8
    
Uso de Eficiência: PRODUZ β
  - β não é usado aqui, apenas calculado
  - Será usado em Skill 04
  
Arquivo: src/concilium/application/skills/manifests/02-calendarios-e-clima/_skill_helpers/_fator_clima.py
```

---

### Skill 04 — Cronograma e Equipes
```
Input:
  - Producao[].producao_horaria (ρ from catálogo)
  - β from Skill 02
  - Cronograma: num_equipes_por_semana por atividade
  
Lógica:
  Fórmula para quantidade semanal:
  
    qtd_semanal[i,j] = ρ_i × β_j × h_j × n_equipes[i,j]
    
  Onde:
    ρ_i = Producao.producao_horaria (ex: 267.47 m³/h)
    β_j = eta_p de Skill 02 (ex: 0.61 em Dec)
    h_j = horas disponíveis na semana j (ex: 48 horas = 6 dias × 8h)
    n_equipes[i,j] = número de equipes na atividade i, semana j
  
  Exemplo (SV-004, Semana 2026-W50 com chuva):
    ρ = 267.47 m³/h
    β = 0.61 (chuva intensa)
    h = 48 h (6 dias × 8h)
    n_equipes = 7 (cronograma says 7 equipes nessa semana)
    
    qtd_semanal = 267.47 × 0.61 × 48 × 7
               = 162.96 × 48 × 7
               = 54,696 m³/semana

  Validação (Axioma A7):
    ∑(qtd_semanal para SV-004) ≈ 243.245,76 m³ (EAP total)
    Tolerância: ±2%

Output:
  cronograma[].distribuicao_semanal[semana]:
    - qtd_semanal: 54,696 m³ (SV-004, W50)
    - producao_efetiva: 162.96 m³/h = 267.47 × 0.61
    - fator_clima_aplicado: true

Uso de Eficiência: CONSOME ρ e β
  - Calcula quantidade_semanal = ρ × β × (equipes × horas)
  - Garante que cronograma é viável com eficiência real
  
Arquivo: src/concilium/application/skills/manifests/04-cronograma/_skill_helpers/_spec.py:62-128
```

---

### Skill 05 — Composição de Equipes
```
Input:
  - cronograma[].distribuicao_semanal (qtd_semanal já com ρ×β aplicado)
  - Producao[].composicao_padrao_equipe (funcoes + equipamentos)
  
Lógica:
  1. Para cada atividade, semana, equipe:
  2. Resolve composição: 1 operador, 1 escavadeira, etc.
  3. Calcula custo_hora = ∑(salario + aluguel + combustível)
  
  Nota: A quantidade_semanal já incorpora eficiência (ρ×β)
        Não precisa recalcular β aqui
  
Output:
  equipes_diretas[].custo_hora:
    - Operador: R$ 8.730/mês = R$ 10.451,80 c/ encargos
    - Escavadeira: R$ 15.000/mês
    - Diesel: R$ 2.500/mês
    - Total C_h: R$ 27.951,80/hora

Uso de Eficiência: CONSOME β (indireto via qtd_semanal)
  - Não usa ρ ou β diretamente
  - Mas qtd_semanal já incorpora ρ×β do Skill 04
  - Custo_hora é aplicado a essa quantidade eficiente
  
Arquivo: src/concilium/application/skills/manifests/05-equipes/_skill_helpers/
```

---

### Skill 06 — Resultado Financeiro & Precificação
```
Input:
  - Producao.producao_horaria (ρ)
  - β (fator climático)
  - custo_hora de Skill 05
  - Quantitativo EAP
  
Lógica — Cálculo de PU via Bottom-Up:

  PASSO 1: Recuperar ρ e β
    ρ = Producao[CPU-TERRA-ATI-044].producao_horaria = 267.47 m³/h
    β = average(todas as semanas da atividade) = 0.65 (média)
  
  PASSO 2: Recuperar C_h (custo horário)
    C_h = Operador + Escavadeira + Combustível + Materiais
    C_h = 27.951,80 (calculado em Skill 05)
  
  PASSO 3: Derivar PU sem BDI (Axioma A4)
    PU_sem_bdi = C_h / (ρ × β)
    PU_sem_bdi = 27.951,80 / (267.47 × 0.65)
    PU_sem_bdi = 27.951,80 / 173.86
    PU_sem_bdi = R$ 160.80/m³
  
  Validação:
    - PU_sem_bdi > 0 ✓
    - PU_sem_bdi ∈ [1, 500] (sanidade) ✓
    - PU_sem_bdi reconhecível para obra ✓

  PASSO 4: Aplicar BDI por categoria
    PU_com_bdi = PU_sem_bdi × (1 + BDI_categoria)
    PU_com_bdi = 160.80 × 1.347 = R$ 216.53/m³
  
  PASSO 5: Calcular Venda (Metodologia B — recomendada)
    Venda = Custo_Total × (1 + Margem)
    Custo_Total = 243.245,76 m³ × R$ 160.80/m³ = R$ 39.103.189
    Margem_meta = 9% (meta VERDE)
    Venda = R$ 39.103.189 × 1.09 = R$ 42.622.476

Output:
  planejamento[]:
    - preco_unitario.total: R$ 160.80/m³ (sem BDI)
    - preco_unitario_com_bdi.total: R$ 216.53/m³
    - produtividade_catalogo: 267.47 m³/h
    - beta_praticabilidade: 0.65 (média aplicada)
  
  resultado:
    - venda: R$ 42.622.476
    - custo: R$ 39.103.189
    - margem: 9% (VERDE)

Uso de Eficiência: CONSOME ρ e β
  - Fórmula: PU = C_h / (ρ × β)
  - Se β = 1.0 (condições ideais): PU_ideal = 27.951,80 / 267.47 = R$ 104.54/m³
  - Se β = 0.61 (chuva): PU_realista = 27.951,80 / (267.47 × 0.61) = R$ 171.38/m³
  - Diferença de 64%: chuva aumenta custo unitário
  
Arquivo: 
  src/concilium/application/skills/manifests/06-resultado-financeiro/_precificacao/_skill_helpers/_preco_cpu.py
  Fórmula: PU = C_h / ρ_efetiva onde ρ_efetiva = ρ × β
```

---

## 3️⃣ IMPACTO DA EFICIÊNCIA NOS RESULTADOS

### Cenário: Mesmo Trabalho, Diferentes Eficiências

**Atividade**: SV-004 (Escavação, 243.245,76 m³)  
**Equipe**: 7 escavadeiras + operadores  
**Custo/Hora**: R$ 27.951,80  

#### Cenário A: Verão (β = 1.0, condições ideais)
```
Produtividade efetiva: 267.47 m³/h × 1.0 = 267.47 m³/h
Duração: 243.245,76 ÷ (267.47 × 48 × 7) = 9.04 semanas ≈ 9 semanas
Custo de MO: 267.47 h-trabalho/h × R$ 27.951,80 × n_horas
PU sem BDI: R$ 104.54/m³
PU com BDI: R$ 140.81/m³
Venda: 243.245,76 × R$ 140.81 = R$ 34.281.738
```

#### Cenário B: Inverno (β = 0.61, muito chuva)
```
Produtividade efetiva: 267.47 m³/h × 0.61 = 162.96 m³/h
Duração: 243.245,76 ÷ (162.96 × 48 × 7) = 14.83 semanas ≈ 15 semanas
Custo de MO: MESMO (não muda equipe, só reduz horas produtivas)
PU sem BDI: R$ 171.38/m³ (64% mais caro!)
PU com BDI: R$ 230.92/m³
Venda: 243.245,76 × R$ 230.92 = R$ 56.151.839
Diferença: +63.8% de preço (compensação pela ineficiência climática)
```

#### Comparação
```
Métrica                 Verão (β=1.0)      Inverno (β=0.61)    Δ
─────────────────────────────────────────────────────────────────
Semanas necessárias     9                  15                  +67%
PU unitário (s/BDI)     R$ 104,54          R$ 171,38           +64%
Preço de venda          R$ 34.281.738      R$ 56.151.839       +64%
Margem esperada         9% (VERDE)         9% (VERDE)          =
─────────────────────────────────────────────────────────────────

Conclusão:
  - Mesmo custo direto (MO, EQ, combustível)
  - Mesma margem % (9%)
  - MAS: inverno requer 64% mais preço porque menos eficiente
  - Cliente paga pela ineficiência climática
```

---

## 4️⃣ ONDE ESTÁ DOCUMENTADO

### Por Conceito

| Conceito | Localização | Tipo | Status |
|----------|-------------|------|--------|
| **ρ (produtividade)** | MAPEAMENTO_FORMULARIO_SKILLS.md §2.2 | Teórico | ✅ |
| **β (praticabilidade)** | AXIOMAS_INVARIANTES_CONFORMIDADE.md §A3 | Axioma | ✅ |
| **ρ × β (efetiva)** | FLUXO_DADOS_SKILLS.md §Rastreamento | Fluxo | ✅ |
| **Skill 02 (calcular β)** | PROCEDIMENTO_OPERACIONAL_VALIDACAO.md §C5 | Checklist | ✅ |
| **Skill 04 (aplicar ρ×β)** | PLANO_DEPRECACAO_FASE2.md §Phase 2B | Teste | ✅ |
| **Skill 06 (usar ρ×β em PU)** | TESTES_REGRESSAO_AUTOMATIZADOS.md §A3, A4 | Teste | ✅ |

### Por Arquivo

| Arquivo | Seções | Detalhamento |
|---------|--------|--------------|
| [AXIOMAS_INVARIANTES_CONFORMIDADE.md](AXIOMAS_INVARIANTES_CONFORMIDADE.md) | A3, A4, V1 | Axioma + test cases |
| [MAPEAMENTO_FORMULARIO_SKILLS.md](MAPEAMENTO_FORMULARIO_SKILLS.md) | §2.2, §2.3 | Variáveis + fórmulas |
| [FLUXO_DADOS_SKILLS.md](FLUXO_DADOS_SKILLS.md) | Rastreamento ρ, β | Entrada → skill → saída |
| [PROCEDIMENTO_OPERACIONAL_VALIDACAO.md](PROCEDIMENTO_OPERACIONAL_VALIDACAO.md) | C3-C5 | Validação de ρ e β |
| [TESTES_REGRESSAO_AUTOMATIZADOS.md](TESTES_REGRESSAO_AUTOMATIZADOS.md) | test_axiomas_producao | 49 test cases |

---

## 5️⃣ CHECKLIST: ENTENDER EFICIÊNCIA PRODUTIVA

- [x] ✅ ρ é produtividade em condições ideais (Producao.producao_horaria)
- [x] ✅ β é redução por clima/calendário (Skill 02 output)
- [x] ✅ ρ × β = quantidade realista produzida por hora
- [x] ✅ Skill 04 calcula qtd_semanal = ρ × β × horas × n_equipes
- [x] ✅ Skill 06 calcula PU = C_h / (ρ × β)
- [x] ✅ Axioma A3 valida: ρ_efetiva ∈ [0.4×ρ, 1.0×ρ]
- [x] ✅ Axioma A4 garante: PU sempre divide custo por eficiência real
- [x] ✅ Resultado: preço varia com clima (chuva = mais caro)

---

## 📋 PRÓXIMAS AÇÕES

Se você precisa:

1. **Entender conceito**: Ler Seção 1-2 acima
2. **Implementar Skill 04**: Veja `_spec.py:62-128` (qtd_semanal = ρ×β×h×n)
3. **Debugar PU**: Verificar Axioma A4 test em TESTES_REGRESSAO
4. **Auditar dados**: Rodar C3-C5 em PROCEDIMENTO_OPERACIONAL_VALIDACAO
5. **Escrever novo relatório**: Usar Cenário A/B (§3) como template

---

**Documento**: Consolidado em 2026-08-14  
**Status**: ✅ COMPLETO, pronto para referência  
**Próximo**: Link este documento em ADRs e NEPs de eficiência produtiva
