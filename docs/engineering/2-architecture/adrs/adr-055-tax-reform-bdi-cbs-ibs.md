# ADR-055: Modelagem da Reforma Tributária CBS/IBS no Simulador de BDI

**Status:** Implementado  
**Data:** 2026-05-15  
**Autor:** Engenheiro Sênior  
**Relacionado:** ADR-023 (BDI Diferenciado por Categoria), ADR-028 (Controle Variável Balanço × Margem), ADR-038 (Catálogo Regionalizado + BDI por Jurisdição)

---

## 1. Contexto

### 1.1 A Reforma Tributária Brasileira (EC 132/2023)

A Emenda Constitucional 132/2023 institui o sistema dual CBS/IBS em substituição aos tributos atuais:

| Tributo extinto | Substituído por |
|-----------------|-----------------|
| PIS + COFINS (federal) | CBS — Contribuição sobre Bens e Serviços |
| ICMS (estadual) + ISS (municipal) | IBS — Imposto sobre Bens e Serviços |
| CSSL + IR | Mantidos (não substituídos) |

**Cronograma de transição relevante para construção:**
- **2026:** Documentos eletrônicos já devem destacar CBS/IBS separadamente
- **2026–2032:** Fase de transição gradual com coexistência dos regimes
- **2033+:** Regime pleno CBS/IBS

**Mecanismo central:** Ambos CBS e IBS são **não-cumulativos com crédito amplo** — o construtor credita o imposto pago nos insumos e paga apenas o diferencial. Isso é fundamentalmente diferente do PIS/COFINS cumulativo do regime atual de obras.

**CIB e apuração por empreendimento:** A regulamentação vincula a construção civil à identificação via CIB (Código de Identificação do Bem Imóvel) e à apuração por empreendimento — o que é compatível com o isolamento de projetos já existente no Concilium.

### 1.2 Modelo BDI atual no Concilium

O modelo vigente (implementado em ADR-023) usa a fórmula do Acórdão TCU 2622/2013:

```
BDI = ((1 + AC + DF + R + CR + L) / (1 - T)) − 1
```

Onde `T = COFINS + ISS + PIS + CSSL + IR` — uma soma estática de alíquotas brutas.

**Estrutura por categoria de custo (`ComponentesBdi`):**
```python
# Sobrecarga (aplicada sobre custo):
ac: float   # Administração Central
df: float   # Despesas Financeiras
r: float    # Garantia/Risco/Seguro
cr: float   # Contingência
l: float    # Lucro/Margem

# Tributos (aplicados sobre preço de venda):
cofins, iss, pis, cssl, ir: float
```

**DEFAULT_BDI_TABELA (vigência abril/2026):**
- `mao_obra`: 35,45% | `material`: 5,00% | `indireto`: 22,47% | `diesel`: 26,07%

**Fluxo de cálculo:**
```
Skill 06: resolve bdi → aplica por categoria de custo → Planejamento{bdi, preco_com_bdi}
Skill 08: agrega planejamento + aplica bdi["indireto"] sobre indiretos → Resultado.margem_pct
```

### 1.3 O Problema Central

O campo `T = COFINS + ISS + PIS + CSSL + IR` na fórmula TCU modela tributos como **custo irrecuperável** que deve ser repassado integralmente ao preço. Isso é correto para o regime cumulativo atual.

Sob CBS/IBS, **parte substancial do tributo bruto é recuperável via crédito**:

```
T_efetivo = T_bruto × (1 − ratio_credito)
```

Manter `T = alíquota_bruta` no regime CBS/IBS implica:
1. **Superestimar a carga tributária** — o BDI calculado será maior que o necessário
2. **Perder visibilidade sobre o crédito** — não é possível comparar cenários de eficiência creditória
3. **Ignorar o custo de carregamento** — créditos chegam com atraso (30–60 dias); esse prazo tem custo financeiro
4. **Tornar o `PerfilBdiProjeto` obsoleto** — ele armazena alíquotas puras, não perfis de crédito

---

