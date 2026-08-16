# ADR-182 — Consolidação de "Custo Já All-In" em Fonte Única + Correção de Regressão no α CLT/PJ

**Status:** Implementado ✅ _(P2 passou por retração e confirmação — ver histórico da decisão)_
**Data:** 2026-08-15
**Contexto:** MendesLobo Construtora — Concilium
**Dependências:** ADR-097 (tributação social), ADR-009 (remoção de `custo_com_encargos`), ADR-165/167 (convenção `metodo_custo_total`)

---

## Contexto

### Problema

Validação dos custos do regime de trabalho da função de obra achou dois bugs na forma como o motor decide se `preco_unitario` de um insumo de MO já é **all-in** (já inclui encargos sociais) ou precisa de `alpha`/`enc` por cima.

**P1 — sinal de "já all-in" duplicado em 3 implementações divergentes de texto livre, nenhuma delas o campo estruturado que já existe no catálogo:**

- `_dimensionamento_custos.py::_resolve_custo_unit_funcao` — checava `"inclui encargos"` em `nota`/`nota_encargos`, + um branch morto `custo_com_encargos` (0 uso em qualquer catálogo — campo removido pela ADR-009).
- `_dimensionamento_itens.py::_finalize_funcao` — implementação própria e divergente do mesmo texto.
- `04-cronograma/_skill_helpers/_custos.py::_custo_hora_mao_de_obra` — só checava `"nota"` (nem `"nota_encargos"`), e só para `unidade` h/hora — mensal nunca protegido.
- `pu_calculator.py::_acumular_custo_mo` — heurística implícita `unidade == "h"` → all-in, sem checar nada.
- Um campo `metodo_custo_total: "custo_total_ja_incluido"` já existe em 25 insumos `MO-*`/`P0092` (ADR-167) e já está no JSON Schema (`insumo.schema.json`), mas **nenhum código o lia** — confirmado por grep exaustivo em `src/`.

**Impacto real, confirmado ao vivo:**
- 7 insumos `horista_CE` (`MO-ENCARREGADO-DE-FRENT`, `MO-TÉCNICO-DE-QSMS`, `MO-TECNICO-DE-PLANEJAME` ×2, `MO-ENGENHEIRO-FLORESTAL`, `MO-GERENTE-DE-CONTRATO-`) não batiam com nenhum dos 3 textos → skill-05 aplicava CLT completo (177,7%) + HE (25%) em cima de salário já all-in. `MO-ENCARREGADO-DE-FRENT` está em 3 CPUs reais; `CPU-DIVER-ATI-072-PROD-001` recalculado: custo_mo_h R$157,15/h calculado vs. R$129,13/h correto (**+21,7%**).
- `MO-TOPOGRAFO` (`categoria_sindical: pj_CE`, `metodo_custo_total: custo_total_ja_incluido`, mas `tipo_contrato: CLT`) — `pu_calculator._alpha()` decide por `tipo_contrato`, não `categoria_sindical`/`metodo_custo_total`, então aplicava CLT completo por cima de valor all-in em 3 CPUs reais (`CPU-DIVER-ATI-070`, `CPU-TERRA-ATI-005`, `PROD-ATI-070`) — **+77,7%**.

**P2 — regressão confirmada em `pu_calculator._alpha()` (com volta atrás e confirmação final no meio do caminho):**

