# ADR-130 — Composição de Equipe como Grafo de Sinergia: Produtividade Derivada do Gargalo

**Status:** ⚠️ Parcialmente Implementado — F1-F3 e D5 completos como motor de domínio puro (`src/concilium/domain/services/sinergia_equipe.py`) com cobertura de teste (36 testes); F4 (dados reais do benchmark AGIS) e integração de F5 com o fluxo de calibração ADR-076 pendentes — o catálogo atual não tem `capacidade_horaria` (m³/h por equipamento) medida em campo, só custo (R$/h); ver Definition of Done por fase
**Data:** 2026-07-06
**Contexto:** MendesLobo Construtora — Concilium
**Dependências:** ADR-011 (produtividade computável), ADR-030 (composição tipada de equipes), ADR-053 (separação CPU × Produtividade), ADR-076 (calibração de PU), ADR-128 (disponibilidade de consumíveis)

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

`CapacidadeElemento.fonte` rastreia proveniência. O fluxo de calibração do ADR-076, que hoje ajusta `valor_horario` como escalar opaco, ganha um alvo estruturado: a medição de campo atualiza a capacidade do **elemento gargalo** (`fonte="medicao_obra"`), e a produtividade re-deriva — preservando a explicação. Isso confina o risco de staleness (P4) aos poucos números de `capacidades`, mantendo `relacoes` estável.

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
| Curadoria: catálogo atual tem 0 CPUs com grafo — funcionalidade nasce inerte | Popular primeiro as famílias de maior peso no benchmark AGIS (terraplenagem/escavação), onde a planilha de referência já discrimina ciclo e frota; medir adoção antes de expandir |
| Modelo min-de-capacidades é simplificação (ignora interferência, fila, rampa) | Aceito por design — é o degrau intermediário entre escalar declarado e simulador (A1); estrutura permite refinamento futuro sem quebrar o contrato |
| Divergência derivado × declarado pode gerar ruído de AVISO em massa | Threshold de 15% em `VAL-SINERGIA-02` ajustável por perfil; AVISO (não ERRO) por decisão D3 |
| `capacidade_horaria` na unidade da CPU exige conversão para equipamentos multi-serviço | Reusar `UnitConversionService` (ADR-034); ERRO de validação se unidade incompatível |

---

## Plano de Implementação

| Fase | Entregas | Status |
|---|---|---|
| **F1 — Modelos** | `RelacaoSinergia`, `CapacidadeElemento`, `GrafoSinergiaEquipe` no domínio de Produtividade (ADR-053); `VAL-SINERGIA-01` | ✅ |
| **F2 — Derivação** | Motor de derivação (D2) + precedência (D3) como serviço de domínio puro (`resolver_producao_efetiva`); `VAL-SINERGIA-02/03` | ✅ |
| **F3 — Reatividade** | Re-derivação em mudança de composição (`revalidar_apos_mudanca_composicao`); `VAL-SINERGIA-04/05` | ✅ (como serviço puro; não conectado ao read-path de skill-03/05 — ver nota abaixo) |
| **F4 — Dados** | Grafos para as famílias de terraplenagem/escavação do benchmark AGIS (planilha já discrimina ciclo/frota) | ❌ Não implementado |
| **F5 — Calibração** | ADR-076 atualiza `CapacidadeElemento` do gargalo (`fonte="medicao_obra"`) em vez do escalar `valor_horario` | ⚠️ Função `atualizar_capacidade_gargalo` implementada e testada; integração real com o fluxo de calibração ADR-076 pendente |

F1–F2 são o caminho crítico e estão completos. F4 é pré-requisito para F3/F5 produzirem valor (lição do ADR-106/F5: não conectar read-path com dado vazio) — **por isso o motor de F2/F3/F5 foi implementado como serviço de domínio puro, consultivo, e deliberadamente ainda não foi ligado à skill-03/05**: o catálogo (`config/catalogos/mendeslobo`) hoje tem 0 CPUs com `GrafoSinergiaEquipe` populado, e os insumos de equipamento (ex. `EQ-ESCAV-HID-38T`, `EQ-CAM-BASC-14M3`) só carregam `preco_unitario` (R$/h); não existe `capacidade_horaria` (m³/h, ciclo real de campo) no catálogo para nenhuma família — ligar o read-path agora repetiria o erro do ADR-106/F5 (conectar a um dado vazio). F4 fica para quando essa medição de campo existir; inventar números para "fechar" a fase violaria a própria justificativa da ADR (D5 — capacidades são o alvo real da calibração, não um preenchimento sintético).

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
- [ ] Ligação ao fluxo real de `composicao_customizada` em skill-05 (`_dimensionamento_orquestracao.py`) — não feita (ver nota F4 acima); hoje é chamada explícita a serviço de domínio, não automática no pipeline

### Fase 4
- [ ] ≥ 1 família do benchmark AGIS com grafo populado e `producao_horaria_derivada` reconciliando com `valor_horario` declarado (delta < 15%) — **não feito**: catálogo não tem capacidade horária real por equipamento (só custo R$/h); sem esse dado, popular o grafo exigiria inventar números, o que a ADR e a política do projeto proíbem

### Fase 5
- [x] `atualizar_capacidade_gargalo` (D5) implementado e testado: identifica o gargalo derivado, atualiza sua `CapacidadeElemento.capacidade_horaria`/`fonte`, preserva `relacoes` e nunca toca `valor_horario` diretamente
- [ ] Integração com o fluxo real de calibração do ADR-076 (hoje ADR-076 atualiza `valor_horario` diretamente; chamar `atualizar_capacidade_gargalo` a partir desse fluxo não foi feito) — depende de F4

---

## Relacionados

- ADR-011 — Produtividade computável (a emergência narrada lá passa a ser computada aqui)
- ADR-030 — Composição tipada de equipes (elementos referenciados pelo grafo)
- ADR-053 — Separação CPU × Produtividade (o grafo vive no domínio de Produtividade)
- ADR-076 — Calibração de PU (F5: alvo estruturado da calibração)
- ADR-016 / ADR-133 — Compartilhamento de recursos *entre* atividades (altitude complementar)
- ADR-128 — Disponibilidade de consumíveis (relação `precondicao` de material)
- ADR-106 — EquipeCustoEngine (lição F5: não ativar read-path sem dado de catálogo)