## 2. Análise de Relevância para o Concilium

Esta seção delimita o escopo: o Concilium é um **simulador de planejamento**, não um sistema fiscal (ERP, SPED). A seguinte tabela distingue o que é relevante do que é superdimensionado:

| Funcionalidade | Relevante para Concilium? | Motivo |
|---------------|--------------------------|--------|
| Alíquotas CBS/IBS por tipo de custo | **Sim** | Impacta o BDI diretamente |
| Ratio de crédito recuperável por categoria | **Sim** | Define T_efetivo na fórmula |
| Custo financeiro do lag de recuperação | **Sim** | Entra no componente `df` (Despesas Financeiras) |
| Versão/vigência da regra tributária | **Sim** | Regime 2026 ≠ regime 2033 |
| Split payment (retenção na fonte) | **Sim** | Altera o cash flow do projeto |
| Apuração mensal real com SPED | **Não** | ERP/fiscal — fora do escopo |
| Integração com registros fiscais (CIB) | **Não** | Gestão fiscal — fora do escopo |
| Workflow de aprovação de crédito | **Não** | Processo fiscal — fora do escopo |
| Cálculo de IR/CSLL em regime CBS/IBS | **Parcialmente** | Mantidos, mas base de cálculo muda |

**Invariante de domínio:** O Concilium modela o **impacto tributário sobre o preço de proposta** — não realiza a apuração. O resultado é um cenário de precificação, não uma obrigação fiscal.

---

## 3. Decisão

### D1 — `TaxRegimeVersion` como valor-objeto versionado

Introduzir `TaxRegimeVersion` como enum estrito que governa qual conjunto de alíquotas e mecanismos se aplica:

```python
class TaxRegimeVersion(str, Enum):
    PRE_REFORMA = "pre_reforma"          # Regime atual: PIS/COFINS/ISS cumulativo
    TRANSICAO = "transicao"              # Coexistência — percentuais escalonados
    PLENO_CBS_IBS = "pleno_cbs_ibs"      # 2033+: regime completo
```

Cada `TaxRegimeVersion` carrega suas alíquotas canônicas. O `PerfilBdiProjeto` referencia a versão, não repete os valores.

### D2 — Separação de tributos brutos e crédito recuperável em `ComponentesBdi`

Substituir o conjunto flat de campos tributários por uma estrutura que separa bruto de líquido:

```python
class ComponentesTributarios(BaseModel):
    """Tributos no regime CBS/IBS — separação de bruto e crédito."""
    model_config = ConfigDict(frozen=True)

    regime_version: TaxRegimeVersion

    # Alíquotas brutas (incidência sobre preço de venda)
    cbs_rate: float = 0.0       # CBS federal — substitui PIS+COFINS
    ibs_rate: float = 0.0       # IBS estadual+municipal — substitui ISS+ICMS
    cssl: float = 0.0           # Mantido
    ir: float = 0.0             # Mantido

    # Perfil de crédito (fração recuperável dos tributos sobre insumos)
    credit_ratio: float = 0.0   # ∈ [0, 1] — 0 = regime cumulativo puro
    # credit_ratio depende de: compliance dos fornecedores, tipo do insumo,
    # e regime de apuração do projeto (simples, presumido, real)

    # Custo de carregamento do crédito (entra em df, não em T_efetivo)
    credit_lag_semanas: int = 0  # Semanas até recuperação do crédito
    # Traduzido em custo financeiro: lag_semanas/52 × taxa_anual_df

    # Split payment
    split_payment: bool = False  # Retenção na fonte pelo tomador

    @property
    def tributos_brutos(self) -> float:
        """Alíquota bruta total (T na fórmula TCU)."""
        return self.cbs_rate + self.ibs_rate + self.cssl + self.ir

    @property
    def tributos_efetivos(self) -> float:
        """Carga líquida após crédito — substitui T na fórmula BDI."""
        cbs_ibs_bruto = self.cbs_rate + self.ibs_rate
        cbs_ibs_liquido = cbs_ibs_bruto * (1.0 - self.credit_ratio)
        return cbs_ibs_liquido + self.cssl + self.ir
```

