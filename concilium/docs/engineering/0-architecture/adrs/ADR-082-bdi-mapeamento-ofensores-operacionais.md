# ADR-082 — Painel de Ajuste de Ponto de Equilíbrio: Ofensores de Produtividade, Levers de Ação e Cobertura BDI

**Status:** 🔴 Aceito  
**Data:** 2026-05-28  
**Contexto:** MendesLobo Construtora — Concilium  
**Dependências:** ADR-040, ADR-053, ADR-060, ADR-074, ADR-076, NEP-032

---

## Contexto

### Problema

**P1.** O `ponto_equilibrio` por item EAP já computa `delta = custo_venda_cpu − custo_operacional_real` e
decompõe em 3 gaps (`gap_escala_abs`, `gap_praticabilidade_abs`, `gap_pool_overhead`), mas o modelo não
informa *quais ações concretas podem fechar cada gap* nem qual seria o impacto monetário de cada ação
na margem do contrato. O stakeholder recebe um diagnóstico sem mapa de ação priorizado.

**P2.** O PU_direto é calculado por NEP-032 usando `valor_horario` (produtividade ideal da CPU). Desvios
do cenário-base — chamados **ofensores de produtividade** — não estão embutidos no PU_direto e só são
cobertos pelo componente **R (Risco)** do BDI. Não há estrutura que vincule os gaps do `ponto_equilibrio`
aos ofensores específicos que os causaram, nem ao campo CPU afetado.

**P3.** O BDI declarado (`overhead_r`) não é verificado quanto à suficiência: não há checagem de que
`R × PU_direto ≥ Σ P(ofensor_i) × ΔPU_max_i`. Um R subdimensionado é invisível até o fechamento
da obra, quando a cobertura já foi consumida.

---

## Decisão

**D1. Formalizar o modelo de ofensor de produtividade.** Cada fator `f` com eficiência relativa
`η_f < 1` gera um custo descoberto por unidade produzida:

$$\eta_f = \frac{\text{valor\_horario\_efetivo}_f}{\text{valor\_horario\_CPU}}, \quad
\Delta PU_f = PU_{\text{direto}} \times \left(\frac{1}{\eta_f} - 1\right)$$

O único componente do BDI que cobre esses desvios é **R (Risco)**. Os demais (AC, DF, L, T) são
determinísticos e não cobrem variância de campo. A verificação de suficiência deve constar no
`memorial_calculo_bdi` gerado pela skill-08:

$$R \times PU_{\text{direto}} \geq \sum_i P(\text{ofensor}_i) \times \Delta PU_{\text{max},i}$$

**D2. Criar a entidade `LeverEquilibrio`** no modelo de domínio (`canonical.py`). Cada lever
representa uma ação operacional ou contratual cujo impacto monetário é calculado diretamente dos
campos já existentes no `PontoEquilibrio`, sem novos inputs externos:

```python
class LeverEquilibrio(BaseModel):
    id: str                        # identificador canônico do lever
    tipo: Literal["custo", "preco"]
    descricao: str
    delta_margin: float            # R$ — positivo = melhoria de margem
    delta_margin_pct: float        # fração de custo_venda_cpu
    viavel: bool                   # False quando gap já é ≤ 0 (lever sem efeito)
    restricoes: list[str]          # condições de aplicação / caveats
```

**D3. Computar 4 levers canônicos** por item EAP no final de `_build_pe_for_equipe()` (skill-08):

| ID | Tipo | Fonte no PE | Fórmula |
|---|---|---|---|
| `fechar_gap_escala` | custo | `gap_escala_abs` | ΔMargin = `gap_escala_abs`; viavel se `n_equipes_efetivo > 1.05` |
| `fechar_gap_praticabilidade` | custo | `gap_praticabilidade_abs` | ΔMargin = `gap_praticabilidade_abs`; viavel se > 0 |
| `fechar_gap_pool` | custo | `gap_pool_overhead` | ΔMargin = `gap_pool_overhead`; viavel se > 0 |
| `revisao_bdi_minima` | preco | `delta`, `ajuste_minimo_pct` | ΔMargin = `−delta`; viavel quando `delta < 0` |

**D4. Adicionar `levers_equilibrio: list[LeverEquilibrio]`** ao modelo `PontoEquilibrio` com
`default_factory=list` para retrocompatibilidade com canônicos anteriores a este ADR.

**D5. Gerar chart `painel_equilibrio.png`** — tornado chart horizontal agregado (Σ por lever type
sobre todos os itens EAP underwater) com:

- Barra horizontal por lever: ΔMargin total agregado em R$
- Linha vertical no deficit total corrente (`Σ delta` dos itens negativos)
- Linha de break-even em zero
- Anotação "Break-even alcançável" / "Insuficiente" baseada em `Σ levers ≥ |deficit_total|`
- Cores: custo `#2e6da4` (azul), preco `#c05c18` (laranja)

---

## Alternativas Rejeitadas

| ID | Alternativa | Motivo Rejeição |
|---|---|---|
| A1 | Monte Carlo por ofensor | Requer `P(ofensor_i)` como input manual do planejador; MVP determinístico com gaps já calculados é suficiente e auditável |
| A2 | Painel interativo via API/UI | Fora do escopo de relatório estático entregável; `charts_png.py` já é o mecanismo de output PNG |
| A3 | Novo skill separado (skill-10) | Dados já existem no canonical após skill-08; skill-09 apenas agrega — sem novo artefato de execução |
| A4 | Diagnóstico sem levers de ação | Diagnostica o problema sem priorizar resposta — responsabilidade gerencial sem suporte quantitativo |

---

## Consequências

### Positivas

| Benefício | Mecanismo |
|---|---|
| Gap mapeia direto a ação | `gap_escala_abs` → lever escala → "reduzir frentes"; rastreabilidade completa |
| Break-even verificável | Se `Σ levers < \|deficit\|`, o contrato não tem saída viável — não apenas margem ruim |
| Levers ordenados por impacto | Stakeholder prioriza ação de maior ΔMargin antes de negociar revisão de BDI |
| Retrocompatível | `levers_equilibrio=[]` por default — canônicos antigos não quebram |
| Suficiência R rastreável | `memorial_calculo_bdi` passa a conter verificação explícita da cobertura do R |

### Negativas / Riscos

| Risco | Mitigação |
|---|---|
| `P(ofensor_i)` requer laudo técnico externo | Campo `restricoes` documenta o vínculo; verificação de suficiência gera aviso, não bloqueio |
| `gap_praticabilidade_abs ≈ 0` em itens simples | `viavel=False` quando gap ≤ 0 — painel omite barras irrelevantes |
| R não cobre ofensores de responsabilidade do contratante | §5 delimita escalação — itens de ressalva documentados separadamente |
| Levers são ações ideais, não garantidas | Campo `restricoes` explicita condições contratuais; label "viavel" não garante aceitação |

---

## Plano de Implementação

| Fase | Entregas | Status |
|---|---|---|
| **1 — Domínio** | `LeverEquilibrio` em `canonical.py`; `levers_equilibrio` em `PontoEquilibrio` | ⏳ Pendente |
| **2 — Computação** | 4 levers em `_build_pe_for_equipe()` (skill-08 `_skill_helpers_a.py`) | ⏳ Pendente |
| **3 — Visualização** | `graficos.painel_equilibrio` em skill-09; `painel_equilibrio.png` em `charts_png.py` | ⏳ Pendente |

---

## Definition of Done

### Fase 1 — Domínio
- [ ] `LeverEquilibrio(BaseModel)` adicionado em `canonical.py` com campos: `id`, `tipo`, `descricao`, `delta_margin`, `delta_margin_pct`, `viavel`, `restricoes`
- [ ] `levers_equilibrio: list[LeverEquilibrio] = Field(default_factory=list)` adicionado a `PontoEquilibrio`
- [ ] `get_errors()` sem novos erros de tipo em `canonical.py`

### Fase 2 — Computação
- [ ] Lever `fechar_gap_escala`: ΔMargin = `gap_escala_abs`, `viavel = n_equipes_efetivo > 1.05`
- [ ] Lever `fechar_gap_praticabilidade`: ΔMargin = `gap_praticabilidade_abs`, `viavel = gap > 0`
- [ ] Lever `fechar_gap_pool`: ΔMargin = `gap_pool_overhead`, `viavel = gap > 0`
- [ ] Lever `revisao_bdi_minima`: ΔMargin = `−delta`, `viavel = delta < 0`
- [ ] `levers_equilibrio` não-vazio para itens AGIS underwater (`delta < 0`) no canonical.json gerado
- [ ] `delta_margin_pct` correto: `delta_margin / custo_venda_cpu` por item

### Fase 3 — Visualização
- [ ] Chave `graficos.painel_equilibrio` presente no canonical.json com `delta_total` e lista `levers` agregados
- [ ] `painel_equilibrio.png` gerado: tornado chart, eixo-X ΔMargin R$, uma barra por lever type
- [ ] Linha vertical "deficit atual" e linha "break-even = 0" anotadas no chart
- [ ] Cores: custo = `#2e6da4`, preco = `#c05c18`
- [ ] Anotação "Break-even alcançável" ou "Insuficiente" baseada em cobertura agregada

