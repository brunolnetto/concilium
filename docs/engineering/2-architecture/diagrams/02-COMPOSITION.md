# Diagramas: Insumo ↔ CPU (Compatibilização Relacional)

## 1. Relação M:N (Many-to-Many)

```mermaid
erDiagram
    INSUMO ||--o{ COMPOSICAO_ITEM : "compõe"
    CPU ||--o{ COMPOSICAO_ITEM : "contém"
    
    INSUMO {
        string id
        string codigo
        string tipo "MAO_OBRA | EQUIPAMENTO | MATERIAL | TERCEIRIZADO"
        string unidade "mes | h | litro | m3"
        float preco_unitario
        string fonte_preco
    }
    
    CPU {
        string codigo
        string unidade
        float producao_horaria
        list composicao_itens
    }
    
    COMPOSICAO_ITEM {
        string insumo_id
        float coeficiente
        string categoria_custo
        float percentual_bdi
    }
```

## 2. Exemplo: CPU ESCO-CARGA Composta por Insumos

```mermaid
graph TD
    CPU["CPU: ESCO-CARGA-1CAT-DMT2000<br/>Produção: 233.54 m³/h<br/>Unidade: m³"]
    
    CPU -->|"composição_itens[0]"| I1["ESCAV-HID-38T<br/>(EQUIPAMENTO)<br/>coef: 0.00428188 h/m³<br/>preço: R$ 175.50/h<br/>custo/m³: R$ 0.75"]
    
    CPU -->|"composição_itens[1]"| I2["CAM-BASC-14M3<br/>(EQUIPAMENTO)<br/>coef: 0.02997319 h/m³<br/>preço: R$ 245.00/h<br/>custo/m³: R$ 7.34"]
    
    CPU -->|"composição_itens[2]"| I3["DIESEL-S10<br/>(MATERIAL)<br/>coef: 0.12203368 l/m³<br/>preço: R$ 5.42/l<br/>custo/m³: R$ 0.66"]
    
    CPU -->|"composição_itens[3]"| I4["OPER-ESCAV<br/>(MAO_OBRA)<br/>coef: 0.1136 mes/m³<br/>preço: R$ 2,043.36/mes<br/>custo/m³: R$ 232.12"]
    
    CPU -->|"composição_itens[4]"| I5["AJUDANTE<br/>(MAO_OBRA)<br/>coef: 0.0568 mes/m³<br/>preço: R$ 2,043.36/mes<br/>custo/m³: R$ 116.06"]
    
    CPU -->|"= TOTAL"| TOTAL["Custo Unitário: R$ 356.93/m³<br/>Com BDI (30%): R$ 463.84/m³"]
    
    I1 --> V1["✓ Validação OK"]
    I2 --> V1
    I3 --> V1
    I4 --> V1
    I5 --> V1
    
    style CPU fill:#ffffcc
    style I1 fill:#e6f0ff
    style I2 fill:#e6f0ff
    style I3 fill:#e6f0ff
    style I4 fill:#e6f0ff
    style I5 fill:#e6f0ff
    style TOTAL fill:#e6ffe6
    style V1 fill:#90EE90
```

## 3. Fluxo de Cálculo: Insumo → CPU → Projeto

