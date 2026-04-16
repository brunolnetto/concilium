# Base Data Management Skill

**Skill ID:** `base-data`  
**Version:** 1.0.0  
**Layer:** 1 - Foundation  
**Status:** Active

## Overview

This skill manages all foundational data tables in the AGIS planning spreadsheet. These are the source tables that feed all downstream calculations and analyses.

## Managed Tables

### 1. DADOS
**Purpose:** Central repository of unit costs and recurring expenses

- **Key Data Points:**
  - Equipamento costs (monthly)
  - Employee/Funcionário costs (salary + benefits)
  - Monthly recurring expenses
  
- **Structure:**
  ```
  Columns: [Descrição, Tipo, Valor/Mês, Unidade, ...]
  Rows: Equipment costs, labor rates, benefits (alimentação, seguro vida, cesta básica, saúde)
  ```

- **Critical Lines (per Procedimento):**
  - L12: Alimentação
  - L24: Seguro de Vida
  - L25: Cesta Básica
  - L26: Plano de Saúde

- **Usage:** Referenced in ADM, MOB (Linha 53 Col K para benefícios)

---

### 2. PRODUÇÕES
**Purpose:** Defines production rates for each construction activity

- **Key Data Points:**
  - Activity name
  - Unit of measure (M3, M2, hour, etc)
  - Hourly production rate
  
- **Structure:**
  ```
  Columns: [Atividade, Unidade, Produção Horária]
  Rows: One row per construction task
  ```

- **Example:**
  ```
  ESCAVAÇÃO, CARGA, TRANSPORTE... | M3 | 15 (units per hour)
  ```

- **Calculation:** 
  - Daily Production = Hourly × 8h = F × 8 (CRONOGRAMA Col G)

- **Usage:** Linked in CRONOGRAMA Line ~5, Col F (Produção Horária)

---

### 3. PRATICABILIDADE
**Purpose:** Monthly productivity factor based on weather conditions

- **Key Data Points:**
  - Days of rain at different thresholds (5-10mm, 10-20mm, >20mm)
  - Monthly productivity percentage

- **Structure:**
  ```
  L13: Dias chuva [5mm ≤ precip < 10mm]    Cols C-N (Jan-Dez)
  L14: Dias chuva [10mm ≤ precip < 20mm]   Cols C-N
  L15: Dias chuva [precip ≥ 20mm]          Cols C-N
  L16: % PRODUTIVO (calculated)            Cols C-N → Used in CRONOGRAMA L8
  ```

- **Calculation:**
  ```
  % PRODUTIVO = 1 - (days_of_rain / working_days_in_month)
  ```

- **Data Source:** 
  - MeteoBLUE historical climate data
  - https://www.meteoblue.com/pt/tempo/historyclimate/climatemodelled/

---

### 4. MÃO DE OBRA (Labor Database)
**Purpose:** Reference table for labor costs and calculations

- **Key Data Points:**
  - Job function (position)
  - Base salary
  - Extra hours calculation
  - Provisionings/Encargos (social contributions)

- **Structure:**
  ```
  Col A: Função (EXACT match required)
  Col H: Salário
  Col K: Horas Extras
  Col S: Encargos e Provisão
  Col U: Custo Total
  ```

- **Critical Requirement:** ⚠️ **EXACT NAME MATCHING**
  - Names in EQUIPE must match EXACTLY (spaces, capital letters, accents)
  - Affects: EQUIPE, ADM, TOP, LAB, QSMS

- **Example Valid Entry:**
  ```
  OPERADOR DE ESCAVADEIRA | R$ 4.500 | 15% | 40% | R$ 6.300
  ```

---

### 5. EQUIPAMENTOS (Equipment&Costs Database)
**Purpose:** Equipment catalog with costs and fuel consumption

- **Key Data Points:**
  - Equipment name
  - Monthly equipment cost
  - Fuel consumption rate
  - Fuel cost per consumption unit