**Impacto na fórmula TCU:**
```
# Regime atual (pre_reforma):
BDI = ((1 + AC + DF + R + CR + L) / (1 - COFINS - ISS - PIS - CSSL - IR)) − 1

# Regime CBS/IBS:
BDI = ((1 + AC + DF + R + CR + L) / (1 - tributos_efetivos)) − 1
       onde tributos_efetivos = (CBS+IBS)×(1-credit_ratio) + CSSL + IR
```

O campo `df` (Despesas Financeiras) absorve o custo de carregamento do crédito:

```
df_efetivo = df_base + (tributos_brutos × credit_ratio × credit_lag_semanas/52 × taxa_financ_anual)
```

### D3 — Backward compatibility via regime_version em `PerfilBdiProjeto`

`PerfilBdiProjeto` recebe um campo `regime_version: TaxRegimeVersion = TaxRegimeVersion.PRE_REFORMA`. Projetos sem o campo explícito continuam usando os campos atuais (`cofins`, `iss`, `pis`, `cssl`, `ir`) com `credit_ratio = 0.0`.

**Priority chain em Skill 06/08 (sem ruptura):**
```
1. inputs["bdi_aplicado"] dict explícito    ← override manual (continua funcionando)
2. inputs["tabela_bdi"] com ComponentesTributarios  ← novo path CBS/IBS
3. inputs["bdi_perfil"] com PerfilBdiProjeto.regime_version  ← perfil de projeto
4. DEFAULT_BDI_TABELA (PRE_REFORMA)         ← fallback inalterado
```

### D4 — `TaxSimulationScenario` como value-object de entrada ao `BDIComposer`

O `BDIComposer` (serviço de domínio) recebe um `TaxSimulationScenario` e produz os `ComponentesTributarios` finais por categoria:

```python
@dataclass(frozen=True)
class TaxSimulationScenario:
    """Cenário de tributação para simulação de BDI (ADR-055).
    
    Modela o IMPACTO da reforma no preço de proposta — não realiza apuração real.
    Todos os campos são premissas do planejador, não obrigações fiscais.
    """
    regime_version: TaxRegimeVersion

    # Alíquotas brutas combinadas CBS+IBS (referência: ~26,5% em regime pleno)
    cbs_ibs_combined_rate: float   # ex: 0.265 em regime pleno

    # Perfil de crédito — premissa do planejador, varia por:
    # - compliance dos fornecedores (scoring do projeto)
    # - tipo de insumo (mão de obra: 0%, material: ~70-85%, serviço: ~60-80%)
    credit_ratio_mao_obra: float = 0.0     # MO: regime cumulativo — sem crédito
    credit_ratio_material: float = 0.75    # Materiais: alta recuperabilidade
    credit_ratio_servicos: float = 0.65    # Subcontratados: depende do compliance
    credit_ratio_diesel: float = 0.70      # Combustível: típico ~70%

    # Timing — custo de carregamento
    credit_lag_semanas: int = 6            # Semanas até recuperação
    taxa_financ_anual: float = 0.12        # CDI/taxa de desconto da empresa

    # Split payment (obras públicas — retenção pelo ente pagador)
    split_payment: bool = False

    # CSSL + IR — mantidos, sem crédito CBS/IBS
    cssl_rate: float = 0.09
    ir_rate: float = 0.15                  # regime presumido

    def tributos_efetivos_por_categoria(self) -> dict[str, float]:
        """Carga líquida por categoria de custo para uso na fórmula BDI."""
        def net(bruto: float, ratio: float) -> float:
            return bruto * (1.0 - ratio) + self.cssl_rate + self.ir_rate

        return {
            "mao_obra":    net(self.cbs_ibs_combined_rate, self.credit_ratio_mao_obra),
            "material":    net(self.cbs_ibs_combined_rate, self.credit_ratio_material),
            "servicos":    net(self.cbs_ibs_combined_rate, self.credit_ratio_servicos),
            "diesel":      net(self.cbs_ibs_combined_rate, self.credit_ratio_diesel),
            "indireto":    net(self.cbs_ibs_combined_rate, self.credit_ratio_servicos),
        }

    def custo_carregamento_df(self, bruto_categoria: float, credit_ratio: float) -> float:
        """Adicional de df pelo lag de recuperação do crédito."""
        credito_recuperavel = bruto_categoria * credit_ratio
        return credito_recuperavel * (self.credit_lag_semanas / 52) * self.taxa_financ_anual
```

