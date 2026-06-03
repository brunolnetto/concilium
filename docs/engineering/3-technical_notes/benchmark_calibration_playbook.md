# Playbook: Calibração de Benchmarks — Procedimento Pós-AGIS

**Versão:** 1.0  
**Data:** 2026-05-11  
**Autoria:** Agente Engenheiro Sênior (Concilium/MendesLobo)  
**Baseado em:** Ciclo de calibração completo do benchmark AGIS (2026-05-11)

---

## 1. Contexto e Motivação

O benchmark AGIS revelou dois problemas sistêmicos que afetam **todos os benchmarks**:

| # | Problema | Efeito observado |
|---|---|---|
| P1 | ADR-038 override paramétrico por equipe | `custo_direto` -30,4% vs referência (AGIS: R$41M vs R$58,9M) |
| P2 | MOB = R$0 no `spec_loader.py` | `custo_indireto` subestimado em ~R$6,2M por projeto |

Ambos foram corrigidos e a solução está **propagada no catálogo** (ADR-050). Este playbook
descreve como replicar o processo para os 11 benchmarks restantes e validar os resultados.

---

## 2. Pré-requisitos Técnicos

### 2.1 Ambiente

```powershell
# Python do venv (executar no diretório concilium/)
$python = "C:\Users\bruno\OneDrive - Mendes Lobo\MendesLobo Construtora\Agente Engenheiro Sênior\.venv\Scripts\python.exe"
$env:CONCILIUM_ROOT = "C:\Users\bruno\OneDrive - Mendes Lobo\MendesLobo Construtora\Agente Engenheiro Sênior\concilium"
$env:CONCILIUM_CONFIG_ROOT = "$env:CONCILIUM_ROOT\config"
$env:CONCILIUM_PROJECTS_ROOT = "$env:CONCILIUM_ROOT\projetos"
```

### 2.2 Estado do Catálogo (já aplicado em 2026-05-11)

Os 52 CPUs do catálogo `mendeslobo` já têm `precos_unitarios_sbdi` populados com
os valores da planilha AGIS. A skill-04 já usa o caminho planilha-first (ADR-050).
O `spec_loader.py` já tem o MOB corrigido.

**Nenhum pré-requisito adicional de código.** Apenas executar benchmark por benchmark.

---

## 3. Valores de Referência por Benchmark

A tabela abaixo contém os alvos de comparação extraídos de cada `referencia.json`
(`resultado.benchmark_confronto_referencia`). Use-os para validar os deltas após cada run.

| Benchmark | CPUs | Custo Direto (ref) | Custo Indireto (ref) | Preço de Venda (ref) | Status |
|---|---:|---:|---:|---:|---|
| **AGIS** ✅ | 52 | R$ 58.985.224 | R$ 25.124.433 | R$ 97.663.745 | CALIBRADO |
| CTC | 6 | R$ 75.180.960 | R$ 28.286.131 | R$ 142.317.761 | ⚠️ ver nota |
| LUNDIN | 8 | R$ 12.761.743 | R$ 14.181.483 | R$ 43.659.291 | pendente |
| MARA_ROSA | 4 | R$ 0 | R$ 0 | R$ 0 | ⚠️ sem alvos |
| MATEC_GUARULHOS | 4 | R$ 19.737.601 | R$ 5.668.080 | R$ 28.669.628 | pendente |
| MATEC_HINES | 4 | R$ 17.753.070 | R$ 5.000.000 | R$ 28.000.000 | pendente |
| MATEC_UBERLANDIA | 4 | R$ 1.252.440 | R$ 8.592.088 | R$ 13.688.419 | pendente |
| ODFJELL | 4 | R$ 2.947.287 | R$ 1.813.470 | R$ 6.299.957 | pendente |
| PRIVATE_LOG | 6 | R$ 14.885.785 | R$ 6.882.876 | R$ 25.944.479 | pendente |
| ROSH | 1 | R$ 2.589.258 | R$ 3.065.109 | R$ 7.383.537 | pendente |
| RUMO | 18 | R$ 13.429.755 | R$ 3.341.476 | R$ 20.651.689 | pendente |
| VALE | 8 | R$ 8.903.472 | R$ 5.887.204 | R$ 17.671.000 | pendente |