- **Structure:**
  ```
  Col A: Equipamento (EXACT match required)
  Col H: Valor Mensal
  Col R: Consumo Combustível
  Col T: Valor Combustível Mensal
  Col U: Custo Unitário (Eq + Comb)
  Col V: Custo Total
  ```

- **Critical Requirement:** ⚠️ **EXACT NAME MATCHING**
  - Names in EQUIPE must match EXACTLY
  - Affects: EQUIPE, ADM, MOB

- **Example Valid Entry:**
  ```
  ESCAVADEIRA HIDRÁULICA SOBRE ESTEIRA 38T | R$ 15.000 | 80L/dia | R$ 350 | ...
  ```

---

### 6. BDI (Markup/Margin)
**Purpose:** Business profit margin applied to each cost category

- **Key Data Points:**
  - Cost type (Material, Diesel, Labor, Equipment)
  - BDI percentage

- **Structure:**
  ```
  Cols K,L,M,N: BDI % for [Material, Diesel, MO, Equipment]
  Should be applied in PLANEJAMENTO (automatic)
  ```

- **Formula:**
  ```
  Price with BDI = Price without BDI × (1 + BDI%)
  ```

- **Typical Range:** 20-35% total

---

## Data Quality Rules

### R1: Name Exactness
```
🔴 CRITICAL
Fields: MÃO DE OBRA (Col A), EQUIPAMENTOS (Col A)
- No extra spaces before/after
- Match case exactly (e.g., "OPERADOR DE ESCAVADEIRA" not "Operador de Escavadeira")
- Include special characters (é, ã, ç)

💥 Failure: Reference returns #REF! or blank in target tables
```

### R2: Data Completeness
```
🔴 CRITICAL
All 6 tables must have data for a processing run
Missing data locations:
- DADOS: Any missing cost will cascade to ADM, MOB, Equip
- PRODUÇÕES: Missing activity → CRONOGRAMA can't calculate
- PRATICABILIDADE: Missing month → CRONOGRAMA can't calculate
```

### R3: Numeric Consistency
```
🟡 HIGH
- All costs must be positive (> 0)
- All percentages must be 0-100 (BDI, Encargos, Consumo)
- Production rates must be > 0

💥 Failure: Negative or zero values propagate through calculations
```

### R4: Monthly Alignment
```
🟡 HIGH
- PRATICABILIDADE and CRONOGRAMA must have same month sequence
- Column C = January (JAN), Column N = December (DEZ)
- If misaligned, productivity factors won't apply correctly

💥 Failure: Productivity % mismatch between abas
```

---

## Operations & Methods

### Operation: `load_table(table_name)`
**Purpose:** Load a table from spreadsheet into memory

```python
df = skill.load_table("DADOS")
# Returns: Pandas DataFrame with all data from aba DADOS
```

**Outputs:**
- DataFrame with proper types (numeric for costs, string for names)
- NaN values removed or flagged

---

### Operation: `validate_data(dataframe)`
**Purpose:** Run all quality checks on a table

```python
report = skill.validate_data(df)
# Returns: Validation report with passes/failures
```

**Checks:**
- No duplicate names in reference columns
- No nulls in critical columns
- Numeric consistency (positive values, valid percentages)
- Uniqueness of identifiers

**Output Format:**
```json
{
  "status": "PASS" | "FAIL",
  "errors": [...],
  "warnings": [...],
  "summary": "..."
}
```

---

### Operation: `sync_references(source_table, target_table)`
**Purpose:** Validate and sync exact names between tables

```python
status = skill.sync_references("MÃO DE OBRA", "EQUIPE")
# Checks: All names in EQUIPE exist in MÃO DE OBRA
```

**Outputs:**
- Success: Names verified and ready
- Failure: Lists mismatches, typos, extra spaces

---

### Operation: `export_table(dataframe, format="xlsx")`
**Purpose:** Export processed data

```python
path = skill.export_table(df, format="csv")
# Returns: File path to exported file
```

