# ── Concilium — Makefile ──────────────────────────────────────────────────────
# Targets rápidos (< 1 min):   test  check
# Targets lentos  (> 1 min):   coverage  codebase-stats
# Utilitários:                  clean
# ─────────────────────────────────────────────────────────────────────────────

PYTHON      := python3
PACKAGE     := concilium
SRC         := src/$(PACKAGE)
TESTS_ALL   := tests
COV_DIR     := .coverage-reports
TEST_REPORT  := $(COV_DIR)/test-report.json
OPT          ?= lint,type,fmt,fsizes
COMMA := ,
SKIP  ?=
_SKIP_EXPR := $(subst $(COMMA), and not ,$(SKIP))
_SKIP_M    := $(if $(SKIP),-m "not $(_SKIP_EXPR)",)
# Desabilita logfire pydantic plugin antes do primeiro import de pydantic.
# logfire 4.x instala entry-point 'pydantic:logfire-plugin' que acrescenta ~10-15s
# de imports pesados (requests, OTel exporters, protobuf) se instalado no env.
TEST_ENV     := PYDANTIC_DISABLE_PLUGINS=__all__ OTEL_SDK_DISABLED=true

DEPLOY    := cd/scripts/deploy.sh
PROVISION := cd/scripts/provision.sh

.PHONY: help test test-file check _check_lint _check_type _check_fmt _check_fsizes \
        cov cov-stats clean \
        status smoke image promote rollback \
        configure keys bootstrap github-secrets exec concilium deploy-all

# ── Default ───────────────────────────────────────────────────────────────────
help:
	@echo ""
	@echo "  Concilium — targets disponíveis"
	@echo ""
	@echo "  Qualidade"
	@echo "    make clean                             Remove caches e artefatos temporários"
	@echo "    make test  [SKIP=slow,flaky]           Testes, agrupados por arquivo (-v)"
	@echo "    make test-file FILE=path/to_test.py    Roda um único arquivo de teste (-v)"
	@echo "    make cov                               Cobertura → $(COV_DIR)/"
	@echo "    make cov-stats                         Análise completa → $(COV_DIR)/report.md"
	@echo "    make check [OPT=lint,type,fmt,fsizes]  lint · type · fmt · file-sizes"
	@echo ""
	@echo "  Deploy"
	@echo "    make status                  Revisions ACA e pesos de tráfego"
	@echo "    make image       [TAG=x]     Build + push imagem para ACR"
	@echo "    make smoke       [REV=x]     Smoke tests contra revision ou produção"
	@echo "    make promote     [REV=x]     Direciona 100% do tráfego para revision"
	@echo "    make rollback    [REV=x]     Rollback para revision anterior"
	@echo ""
	@echo "  Plataforma"
	@echo "    make bootstrap   [VALIDATE=1] Provisiona infra Azure (idempotente)"
	@echo "    make keys        [ROTATE=1]  Gera (ou rotaciona) JWT keys → Key Vault"
	@echo "    make github-secrets          Configura GitHub Secrets/Vars via gh CLI"
	@echo "    make deploy-all              bootstrap → keys → github-secrets"
	@echo "    make configure               Aplica env vars nos containers ACA"
	@echo "    make exec              CMD='...'  az containerapp exec (shell se CMD omitido)"
	@echo "    make concilium [args]            concilium <args> no container (CMD= para flags --)"
	@echo ""

# ── Tests ─────────────────────────────────────────────────────────────────────
# -v (em vez de -q) imprime "arquivo::teste PASSED/FAILED" linha a linha, na ordem
# de coleta (por arquivo) — facilita achar rápido onde travou/quebrou.
test:
	$(TEST_ENV) $(PYTHON) -m pytest $(TESTS_ALL) -v --tb=short $(_SKIP_M)

# make test-file FILE=tests/unit/test_auth_store_coverage.py
test-file:
	$(TEST_ENV) $(PYTHON) -m pytest $(FILE) -v --tb=short $(_SKIP_M)

# ── Check (lint · type · fmt · fsizes) ────────────────────────────────────────
check:
	@for opt in $$(echo "$(OPT)" | tr ',' ' '); do \
		$(MAKE) -s _check_$$opt || exit 1; \
	done

