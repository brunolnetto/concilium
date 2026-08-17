# Mapeamento do Formulário e Variáveis-Chave — Skills AGIS

**Data**: 2026-08-13  
**Escopo**: Modelagem de dados do catálogo, variáveis financeiras e distribuição de recursos no pipeline de skills

---

## 1. ESTRUTURA DE CATÁLOGO (Camada 2)

### 1.1 Hierarquia de Entidades

```
┌─ Insumo (elemento atômico)
│  ├─ tipo: MAO_OBRA, EQUIPAMENTO, MATERIAL, TERCEIRIZADO, TREINAMENTO, EXAME, BENEFICIO
│  ├─ preco_unitario: R$/unidade (catálogo)
│  ├─ unidade: m3, m2, kg, l/h, etc.
│  └─ atributos_especificos: AtributosInsumo
│
├─ Producao (produtividade — PRIMEIRA CLASSE, versionada)
│  ├─ id: "CPU-TERRA-ATI-041-PROD-001"
│  ├─ codigo: "ESCO-CARGA-1CAT"
│  ├─ producao_horaria: float (m2/h, m3/h, etc.)
│  ├─ unidade: str (unidade de produção)
│  ├─ composicao_padrao_equipe: ComposicaoPadraoEquipe
│  │  ├─ funcoes: [FuncaoEquipe{funcao_id, num_pessoas}]
│  │  └─ equipamentos: [EquipamentoEquipe{equip_id, num_unidades}]
│  ├─ origem: OrigemProducao{tipo, fonte_id, data_calibracao}
│  ├─ qualidade: QualidadeProducao{confianca_pct, intervalo_confianca}
│  └─ grafo_sinergia: GrafoSinergiaEquipe (opcional, ADR-130)
│
└─ CPU — Composição de Preço Unitário
   ├─ codigo: "CPU-TERRA-ATI-041"
   ├─ unidade: "m2"
   ├─ producao_id_ref: "CPU-TERRA-ATI-041-PROD-001" (FK → Producao)
   ├─ composicao_itens: [ComposicaoItem{insumo_id, coeficiente}]
   │  └─ Contém MATERIAL e COMBUSTIVEL apenas (ADR-138)
   │      MO e EQ vêm da Producao.composicao_padrao_equipe
   └─ categoria: TERRAPLENAGEM, PAVIMENTACAO, etc.
```

---

## 2. VARIÁVEIS FUNDACIONAIS

### 2.1 Preço Unitário (PU) — Bottom-Up vs Catálogo

**Definição**: Custo para executar 1 unidade do serviço (ex: R$/m², R$/m³)

**Fonte 1 — Bottom-Up (NEP-032, recomendado)**
```python
PU_sem_bdi = Σ[
    # Mão de Obra (todas as funções na equipe)
    (SALARIO_MENSAL / HORAS_MES) × NUM_PESSOAS × ENCARGOS
    
    # Equipamentos (aluguel + manutenção)
    (CUSTO_MENSAL_ALUGUEL / HORAS_MES) × NUM_UNIDADES
    
    # Combustível (consumo horário)
    L_POR_HORA × PRECO_L
    
    # Materiais (do composicao_itens da CPU)
    COEF_INSUMO × PRECO_INSUMO
] / PRODUCAO_HORARIA

# Fórmula geral
PU_sem_bdi = (CUSTO_TOTAL_EQUIPE_HORA + CUSTO_MATERIAL_HORA) / PRODUCAO_HORARIA
```

**Fonte 2 — Catálogo (Fallback, ADR-138)**
```python
PU_sem_bdi = Σ(COEF_INSUMO × PRECO_INSUMO)  # apenas composicao_itens da CPU
```

**Arquivo**: `src/concilium/application/skills/manifests/06-resultado-financeiro/_precificacao/`

---

### 2.2 Produtividade Horária (ρ)

**Definição**: Quantidade produzida por hora de trabalho da equipe