### D5 — Cenários pré-definidos para os três regimes

O sistema expõe cenários canônicos que o planejador pode escolher como ponto de partida:

```python
CENARIOS_TRIBUTARIOS: dict[TaxRegimeVersion, TaxSimulationScenario] = {
    TaxRegimeVersion.PRE_REFORMA: TaxSimulationScenario(
        regime_version=TaxRegimeVersion.PRE_REFORMA,
        cbs_ibs_combined_rate=0.0,   # PIS/COFINS/ISS tratados no modelo legado
        credit_ratio_mao_obra=0.0,
        credit_ratio_material=0.0,
        credit_ratio_servicos=0.0,
        credit_ratio_diesel=0.0,
        credit_lag_semanas=0,
    ),
    TaxRegimeVersion.TRANSICAO: TaxSimulationScenario(
        regime_version=TaxRegimeVersion.TRANSICAO,
        cbs_ibs_combined_rate=0.013,  # ~5% do regime pleno (1,7% CBS + 0,1% IBS em 2026)
        credit_ratio_material=0.75,
        credit_ratio_servicos=0.60,
        credit_ratio_diesel=0.65,
        credit_lag_semanas=6,
        split_payment=False,          # Ainda não implementado em 2026
    ),
    TaxRegimeVersion.PLENO_CBS_IBS: TaxSimulationScenario(
        regime_version=TaxRegimeVersion.PLENO_CBS_IBS,
        cbs_ibs_combined_rate=0.265,  # Estimativa base — varia por jurisdição
        credit_ratio_mao_obra=0.0,    # MO: não gera crédito CBS/IBS
        credit_ratio_material=0.80,
        credit_ratio_servicos=0.70,
        credit_ratio_diesel=0.72,
        credit_lag_semanas=4,
        split_payment=True,           # Obras públicas: retenção obrigatória
    ),
}
```

---

## 4. Impacto nos Skills Existentes

### Skill 06 — Precificação Unitária

**Mudança:** `_resolve_bdi` aceita `TaxSimulationScenario` como novo path. Se presente no `inputs["tax_scenario"]`, deriva `ComponentesTributarios` por categoria; senão, mantém o path legado com os campos flat de alíquota.

**Sem mudança:** A saída continua sendo `{"mao_obra": float, "material": float, "diesel": float, "equipamentos": float}` — o campo de tributos se torna "carga efetiva" em vez de "alíquota bruta".

### Skill 08 — Consolidação Financeira

**Mudança:** `_resolve_bdi_rates` inclui `"indireto"` derivado do `TaxSimulationScenario`. A adição de `df_efetivo` (custo de carregamento do crédito) ao componente `df` de cada categoria.

**Sem mudança:** Fórmula de margem e `Resultado` inalterados — o resultado final continua sendo `margem_pct` e `venda.total_com_bdi`.

### UI — `render_bdi_editor`

**Adição:** Dropdown de regime tributário e campos de credit_ratio por categoria. Valores padrão derivados do cenário canônico selecionado. Os campos existentes de BDI (MO, Equip., Material, Diesel, Indireto) continuam visíveis como resultado derivado — não como entrada direta quando o modo CBS/IBS estiver ativo.

**Modo "Simples" (legado):** Mantém edição direta dos campos flat — compatível com quem usa o modelo atual.

---

## 5. O Que Não Muda

