# NEP-039: Ciclo de vida benchmark-projeto e governança de reutilização

**Status:** Parcialmente Implementado ⚠️ _(auditado 2026-06-08)_  
**Prioridade:** 🟠 Alto  
**Área:** Arquitetura e Skills  
**Tipo:** Governança + Feature  
**Esforço:** L  
**Identificado em:** 2026-06-03

> **Nota de auditoria (2026-06-08):** `BenchmarkMetadata` e `BenchmarkExecution` implementados em
> `src/concilium/domain/benchmark/models.py`; `benchmark_nep039.py` MCP tool presente.
> Pendente: MCP tools de edição controlada, migração de benchmarks existentes, campos
> `derivado_de_benchmark`/`benchmark_versao` em `ProjectMetadata`.

---

## Contexto

Benchmarks são usados em dois contextos no sistema Concilium:

1. **CLI** — `tools/run_agis_with_discrepancy_artifacts.py`, `benchmarks/run_all.py`
2. **MCP Server** — Tools de execução de pipeline com referência a benchmark

Atualmente, benchmarks funcionam como artefatos de validação técnica, mas não há um modelo
formal de relacionamento benchmark ↔ projeto. O usuário pode executar um benchmark
diretamente, sem criar um projeto; ou pode criar um projeto e "importar" dados de um benchmark
como início quente (warm start).

Essa ambiguidade gera questões operacionais:

1. **Edição de benchmark** — Se editarmos dados de um benchmark, isso deve afetar projetos derivados?
2. **Auditabilidade** — Se um projeto foi criado a partir de AGIS_2025_Q1, o projeto deve armazenar essa proveniência?
3. **Reutilização** — Podemos criar vários projetos a partir do mesmo benchmark? O benchmark é imutável ou editável?
4. **Execução vs. Consulta** — É possível consultar metadados de um benchmark sem criar um projeto? Ou toda interação requer inicialização de projeto?
5. **Melhorias incrementais** — Se um benchmark é reexecutado após correções no catálogo/algoritmo, ele deve criar um novo snapshot ou substituir o anterior?

---

## Problema Observado

### P1 — Benchmark como entidade autônoma vs. entidade transitória

Hoje, benchmarks são apenas diretórios em `benchmarks/data/*/`:

```
benchmarks/data/AGIS/
  reference.json
  project_input.json
  expected_outputs/
```

Não há:
- ID formal de benchmark
- Versionamento explícito
- Registro de execuções históricas
- Metadados (origem, data de criação, tags)

### P2 — Projetos não registram proveniência de benchmark

Um projeto criado via `disparar_pipeline()` com dados de AGIS não armazena:

1. Que foi derivado de AGIS
2. Que versão do benchmark foi usada
3. Se os dados foram editados após importação

**Efeito:** Impossível rastrear se um projeto real é "filho" de um benchmark de validação.

### P3 — Edição de benchmark sem controle de mutabilidade

Se editarmos `benchmarks/data/AGIS/reference.json` após criar 5 projetos derivados:
- Os 5 projetos devem ser re-validados?
- A edição invalida a referência original?
- Devemos criar um novo benchmark `AGIS_v2`?

Não há política de imutabilidade.

### P4 — Execução de benchmark sem projeto é "operação órfã"

Ferramentas CLI executam benchmarks diretamente sem criar registro em `projetos/`.
- Resultados ficam em arquivos locais
- Não são versionados
- Não aparecem em `listar_jobs_pipeline()`

### P5 — Benchmark reutilizado não aproveita melhorias

Se corrigirmos bug no catálogo e re-executarmos AGIS:
- A saída muda (custo, BDI, cronograma)
- Mas não há critério para saber se a nova saída é "melhor" ou "regressão"
- Não há diff estruturado entre versões do benchmark

---

## Causa Raiz

Benchmarks foram desenhados como **artefatos de teste estático** (validação de pipeline),
mas estão sendo usados como **template de projeto reutilizável** (warm start).

Falta separação explícita entre:

1. **Benchmark como template** — imutável, versionado, usado para derivar projetos
2. **Benchmark como suite de validação** — executável, auditável, com histórico de runs
3. **Projeto derivado** — mutável, auditável, com link para benchmark de origem

---

## Objetivo

Formalizar o ciclo de vida de benchmarks e sua relação com projetos:

1. **Leitura sem execução** — Consultar metadados de benchmark (nome, origem, referência) sem inicializar projeto
2. **Execução atrelada a projeto** — Benchmark só é executado quando cria ou atualiza um projeto
3. **Edição controlada** — Benchmark pode ser editado, mas edições devem gerar nova versão (snapshot)
4. **Proveniência auditável** — Projeto registra benchmark de origem + versão
5. **Reutilização com evolução** — Re-executar benchmark aproveita melhorias no catálogo/algoritmo

---

## Decisão Proposta

### D1 — Benchmark como entidade de primeira classe

Criar modelo `Benchmark` no domínio:

```python
@dataclass
class BenchmarkMetadata:
    benchmark_id: str  # "AGIS_2025_Q1"
    nome: str
    origem: str  # "AGIS — Obra real 2025 Q1"
    tags: list[str]  # ["civil", "terraplenagem", "real"]
    criado_em: datetime
    versao: int  # auto-incrementado
    imutavel: bool  # True após primeira execução bem-sucedida
    
@dataclass
class BenchmarkExecution:
    execution_id: str
    benchmark_id: str
    versao: int
    projeto_id: str | None  # Link para projeto derivado
    status: JobStatus
    discrepancia_sumario: dict | None
    executado_em: datetime
```

### D2 — Leitura sem execução

Adicionar MCP tool:

```python
def consultar_benchmark(benchmark_id: str) -> BenchmarkMetadata:
    """Retorna metadados do benchmark sem executar pipeline."""
    ...
```

Retorna:
- Nome, origem, tags
- Versão atual
- Histórico de execuções (últimas 10)
- Sumário de discrepância da última execução
- Lista de projetos derivados

### D3 — Execução sempre atrelada a projeto

**Regra:** Não é possível executar benchmark "solto".  
Toda execução deve:

1. Criar um novo projeto (`project_id` gerado)
2. Ou atualizar um projeto existente (re-run)

```python
def executar_benchmark(
    benchmark_id: str,
    criar_novo_projeto: bool = True,
    project_id: str | None = None
) -> JobDTO:
    """
    - Se criar_novo_projeto=True: cria projeto e executa pipeline
    - Se project_id fornecido: re-executa pipeline no projeto existente
    """
    ...
```

**Benefício:** Toda execução fica registrada em `projetos/`, auditável via `listar_jobs_pipeline()`.

### D4 — Projeto registra proveniência de benchmark

Adicionar campos ao `ProjectMetadata`:

```python
@dataclass
class ProjectMetadata:
    ...
    derivado_de_benchmark: str | None  # "AGIS_2025_Q1"
    benchmark_versao: int | None  # 3
    benchmark_execution_id: str | None  # ID da execução que criou este projeto
```

**Benefício:** Rastreabilidade completa — dado um projeto, sabemos qual benchmark o gerou.

### D5 — Edição de benchmark gera nova versão (snapshot)

**Regra:** Benchmark marcado como `imutavel=True` não pode ser editado diretamente.  
Para modificar:

1. Criar nova versão do benchmark (`AGIS_2025_Q1_v2`)
2. Ou desmarcar `imutavel` (apenas em modo dev/teste)

**Fluxo:**

```python
def editar_benchmark(benchmark_id: str, patch: dict) -> BenchmarkMetadata:
    """
    - Se imutavel=True: gera nova versão automaticamente
    - Se imutavel=False: aplica patch in-place (dev mode)
    """
    ...
```

**Benefício:** Projetos derivados não são invalidados por edições posteriores.

### D6 — Re-execução aproveita melhorias

**Cenário:** Corrigimos bug no catálogo (ex.: produtividade de terraplenagem).  
Queremos saber se AGIS_2025_Q1 melhora com a correção.

**Fluxo:**

1. `executar_benchmark("AGIS_2025_Q1", criar_novo_projeto=True)`
2. Sistema cria novo projeto `projeto_abc123` com versão incremental
3. Executa pipeline com catálogo atual
4. Compara com referência original
5. Gera diff estruturado:

```json
{
  "delta_custo_direto": -5.2,  // % — custo direto caiu 5.2%
  "delta_preco_venda": -2.1,
  "itens_impactados": [
    {"codigo": "CPU-001", "delta_pu": -8.5}
  ]
}
```

**Benefício:** Auditoria de impacto de melhorias no algoritmo/catálogo.

---

## Escopo

### Fase 1 — Modelo de dados (S)

- [ ] Criar `BenchmarkMetadata` e `BenchmarkExecution` em `src/concilium/domain/benchmark/`
- [ ] Criar `BenchmarkRepository` (in-memory + filesystem backend)
- [ ] Migrar benchmarks existentes em `benchmarks/data/` para modelo