| Campo | Tipo | Unidade | Fonte | Notas |
|-------|------|---------|-------|-------|
| `Producao.producao_horaria` | float | m²/h, m³/h, etc. | Catálogo | Calibrada contra obra real |
| `Planejamento.produtividade_catalogo` | float | idem | Canonicalizei | Referência estrutural (ρ_i) |
| `Planejamento.beta_praticabilidade` | float | fator | Skill 04 | Ajuste climático/calendário (β_i) |
| **Produtividade Efetiva** | ρ_i × β_i | idem | Derivado | Usado em precificação |

**Cálculo**:
```python
produtividade_efetiva = producao_horaria × beta_praticabilidade
produtividade_efetiva = producao_horaria × (fator_clima × fator_calendario)
```

**Arquivo**: `src/concilium/application/skills/manifests/04-cronograma/_skill_helpers/_calendario.py:441-459`

---

### 2.3 Custo Horário (C_h) — Taxa de Consumo de Recursos

**Definição**: Custo total/hora de operação de 1 equipe completa

**Componentes**:

| Componente | Variável | Origem | Cálculo |
|-----------|----------|--------|---------|
| **Mão de Obra** | C_h^MO | Funcoes na Producao | ∑(salario_mensal / horas_mes × num_pessoas × (1+encargos)) |
| **Equipamentos** | C_h^EQ | Equipamentos na Producao | ∑(preco_unitario / horas_mes × num_unidades) |
| **Combustível** | C_h^COMB | Insumo DIESEL/CNG | ∑(l_por_hora × preco_l) |
| **Materiais** | C_h^MAT | Composicao_itens (CPU) | ∑(coef × preco_unitario) × producao_horaria |

```python
# Custo horário total (sem BDI)
custo_horario_total = C_h^MO + C_h^EQ + C_h^COMB + C_h^MAT

# Relação com PU
PU_sem_bdi = custo_horario_total / producao_horaria
```

**Arquivo**: `src/concilium/application/skills/manifests/04-cronograma/_skill_helpers/_custos.py`

---

## 3. DISTRIBUÇÃO DE EQUIPES E CRONOGRAMA

### 3.1 Dimensionamento de Frentes (n_frentes, duração)

**Entrada**: Quantitativo, produtividade, cronograma do usuário

**Cálculo (Skill 04)**:
```python
# Duração com 1 frente (sem limite)
duracao_1_frente = ceil(quantitativo / (producao × horas_semana × semanas_necessarias))

# Equipes necessárias (skill 04 recebe do usuário)
n_frentes_cronograma = num_equipes_por_item["item_id"]["YYYY-Www"]

# Duração ajustada
duracao_ajustada = ceil(duracao_1_frente / n_frentes_cronograma)
```

**Variável Chave**: `num_equipes_por_item` — dicionário distribuindo equipes por semana

```python
CRONOGRAMA = {
    "SV-001": {
        "2026-W45": 2,  # 2 equipes na semana 45
        "2026-W46": 2,
        ...
    },
    "SV-004": {
        "2026-W50": 7,  # 7 equipes em dez/jan (período chuvoso)
        ...
    }
}
```

**Arquivo**: `src/concilium/application/skills/manifests/04-cronograma/_skill_helpers/_spec.py:62-128`

---

### 3.2 Quantitativos Semanais (Q_semana)

**Cálculo (Skill 04 e 05)**:
```python
# Produção semanal com n_frentes
qtd_semanal = producao_efetiva × horas_semana × n_frentes × dias_atividade

# Acumulado
qtd_acumulada += qtd_semanal

# Término quando acumulada >= quantitativo_total
```

**Rastreamento no Canonical**:
- `cronograma[].atividades[]` — lista de semanas com produções
- `intervalos_atividade[]` — faixas de semana por atividade
- `composicao_equipes_atividade[]` — detalhes de cada frente

**Arquivo**: `src/concilium/application/skills/manifests/04-cronograma/`

---

## 4. CUSTOS — SEM BDI E COM BDI

### 4.1 Planejamento: Precificação de Atividade

