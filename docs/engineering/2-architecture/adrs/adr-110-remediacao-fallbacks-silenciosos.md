# ADR-110 — Remediação de Fallbacks Silenciosos

**Status:** Implementado ✅ _(F1–F7 2026-06-18)_  
**Data:** 2026-06-18  
**Contexto:** MendesLobo Construtora — Concilium  
**Dependências:** ADR-043 (Benchmark App Layer), ADR-085 (Custo Instancial), ADR-060 (Ponto de Equilíbrio), ADR-090 (BDI Sistemático)

---

## Contexto

### Problema

Uma auditoria codebase-wide em `src/concilium/` identificou seis categorias de fallbacks que geram
resultados incorretos de forma silenciosa — sem log, sem exceção, sem indicador no output.

**P1. Exceções genéricas engolidas em operações estruturais.**  
Blocos `except Exception: return None / pass` em resolução de CPU, loading de canonical, spec loader
e seletor de heurísticas absorvem falhas sem registro. O caller recebe `None` ou lista vazia sem saber
se "dado realmente não existe" ou "erro ao carregar".

Ocorrências confirmadas:

| Arquivo | Linha | Operação | Fallback |
|---|---|---|---|
| `application/services/concilium_service.py` | 168–173 | resolução de CPU em catálogo | `master_cpu = None` |
| `application/services/concilium_service.py` | 126–129 | busca em catálogo | `continue` silencioso |
| `application/services/concilium_service.py` | 256–259 | lista de versões de contexto | `versions = []` |
| `application/services/project/project_service.py` | 135–142 | load canonical por versão | `canonical = None` |
| `application/benchmarks/spec/spec_loader.py` | 230–233 | resolução de contexto/versão | `return None` |
| `application/scheduling/selector.py` | 183–184 | execução de heurística | `pass` |
| `application/benchmarks/cronograma_parser.py` | 75–83 | parse de produtividade (duplo) | `pass / pass` |
| `application/benchmarks/spec/referencia_enricher.py` | 58–64 | enriquecimento EAP (duplo) | `pass / pass` |
| `application/benchmarks/comparison/granular.py` | 15–18 | leitura de JSON de comparação | `return {}` |
| `application/benchmarks/execution/runner.py` | 231–232, 244–250 | metadata de benchmark store | `pass` |

**P2. Confusão semântica entre "dado ausente" (None) e "zero calculado" (0.0).**  
O padrão `x or 0.0` e `dict.get(key, 0.0)` em cálculos financeiros não distingue entre um insumo
sem preço (anomalia de dados) e um insumo com preço legitimamente zero (subsídio, estoque próprio).
Falha de leitura de dados e valor real zero produzem o mesmo número no output.

Ocorrências confirmadas em cálculos financeiros críticos:

| Arquivo | Linha | Campo | Risco |
|---|---|---|---|
| `domain/services/simulation.py` | 31, 44, 67 | `preco_unitario` (MO, equip., material) | custo zero mascara insumo ausente |
| `domain/services/simulation.py` | 77 | `valor_horario` (produtividade) | produtividade zero ≠ não encontrado |
| `domain/services/simulation.py` | 106 | `producoes.get(prod_id_ref, 0)` | produção zero ≠ ref. inválida |
| `application/services/_concilium_service_helpers.py` | 187–188 | `producao_horaria`, `quantitativo` | quantitativo zero ≠ campo ausente |
| `application/services/_concilium_service_helpers.py` | 221–222 | cascata tripla `or 0.0` | produtividade absorve 3 falhas |
| `application/skills/manifests/06-resultado-financeiro/…/_skill_helpers_a.py` | 159–173 | `bdi_rates.get(cat, 0.0)` | BDI ausente → markup zero → preço irreal |
| `infrastructure/adapters/excel/cash_flow.py` | 13 | `cost_per_unit.get(act_id, 0.0)` | atividade sem custo ≠ custo zero |

**P3. `x or fallback` esmacando zeros legítimos de domínio.**  
`float(x or 1.0)` em fatores multiplicativos (fator_clima, fator_calendario) converte `0.0` (paralisação
legítima de obra) em `1.0` (sem ajuste). Idêntico problema em `num_equipes_base or 1`.

Ocorrências confirmadas:

| Arquivo | Linha | Campo | Consequência |
|---|---|---|---|
| `application/services/concilium_service.py` | 567–568 | `fator_clima`, `fator_calendario` | paralisação → fator 1.0 (obra ativa) |
| `infrastructure/adapters/excel/sheets/recursos.py` | 83 | `fator_calendario` | idem |
| `application/benchmarks/reconciliacao_planejamento.py` | 188–191 | `num_equipes_base or 1` | 0 equipes → custo multiplicado × 1 |
| `application/benchmarks/report/projection.py` | 151–154 | `getattr(sem_bdi, cat, 0.0) or 0.0` | redundância; boolean coerce silencioso |
| `domain/services/project_rules.py` | 31 | `.get(key, 0.0) or 0.0` | redundância dupla |

**P4. Constantes de negócio duplicadas e dispersas.**  
Valores de política de negócio repetidos em múltiplos arquivos sem fonte única: alteração de política
requer varredura manual, com risco de inconsistência entre callers.

| Constante | Valor | Arquivos (N de cópias) |
|---|---|---|
| `meta_margem_pct` | 0.10 | `tools/campaign.py`, `commands_campaign.py`, `routes/campaign.py`, `tools/replan.py` — **5 cópias** |
| ISS default | 0.05 | `tools/spec.py`, `tools/campaign.py`, duplicado — **3+ cópias** |
| `dias_semana` | 6 | `domain/constants.py`, `schemas.py` — potencial divergência |
| `horas_dia` | 8 | idem |

**P5. Defaults de modelo com semântica invertida (zero = "nada" vs. "ideal").**

| Arquivo | Campo | Default | Problema |
|---|---|---|---|
| `domain/models/planning/calendario_operacional.py` | `fator_operacao` | `0.0` | semana sem dado → sem produção; prazo inflado silenciosamente |
| `domain/constants.py` | `MARGEM_MINIMA` | `0.05` | global sem override por tipo de obra ou perfil de cliente |
| `presentation/api/schemas.py` | `dias_semana`, `horas_dia` | `6`, `8` | API rejeita regimes alternativos sem mensagem clara |

**P6. Funções de conversão numérica com três implementações independentes e comportamento idêntico.**  
`_norm_float`, `_as_float` (em `_audit_utils.py`) e `_f` (em `pipeline_validator.py`) têm implementação
idêntica: `float(v or 0)` com `except Exception: return 0.0`. Nenhuma emite log.
Erros de conversão são amplificados silenciosamente em agregações de custo.

**P7. Mistura de bases de cálculo em fallback de preço de venda.**  
`_bfc_preco_venda` em `benchmarks/report/projection.py` tem 3 fontes em cascata:
`total_com_bdi` (operacional) → `total_custo_plus_catalogo` (catálogo) → derivado `custo_total × (1 + bdi_lucro)`.
O terceiro fallback mistura `raw_bdi_lucro` de catálogo com `custo_total` instancial — resultado não é
comparável entre itens e não há indicador de qual fonte foi usada.

---

## Decisão

A remediação será feita em **7 fases incrementais**, cada uma com suite de testes antes e depois, sem
alterar o comportamento observável dos outputs. A ordem maximiza observabilidade antes de modificar
semântica.

**D1 — Adicionar logging a todas as exceções estruturais engolidas (Fase 1).**  
Todas as ocorrências de P1 recebem `logger.error(f"...: {e}", exc_info=True)` antes do fallback. O
valor de retorno não muda; apenas o erro passa a ser rastreável. Nenhum teste de resultado pode falhar
por esta mudança.

Padrão mandatório:
```python
except Exception as e:
    logger.error("Falha ao resolver CPU %s no catálogo %s: %s", cpu_id, catalog_id, e, exc_info=True)
    master_cpu = None
```

**D2 — Separar semântica de None e 0.0 em simulação e cálculos de insumo (Fase 2).**  
Substituir `dict.get(key, 0.0)` por `dict.get(key)` nos locais de P2 onde zero e ausência são
distintos. Callers devem verificar `if valor is None: raise/warn` ou propagar `None` explicitamente.
Em `simulation.py`, insumo sem `preco_unitario` levanta `ValueError` (não silencia).

**D3 — Substituir `x or fallback` por `x if x is not None else fallback` nos fatores (Fase 3).**  
Todos os locais de P3. O operador `or` só é aceitável para strings e listas onde falsy = ausente; para
floats em domínio financeiro ou de cronograma é proibido a partir desta ADR.

**D4 — Centralizar constantes de política de negócio em `domain/constants.py` (Fase 4).**  
Criar:
```python
META_MARGEM_PADRAO: float = 0.10        # pode ser sobreescrito por PerfilExpectativas
ISS_PADRAO: float = 0.05                # máximo legal; deve ser configurado por jurisdição
TOLERANCIA_MARGEM_PADRAO: float = 0.03
```
Todos os callers de P4 passam a importar de `domain/constants.py`. Arquivos de origem removem o literal.