### Fase 2 — MCP Tools (M)

- [ ] `consultar_benchmark(benchmark_id)` — leitura sem execução
- [ ] `listar_benchmarks()` — catálogo de benchmarks disponíveis
- [ ] `executar_benchmark(benchmark_id, criar_novo_projeto, project_id)` — atrelado a projeto
- [ ] `editar_benchmark(benchmark_id, patch)` — com controle de imutabilidade

### Fase 3 — Proveniência (M)

- [ ] Adicionar campos `derivado_de_benchmark`, `benchmark_versao` ao `ProjectMetadata`
- [ ] Atualizar `disparar_pipeline()` para registrar proveniência ao usar benchmark
- [ ] Atualizar `consultar_job_pipeline()` para retornar metadados de benchmark

### Fase 4 — Diff estruturado (L)

- [ ] Criar `BenchmarkDiffService` para comparar execuções
- [ ] Adicionar `comparar_execucoes_benchmark(exec_id_1, exec_id_2)` MCP tool
- [ ] Gerar relatório visual de delta (custo, cronograma, BDI)

---

## Critérios de Aceite

### CA1 — Leitura sem execução

```python
# Agente deve poder consultar metadados sem criar projeto
metadata = consultar_benchmark("AGIS_2025_Q1")
assert metadata.nome == "AGIS — Obra Terraplenagem Q1/2025"
assert metadata.versao == 3
assert len(metadata.execucoes_historico) > 0
```

### CA2 — Execução sempre cria projeto

```python
# Executar benchmark deve criar projeto novo
job = executar_benchmark("AGIS_2025_Q1", criar_novo_projeto=True)
assert job.project_id is not None
assert projeto_existe(job.project_id)
```

### CA3 — Proveniência registrada

```python
# Projeto deve saber de qual benchmark foi derivado
project = consultar_projeto(job.project_id)
assert project.derivado_de_benchmark == "AGIS_2025_Q1"
assert project.benchmark_versao == 3
```

### CA4 — Edição gera nova versão

```python
# Editar benchmark imutável deve criar v4
metadata_v3 = consultar_benchmark("AGIS_2025_Q1")
assert metadata_v3.versao == 3
assert metadata_v3.imutavel == True

# Edição deve falhar ou criar nova versão
metadata_v4 = editar_benchmark("AGIS_2025_Q1", {"reference": {...}})
assert metadata_v4.versao == 4
assert metadata_v3.versao == 3  # v3 permanece intacto
```

### CA5 — Diff estruturado

```python
# Re-executar benchmark após melhoria deve gerar diff
exec_1 = executar_benchmark("AGIS_2025_Q1", criar_novo_projeto=True)
# ... corrigir catálogo ...
exec_2 = executar_benchmark("AGIS_2025_Q1", criar_novo_projeto=True)

diff = comparar_execucoes_benchmark(exec_1.execution_id, exec_2.execution_id)
assert "delta_custo_direto" in diff
assert "itens_impactados" in diff
```

---

## Impacto

### Benefícios

1. **Rastreabilidade** — Todo projeto sabe sua origem (benchmark ou manual)
2. **Auditabilidade** — Histórico de execuções de benchmark versionado
3. **Reutilização segura** — Benchmarks imutáveis garantem reprodutibilidade
4. **Observabilidade** — Diff estruturado mostra impacto de melhorias
5. **Governança** — Separação clara entre template (benchmark) e instância (projeto)

### Riscos

1. **Complexidade adicional** — Mais metadados para gerenciar
2. **Migração de dados** — Benchmarks existentes precisam ser migrados
3. **Performance** — Armazenar histórico de execuções pode crescer rapidamente

### Mitigação

1. **Fase 1 incremental** — Começar com modelo in-memory, migrar para SQLite depois
2. **TTL em execuções** — Reter apenas últimas 50 execuções por benchmark
3. **Opt-in gradual** — Manter CLI atual funcionando, migrar MCP primeiro

---

## Relações com outras NEPs

- **NEP-027** — `BenchmarkInferenceService` será consumido por `executar_benchmark()`
- **NEP-030** — Injeção mínima honesta garante que benchmark valida algoritmo, não copia referência
- **NEP-028** — Governança de catálogo isolado por projeto: benchmark usa catálogo global, projeto pode sobrescrever

---

## Próximos Passos

1. Validar proposta com stakeholders
2. Implementar Fase 1 (modelo de dados)
3. Criar ADR formal caso aceito
4. Atualizar documentação MCP tools