**Estrutura** (`Planejamento` class):
```python
class Planejamento(BaseModel):
    item_id: str
    cpu_id: str
    quantitativo: float
    
    # PU por categoria (SBDI — sem BDI)
    preco_unitario: PrecoUnitarioCategoria  # {material, diesel, mao_obra, equipamentos, total}
    bdi: BdiCategorias  # fração multiplicativa por categoria
    preco_unitario_com_bdi: PrecoUnitarioCategoria  # aplicado BDI
    
    # Subtotais
    subtotal: SubtotalSemBdiComBdi
        .sem_bdi: SubtotalCategorias  # por categoria
        .com_bdi: SubtotalCategorias
    
    # Rastreamento
    produtividade_catalogo: float  # ρ_i (referência)
    beta_praticabilidade: float  # β_i (fator climático)
    precificacao_via_fallback_composicao: bool  # Fonte 1 ou Fonte 2?
```

**Cálculo**:
```python
# Sem BDI
subtotal_sem_bdi = preco_unitario.total × quantitativo

# Com BDI (por categoria)
bdi_total_aplicado = preco_unitario.material × bdi.material
                   + preco_unitario.diesel × bdi.diesel
                   + preco_unitario.mao_obra × bdi.mao_obra
                   + preco_unitario.equipamentos × bdi.equipamentos

subtotal_com_bdi = subtotal_sem_bdi + bdi_total_aplicado
```

**Arquivo**: `src/concilium/application/skills/manifests/06-resultado-financeiro/_precificacao/_skill_helpers/_planejamento_entry.py`

---

### 4.2 Custos por Atividade (CustoAtividade)

**Rastreamento em Canonical**:
```python
canonical.custos_atividades = [
    {
        "atividade_id": "SV-001",
        "cpu_id": "CPU-TERRA-ATI-041",
        "quantitativo": 169798.78,
        "custo_horario_unitario": 3472.55,  # C_h / composição padrão
        "producao_horaria": 582.75,
        "custo_total": 169798.78 × PU_sem_bdi,
        "custo_com_bdi": custo_total × (1 + BDI_MEDIO),
        ...
    }
]
```

**Agrupamento**:
- `custo_direto_equipes` = Σ(custos_atividades)
- Separado por categoria: MO, EQ, MATERIAL, COMBUSTÍVEL

**Arquivo**: `src/concilium/application/skills/manifests/06-resultado-financeiro/_consolidacao/`

---

## 5. CUSTOS INDIRETOS (ADM, TOP, LAB, QSMS, MOB)

### 5.1 Estrutura (Indireto class)

```python
class Indireto(BaseModel):
    categoria: Literal["ADM", "TOP", "LAB", "QSMS", "MOB"]
    descricao: str
    
    # Composição de custos
    funcoes: list[dict]  # MO indireta (gestores, segurança, etc.)
    equipamentos: list[dict]  # EQ suporte (veículos, etc.)
    verbas_mensais: list[dict]  # despesas fixas
    verbas_fixas: list[dict]  # mobilização, seguros, etc.
    mobilizacoes: list[Mobilizacao]
    
    # Custos por natureza (NEP-037 D4)
    custo_total: float
    custo_mao_obra: float  # salários base
    custo_encargos: float  # encargos sobre MO
    custo_equipamentos: float
    custo_combustivel: float
    custo_verba: float
    custo_mobilizacao: float
    
    permanencia_meses: float  # duração
```

### 5.2 Cálculo de Custo Semanal/Mensal

**Skill 05 — Indiretos**:
```python
# Custo indireto semanal
custo_indireto_semanal = Σ(categorias) [ custo_total / num_semanas_ativas ]

# Custo indireto mensal
custo_indireto_mensal = Σ(categorias) [ custo_total / permanencia_meses ]

# Ponderado por frentes ativas (skill 05)
custo_indireto_ponderado = custo_total × (frentes_ativas_media / frentes_max)
```

**Rastreamento**:
- `indiretos[]` — lista completa de todos os indiretos
- `indiretos_semanal[]` — custos desagregados por semana
- `indiretos_com_bdi[]` — após aplicação de BDI por categoria

**Arquivo**: `src/concilium/application/skills/manifests/06-resultado-financeiro/_indiretos/`

---

## 6. BDI — Benefícios, Despesas Indiretas e Lucros

