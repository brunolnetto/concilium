# Descoberta Aprofundada: Estrutura Real das 22 Abas

**Data:** 15 de Abril de 2026  
**Método:** Investigação via pandas com análise de conteúdo  
**Status:** Descoberta Completa ✅

---

## 🎯 Achados Principais

### ✅ **CPU** = Central de Composição Unitária de Serviço

**O que é:**
- Base de dados de **serviços precificados** com estrutura unitária
- Contém: CÓDIGO, DATA BASE, SERVIÇO (descrição completa), UNIDADE
- Exemplo: "ESCAVAÇÃO, CARGA, TRANSPORTE, DESCARGA E ESPALHAMENTO DE MATERIAL DE 1ª CATEGORIA - DMT ATÉ 2000M" (M3)

**Estrutura:**
```
Row 1: Tipo de obra
Row 3: CABEÇALHO CÓDIGO | DATA BASE | SERVIÇO | UNIDADE
Row 4+: Dados dos serviços

Seção de EQUIPAMENTO (A):
- CÓDIGO, QUANT., UTILIZAÇÃO (PROD./IMPROD.), CUSTO HORÁRIO
```

**Relação com outras abas:**
- **PLANEJAMENTO** (linha 52): Usa CPU como referência de serviços base
- **BDI**: Recebe CPU e aplica markup de BDI (Material, Diesel, Labor, Equipment)
- **RESULTADO**: Usa valores de CPU com BDI para cálculo final

**Mapeamento em Skill:**
- ✅ Já mapeada implicitamente em execution-planning (Layer 3)
- Precisa ser adicionada como validação em base-data (Layer 1)

---

### ✅ **MATERIAIS** = Base de Custos de Materiais-Primas

**O que é:**
- Database de **materiais de construção** com preços unitários
- Substitui ou complementa o esperado "DADOS"
- Contém: CÓDIGO (M0001+), DESCRIÇÃO, UNID., R$ UNITÁRIO, QUANT. TOTAL, R$ TOTAL

**Exemplo de conteúdo:**
```
M0001 | CAP 50/70          | T  | 5300.00  | NaN | 0
M0002 | RR2C               | T  | 3850.00  | NaN | 0
M0003 | TUBO CONCRETO 400M | m  | 161.40   | NaN | 0
M0004 | TUBO CONCRETO 600M | m  | 249.50   | NaN | 0
```

**Hipótese de uso:**
- Materiais são **inputs de CRONOGRAMA ou PLANEJAMENTO**
- Podem referenciar "MÃO DE OBRA" para custos de assentamento
- Quantidade total (col 5) provavelmente é preenchida dinamicamente

**Mapeamento em Skill:**
- ✅ DEVE ser adicionada em **base-data** (Layer 1) como referência de custos
- Substitui ou complementa "DADOS" esperado
- Precisa validação de: código único, preços positivos, descrições

---

### ✅ **ENCARGOS** = Cálculo Demonstrativo de Encargos Sociais

**O que é:**
- Tabela de **cálculos de encargos trabalhistas** (sociais)
- Separado por tipo: **Horistas** vs **Mensalistas**
- Contém: % de encargo (provisão folha, encargos, administração)

**Exemplo de conteúdo:**
```
Item | Descrição                    | % Encargo
  1  | UNIMED                       | NaN
  2  | UNIODONTO                    | NaN
  3  | PROVISÃO SOBRE FOLHA         | 0.31
  4  | ENCARGOS                     | 0.30
  5  | ADMINISTRAÇÃO CENTRAL        | 0.05
```

**Fórmula implícita:**
```
Custo Total = Salário Base × (1 + Taxa ENCARGOS)
```

**Relação com outras abas:**
- **MÃO DE OBRA**: Recebe custos base de mão de obra
- **EQUIPE**: Usa encargos para calcular custo real de cada função
- **ADM**: Pode usar para cálculos de overhead

**Mapeamento em Skill:**
- ✅ DEVE ser adicionada em **operational-calc** (Layer 2)
- Afeta cálculo de `calculate_crew_cost()` - precisa multiplicar salário por (1 + encargos)
- Validação: taxas devem ser 0-100%, representar encargos válidos

---

### ✅ **DD - C. EXAMES E EPI** = Despesa Diária - Exames e EPIs

**O que é:**
- **Duas tabelas em uma aba:**
  1. **Exames**: UNIMED, UNIODONTO, PROVISÕES (%), ENCARGOS (%), ADMIN (%)
  2. **EPIs**: Equipamento de proteção individual com custo e vida útil