---

## Modelo de Ofensor (detalhamento técnico)

### Campos da CPU afetados por ofensores

| Campo CPU | Significado | Ofensores típicos |
|---|---|---|
| `valor_horario` | Produção por hora operativa (unidade/h) | Variação granulométrica, DMT extra, matacões, operadores sem treinamento |
| `disponibilidade_mecanica` | % tempo disponível da frota | Falhas mecânicas, peças com lead-time longo, frota antiga |
| `fator_praticabilidade` | % semanas produtivas (via análise climática) | Chuvas excessivas, alagamento, vento |
| `num_equipes` | Frentes simultâneas operáveis | Interferência entre frentes, falta de licença parcial, acesso bloqueado |
| `consumo_L_h` | Combustível efetivo (L/h operativa) | Piso deteriorado, gradiente real ≠ planejado, carga adicional |

---

## Catálogo de Ofensores por Origem

### Ofensores Climáticos

| Ofensor | Campo CPU afetado | Métrica de impacto | Hipótese de cobertura padrão |
|---|---|---|---|
| Pluviometria acima da normal climatológica | `fator_praticabilidade` | Δ dias improdutivos/mês | Excedência < P90 do histórico 10 anos |
| Enchente/inundação de frente | `fator_praticabilidade`, `num_equipes` | Paralisação total (dias) | Evento < TR-25 anos |
| Temperatura extrema (> 40°C) | `valor_horario` | Redução rendimento operador estimada | Não coberto por R — força maior → ressalva |

### Ofensores Geotécnicos

| Ofensor | Campo CPU afetado | Métrica de impacto | Hipótese de cobertura padrão |
|---|---|---|---|
| Classe de material superior ao previsto (1a→2a→3a Cat) | `valor_horario`, `consumo_L_h` | Fator de escarificação adicional | Variação ≤ 15% do volume total contratado |
| Matacões e blocos não previstos em sondagem | `valor_horario` | h_máquina_parada / volume | ≤ 3% do volume de corte |
| Lençol freático → solo mole/instabilidade de talude | `num_equipes`, `valor_horario` | Índice de retrabalho (%) | Solo saturado ≤ 10% da extensão do trecho |
| DMT real > DMT planejado (re-roteamento, obstáculo) | `valor_horario`, `consumo_L_h` | Δ DMT médio ponderado (m) | Desvio ≤ 10% do DMT contratual |

### Ofensores Mecânicos / Disponibilidade

| Ofensor | Campo CPU afetado | Métrica de impacto | Hipótese de cobertura padrão |
|---|---|---|---|
| Disponibilidade mecânica efetiva < premissa CPU | `valor_horario` | Δ disp_mec (%) | Disp_efetiva ≥ 80% (CPU padrão: 85%) |
| Falta de peças sobressalentes (lead-time > prazo) | `disponibilidade_mecanica` | h_parada_frota acumuladas/mês | ≤ 48h acumuladas por mês |
| Frota subdimensionada para pico de produção | `num_equipes` | Horas-extra não planejadas | Alocação conforme cronograma aprovado |

### Ofensores Organizacionais / Contratuais

| Ofensor | Campo CPU afetado | Métrica de impacto | Responsabilidade contratual |
|---|---|---|---|
| Interferência de frentes simultâneas (conflito de espaço) | `num_equipes` | % tempo de espera por interferência | Coordenação responsabilidade do contratante |
| Atraso na emissão de licença ambiental parcial | `num_equipes`, `fator_praticabilidade` | Semanas de paralisação forçada | Licença disponível conforme cronograma-base |
| Acesso à frente bloqueado (propriedade, litigância) | `num_equipes` | Dias paralisados / trecho | Desapropriação responsabilidade do contratante |

> **Nota:** Ofensores de responsabilidade do contratante não são cobertos por R — geram
> direito a ressalva direta sem consumo da reserva de contingência.

---

## Hipóteses de Cobertura e Verificação de Suficiência do R

### Estrutura de declaração por perfil

Cada ofensor deve ser declarado com limite e impacto máximo no campo `notas_bdi.overhead_r`
do perfil (`config/perfis/<contexto>.yaml`):

