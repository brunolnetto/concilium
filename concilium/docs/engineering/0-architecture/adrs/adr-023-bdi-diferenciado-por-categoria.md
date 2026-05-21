# ADR-023 — Modelo BDI Diferenciado por Categoria de Custo

**Status:** Implementado  
**Data:** 2026-05-04  
**Data Implementado:** 2026-05-04  
**Implementadores:** models/bdi.py (TabelaBdi, ComponentesBdi, IndiretoComBdi, DEFAULT_BDI_TABELA), skills/04-planejamento-bdi/skill.py (_resolve_bdi via TabelaBdi), skills/05-indiretos/skill.py (IndiretoComBdi por categoria), models/canonical.py (indiretos_com_bdi)  
**Contexto:** MendesLobo Construtora — Concilium  
**Fonte de Dados:** `rfi_catalog.xlsm` — abas `BDI`, `ENCARGOS`, `BENCHMARK_INDIRETOS` (referência abril/2026)

---

## Contexto

### Estado Atual (AS-IS)

O modelo `BdiCategorias` em `canonical.py` armazena quatro taxas como floats simples:

```python
class BdiCategorias(BaseModel):
    material:    float = 0.0
    diesel:      float = 0.0
    mao_obra:    float = 0.0
    equipamentos: float = 0.0
```

E `Venda` apenas acumula:

```python
class Venda(BaseModel):
    total_sem_bdi: float
    total_com_bdi: float
```

**Problemas críticos deste modelo:**

| ID  | Problema                                          | Impacto                                                                                    |
|-----|---------------------------------------------------|--------------------------------------------------------------------------------------------|
| B1  | Taxa única de BDI (sem decomposição)              | Impossível auditar de onde vem o percentual — AC, lucro, tributos ficam implícitos          |
| B2  | Sem BDI para custos indiretos (TOP/ADM/LAB/QSMS)  | Custos indiretos são lançados sem markup → margem sub-declarada, proposta sub-precificada   |
| B3  | Diesel misturado com EQUIPAMENTO no BDI           | Diesel tem tratamento tributário diferente (ISS não incide, risco = 0) — taxar como EQ é errado |
| B4  | Sem componente de Contingência de Risco (CR)      | Projetos que exigem CR (obras complexas, zonas remotas) não têm onde expressar este parâmetro |
| B5  | Sem validação por faixa de projeto (benchmark)    | Não há alertas quando a composição BDI diverge do histórico real da empresa                |
| B6  | Encargos sociais desconectados da base de tributos | Não está claro que % de encargos é aplicado antes do BDI, gerando risco de double-counting  |

### Evidências da Planilha de Referência

A aba **BDI** da `rfi_catalog.xlsm` (atualizada em abril/2026) discrimina **5 tipos distintos de BDI**:

#### Componentes por categoria (planilha rfi_catalog.xlsm, aba BDI)

| Componente | Sigla | BDI MO | BDI MAT | BDI SERV | BDI INDIR | BDI DIESEL |
|------------|-------|-------:|--------:|---------:|----------:|-----------:|
| Adm. Central | AC | 5,00% | 5,00% | 5,00% | 4,00% | 4,00% |
| Despesas Financeiras | DF | 1,50% | — | 1,50% | — | 0,00% |
| Garantia / Risco / Seguro | R | 1,00% | — | 1,00% | — | 0,00% |
| Lucro | L | 9,00% | 5,00% | 9,00% | 2,00% | 5,00% |
| COFINS | — | 3,00% | — | 3,00% | 3,00% | 3,00% |
| ISS | — | 5,00% | — | 5,00% | 5,00% | 5,00% |
| PIS | — | 0,65% | — | 0,65% | 0,65% | 0,65% |
| CSSL | — | 1,99% | — | 1,99% | 1,99% | 1,99% |
| IR | — | 2,74% | — | 2,74% | 2,74% | 2,74% |
| **Tributos (T)** | T | **13,38%** | 0,00% | **13,38%** | **13,38%** | **13,38%** |
| Contingência de Risco | CR | — | 0,00% | 0,00% | 0,00% | 0,00% |
| **BDI Total** | TT | **35,45%** | **5,00%** | **35,45%** | **22,47%** | **26,07%** |

> **Nota sobre BDI-MATERIAL (5%):** materiais fornecem apenas lucro (5%), sem tributos sobre
> serviço (ISS não incide na revenda de materiais) e sem despesas financeiras. Esta é a
> base do Acórdão TCU 2622/2013 para obras públicas.