**Supported Formats:**
- `xlsx`: Excel workbook
- `csv`: Comma-separated values
- `json`: JSON format

---

## Input/Output Contracts

### Input Sources
1. **MeteoBLUE Website** → PRATICABILIDADE Table
2. **HR/Finance System** → MÃO DE OBRA Table
3. **Equipment Manager** → EQUIPAMENTOS Table
4. **Budget/Finance** → DADOS Table (costs)
5. **Engineering/Planning** → PRODUÇÕES Table

### Output Destinations
- **EQUIPE**: Uses MÃO DE OBRA + EQUIPAMENTOS
- **ADM**: Uses MÃO DE OBRA + DADOS
- **CRONOGRAMA**: Uses PRODUÇÕES + PRATICABILIDADE
- **PLANEJAMENTO**: Uses BDI for markup calculations

---

## Dependencies & Constraints

### ✅ No Dependencies
This is a root skill with no upstream dependencies.

### ⬇️ Downstream Dependencies
- `operational-calc`: Depends on all 6 tables being available
- `execution-planning`: Indirectly depends via operational-calc
- `financial-validation`: Indirectly depends

### 🚫 Constraints
- Tables are **READ-ONLY** in normal operation
- Changes require approval and versioning
- Name changes in MÃO DE OBRA / EQUIPAMENTOS require cascading updates

---

## Troubleshooting

### Issue: #REF! errors in EQUIPE after loading MÃO DE OBRA
**Cause:** Name mismatch (spaces, case, accents)  
**Solution:**
```python
skill.sync_references("MÃO DE OBRA", "EQUIPE")
# Review report and fix names exactly
```

### Issue: CRONOGRAMA shows 0% productivity
**Cause:** PRATICABILIDADE missing data for month  
**Solution:**
```python
p_table = skill.load_table("PRATICABILIDADE")
skill.validate_data(p_table)
# Check L16 for all months (C-N)
```

### Issue: Cost calculations don't flow to ADM
**Cause:** DADOS missing a required cost entry  
**Solution:**
```python
d_table = skill.load_table("DADOS")
report = skill.validate_data(d_table)
# Review 'warnings' for missing fields
# Add missing costs in proper rows
```

---

## Examples

### Example 1: Validate Complete Dataset
```python
skill = BaseDataSkill()

tables = ["DADOS", "PRODUÇÕES", "PRATICABILIDADE", "MÃO DE OBRA", "EQUIPAMENTOS", "BDI"]
for table_name in tables:
    df = skill.load_table(table_name)
    report = skill.validate_data(df)
    if report['status'] == 'FAIL':
        print(f"❌ {table_name}: {report['errors']}")
    else:
        print(f"✅ {table_name}: OK")
```

### Example 2: Sync Labor Costs After Update
```python
# After updating MÃO DE OBRA in source system
mo_df = skill.load_table("MÃO DE OBRA")
mo_report = skill.validate_data(mo_df)

if mo_report['status'] == 'PASS':
    sync_status = skill.sync_references("MÃO DE OBRA", "EQUIPE")
    if sync_status == 'OK':
        print("✅ EQUIPE references updated")
```

### Example 3: Export Updated Costs
```python
dados_df = skill.load_table("DADOS")
# ... modifications ...
output_file = skill.export_table(dados_df, format="xlsx")
print(f"Exported to: {output_file}")
```

---

## Related Skills
- [`operational-calc`]: Uses DADOS, PRODUÇÕES, MÃO DE OBRA, EQUIPAMENTOS
- [`execution-planning`]: Uses PRODUÇÕES, PRATICABILIDADE
- [`financial-validation`]: Uses BDI

## Useful References
- {PROCEDIMENTO_PLANEJAMENTO_AGIS.md}: Section 2-6
- {Prompt Camila.txt}: Detailed workflow description
- {Relacionamentos_Tabelas.xlsx}: Table relationships
