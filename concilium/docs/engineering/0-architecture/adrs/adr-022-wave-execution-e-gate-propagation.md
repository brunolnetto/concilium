# ADR-022 — Wave Execution e Propagação de Falhas com Gate Blocking

**Status:** Implementado  
**Data:** 2026-05-04  
**Data Implementado:** 2026-05-04  
**Implementadores:** mcp_server/_context.py (_GATE_PREDECESSORS via SkillRegistry), mcp_server/tools/pipeline.py (gate blocking), models/canonical.py (pipeline_blocked_from, pipeline_integridade)  
**Contexto:** MendesLobo Construtora — Concilium

---

## Contexto

O pipeline de skills executa skills individuais em ordem topológica, mas o runtime atual
não possui um modelo formal de o que acontece quando uma skill falha e qual o impacto
permitido nos nós downstream.

O incidente "Recife PE" (2026-05-04) expôs dois modos de falha distintos:

### Modo A — Falha visível com bloqueio parcial

Skill 03-equipes-diretas falhou com `AttributeError` (tuple iteration).
Skills 06-consolidar e 07-adapter-saida pararam com `PRECONDICAO ERRO`.
Resultado: pipeline visivelmente quebrado.

### Modo B — Falha silenciosa com propagação sintética (o problema real)

Skill 03 falhou → `equipes_diretas = []` (lista vazia).  
Skill 05-indiretos executou com `canonical.equipes_diretas = []`:
- `custo_direto_total = sum(e.custo_total for e in equipes_diretas)` → **R$ 0,00**
- MOB calculado sobre R$ 0 → **MOB = R$ 0** (errado, silencioso)
- Custo total reportado: R$ 159.662,66 (1 semana de indiretos sem equipes)

Skills 13-replan-advisor e 14-plan-space-explorer executaram com `resultado.custo_total`
baseado neste valor corrompido e geraram sugestões de re-planejamento sobre dados inválidos.

O sistema não tinha como distinguir `equipes_diretas = []` (sem equipes no escopo)
de `equipes_diretas = []` (skill 03 falhou antes de popular o campo).

### Raiz estrutural

A propagação de dados entre skills é feita exclusivamente via campos do `CanonicalModel`.
Campos com valor-zero (lista vazia, `None`, `0.0`) são **morfologicamente indistinguíveis**
de campos não-calculados após falha de skill.

Qualquer skill downstream que agregar esses campos produzirá um resultado **numericamente
correto sobre entrada errada** — o pior tipo de defeito em sistemas financeiros.

---

## Decisões

### D1 — Execução em Waves (BFS Topológico)

O runtime executa o pipeline em **waves**: conjuntos de skills cuja totalidade de
predecessores **GATE** já executou com sucesso.

```
Wave 0:  00-escopo
Wave 1:  00A, 00B, 01-praticabilidade
Wave 2:  01A, 02-cronograma
Wave 3:  03-equipes-diretas, 04-planejamento-bdi
Wave 4:  03A-derivar-requisitos, 05-indiretos
Wave 5:  03B-alocacao-recursos, 06-consolidar
Wave 6:  03C, 06A-reconciliar-custos-recurso, 07-adapter-saida, 08-criticality
Wave 7:  09-cost-criticality, 10-intervention-roi
Wave 8:  13-replan-advisor
Wave 9:  14-plan-space-explorer
```

Dentro de uma wave, as skills são independentes entre si e podem executar em paralelo.
Uma wave só avança quando todas as skills GATE da wave anterior terminaram (com sucesso
ou com status `BLOQUEADO` propagado — ver D3).

### D2 — Classificação de Skills: GATE vs ADVISORY

Cada skill é classificada em seu `skill.toml` com `gate = true | false`.

**GATE** — falha bloqueia todos os descendentes dependentes:

| Skill | Campo crítico produzido | Por que bloqueia |
|-------|------------------------|------------------|
| `00-escopo` | `eap` | Sem EAP não há nada a orçar |
| `01-praticabilidade` | `praticabilidade` | Viabilidade não validada |
| `02-cronograma` | `cronograma` | Base temporal de custo e duração |
| `03-equipes-diretas` | `equipes_diretas` | Custo direto — base de MOB e 06 |
| `04-planejamento-bdi` | `planejamento` | Receita — base de margem em 06 |
| `06-consolidar` | `resultado` | Resultado financeiro — base de 13 e 14 |

**ADVISORY** — falha gera `status=DEGRADADO` nos descendentes mas não os bloqueia:

| Skill | Motivo ADVISORY |
|-------|-----------------|
| `00A-atividades` | 02 opera sobre itens da EAP diretamente |
| `00B-sequenciamento` | 02 roda sem DAG (heurística MINSLK) |
| `01A-declarar-recursos` | 03A auto-deriva pools |
| `03A-derivar-requisitos` | 03B pula se `requisitos = []` |
| `03B-alocacao-recursos` | Sem impacto financeiro direto |
| `03C-validar-compartilhamento` | Diagnóstico puro |
| `05-indiretos` | **Ver D4 — caso especial** |
| `06A-reconciliar-custos-recurso` | Enriquecimento, não base |
| `08` → `14` | Análise e re-planejamento, não custo base |

### D3 — Taint Marking: Campo `pipeline_blocked_from`

Quando uma skill GATE falha, o runtime adiciona seu ID ao campo do canônico:

```python
canonical.pipeline_blocked_from: list[str]  # IDs de skills GATE que falharam
```

O runtime consulta `pipeline_blocked_from` **antes** de executar qualquer skill:

```
PARA cada skill a executar:
  SE qualquer predecessor GATE está em pipeline_blocked_from:
    NÃO executar a skill
    Registrar: validacoes += [ValidacaoItem("VAL-BLOCKED", "BLOQUEADO",
                 f"Bloqueado por falha em: {predecessores_bloqueados}")]
    Adicionar skill ao pipeline_blocked_from
    Propagar bloqueio aos descendentes
```

O bloqueio propaga transitivamente: se 03 está em `pipeline_blocked_from`,
então 05, 06, 07, 13, 14 também serão marcados BLOQUEADO sem executar.

### D4 — Propagação Sintética Proibida: Pontos Sem Retorno

Os campos abaixo **não podem receber valores sintéticos ou padrão** quando sua
skill produtora falhou. Um campo vazio por falha de GATE deve permanecer vazio
— jamais será preenchido com 0.0, [], ou valores defaults pelo runtime.

| Campo canônico | Skill produtora (GATE) | Risco sintético |
|---------------|------------------------|-----------------|
| `equipes_diretas` | `03-equipes-diretas` | `custo_direto = R$ 0` → MOB = R$ 0, margem inflada |
| `planejamento` | `04-planejamento-bdi` | `venda = R$ 0` → margem = -∞ ou NaN |
| `resultado` | `06-consolidar` | Sugestões de replan sobre dados inválidos |
| `cronograma` | `02-cronograma` | Duração zero → custo permanência = R$ 0 |
| `praticabilidade` | `01-praticabilidade` | Parâmetros de viabilidade indefinidos |

**Regra de implementação:** Skills downstream que agregam esses campos DEVEM
verificar `pipeline_blocked_from` antes de qualquer agregação. A verificação
de `if not canonical.equipes_diretas` é **insuficiente** — a lista pode estar
vazia legitimamente (projeto sem equipes) ou por falha de GATE. Somente
`pipeline_blocked_from` distingue os dois casos.

### D5 — Skill 05-indiretos: Caso Especial (ADVISORY com Dependência Financeira)

Skill 05 é classificada ADVISORY (pode executar sem todas as equipes finalizadas),
mas possui uma dependência financeira de `equipes_diretas` no cálculo de MOB:

```python
mob = perfil["mob_pct"] * sum(e.custo_total for e in canonical.equipes_diretas)
```

Se `03-equipes-diretas` estiver em `pipeline_blocked_from`, skill 05 DEVE:
1. Calcular ADM, TOP, LAB, QSMS com os dados disponíveis
2. Registrar `VAL-INDIR-MOB-BLOQUEADO`: `status=AVISO`, MOB = `None` (não R$ 0)
3. NÃO somar MOB ao custo indireto total
4. Marcar `indiretos` com `parcial=True` no resultado

Isso garante que skill 06 veja custos indiretos parciais — e não custos indiretos
com MOB=0 silencioso que inflam artificialmente a margem calculada.

### D6 — Status de Execução no Canônico

O canônico passa a carregar um campo de auditoria de execução:

```python
class PipelineStatus(BaseModel):
    skills_executadas: list[str]          # skills com sucesso
    skills_bloqueadas: list[str]          # bloqueadas por D3
    skills_degradadas: list[str]          # ADVISORY com falha
    pipeline_blocked_from: list[str]      # GATE failures (fonte do bloqueio)
    frontier: list[str]                   # último wave completo com sucesso
    integridade: Literal["COMPLETO", "PARCIAL", "CORROMPIDO"]
```

`integridade`:
- `COMPLETO`: todas as skills GATE executaram com sucesso
- `PARCIAL`: algumas skills ADVISORY falharam; análises disponíveis mas degradadas
- `CORROMPIDO`: ao menos uma skill GATE está em `pipeline_blocked_from`;
  resultados financeiros NÃO devem ser usados para decisão de negócio