#### Fórmula base (TCU — Acórdão 2622/2013)

$$
\text{BDI} = \frac{1 + AC + DF + R + CR + L}{1 - T} - 1
$$

Onde $T = \text{COFINS} + \text{ISS} + \text{PIS} + \text{CSSL} + \text{IR}$ incide sobre o **preço de venda**.

#### Encargos Sociais (aba ENCARGOS — aplicados à base de custo, antes do BDI)

| Regime | Total Encargos | Composição Principal |
|--------|---------------:|----------------------|
| Horistas (canteiro) | 177,70% | A=37,8% + B=47,8% + C=40,5% + D=19,1% + E=10,2% + F=19,2% + Judicial=3% |
| Mensalistas (adm.)  | 106,00% | A=37,8% + B=9,9% + C=40,3% + D=4,7% + E=10,2% + Judicial=3% |

> Os encargos são aplicados sobre o salário base para obter o **custo de mão de obra**,
> antes do BDI. O BDI incide sobre esse custo já com encargos.

#### Benchmark de custos indiretos (aba BENCHMARK_INDIRETOS)

| Faixa de Obra | N | Valor Médio (R$) | ADM | TOPO | LAB | QSMS | MOB | DESM | **Indireto Total** |
|---------------|---|-----------------|----:|-----:|----:|-----:|----:|-----:|-------------------:|
| ≤ R$ 10 MM    | 3 | R$ 8,5 MM       | 27,5% | 2,7% | 2,2% | 1,0% | 3,8% | 2,5% | **39,6%** |
| R$ 10–50 MM   | 5 | R$ 29,2 MM      | 20,9% | 1,4% | 0,3% | 1,7% | 3,0% | 2,0% | **29,2%** |
| > R$ 50 MM    | 1 | R$ 119 MM       | 13,4% | — | 1,8% | — | 0,9% | — | **16,1%** |

> Percentuais calculados sobre o **valor total orçado** (incluindo BDI).
> Projetos referência: Lundin, CCR, Rosh, AGIS, Bracell, BRDU, Fronter, HOC.

---

## Decisão

Refatorar o modelo de BDI de taxas opacas para um **modelo de componentes auditável**,
com 5 categorias diferenciadas, validação por benchmark histórico e rastreabilidade
total dos sub-componentes.

---

### D1 — Cinco Categorias de BDI (substituição de BdiCategorias)

```python
CategoriaBdi = Literal["MAO_OBRA", "MATERIAL", "SERVICOS", "INDIRETO", "DIESEL"]

class ComponentesBdi(BaseModel):
    """Decomposição auditável de um BDI por categoria de custo."""

    # Sub-componentes de sobrecarga (overhead)
    ac: float = Field(ge=0, description="Administração Central — % s/ custo base")
    df: float = Field(ge=0, description="Despesas Financeiras — % s/ custo base")
    r:  float = Field(ge=0, description="Garantia / Risco / Seguro — % s/ custo base")
    cr: float = Field(ge=0, description="Contingência de Risco — % s/ custo base")
    l:  float = Field(ge=0, description="Lucro — % s/ custo base")

    # Sub-componentes tributários (incidem sobre preço de venda)
    cofins: float = Field(ge=0)
    iss:    float = Field(ge=0)
    pis:    float = Field(ge=0)
    cssl:   float = Field(ge=0)
    ir:     float = Field(ge=0)

    @property
    def tributos(self) -> float:
        return round(self.cofins + self.iss + self.pis + self.cssl + self.ir, 6)

    @property
    def bdi_total(self) -> float:
        """Fórmula TCU (Acórdão 2622/2013): BDI = (1+AC+DF+R+CR+L) / (1-T) - 1."""
        numerador = 1 + self.ac + self.df + self.r + self.cr + self.l
        denominador = 1 - self.tributos
        if denominador <= 0:
            raise ValueError(f"Tributos ≥ 100%: {self.tributos:.2%}")
        return round(numerador / denominador - 1, 6)


class TabelaBdi(BaseModel):
    """Tabela de BDI para todos os tipos de custo de um projeto."""

    mao_obra:    ComponentesBdi
    material:    ComponentesBdi
    servicos:    ComponentesBdi
    indireto:    ComponentesBdi
    diesel:      ComponentesBdi
    referencia:  str = Field(description="Ex: 'rfi_catalog.xlsm abril/2026 — Minaçu'")
    data_vigencia: date
```

