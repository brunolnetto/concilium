# AGIS Gerente de Engenharia — Evals & Trieval

> Framework completo de avaliação para o agente de planejamento de obras, com suporte a testes sem LLM (CI/CD) e avaliação RAG com LLM via **trieval**.

## 📊 Status

- ✅ **91 testes passando** (sem LLM) — executa em ~5s
- ✅ **12 testes trieval** (com LLM) — 5 golden cases
- ✅ **4 Gates de validação** funcionais (Base Data → Custos → Cronograma → Viabilidade)
- ✅ **Copilot instructions** para usar sem Claude Desktop

## 🚀 Quick Start

### Rodar evals sem LLM (padrão, recomendado para CI/CD)

```bash
python3 -m pytest evals/ -m "not trieval" -q
```

ou via runner:

```bash
python3 evals/run_evals.py
```

**Saída esperada:**
```
91 passed, 12 deselected in 2.23s
```

### Rodar com LLM (trieval)

```bash
# 1. Instalar dependências (em virtual environment)
python3 -m venv venv && source venv/bin/activate
pip install -r requirements-trieval.txt

# 2. Exportar chave da API
export OPENAI_API_KEY=sk-...

# 3. Rodar evals com LLM
python3 evals/run_evals.py --with-llm --report
```

Veja [TRIEVAL_SETUP.md](TRIEVAL_SETUP.md) para detalhes de instalação.

## 📁 Estrutura

```
evals/
├── conftest.py                      # Fixtures mock (sem .xlsm)
├── test_skill1_base_data.py        # Layer 1 (15 testes)
├── test_skill2_operational.py      # Layer 2 (19 testes) ← ENCARGOS
├── test_skill3_planning.py         # Layer 3 (14 testes)
├── test_skill4_financial.py        # Layer 4 (19 testes)
├── test_e2e_workflow.py            # E2E + 4 Gates (15 testes)
├── test_trieval_integration.py     # RAG (21 testes, 12 com LLM)
├── run_evals.py                    # CLI runner
└── report.json                     # Relatório gerado

.github/
└── copilot-instructions.md         # Copilot custom instructions

TRIEVAL_SETUP.md                    # Guia de instalação trieval
requirements-trieval.txt            # Dependências
pytest.ini                          # Configuração pytest
```

## ✅ Casos de Avaliação

### Layer 1 — Base Data (15 testes)
- ✓ Tabelas obrigatórias definidas
- ✓ MÃO DE OBRA com exact_match = true
- ✓ ENCARGOS totalizando 66%
- ✓ CPU com preços positivos
- ✓ Sincronização de nomes exatos

### Layer 2 — Operacional (19 testes)
- ✓ Multiplicador ENCARGOS 1.66
- ✓ calculate_crew_cost com escala linear
- ✓ validate_cost_delta (C_FIXO < 5%)
- ✓ aggregate_indirect
- ✓ validate_team_composition

### Layer 3 — Planejamento (14 testes)
- ✓ validate_schedule (100% completion)
- ✓ calculate_bdi (markup correto)
- ✓ Fórmula de produção mensal
- ✓ BDI com ou sem categorias

### Layer 4 — Validação Financeira (19 testes)
- ✓ validate_profitability (8%-10% target)
- ✓ calculate_breakeven (Custos Fixos / Margem)
- ✓ sensitivity_analysis (±5%, ±10%, ±15%)
- ✓ Health status (🟢🟡🔴)

### E2E — Workflow Completo (15 testes)
- ✓ **Gate 1:** Base data válida (ENCARGOS)
- ✓ **Gate 2:** Costs converged (delta < 5%)
- ✓ **Gate 3:** Schedule 100% complete
- ✓ **Gate 4:** Profitability 8%-10%
- ✓ Cenário GO (todos gates passam)
- ✓ Cenário NOGO (gates falham)

### Trieval — RAG Quality (21 testes)
- ✓ 5 golden cases (EC-001 a EC-005)
- ✓ Estrutura dos casos (sem LLM)
- ✓ Avaliação com LLM (com `--with-llm`)
- ✓ Anti-alucinação (EC-005)
- ✓ Métricas: Faithfulness, Context Relevance, Answer Relevance, etc

**Golden Cases:**