**D5 — Consolidar as três funções de conversão em `_safe_float` com logging (Fase 5).**  
Criar `_safe_float(v, context="", default=0.0)` em módulo compartilhado:
```python
def _safe_float(v: Any, context: str = "", default: float = 0.0) -> float:
    try:
        return float(v)
    except (TypeError, ValueError) as e:
        logger.warning("Conversão float falhou [%s] v=%r: %s", context, v, e)
        return default
```
Remover `_norm_float`, `_as_float`, `_f` após substituição. O `v or 0` dentro das funções atuais é
removido — caller decide o tratamento de falsy.

**D6 — Corrigir `fator_operacao` em `CalendarioOperacional` e `dias_semana`/`horas_dia` em schemas (Fase 6).**  
`fator_operacao` passa a `Optional[float] = None`: ausência de dado é explícita, e o loader de
calendário levanta aviso ao encontrar `None` em semana esperada como ativa.
`dias_semana` e `horas_dia` em `schemas.py` mantêm defaults mas adicionam `description=` documentando
que outros regimes são válidos; o validator emite `UserWarning` quando o regime difere do padrão.

**D7 — Serializar a fonte de preço de venda em `projection.py` (Fase 7).**  
`_bfc_preco_venda` passa a retornar `tuple[float | None, float | None, str]` onde o terceiro elemento
é `"total_com_bdi" | "total_custo_plus_catalogo" | "derivado" | "indisponivel"`. O `BenchmarkProjection`
armazena o campo `preco_venda_fonte` auditável. Relatórios e comparações downstream podem filtrar por
fonte para garantir comparações homogêneas.

---

## Alternativas Rejeitadas

| ID | Alternativa | Motivo |
|---|---|---|
| A1 | Substituir todos os fallbacks por raise em uma única passagem | Alto risco de regressão em produção; fallbacks existentes cobrem casos reais de dados ausentes |
| A2 | Criar wrapper `safe_get` global para todos os `.get()` | Generalização prematura; a maioria dos `.get()` com default numérico é legítima; apenas os financeiros são problemáticos |
| A3 | Adicionar type annotations estritas (mypy strict) para forçar verificação de None | Cobre P2 a longo prazo, mas não resolve comportamento de runtime de P1/P3; complementar, não substituto |
| A4 | Fase única sem suite de testes intermediária | Impossível garantir não-regressão em codebase com 100+ chamadas afetadas |

---

## Consequências

### Positivas

| Efeito | Descrição |
|---|---|
| Observabilidade imediata (D1) | Erros estruturais passam a aparecer nos logs antes de qualquer mudança de comportamento |
| Diagnóstico de qualidade de dados | Logs de D2 revelam quantos insumos chegam sem `preco_unitario` — dado de qualidade de catálogo |
| Paralisação corretamente modelada (D3) | `fator_clima=0.0` em semanas de chuva intensa representa corretamente zero produção |
| Política de margem centralizada (D4) | Alteração de política requer 1 linha em `constants.py` em vez de 5 arquivos |
| Comparações homogêneas (D7) | Benchmark só compara itens com mesma fonte de preço de venda |

### Negativas / Riscos

| Risco | Mitigação |
|---|---|
| D2 pode expor bugs latentes em dados de catálogo que hoje são mascarados | Rodar fase 2 com `logger.warning` antes de `raise`; promover para exceção somente após ciclo de limpeza de catálogo |
| D3 pode alterar resultados numéricos em benchmarks com fator_clima=0 | Verificar dados reais: se nenhum projeto tem fator=0 legítimo, o risco é zero; caso contrário, resultado atual está errado e D3 é correção |
| D7 muda assinatura de `_bfc_preco_venda` | Função é privada ao módulo; sem callers externos; risco contido |

---

## Plano de Implementação

