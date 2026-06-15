# Executando Testes com Paralelização

## Instalação Rápida

```bash
pip install pytest-xdist
```

## Uso Básico

### Auto-detectar número de CPUs
```bash
pytest -n auto tests/integration/
```

### Número específico de workers
```bash
pytest -n 4 tests/integration/
```

### Com output verboso
```bash
pytest -n auto -v tests/integration/
```

### Apenas testes rápidos (unit)
```bash
pytest -n auto tests/unit/
```

## Ganho de Performance Esperado

### Sem paralelização
```
pytest tests/integration/ 
# ~90-120s total
```

### Com paralelização (4 cores)
```
pytest -n auto tests/integration/
# ~25-35s total (3-4× mais rápido)
```

## Troubleshooting

### Erro: "fixture X not found"
- Session-scoped fixtures são automaticamente compartilhadas entre workers
- Se vir este erro, verifique se a fixture está no `conftest.py`

### Testes falhando intermitentemente
- Pode indicar race condition ou estado compartilhado
- Use `pytest -n 0` (sem paralelização) para debug

### Output confuso/entrelaçado
- Use `-v` para melhor organização do output
- Use `--tb=short` para tracebacks mais concisos

## Alternativas

### pytest-split (para CI com múltiplos jobs)
```bash
pip install pytest-split

# Job 1 de 4
pytest --splits 4 --group 1 tests/

# Job 2 de 4  
pytest --splits 4 --group 2 tests/

# etc...
```

### GNU Parallel (linha de comando)
```bash
find tests/integration -name "test_*.py" | parallel -j 4 pytest {}
```

## CI/CD Integration

### GitHub Actions
```yaml
- name: Run tests in parallel
  run: pytest -n auto tests/integration/
```

### GitLab CI
```yaml
test:
  script:
    - pip install pytest-xdist
    - pytest -n auto tests/integration/
  parallel: 4
```