| ID | Categoria | Descrição |
|----|-----------|-----------|
| EC-001 | operational-encargos | Agente multiplica salário por 1.66 |
| EC-002 | planning-bdi | BDI aplicado corretamente ao custo |
| EC-003 | financial-viability | Margem 7% é classificada como NOGO |
| EC-004 | financial-breakeven | Ponto de equilíbrio = Custos Fixos / Margem |
| EC-005 | anti-hallucination | Agente não responde sem contexto |

## 🎯 Como Reproduzir Comportamento do Copilot (sem Claude Desktop)

O arquivo [.github/copilot-instructions.md](.github/copilot-instructions.md) contém as instrções customizadas do Copilot. Estas instruções:

1. **Definem o fluxo obrigatório:** Layer 1 → 2 → 3 → 4
2. **Proíbem alucinações:** ❌ "In my experience, margins are..."
3. **Forçam dados reais:** ✅ "Tool load_base_data returned..."
4. **Aplicam ENCARGOS:** Salário × 1.66 (crítico)
5. **Requerem validação:** Delta < 5%, Margem 8%-10%

**Use com Copilot no VS Code:**
- O Copilot lê automaticamente `.github/copilot-instructions.md`
- Responde com o mesmo rigor que o Claude Desktop seria forçado a seguir
- Todas as respostas devem passar pelos 4 Gates

## 🔧 CLI Runner

```bash
python3 evals/run_evals.py [opções]

Opções:
  --layer N          Executar apenas Layer N (1-4)
  --only-e2e         Executar apenas E2E
  --with-llm         Incluir testes trieval (requer trieval + OPENAI_API_KEY)
  --report           Gerar report.json em evals/
  -x, --fail-fast    Parar na primeira falha
```

**Exemplos:**

```bash
# Todos os evals (sem LLM)
python3 evals/run_evals.py

# Apenas Layer 2 (ENCARGOS)
python3 evals/run_evals.py --layer 2

# E2E + relatório JSON
python3 evals/run_evals.py --only-e2e --report

# Com LLM, fail-fast
python3 evals/run_evals.py --with-llm -x
```

## 📊 Relatório Gerado

Com `--report`, é gerado `evals/report.json`:

```json
{
  "timestamp": "2026-04-16T19:58:04.610931+00:00",
  "overall_passed": true,
  "suites": {
    "1": {
      "label": "Layer 1 — Base Data",
      "exit_code": 0,
      "passed": true
    },
    ...
  }
}
```

Use para CI/CD, dashboards, histórico de qualidade.

## ⚠️ Limitações Conhecidas

1. **trieval não instalado** — Sistema com `externally-managed-environment`
   - **Solução:** Use venv ou `--break-system-packages` ([TRIEVAL_SETUP.md](TRIEVAL_SETUP.md))

2. **Dados mock, não reais** — evals usam DataFrames em memória
   - **Quando dados reais forem disponíveis:** Remova `mock_path.touch()` de conftest.py
   - Skills carregarão dados reais da planilha .xlsm

3. **Sem integração de CI/CD** — Pronto para adicionar
   - GitHub Actions, GitLab CI, Jenkins, etc

## 🔐 Garantias de Qualidade

✅ **ENCARGOS sempre 1.66** — Validado em Layer 2 + EC-001
✅ **Delta C_FIXO < 5%** — Gate 2 falha se exceder
✅ **Cronograma 100%** — Gate 3 bloqueia incompletos
✅ **Margem 8%-10%** — Gate 4 rejeita viabilidade fora da faixa
✅ **Anti-alucinação** — EC-005 detecta respostas sem contexto
✅ **Rastreabilidade** — Cada resposta cita fonte (Layer 1-4)

## 📚 Referências

- [TRIEVAL_SETUP.md](TRIEVAL_SETUP.md) — Como instalar trieval
- [.github/copilot-instructions.md](.github/copilot-instructions.md) — Custom instructions
- [requirements-trieval.txt](requirements-trieval.txt) — Dependências completas
- `evals/conftest.py` — Dados mock das 8 tabelas AGIS

## 🚧 Próximos Passos (Opcional)

1. Integrar com CI/CD (GitHub Actions)
2. Adicionar cobertura de dados reais quando .xlsm disponível
3. Expandir golden cases trieval (mais cenários)
4. Adicionar benchmarks de performance (tempo de execução)
5. Dashboard de histórico de evals (passa/falha por commit)

---

**Mantém:**
- Simples (pytest + python3)
- Rápido (5s sem LLM)
- Confiável (91 testes passando)
- Extensível (add novos evals facilmente)
