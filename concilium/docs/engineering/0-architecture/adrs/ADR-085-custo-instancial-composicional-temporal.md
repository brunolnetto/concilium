# ADR-085 — Custo Instancial Composicional Temporal: Linha do Tempo por Instância, Taxa Ociosa por Componente e Base Bottom-Up de Precificação

**Status:** Implementado
**Data:** 2026-05-29
**Autores:** Bruno Peixoto / Concilium
**Dependências:** ADR-071, ADR-077, ADR-079, ADR-080 (supersede), ADR-083, ADR-084, ADR-023, ADR-039, ADR-076

---

## 1. Contexto

### 1.1 Tese central

O preço unitário de catálogo (CPU) serve **exclusivamente** para derivar a *composição* de equipe
de cada atividade (`funcoes`, `equipamentos`, `materiais`). A partir do momento em que escolhemos
uma estratégia de construção do cronograma, a composição autônoma de equipes evolui para um **pool
de recursos** que congrega esforços de enxugar custo via reaproveitamento (mobilização tardia,
desmobilização antecipada, perpetuação entre atividades não-simultâneas).

Logo, o custo verdadeiro de uma atividade não é `PU_catálogo × Q`, nem o custo autônomo de um
equipe-bundle dedicado. É o **custo instancial**: a soma do que cada instância de recurso do pool
incorre ao longo de sua linha do tempo, particionado entre as atividades que ela serviu. A
precificação (BDI → preço de venda) deve ser **bottom-up** a partir desse custo instancial — não uma
reconciliação paliativa entre catálogo e operação, que mascara o erro em vez de corrigi-lo.

### 1.2 A instância como objeto temporal de primeira classe

Cada instância $I_k$ de um tipo de recurso $r$ (um slot contratual do pool, ex.: `ESC-3CAT-03`) tem
uma **composição temporal**: uma sequência de estados ao longo das semanas, com carimbos de início
e fim e janelas de ociosidade. Os recursos efetivamente mobilizados na semana $j$ formam um
**subconjunto** da união disjunta das equipes que todas as atividades precisariam se executadas
isoladamente — exatamente porque há mobilização tardia e desmobilização antecipada.

$$\text{Pool}_r(j) \;\subseteq\; \biguplus_{i} \text{equipe}_r(i)$$

A diferença entre o lado direito (disjunto, autônomo) e o lado esquerdo (instancial, compartilhado)
é a economia de pool que o sistema existe para capturar.

### 1.3 Custos de equipamento e mão-de-obra diferem na ociosidade

A operação vigente impõe tratamentos distintos por componente durante o standby de uma instância:

| Componente | Comportamento em standby (instância ociosa, dentro do ciclo de vida) |
|---|---|
| **Mão-de-obra (MO)** | Salário + encargos **integrais**. A CLT não permite "taxa reduzida" por ociosidade — o trabalhador presente custa o mesmo ativo ou aguardando. |
| **Equipamento (EQ)** | **Taxa de locação reduzida** (`custo_idle_semanal_unit`): aluguel do ativo físico sem operador, sem combustível, sem desgaste produtivo — tipicamente 20–40% da taxa ativa. |
| **Combustível** | **Zero** — sem operação, sem consumo. |
| **Material** | **Zero** — consumido proporcionalmente à produção. |

Mobilização tardia e desmobilização antecipada têm semântica física distinta por componente:
para EQ é transporte de máquina (ida/volta); para MO é admissão/rescisão (aviso prévio, multa FGTS)
ou remanejamento entre frentes. O custo de rescisão CLT permanece **fora de escopo** (candidato a ADR
futuro), conforme já decidido no ADR-080 R2.

### 1.4 Estado atual confrontado com o modelo