> **Nota CTC:** A referência de R$75,1M é suspeita (inflada vs EAP técnica ~R$17,2M).
> Ver `docs/engineering/technical_notes/technical_note_ctc_discrepancy.md`.
> Tratar como inválida para fins de calibração de produtividade.
>
> **Nota MARA_ROSA:** `benchmark_confronto_referencia` está zerado. Investigar se
> a referência foi extraída corretamente antes de calibrar.

---

## 4. Procedimento por Benchmark

### 4.1 Script de Execução (run_bench_slug.py)

Criar `C:\Temp\run_bench_SLUG.py` substituindo `SLUG` pelo nome (ex: LUNDIN):

```python
import sys, os, json
ROOT = os.environ['CONCILIUM_ROOT']
sys.path.insert(0, os.path.join(ROOT, 'src'))
os.environ.setdefault('CONCILIUM_CONFIG_ROOT', os.path.join(ROOT, 'config'))
os.environ.setdefault('CONCILIUM_PROJECTS_ROOT', os.path.join(ROOT, 'projetos'))
from concilium.application.benchmarks import BenchmarkFacade
facade = BenchmarkFacade.from_env()
report = facade.run_single('LUNDIN', reset=True)  # <-- mudar slug aqui

skills = report.get('skills_log', [])
for s in skills:
    status = s.get('status'); skill = s.get('skill'); erros = s.get('erros', [])
    print(f'  {skill}: {status}' + (f' -- {erros[:1]}' if erros else ''))

confronto = report.get('confronto', {})
ferr = confronto.get('ferramenta', {})
deltas = confronto.get('deltas', {})
ind_bkdn = confronto.get('ferramenta_breakdown_indireto', {})

print('\n=== INDIRETO BREAKDOWN ===')
for k, v in ind_bkdn.items():
    print(f'  {k}: {v:,.2f}' if isinstance(v, float) else f'  {k}: {v}')

print('\n=== FERRAMENTA ===')
for k, v in ferr.items():
    if isinstance(v, float):
        print(f'  {k}: {v:,.2f}')

print('\n=== DELTAS ===')
for k, v in deltas.items():
    print(f'  {k}: {v}')

print('\nstatus_final:', report.get('status_final'))
```

### 4.2 Execução

```powershell
Start-Process -FilePath $python `
    -ArgumentList "C:\Temp\run_bench_SLUG.py" `
    -NoNewWindow -Wait `
    -RedirectStandardOutput "C:\Temp\bench_out_SLUG.txt" `
    -RedirectStandardError  "C:\Temp\bench_err_SLUG.txt"
Get-Content "C:\Temp\bench_out_SLUG.txt" | Select-Object -Last 40
Get-Content "C:\Temp\bench_err_SLUG.txt" | Select-Object -Last 10
```

### 4.3 Critérios de Aprovação (Gates ADR-043)

| Métrica | Gate S0 (ideal) | Gate S1 (atenção) | Ação se S2/S3 |
|---|---|---|---|
| `custo_direto` | ±5% | ±15% | Investigar CPUs do benchmark |
| `custo_indireto` | ±5% | ±15% | Verificar `spec_loader.py` |
| `preco_venda` | ±5% | ±15% | Revisar BDI e parâmetros |
| `status_final` | APROVADO | — | Verificar skills em ERRO |

---

## 5. Diagnóstico de Desvios Frequentes

### 5.1 `custo_direto` muito abaixo (< -15%)

**Causa provável:** CPU do benchmark não tem `precos_unitarios_sbdi` ou o campo está
zerado → skill-04 cai no caminho ADR-038 e distorce o PU.

**Diagnóstico:**
```python
import json, pathlib
ref = json.loads(pathlib.Path('benchmarks/data/SLUG/referencia.json').read_text('utf-8'))
for item in ref['cpus']['itens_eap']:
    cpu_file = pathlib.Path(f'config/catalogos/mendeslobo/cpus/{item["cpu_id"]}.json')
    if cpu_file.exists():
        cpu = json.loads(cpu_file.read_text('utf-8'))
        has_pu = 'precos_unitarios_sbdi' in cpu
        total = (cpu.get('precos_unitarios_sbdi') or {}).get('total', 0)
        print(f"{item['cpu_id']:50s}  pu_sbdi={'OK' if has_pu and total > 0 else 'AUSENTE'}")
```

**Correção:** Executar o script de calibração abaixo (§6) para o benchmark.

### 5.2 `custo_direto` muito acima (> +15%)

**Causa provável:** `precos_unitarios_sbdi` com valores incorretos (ex: campo `total`
incluindo BDI em vez de ser SBDI — sem BDI).