**Valores padrão derivados da planilha (abril/2026):**

```python
DEFAULT_BDI_TABELA = TabelaBdi(
    mao_obra  = ComponentesBdi(ac=0.050, df=0.015, r=0.010, cr=0.000, l=0.090,
                               cofins=0.030, iss=0.050, pis=0.0065, cssl=0.0199, ir=0.0274),
    material  = ComponentesBdi(ac=0.050, df=0.000, r=0.000, cr=0.000, l=0.050,
                               cofins=0.000, iss=0.000, pis=0.0000, cssl=0.0000, ir=0.0000),
    servicos  = ComponentesBdi(ac=0.050, df=0.015, r=0.010, cr=0.000, l=0.090,
                               cofins=0.030, iss=0.050, pis=0.0065, cssl=0.0199, ir=0.0274),
    indireto  = ComponentesBdi(ac=0.040, df=0.000, r=0.000, cr=0.000, l=0.020,
                               cofins=0.030, iss=0.050, pis=0.0065, cssl=0.0199, ir=0.0274),
    diesel    = ComponentesBdi(ac=0.040, df=0.000, r=0.000, cr=0.000, l=0.050,
                               cofins=0.030, iss=0.050, pis=0.0065, cssl=0.0199, ir=0.0274),
    referencia = "rfi_catalog.xlsm — abril/2026 — Minaçu/GO",
    data_vigencia = date(2026, 4, 1),
)
```

> **BDIs totais computados:** MO=35,45% | MAT=5,00% | SERV=35,45% | INDIR=22,47% | DIESEL=26,07%

> **Nota sobre parametrização por projeto:** os campos `l` (lucro) e os componentes tributários (`cofins`, `iss`, `pis`, `cssl`, `ir`) **não são fixos** nesta tabela. A `TabelaBdi` funciona como template de referência da construtora. A configuração efetiva de cada projeto é o resultado do merge entre a tabela-base e o `PerfilBdiProjeto` (§D6) — snapshot versionado coletado na criação do projeto, contendo `PerfilTributarioProjeto` + `PerfilLucroProjeto` (§D7). A função `resolver_componentes_bdi(base, perfil)` em §D7 materializa esse merge; skills 04–06 consomem o perfil como input disponível desde a inicialização.

---

### D2 — Encargos Sociais como Parâmetro Explícito (separado do BDI)

Os encargos sociais **não fazem parte do BDI**. São aplicados à base salarial para obter
o custo de mão de obra. O BDI incide sobre esse custo já com encargos.

```python
class EncargosRegime(BaseModel):
    """Regime de encargos sociais para uma categoria de trabalhador."""

    regime: Literal["horista", "mensalista"]
    percentual_total: float  # Ex: 1.777 para 177,7%

    # Grupos de componentes (para auditoria — apenas os valores totais por grupo)
    grupo_a_basicos:       float  # INSS + FGTS + Educação + SESI + SENAI + ...
    grupo_b_com_incidencia: float  # Repouso semanal + 13º + auxilios + ...
    grupo_c_sem_incidencia: float  # Rescisão + férias indenizadas + ...
    grupo_d_reincidencias:  float  # Reincidências de A sobre B e C
    grupo_e_seguros:        float  # Seguro vida + plano saúde
    grupo_f_transporte_alimentacao: float  # Vale transporte + cesta básica
    judicial:               float  # Despesas judiciais trabalhistas


class TabelaEncargos(BaseModel):
    horistas:    EncargosRegime
    mensalistas: EncargosRegime
    referencia:  str
    data_vigencia: date
```

**Valores padrão (aba ENCARGOS da planilha, abril/2026):**

| Grupo | Horistas | Mensalistas |
|-------|--------:|------------:|
| A — Básicos (INSS, FGTS, etc.) | 37,80% | 37,80% |
| B — Com incidência de A | 47,84% | 9,94% |
| C — Sem incidência de A | 40,53% | 40,30% |
| D — Reincidências | 19,07% | 4,74% |
| E — Seguros e plano saúde | 10,22% | 10,22% |
| F — Transporte e alimentação | 19,24% | 0,00% |
| Judicial | 3,00% | 3,00% |
| **Total** | **177,70%** | **106,00%** |

> **Regra de aplicação:** insumos com `tipo="MAO_OBRA"` e `fonte_preco="negociado"` 
> usam encargos de horistas; funções `categoria_sindical="CLT"` mensalistas usam
> encargos de mensalistas.

