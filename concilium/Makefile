# ── Concilium — Makefile ──────────────────────────────────────────────────────
# Targets rápidos (< 1 min):   test  lint  lint-report  type-check  fmt
# Targets lentos  (> 1 min):   test-all  coverage  codebase-stats
# Utilitários:                  file-sizes  clean
# ─────────────────────────────────────────────────────────────────────────────

PYTHON      := python3
PACKAGE     := concilium
SRC         := src/$(PACKAGE)
TESTS_UNIT  := tests/unit
TESTS_ALL   := tests
COV_DIR     := .coverage-reports
LINT_REPORT := .lint-report.json
TEST_REPORT  := $(COV_DIR)/test-report.json
# Exclude skill manifests (dirs with dashes are not valid Python package names)
MYPY_EXCLUDE := --exclude 'src/concilium/application/skills/manifests'
SKIP_SLOW   := --ignore=$(TESTS_UNIT)/test_application_services_refactor.py \
               --ignore=$(TESTS_UNIT)/test_13_replan_advisor.py

.PHONY: help test test-all lint lint-report type-check fmt \
        coverage codebase-stats file-sizes size clean

# ── Default ───────────────────────────────────────────────────────────────────
help:
	@echo ""
	@echo "  Concilium — targets disponíveis"
	@echo ""
	@echo "  Rápidos (< 1 min)"
	@echo "    make test           Testes unitários"
	@echo "    make lint           Ruff: exibe violações (não falha em B008)"
	@echo "    make lint-report    Ruff: gera $(LINT_REPORT) agrupado por regra para agente de código"
	@echo "    make type-check     Mypy: checagem estática de tipos"
	@echo "    make fmt            Ruff: formata + corrige imports in-place"
	@echo ""
	@echo "  Lentos (> 1 min)"
	@echo "    make test-all       Unitários + integração"
	@echo "    make coverage       Cobertura → $(COV_DIR)/{coverage.json,test-report.json}"
	@echo "    make codebase-stats Análise completa → $(COV_DIR)/report.md (requer make coverage)"
	@echo ""
	@echo "  Utilitários"
	@echo "    make file-sizes     Maiores arquivos no repositório (detecta blobs acidentais)"
	@echo "    make clean          Remove caches, artefatos temporários e relatórios"
	@echo ""

# ── Tests ─────────────────────────────────────────────────────────────────────
test:
	$(PYTHON) -m pytest $(TESTS_UNIT) -q --tb=short $(SKIP_SLOW)

test-all:
	$(PYTHON) -m pytest $(TESTS_ALL) -q --tb=short $(SKIP_SLOW)

# ── Lint ──────────────────────────────────────────────────────────────────────
# B008: false-positive em Depends()/typer.Option() — ignorado no lint interativo.
# Para ver B008 também: make lint-report
lint:
	$(PYTHON) -m ruff check $(SRC) tests/ --ignore B008 || true
	@$(PYTHON) -m ruff check $(SRC) tests/ --output-format json 2>/dev/null \
		| $(PYTHON) -c "\
import json,sys; d=json.load(sys.stdin); \
from collections import Counter; codes=Counter(x['code'] for x in d); \
fx=Counter(x['code'] for x in d if x.get('fix')); \
total=sum(codes.values()); ftotal=sum(fx.values()); \
print(f'\n  {total} violações ({ftotal} auto-corrigíveis com make fmt)'); \
print('  Top 5:', ', '.join(f\"{c}×{n}\" for c,n in codes.most_common(5)))"

# Gera $(LINT_REPORT) agrupado por regra + severidade para leitura pelo agente de código.
lint-report:
	@$(PYTHON) -m ruff check $(SRC) tests/ --output-format json 2>/dev/null \
		| $(PYTHON) scripts/lint_report.py > $(LINT_REPORT)
	@echo "  Lint report → $(LINT_REPORT)"
	@$(PYTHON) -c "\
import json; r=json.load(open('$(LINT_REPORT)')); \
[print(f\"  {g['code']:<8} {g['count']:>4}  {'✓' if g['auto_fix'] else ' '}  {g['description']}\") \
 for g in sorted(r['by_rule'], key=lambda x: -x['count'])[:15]]; \
print(f\"\n  Total: {r['summary']['total']}  fixable: {r['summary']['fixable']}  manual: {r['summary']['manual']}\")"