| # | Conceito do modelo | Estado no código | Lacuna |
|---|---|---|---|
| C1 | Linha do tempo $\sigma_k(j) \in \{\text{prod}, \text{idle}, \text{off}\}$ | `_build_instancias_recurso` rastreia `instance_active`/`instance_standby` e `instance_week_map` (semana→atividade) por slot | Estado `off` (fora do ciclo) inexistente — toda instância abrange o span inteiro do contrato |
| C2 | Mobilização tardia $\text{mob}_k$ = 1ª semana atribuída | Campo `mobilizacao_por_instancia` existe mas **nunca é preenchido** (`{}`) | Não implementado |
| C3 | Desmob. antecipada $\text{demob}_k$ efetiva | `economia_desmobilizacao_antecipada` é só diagnóstico; `desmob_antecipada_aplicada` sempre `False` | Não aplicado ao custo |
| C4 | Custo do contrato = $\sum_k \text{custo}(I_k)$ | `custo_total_contrato = quantidade_contratada × custo_unit_semanal × semanas_contrato` (monolítico, ADR-071), computado **antes** das instâncias | Superestima; ignora a estrutura instancial existente |
| C5 | Taxa ociosa **por componente** (MO integral, EQ reduzida, comb/mat zero) | `custo_idle_semanal_unit` é escalar único; standby cobra essa taxa ou a taxa cheia (fallback) | Sem diferenciação composicional |
| C6 | Custo instancial categorial $C_i^{\text{inst,cat}}$ para BDI bottom-up | `CustoParticionadoItem` só tem agregado `custo_total_particionado`; BDI em skill-08 aplica sobre `equipes_diretas.*_mensal` (taxas de catálogo, sem permanência, sem pool) | Base de BDI desacoplada do custo instancial real |

O ADR-080 endereçava C2, C3, C4 e parcialmente C5 (idle escalar). Este ADR **subsume e generaliza**
o ADR-080: trata C5 como decomposição por componente e adiciona C6 (a base bottom-up de
precificação), fechando o ciclo composição → cronograma → pool → instância → custo → BDI → preço.

---

## 2. Decisão

### D1 — Instância como objeto de custo temporal composicional

Para cada tipo $r$ com pool de tamanho $N_r$, as instâncias $I_{r,1}, \dots, I_{r,N_r}$ recebem uma
**linha do tempo de estados**:

$$\sigma_k(j) = \begin{cases}
\text{prod} & \text{se a instância } k \text{ está atribuída a alguma atividade na semana } j \\
\text{idle} & \text{se } j \in [\text{mob}_k, \text{demob}_k] \text{ e nenhuma atividade atribuída} \\
\text{off} & \text{caso contrário (não mobilizada ou já desmobilizada)} — \text{custo zero}
\end{cases}$$

com ciclo de vida:

$$\text{mob}_k = \min\{j : \sigma_k(j) = \text{prod}\}, \qquad
\text{demob}_k = \begin{cases}
\text{última semana ativa} & \text{se desmob antecipada aplicada} \\
\text{semana\_fim do contrato} & \text{caso contrário}
\end{cases}$$

### D2 — Decomposição por componente da taxa instancial

A taxa semanal unitária de cada tipo $r$ é decomposta nos quatro componentes, recuperados da
`EquipeDireta` representativa (taxas mensais ÷ `SEMANAS_POR_MES`):

$$c_r = c_r^{\text{mo}} + c_r^{\text{eq}} + c_r^{\text{comb}} + c_r^{\text{mat}}$$

A taxa em standby é diferenciada por componente:

$$c_r^{\text{idle}} = \underbrace{c_r^{\text{mo}}}_{\text{integral (CLT)}} + \underbrace{\rho_r \cdot c_r^{\text{eq}}}_{\text{locação reduzida}} + \underbrace{0}_{\text{comb}} + \underbrace{0}_{\text{mat}}$$

onde $\rho_r = c_r^{\text{idle,eq}} / c_r^{\text{eq}}$ é derivado de `custo_idle_semanal_unit` quando
disponível, senão $\rho_r = 1$ para MO e a fração padrão para EQ. Quando `custo_idle_semanal_unit = 0`,
o comportamento recai em $c_r^{\text{idle}} = c_r$ (retrocompatível com ADR-071/079).

### D3 — Custo da instância e do contrato (substitui a fórmula monolítica)

