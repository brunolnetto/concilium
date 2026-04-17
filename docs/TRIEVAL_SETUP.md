# Como Executar os Evals com Trieval (LLM)

## Pré-requisitos

1. **OPENAI_API_KEY** — Já definida no seu shell ✅
2. **trieval** — Biblioteca de avaliação RAG
3. **Ambiente isolado** — O seu sistema usa proteção `externally-managed-environment`

## Opção 1: Instalar dentro de um Virtual Environment (Recomendado)

Se você estiver **fora** de um venv:

```bash
# Criar venv
python3 -m venv venv
source venv/bin/activate  # Linux/Mac
# ou no Windows:
# venv\Scripts\activate

# Instalar dependências
pip install -r requirements-trieval.txt

# Rodar evals com LLM
python3 evals/run_evals.py --with-llm --report
```

## Opção 2: Usando `--break-system-packages`

Se você quiser instalar globalmente (menos recomendado):

```bash
pip install --break-system-packages -r requirements-trieval.txt
python3 evals/run_evals.py --with-llm --report
```

## Opção 3: Usar Docker (se disponível)

```dockerfile
FROM python:3.12-slim
WORKDIR /app
COPY requirements-trieval.txt .
RUN pip install -r requirements-trieval.txt
COPY . .
CMD ["python3", "evals/run_evals.py", "--with-llm", "--report"]
```

## Verificar a instalação

```bash
python3 -c "import trieval; print('✅ trieval instalado')"
```

## Rodar os testes

```bash
# Todos os evals
python3 evals/run_evals.py

# Com LLM (trieval)
python3 evals/run_evals.py --with-llm

# Com relatório JSON
python3 evals/run_evals.py --with-llm --report

# Uma layer específica
python3 evals/run_evals.py --layer 2

# Apenas E2E
python3 evals/run_evals.py --only-e2e

# Fail-fast
python3 evals/run_evals.py --with-llm -x
```

## Problemas comuns

### "trieval não instalado"
→ Siga **Opção 1** (Virtual Environment) ou **Opção 2** (--break-system-packages)

### "OPENAI_API_KEY não definida"
→ Você já fez, mas verifique:
```bash
echo $OPENAI_API_KEY
```

### Testes ainda sendo skipped
→ Verifique que `trieval` foi instalado no **mesmo Python** que roda pytest:
```bash
python3 -m pip list | grep trieval
```

## Estrutura dos testes trieval

| Arquivo | Testes | Método |
|---|---|---|
| `evals/test_trieval_integration.py` | 12 cases | parametrizados com `@pytest.mark.trieval` |
| Golden Cases | EC-001 a EC-005 | Q/C/A triplets predefinidos |
| Métricas | Faithfulness, Context Relevance, etc | 6 métricas via pydantic-ai |

## Saída esperada

```
====================== 91 passed, 12 skipped in 5.21s ========================
# sem --with-llm

====================== 103 passed in 8.45s ===============================
# com --with-llm (todos os 12 testes trieval executados)
```