# ── Type check ────────────────────────────────────────────────────────────────
type-check:
	$(PYTHON) -m mypy $(SRC) --ignore-missing-imports --no-error-summary $(MYPY_EXCLUDE)

# ── Format ────────────────────────────────────────────────────────────────────
fmt:
	$(PYTHON) -m ruff format $(SRC) tests/
	$(PYTHON) -m ruff check --fix $(SRC) tests/ || true
	@echo "  Auto-fix concluído. Violações remanescentes → make lint-report"

# ── Coverage ──────────────────────────────────────────────────────────────────
coverage:
	@mkdir -p $(COV_DIR)
	$(PYTHON) -m pytest $(TESTS_UNIT) -q --tb=short $(SKIP_SLOW) \
		--cov=$(SRC) \
		--cov-branch \
		--cov-report=json:$(COV_DIR)/coverage.json \
		--json-report --json-report-file=$(TEST_REPORT) \
		--cov-report=term-missing:skip-covered \
		--no-cov-on-fail
	@echo "  Cobertura → $(COV_DIR)/{coverage.json,test-report.json}"

# ── Codebase stats ────────────────────────────────────────────────────────────
codebase-stats:
	@test -f $(COV_DIR)/coverage.json || (echo "Run 'make coverage' first." && exit 1)
	@$(PYTHON) -c "\
from codebase_stats import CodebaseStatsReporter; \
import pathlib, json; \
rep = '$(TEST_REPORT)'; \
rep_ok = pathlib.Path(rep).exists() and 'tests' in json.loads(pathlib.Path(rep).read_text()); \
r = CodebaseStatsReporter( \
    coverage_file='$(COV_DIR)/coverage.json', \
    report_file=rep if rep_ok else None, \
    radon_root='src', fs_root='src', tree_root='src'); \
p = r.save_report('$(COV_DIR)/report.md', include_tree=False); \
print(f'  Codebase stats → {p}')"

# ── File sizes / Disk usage ───────────────────────────────────────────────────
# Reporta uso por diretório e detecta arquivos grandes (> 500 KB).
# Use 'make size' para o resumo rápido por pasta.
size file-sizes:
	@echo ""
	@echo "  Uso por diretório (inclui .venv e ignorados pelo Git):"
	@echo "  ────────────────────────────────────────────────────────"
	@du -sh * .venv .coverage-reports 2>/dev/null | sort -rh | \
		awk '{printf "  %8s  %s\n", $$1, $$2}'
	@echo ""
	@echo "  Arquivos > 500 KB (excluindo .venv e caches):"
	@echo "  ────────────────────────────────────────────────────────"
	@$(PYTHON) -c "\
from pathlib import Path; \
skip = {'.git','.venv','__pycache__','.coverage-reports','node_modules','.mypy_cache','.ruff_cache','.pytest_cache'}; \
files=sorted([(f.stat().st_size,str(f)) for f in Path('.').rglob('*') \
              if f.is_file() and not any(s in f.parts for s in skip)], reverse=True); \
large=[(s,p) for s,p in files if s>524288]; \
[print(f'  ⚠  {s/1024:>8.1f} KB  {p}') for s,p in large] if large \
  else print('  Nenhum arquivo > 500 KB fora do .venv.'); \
print(f'\n  Total rastreado: {len(files)} arquivos  |  {len(large)} blobs > 500 KB')"

# ── Cleanup ───────────────────────────────────────────────────────────────────
clean:
	rm -rf $(COV_DIR) .coverage $(LINT_REPORT)
	find . -type d -name '__pycache__'   -not -path './.git/*' -not -path './.venv/*' -exec rm -rf {} + 2>/dev/null || true
	find . -type d -name '.pytest_cache' -not -path './.git/*' -not -path './.venv/*' -exec rm -rf {} + 2>/dev/null || true
	find . -type d -name '.mypy_cache'   -not -path './.git/*' -not -path './.venv/*' -exec rm -rf {} + 2>/dev/null || true
	find . -type d -name '.ruff_cache'   -not -path './.git/*' -not -path './.venv/*' -exec rm -rf {} + 2>/dev/null || true
	find . -name '*.pyc' -not -path './.venv/*' -delete 2>/dev/null || true
	@echo "  Caches limpos."
