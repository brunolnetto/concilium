# ADR-028 — Classificação de Fatores Tunáveis vs Externos no Balanço de Margem

**Status:** Implementado
**Data:** 2026-05-04
**Data Implementado:** 2026-05-04
**Implementadores:** models/canonical.py (ControleVariavel, BalancoControle, campo em Resultado e Lever), skills/06-consolidar/skill.py (balanco_de_controle), skills/14-plan-space-explorer/skill.py (ControleVariavel em Lever), skills/13-replan-advisor/skill.py (ControleVariavel em ReplanSugestao)
**Contexto:** MendesLobo Construtora — Concilium

---

## Contexto

### Problema

O `resultado` de skill 06 produz `margem_pct` e `status_margem`, mas não distingue *por que* a margem está abaixo da meta. A totalidade do gap é apresentada como se fosse igualmente fechável por decisão do engenheiro — quando parte do gap pode ser estrutural dado o contexto externo (tabela SINAPI vigente, combustível, impostos da jurisdição, praticabilidade sazonal).

Os levers em skills 13 e 14 (EXPAND_POOL, REDUCE_DURATION, ADD_TEAMS, REVIEW_BDI) estão todos implicitamente tratados como ações livres — sem marcar se o engenheiro efetivamente controla aquela variável ou se ela é parcialmente constrangida por fatores fora do projeto.

Consequência: o sistema pode sugerir "REVIEW_BDI: ganho de 1.8pp" quando o BDI está determinado pela jurisdição fiscal; ou "REDUCE_DURATION: ganho de 2pp" quando a praticabilidade sazonal fixa a janela de trabalho. O engenheiro não tem como distinguir, a partir da saída do sistema, qual gap é fechável e qual é residual.

### Enunciado correto do problema de otimização

$$\max_{x \in \mathcal{T}} \; \text{margem}(x, \bar{e}) \quad \text{s.a.} \quad \text{viável}(x), \quad \text{margem}(x, \bar{e}) \geq \text{meta}$$

onde:
- $x$ = variáveis de decisão **tunáveis** pelo engenheiro
- $\bar{e}$ = fatores **externos** dados, não controláveis

O sistema até aqui trata tudo como $x$. Este ADR introduz a separação explícita.

---

## Decisão

### D1 — `ControleVariavel`: enum de classificação de controle

```python
ControleVariavel = Literal["TUNAVEL", "SEMI_TUNAVEL", "EXTERNO"]
```

| Classe | Definição | Exemplos |
|---|---|---|
| `TUNAVEL` | Variável que o engenheiro decide diretamente, sem aprovação externa | `num_equipes`, `algorithm/deadline`, escolha de CPU (mesma categoria), regime de trabalho |
| `SEMI_TUNAVEL` | Pode ser influenciada, mas sujeita a aprovação, disponibilidade ou negociação | tamanho do pool (sujeito a procurement), rebalanceamento de BDI dentro de faixas do perfil |
| `EXTERNO` | Determinada por fatores fora do projeto | tabela SINAPI/SICRO vigente, alíquota de ISS da jurisdição, índice de combustível, fator de praticabilidade sazonal |

### D2 — `ControleVariavel` nos modelos `Lever` e `ReplanSugestao`

```python
class Lever(BaseModel):
    ...
    controle: ControleVariavel = "TUNAVEL"  # campo novo com default seguro
```

```python
class ReplanSugestao(BaseModel):
    ...
    controle: ControleVariavel = "TUNAVEL"  # campo novo
```

Classificação aplicada por tipo de lever:

| Tipo | Classificação | Justificativa |
|---|---|---|
| `EXPAND_POOL` | `SEMI_TUNAVEL` | Requer procurement — disponibilidade de mercado não garantida |
| `REDUCE_DURATION` | `TUNAVEL` | Parâmetro diretamente configurável em `02-cronograma` |
| `ADD_TEAMS` | `TUNAVEL` | Input direto de `03-equipes-diretas` |
| `REVIEW_BDI` | `SEMI_TUNAVEL` | Dentro de faixas do perfil (`perfis/agis.json`); não livre arbitrariamente |

### D3 — `BalancoControle` em `Resultado` (skill 06)

```python
class BalancoControle(BaseModel):
    gap_total_pp: float            # margem_meta - margem_atual em pontos percentuais
    gap_fechavel_pp: float         # porção do gap redutível por variáveis TUNAVEL
    gap_semi_tunavel_pp: float     # porção redutível por SEMI_TUNAVEL
    gap_externo_pp: float          # porção estrutural — não fechável por decisão
    viavel_por_decisao: bool       # gap_fechavel + gap_semi_tunavel >= gap_total
    principais_fatores_externos: list[str]  # ex: ["SINAPI", "ISS_JURISDICAO", "PRATICABILIDADE"]
```

`BalancoControle` é calculado em skill 06 com base nas fontes de custo:

- **Gap externo** = parcela do custo determinada por fatores externos identificáveis:
  - Custo de insumos com `fonte_preco = "SINAPI"` ou `"SICRO"` (lidos via catálogo)
  - Alíquotas fiscais da jurisdição (do `contexto.jurisdicao`)
  - Custo adicional de praticabilidade (quando `pct_completude < 1.0` no cronograma)