1. **Fórmula TCU** — a estrutura `((1 + overhead) / (1 - T)) − 1` é mantida; apenas o `T` passa a ser `T_efetivo = tributos_efetivos()`
2. **`PerfilBdiProjeto` como mecanismo de versão** — continua sendo o snapshot imutável por projeto
3. **`DEFAULT_BDI_TABELA`** — continua funcionando como fallback para o regime pré-reforma
4. **Encargos sociais** — permanecem pré-BDI (177,70% horistas, 106% mensalistas), não são afetados pelo CBS/IBS
5. **Separação por categoria de custo** (mao_obra, material, diesel, servicos, indireto) — a granularidade existente é adequada para modelar perfis de crédito diferenciados

---

## 6. Configuração por Categoria — Justificativa

A reforma tributária tem impacto **diferenciado por categoria de custo**:

| Categoria | Crédito CBS/IBS? | Justificativa |
|-----------|-----------------|---------------|
| Mão de Obra | **Não** | MO é remuneração, não incide CBS/IBS |
| Material | **Sim (~75-85%)** | Alta recuperabilidade; compliance do fornecedor importa |
| Serviços (subcontratados) | **Sim (~60-75%)** | Depende do regime do subcontratado |
| Diesel/Combustível | **Sim (~65-72%)** | Insumo direto; redução de alíquota prevista |
| Indiretos | **Parcial (~40-60%)** | Mistura de serviços e materiais |

O modelo existente já separa essas categorias — isso é uma vantagem arquitetural do ADR-023 que se preserva.

---

## 7. Questões Abertas

### Q1 — Alíquota CBS/IBS efetiva por jurisdição para obras
A regulamentação vincula IBS a estados e municípios com alíquotas próprias. A alíquota combinada varia por localidade. O Concilium já tem `ContextoObra` e jurisdição (ADR-038) — a questão é se e quando os dados por jurisdição estarão disponíveis para parametrização.

**Resolução proposta:** `CENARIOS_TRIBUTARIOS` são nacionais por padrão; o `PerfilBdiProjeto` pode sobrescrever `ibs_rate` para projetos com jurisdição específica conhecida.

### Q2 — Crédito de MO indireta (gestão, supervisão)
A reforma pode permitir crédito parcial sobre serviços de gestão e supervisão (subcontratados especializados). A distinção entre MO direta (sem crédito) e serviços de gestão subcontratados (com crédito) requer classificação adicional no EAP.

**Resolução proposta:** Manter `credit_ratio_mao_obra = 0.0` como conservador. Adicionar `credit_ratio_servicos_gestao: float` ao `TaxSimulationScenario` quando a regulamentação específica estiver clara.

### Q3 — Split payment e fluxo de caixa
O split payment não altera o BDI (carga tributária total é a mesma), mas altera o fluxo de caixa — o construtor recebe o preço líquido e o tomador recolhe o imposto diretamente. O Concilium não modela fluxo de caixa de recebíveis ainda.

**Resolução proposta:** O flag `split_payment: bool` é persistido no cenário e exposto nos relatórios como aviso, sem impacto no cálculo de margem. Impacto de cash flow fica para ADR futuro de fluxo de caixa.

### Q4 — Período de transição: coexistência de regimes
De 2026 a 2032, obra que inicia sob regime antigo pode terminar sob regime CBS/IBS. Projetos multi-ano precisarão de alíquotas ponderadas por período.

**Resolução proposta:** Por enquanto, o cenário de tributação é único por `SimulationRun`. Projetos multi-ano usam o cenário da data de referência do orçamento. A resolução completa (ponderação por período) é trabalho futuro.

---

## 8. Consequências

### Positivas
- BDI gerado com CBS/IBS reflete carga líquida real — não superestima a tributação
- Comparação de cenários de crédito via `ScenarioComparator` existente
- Compatibilidade com a obrigação de destacar CBS/IBS em documentos eletrônicos (já prevista para 2026)
- Modelo extensível: quando regulamentação específica de obras ficar clara, apenas `TaxSimulationScenario` precisa de novos campos
- Backward compatibility total — projetos existentes não são afetados

