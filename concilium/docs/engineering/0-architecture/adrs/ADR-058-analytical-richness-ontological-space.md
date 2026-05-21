# ADR-058: Analiticidade do Espaço Ontológico — Decomposição Granular de Custos e Curva ABC

**Status:** Aceito  
**Data:** 2026-05-16  
**Autor:** Engenheiro Sênior  
**Relacionado:** ADR-010 (Activity Cost Breakdown), ADR-023 (BDI), ADR-027 (CPU Sensitivity), ADR-039 (The Bridge), ADR-056 (Debt Remediation), ADR-057 (Memorial BDI)

---

## 1. Contexto

O espaço ontológico do Concilium já contém, distribuído pelo canonical, toda a informação necessária para uma análise de custo extraordinariamente granular:

```
EapItem
  └── cpu_id → CPU
                 ├── composicao_itens: list[ComposicaoItem]
                 │     insumo_id × coeficiente × categoria_custo (MO/EQ/MAT/DIESEL)
                 └── producao_id_ref → Produtividade
                                         └── composicao_padrao_equipe
                                               ├── funcoes: list[FuncaoEquipe]
                                               └── equipamentos: list[EquipamentoEquipe]

EquipeDireta (por item)
  ├── funcoes: list[FuncaoEquipeDireta]    (funcao_id, salario_base, encargos, custo_mensal)
  ├── equipamentos: list[EquipamentoEquipeDireta]  (equip_id, custo_mensal, consumo_diesel)
  ├── custo_mao_obra_mensal
  ├── custo_equipamentos_mensal
  ├── custo_combustivel_total_mensal
  └── permanencia_meses

AtividadeCustoCompleto (por item)
  └── custos_diretos: list[AtividadeInsumo]
        └── InsumoComponenteAtividade
              ├── nome
              ├── itens: list[dict]  ← PROBLEMA: untyped
              └── custo_total

IndiretoSemanal (por semana × categoria TOP/ADM/LAB/QSMS/MOB)
  ├── custo_mao_de_obra
  ├── custo_equipamentos
  └── custo_verbas
```

Apesar dessa riqueza, **nenhum skill ou artifact** a explora além do nível de atividade agregada. A curva ABC existente usa ranking Pareto (top 20/40/70%) por atividade, sem decomposição por insumo, sem curva acumulada, e sem cruzamento com o espaço temporal.

---

## 2. O Que a Analiticidade Plena Permite

### 2.1 Curva ABC Granular (por insumo, não por atividade)

A curva ABC clássica responde: "quais 20% dos itens representam 80% do custo?" No nível atual (atividade), isso já existe. No nível de insumo:

```
Pergunta respondível:
  "O item de custo ESCAVADEIRA HID-38T representa 34% do custo total direto
   do lote. Está nas atividades A1, A3, A7. Seu custo mensal base é R$X.
   Uma variação de 5% no seu preço impacta R$Y na margem."
```

Para isso, a cadeia `ComposicaoItem[insumo_id, coeficiente]` precisa ser rastreada até o `Resultado` através de cada atividade.

### 2.2 Cubo de Custos (multidimensional)

O espaço ontológico define naturalmente um cubo:

| Dimensão | Exemplos de valores |
|----------|-------------------|
| **Insumo** | ESCAV-HID-38T, CAM-BASC-14M3, DIESEL-S10, MO-OPER-ESCAV |
| **Categoria** | EQUIPAMENTO, MAO_OBRA, DIESEL, MATERIAL |
| **Atividade** | eap-1_0, eap-2_0, ... |
| **Tempo** | 2026-W23, 2026-W24, ... (semana ISO) |
| **Imposto** | COFINS, ISS, PIS, CSSL, IR (via BDI por categoria) |
| **BDI** | overhead_ac, overhead_l, tributos |

Aggregações naturais disponíveis:
- Custo total por insumo ao longo do projeto
- Quantidade de equipamentos únicos ativos por semana
- Custo de mão de obra por função por mês
- Impacto de tributos por categoria de custo ao longo do tempo
- S-curve (curva de avanço de custo acumulado)

### 2.3 Sensibilidade por Insumo

Além de saber *quanto* custa cada insumo, o planejador precisa saber *quanto a margem muda* se o preço de um insumo variar:

```
∂Margem/∂Preço(DIESEL-S10) = f(quantidade_total × (1 + BDI_diesel))
```

`CpuExposurePerfil` (ADR-027) já faz isso em 4 vetores (equip, mo, material, outros). Esta ADR propõe aprofundar para vetores por `insumo_id`.

---

## 3. Lacunas Identificadas

### L1 — `InsumoComponenteAtividade.itens` é `list[dict]` sem schema

```python
# Atual — não auditável:
class InsumoComponenteAtividade(BaseModel):
    itens: list[dict] = Field(default_factory=list)  # ← sem tipo

# Proposto — rastreável:
class InsumoDetalheAtividade(BaseModel):
    insumo_id: str              # FK para catálogo
    descricao: str
    categoria: CategoriaCusto   # EQUIPAMENTO / MAO_OBRA / DIESEL / MATERIAL
    coeficiente: float          # da CPU.composicao_itens
    quantidade_total: float     # coeficiente × quantitativo_atividade
    preco_unitario: float       # do catálogo na data de referência
    custo_total: float          # = quantidade_total × preco_unitario
```

### L2 — Sem curva ABC por insumo

O `run_diagnostico_criticidade` (Skill 10) faz ranking Pareto por atividade. Não há skill que construa uma `CurvaABCInsumo` acumulando custos por `insumo_id` através de todas as atividades.

### L3 — Sem agregação semanal de equipamentos