---

### D3 — Aplicação do BDI por Categoria de Custo na Composição

Cada `ComposicaoItem` de uma CPU já tem `categoria_custo` (`MAO_OBRA`, `EQUIPAMENTO`, `MATERIAL`).
A skill `04-planejamento-bdi` deve mapear para a `CategoriaBdi` correspondente:

```
CategoriaCusto → CategoriaBdi      Regra
─────────────────────────────────────────────────────────────────────────────
MAO_OBRA      → MAO_OBRA           direto
MATERIAL      → MATERIAL           direto, exceto...
MATERIAL      → DIESEL             se insumo_id referencia DIESEL-* ou similar
EQUIPAMENTO   → MAO_OBRA           custo de operação (mão de obra de equip.)
EQUIPAMENTO   → MATERIAL           custo de consumo de peças/lubrificante
EQUIPAMENTO   → DIESEL             custo de combustível (consumo_litros_hora > 0)
```

O custo de um equipamento deve ser decomposto antes do BDI:

```python
class DecomposicaoEquipamento(BaseModel):
    """Decomposição de custo de equipamento em sub-categorias para BDI correto."""

    equip_id: str
    custo_hora_total: float

    # Decomposição
    custo_mao_obra_h:  float  # operador + manutenção → BDI MAO_OBRA
    custo_diesel_h:    float  # consumo_litros_hora × preco_diesel → BDI DIESEL
    custo_material_h:  float  # lubrificantes, pneus, peças → BDI MATERIAL
    custo_capital_h:   float  # depreciação + remuneração capital → BDI MAO_OBRA ou INDIRETO
```

> Para a fase inicial, uma simplificação aceitável é aplicar BDI EQUIPAMENTO = média
> ponderada de MAO_OBRA (70%) e DIESEL (30%), a ser parametrizada por tipo de
> equipamento no catálogo.

---

### D4 — BDI sobre Custos Indiretos (Novo)

Custos indiretos (TOP, ADM, LAB, QSMS, MOB) **devem receber BDI-INDIRETO (22,47%)**
antes de compor o preço de venda. Atualmente o modelo não faz isso.

```python
class IndiretoComBdi(BaseModel):
    """Custo indireto com BDI aplicado (ADR-023 §D4)."""

    categoria: Literal["TOP", "ADM", "LAB", "QSMS", "MOB"]
    custo_sem_bdi:  float   # custo_total do IndirectoCategoria (ADR-009)
    bdi_aplicado:   float   # ComponentesBdi.bdi_total para categoria "indireto"
    custo_com_bdi:  float   # = custo_sem_bdi × (1 + bdi_aplicado)
```

**Impacto no cálculo de Venda:**

```
Venda Total = Σ (CPU_i × Qtd_i × BDI_custo_direto)   ← já existe
            + Σ (Indireto_j × (1 + BDI_INDIRETO))     ← NOVO — hoje faltando
```

---

### D5 — Perfil BDI do Projeto: Snapshot Versionado Coletado na Inicialização

A composição tributária do BDI é **project-specific**: contrato de fornecimento de material não paga ISS; municípios com ISS a 2% geram BDI diferente do default (5%); optantes do Simples Nacional têm alíquotas próprias de COFINS/PIS. Esses parâmetros não podem ser hardcoded no catálogo — são atributos do **contrato e da jurisdição fiscal do projeto**.

Não há impedimento técnico para coletar estas informações na criação do projeto: município da obra, regime tributário e tipo de contrato são conhecidos antes de qualquer skill executar. Antecipar a coleta elimina interrupções de HiL no meio da pipeline e permite que skills 04–06 consumam o perfil como input estável disponível desde o início.

Esta decisão move o **ponto de entrada HiL para `concilium project create`** (MCP: `create_project`). O perfil passa a ser pré-condição do projeto, versionado como snapshot imutável e revisável a qualquer momento durante o planejamento:

```python
class CheckboxTributo(BaseModel):
    """Flag de aplicabilidade + alíquota efetiva de um tributo para uma categoria BDI."""
    aplicavel: bool = True
    aliquota:  float  # alíquota efetiva; ignorada se aplicavel=False


class AplicacaoTributaria(BaseModel):
    """Perfil de incidência tributária para uma categoria de BDI."""
    iss:    CheckboxTributo
    cofins: CheckboxTributo
    pis:    CheckboxTributo
    cssl:   CheckboxTributo
    ir:     CheckboxTributo

    @property
    def tributos_efetivos(self) -> float:
        return round(sum(
            f.aliquota for f in [self.iss, self.cofins, self.pis, self.cssl, self.ir]
            if f.aplicavel
        ), 6)


class PerfilTributarioProjeto(BaseModel):
    """Configuração tributária por categoria BDI — confirmada em etapa HiL."""
    mao_obra:  AplicacaoTributaria
    material:  AplicacaoTributaria
    servicos:  AplicacaoTributaria
    indireto:  AplicacaoTributaria
    diesel:    AplicacaoTributaria

    municipio_obra:     str   = Field(description="Município da obra — determina alíquota ISS")
    regime_tributario:  Literal["simples_nacional", "lucro_presumido", "lucro_real"] = "lucro_presumido"

    confirmado_por: str | None = None
    confirmado_em:  datetime | None = None
    observacoes:    str | None = None
```

**Fluxo com perfil coletado na inicialização:**

```
★ HiL: project create ★  →  [00-escopo] → [01] → ... → [04-planejamento-bdi] → [05] → [06]
        ↑                                                        ↓
 PerfilBdiProjeto v1                            lê perfil_id — sem gate no meio da pipeline
 (imutável; revisão via                         skills 04–06 assumem perfil já presente
  bdi-update cria v2, v3...)
```

O formulário `bdi-review` (usado tanto na criação quanto em `concilium bdi-update`) apresenta os valores-base da `TabelaBdi` de referência pré-preenchidos:

```
╔══════════════════════════════════════════════════════════════════╗
║  REVISÃO BDI — Projeto P-042 — Terraplenagem Minaçu/GO           ║
╠══════════════════════════════════════════════════════════════════╣
║  Regime tributário: [x] Lucro Presumido  [ ] Simples  [ ] LR     ║
║  Município da obra: Minaçu/GO   ISS local: 5,00%                  ║
║                                                                   ║
║  TRIBUTOS              MO      MAT     SERV    INDIR   DIESEL     ║
║  ISS   (5,00%)        [x]     [ ]     [x]     [x]     [x]        ║
║  COFINS (3,00%)       [x]     [ ]     [x]     [x]     [x]        ║
║  PIS   (0,65%)        [x]     [ ]     [x]     [x]     [x]        ║
║  CSSL  (1,99%)        [x]     [ ]     [x]     [x]     [x]        ║
║  IR    (2,74%)        [x]     [ ]     [x]     [x]     [x]        ║
╚══════════════════════════════════════════════════════════════════╝
```

**Regras pré-configuradas por tipo de contrato** (ponto de partida do formulário):

| Tipo de Contrato | ISS | Nota |
|---|---|---|
| Serviços — empreitada global | ✓ aplica | padrão |
| Fornecimento de materiais | ✗ não aplica | base TCU 2622/2013 — ISS não incide sobre revenda |
| Fornecimento de diesel | ✓ aplica | ISS sobre serviço de abastecimento |
| Contrato global (mat+serv) | ✓ aplica sobre serviços | engenheiro deve separar a base tributável |

**Snapshot imutável por versão de perfil BDI:**

```python
class PerfilBdiProjeto(BaseModel):
    """Snapshot imutável do perfil BDI de um projeto (tributário + lucro)."""

    perfil_id:      str       # UUID v4
    version:        int       # começa em 1; incrementa a cada mudança
    content_hash:   str       # SHA-256 de (tributario + lucro) normalizado
    project_id:     str
    created_at:     datetime
    created_by:     str
    motivo_revisao: str | None = None  # obrigatório em version > 1

    tributario: PerfilTributarioProjeto
    lucro:      PerfilLucroProjeto    # vide §D7
```

Cada artefato gerado pela pipeline registra `bdi_perfil_id` em `ArtifactMeta` (análogo ao `catalog_snapshot_id` do ADR-024). Uma mudança de perfil durante o planejamento cria `PerfilBdiProjeto` v2 — a versão anterior permanece intacta para todos os artefatos que a referenciam.

**Revisão durante o planejamento:**

```bash
concilium bdi-update --project P-042 --motivo "ISS negociado para 2% com prefeitura"
```

