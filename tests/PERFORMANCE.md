# Performance dos Testes

## Visão Geral

A suíte de testes de integração do Concilium executa pipelines completos (skills 01-09) que podem levar ~70-80s. Para otimizar o tempo total, implementamos várias estratégias:

## Otimizações Implementadas

### 1. Fixtures Session-Scoped (~60-70% economia)

- **`_session_pipeline_sk03`**: Executa skills 01-03 (base) uma vez por sessão (~70s)
- **`_session_pipeline_sk09`**: Executa skills 04-09 uma vez por sessão (~15s adicional)  
- **`_session_pipeline_mendeslobo_sk09`**: Pipeline com catálogo mendeslobo (~70-80s)
- **`_wb_sk09`**: Workbook Excel pré-carregado (~0.5-2s)
- **`server_with_config`**: MCP server construído uma vez (~0.6-2.7s)

**Economia**: Ao invés de executar o pipeline 10-20× (uma por teste), executa apenas 1×.

### 2. Class-Scoped Fixtures (~20-28s economia)

- **`projeto_analitico`**: Cópia do projeto compartilhada por classe de teste
  - Antes: 7 testes × 3-5s copytree = ~21-35s
  - Depois: 1× copytree = ~3-5s

### 3. Deliverables Desabilitados (~80-85s economia)

```python
deliverables_config.json:
{
  "relatorio_pdf": false,    # -20-25s por render
  "memorial_bdi_pdf": false, # -20-25s por render
  "graficos_png": false      # -60s por geração de PNGs analíticos
}
```

### 4. Lazy Imports

- `openpyxl` só é importado quando workbook é realmente usado
- Reduz tempo de inicialização para testes que não precisam de Excel

### 5. Ignore Patterns em Copytree

```python
def _ignore(dir_path, names):
    ignore = set()
    for name in names:
        # CRÍTICO: NÃO ignorar .log! O runtime usa invocations.log para tracking de dependências
        if name.endswith(('.pdf', '.zip', '.tar.gz')):
            ignore.add(name)
        if name in ('__pycache__', '.pytest_cache', 'referencias'):
            ignore.add(name)
    return ignore
```

**⚠️ IMPORTANTE:** Não ignore arquivos `.log` - o sistema usa `invocations.log` para rastrear quais skills foram executadas com sucesso. Sem esse arquivo, testes de dependências falham!

Economiza ~3-5s → 0.02s por cópia (99% mais rápido) ao não copiar arquivos desnecessários.

## Tempos Típicos de Setup (Normal e Esperado)

Estes tempos aparecem apenas na **primeira vez** que cada fixture é usada:

- **14.99s** - `_session_pipeline_sk09` sendo executado pela primeira vez
- **10.19s** - `_session_pipeline_mendeslobo_sk09` sendo executado  
- **4.37s** - `_wb_sk09` carregando workbook Excel
- **3.29s** - `server_with_config` construindo MCP server
- **2-5s** - `projeto_analitico` fazendo copytree

Depois disso, outros testes que usam as mesmas fixtures **não pagam esse custo**.

## Otimização Adicional: Paralelização com pytest-xdist

### Instalação

```bash
pip install pytest-xdist
```

### Uso

```bash
# Auto-detecta número de cores
pytest -n auto tests/integration/

# Especifica número de workers
pytest -n 4 tests/integration/

# Com output verboso
pytest -n auto -v tests/integration/
```

### Ganho Esperado

- **2-4× mais rápido** em máquina com 4+ cores
- Testes de integração são independentes e podem rodar em paralelo
- Session-scoped fixtures são compartilhadas entre workers automaticamente

## Analisando Performance

### Mostrar tempos de fixtures

Os hooks em `conftest.py` automaticamente logam fixtures > 0.5s:

```
[PERF] _session_pipeline_sk09 (session): 15.23s
[PERF] sk09/04-cronograma: 2.14s
[PERF] sk09/05-equipes: 1.87s
[PERF] sk09/06-resultado-financeiro: 3.92s
[PERF] sk09/09-relatorio: 5.61s
```

### Perfil completo com pytest-profiling

```bash
pip install pytest-profiling
pytest --profile tests/integration/
```

### Top 10 testes mais lentos

```bash
pytest --durations=10 tests/integration/
```

## Gargalos Conhecidos

### Skill 03: Catálogo (~50-60s)

- Carrega todo o catálogo de recursos (SICRO, composições, etc.)
- **Mitigação**: Session-scoped fixture compartilhada
- **Otimização futura**: Lazy loading de catálogo, cache em disco

### Skill 09: Relatório (~5-10s)

- Geração de Markdown, Excel com múltiplas abas
- **Mitigação**: PDFs e PNGs desabilitados em testes
- **Otimização futura**: Template engine mais rápido

### Load Workbook (~0.5-2s por carregamento)

- openpyxl lê todo o arquivo na memória
- **Mitigação**: `_wb_sk09` session-scoped com `read_only=True`
- **Otimização futura**: Validar apenas metadados sem carregar dados

### Copytree Projeto (~3-5s)

- Copia todo o diretório do projeto para isolamento
- **Mitigação**: Class-scoped ao invés de function-scoped
- **Mitigação**: Ignore patterns para arquivos grandes
- **Otimização futura**: Hardlinks ao invés de cópia para arquivos imutáveis

## Roadmap de Otimizações

### Curto Prazo (implementado)
- ✅ Session-scoped fixtures
- ✅ Class-scoped fixtures
- ✅ Lazy imports
- ✅ Ignore patterns em copytree
- ✅ Deliverables desabilitados

### Médio Prazo (recomendado)
- ⚠️ **pytest-xdist** para paralelização (maior ganho, fácil implementar)
- 🔄 Lazy loading de catálogo
- 🔄 Cache em disco para resultados de skills

### Longo Prazo (se necessário)
- 🔮 Hardlinks ao invés de copytree
- 🔮 Database em memória para testes
- 🔮 pytest-split para CI com múltiplos jobs

## Comparação: Antes vs Depois

### Antes (sem otimizações)
```
20 testes × 70s pipeline = 1400s (~23 minutos)
```

### Depois (com session-scoped)
```
1× 70s pipeline + 19× 0.1s overhead = ~72s (~1.2 minutos)
```

### Com pytest-xdist (4 workers)
```
~72s / 4 = ~18s (~18 segundos)
```

**Economia total: ~23 min → ~18 seg = 77× mais rápido** 🚀