$$\text{custo}(I_k) = \sum_{j:\,\sigma_k(j)=\text{prod}} c_r \;+\; \sum_{j:\,\sigma_k(j)=\text{idle}} c_r^{\text{idle}} \;+\; c_r^{\text{mob}} \;+\; c_r^{\text{demob,efetivo}}$$

$$\boxed{\;\text{custo\_total\_contrato}_r = \sum_{k=1}^{N_r} \text{custo}(I_k)\;}$$

onde $c_r^{\text{demob,efetivo}} = c_r^{\text{demob}}$ se a desmob antecipada foi aplicada à instância,
senão $0$ (custo de desmob embutido no contrato, comportamento legado). Esta soma **substitui** a
fórmula `peak × unit × span` em `_build_contratos_recurso`, e passa a ser computada **após**
`_build_instancias_recurso`.

### D4 — Custo instancial categorial por atividade (base bottom-up)

Cada componente do custo de instância é imputado às atividades servidas. Para a atividade $i$:

$$C_i^{\text{inst,cat}} = \sum_{k}\sum_{j:\,\text{atrib}(k,j)=i} c_r^{\text{cat}}(\sigma_k(j)) \;+\; \text{quota causal de idle/mob/demob}_i^{\text{cat}}$$

para cada $\text{cat} \in \{\text{mo}, \text{eq}, \text{comb}, \text{mat}\}$. A quota causal de
ociosidade segue o princípio do ADR-083 (imputada ao sucessor que causou o gap); mob/demob seguem a
partição por cadeia de perpetuação (ADR-073). Estes campos enriquecem `CustoParticionadoItem`.

### D5 — Precificação bottom-up (reposicionamento do BDI)

O preço de venda de cada atividade passa a ser construído sobre a base instancial categorial,
com BDI diferenciado por categoria (ADR-023):

$$V_i = C_i^{\text{inst,mo}}(1+b_{\text{mo}}) + C_i^{\text{inst,eq}}(1+b_{\text{eq}}) + C_i^{\text{inst,comb}}(1+b_{\text{diesel}}) + C_i^{\text{inst,mat}}(1+b_{\text{mat}})$$

`venda_sem_bdi` (PU × Q de catálogo) é **rebaixado a referência de benchmarking competitivo** — deixa
de ser base de custo e de margem. `frentes_equivalentes_necessarias` (ADR-076) permanece como
indicador de pressão: $C_i^{\text{inst}} / (\text{PU}_{\text{cat}} \times Q_i) > 1$ sinaliza que o custo
operacional supera a referência de mercado, exigindo decisão estratégica explícita. O ponto de
equilíbrio (ADR-076/082) muda de semântica: de "o catálogo cobre o custo?" para "o BDI é suficiente
dado o custo instancial?".

---

## 3. Modelo de Dados

### 3.1 `InstanciaRecurso` (estende ADR-077)

```python
# Ciclo de vida (ADR-085 D1)
semana_mobilizacao: str = ""          # 1ª semana ativa (late mob); "" = span do contrato
semana_desmobilizacao: str = ""       # última semana coberta (após desmob efetiva)
semanas_off: int = 0                  # semanas do span do contrato fora de [mob, demob]
# Custo instancial composicional (ADR-085 D2/D3)
custo_ativo_mo: float = 0.0
custo_ativo_eq: float = 0.0
custo_ativo_comb: float = 0.0
custo_ativo_mat: float = 0.0
custo_idle_mo: float = 0.0            # MO integral durante idle (CLT)
custo_idle_eq: float = 0.0            # EQ a taxa reduzida durante idle
custo_mob_instancia: float = 0.0
custo_demob_instancia: float = 0.0
custo_instancia_total: float = 0.0    # soma de todos os termos (D3)
```

### 3.2 `CustoParticionadoItem` (estende ADR-083 com categorias — D4)

```python
# Decomposição categorial do custo instancial particionado (ADR-085 D4)
custo_inst_mo: float = 0.0
custo_inst_eq: float = 0.0
custo_inst_comb: float = 0.0
custo_inst_mat: float = 0.0
# Invariante: custo_inst_mo + eq + comb + mat == custo_total_particionado
```