| Fase | Escopo | Arquivos | Status |
|---|---|---|---|
| F1 | Logging em exceções engolidas (P1) | `concilium_service.py`, `project_service.py`, `spec_loader.py`, `selector.py`, `cronograma_parser.py`, `referencia_enricher.py`, `comparison/granular.py`, `runner.py` | ✅ 2026-06-18 |
| F2 | Separar None de 0.0 em simulação e insumos (P2) | `simulation.py`, `_concilium_service_helpers.py`, `_skill_helpers_a.py` (BDI) | ✅ 2026-06-18 |
| F3 | Substituir `x or fallback` por ternário em fatores (P3) | `concilium_service.py`, `sheets/recursos.py`, `reconciliacao_planejamento.py`, `projection.py`, `project_rules.py` | ✅ 2026-06-18 _(regressão `None` explícito detectada e corrigida)_ |
| F4 | Centralizar constantes de negócio (P4) | `domain/constants.py`, `tools/campaign.py`, `commands_campaign.py`, `routes/campaign.py`, `tools/replan.py`, `tools/spec.py` | ✅ 2026-06-18 |
| F5 | Consolidar `_norm_float`/`_as_float`/`_f` (P6) | `benchmarks/analysis/_audit_utils.py`, `benchmarks/analysis/pipeline_validator.py` | ✅ 2026-06-18 |
| F6 | Corrigir defaults de modelo (P5) | `domain/models/planning/calendario_operacional.py`, `presentation/api/schemas.py`, `skills/04-cronograma/skill.py` | ✅ 2026-06-18 |
| F7 | Serializar fonte de preço de venda (P7) | `benchmarks/report/projection.py`, `benchmarks/report/report_builder.py` | ✅ 2026-06-18 |

**Invariante de cada fase:** `pytest tests/` deve passar sem regressão antes de abrir PR da fase seguinte.

---

## Definition of Done

### Fase 1 — Logging em exceções
- [ ] Todos os 10 blocos `except Exception` listados em P1 têm `logger.error(..., exc_info=True)`
- [ ] Nenhum retorno de fallback foi alterado
- [ ] `pytest tests/` verde (zero regressões)
- [ ] `grep -rn "except Exception:" src/concilium/application/services/ src/concilium/application/benchmarks/spec/` retorna apenas casos documentados ou novos com justificativa

### Fase 2 — Separação None / 0.0 em insumos
- [ ] `simulation.py` levanta `ValueError` (com log) quando `preco_unitario` ausente em insumo produtivo
- [ ] `_concilium_service_helpers.py` L221-222 usa cadeia explícita sem `or`
- [ ] Benchmarks de referência (AGIS, Serra Verde) produzem resultados idênticos ou diferença justificada
- [ ] `pytest tests/` verde

### Fase 3 — Ternário em fatores multiplicativos
- [ ] Nenhuma ocorrência de `float(x or 1.0)` ou `float(x or 0.0)` onde `x` é fator de cronograma ou financeiro
- [ ] `fator_clima=0.0` em dado de teste produz semana com produção zero (não 1.0)
- [ ] `pytest tests/` verde

### Fase 4 — Centralização de constantes
- [ ] `grep -rn "meta_margem_pct.*0\.10\|meta_margem.*0\.1[^0-9]" src/concilium/presentation/` retorna zero ocorrências
- [ ] `grep -rn '"iss".*0\.05\|iss.*0\.05' src/concilium/presentation/` retorna zero ocorrências
- [ ] `domain/constants.py` contém `META_MARGEM_PADRAO`, `ISS_PADRAO`, `TOLERANCIA_MARGEM_PADRAO`
- [ ] `pytest tests/` verde

### Fase 5 — Consolidação de float conversion
- [ ] `_norm_float` e `_as_float` removidos de `_audit_utils.py`
- [ ] `_f` removido de `pipeline_validator.py`
- [ ] `_safe_float` com logging em módulo compartilhado (`benchmarks/analysis/_utils.py` ou similar)
- [ ] `pytest tests/` verde

### Fase 6 — Defaults de modelo
- [ ] `fator_operacao: Optional[float] = None` em `CalendarioOperacional`
- [ ] Loader de calendário emite `logger.warning` ao encontrar semana sem fator
- [ ] `pytest tests/` verde

### Fase 7 — Fonte de preço de venda
- [ ] `_bfc_preco_venda` retorna `(raw_bdi, preco, fonte: str)`
- [ ] `BenchmarkProjection` armazena `preco_venda_fonte`
- [ ] Relatório de confronto filtra por `fonte == "total_com_bdi"` para comparações homogêneas
- [ ] `pytest tests/` verde após ajuste de callers

---

## Relacionados

- ADR-043 — Benchmark Application Layer (callers afetados nas fases 2, 7)
- ADR-085 — Custo Instancial (simulation.py — fase 2)
- ADR-060 — Ponto de Equilíbrio (projection.py — fase 7)
- ADR-090 — BDI Sistemático (bdi_rates fallbacks — fase 2)
- ADR-095 — Observabilidade OpenTelemetry (logging adicionado na fase 1 pode emitir spans)
- NEP-043 — C_r Reconciliação (bugs de n_frentes e encargos relacionados ao P3 desta ADR)