### 6.1 Estrutura de BDI

**Definição**: Fator multiplicativo por categoria de custo

```python
class BdiCategorias(BaseModel):
    material: float      # ex: 0.347 (34.7%)
    diesel: float        # ex: 0.04 (4%)
    mao_obra: float      # ex: 0.347 (34.7%)
    equipamentos: float  # ex: 0.347 (34.7%)
```

**Componentes Típicos (planilha AGIS)**:
```
BDI_MO = (AC + DF + R + CR) + LUCRO + (COFINS + ISS + PIS + CSSL + IR)
       = 0.04 + 0.01 + 0.01 + 0 + 0.10 + (0.03 + 0.05 + 0.0065 + 0.0199 + 0.0274)
       ≈ 0.347 (34.7%)

BDI_MATERIAL = 0.347 (idem)
BDI_DIESEL = 0.04 (apenas impostos)
```

### 6.2 Aplicação de BDI

**Skill 06 — Resultado Financeiro**:
```python
# Por categoria
valor_com_bdi = valor_sem_bdi × (1 + bdi)

# Total
total_com_bdi = Σ(categorias) [
    valor_categoria_sem_bdi × (1 + bdi_categoria)
]

# Fator BDI efetivo (ponderado)
bdi_efetivo = (total_com_bdi - total_sem_bdi) / total_sem_bdi
```

**Rastreamento**:
- `Planejamento.bdi` — por atividade
- `Indireto` — aplicado aos custos indiretos por categoria
- `resultado.bdi_lucro_impostos` — fator de margem total

**Arquivo**: `src/concilium/application/skills/manifests/06-resultado-financeiro/_consolidacao/_skill_helpers/_bdi_resolucao.py`

---

## 7. PREÇO DE VENDA (Venda)

### 7.1 Metodologias de Precificação

**Metodologia A — Catálogo (Legado)**
```python
preco_venda_catalogo = PU_sem_bdi × quantitativo × (1 + BDI)
                     = preco_unitario.total × quantidade × (1 + bdi_efetivo)
```

**Metodologia B — Custo-Mais-Margem (Recomendada)**
```python
# Custo real = direto + indireto
custo_real_total = custo_direto_equipes + Σ(indiretos.custo_total)

# Margem (lucro + impostos)
fator_margem = 1 + (LUCRO + IMPOSTOS)  # ex: 1.1433 = 9% lucro + 5.33% tributária

# Preço de venda
preco_venda_custo_mais = custo_real_total × fator_margem
```

### 7.2 Classe Venda

```python
class Venda(BaseModel):
    # Metodologia A
    total_sem_bdi: float  # referência catálogo
    total_com_bdi: float  # incluindo BDI nominal
    
    # Metodologia B
    total_custo_plus: float  # (custo_real) × fator_margem
    total_custo_plus_catalogo: float  # (custo_catálogo) × fator_margem
    bdi_lucro_impostos: float  # fator aplicado (ex: 0.1433)
```

**Reconciliação**:
```python
# Fallback quando planejamento vazio
if venda_sem_bdi <= 0:
    venda_sem_bdi = custo_direto_equipe
    venda_com_bdi = custo_direto_equipe
```

**Arquivo**: `src/concilium/application/skills/manifests/06-resultado-financeiro/_consolidacao/_skill_helpers/_venda_custo.py`

---

## 8. RELAÇÃO ENTRE CUSTO DIRETO E INDIRETO

### 8.1 Taxa de Overhead

**Definição**:
```python
taxa_overhead = custo_indireto_total / custo_direto_equipes
               # ex: 0.25 = 25% de overhead

# Inversamente
custo_direto_pct = custo_direto / (custo_direto + custo_indireto)
custo_indireto_pct = 1 - custo_direto_pct
```

### 8.2 Margem Financeira

**Equação Fundamental**:
```python
# Resultado = Venda - Custo
resultado_financeiro = preco_venda - (custo_direto + custo_indireto)

# Margem (%)
margem_pct = resultado_financeiro / preco_venda × 100

# Status
status_margem = "VERDE" se 8% ≤ margem_pct ≤ 10%
             else "AMARELO" se 5% ≤ margem_pct < 8% ou 10% < margem_pct ≤ 15%
             else "VERMELHO"
```