O comando: (1) abre formulário pré-preenchido com versão atual; (2) engenheiro ajusta campos; (3) salva `PerfilBdiProjeto` (version+1, novo `content_hash`); (4) emite `BdiPerfilDiff` como artefato (§D7); (5) sinaliza checkpoint `bdi-profile-changed` — skills 04–06 do próximo run usarão a nova versão.

---

### D7 — Margem de Lucro Negociável: Padrão Empresa + Override por Projeto

O campo `l` (Lucro) em `ComponentesBdi` é **project-specific**: o engenheiro ajusta a margem por categoria dentro de limites definidos pela construtora, acomodando negociação comercial, contexto competitivo ou precificação estratégica.

```python
class PadraoLucroConstrutora(BaseModel):
    """Valores-padrão e pisos de negociação — carregado de concilium.yaml."""

    # Defaults (inicializam PerfilLucroProjeto)
    mao_obra_default:  float = 0.090   # 9,0%
    material_default:  float = 0.050   # 5,0%
    servicos_default:  float = 0.090   # 9,0%
    indireto_default:  float = 0.020   # 2,0%
    diesel_default:    float = 0.050   # 5,0%

    # Pisos de negociação (abaixo destes → aprovação obrigatória)
    mao_obra_min:  float = 0.050
    material_min:  float = 0.020
    servicos_min:  float = 0.050
    indireto_min:  float = 0.010
    diesel_min:    float = 0.020


class PerfilLucroProjeto(BaseModel):
    """Margem de lucro efetiva do projeto por categoria BDI."""
    mao_obra:  float = Field(ge=0)
    material:  float = Field(ge=0)
    servicos:  float = Field(ge=0)
    indireto:  float = Field(ge=0)
    diesel:    float = Field(ge=0)

    # Obrigatórios quando qualquer valor < PadraoLucroConstrutora.*_min
    aprovado_por:           str | None = None
    data_aprovacao:         date | None = None
    justificativa_desconto: str | None = None
```

**Configuração em `concilium.yaml`:**

```yaml
perfil_lucro_empresa:
  mao_obra_default: 0.090
  material_default: 0.050
  servicos_default: 0.090
  indireto_default: 0.020
  diesel_default:   0.050
  mao_obra_min: 0.050
  material_min: 0.020
  servicos_min: 0.050
  indireto_min: 0.010
  diesel_min:   0.020
```

**Apresentação no formulário HiL** (continuação de `bdi-review`, §D6):

```
╔══════════════════════════════════════════════════════════════════╗
║  MARGEM DE LUCRO (padrão empresa → ajustável por projeto)        ║
╠══════════════════════════════════════════════════════════════════╣
║  Categoria     Padrão    Projeto    Piso     Status              ║
║  Mão de obra   9,00%    [9,00%]    5,00%    ✓ OK                 ║
║  Material      5,00%    [5,00%]    2,00%    ✓ OK                 ║
║  Serviços      9,00%    [9,00%]    5,00%    ✓ OK                 ║
║  Indireto      2,00%    [2,00%]    1,00%    ✓ OK                 ║
║  Diesel        5,00%    [5,00%]    2,00%    ✓ OK                 ║
╠══════════════════════════════════════════════════════════════════╣
║  Aprovado por: [_______________________] (obrig. se valor < piso) ║
╚══════════════════════════════════════════════════════════════════╝
```

**Regra de aprovação:** qualquer `l` abaixo do piso correspondente em `PadraoLucroConstrutora` torna `aprovado_por` + `justificativa_desconto` obrigatórios. A validação ocorre em `concilium project create` e em qualquer `concilium bdi-update`.

**Diff entre versões de perfil:**

```python
class BdiPerfilDiff(BaseModel):
    """Diff entre versões de PerfilBdiProjeto — ArtifactKind.BDI_PERFIL_DIFF."""

    previous_perfil_id: str
    current_perfil_id:  str
    previous_version:   int
    current_version:    int
    changed:            bool
    changed_fields:     list[str]        # ex: ["material.iss.aliquota", "mao_obra.l"]
    delta_bdi:          dict[str, float] # categoria → Δ BDI total em pontos percentuais
    summary:            str              # ex: "ISS material: 5%→2%; BDI MAT: 5,00%→3,91%"
```

**Função de merge — `ComponentesBdi` efetivo do projeto:**