- **Gap tunável** = parcela endereçável diretamente pelo engenheiro (escolha de equipe, deadline)
- **Gap semi-tunável** = procurement e BDI dentro de faixas

**Na fase 1** (sem acesso ao catálogo dentro da skill 06), o balanço usa uma decomposição simplificada baseada nas categorias de custo:
```
custo_externo_estimado ≈ custo_diesel + custo_materiais_sinapi
custo_tunavel_estimado ≈ custo_mo_equipe_propria
custo_semi_tunavel_estimado ≈ custo_equipamento + custo_adm_bdi
```

`Resultado` recebe campo novo:
```python
class Resultado(BaseModel):
    ...
    balanco_de_controle: BalancoControle | None = None
```

### D4 — Skills 13 e 14 expõem `controle` em cada sugestão/lever

Skill 13 (`replan-advisor`) adiciona `controle` a cada `ReplanSugestao`:
- REPLAN-001 (EXPAND_POOL) → `SEMI_TUNAVEL`
- REPLAN-002 (ADD_TEAMS) → `TUNAVEL`
- REPLAN-003 (REDUCE_DURATION) → `TUNAVEL`
- REPLAN-004 (REVIEW_BDI) → `SEMI_TUNAVEL`

Skill 14 (`plan-space-explorer`) adiciona `controle` a cada `Lever` ao construí-los em `_build_levers`.

### D5 — MCP: `consultar_status` expõe `balanco_de_controle`

Quando `canonical.resultado.balanco_de_controle` está populado, `consultar_status` inclui na resposta:
```json
"balanco_de_controle": {
  "gap_total_pp": 4.5,
  "gap_fechavel_pp": 2.8,
  "gap_semi_tunavel_pp": 1.0,
  "gap_externo_pp": 0.7,
  "viavel_por_decisao": true,
  "principais_fatores_externos": ["SINAPI", "PRATICABILIDADE"]
}
```

---

## Alternativas Consideradas

| Alternativa | Razão para Rejeição |
|---|---|
| Não classificar — deixar a decisão 100% ao engenheiro | Omite informação disponível no sistema; o engenheiro pode não saber que BDI é parcialmente travado pela jurisdição |
| Score único de "controlabilidade" (0–1) | Retoma o problema de escores sintéticos (ADR-020) — colapsa informação categórica em número sem fundamento |
| Classificar apenas levers sem tocar em `Resultado` | Perde o balanço agregado — o engenheiro precisa saber o gap total e qual fração é endereçável |
| Cálculo de custo externo via catálogo dentro de skill 06 | Skill 06 não acessa catálogo diretamente (opera sobre canônico já computado). Usa decomposição por categoria de custo como proxy conservador |

---

## Consequências

### Positivas
- **Expectativas realistas:** o engenheiro sabe imediatamente se o gap é estrutural (EXTERNO) ou corrigível (TUNAVEL)
- **Rastreabilidade de decisão:** levers com `controle: SEMI_TUNAVEL` exigem confirmação de procurement — o sistema sinaliza isso explicitamente
- **Fundamento para ADR-027:** a parcela de custo externo inclui exposição a diesel/SINAPI, que ADR-027 deriva por CPU — os dois ADRs se complementam

### Negativas / Riscos
- **Decomposição simplificada na Fase 1:** `BalancoControle` em skill 06 usa categorias de custo como proxy para fatores externos, não leitura direta das fontes de preço dos insumos. Pode sub ou superestimar ligeiramente a parcela externa
  - Mitigação: campo `fonte: "ESTIMADO"` indica ao usuário que é aproximação. Refinamento futuro via skill nova ou enriquecimento de skill 06 com acesso ao catálogo via `runtime`
- **`ControleVariavel` é estático por tipo de lever:** um `EXPAND_POOL` é sempre `SEMI_TUNAVEL` mesmo que o projeto tenha o equipamento em estoque próprio. Refinamento futuro pode torná-lo dinâmico

---

## Definition of Done

- [x] `models/canonical.py` — adicionar `ControleVariavel`, `BalancoControle`, campo `balanco_de_controle` em `Resultado`, campo `controle` em `Lever`
- [x] `models/canonical.py` — adicionar campo `controle: ControleVariavel = "TUNAVEL"` em `ReplanSugestao`
- [x] `skills/06-consolidar/skill.py` — calcular e popular `BalancoControle` no `Resultado`
- [x] `skills/14-plan-space-explorer/skill.py` — adicionar `controle` a cada `Lever` em `_build_levers`
- [x] `skills/13-replan-advisor/skill.py` — adicionar `controle` a cada `ReplanSugestao`
- [x] Testes: `test_balanco_de_controle_vermelho`, `test_balanco_de_controle_verde`, `test_lever_controle_classificado`, `test_replan_sugestao_controle`

---

## Referências

- **ADR-021:** Plan Space Explorer — `Lever`, `RepairPath`, `OportunidadeVerde`
- **ADR-019:** Replanning Strategy — `ReplanSugestao`, `ReplanSuggestions`
- **ADR-020:** Criticidade Multi-Dimensional — precedente de "classificar em vez de combinar"
- **ADR-027:** CPU Sensitivity Profile — fonte de dados para identificar quais CPUs contribuem para a parcela EXTERNO