### 8.3 Ponto de Equilíbrio (Break-Even)

**Definição**: Volume em que resultado = 0

```python
# Custo fixo estrutural
custo_fixo_mensal = ADM + TOP + LAB + QSMS + MOB_demob
custo_fixo_total = custo_fixo_mensal × num_meses

# Margem de contribuição (por unidade)
margem_contribuicao_unitaria = preco_unitario - custo_variavel_unitario

# Volume de break-even
qtd_break_even = custo_fixo_total / margem_contribuicao_unitaria

# Percentual de realização
pct_realizacao = quantitativo_planejado / qtd_break_even
status = "OK" se pct_realizacao > 1.2 else "CRITICO"
```

**Rastreamento em Canonical**:
```python
canonical.ponto_equilibrio = [
    {
        "item_id": "SV-001",
        "custo_fixo_equipe": ...,
        "custo_venda_cpu": ...,
        "delta": venda - custo,
        "delta_pct": delta / venda,
        "frentes_equivalentes": custo_operacional / custo_fixo
    }
]
```

**Arquivo**: `src/concilium/application/skills/manifests/06-resultado-financeiro/_consolidacao/_skill_helpers/_ponto_equilibrio.py`

---

## 9. RECONCILIAÇÃO E INTEGRIDADE — BRIDGE LAYER

### 9.1 Fluxo N1 → N2 → N3 → N4

**N1 — Entrada**: EAP, cronograma, catálogo  
**N2 — Equipes**: Composição de cada equipe (MO + EQ)  
**N3 — Custo Operacional Bridge**: Diagnostica gaps (clima, scale, pool)  
**N4 — Custo Instancial Real**: Aplicado ao pool de recursos

```python
# Bridge (N3)
gap_praticabilidade = Σ(semanas) [
    (producao_catálogo - producao_efetiva) / producao_catálogo × custo_h × n_frentes
]

# N4 (real cobrado)
custo_operacional_real = Σ(pools) [ horas_consumidas × taxa_horária ]

# Limitação conhecida (ADR-148, issue #124)
# gap_praticabilidade diagnosticado em N3, mas NUNCA entra em N4
# (duração não é estendida por clima, mantém RCPSP computável)
```

**Arquivo**: `src/concilium/application/skills/manifests/06-resultado-financeiro/_consolidacao/_skill_helpers/_bridge.py`

---

## 10. MATRIZ DE RASTREAMENTO COMPLETA

| Variável | Skill Origem | Campo no Canonical | Equação / Derivação |
|----------|--------------|-------------------|-------------------|
| **Produção Horária (ρ)** | Catálogo | `planejamento[].produtividade_catalogo` | `Producao.producao_horaria` |
| **Fator Climático (β)** | Skill 02 | `planejamento[].beta_praticabilidade` | `fator_clima × fator_calendario` |
| **Custo Horário (C_h)** | Skill 05 | Implícito em equipes_diretas | ∑(MO + EQ + Comb + Mat) |
| **PU sem BDI** | Skill 06 | `planejamento[].preco_unitario.total` | `C_h / (ρ × β)` |
| **BDI** | Skill 06 | `planejamento[].bdi.*` | Catálogo por categoria |
| **PU com BDI** | Skill 06 | `planejamento[].preco_unitario_com_bdi.total` | `PU_sem_bdi × (1 + BDI)` |
| **Subtotal Atividade (sem BDI)** | Skill 06 | `planejamento[].subtotal.sem_bdi` | `PU_sem_bdi × quantitativo` |
| **Subtotal Atividade (com BDI)** | Skill 06 | `planejamento[].subtotal.com_bdi` | `PU_com_bdi × quantitativo` |
| **Custo Direto (C_direto)** | Skill 06 | `resultado.custo.direto_equipes` | ∑(custos_atividades) |
| **Custo Indireto (C_indireto)** | Skill 05/06 | `resultado.custo.indireto_*` | ∑(indiretos[categoria].custo_total) |
| **Custo Total (C_total)** | Skill 06 | `resultado.custo.total` | `C_direto + C_indireto` |
| **Venda sem BDI** | Skill 06 | `resultado.venda.total_sem_bdi` | `PU_sem_bdi_total × quantidade_total` |
| **Venda com BDI** | Skill 06 | `resultado.venda.total_com_bdi` | `(C_direto + C_indireto) × (1 + BDI_efetivo)` |
| **Venda Custo-Mais** | Skill 06 | `resultado.venda.total_custo_plus` | `(C_direto + C_indireto) × (1 + Lucro + Trib)` |
| **Resultado (Margem)** | Skill 06 | `resultado.resultado_financeiro` | `Venda - (C_direto + C_indireto)` |
| **Margem (%)** | Skill 06 | `resultado.margem_pct` | `Resultado / Venda × 100` |
| **Status Margem** | Skill 06 | `resultado.status_margem` | VERDE / AMARELO / VERMELHO |