O MCP e a CLI DEVEM exibir `integridade = CORROMPIDO` proeminentemente antes
de apresentar qualquer resultado numérico.

---

## Consequências

1. **Runtime (`avancar_pipeline`)**: precisa consultar `pipeline_blocked_from`
   antes de despachar cada skill; atualizar `PipelineStatus` após cada execução.

2. **Skills GATE com precondição existente**: manter as verificações internas
   (`if not canonical.equipes_diretas`) como segunda linha de defesa, mas
   o runtime é a primeira linha.

3. **Skill 05-indiretos**: implementar D5 — MOB explicitamente `None` quando
   skill 03 está bloqueada.

4. **MCP `consultar_status`**: deve expor `integridade` e `pipeline_blocked_from`
   no primeiro campo da resposta.

5. **Checkpoints (ADR-019 D1)**: um checkpoint só é válido se a skill de origem
   não está em `pipeline_blocked_from` da versão de onde se parte.

6. **Testes**: casos de teste devem cobrir o cenário "03 falha, 05 não propaga
   MOB=0, 06 reflete custo parcial, `integridade=CORROMPIDO`".

---

## Alternativas Rejeitadas

### Alt-A — Precondições em cada skill (status quo)
Cada skill verifica seus próprios pré-requisitos. Rejeitado: requer que cada
desenvolvedor de skill conheça e implemente todas as dependências corretas.
O incidente Recife PE mostrou que essa abordagem falha quando a lista está
morfologicamente vazia mas semanticamente inválida.

### Alt-B — Valores sentinela no canônico (ex: `equipes_diretas = None`)
Usar `None` em vez de `[]` para campos não-calculados. Rejeitado: quebra
o invariante de que o canônico é sempre um objeto válido e serializável;
exigiria mudanças em todos os consumidores do campo.

### Alt-C — Wave execution sem GATE/ADVISORY (bloquear tudo na primeira falha)
Parar o pipeline inteiro na primeira falha. Rejeitado: skills de análise
(08–14) são independentes do custo e têm valor mesmo com pipeline parcial.
O objetivo é maximizar informação útil, não maximizar pureza.

---

## Validações Novas

| Código | Origem | Significado |
|--------|--------|-------------|
| `VAL-BLOCKED` | Runtime | Skill não executada por bloqueio GATE upstream |
| `VAL-INDIR-MOB-BLOQUEADO` | 05-indiretos | MOB omitido; skill 03 bloqueada |
| `VAL-INTEGRITY-CORROMPIDO` | Runtime / MCP | `integridade=CORROMPIDO`; resultados financeiros inválidos |
| `VAL-INTEGRITY-PARCIAL` | Runtime / MCP | `integridade=PARCIAL`; análises degradadas mas resultados financeiros válidos |

## Definition of Done

- [x] Wave/BFS topological execution in runtime: skills advance in waves by GATE predecessor completion
- [x] GATE vs ADVISORY classification per skill in `skill.toml` (`gate = true | false`)
- [x] `_GATE_PREDECESSORS` map in `mcp_server/_context.py` via `SkillRegistry`
- [x] Gate blocking in `mcp_server/tools/pipeline.py`: GATE failure adds skill to `pipeline_blocked_from` and blocks all descendants
- [x] `pipeline_blocked_from: list[str]` field in `CanonicalModel`
- [x] Transitive taint propagation: skills whose GATE predecessor is in `pipeline_blocked_from` are marked BLOQUEADO without executing
- [x] Skill 05-indiretos D5 special case: MOB set to `None` (not R$ 0) when skill 03 is blocked; `VAL-INDIR-MOB-BLOQUEADO` emitted; `parcial=True` in indiretos result
- [x] `pipeline_integridade: Literal["COMPLETO", "PARCIAL", "CORROMPIDO"]` in `CanonicalModel`
- [x] `integridade=CORROMPIDO` displayed prominently by MCP and CLI before any financial result
- [x] `consultar_status` exposes `integridade` and `pipeline_blocked_from` as first-class response fields
- [x] VAL-BLOCKED: skill not executed due to upstream GATE failure
- [x] VAL-INDIR-MOB-BLOQUEADO: MOB omitted; skill 03 blocked
- [x] VAL-INTEGRITY-CORROMPIDO: at least one GATE skill in `pipeline_blocked_from`
- [x] VAL-INTEGRITY-PARCIAL: some ADVISORY skills failed; financial results valid
- [x] Tests: "03 fails → 05 does not propagate MOB=0 → 06 reflects partial cost → `integridade=CORROMPIDO`"