Processo desta decisão teve idas e vindas, registradas aqui por transparência:
1. Lido o texto da ADR-097 (linhas 168/216, "✅ Alinhado"/"✅ Feito" para `(1+ENCARGOS_CLT)=2.777`) → corrigido `_alpha()` para `1.0 + alpha_clt/alpha_pj`.
2. Usuário declarou de memória que o multiplicador é direto (`salario × 1,777`, sem somar 1) → fix revertido.
3. Conferência de um dado histórico real do catálogo (`MO-AJUDANTE`: `percentual_encargos_local: 1.06`, `custo_com_encargos` removido = R$4.209,32 = 2.043,36 × **2,06** = 2.043,36 × **(1+1,06)**) contradisse a reversão — usuário pediu para investigar o sistema tributário brasileiro atual.
4. Pesquisa externa (SINAPI/SINDUSCON, metodologia oficial do setor) confirma, com exemplo numérico verificável: **pedreiro horista, salário R$2.500/mês (220h), encargos 90% → custo R$21,58/h = (2.500/220) × (1+0,90) = R$11,36 × 1,90**. Multiplicador direto (×0,90) daria R$10,23/h — não bate. Fonte: [gestordeobras.com.br](https://www.gestordeobras.com.br/conversao-de-custo-de-mao-de-obra-com-encargos-sociais-horista-x-mensalista-sinapi/) ("Custo do Homem-Hora = Salário-Hora × (1 + Encargos%)").

**Três fontes independentes convergem em `(1+enc)`**: texto da ADR-097, dado histórico do próprio catálogo, e metodologia de mercado (SINAPI/SINDUSCON) com exemplo numérico verificado. `_alpha()` restaurado para `1.0 + (alpha_pj|alpha_clt)` no branch `tipo_contrato` — consistente com o branch `percentual_encargos_local` (que já fazia `1.0 + enc_local`) e com `encargo_resolver.resolver_encargo()`/skill-05 (`salario × (1+enc)`, usado por skill-05/06/07 — **não precisou de nenhuma mudança**, sempre esteve correto).

**P3 — achado durante a migração de dados (D5): a heurística `unidade == "h"` sendo removida já era ela própria um bug para 7 insumos:**

Ao popular `metodo_custo_total` nos 41 insumos `unidade: "h"` candidatos, 7 (`SV-OUV-MO-SINALEIRO/OPER-ESCAV/AJUDANTE/OPER-PA/MOTOR-BASC/OPER-MOTOSSERRA/OPER-TRAT-EST`, catálogo `mendeslobo`, referenciados em 4-9 CPUs reais cada — ex.: `CPU-TERRA-ATI-045/047/049`) têm `atributos_especificos.memoria_calculo` afirmando explicitamente o oposto de all-in: *"Valor é SALÁRIO BASE (sem encargos) — encargos aplicados via pipeline (resolver_encargo/ENCARGOS_CLT), não incluídos aqui."* Ou seja, a heurística antiga (`unidade == "h"` → all-in, sem checar nada) já causava, nesses 7 casos, o erro **oposto** ao de P1: omitia 100% do encargo em `pu_calculator` (o skill-05 já aplicava corretamente, por não depender dessa heurística). Excluídos deliberadamente da migração D5 (não recebem `metodo_custo_total`) — depois do fix D3/D4, `_alpha()` volta a aplicar o encargo completo (`tipo_contrato: CLT` → `1+alpha_clt`) para eles, corrigindo esse terceiro bug como efeito colateral direto da consolidação.

---

## Decisão

### D1 — `custo_ja_inclui_encargos(atrib)` como fonte única de verdade

Nova função em `domain/services/financial/encargo_resolver.py` (mesmo módulo que já centraliza `resolver_encargo()`):

```python
def custo_ja_inclui_encargos(atrib: dict) -> bool:
    return atrib.get("metodo_custo_total") == "custo_total_ja_incluido"
```

Substitui as 3 implementações de texto livre + a heurística por unidade em `pu_calculator._alpha()`/`_acumular_custo_mo`, `_dimensionamento_custos.py::_resolve_custo_unit_funcao`, `_dimensionamento_itens.py::_finalize_funcao`, `04-cronograma/_custos.py::_custo_hora_mao_de_obra`. Remove também o branch morto `custo_com_encargos` (0 uso confirmado em `mendeslobo`/`rfi-r02`/`samples`/`test`).

### D2 — Formalizar `metodo_custo_total`/`percentual_encargos_local` em `AtributosInsumo`

Ambos já existiam no JSON Schema (`insumo.schema.json`) mas nunca no Pydantic `AtributosInsumo` (`extra="ignore"` os descartava silenciosamente em qualquer round-trip pelo model; só sobreviviam porque o código de cálculo lê `atributos_especificos` como dict cru). Adicionados como campos declarados; `metodo_custo_total` ganha `Literal["custo_total_ja_incluido"] | None` (Pydantic) e `enum` (JSON Schema) para travar contra typo futuro.

### D3 — Corrigir `_alpha()`: `1.0 + (params.alpha_pj | params.alpha_clt)` no branch `tipo_contrato`

Alinha o branch default à mesma convenção já usada pelo branch `percentual_encargos_local` (`1.0 + enc_local`) e por `encargo_resolver.resolver_encargo()` (skill-05/06/07) — confirmado por 3 fontes independentes (ADR-097, dado histórico do catálogo, metodologia SINAPI/SINDUSCON, ver P2). `custo_ja_inclui_encargos()` ganha prioridade sobre `tipo_contrato` no topo de `_alpha()` — fecha também o caso `MO-TOPOGRAFO` (P1).

### D4 — `_acumular_custo_mo`: unidade decide só a conversão R$/mês→R$/h, não mais o all-in

`unidade == "h"` deixa de pular `_alpha()`; passa a chamar `_alpha()` sempre (que agora sabe decidir all-in via D1). Migração de dados necessária (D5) para preservar paridade comportamental.

### D5 — Migração de dados: 34 insumos MO `unidade: "h"` ganham `metodo_custo_total`

33 em `mendeslobo` (`SV-P00XX-D/N`, `AGIS-FN-*`) + `MO-SERVENTE-USINA-H` em `mendeslobo`/`rfi-r02` — todos com `nota`/`nota_encargos` "inclui encargos" OU `descricao` explícita "taxa horária com encargos". Os 7 `SV-OUV-MO-*` (P3) são **excluídos deliberadamente**: seu `memoria_calculo` documenta o oposto de all-in. Os 25 insumos `MO-*`/`P0092` mensais já tinham o campo (ADR-167) — resolve os 7 casos `horista_CE` automaticamente, sem migração de dado.

### D6 — Remoção de código morto (`b.py`)

`05-equipes-e-alocacao/_skill_helpers/b.py` linhas 154-243: duplicata pré-refatoração de `_resolve_salario`/`_resolve_encargo_funcao`/`_calcular_custo_funcao`/`_converter_preco_equip`/`_consumo_from_decomposicao`, sem a lógica desta ADR nem delegação a `encargo_resolver` — confirmado 100% morta (nada em `__init__.py` importa essas 5 funções de `.b`). Removida.

---

## Alternativas Rejeitadas

| ID | Alternativa | Motivo |
|---|---|---|
| R1 | Corrigir só os 7 insumos `horista_CE` via dado (`percentual_encargos_local: 0.0`) | Deixaria as 3 implementações de texto livre divergentes no lugar — próximo insumo com fraseado diferente reabre o mesmo bug (foi exatamente o que já aconteceu 3 vezes) |
| R2 | Não tocar em `pu_calculator._alpha()` (ADR-097), tratar como issue separada | Decisão do usuário: escopo maior, correto, corrigir junto — regressão de algo já documentado como corrigido não deveria esperar |
| R3 | Redefinir `ENCARGOS_CLT`/`ENCARGOS_PJ` para já serem `2.777`/`1.06` (sem `+1` no código) | Quebraria a semântica de `percentual_encargos_local` (fração, usado em 4+ call sites) e a de `resolver_encargo()` — preferível manter as constantes como fração e ajustar só o ponto que estava com o `+1` faltando |

---

## Consequências

### Positivas

| Efeito | Descrição |
|---|---|
| Fonte única de verdade | 1 função (`custo_ja_inclui_encargos`) substitui 4 mecanismos divergentes (3 textos + 1 heurística de unidade) |
| Campo auditável | `metodo_custo_total` formal no Pydantic + `enum` no JSON Schema — typo futuro vira erro de validação, não bug silencioso |
| Bug de MO real corrigido | 7 insumos `horista_CE` + `MO-TOPOGRAFO` deixam de sofrer dupla contagem (confirmado em 6 CPUs reais) |
| Regressão ADR-097 corrigida | `_alpha()` volta a aplicar `(1+alpha)` no caso padrão CLT/PJ mensal — custo deixa de estar subestimado em ~36% |
| Código morto removido | `b.py` perde 90 linhas de duplicata pré-refatoração |

### Negativas / Riscos

| Risco | Mitigação |
|---|---|
| Correção do α (D3) muda custo calculado de toda MO mensal CLT/mensalista sem override — pode quebrar benchmarks/golden tests | Rodar suíte completa + golden test após a mudança; re-baseline consciente se necessário (números sobem para o valor correto, não é regressão) |
| Migração de 41 arquivos de catálogo (D5) sem tool MCP de rascunho dedicada para `atributos_especificos` de insumo existente | Script idempotente `scripts/catalog/adr182_metodo_custo_total_h_unit.py` (dry-run + apply) editando JSON direto, seguido de `concilium catalog validate`/`quality` |

---

## Plano de Implementação

| Fase | Entregas | Status |
|---|---|---|
| 1 | `custo_ja_inclui_encargos()` + formalização Pydantic/JSON Schema | ✅ Feito |
| 2 | `pu_calculator._alpha()`/`_acumular_custo_mo` (D3/D4) | ✅ Feito |
| 3 | Consolidação dos 3 pontos de skill-05/04 (D1) | ✅ Feito |
| 4 | Remoção de código morto `b.py` (D6) | ✅ Feito |
| 5 | Migração de dados dos 41 insumos `unidade: h` (D5) | ✅ Feito |
| 6 | Testes (novos + adaptados + remoção dos que cobriam código morto) | ✅ Feito |

## Definition of Done

- [x] `custo_ja_inclui_encargos()` em `encargo_resolver.py`, usada pelos 4 pontos de cálculo
- [x] `metodo_custo_total`/`percentual_encargos_local` declarados em `AtributosInsumo` + `insumo.schema.json`
- [x] `_alpha()` corrige branch `tipo_contrato` para `1.0 + alpha_clt/alpha_pj` — confirmado por 3 fontes independentes (ADR-097, dado histórico do catálogo, metodologia SINAPI/SINDUSCON)
- [x] 41 insumos `unidade: h` migrados com `metodo_custo_total`
- [x] `b.py` sem código morto
- [x] Testes verdes (`test_encargo_resolver.py`, `test_pu_calculator_fuel_price.py`, `test_skill05_helpers_a_coverage.py`, `test_skill05_helpers_b.py`)

---

## Adendo — P4: `categoria_sindical` ausente nos 7 insumos `SV-OUV-MO-*` (2026-08-16)

Ao rodar o benchmark `MATA_DENSA_SIMPLES` (2 CPUs que referenciam exatamente os 7 insumos `SV-OUV-MO-*` de P3), achei que esses 7 têm `tipo_contrato: CLT` mas `categoria_sindical: None` — `pu_calculator._alpha()` decide por `tipo_contrato` (α=2,777), `encargo_resolver.resolver_encargo()` (skill-05) decide por `categoria_sindical` (ausente → default mensalista, α=2,06) — mesma classe de inconsistência de P1, ~35% de divergência entre os dois caminhos para o mesmo insumo.

Corrigido: `categoria_sindical: "horista_CE"` adicionado aos 7 (convenção dominante do catálogo, 72 outras ocorrências vs. 13 de `"horista"` puro).

**Não resolveu o GATE=INVIAVEL do benchmark** — reexecutado após o fix, `custo_execucao_pool` saiu idêntico (R$409.491,56, mesmo valor de antes). Confirmado que esse número vem do `CuboPoolInstancial` (ADR-086), um mecanismo de custo de pool separado que não passa por `encargo_resolver.resolver_encargo()` — a divergência de 3,04×/2,39× entre "custo autônomo" e "PU de catálogo" tem causa raiz diferente, ainda sob investigação (fora do escopo original desta ADR — provavelmente uma questão de calibração de `producao_horaria`/composição das CPUs `CPU-TERRA-ATI-041`/`044`, não de encargo). Mantido o fix de `categoria_sindical` de qualquer forma — é uma correção de dado legítima e independente.

## Relacionados

ADR-097, ADR-009, ADR-165, ADR-167, ADR-086