### Negativas / Riscos
- Os `credit_ratio` por categoria são **premissas do planejador**, não valores auditados. Precisam de nota explicativa nos relatórios
- As alíquotas combinadas CBS/IBS (~26,5%) ainda não são definitivas para construção civil — a regulamentação de 2026 continua em edição
- A distinção entre regimes durante a transição (2026–2032) adiciona complexidade que será gerenciada via `TaxRegimeVersion`

---

## 9. Plano de Implementação

| Fase | Entregas | Prioridade |
|------|----------|-----------|
| **1** | `TaxRegimeVersion` enum, `ComponentesTributarios`, `TaxSimulationScenario` — modelos de domínio | Alta |
| **1** | `CENARIOS_TRIBUTARIOS` pré-definidos | Alta |
| **1** | Atualização de `PerfilBdiProjeto` com `regime_version` | Alta |
| **2** | Integração em Skill 06: novo path `inputs["tax_scenario"]` | Alta |
| **2** | Integração em Skill 08: `df_efetivo` com custo de carregamento | Média |
| **3** | UI: dropdown de regime + campos de credit_ratio por categoria | Média |
| **3** | Cenário de comparação pré-reforma vs. CBS/IBS no tab Comparação | Média |
| **Futuro** | ~~Alíquotas por jurisdição~~ — UF corrigido em 2026-07-16 (ver nota de implementação); granularidade municipal segue pendente | Baixa |
| **Futuro** | Fluxo de caixa com split payment | Baixa |

## Definition of Done

### Fase 1 ✅
- [x] `TaxRegimeVersion` enum (3 valores) em `domain/models/bdi.py`
- [x] `TaxSimulationScenario` frozen dataclass com `tributos_efetivos_por_categoria()`, `custo_carregamento_df()`, `to_dict()`, `from_dict()`
- [x] `CENARIOS_TRIBUTARIOS` com 3 cenários canônicos (PRE_REFORMA, TRANSICAO, PLENO_CBS_IBS)
- [x] `resolver_bdi_cbs_ibs()` — noop em PRE_REFORMA; substitui tributos e df em CBS/IBS
- [x] `PerfilBdiProjeto.regime_version: TaxRegimeVersion = PRE_REFORMA`
- [x] 24 testes unitários cobrindo: imutabilidade, round-trip, fórmula T_efetivo, zero/full/partial credit, custo carregamento, backward compat

### Fase 2 ✅ (corrigido — ver nota de implementação abaixo)
- [x] Skill 06 (precificação): path `inputs["tax_scenario"]` com `VAL-BDI-REGIME`
- [x] Skill 08 (consolidação): path `inputs["tax_scenario"]` com `VAL-CONSOL-BDI-REGIME`
- [x] Ambos com fallback gracioso para path legado quando `tax_scenario` inválido
- [x] Pipeline passes 100% dos testes sem alteração (backward compat)

> **Correção (2026-07-16):** o checkbox de Skill 06 acima estava marcado como feito desde a
> entrega original da Fase 2, mas era **falso** — `_bdi_regime.py` (com `_rb_try_tax_scenario`)
> foi escrito e testado isoladamente, porém nunca importado/chamado por
> `_precificacao/skill.py::_resolve_bdi`. Só o estágio de consolidação (Skill 08) honrava
> `inputs["tax_scenario"]` de fato. Nenhum teste de integração exercitava
> `run_resultado_financeiro`/`run_precificacao_unitaria` com `tax_scenario` — os 24 testes de
> `test_adr055_tax_reform_bdi.py` cobriam só a lógica de domínio isolada, por isso o gap não
> foi pego antes. Ver seção "Nota de implementação — correção de wiring" no fim deste documento.

### Fase 3 ✅ (UI)
- [x] `render_bdi_editor` com dropdown de regime tributário
- [x] Modo Legado (PRE_REFORMA): comportamento original preservado
- [x] Modo CBS/IBS: slider CBS+IBS bruto, inputs de credit_ratio por categoria, expander de parâmetros avançados (lag, taxa, split_payment)
- [x] Preview de BDI derivado calculado localmente (sem API call)
- [x] Salva `tax_scenario` nos overrides dos skills 06 e 08
- [x] Aviso de split_payment quando ativo

