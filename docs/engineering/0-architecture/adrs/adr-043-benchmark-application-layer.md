# ADR-043 — Benchmark Application Layer: Unificação e Normalização do Ciclo de Benchmark

**Status:** Implementado  
**Data:** 2026-05-11  
**Contexto:** AGIS benchmark pipeline  
**Dependências:** ADR-024 (Referências + Snapshot), ADR-029 (DDD Package), ADR-039 (The Bridge)

---

## Contexto

### Situação pré-ADR

O ciclo de benchmark estava dividido entre duas camadas com responsabilidades sobrepostas:

1. **`benchmarks/_benchmark_runner.py`** — script de bootstrapping em `benchmarks/`, que importa de `concilium.application.benchmarks` e repassa ao `BenchmarkRunner`. Mantido por razões de compatibilidade com scripts individuais (`run_rosh.py`, `run_agis.py`, etc.) que residem no mesmo diretório.

2. **`benchmarks/run_all.py`** — script que instancia `BenchmarkBatchRunner` e percorre os subdiretórios de `benchmarks/data/`. Usa `Path(__file__).resolve()` para descobrir caminhos, o que impede execução de fora do diretório `benchmarks/`.

3. **`src/concilium/application/benchmarks/runner.py`** — o `BenchmarkRunner` real, que executa a pipeline e gera o relatório. Já está corretamente na camada de aplicação.

4. **`src/concilium/application/benchmarks/spec_loader.py`** — o `BenchmarkSpecLoader` que carrega `referencia.json` e deriva `ProjectSpec`, incluindo o **mapeamento semana-numérica → ISO-week** através do `BenchmarkInputDeriver`.

### Problema raiz identificado no AGIS

O `referencia.json` do AGIS armazena o cronograma com **chaves numéricas de semana** (`"1"`, `"2"`, ..., `"30"`) derivadas da planilha Excel, enquanto o `BenchmarkInputDeriver._derive_from_reference_schedule()` itera usando **chaves ISO-week** (`"2026-W02"`, `"2026-W03"`, ...) geradas a partir de `data_inicio`/`data_termino`.

**O `referencia.json` do AGIS não tem `data_inicio` nem `data_termino` no nível raiz.** Esses campos são `null`. Por isso, `iso_weeks()` falha silenciosamente ou usa defaults, gerando chaves ISO que nunca casam com as chaves numéricas do cronograma.

O resultado: para todos os itens sem `has_cronograma: true` (eap-11 a eap-52), o `_derive_from_reference_schedule` retorna vazio, o fallback atribui 1 equipe por semana usando as semanas ISO geradas a partir de datas default, e a Skill-02 computa produção acumulada que não cobre 100% do quantitativo dentro do prazo real da obra.

### Causa secundária: semanas numéricas vs. ISO

O cronograma da planilha AGIS usa semanas relativas ao projeto (`"1"` = 2026-01-05, `"30"` = 2026-07-27). O `referencia.json` reproduz esse esquema fiel à planilha. O `BenchmarkInputDeriver`, contudo, só reconhece chaves ISO (`"2026-W02"`). Há impedância estrutural entre os dois esquemas.

---

## Decisão

### 1. Adicionar `BenchmarkFacade` na camada de aplicação

Criar `src/concilium/application/benchmarks/facade.py` que encapsula toda a lógica de:
- Descoberta de specs (`discover_specs`)
- Execução individual ou em lote (`run`, `run_all`)
- Sumarização de resultados (`build_summary`)
- **Conversão de semanas numéricas → ISO-week** antes de injetar no `BenchmarkInputDeriver`

O facade resolve a Unicode-path issue ao usar apenas `os.environ['CONCILIUM__ROOT']` e nunca `Path(__file__)` para descobrir raízes.

### 2. Adicionar `BenchmarkWeekMapper` na camada de aplicação