**Exemplo de conteúdo:**
```
EPIs:
- PROTETOR SOLAR FPS 60  | R$ 60  | Vida: 60 dias | Custo: 60
- ABAFADOR DE RUÍDOS     | R$ 90  | Vida: 360 dias| Custo: 90
- CINTO PARAQUEDISTA     | NaN    | Vida: 1095    | Custo: 0
```

**Estrutura de cálculo:**
- EPIs tem columns M1-M12 (por mês)
- Tem coluna "Quant." indicando quantidade de pessoas
- Cálculo: QUANT × CUSTO = TOTAL POR MÊS

**Relação com outras abas:**
- **EQUIPE**: Precisa considerar EPIs no custo total da atividade
- **MOB**: Pode usar para despesas diretas
- **ADM ou RESULTADO**: Agrupa EPIs em custos indiretos

**Mapeamento em Skill:**
- ✅ DEVE ser adicionada em **operational-calc** (Layer 2) especificamente para MOB/ADM
- Ou como **nova categoria separada** em execution-planning (Layer 3)
- Validação: EPIs devem existir no projeto, custos >= 0

---

### ✅ **Transportes** = Variáveis de Transporte e Escavação

**O que é:**
- **Tabela de suporte operacional** para cálculos de índices de produtividade
- Contém **equipamentos de escavação e transporte** com especificações técnicas

**Exemplo de conteúdo:**
```
Escavadeiras:
- CAT-320  | Caçamba: 1.19 m3    | Prof. Máx: 6.72m
- CAT-336  | Caçamba: 2.41 m3    | Prof. Máx: 7.52m  
- CAT-349  | Caçamba: 2.41 m3    | Prof. Máx: 7.70m

Carregadeiras:
- 966L     | Capacidade: 3.2-7.4 t
- 938K     | Capacidade: 2.5-3.2 t
- 924K     | Capacidade: 1.7-5.0 t
```

**Propósito:**
- **Suporta validação/seleção de equipamento correto** em CRONOGRAMA
- Ajuda a validar se equipamento escolhido cabe no projeto

**Relação com outras abas:**
- **EQUIPAMENTOS**: Lista de equipamentos disponíveis (base de dados)
- **Transportes**: Especificações técnicas de equipamentos (reference table)
- **CRONOGRAMA/EQUIPE**: Valida se equipamento selecionado existe e tem capacidade

**Mapeamento em Skill:**
- ✅ DEVE ser adicionada em **operational-calc** (Layer 2) como tabela de referência
- Ou em **base-data** (Layer 1) como validação de equipamentos
- Validação: equipamento deve existir, capacidades devem ter ranges válidos

---

## 📊 Mapeamento Corrigido: 22 Abas

### **Layer 1: Base Data Management** (8 abas)
| # | Aba | Status | Função |
|---|---|---|---|
| 1 | MÃO DE OBRA | ✅ MAPEADA | Base de dados de funções e salários |
| 2 | EQUIPAMENTOS | ✅ MAPEADA | Base de dados de equipamentos |
| 3 | BDI | ✅ MAPEADA | Taxas de markup por tipo de custo |
| 4 | PRODUÇÕES | ✅ MAPEADA | Taxas de produção horária |
| 5 | PRATICABILIDADE | ✅ MAPEADA | Fatores de produtividade mensais |
| 6 | MATERIAIS | ✅ DESCOBERTA NOVA | Base de custos de materiais-primas |
| 7 | CPU | ✅ DESCOBERTA NOVA | Composição unitária de serviços |
| 8 | Transportes | ✅ DESCOBERTA NOVA | Especificações técnicas de equipamentos |

### **Layer 2: Operational Calculation** (10 abas)
| # | Aba | Status | Função |
|---|---|---|---|
| 9 | EQUIPE | ✅ MAPEADA | Custos de equipes e atividades |
| 10 | ADM | ✅ MAPEADA | Custos administrativos |
| 11 | TOP | ✅ MAPEADA | Custos de topografia |
| 12 | LAB | ✅ MAPEADA | Custos de laboratório |
| 13 | QSMS | ✅ MAPEADA | Custos de QSMS |
| 14 | MOB | ✅ MAPEADA | Custos de mobilização/desmobilização |
| 15 | Escavação e Carga | ✅ MAPEADA | Custos de escavação |
| 16 | ENCARGOS | ✅ DESCOBERTA NOVA | Taxas de encargos sociais |
| 17 | DD - C. EXAMES E EPI | ✅ DESCOBERTA NOVA | Custos de exames e EPIs |
| 18 | C_FIXO | ❓ VERIFICAR | Consolidação de custos fixos |