`EquipeDireta.permanencia_meses` é o total; não há `equipamentos_por_semana: dict[str, int]` derivado de `distribuicao_semanal.num_equipes × equipe.equipamentos[i].num_unidades`.

### L4 — Sem S-curve (curva de avanço de custo)

`IndiretoSemanal` existe por categoria, mas não há uma S-curve consolidada que some diretos + indiretos + BDI semana a semana como percentual acumulado do custo total.

### L5 — Sensibilidade por insumo não implementada

`CpuExposurePerfil` (ADR-027) cobre 4 vetores. Não há `InsumoSensibilidade` por `insumo_id` individual.

---

## 4. Decisões

### D1 — `InsumoDetalheAtividade`: modelo tipado para rastreabilidade de insumo

Substituir `itens: list[dict]` por `itens: list[InsumoDetalheAtividade]` em `InsumoComponenteAtividade`. Backward compat via `extra="ignore"` no campo legado.

**Campo adicionado em `InsumoComponenteAtividade`:**
```python
itens_detalhados: list[InsumoDetalheAtividade] = Field(default_factory=list)
```

### D2 — `CurvaABCInsumo`: artifact analítico gerado por Skill 14 ou novo Skill

Estrutura:
```python
@dataclass(frozen=True)
class ItemCurvaABC:
    insumo_id: str
    descricao: str
    categoria: str
    custo_total: float
    pct_custo_acumulado: float   # frações acumuladas de 0 a 1
    classe: Literal["A", "B", "C"]  # A: 0-80%, B: 80-95%, C: 95-100%
    atividades: list[str]        # quais atividades usam este insumo

@dataclass(frozen=True)
class CurvaABCInsumo:
    projeto_id: str
    gerado_em: str
    total_custo_direto: float
    itens: list[ItemCurvaABC]    # ordenados por custo desc
```

### D3 — `AgregacaoSemanal`: equipamentos únicos e custos por semana

```python
@dataclass(frozen=True)
class AgregacaoSemanalEquipamentos:
    semana_iso: str
    equipamentos_ativos: dict[str, int]   # {equip_id: n_unidades}
    custo_equipamentos_semana: float
    custo_mao_obra_semana: float
    custo_diesel_semana: float
    custo_total_semana: float

@dataclass(frozen=True)
class SCurve:
    projeto_id: str
    semanas: list[str]                    # ISO weeks ordenadas
    custo_acumulado: list[float]          # R$ acumulado por semana
    pct_acumulado: list[float]            # fração 0–1
```

### D4 — Skill analítica ou extensão de Skill 14

`14-explorador-cenarios` já faz análise combinatorial. A analiticidade de insumos pode viver ali como um modo adicional, ou como um novo `16-analitica-ontologica` dedicado.

### D5 — Sensibilidade por insumo

Estender `CpuExposurePerfil` com:
```python
sensibilidade_insumos: list[InsumoSensibilidade]

@dataclass(frozen=True)
class InsumoSensibilidade:
    insumo_id: str
    descricao: str
    categoria: str
    custo_base: float
    impacto_margem_por_pct: float  # R$ de impacto por 1% de variação no preço
    classe_abc: str
```

---

## 5. Consequências

### Positivas
- Respostas diretas a questionamentos de auditoria: "qual insumo representa a maior exposição de custo?"
- S-curve para controle de prazo-custo (earned value)
- Curva ABC por insumo habilita gestão de compras priorizada
- Agregação semanal de equipamentos habilita gestão de frota

### Negativas / Riscos
- `InsumoDetalheAtividade` requer que Skill 08 preencha `itens_detalhados` — adiciona complexidade de populamento
- A resolução do preço unitário por `insumo_id` na data de referência requer integração com o catálogo de insumos — `RepositorioInsumo` já existe mas a query é por item, não em batch

---

## 6. Questões Abertas

### Q1 — Granularidade de coeficiente temporal
A `CPU.composicao_itens[i].coeficiente` é o coeficiente por unidade de produção (ex: 0.004 h/m³ para escavadeira). O custo total depende de `quantitativo_atividade`. Mas como distribuir este custo semanalmente? Proposta: proportional à `distribuicao_semanal.qtd_executada`.

### Q2 — Insumos de custo indireto
`Indireto.funcoes` e `Indireto.equipamentos` são `list[dict]` (sem schema). A mesma lacuna de L1 existe nos indiretos. Resolver junto?

### Q3 — ABC de custo com ou sem BDI?
A curva ABC analítica deve usar custos antes do BDI (para comparar com catálogo) ou depois (para refletir o preço de venda)?  
Proposta: expor ambos — `custo_sem_bdi` e `custo_com_bdi` — com o BDI decomponível.

---

## 7. Plano de Implementação

| Fase | Entrega | Prioridade |
|------|---------|-----------|
| 1 | `InsumoDetalheAtividade` + `itens_detalhados` em `InsumoComponenteAtividade` | Alta |
| 1 | Skill 08 popula `itens_detalhados` via `EquipeDireta.funcoes` e `equipamentos` | Alta |
| 2 | `CurvaABCInsumo` + `ItemCurvaABC` como domain objects | Média |
| 2 | Skill analítica que constrói a curva a partir de `custos_atividades` | Média |
| 3 | `AgregacaoSemanal` de equipamentos (derivado de schedule + equipes) | Média |
| 3 | `SCurve` consolidada diretos + indiretos + BDI | Média |
| 4 | `InsumoSensibilidade` estendendo `CpuExposurePerfil` | Baixa |
| 5 | Export Excel: aba `CURVA.ABC` + aba `S-CURVE` | Baixa |