```python
def resolver_componentes_bdi(
    base:   TabelaBdi,
    perfil: PerfilBdiProjeto,
) -> dict[CategoriaBdi, ComponentesBdi]:
    """Merge TabelaBdi base + PerfilBdiProjeto (tributário + lucro) → ComponentesBdi efetivo."""
    resultado: dict[CategoriaBdi, ComponentesBdi] = {}
    for cat in ("mao_obra", "material", "servicos", "indireto", "diesel"):
        b         = getattr(base, cat)
        t         = getattr(perfil.tributario, cat)
        l_efetivo = getattr(perfil.lucro, cat)
        resultado[cat] = ComponentesBdi(
            ac=b.ac, df=b.df, r=b.r, cr=b.cr,
            l=l_efetivo,
            cofins=t.cofins.aliquota if t.cofins.aplicavel else 0.0,
            iss=t.iss.aliquota   if t.iss.aplicavel   else 0.0,
            pis=t.pis.aliquota   if t.pis.aplicavel   else 0.0,
            cssl=t.cssl.aliquota if t.cssl.aplicavel  else 0.0,
            ir=t.ir.aliquota     if t.ir.aplicavel     else 0.0,
        )
    return resultado
```

---

## Alternativas Consideradas

| Alternativa | Razão para Rejeição |
|---|---|
| Manter taxa flat por categoria (AS-IS) | Não auditável; BDI de indiretos não aplicado; diesel sub-tributado |
| BDI único para todo projeto | Viola Acórdão TCU 2622/2013; materiais seriam sobre-tributados |
| BDI calculado apenas na hora da proposta | Perde rastreabilidade intra-planejamento; skill 04 não teria base |
| Incorporar encargos dentro do BDI | Double-counting: encargos já estão nos salários do catálogo |

---

## Consequências

### Positivas
- **Auditabilidade total**: qualquer revisor pode rastrear de onde vem o percentual final de BDI
- **Conformidade TCU**: modelo alinhado ao Acórdão 2622/2013 e a exigências de licitações públicas
- **BDI de indiretos aplicado**: elimina sub-precificação sistêmica em TOP/ADM/LAB/QSMS/MOB
- **Benchmark integrado**: alertas automáticos quando composição diverge do histórico real da empresa
- **Diesel corretamente separado**: elimina sobre-tributação de combustível (ISS não incide)
- **Tributação por projeto**: engenheiro configura via HiL quais tributos incidem em cada categoria — contratos de fornecimento de material, municípios com ISS diferenciado e regimes especiais são acomodados sem alterar o catálogo
- **Negociação de margem com governança**: lucro é ajustável por projeto dentro de pisos definidos pela construtora; abaixo do piso exige `aprovado_por` + `justificativa_desconto` — auditável no `PerfilLucroProjeto`

### Negativas / Atenção
- **Perfil coletado na criação do projeto**: pipeline roda sem interrupção de HiL — `PerfilBdiProjeto` já existe desde `concilium project create`; em runs automatizados (CI, batch) o perfil aprovado mais recente é reutilizado automaticamente sem input interativo
- **Snapshot por versão de planejamento**: alterações ao perfil BDI durante o planejamento geram nova versão imutável + `BdiPerfilDiff` auditável — rastreabilidade análoga ao `CatalogSnapshot` (ADR-024); cada artefato referencia o `bdi_perfil_id` exato usado no run
- **Migração de dados**: `BdiCategorias` → `TabelaBdi` requer migração nos snapshots existentes
  (retrocompat: skill 04 pode calcular `ComponentesBdi` a partir de taxas legadas via `bdi_total`)
- **Decomposição de equipamentos** (§D3): requer enriquecimento do catálogo com
  `custo_mao_obra_h`, `custo_diesel_h`, `custo_material_h` — não disponível em todos os E-codes
  → **fase inicial usa simplificação 70/30** (parametrizável por tipo de equipamento)
- **n=1 para faixa >R$50MM**: benchmark estatisticamente fraco; não deve gerar bloqueio,
  apenas alerta informativo

---

## Plano de Implementação