```yaml
bdi:
  overhead_r: 0.030   # R = 3,0%
  notas_bdi:
    overhead_r: |
      Cobertura declarada:
      - variacao_classe_material: variacao <= 15% volume; impacto_pu_max = +8%
      - pluviometria_p90: excedencia < P90/10a; impacto_pu_max = +5%
      - disponibilidade_mecanica: disp_efetiva >= 80%; impacto_pu_max = +4%
      Total esperado E[ΔPU]: ~9% → R=3% sobre PU_direto cobre (~R$... /unid)
      Fonte: laudo_geotecnico_2025.pdf + analise_praticabilidade_open-meteo
```

### Verificação de suficiência

Para que o R seja considerado **bem calibrado**:

$$R \times PU_{\text{direto}} \geq \sum_i P(\text{ofensor}_i) \times \Delta PU_{\text{max},i}$$

Se a soma esperada exceder o R declarado, o BDI está subdimensionado e a cobertura é parcial
— o excesso fica a descoberto ou é objeto de escalação para ressalva.

---

## Escalação para Receitas de Ressalva

Quando um ofensor excede a hipótese declarada, ou não foi previsto:

$$\text{Custo\_descoberto} = \Delta PU_{\text{real}} - R \times PU_{\text{direto}} \quad (\text{quando} > 0)$$

O mecanismo de **remanejamento de receitas de ressalva** permite absorver esse custo:

| Instrumento | Gatilho | Limitações |
|---|---|---|
| **Aditivo de quantidade** | Volume real > volume contratado (mesma CPU) | Aprovação do contratante; teto % sobre contrato original |
| **Aditivo de serviço novo** | Serviço não previsto no escopo | Requer nova CPU com BDI separado |
| **Reequilíbrio econômico-financeiro** | Evento imprevisível e extraordinário que altera estrutura de custo | Prova de imprevisibilidade; processo formal (TCU/contrato) |
| **Remanejamento de saldo R intra-contrato** | Ofensor grave em item A absorvido por R não consumido em item B | Apenas se saldo global de R ≥ 0; deve ser documentado |

### Condições para remanejamento intra-BDI

O remanejamento de saldo de R entre itens EAP é viável quando:

1. O ofensor que gerou custo descoberto em um item EAP é compensado por **economia de R**
   em outro item do mesmo contrato (onde a ofensa prevista não ocorreu).
2. O remanejamento **não viola** o teto de R declarado para o item afetado na visão do
   auditor/fiscal do contratante.
3. O saldo de R agregado do contrato permanece ≥ 0 após o remanejamento.

### Limites do remanejamento

- **Ofensas graves** (impacto > 20% do PU_direto no item): requerem reequilíbrio formal —
  remanejamento interno não é suficiente.
- **Itens de alta criticidade** (caminho crítico EAP): qualquer cobertura extra deve ser
  declarada antes de solicitar medição, para evitar glosa posterior.
- **Receitas de seguros** (indenização all-risks, RCO): devem ser aplicadas ao item afetado
  antes de ativar remanejamento interno de R.

---

## Integração com o Pipeline

| Artefato | Como reflete este ADR |
|---|---|
| `config/perfis/<ctx>.yaml` → `bdi.overhead_r` | Deve satisfazer a verificação de suficiência §4.2 |
| `config/perfis/<ctx>.yaml` → `notas_bdi.overhead_r` | Lista ofensores cobertos, seus limites e fonte de quantificação |
| `memorial_calculo_bdi` (canonical.json, skill-08) | Deve incluir ofensores declarados e impacto_pu_max por item |
| `cost_criticality_report` (skill-05) | Itens de alta criticidade → monitoramento prioritário dos ofensores de campo |
| `analise_campanhas` (skill-05) | `fator_praticabilidade` efetivo → input direto ao ofensor climático |
| `bar_categoria_componente.png` (skill-09) | `overhead_r` visível na decomposição — este ADR fornece sua semântica |
| Relatório PDF (skill-09) | Seção "Riscos Operacionais" deve listar ofensores ativos e saldo R disponível |

---

## Referências

- NEP-032: Derivação bottom-up de PU por composição de equipe produtiva
- ADR-040: Perfis de BDI e configuração por contexto
- ADR-053: Estrutura de custos diretos e composição de CPU
- ADR-074: Análise de praticabilidade climática (ofensor climático §3.1)
- ADR-076: Cubo analítico e relatório financeiro
- ADR-081: Precedência EAP com threshold de conclusão parcial
- TCU Acórdão 2622/2013: Parâmetros referenciais de BDI para obras públicas
- SINAPI — Metodologia de Cálculo de BDI (Caixa Econômica Federal, 2021)