**Verificação:** Comparar `total_sbdi` do item em `referencia.json` com
`custo_direto_unitario_planilha` do CPU. Devem ser iguais (ou muito próximos).

### 5.3 `custo_indireto` próximo a zero

**Causa provável:** MOB ausente na configuração de perfil do projeto.

**Verificação:** Checar `config/perfis/mendeslobo.json` e confirmar que o campo
`mobilizacao` (ou equivalente) está mapeado corretamente no `spec_loader.py`.

**Nota histórica:** O MOB foi corrigido no spec_loader em 2026-05-11 (este ciclo AGIS).
Se um benchmark ainda mostrar MOB=0, o projeto foi criado antes da correção. Use `reset=True`.

### 5.4 Skill em ERRO / `status_final: REPROVADO`

1. Ver `erros` no log da skill afetada.
2. Verificar se todos os `cpu_id` da EAP do benchmark existem em `config/catalogos/mendeslobo/cpus/`.
3. CPUs inexistentes → criar o CPU ou mapear para um existente no `referencia.json`.

### 5.5 `custo_direto` diverge mas é < ±5%

Aceitar como S0. A diferença residual é arredondamento de PU (4 casas decimais no catálogo
vs planilha) e não requer ação.

---

## 6. Script de Calibração de CPU por Benchmark

Quando o benchmark tem CPUs sem `precos_unitarios_sbdi`, execute:

```python
"""
Injeta precos_unitarios_sbdi nos CPUs a partir da referencia.json do benchmark.
Uso: python calibrar_cpus_benchmark.py SLUG
"""
import sys, json, pathlib

SLUG = sys.argv[1]
ROOT = pathlib.Path(".")
REF  = ROOT / "benchmarks" / "data" / SLUG / "referencia.json"
CPUS = ROOT / "config" / "catalogos" / "mendeslobo" / "cpus"

ref = json.loads(REF.read_text("utf-8"))
n_ok = n_skip = n_miss = 0

for item in ref["cpus"]["itens_eap"]:
    cpu_id  = item.get("cpu_id", "")
    pu_ref  = item.get("precos_unitarios", {}) or {}
    mo      = float(pu_ref.get("mo_sbdi")       or 0)
    diesel  = float(pu_ref.get("diesel_sbdi")   or 0)
    mat     = float(pu_ref.get("material_sbdi") or 0)
    srv     = float(pu_ref.get("servicos_sbdi") or 0)
    total   = float(pu_ref.get("total_sbdi")    or 0)
    eq      = total - mo - diesel - mat  # resíduo = equipamentos/serviços

    cpu_file = CPUS / f"{cpu_id}.json"
    if not cpu_file.exists():
        print(f"  AUSENTE: {cpu_id}")
        n_miss += 1
        continue
    if total == 0:
        print(f"  SEM PU: {cpu_id} (total_sbdi=0)")
        n_skip += 1
        continue

    cpu = json.loads(cpu_file.read_text("utf-8"))
    cpu["precos_unitarios_sbdi"] = {
        "mo":           round(mo,     6),
        "diesel":       round(diesel, 6),
        "material":     round(mat,    6),
        "equipamentos": round(eq,     6),
        "total":        round(total,  6),
    }
    cpu["custo_direto_unitario_planilha"] = round(total, 6)
    cpu["fonte_preco"]           = f"PLANILHA_{SLUG}_{REF.stat().st_mtime:.0f}"
    cpu["data_referencia_preco"] = (ref.get("meta") or {}).get("extraido_em", "")[:10]
    cpu_file.write_text(json.dumps(cpu, ensure_ascii=False, indent=2), "utf-8")
    print(f"  OK: {cpu_id:50s}  total={total:.4f}")
    n_ok += 1

print(f"\nOK={n_ok}  sem PU={n_skip}  ausentes={n_miss}")
```

**Executar:**
```powershell
& $python calibrar_cpus_benchmark.py RUMO
```

> **Atenção:** Se o mesmo `cpu_id` aparece em múltiplos benchmarks, o último script
> executado sobrescreve o campo. Isso é aceitável se os PUs forem comparáveis entre
> projetos — caso contrário, avaliar criar CPUs separados por cliente/contrato.

---

## 7. Checklist de Execução por Benchmark

Para cada benchmark da tabela da §3, execute os passos abaixo e marque:

```
[ ] LUNDIN
    [ ] 1. Verificar se todos os cpu_ids existem no catálogo
    [ ] 2. Executar run_bench_LUNDIN.py com reset=True
    [ ] 3. Conferir bench_err: sem exceções críticas
    [ ] 4. Conferir custo_direto delta vs referência (alvo: ±5%)
    [ ] 5. Conferir custo_indireto delta (alvo: ±5%)
    [ ] 6. Conferir status_final = APROVADO
    [ ] 7. Se desvio > 5%: rodar calibrar_cpus_benchmark.py LUNDIN e repetir

[ ] MATEC_GUARULHOS   (mesma sequência)
[ ] MATEC_HINES       (mesma sequência)
[ ] MATEC_UBERLANDIA  (mesma sequência)
[ ] ODFJELL           (mesma sequência)
[ ] PRIVATE_LOG       (mesma sequência)
[ ] ROSH              (mesma sequência)
[ ] RUMO              (mesma sequência)
[ ] VALE              (mesma sequência)
[ ] CTC               (ler nota — referência provavelmente inválida)
[ ] MARA_ROSA         (investigar referência zerada antes de calibrar)
```

---

## 8. Referência Rápida: Estrutura `referencia.json`

```
referencia.json
├── meta
│   ├── slug              — identificador do benchmark (ex: "AGIS")
│   ├── projeto           — nome completo
│   ├── extraido_em       — data ISO da extração
│   └── fontes            — arquivos de origem (planilhas)
├── cpus
│   ├── total             — contagem de itens na EAP
│   └── itens_eap[*]
│       ├── item_id       — ex: "eap-01"
│       ├── cpu_id        — FK para config/catalogos/mendeslobo/cpus/<cpu_id>.json
│       ├── quantitativo  — quantidade na EAP
│       ├── custo_unit_sbdi  — PU total sem BDI (escalar)
│       └── precos_unitarios
│           ├── mo_sbdi       → precos_unitarios_sbdi.mo
│           ├── diesel_sbdi   → precos_unitarios_sbdi.diesel
│           ├── material_sbdi → precos_unitarios_sbdi.material
│           ├── servicos_sbdi → precos_unitarios_sbdi.equipamentos (resíduo)
│           └── total_sbdi    → precos_unitarios_sbdi.total
├── indiretos
│   └── ADM_TOP_LAB_QSMS_MOB — valores por componente
├── bdi
│   └── por_item[*] — BDI por componente por item
└── resultado
    ├── benchmark_confronto_referencia — ALVOS DE COMPARAÇÃO
    │   ├── custo_direto
    │   ├── custo_indireto
    │   ├── custo_total
    │   └── preco_venda
    └── benchmark_confronto_ferramenta — resultado atual da ferramenta (atualizado no run)
```

---

## 9. Lições Aprendidas (AGIS → generalizações)

| # | Lição | Impacto | Ação Sistemática |
|---|---|---|---|
| L1 | ADR-038 distorce PU em ambas as direções para itens com equipe | -30% custo_direto | ADR-050: precos_unitarios_sbdi no CPU evita ADR-038 |
| L2 | MOB ausente = R$0 no custo indireto | Subestima indireto em ~25% | spec_loader.py corrigido (permanente) |
| L3 | `reset=True` descarta patches manuais em canonical.json | Calibrações ad-hoc não persistem | Nunca calibrar canonical diretamente; sempre via catálogo |
| L4 | `custo_direto_catalogo` ≠ `custo_direto_equipes` — comparar contra o primeiro | Métrica errada = diagnóstico errado | projection.py usa `direto_catalogo` como métrica primária |
| L5 | CPUs duplicados (mesmo código) em referencia.json resultam em sobreposição | Itens reais com PUs incorretos | Usar `cpu_id` único por combinação material/dimensão |
| L6 | Referência CTC: cabeçalho inflado vs EAP técnica | Benchmark inválido para calibração | Validar consistência referência antes de calibrar (comparar Σ(PU×qty) vs header) |
| L7 | servicos_sbdi (subempreiteiro de drenagem) não tem categoria própria no modelo flat | equipamentos absorve serviços de terceiros | Considerar ADR-042 (terceirizado) para benchmarks com alto teor de subempreiteiros |

---

## 10. Histórico de Execuções

| Data | Benchmark | `custo_direto` Δ% | `custo_indireto` Δ% | `preco_venda` Δ% | Status |
|---|---|---|---|---|---|
| 2026-05-11 | AGIS | +0,39% | +0,17% | -0,64% | APROVADO ✅ |