---

## 11. FORMULÁRIO DE ENTRADA (Skill 01)

### 11.1 Estrutura EAP

```python
EAP_ITEMS = [
    {
        "item_id": "SV-001",
        "cpu_id": "CPU-TERRA-ATI-041",
        "descricao": "Supressão vegetal de Mata Densa...",
        "unidade": "m2",
        "quantitativo": 169798.78,
        "ordem": 1,
        "predecessores": []  # item_id ou lista de {"item_id": ...}
    },
    ...
]
```

### 11.2 Cronograma

```python
CRONOGRAMA = {
    "SV-001": {
        "2026-W45": 2,  # 2 equipes
        "2026-W46": 2,
        "2026-W47": 2,
        "2026-W48": 2,
    },
    "SV-004": {
        "2026-W50": 7,  # 7 equipes (compensação climática)
        ...
    }
}
```

### 11.3 Contexto (Escopo)

```python
{
    "nome": "CMOC Ouvidor/GO — Supressão Vegetal",
    "tipo_obra": "TERRAPLENAGEM",
    "localizacao": "Ouvidor, Goiás",
    "coordenadas": {"lat": -13.5311, "lng": -48.2262},
    "regime_trabalho": {
        "dias_semana": 6,
        "horas_dia": 8,
        "horas_improdutivas_dia": 0.5
    },
    "data_inicio": "2026-11-02",
    "data_termino": "2027-01-31",
    "contexto_id": "mendeslobo"  # Catálogo a usar
}
```

---

## 12. EXEMPLOS DE CÁLCULO PONTA-A-PONTA

### 12.1 Cenário: Atividade SV-001 (Supressão Mata Densa)

**Dados de Entrada**:
- CPU: CPU-TERRA-ATI-041
- Quantitativo: 169.798,78 m²
- Produção: 582,75 m²/h (Producao.producao_horaria)
- Fator Clima (Nov): 0,90 (β_i)
- Cronograma: 2 equipes × 4 semanas (W45-W48)
- Regime: 6 dias/semana, 8h/dia = 48h/semana

**Cálculo de Cronograma**:
```
Produção efetiva = 582,75 × 0,90 = 524,475 m²/h
Semanas totais = ceil(169.798,78 / (524,475 × 48 × 2))
               = ceil(169.798,78 / 50.350) ≈ 4 semanas ✓
```

**Custo Horário** (de Producao.composicao_padrao_equipe):
- MO: 1 Operador PA (R$6.300/mês) + 3 Motores (R$2.525/mês) + ... = R$472,24/h × 1,66 encargos
- EQ: 1 PA Mandíbula (R$62.400/mês) + 3 Caminhões (R$8.500) + ... = R$1.905/h
- Combustível: L/h × Preço = R$1.095,31/h
- **Total: C_h = R$3.472,55/h**

**PU sem BDI**:
```
PU = 3.472,55 / 582,75 = R$ 5,96/m²
```

**BDI** (catálogo mendeslobo, categoria TERRAPLENAGEM):
```
BDI_MO = 34,7%
BDI_EQ = 34,7%
BDI_COMB = 4,0%
BDI_Ponderado ≈ 0,347 (34,7%)
```

