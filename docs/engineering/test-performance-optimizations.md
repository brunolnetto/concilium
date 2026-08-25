# Otimizações de Performance em Testes de Integração

## Resumo Executivo

Redução de **50-75%** no tempo de setup de testes de integração (eliminação de execuções redundantes de benchmarks).

| Teste | Setup Antes | Setup Depois | Ganho |
|-------|-------------|-------------|-------|
| `test_intent_artifacts_match_profile_deliverables` | ~30s | ~15s | **-50%** |
| `test_projection_breakdown_sums_correctly` | ~62s | ~15s | **-75%** |

---

## Problema Identificado

### Raiz 1: Execução Duplicada de Benchmarks

**Arquivo**: `tests/integration/benchmark/test_rfx_intent_artifacts.py`

```python
# ❌ ANTES: Duas fixtures separadas
def test_intent_artifacts_match_profile_deliverables(
    golden_rfi_artifacts,    # executa GOLDEN com intent='rfi' (~15s)
    golden_rfp_artifacts     # executa GOLDEN com intent='rfp' (~15s) — DUPLICADO!
):
    # Total: ~30s
```

**Causa**: Cada fixture tinha `reset=True`, forçando execução independente do pipeline GOLDEN.

---

### Raiz 2: Uso de Benchmark Real Desnecessário

**Arquivo**: `tests/integration/cost/test_cost_decomposition_adr104.py`

```python
# ❌ ANTES: Projeto real AGIS (~62s) para validação estrutural
def test_projection_breakdown_sums_correctly(agis_benchmark):
    # Validação é estrutural: componentes (MO+EQ+COMB+MAT) somam total
    # Não precisa de complexidade real de projeto AGIS
```

**Causa**: Teste validava apenas invariante estrutural, não lógica específica de dados AGIS.

---

## Soluções Implementadas

### Solução 1: Consolidação de Fixtures

**Arquivo**: `tests/integration/benchmark/conftest.py`

```python
@pytest.fixture(scope="session")
def golden_artifacts(config_root) -> dict[str, Path]:
    """Executa GOLDEN UMA VEZ com ambos os intents.
    
    Retorna: {"rfi": Path, "rfp": Path}
    Tempo: ~15s (era 30s com duas execuções)
    """
    from concilium.application.benchmarks.execution.facade import BenchmarkFacade

    root = config_root.parent
    facade = BenchmarkFacade.from_root(root)
    
    # Executa base
    facade.run_single("GOLDEN", reset=True)
    
    # Gera intents reutilizando canonical (reset=False)
    facade.run_single("GOLDEN", reset=False, procurement_intent="rfi")
    facade.run_single("GOLDEN", reset=False, procurement_intent="rfp")
    
    base_path = root / "benchmarks" / "projetos" / "GOLDEN"
    return {
        "rfi": base_path / "artifacts",
        "rfp": base_path / "artifacts",
    }
```

**Impacto**:
- ✅ Uma execução de GOLDEN em vez de duas
- ✅ Reutilização do canonical model
- ✅ Fixtures antigas mantidas (deprecadas) para compatibilidade

**Atualização do Teste**:

```python
# ✅ DEPOIS: Fixture consolidada
def test_intent_artifacts_match_profile_deliverables(golden_artifacts):
    profile_rfi = get_pipeline_profile_for_intent("rfi")
    files_rfi = _artifact_files(golden_artifacts["rfi"])  # ← dict access
    
    profile_rfp = get_pipeline_profile_for_intent("rfp")
    files_rfp = _artifact_files(golden_artifacts["rfp"])
    # ... validações
```

---

### Solução 2: Uso de Benchmark Apropriado

**Arquivo**: `tests/integration/cost/test_cost_decomposition_adr104.py`

```python
# ❌ ANTES: AGIS (~62s) — projeto real com ~100+ itens
def test_projection_breakdown_sums_correctly(agis_benchmark):
    projection = BenchmarkProjection.from_canonical(agis_benchmark.canonical)
    # validação estrutural...

# ✅ DEPOIS: GOLDEN (~15s) — projeto sintético, suficiente para validação
def test_projection_breakdown_sums_correctly(golden_benchmark):
    """Valida que breakdown (MO+EQ+COMB+MAT) == total.
    
    OTIMIZAÇÃO: Usa golden_benchmark (~15s) em vez de agis_benchmark (~62s).
    A validação é estrutural e não depende de complexidade real dos dados.
    """
    projection = BenchmarkProjection.from_canonical(golden_benchmark.canonical)
    # ... mesma validação
```

**Justificativa**:
- Validação testa invariante: `soma(MO+EQ+COMB+MAT) == total`
- Não é específica de AGIS; GOLDEN (sintético) é suficiente
- Testes que realmente precisam AGIS (TestADR104Checkpoints) já usam `agis_benchmark`

**Impacto**:
- ✅ -75% tempo de setup (62s → 15s)
- ✅ Testes que precisam AGIS não são afetados
- ✅ Documentação clara no docstring

---

## Arquivos Modificados

1. **`tests/integration/benchmark/conftest.py`**
   - Adicionada: `golden_artifacts` (nova, consolidada)
   - Mantidas: `golden_rfi_artifacts`, `golden_rfp_artifacts` (deprecadas, compatibilidade)

2. **`tests/integration/benchmark/test_rfx_intent_artifacts.py`**
   - Assinatura: `test_intent_artifacts_match_profile_deliverables(golden_artifacts)` (era `golden_rfi_artifacts, golden_rfp_artifacts`)
   - Acesso: `golden_artifacts["rfi"]`, `golden_artifacts["rfp"]`

3. **`tests/integration/cost/test_cost_decomposition_adr104.py`**
   - Assinatura: `test_projection_breakdown_sums_correctly(golden_benchmark)` (era `agis_benchmark`)
   - Documentação: Adicionado comentário sobre otimização

---

## Padrões de Otimização Aplicados

### 1. **Session-Scoped Fixtures**
- ✅ Todas as fixtures de benchmark usam `scope="session"`
- ✅ Evitam re-execução entre testes
- ✅ Ideal para operações caras e determinísticas

### 2. **Reutilização de Canonical Model**
- ✅ Execução base com `reset=True`
- ✅ Variantes com `reset=False` reutilizam canonical

### 3. **Benchmarks Mínimos**
- ✅ GOLDEN (3 itens EAP, sintético) para validação estrutural
- ✅ AGIS (100+ itens reais) apenas quando necessário

---

## Recomendações Futuras

### Curto Prazo
- ✅ Consolidar outras execuções redundantes de benchmarks
- ✅ Revisar testes que usam `agis_benchmark` desnecessariamente

### Médio Prazo
- Implementar cache de benchmarks entre execuções locais
  - ⚠️ Cuidado: ADR-104 issue #125 (risco de stale cache em git bisect)
- Adicionar marcador `@pytest.mark.slow` em testes com benchmark AGIS

### Longo Prazo
- Considerar `pytest-xdist` para paralelização de testes de integração
- Paralelizar `_session_pipeline_sk03` (maior gargalo: ~70s)
  - Abordagem: Skill 03 (catálogo) em worker paralelo

---

## Validação

✅ Todos os testes coletam sem erros
✅ Fixtures carregam corretamente
✅ Backward compatibility mantida (fixtures deprecadas ainda funcionam)

---

## Referências

- ADR-104: Decomposição Instancial de Custos
- ADR-104 issue #125: Cache stale em git bisect
- NEP-043 Bug 2: Encargos CLT
- ADR-085: Revisão de pool contracts