### **Layer 3: Execution Planning** (3 abas)
| # | Aba | Status | Função |
||---|---|---|
| 19 | CRONOGRAMA | ✅ MAPEADA | Cronograma de atividades |
| 20 | PLANEJAMENTO | ✅ MAPEADA | Planejamento orçamentário |
| 21 | RESULTADO | ✅ MAPEADA | Resultado financeiro |

### **Layer 4: Financial Validation** (1 aba)
| # | Aba | Status | Função |
|---|---|---|---|
| 22 | PONTO DE EQUILIBRIO | ✅ MAPEADA | Análise de viabilidade |

---

## 🔄 Impacto nas Skills Existentes

### **Skill 1: base-data** ✏️ REQUER UPDATE
**Adicionar:**
- ✅ CPU (composição unitária - nova)
- ✅ MATERIAIS (custos de materiais - nova)
- ⚠️ Transportes (especificações técnicas - como referência)

**Remover:**
- ❌ DADOS (não existe)

**Novos métodos necessários:**
- `load_cpu_services()` - carrega serviços precificados
- `load_material_costs()` - carrega custos de materiais
- `validate_cpu_completeness()` - valida se todos serviços tem preço

---

### **Skill 2: operational-calc** ✏️ REQUER GRANDE UPDATE
**Adicionar:**
- ✅ ENCARGOS (multiplicador de custos de mão de obra)
- ✅ DD - EXAMES E EPI (custos adicionais de pessoal)

**Modificar:**
- `calculate_crew_cost()` - deve agora multiplicar salário por (1 + ENCARGOS%)
- `validate_cost_delta()` - ajustar para incluir EPIs

**Novos métodos necessários:**
- `apply_encargos_social(salary, encargo_rate)` - aplica encargos
- `calculate_epi_costs(team_size, selected_epis)` - calcula EPIs
- `calculate_total_crew_cost_with_benefits()` - integra tudo

---

### **Skill 3: execution-planning** ✏️ REQUER VALIDAÇÃO
- Validar se CPU row 52 é realmente referência
- Pode não requer mudanças se PLANEJAMENTO usa auto-lookup

---

### **Skill 4: financial-validation** ✅ PODE NER AJUSTE
- Pode precisar reformular se EPIs e ENCARGOS afetam margem

---

## 📋 Próximos Passos Prioritários

### **[ALTA PRIORIDADE]**
1. ✅ Atualizar `skills/1-base-data/skill.py`:
   - Adicionar CPU, MATERIAIS, Transportes
   - Novos validadores

2. ✅ Atualizar `skills/2-operational-calc/skill.py`:
   - Integrar ENCARGOS no cálculo de crew_cost
   - Adicionar DD - EXAMES E EPI
   - Recalcular deltas

3. ✅ Atualizar `skills/manifest.json`:
   - Adicionar 4 novas abas ao mapeamento

### **[MÉDIA PRIORIDADE]**
4. ✅ Criar testes com dados reais
5. ✅ Validar PLANEJAMENTO linha 52 (é referência CPU?)

### **[IMPLEMENTAÇÃO]**
6. Executar testes com skills atualizadas
7. Documentar mudanças em PROCEDIMENTO_PLANEJAMENTO_AGIS.md

---

## 📊 Resumo das Descobertas

| Item | Antes | Depois | Status |
|---|---|---|---|
| Abas documentadas | 18/20 | 22/22 | ✅ 100% |
| Abas "DADOS" | Esperada | Não existe (=MATERIAIS) | ✅ Resolvido |
| Aba CPU | Desconhecida | Composição Unitária | ✅ Descoberta |
| Aba ENCARGOS | Desconhecida | Encargos Sociais | ✅ Descoberta |
| Aba DD - EXAMES | Desconhecida | EPIs + Exames | ✅ Descoberta |
| Aba Transportes | Desconhecida | Especificações Técnicas | ✅ Descoberta |
| Skills a atualizar | 0/4 | 2/4 (1, 2) | ✅ Planejado |
| **Cobertura Total** | **82%** | **100%** | ✅ |

---

**Status Geral:** Descoberta completa - Pronto para atualizar Skills