**PU com BDI**:
```
PU_com_bdi = 5,96 × (1 + 0,347) = R$ 8,02/m²
```

**Subtotal da Atividade**:
```
SEM BDI: 169.798,78 m² × R$ 5,96 = R$ 1.012,143,45
COM BDI: 169.798,78 m² × R$ 8,02 = R$ 1.361,319,50
```

**Custo Operacional Real** (Skill 05):
```
Tempo Total = 169.798,78 m² ÷ 524,475 m²/h = 323,5 horas
Equipe-Horas = 323,5 h × 2 frentes = 647 EH
Custo = 647 EH × R$ 3.472,55/h = R$ 2.247.121

Nota: Pode divergir de subtotal por eficiência real vs catálogo
```

**Resultado da Atividade (se isolada)**:
```
Venda sem BDI: R$ 1.012.143,45
Venda com BDI: R$ 1.361.319,50
Custo Operacional: R$ 2.247.121 (com alocação de overhead)
Margem: Negativa (atividade absorve indiretos)
```

---

## 13. PONTOS DE AUDITORIA CRÍTICOS

### 13.1 Verificações Essenciais

- [ ] `producao_horaria` preenchido em todos os CPUs (validação: > 0)
- [ ] Composição de equipe em Producao.composicao_padrao_equipe (MO + EQ)
- [ ] Encargos de MO aplicados (66% = 30% encargos CLT + 31% provisão + 5% admin)
- [ ] BDI diferenciado por categoria (MO 34.7%, Combustível 4%, etc.)
- [ ] Quantitativos = somatório de cronograma (∑ qtd_semanal = quantitativo_total)
- [ ] Margem dentro da faixa aceitável (VERDE: 8-10%, AMARELO: 5-15%)
- [ ] Custo indireto <= 30% do direto (taxa_overhead <= 0,30)
- [ ] Ponto de equilíbrio coberto (pct_realizacao >= 1.2)

### 13.2 Erros Comuns

| Erro | Causa | Detecção |
|------|-------|----------|
| PU subestimado | `producao_horaria = 0` ou fallback composição | Skill 06 alerta frentes_necessarias > 1.5 |
| BDI sobre-aplicado | BDI global em vez de por categoria | Venda com BDI > custo real × 2 |
| Overhead omitido | Indiretos fora do cronograma | Custo operacional >> custo direto |
| Sincronismo cronograma | Semanas desalinhadas com quantitativo | ∑ qtd_semanal ≠ quantitativo_total |

---

## 14. τ_i: FRENTES NECESSÁRIAS (Fórmula Crítica de Viabilidade)

### 14.1 Definição e Fórmulas

**Símbolo:** τ_i = `frentes_equivalentes_necessarias`

**Fórmula Direta:**
$$\tau_i = \frac{\text{custo\_total\_autonomo}}{\text{venda\_sem\_bdi}}$$

**Fórmula Teórica (Reformulação User):**
$$\tau_i = 1 + (1-\delta_i)\frac{1-\bar{\varepsilon}_i}{\bar{\varepsilon}_i}$$

Onde:
- $\delta_i = \frac{\gamma_i^v}{\gamma_i^c + \gamma_i^v}$ = fração de custos consumíveis
- $\bar{\varepsilon}_i = \frac{\sum_j \varepsilon_j m_{ij}}{\sum_j m_{ij}}$ = produtividade média ponderada por frentes
- $\gamma_i^c$ = custos contratados (MO + EQ + Mob + Overhead)
- $\gamma_i^v$ = custos consumíveis (Diesel/Combustível)
- $m_{ij}$ = número de frentes paralelas

**Fórmula do Gap:**
$$OC_i - CC_i = \gamma_i^c \cdot \sum_j(1-\varepsilon_j)m_{ij}$$

### 14.2 Interpretação Econômica

- **τ_i < 1.0**: Projeto viável com margem positiva
- **τ_i = 1.0**: Ponto de equilíbrio (margem zero)
- **τ_i > 1.0**: Projeto inviável; precisaria de τ_i paralelos para viabilizar