## Nota de implementação — correção de wiring (2026-07-16)

Durante a investigação de um item "em aberto" do deck técnico (IBS varia por jurisdição —
hoje resolvemos só por UF), duas lacunas reais foram encontradas e corrigidas nesta mesma
entrega, além do achado descrito na correção da Fase 2 acima:

1. **Path CBS/IBS órfão em Skill 06 (precificação).** `_bdi_regime.py::_rb_try_tax_scenario`
   existia, com testes unitários próprios, mas não tinha nenhum call site fora do próprio
   arquivo. Corrigido conectando-o a `_precificacao/skill.py::_resolve_bdi`, na mesma posição
   de precedência já usada pela consolidação (`bdi_aplicado` > `tax_scenario` > `tabela_bdi` >
   ... > `DEFAULT_BDI_TABELA`).

2. **Jurisdição resolvida (UF) nunca influenciava o BDI calculado.** `Escopo.jurisdicao_id`
   já resolvia `AliquotasBdi` (ISS/PIS/COFINS/CPRB) desde antes desta entrega, mas o único
   consumidor (`_resolve_tributario`, `presentation/mcp/tools/spec.py`) só populava um dict
   de metadado (`regime_tributario`) — nunca lido de volta pela fórmula TCU de BDI. Corrigido
   com um novo passo de precedência (`resolver_bdi_jurisdicao`, `domain/models/financial/bdi/
   _profiles.py`), inserido em ambos os estágios (precificação e consolidação) logo antes do
   fallback final em `DEFAULT_BDI_TABELA`, e um novo input `inputs["aliquotas_bdi_jurisdicao"]`
   resolvido automaticamente pelo runtime (`InputsMixin._apply_defaults_tributos_bdi`) a partir
   da jurisdição do escopo — sem plumbing nova, reaproveitando o mesmo espalhamento de
   `escopo_meta` já usado pelo estoque de consumíveis (ADR-128 F5).

   `resolver_bdi_jurisdicao` só sobrescreve ISS/PIS/COFINS numa categoria quando a `TabelaBdi`
   base já declara esse tributo > 0 — a jurisdição muda a *alíquota*, nunca decide *se* o
   tributo se aplica à categoria (material/diesel continuam sem ISS, por serem mercadoria e
   não serviço — distinção categórica do ADR-023, preservada). `AliquotasBdi.CPRB`
   deliberadamente não entra neste passo: não é campo de `ComponentesBdi`; CPRB é desoneração
   de encargos sociais sobre folha de pagamento, já wired separadamente via
   `InputsMixin._apply_defaults_encargos` (mesma família de `motor_encargos_sociais`).

3. **Regex de código de jurisdição desatualizado.** `Jurisdicao.codigo` e
   `JurisdicaoVersionada.id` não aceitavam o formato hifenizado (`BR-CE`, `BR-SP`) realmente
   usado pelos 27 arquivos de `config/jurisdicoes/`. Corrigido para aceitar exatamente esse
   formato (UF de 2 letras, com prefixo `BR-` opcional).

**O que isto não é:** granularidade municipal de IBS/ISS (destino por município, não só por
UF) e modelagem de fluxo de caixa de split payment seguem **fora de escopo**, deliberadamente
— seriam mudanças de modelo de dados mais profundas (nova entidade de jurisdição municipal,
herdando de `BR-{UF}`) e não bugs de wiring como os três itens acima. `ConfigMixin.
load_jurisdicao` já suporta cadeias de herança arbitrárias via `parent_id` (mecanismo
genérico, sem lógica específica de UF), então uma extensão futura para município não exigiria
mudança nesse mecanismo — apenas nos dados de configuração e, possivelmente, em como o
`Escopo` referencia a jurisdição mais granular.
