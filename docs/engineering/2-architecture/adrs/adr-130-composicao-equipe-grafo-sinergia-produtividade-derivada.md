# ADR-130 — Composição de Equipe como Grafo de Sinergia: Produtividade Derivada do Gargalo

**Status:** ⚠️ Parcialmente Implementado — F1-F3 completos, incluindo ligação real ao read-path de skill-05 e ao write-back de calibração (`CatalogUpdater`); F4 tem dados reais para o catálogo `rfi-r02` (75 CPUs / 7 clusters, terraplenagem/escavação, PR #91), mas **não** para o catálogo `mendeslobo` (primário) — ver Definition of Done por fase e nota de implementação abaixo
**Data:** 2026-07-06
**Contexto:** MendesLobo Construtora — Concilium
**Dependências:** ADR-011 (produtividade computável), ADR-017 (CatalogUpdater/PropostaAtualizacao — mecanismo real de write-back de F5), ADR-030 (composição tipada de equipes), ADR-053 (separação CPU × Produtividade), ADR-076 (calibração de PU — a decisão conceitual; a implementação de write-back é ADR-017), ADR-128 (disponibilidade de consumíveis)

---

## Contexto

### Problema

P1. **Engenheiros de planejamento não confiam nas composições e produtividades de referência (SINAPI, SICRO, GoInfra) e recompõem do zero.** O motivo estrutural: essas referências publicam a *lista* de insumos e o *número final* de produção horária, mas não a **estrutura de sinergia** que os liga — dependência equipamento↔mão-de-obra (operador e escavadeira são um par indissociável), mão-de-obra↔mão-de-obra (encarregado dimensiona frentes), e mão-de-obra/equipamento↔material (a equipe inteira para se o material não chega). Quando o contexto da obra muda (DMT, frota disponível, logística de material), o engenheiro não tem como ajustar o número de forma justificada — e descarta a referência inteira.

P2. **O modelo atual reproduz exatamente essa limitação.** `ComposicaoPadraoEquipe` (ADR-030) é uma lista plana — `funcoes: list[FuncaoEquipe]`, `equipamentos: list[EquipamentoEquipe]`, `materiais: list[MaterialEquipe]` — e a produtividade (`Producao.valor_horario`, ADR-053) é um escalar *declarado ao lado* dessa lista, não *derivado* dela. Não existe nenhuma estrutura que expresse que os elementos interagem: que os 7 caminhões da CPU de escavação existem em função do ciclo da escavadeira, que a produção da equipe é a do **recurso gargalo** (não a soma das capacidades individuais), ou que material é pré-condição de operação. O ADR-011 documenta que a produtividade "emerge da composição da CPU", mas a emergência é narrativa (planilha AGIS) — não é computada pelo sistema.

P3. **Sem estrutura de sinergia, não há resposta computável para perguntas de replanejamento reais.** "Se eu trocar a escavadeira de 38T por uma de 25T, quantos caminhões preciso e qual a nova produção?" — hoje a resposta exige recompor a CPU manualmente e re-declarar `valor_horario`. O sistema não sabe qual elemento é gargalo, então qualquer variação de frota/equipe invalida silenciosamente a produtividade declarada, sem nenhum `VAL-*` que o detecte.

P4. **O risco de um modelo de processo completo é staleness.** Um simulador de processo construtivo pleno (tempo de ciclo, fila, DMT, empolamento, física por família de serviço) exige um volume de parâmetros que tende a estagnar com o tempo — o mesmo destino do SINAPI. A observação-chave que viabiliza esta ADR: **a sinergia é majoritariamente estrutural, não paramétrica**. "A escavadeira é o gargalo; caminhões são dimensionados pelo ciclo dela; material é pré-condição" é conhecimento de processo que quase não muda. O que muda (ciclos medidos, capacidades, disponibilidades) são poucos parâmetros pendurados nessa estrutura — e é neles que a calibração contra obra real (ADR-076) deve atuar.

### Escopo e altitude

Esta ADR trata da sinergia **intra-equipe** (dentro de uma `ComposicaoPadraoEquipe`/CPU). Dependências **entre atividades** já são cobertas por ADR-016 (taxonomia de compartilhamento de recursos) e ADR-133 (compartilhamento em atividades paralelas) — altitudes distintas, sem sobreposição.

---

## Decisão

### D1 — `GrafoSinergiaEquipe`: a composição ganha estrutura de dependência

Novo artefato opcional na especificação da equipe (catálogo, domínio de Produtividade conforme ADR-053), declarando três tipos de relação entre os elementos já existentes da composição:

```python
class RelacaoSinergia(BaseModel):
    """Aresta do grafo de sinergia intra-equipe."""

    model_config = ConfigDict(extra="forbid")

    tipo: Literal[
        "acoplamento",      # A e B operam como par indissociável (operador ↔ escavadeira)
        "dimensionamento",  # quantidade de B é função da capacidade de A (caminhões ← ciclo da escavadeira)
        "precondicao",      # B só opera se A disponível (equipe ← material na frente)
    ]
    origem: str   # ref a FuncaoEquipe.funcao_id | EquipamentoEquipe.equip_id | MaterialEquipe.insumo_id
    destino: str
    razao: float | None = None   # dimensionamento: unidades de destino por unidade de capacidade de origem
    descricao: str | None = None


class CapacidadeElemento(BaseModel):
    """Parâmetro de capacidade de um elemento da composição — os poucos números que mudam."""

    model_config = ConfigDict(extra="forbid")

    elemento_id: str
    capacidade_horaria: float = Field(gt=0)   # na unidade de produção da CPU (ex.: m³/h)
    unidade: str
    fonte: Literal["catalogo", "fabricante", "medicao_obra"] = "catalogo"


class GrafoSinergiaEquipe(BaseModel):
    """Estrutura de sinergia da equipe: relações + capacidades. Opcional por CPU."""

    model_config = ConfigDict(extra="forbid")

    relacoes: list[RelacaoSinergia] = Field(default_factory=list)
    capacidades: list[CapacidadeElemento] = Field(default_factory=list)
    gargalo_declarado: str | None = None   # elemento_id; se None, derivado (D2)
```

A separação estrutura × parâmetro é deliberada (mitiga P4): `relacoes` é conhecimento de processo estável; `capacidades` é o conjunto pequeno de números sujeito a recalibração (ADR-076, `fonte="medicao_obra"`).

### D2 — Produtividade derivada do gargalo

Quando `GrafoSinergiaEquipe` está presente e possui capacidades, a produtividade da equipe passa a ser **computada**:

```
producao_horaria_derivada = min(
    capacidade_efetiva(e) para cada elemento e com capacidade declarada
)

onde capacidade_efetiva considera:
  - acoplamento: par opera na capacidade do menor dos dois
  - dimensionamento: capacidade do conjunto destino = n_unidades × capacidade_unitaria,
    saturada pela capacidade da origem (não adianta caminhão além do ciclo da escavadeira)
  - precondicao: não altera a taxa; expõe o risco via ADR-128
    (disponibilidade de consumíveis) quando o material tem DisponibilidadeConsumivel
```

O gargalo é o elemento cuja capacidade efetiva realiza o mínimo (ou `gargalo_declarado`, se informado — com validação de consistência, D4).

### D3 — Precedência e fallback: coeficientes atuais continuam válidos

Nenhuma CPU é obrigada a ter grafo. Precedência de resolução da produtividade em skill-03/05:

1. `Producao.valor_horario` calibrado contra obra real (ADR-076) — medição vence modelo
2. `producao_horaria_derivada` do `GrafoSinergiaEquipe` (esta ADR)
3. `Producao.valor_horario` declarado (estado atual — fallback integral)

Quando (2) e (3) coexistem, a divergência é reportada (D4), mas o valor calibrado/declarado prevalece até decisão explícita do engenheiro — o grafo entra como **explicação e instrumento de ajuste**, não como sobrescrita silenciosa.

### D4 — Validações novas

| Código | Status | Condição |
|---|---|---|
| `VAL-SINERGIA-01` | ERRO | `RelacaoSinergia.origem/destino` não referencia elemento existente na composição |
| `VAL-SINERGIA-02` | AVISO | `producao_horaria_derivada` diverge > 15% do `valor_horario` declarado |
| `VAL-SINERGIA-03` | AVISO | `gargalo_declarado` não coincide com o gargalo derivado das capacidades |
| `VAL-SINERGIA-04` | INFO | Composição alterada (frota/equipe) com grafo presente → produtividade re-derivada automaticamente |
| `VAL-SINERGIA-05` | AVISO | Relação `dimensionamento` com `razao` violada pela composição atual (ex.: caminhões insuficientes para o ciclo do gargalo) |

`VAL-SINERGIA-04/05` são a resposta computável a P3: variação de composição deixa de invalidar silenciosamente a produtividade.

### D5 — Ciclo de vida dos parâmetros: capacidades são o alvo da calibração

`CapacidadeElemento.fonte` rastreia proveniência. O fluxo real de write-back de calibração — `CatalogUpdater.apply_update`/`_update_producao` (ADR-017 §D5), acionado por uma `PropostaAtualizacao` aprovada — ganha um alvo estruturado além do escalar `valor_horario`: quando `proposta.campo == "capacidade_horaria"`, a medição de campo atualiza a capacidade do **elemento gargalo** (`fonte="medicao_obra"`) via `atualizar_capacidade_gargalo`, e a produtividade re-deriva — preservando a explicação. Isso confina o risco de staleness (P4) aos poucos números de `capacidades`, mantendo `relacoes` estável. (Nota: ADR-076 é a decisão conceitual de calibração de PU, mas sua implementação — `_ponto_equilibrio.py` — é diagnóstico-only e nunca escreve no catálogo; o mecanismo real de escrita sempre foi `CatalogUpdater`.)

---

## Alternativas Rejeitadas

| ID | Alternativa | Motivo |
|---|---|---|
| A1 | Simulador de processo construtivo completo (ciclo, fila, DMT, empolamento por família de serviço) | Volume de parâmetros por família tende a estagnar (o problema do SINAPI reproduzido internamente); custo de modelagem por família de processo é alto e o valor incremental sobre gargalo+acoplamento não se sustenta sem dado de campo que hoje não existe |
| A2 | Enriquecer apenas os coeficientes (mais campos numéricos em `ComposicaoPadraoEquipe`) | Não expressa relação entre elementos — não responde P3 (troca de equipamento) nem P1 (justificar ajuste ao contexto); mais parâmetros sem estrutura agrava staleness |
| A3 | Produtividade derivada sobrescreve a declarada quando grafo presente | Sobrescrita silenciosa quebraria benchmarks calibrados (mesma lição do ADR-106/F5); divergência deve ser exposta (`VAL-SINERGIA-02`), decisão é do engenheiro |
| A4 | Modelar sinergia no nível de atividade/cronograma (estender ADR-133) | Altitude errada — ADR-133 trata compartilhamento *entre* atividades; a sinergia aqui é interna à equipe da CPU, dado de catálogo/produtividade (ADR-053), não de schedule |
| A5 | Grafo obrigatório para toda CPU nova | A maioria das CPUs não terá esse dado no curto prazo; obrigatoriedade travaria curadoria do catálogo (mesma razão do ADR-128/A2) |

---

## Consequências

### Positivas

| Efeito | Descrição |
|---|---|
| Confiança na referência | Engenheiro vê *por que* a equipe rende X (gargalo explícito) e ajusta ao contexto da obra de forma justificada, em vez de descartar a composição |
| Replanejamento computável | Troca de equipamento/frota re-deriva produtividade e emite `VAL-SINERGIA-04/05` — responde P3 |
| Staleness confinado | Estrutura (`relacoes`) estável; apenas `capacidades` exigem manutenção, e são o alvo natural da calibração ADR-076 |
| Ponte com ADR-128 | `precondicao` de material conecta a sinergia MO↔material à disponibilidade de consumíveis no RCPSP |
| Retrocompatibilidade total | Grafo opcional; fallback integral para `valor_horario` declarado (D3) |

### Negativas / Riscos

| Risco | Mitigação |
|---|---|
| Curadoria: catálogo primário (`mendeslobo`) ainda tem 0 CPUs com grafo | Mitigado parcialmente: `rfi-r02` já tem 75 CPUs / 7 clusters de terraplenagem/escavação populados (PR #91) e o wiring F3/F5 provado ponta-a-ponta contra esse dado real; medir adoção antes de expandir para `mendeslobo` |
| Modelo min-de-capacidades é simplificação (ignora interferência, fila, rampa) | Aceito por design — é o degrau intermediário entre escalar declarado e simulador (A1); estrutura permite refinamento futuro sem quebrar o contrato |
| Divergência derivado × declarado pode gerar ruído de AVISO em massa | Threshold de 15% em `VAL-SINERGIA-02` ajustável por perfil; AVISO (não ERRO) por decisão D3 |
| `capacidade_horaria` na unidade da CPU exige conversão para equipamentos multi-serviço | Reusar `UnitConversionService` (ADR-034); ERRO de validação se unidade incompatível |

---

## Plano de Implementação

| Fase | Entregas | Status |
|---|---|---|
| **F1 — Modelos** | `RelacaoSinergia`, `CapacidadeElemento`, `GrafoSinergiaEquipe` no domínio de Produtividade (ADR-053); `VAL-SINERGIA-01` | ✅ |
| **F2 — Derivação** | Motor de derivação (D2) + precedência (D3) como serviço de domínio puro (`resolver_producao_efetiva`); `VAL-SINERGIA-02/03` | ✅ |
| **F3 — Reatividade** | Re-derivação em mudança de composição (`revalidar_apos_mudanca_composicao`); `VAL-SINERGIA-04/05`; ligação ao read-path real de skill-05 | ✅ Motor puro completo; **ligado ao read-path real de `_dimensionamento_orquestracao.py`/`_dimensionamento_itens.py`** (skill-05) — ver nota abaixo |
| **F4 — Dados** | Grafos para as famílias de terraplenagem/escavação do benchmark AGIS (planilha já discrimina ciclo/frota) | ⚠️ Feito para `rfi-r02` (75 CPUs / 7 clusters, PR #91); **não feito** para `mendeslobo` (catálogo primário) |
| **F5 — Calibração** | Fluxo real de calibração atualiza `CapacidadeElemento` do gargalo (`fonte="medicao_obra"`) em vez do escalar `valor_horario` | ✅ `atualizar_capacidade_gargalo` implementado, testado, e **ligado ao write-back real** (`CatalogUpdater._update_producao`, ADR-017) |

F1–F2 são o caminho crítico e estão completos. F4 permanecia pré-requisito para F3/F5 produzirem valor (lição do ADR-106/F5: não conectar read-path com dado vazio) — **por isso o motor de F2/F3/F5 foi implementado primeiro como serviço de domínio puro, consultivo, e só ligado às skills quando F4 deixou de estar vazio**: o PR #91 populou `GrafoSinergiaEquipe` para 75 CPUs / 7 clusters do catálogo `rfi-r02` (famílias de terraplenagem/escavação, com `capacidade_horaria` derivada de especificação de fabricante + parâmetros SICRO/DNIT, rastreada via `CapacidadeElemento.justificativa`). Com esse dado real disponível, F3 (read-path de skill-05) e F5 (write-back via `CatalogUpdater`) foram ligados nesta mesma leva de trabalho. O catálogo `mendeslobo` (primário) continua com 0 CPUs com `GrafoSinergiaEquipe` — para essas CPUs o wiring é um no-op total (fallback D3 integral), exatamente como antes desta ligação.

### Nota de implementação — limites conhecidos da ligação F3/F5

- **F3 (skill-05)**: `_validar_sinergia_producao` (em `_dimensionamento_itens.py`) reconstrói um `Producao` mínimo a partir do dict bruto do catálogo só para acionar `resolver_producao_efetiva` e coletar `VAL-SINERGIA-02/03` — os campos de rastreabilidade que o modelo `Producao` exige (`qualidade`, `auditoria`, `condicoes_calibracao`, `origem.tipo`) não existem no catálogo bruto e são preenchidos com placeholders inertes (não lidos por `resolver_producao_efetiva`). Chaves legadas do catálogo que não pertencem ao contrato tipado de `EquipamentoEquipe`/`FuncaoEquipe` (ex.: `consumo_litros_hora` em vez de `consumo_litros_hora_estimado`) são filtradas antes da reconstrução — a composição usada para custear a equipe continua sendo o dict bruto original, nunca a reconstrução tipada. Qualquer falha de validação nessa reconstrução (dado malformado) resulta em no-op silencioso (nenhuma validação de sinergia adicionada), nunca em exceção — a robustez do pipeline de custo não depende deste caminho.
- **F5 (`CatalogUpdater`)**: o caso especial `proposta.campo == "capacidade_horaria"` exige que a `Producao` alvo já tenha `GrafoSinergiaEquipe` com gargalo determinável — caso contrário `atualizar_capacidade_gargalo` levanta `ValueError`, que propaga por `apply_update` (uma proposta mal-direcionada falha alto, não corrompe o catálogo). Isso significa que F5 só é utilizável hoje para as CPUs do `rfi-r02` populadas pelo PR #91; para o catálogo `mendeslobo`, uma `PropostaAtualizacao` de `capacidade_horaria` falhará até que F4 exista para essas CPUs — comportamento esperado, não um bug.

## Definition of Done

### Fase 1
- [x] `GrafoSinergiaEquipe` opcional no modelo de Produtividade, `extra="forbid"`, serialização retrocompatível
- [x] `VAL-SINERGIA-01` com teste de referência órfã

### Fase 2
- [x] `producao_horaria_derivada` = min de capacidades efetivas (acoplamento, dimensionamento, saturação)
- [x] Precedência D3 testada: calibrado > derivado > declarado
- [x] `VAL-SINERGIA-02` emitido em divergência > 15%; valor declarado preservado

### Fase 3
- [x] Re-derivação em mudança de composição (`revalidar_apos_mudanca_composicao`) emite `VAL-SINERGIA-04`, testado com troca de composição
- [x] `VAL-SINERGIA-05` para razão de dimensionamento violada
- [x] Ligação ao read-path real de skill-05 (`_build_comp_para_item`/`_dimensionamento_itens.py`, via `_validar_sinergia_producao`): `resolver_producao_efetiva` é acionado para toda `Producao` com `grafo_sinergia` populado, e `VAL-SINERGIA-02/03` são surfaced na lista de validações real de `_build_dimensionamento`; no-op total (zero validações, custo idêntico) para as CPUs sem grafo — testado end-to-end com um CPU real do `rfi-r02`

### Fase 4
- [x] ≥ 1 família do benchmark AGIS com grafo populado e `producao_horaria_derivada` reconciliando com `valor_horario` declarado (delta < 15%) — **feito para `rfi-r02`**: PR #91 populou 75 CPUs / 7 clusters de terraplenagem/escavação, com `capacidade_horaria` derivada de especificação de fabricante + parâmetros SICRO/DNIT (rastreada em `CapacidadeElemento.justificativa`), reconciliando com `valor_horario` dentro de <1% para o exemplo verificado (`CPU-TERRA-ESCO-CARGA-1CAT-DMT2000`)
- [ ] Mesma cobertura para o catálogo `mendeslobo` (primário) — **não feito**: continua sem `capacidade_horaria` medida em campo para nenhuma família; popular o grafo aqui exigiria inventar números, o que a ADR e a política do projeto proíbem

### Fase 5
- [x] `atualizar_capacidade_gargalo` (D5) implementado e testado: identifica o gargalo derivado, atualiza sua `CapacidadeElemento.capacidade_horaria`/`fonte`, preserva `relacoes` e nunca toca `valor_horario` diretamente
- [x] Integração com o fluxo real de calibração: `CatalogUpdater._update_producao` (ADR-017 §D5) — não ADR-076, que é apenas diagnóstico (`_ponto_equilibrio.py`) e nunca escreve no catálogo — trata `proposta.campo == "capacidade_horaria"` como caso especial, chamando `atualizar_capacidade_gargalo` e aplicando o mesmo versionamento/auditoria do caminho genérico; `ValueError` (sem grafo/gargalo determinável) propaga sem corromper o catálogo. Utilizável hoje para as CPUs do `rfi-r02`; para `mendeslobo`, aguarda F4

---

## Relacionados

- ADR-011 — Produtividade computável (a emergência narrada lá passa a ser computada aqui)
- ADR-030 — Composição tipada de equipes (elementos referenciados pelo grafo)
- ADR-053 — Separação CPU × Produtividade (o grafo vive no domínio de Produtividade)
- ADR-076 — Calibração de PU (decisão conceitual; implementação é diagnóstico-only, não escreve no catálogo)
- ADR-017 — CatalogUpdater/PropostaAtualizacao (F5: mecanismo real de write-back, alvo estruturado da calibração)
- ADR-016 / ADR-133 — Compartilhamento de recursos *entre* atividades (altitude complementar)
- ADR-128 — Disponibilidade de consumíveis (relação `precondicao` de material)
- ADR-106 — EquipeCustoEngine (lição F5: não ativar read-path/write-back sem dado de catálogo)
