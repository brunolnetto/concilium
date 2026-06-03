"""Compara o benchmark AGIS atual com o resultado anterior para detectar regressões."""
import io, json, sys
from pathlib import Path

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

ROOT  = Path(__file__).resolve().parents[1]
BENCH = ROOT / "benchmarks/data/AGIS"

# Report anterior (salvo em artifacts/audit antes do --reset)
ANTES = BENCH / "artifacts/audit/benchmark_report.json"
# Report atual (gerado pelo --reset)
DEPOIS = BENCH / "audit/benchmark_report.json"

def load(p):
    if p.exists():
        return json.loads(p.read_text(encoding="utf-8"))
    print(f"  [FALTANDO] {p}")
    return None

antes  = load(ANTES)
depois = load(DEPOIS)

if not antes or not depois:
    # Tenta o intermediário
    ANTES = BENCH / "artifacts/intermediate/relatorio.json"
    antes = load(ANTES)

print("=" * 70)
print("ANÁLISE DE REGRESSÕES — BENCHMARK AGIS")
print("=" * 70)

# Status
def _get_status(r):
    if not r: return "N/A"
    return (r.get("status_final") or
            (r.get("quality_gates") or {}).get("decision") or
            r.get("decision") or "N/A")

def _get_custo(r, key):
    if not r: return None
    cf = r.get("confronto") or {}
    for src in [cf.get("ferramenta") or {}, cf.get("referencia") or {}, r]:
        v = src.get(key)
        if v is not None:
            return float(v)
    return None

def _get_delta(r, key):
    if not r: return None
    cf = r.get("confronto") or {}
    d = (cf.get("deltas") or {}).get(key) or {}
    return d.get("percentual")

# ── Report atual (DEPOIS do --reset) ─────────────────────────────────────────
# Lê do output do --reset que está em artifacts/intermediate
M0 = BENCH / "artifacts/intermediate/M0_BASE_MANUAL.benchmark_report.json"
m0 = load(M0)

print("\n[ANTES — resultado armazenado em artifacts/audit]")
if antes:
    print(f"  Status: {_get_status(antes)}")
    for k in ("custo_direto", "custo_total", "preco_venda"):
        v = _get_custo(antes, k)
        d = _get_delta(antes, k)
        ds = f"  Δ={d:+.2f}%" if d is not None else ""
        print(f"  {k:<25}: R$ {v:>18,.2f}{ds}" if v else f"  {k}: N/A")
else:
    print("  Arquivo não encontrado — usando relatorio.json intermediário")
    if antes:
        for k in ("custo_direto", "custo_total"):
            v = (antes.get("resultado") or {}).get(k)
            print(f"  {k}: R$ {v:,.2f}" if v else f"  {k}: N/A")

print("\n[DEPOIS — cenário M0_BASE_MANUAL (resultado atual)]")
if m0:
    print(f"  Status: {_get_status(m0)}")
    cf = m0.get("confronto") or {}
    ferr = cf.get("ferramenta") or {}
    ref  = cf.get("referencia") or {}
    deltas = cf.get("deltas") or {}
    for k in ("custo_direto", "custo_indireto", "custo_total", "preco_venda"):
        v_ferr = ferr.get(k)
        v_ref  = ref.get(k)
        delta  = (deltas.get(k) or {}).get("percentual")
        ds = f"  Δ={delta:+.2f}%" if delta is not None else ""
        print(f"  {k:<25}: engine=R${v_ferr:>14,.2f}  ref=R${v_ref:>14,.2f}{ds}" if v_ferr and v_ref else f"  {k}: N/A")

# ── Desvios de PU por item ────────────────────────────────────────────────────
print("\n[DESVIOS PU POR ITEM]")
if m0:
    gq = m0.get("quality_gates") or {}
    gates = gq.get("gates") or []
    for g in gates:
        pu_ok = g.get("pu_ok")
        item  = g.get("item_id") or g.get("atividade_id") or "?"
        pct   = g.get("desvio_pct") or g.get("delta_pct")
        status = "OK" if pu_ok else "DESVIO"
        if pct is not None:
            print(f"  {status:<8} {item:<40} {pct:+.1f}%")
        else:
            # Tenta outro formato
            for key, val in g.items():
                if "desvio" in key.lower() or "delta" in key.lower():
                    print(f"  {status:<8} {item:<40} {key}={val}")
                    break

# ── Regressões de catálogo ────────────────────────────────────────────────────
print("\n[ANÁLISE DE REGRESSÕES DO CATÁLOGO]")
if m0:
    cf = m0.get("confronto") or {}
    deltas = cf.get("deltas") or {}
    d_cd = (deltas.get("custo_direto") or {}).get("percentual")
    d_ct = (deltas.get("custo_total") or {}).get("percentual")
    d_pv = (deltas.get("preco_venda") or {}).get("percentual")

    print(f"  Delta custo direto  : {d_cd:+.2f}%" if d_cd is not None else "  Delta custo direto  : N/A")
    print(f"  Delta custo total   : {d_ct:+.2f}%" if d_ct is not None else "  Delta custo total   : N/A")
    print(f"  Delta preço venda   : {d_pv:+.2f}%" if d_pv is not None else "  Delta preço venda   : N/A")

    if d_cd is not None and abs(d_cd) > 5:
        print(f"  ⚠ REGRESSÃO DETECTADA: Δ custo direto = {d_cd:+.2f}% (threshold ±5%)")
    elif d_cd is not None:
        print(f"  ✓ Custo direto dentro do threshold (±5%)")

# Mostra breakdown financeiro completo
print("\n[BREAKDOWN FINANCEIRO ATUAL]")
if m0:
    breakdown = m0.get("breakdown_por_categoria") or {}
    for cat, val in breakdown.items():
        if isinstance(val, (int, float)) and val > 0:
            print(f"  {cat:<25}: R$ {val:>14,.2f}")

print("\n[VALIDAÇÕES SKILL 06]")
if m0:
    valids = m0.get("validacoes") or []
    for v in valids:
        if isinstance(v, dict):
            code = v.get("codigo") or ""
            status = v.get("status") or ""
            msg = (v.get("mensagem") or "")[:80]
            print(f"  [{status:5}] {code:<25} {msg}")