```mermaid
graph LR
    subgraph Insumo["1️⃣ CATÁLOGO INSUMO"]
        INS1["ESCAV-HID-38T<br/>R$ 175.50/h"]
        INS2["DIESEL-S10<br/>R$ 5.42/l"]
        INS3["OPER-ESCAV<br/>R$ 2,043.36/mes"]
    end
    
    subgraph ComposicaoCPU["2️⃣ COMPOSIÇÃO CPU"]
        COEF1["0.00428188 h/m³"]
        COEF2["0.12203368 l/m³"]
        COEF3["0.1136 mes/m³"]
    end
    
    subgraph CalcCPU["3️⃣ CÁLCULO CPU"]
        CALC1["0.00428188 × 175.50<br/>= R$ 0.75/m³"]
        CALC2["0.12203368 × 5.42<br/>= R$ 0.66/m³"]
        CALC3["0.1136 × 2,043.36<br/>= R$ 232.12/m³"]
        CPU_TOTAL["TOTAL: R$ 356.93/m³"]
    end
    
    subgraph Projeto["4️⃣ PROJETO"]
        QTDE["80,000 m³"]
        SUBTOTAL["R$ 356.93 × 80,000<br/>= R$ 28,554,400"]
        BDI["Com BDI (30%):<br/>R$ 37,120,800"]
    end
    
    INS1 --> COEF1
    INS2 --> COEF2
    INS3 --> COEF3
    
    COEF1 --> CALC1
    COEF2 --> CALC2
    COEF3 --> CALC3
    
    CALC1 --> CPU_TOTAL
    CALC2 --> CPU_TOTAL
    CALC3 --> CPU_TOTAL
    
    CPU_TOTAL --> QTDE
    QTDE --> SUBTOTAL
    SUBTOTAL --> BDI
    
    style INS1 fill:#e6f0ff
    style INS2 fill:#e6f0ff
    style INS3 fill:#e6f0ff
    style CALC1 fill:#fff9e6
    style CALC2 fill:#fff9e6
    style CALC3 fill:#fff9e6
    style CPU_TOTAL fill:#ffffcc
    style BDI fill:#e6ffe6
```

## 4. Matriz de Tipos de Insumo

```mermaid
graph TB
    subgraph MAO["MAO_OBRA<br/>(Labor)"]
        M1["AJUDANTE<br/>mes<br/>R$ 2,043.36"]
        M2["OPER-ESCAV<br/>mes<br/>R$ 2,043.36"]
        M3["Atributo:<br/>categoria_sindical<br/>horas_extras_pct"]
    end
    
    subgraph EQUIP["EQUIPAMENTO<br/>(Machinery)"]
        E1["ESCAV-HID-38T<br/>h<br/>R$ 175.50"]
        E2["CAM-BASC-14M3<br/>h<br/>R$ 245.00"]
        E3["Atributo:<br/>consumo_litros_hora<br/>potencia_cv"]
    end
    
    subgraph MAT["MATERIAL<br/>(Commodities)"]
        MA1["DIESEL-S10<br/>litro<br/>R$ 5.42"]
        MA2["CIMENTO<br/>kg<br/>R$ 0.80"]
        MA3["Atributo:<br/>fonte_preco<br/>cotacao_data"]
    end
    
    subgraph TERC["TERCEIRIZADO<br/>(Subcontracted)"]
        T1["TERRAPL-TERC<br/>m3<br/>R$ 12.50"]
        T2["Atributo:<br/>fornecedor_id<br/>prazo_dias"]
    end
    
    M1 --> M3
    M2 --> M3
    E1 --> E3
    E2 --> E3
    MA1 --> MA3
    MA2 --> MA3
    T1 --> T2
    
    style MAO fill:#ccf
    style EQUIP fill:#cfc
    style MAT fill:#ffc
    style TERC fill:#fcc
```

## 5. Validações Necessárias (VAL-CPU-INS-*)