| Fase | Escopo | Dependências |
|------|--------|-------------|
| **1** | Criar `ComponentesBdi`, `TabelaBdi`, `TabelaEncargos` em `canonical.py`; adicionar `DEFAULT_BDI_TABELA` em `config/` | ADR-001 (semantic layer) |
| **1B** | Criar `CheckboxTributo`, `AplicacaoTributaria`, `PerfilTributarioProjeto`, `PadraoLucroConstrutora`, `PerfilLucroProjeto`, `PerfilBdiProjeto`, `BdiPerfilDiff` em `canonical.py`; seção `perfil_lucro_empresa` em `concilium.yaml`; `ArtifactKind.BDI_PERFIL` + `ArtifactKind.BDI_PERFIL_DIFF` no enum; `resolver_componentes_bdi(base, perfil)` em `models/bdi_resolver.py` | §D6, §D7 (este ADR); Fase 1 |
| **1C** | Integrar `bdi-review` em `concilium project create` e MCP `create_project`; formulário pré-preenchido com `TabelaBdi` + `PadraoLucroConstrutora`; salvar `PerfilBdiProjeto` v1 na criação; `concilium bdi-update` para revisão com motivo; diff automático `BdiPerfilDiff` a cada mudança; `ArtifactMeta.bdi_perfil_id`; skills 04–06 lêem `PerfilBdiProjeto` como input (sem gate de interrupção na pipeline) | ADR-022, ADR-024 (padrão snapshot); Fase 1B |
| **2** | Refatorar skill `04-planejamento-bdi` para chamar `resolver_componentes_bdi(base, perfil)` e emitir `preco_unitario_com_bdi` decomposto por categoria | ADR-010 (cost breakdown); Fase 1C |
| **3** | Adicionar `IndiretoComBdi` ao output da skill `05-indiretos`; incluir em `Venda.total_com_bdi` | ADR-009 (indiretos) |
| **4** | Implementar validação `BenchmarkIndiretosFaixa` em skill `06-consolidar` | ADR-020 (criticidade) |
| **5** | Enriquecer catálogo E-codes com `custo_mao_obra_h / custo_diesel_h / custo_material_h` | ADR-017 (catalog lifecycle) |

---

## Referências

- **Planilha:** `rfi_catalog.xlsm` — abas `BDI`, `ENCARGOS`, `BENCHMARK_INDIRETOS` (abril/2026)
- **TCU:** Acórdão 2622/2013 — Metodologia de cálculo de BDI diferenciado para obras públicas
- **ADR-009:** Indirect Costs as First-Class Models (TOP/ADM/LAB/QSMS/MOB)
- **ADR-010:** Activity Cost Breakdown & Resource Allocation
- **ADR-017:** Catalog Lifecycle Management
- **canonical.py:** `BdiCategorias`, `Planejamento`, `Venda`, `Resultado`

## Definition of Done

- [x] `ComponentesBdi` model: all sub-components (`ac`, `df`, `r`, `cr`, `l`, `cofins`, `iss`, `pis`, `cssl`, `ir`) with TCU formula in `bdi_total` property (Acórdão 2622/2013)
- [x] `TabelaBdi` model with 5 categories: `mao_obra`, `material`, `servicos`, `indireto`, `diesel`
- [x] `TabelaEncargos` model: `EncargosRegime` with `horistas` (177,70%) and `mensalistas` (106,00%) from `rfi_catalog.xlsm`
- [x] `DEFAULT_BDI_TABELA` populated from `rfi_catalog.xlsm` (abril/2026): MO=35,45% | MAT=5,00% | SERV=35,45% | INDIR=22,47% | DIESEL=26,07%
- [x] `IndiretoComBdi` model: `categoria`, `custo_sem_bdi`, `bdi_aplicado`, `custo_com_bdi`
- [x] `indiretos_com_bdi` field in `CanonicalModel`
- [x] Skill `04-planejamento-bdi` uses `TabelaBdi` via `_resolve_bdi` (replaces flat-rate `BdiCategorias`)
- [x] Skill `05-indiretos` applies `IndiretoComBdi` per category (TOP, ADM, LAB, QSMS, MOB)
- [x] `PerfilTributarioProjeto` / `CheckboxTributo` / `AplicacaoTributaria` models (Phase 1B §D6)
- [x] `PerfilLucroProjeto` / `PadraoLucroConstrutora` with negotiation floors (Phase 1B §D7)
- [x] `PerfilBdiProjeto` snapshot (versioned, immutable, with `content_hash`) (Phase 1B)
- [x] `resolver_componentes_bdi(base, perfil)` in `models/bdi_resolver.py` (Phase 1B)
- [x] `bdi-review` HiL form integrated in `concilium project create` and MCP `create_project` (Phase 1C)
- [x] `BdiPerfilDiff` artifact and `concilium bdi-update` command (Phase 1C)
- [x] Equipment cost decomposition enrichment in catalog (`custo_mao_obra_h`, `custo_diesel_h`, `custo_material_h`) (Phase 5 §D3)