**Exemplo:** τ_i = 4.31 significa "seriam necessárias 4,31 unidades paralelas deste projeto para quebrar a margem"

### 14.3 Componentes da Estrutura Econômica

**Custos Contratados (Fixos, não escaláveis com ε):**
- Mão de Obra (permanência mínima)
- Equipamentos (aluguel mensal)
- Mobilização/Desmobilização
- Overhead Pool (ADM, TOP, QSMS, LAB)
- **Total ≈ 79% do custo**

**Custos Consumíveis (Escaláveis com ε):**
- Diesel/Combustível (varia com execução real)
- **Total ≈ 21% do custo**

### 14.4 Localização em Código

| Componente | Arquivo | Linha | Campo |
|-----------|---------|-------|-------|
| Cálculo τ_i | _ponto_equilibrio.py | 47 | `frentes_nec` |
| Custo Operacional | _causal_cost_partition.py | 50-200 | `custo_total_autonomo` |
| Custo Catálogo | Skill 06 precificação | — | `planejamento.subtotal.sem_bdi.total` |
| Produtividade Média | _ponto_equilibrio.py | 670+ | `eta_real` = $\bar{\varepsilon}_i$ |
| Machine-weeks | _ponto_equilibrio.py | 650+ | `machine_weeks_brutas`, `machine_weeks_efetivas` |
| Modelo de Dados | _financeiro_resultado.py | 95-195 | `PontoEquilibrio` dataclass |

### 14.5 Validação Numérica (MATA_DENSA_SIMPLES)

**Dados Observados:**
- OC_i = R$ 336.103,34 (custo operacional)
- CC_i = R$ 78.007,38 (custo catálogo)
- τ_i = 4.3100 (observado)

**Validação Fórmula Direta:**
- Cálculo: 336.103 / 78.007 = 4.3086 ✅
- Diferença vs código: 0.03%

**Validação Fórmula Teórica:**
- δ_i = 0.207 (20.7% consumível)
- ε̄_i = 0.230 (23% de produtividade realizada)
- τ_i = 1 + 0.793 × 3.348 = 3.66
- Gap residual vs observado: 0.65 (15%)
- Causa: Overhead tem sensibilidade parcial a ε_j

**Documentação Completa:**
- [PROVA_COMPLETA_TAU_431.md](PROVA_COMPLETA_TAU_431.md) — Três provas e validação numérica
- [ESTRUTURA_ECONOMICA_CONTRATADO_CONSUMIVEL.md](ESTRUTURA_ECONOMICA_CONTRATADO_CONSUMIVEL.md) — Categorização de custos
- [MAPEAMENTO_TEORIA_CODIGO.md](MAPEAMENTO_TEORIA_CODIGO.md) — Símbolos teóricos ↔ variáveis AGIS

---

## 15. ARQUIVOS DE REFERÊNCIA

| Arquivo | Propósito | Skills |
|---------|-----------|--------|
| `src/concilium/domain/models/catalog/catalogo.py` | Insumo, CPU, ComposicaoItem | 01, 03, 06 |
| `src/concilium/domain/models/catalog/producao.py` | Producao, ComposicaoPadraoEquipe | 02, 04, 05 |
| `src/concilium/domain/models/canonical/_financeiro_resultado.py` | Planejamento, Venda, CustoTotal, Resultado | 06 |
| `src/concilium/application/skills/manifests/04-cronograma/_skill_helpers/_custos.py` | Cálculo de PU bottom-up | 04 |
| `src/concilium/application/skills/manifests/06-resultado-financeiro/_precificacao/` | Precificação (PU + BDI) | 06 |
| `src/concilium/application/skills/manifests/06-resultado-financeiro/_consolidacao/` | Resultado financeiro | 06 |
| `src/concilium/application/skills/manifests/06-resultado-financeiro/_indiretos/` | Custos indiretos | 05, 06 |

---

**Versão**: 1.0  
**Última atualização**: 2026-08-13  
**Autor**: Engenheiro de Planejamento AGIS