Criar `src/concilium/application/benchmarks/week_mapper.py` com a responsabilidade única de:
- Detectar se o cronograma da referência usa **esquema numérico** (`"1"`, `"2"`) ou **esquema ISO** (`"2026-W02"`)
- Mapear semanas numéricas → ISO usando o dicionário `cronograma.semanas[n].data_inicio`
- Injetar datas reais (`data_inicio`, `data_termino`) no spec quando ausentes da raiz do `referencia.json`

**Regra de detecção:**
```python
def _is_numeric_scheme(semanas: dict) -> bool:
    return all(k.isdigit() for k in semanas.keys())
```

**Mapeamento:**
```python
def map_numeric_to_iso(semanas_meta: dict) -> dict[str, str]:
    """Retorna {str_num: iso_week_key} para cada semana numérica."""
    result = {}
    for k, v in semanas_meta.items():
        if k.isdigit() and isinstance(v, dict) and "data_inicio" in v:
            d = date.fromisoformat(v["data_inicio"])
            iso = d.isocalendar()
            result[k] = f"{iso.year}-W{iso.week:02d}"
    return result
```

### 3. Migrar `benchmarks/_benchmark_runner.py` e `benchmarks/run_all.py`

- `benchmarks/_benchmark_runner.py` passa a ser um thin wrapper que apenas importa `BenchmarkFacade` e delega. Remove lógica própria.
- `benchmarks/run_all.py` passa a importar e chamar `BenchmarkFacade.run_all_from_root(root)`.
- Ambos mantêm compatibilidade de interface para scripts legados.

### 4. Corrigir `referencia.json` do AGIS

Adicionar campos ausentes no nível raiz:
```json
{
  "data_inicio": "2026-01-05",
  "data_termino": "2026-07-27",
  ...
}
```

E garantir que as semanas numéricas do cronograma das atividades sem `has_cronograma` recebam schedule derivado via `BenchmarkWeekMapper` antes de chegar ao `BenchmarkInputDeriver`.

---

## Consequências

### Positivas
- **Elimina o impedimento imediato**: eap-18 e demais itens de drenagem recebem `num_equipes` mapeado para ISO-weeks corretas.
- **Resolve a Unicode-path issue de execução**: o facade não usa `Path(__file__)` para raízes.
- **Centraliza o mapeamento de semanas**: uma única função canônica, testável, auditável.
- **Separa preocupações**: scripts em `benchmarks/` viram thin wrappers; toda lógica vai para a camada de aplicação.
- **Facilita iteração de cronograma**: o facade expõe `run_single(slug)` para rodar apenas um benchmark.

### Negativas / Riscos
- Scripts legados em `benchmarks/` precisam ser atualizados (low risk — são wrappers).
- O mapeamento numérico→ISO só funciona quando `cronograma.semanas[n].data_inicio` está presente (invariante mantido pela extração via planilha).

---

## Estrutura de arquivos após implementação

```
src/concilium/application/benchmarks/
  __init__.py               (exporta BenchmarkFacade)
  batch.py                  (BenchmarkBatchRunner — mantido)
  facade.py                 (NOVO — BenchmarkFacade)
  input_derivation/
    __init__.py
    cronograma.py           (BenchmarkInputDeriver — atualizado: aceita weeks ISO)
    week_mapper.py          (NOVO — BenchmarkWeekMapper)
  runner.py
  report_builder.py
  report_printer.py
  spec_loader.py

benchmarks/
  _benchmark_runner.py      (thin wrapper → BenchmarkFacade)
  run_all.py                (thin wrapper → BenchmarkFacade.run_all_from_root)
```

---

## Critério de aceitação

- `BenchmarkWeekMapper.map_numeric_to_iso()` retorna mapeamento correto para AGIS (semana "1" → "2026-W02").
- `BenchmarkFacade.run_single("AGIS")` executa sem erro de Skill-02 `eap-18=53%`.
- `benchmark_agis.json` contém `confronto.computed.custo_direto` após a execução.
- `benchmark_agis.json` exibe `delta_custo_direto_pct` ≤ 10% (meta imediata) e idealmente ≤ 5% (meta de precisão).