```mermaid
graph TB
    CPU["CPU submetida"]
    
    V1{"VAL-CPU-INS-01<br/>Insumo existe<br/>no catálogo?"}
    
    V2{"VAL-CPU-INS-02<br/>Tipo insumo<br/>combina com<br/>categoria_custo?"}
    
    V3{"VAL-CPU-INS-03<br/>Coeficiente<br/>> 0?"}
    
    V4{"VAL-CPU-INS-04<br/>Coeficiente<br/>sensato<br/>para unidade?"}
    
    V5{"VAL-CPU-INS-05<br/>Unidade do insumo<br/>combina com<br/>coeficiente?"}
    
    V6{"VAL-CPU-INS-06<br/>Funções<br/>existem?"}
    
    V7{"VAL-CPU-INS-07<br/>Equipamentos<br/>existem?"}
    
    PASS["✅ CPU APROVADA<br/>Pode ser usada"]
    
    FAIL["❌ CPU REJEITADA<br/>Erros detectados"]
    
    CPU --> V1
    V1 -->|FAIL| FAIL
    V1 -->|PASS| V2
    V2 -->|FAIL| FAIL
    V2 -->|PASS| V3
    V3 -->|FAIL| FAIL
    V3 -->|PASS| V4
    V4 -->|FAIL| FAIL
    V4 -->|PASS| V5
    V5 -->|FAIL| FAIL
    V5 -->|PASS| V6
    V6 -->|FAIL| FAIL
    V6 -->|PASS| V7
    V7 -->|FAIL| FAIL
    V7 -->|PASS| PASS
    
    style CPU fill:#ffffcc
    style PASS fill:#e6ffe6
    style FAIL fill:#ffe6e6
```

## 6. Compatibilidade de Tipos

```mermaid
graph TB
    subgraph Mapeamento["Compatibilidade: Insumo.tipo → categoria_custo"]
        
        M1["Insumo.tipo<br/>MAO_OBRA"]
        C1["categoria_custo<br/>MAO_OBRA ✓"]
        
        M2["Insumo.tipo<br/>EQUIPAMENTO"]
        C2["categoria_custo<br/>EQUIPAMENTO ✓"]
        
        M3["Insumo.tipo<br/>MATERIAL"]
        C3["categoria_custo<br/>DIESEL ou MATERIAL ✓"]
        
        M4["Insumo.tipo<br/>TERCEIRIZADO"]
        C4["categoria_custo<br/>TERCEIRIZADO ✓"]
    end
    
    M1 ==>|"DEVE<br/>SER<br/>IGUAL"| C1
    M2 ==>|"DEVE<br/>SER<br/>IGUAL"| C2
    M3 ==>|"PODE SER<br/>MATERIAL<br/>ou DIESEL"| C3
    M4 ==>|"DEVE<br/>SER<br/>IGUAL"| C4
    
    style M1 fill:#ccf
    style M2 fill:#cfc
    style M3 fill:#ffc
    style M4 fill:#fcc
    style C1 fill:#ccf
    style C2 fill:#cfc
    style C3 fill:#ffc
    style C4 fill:#fcc
```

## 7. Compatibilidade de Unidades

```mermaid
graph TB
    subgraph Unidades["Compatibilidade: Insumo.unidade ↔ Coeficiente"]
        
        U1["Insumo: AJUDANTE<br/>unidade: mes"]
        C1["Coeficiente: 0.1136<br/>Significa: 0.1136 meses/m³<br/>✓ Compatível"]
        
        U2["Insumo: ESCAV-HID-38T<br/>unidade: h"]
        C2["Coeficiente: 0.00428188<br/>Significa: 0.00428188 h/m³<br/>✓ Compatível"]
        
        U3["Insumo: DIESEL-S10<br/>unidade: litro"]
        C3["Coeficiente: 0.12203368<br/>Significa: 0.12203368 litros/m³<br/>✓ Compatível"]
        
        U4["Insumo: CIMENTO<br/>unidade: kg"]
        C4["Coeficiente: 23.5<br/>Significa: 23.5 kg/m³<br/>✓ Compatível"]
    end
    
    U1 --> C1
    U2 --> C2
    U3 --> C3
    U4 --> C4
    
    style U1 fill:#e6f0ff
    style U2 fill:#e6f0ff
    style U3 fill:#e6f0ff
    style U4 fill:#e6f0ff
    style C1 fill:#e6ffe6
    style C2 fill:#e6ffe6
    style C3 fill:#e6ffe6
    style C4 fill:#e6ffe6
```