_check_lint:
	@$(PYTHON) -m ruff check $(SRC) tests/ --ignore B008 --output-format json 2>/dev/null \
		| $(PYTHON) -c "\
import json,sys; d=json.load(sys.stdin); \
[print(f\"{x['filename']}:{x['location']['row']}:{x['location']['column']}: {x['code']} {x['message']}\") for x in d]; \
from collections import Counter; codes=Counter(x['code'] for x in d); \
fx=Counter(x['code'] for x in d if x.get('fix')); \
total=sum(codes.values()); ftotal=sum(fx.values()); \
print(f'\n  {total} violações ({ftotal} auto-corrigíveis com make check OPT=fmt)' if d else '  Sem violações.'); \
print('  Top 5:', ', '.join(f\"{c}×{n}\" for c,n in codes.most_common(5))) if d else None" || true

_check_type:
	ty check $(SRC)

_check_fmt:
	$(PYTHON) -m ruff format $(SRC) tests/
	$(PYTHON) -m ruff check --fix $(SRC) tests/ || true

_check_fsizes:
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

# ── Coverage ──────────────────────────────────────────────────────────────────
cov:
	@mkdir -p $(COV_DIR)
	@rm -f .coverage .coverage.*
	$(TEST_ENV) $(PYTHON) -m pytest $(TESTS_ALL) --tb=short \
		--cov=$(SRC) \
		--cov-branch \
		--tb=short \
		--cov-report=json:$(COV_DIR)/coverage.json \
		--json-report --json-report-file=$(TEST_REPORT) \
		--cov-report=term-missing:skip-covered \
		--no-header \
		--durations=50 -rfsx
	@echo "  Cobertura → $(COV_DIR)/{coverage.json,test-report.json}"´
	$(MAKE) cov-stats

# ── Codebase stats ────────────────────────────────────────────────────────────
cov-stats:
	@$(PYTHON) -c "\
from codebase_stats import CodebaseStatsReporter; \
import pathlib, json; \
rep = '$(TEST_REPORT)'; \
rep_ok = pathlib.Path(rep).exists() and 'tests' in json.loads(pathlib.Path(rep).read_text()); \
r = CodebaseStatsReporter(coverage_file='$(COV_DIR)/coverage.json', report_file=rep if rep_ok else None, radon_root='src', fs_root='src', tree_root='src'); \
p = r.save_report('$(COV_DIR)/report.md', include_tree=False, blame_limit=0, threshold=100); \
print(f'  Codebase stats → {p}')"

# ── Runtime CI/CD (wrappers para deploy.sh) ──────────────────────────────────

status:
	$(DEPLOY) status

image:
	$(DEPLOY) image $(if $(TAG),--tag $(TAG),)

smoke:
	$(DEPLOY) smoke $(if $(REV),--revision $(REV),)

promote:
	$(DEPLOY) promote $(if $(REV),--revision $(REV),)

rollback:
	$(DEPLOY) rollback $(if $(REV),--revision $(REV),)

# ── Plataforma (wrappers para provision.sh) ───────────────────────────────────

configure:
	$(PROVISION) configure

keys:
	$(PROVISION) keys $(if $(ROTATE),--rotate,)

bootstrap:
	$(PROVISION) bootstrap $(if $(VALIDATE),--validate,)

github-secrets:
	$(PROVISION) github

# `make concilium ops auth list` — palavras extras viram _CONCILIUM_ARGS.
# Para args com flags (--help, --client-id ...) use CMD=: make concilium CMD="ops --help"
ifeq (concilium,$(firstword $(MAKECMDGOALS)))
  _CONCILIUM_ARGS := $(wordlist 2,$(words $(MAKECMDGOALS)),$(MAKECMDGOALS))
  $(foreach _w,$(_CONCILIUM_ARGS),$(eval $(_w):;@:))
endif

exec:
	$(PROVISION) exec "$(CMD)"

concilium:
	$(PROVISION) exec "concilium $(or $(_CONCILIUM_ARGS),$(CMD))"

deploy-all:
	$(PROVISION) all

# ── Cleanup ───────────────────────────────────────────────────────────────────
clean:
	rm -rf $(COV_DIR) .coverage .coverage.* .lint-report.json
	find . -type d \( -name '__pycache__' -o -name '.pytest_cache' -o -name '.mypy_cache' -o -name '.ruff_cache' \) \
		-not -path './.git/*' -not -path './.venv/*' -exec rm -rf {} + 2>/dev/null || true
	find . -name '*.pyc' -not -path './.venv/*' -delete 2>/dev/null || true
	@echo "  Caches limpos."