### 3.3 `RecursoContrato` (taxas por componente — D2)

```python
# Decomposição da taxa semanal unitária por componente (ADR-085 D2)
custo_unit_semanal_mo: float = 0.0
custo_unit_semanal_eq: float = 0.0
custo_unit_semanal_comb: float = 0.0
custo_unit_semanal_mat: float = 0.0
rho_idle_eq: float = 1.0              # fração da taxa de EQ cobrada em standby
```

Campos `mobilizacao_por_instancia` (ADR-080) e `desmob_antecipada_aplicada` (ADR-077/080) passam a
ser **efetivamente preenchidos**.

---

## 4. Plano de Implementação

| Fase | Entregas | Status |
|---|---|---|
| 1 | Modelo: campos em `InstanciaRecurso`, `CustoParticionadoItem`, `RecursoContrato` | ✅ Implementado |
| 2 | Custo instancial composicional em `_build_instancias_recurso`; `custo_total_contrato = Σ custo(I_k)` via `_aplicar_custo_instancial_adr085` (pós-instâncias); mob tardia + idle/off por `gap_max` + desmob antecipada | ✅ Implementado |
| 3 | Decomposição categorial `C_i^{inst,cat}` em `CustoParticionadoItem` (proporcional, invariante de soma) | ✅ Implementado |
| 4 | `_calc_venda_com_bdi` (skill-08) sobre base instancial categorial bottom-up; `direto_catalogo` vira referência | ✅ Implementado |
| 5 | Validações (`VAL-MOB-TARDIA-OK`, `VAL-INST-CAT-SOMA`, `VAL-BDI-BOTTOM-UP`) + verificação AGIS | ✅ Implementado |

**Nota de implementação (Fase 2):** a reconciliação ocorre em `_aplicar_custo_instancial_adr085`
após `_build_instancias_recurso` (em vez de reordenar o cálculo do contrato), reescalando
`atribuicao`/`particao_por_item` e preservando a invariante Σ `custo_total_particionado` ==
`custo_total_contrato`. O helper composicional vive em
`_05_equipes_custo_helpers.calcular_custo_instancia_composicional`.

**Nota de implementação (decisão idle/off — refinamento do bug):** a classificação de cada gap
usa a **economia verdadeira de permanência** (MO-aware): manter ocioso custa `(c_mo + c_idle_eq)`
por semana (MO integral por CLT + EQ reduzida); liberar custa `(c_mob + c_demob)` uma vez. Bridge
(IDLE) sse `(c_mo + c_idle_eq)·gap ≤ c_mob + c_demob`, senão OFF (recurso desmobilizado, não
faturado — a "união disjunta" do §1.2). Como a MO é cobrada integral no idle, recursos MO-pesados
em gaps são **liberados**, não mantidos ociosos — corrigindo o viés que tornava o pool mais caro
que o autônomo. O diagnóstico de perpetuação `custo_mob_desmob_contrato` (ADR-073/079, baseado no
`gap_max` de EQ) permanece separado e **não entra** em `custo_total_contrato`/N4, preservando os
testes do ADR-079. Unificar o `gap_max` do scheduler com a economia MO-aware é refinamento futuro.

**Nota de implementação (Fase 4–5):** `_calc_venda_com_bdi` passou a aplicar BDI sobre o custo
instancial categorial (`_build_custo_categorial_bottom_up`): itens com partição instancial usam
`custo_inst_{mo,eq,comb,mat}`; demais decompõem `EquipeDireta.custo_total` pelas frações
recorrentes. `venda_sem_bdi` (catálogo) permanece como referência de mercado e governa o confronto
de benchmark — por isso o AGIS segue **APROVADO** sem rebaseline. A `VAL-BDI-BOTTOM-UP` reporta o
prêmio operacional do preço bottom-up sobre o catálogo (AGIS: ~+28%, sinal de PU subcoberto).

## 5. Validações

| Código | Condição | Status |
|---|---|---|
| `VAL-MOB-TARDIA-OK` | `semana_mobilizacao ≥ semana_inicio` do contrato para cada instância | INFO |
| `VAL-IDLE-COMP-OK` | `0 < rho_idle_eq ≤ 1` e `custo_idle_mo == custo_ativo_mo` por semana (MO integral) | INFO |
| `VAL-IDLE-COMP-WARN` | `c_idle ≥ custo_unit_semanal` (parametrização suspeita) | AVISO |
| `VAL-DESMOB-EFETIVA-OK` | `desmob_antecipada_aplicada = True` para instâncias com economia > 0 | INFO |
| `VAL-INST-CAT-SOMA` | `Σ custo_inst_cat == custo_total_particionado` (±0,01) por item | ERRO |
| `VAL-CUSTO-CONTRATO-POSITIVO` | `custo_total_contrato_r > 0` após refactoring | ERRO |
| `VAL-BDI-BOTTOM-UP` | base de BDI = `Σ C_i^{inst,cat}` (não catálogo) quando contratos presentes | INFO |

## 6. Alternativas Rejeitadas

| ID | Alternativa | Motivo |
|---|---|---|
| R1 | Reconciliar catálogo × operacional via fator de ajuste | Paliativo; mascara o erro e o perpetua. O custo correto é bottom-up por construção. |
| R2 | Reduzir salário de MO em standby | Incompatível com CLT (herdado de ADR-080 R1). |
| R3 | Modelar rescisão CLT no early demob de MO | Depende de tempo de empresa/sindicato — dados ausentes; ADR futuro (herdado de ADR-080 R2). |
| R4 | Span por instância via campo manual em `rcpsp_spec` | Duplica o cronograma; derivação automática é superior (herdado de ADR-080 R3). |
| R5 | Manter idle como escalar único (ADR-080 §B) | Não distingue MO (integral) de EQ (reduzida) — viola a operação vigente. |

## 7. Consequências

### Positivas
| Efeito | Descrição |
|---|---|
| N4/Bridge corrigido | `custo_total_contrato` deixa de superestimar (mob tardia + idle por componente + desmob efetiva) |
| Precificação coerente | BDI sobre custo instancial real, não sobre catálogo desacoplado |
| Auditabilidade | Cada R$ do preço rastreável até instância × semana × componente |
| Convergência de threads | Unifica ADR-080 (custo temporal) com a base bottom-up de BDI |

### Negativas / Riscos
| Risco | Mitigação |
|---|---|
| Mudança material nos outputs de preço/margem | Rebaseline AGIS controlado; `venda_sem_bdi` preservado como referência |
| Reordenação de cálculo (instâncias antes do custo) | Fase 2 isolada com testes de retrocompatibilidade |
| Recuperação de taxas por componente depende de `EquipeDireta` representativa | Quando múltiplas equipes no tipo, usar média ponderada por machine-weeks (consistente com `custo_unit_semanal`) |

## 8. Definition of Done

### Fase 1
- [ ] Campos adicionados aos três modelos com defaults retrocompatíveis
- [ ] Testes de serialização/round-trip Pydantic

### Fase 2
- [ ] `custo_total_contrato = Σ custo(I_k)` com mob tardia, idle por componente, desmob efetiva
- [ ] `mobilizacao_por_instancia` e `desmob_antecipada_aplicada` preenchidos
- [ ] `c_idle = 0` → comportamento idêntico ao ADR-079 (retrocompat)

### Fase 3
- [ ] `CustoParticionadoItem` categorial; invariante `VAL-INST-CAT-SOMA`

### Fase 4
- [ ] `_calc_venda_com_bdi` sobre base instancial; `direto_catalogo` documentado como referência
- [ ] Margem operacional vs. margem catálogo separadas no resultado

### Fase 5
- [ ] ≥ 30 testes; rebaseline AGIS `referencia.json`; INDEX atualizado

## 9. Relacionados

[[adr071-resource-contract-model]] [[adr077-recurso-instancial-utilizacao]]
[[adr079-ativacao-economica-compartilhamento]] [[adr080-custo-diferenciado-permanencia]]
[[adr083-custo-particionado-pool-muitos-para-muitos]] [[adr084-custo-particionado-pool-predecessao-parcial]]
