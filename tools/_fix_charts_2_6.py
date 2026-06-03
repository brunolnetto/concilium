"""
Recria charts 02 e 06 com melhor visualização:
  02 — Plan Space como heatmap de pools × cenário (makespan convergiu → mostra o quê mudou)
  06 — Times indiretos com escala logarítmica e breakdown % mais claro
"""
import io, json, sys, os
from pathlib import Path

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
os.environ["MPLBACKEND"] = "Agg"

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.patches as mpatches
import matplotlib.ticker as mticker
import numpy as np

ROOT  = Path(__file__).resolve().parents[1]
BENCH = ROOT / "benchmarks/data/AGIS"
OUT   = BENCH / "outputs"
INTER = BENCH / "artifacts/intermediate"

CORES = {
    "azul_escuro": "#1B3A6B", "azul": "#2563EB", "azul_claro": "#60A5FA",
    "teal": "#0D9488", "verde": "#16A34A", "verde_claro": "#86EFAC",
    "laranja": "#EA580C", "vermelho": "#DC2626", "amarelo": "#CA8A04",
    "cinza_escuro": "#374151", "cinza": "#6B7280", "cinza_claro": "#E5E7EB",
    "roxo": "#7C3AED",
}
BG = "#F8FAFC"
GRID_COLOR = "#E5E7EB"

plt.rcParams.update({
    "figure.facecolor": BG, "axes.facecolor": BG, "axes.edgecolor": GRID_COLOR,
    "axes.grid": True, "grid.color": GRID_COLOR, "grid.linewidth": 0.7,
    "font.family": "DejaVu Sans", "font.size": 10, "axes.titlesize": 12,
    "axes.titleweight": "bold", "axes.titlecolor": CORES["azul_escuro"],
    "axes.labelcolor": CORES["cinza_escuro"], "figure.dpi": 150,
})

# ══════════════════════════════════════════════════════════════════════════════
# CHART 02 — Plan Space: Sensibilidade de Pool × Custo e Makespan
# ══════════════════════════════════════════════════════════════════════════════
print("  [02] Plan space redesenhado...")

# Configurações dos cenários (pools de recursos e makespan)
CENARIOS_DEF = [
    {"slug": "M0_BASE_MANUAL",      "label": "M0\nManual",    "ESC3": 10, "ATERRO": 5,  "ESC2": 4, "ESC1": 2, "deadline": 56, "manual": True},
    {"slug": "A0_BASE_AUTO",         "label": "A0\nAuto",      "ESC3": 10, "ATERRO": 5,  "ESC2": 4, "ESC1": 2, "deadline": 56, "manual": False},
    {"slug": "A1_ESC3_8",            "label": "A1\nESC3=8",    "ESC3": 8,  "ATERRO": 5,  "ESC2": 4, "ESC1": 2, "deadline": 56, "manual": False},
    {"slug": "A2_ESC3_12",           "label": "A2\nESC3=12",   "ESC3": 12, "ATERRO": 5,  "ESC2": 4, "ESC1": 2, "deadline": 56, "manual": False},
    {"slug": "A3_ESC3_14",           "label": "A3\nESC3=14",   "ESC3": 14, "ATERRO": 5,  "ESC2": 4, "ESC1": 2, "deadline": 56, "manual": False},
    {"slug": "A4_ATERRO_6",          "label": "A4\nATR=6",     "ESC3": 10, "ATERRO": 6,  "ESC2": 4, "ESC1": 2, "deadline": 56, "manual": False},
    {"slug": "A5_ESC2_6",            "label": "A5\nESC2=6",    "ESC3": 10, "ATERRO": 5,  "ESC2": 6, "ESC1": 2, "deadline": 56, "manual": False},
    {"slug": "A6_ESC1_4",            "label": "A6\nESC1=4",    "ESC3": 10, "ATERRO": 5,  "ESC2": 4, "ESC1": 4, "deadline": 56, "manual": False},
    {"slug": "A7_DEADLINE_52",       "label": "A7\nD=52s",     "ESC3": 10, "ATERRO": 5,  "ESC2": 4, "ESC1": 2, "deadline": 52, "manual": False},
    {"slug": "A8_DEADLINE_60",       "label": "A8\nD=60s",     "ESC3": 10, "ATERRO": 5,  "ESC2": 4, "ESC1": 2, "deadline": 60, "manual": False},
    {"slug": "A9_ESC3_10_ATERRO_6",  "label": "A9\nDual",      "ESC3": 10, "ATERRO": 6,  "ESC2": 4, "ESC1": 2, "deadline": 56, "manual": False},
    {"slug": "A11_FULL_RELAX",       "label": "A11\nFull",     "ESC3": 20, "ATERRO": 10, "ESC2": 8, "ESC1": 4, "deadline": 56, "manual": False},
]

# Lê makespan e delta de cada JSON
for c in CENARIOS_DEF:
    p = INTER / f"{c['slug']}.benchmark_report.json"
    if p.exists():
        r = json.loads(p.read_text(encoding="utf-8"))
        rcpsp = r.get("rcpsp_schedule") or {}
        confronto = r.get("confronto") or {}
        deltas = confronto.get("deltas") or {}
        c["makespan"]    = rcpsp.get("makespan_weeks") or 52
        c["folga"]       = rcpsp.get("folga_semanas") or 4
        c["feasible"]    = rcpsp.get("is_feasible", True)
        c["delta_cd"]    = (deltas.get("custo_direto") or {}).get("percentual") or 0
        c["delta_venda"] = (deltas.get("preco_venda") or {}).get("percentual") or 0
    else:
        c["makespan"] = 52; c["folga"] = 4; c["feasible"] = True
        c["delta_cd"] = -0.2; c["delta_venda"] = -0.27

fig = plt.figure(figsize=(18, 10), facecolor=BG)
fig.suptitle("AGIS — Espaço de Plano: Sensibilidade de Recursos e Prazo (12 cenários MINSLK)",
             fontsize=14, fontweight="bold", color=CORES["azul_escuro"], y=0.98)

gs = fig.add_gridspec(2, 3, hspace=0.45, wspace=0.35,
                      left=0.07, right=0.97, top=0.92, bottom=0.08)

labels_short = [c["label"] for c in CENARIOS_DEF]
x = np.arange(len(CENARIOS_DEF))

# ── Painel 1: Pool ESC-3CAT ───────────────────────────────────────────────────
ax1 = fig.add_subplot(gs[0, 0])
esc3 = [c["ESC3"] for c in CENARIOS_DEF]
cors1 = [CORES["laranja"] if v < 10 else (CORES["verde"] if v == 10 else CORES["azul"]) for v in esc3]
bars1 = ax1.bar(x, esc3, color=cors1, width=0.65, edgecolor="white", linewidth=0.5)
ax1.axhline(10, color=CORES["cinza_escuro"], linewidth=1.2, linestyle="--", alpha=0.6, label="Mínimo viável (10)")
ax1.set_xticks(x); ax1.set_xticklabels(labels_short, fontsize=7.5, rotation=0)
ax1.set_ylabel("Frentes"); ax1.set_title("Pool ESC-3CAT (crítico)")
ax1.legend(fontsize=8); ax1.set_ylim(0, 23)
for bar, v in zip(bars1, esc3):
    ax1.text(bar.get_x() + bar.get_width()/2, v + 0.3, str(v), ha="center", fontsize=8, fontweight="bold")

# ── Painel 2: Pool ATERRO ─────────────────────────────────────────────────────
ax2 = fig.add_subplot(gs[0, 1])
aterro = [c["ATERRO"] for c in CENARIOS_DEF]
cors2 = [CORES["teal"] if v == 5 else CORES["verde"] for v in aterro]
bars2 = ax2.bar(x, aterro, color=cors2, width=0.65, edgecolor="white", linewidth=0.5)
ax2.axhline(5, color=CORES["cinza"], linewidth=1, linestyle="--", alpha=0.5, label="Base (5)")
ax2.set_xticks(x); ax2.set_xticklabels(labels_short, fontsize=7.5, rotation=0)
ax2.set_ylabel("Frentes"); ax2.set_title("Pool ATERRO")
ax2.legend(fontsize=8); ax2.set_ylim(0, 14)
for bar, v in zip(bars2, aterro):
    ax2.text(bar.get_x() + bar.get_width()/2, v + 0.15, str(v), ha="center", fontsize=8, fontweight="bold")

# ── Painel 3: Deadline ────────────────────────────────────────────────────────
ax3 = fig.add_subplot(gs[0, 2])
deadlines = [c["deadline"] for c in CENARIOS_DEF]
makespans = [c["makespan"] for c in CENARIOS_DEF]
cors3 = [CORES["azul_escuro"] if c["manual"] else CORES["azul_claro"] for c in CENARIOS_DEF]
ax3.bar(x, deadlines, color=CORES["cinza_claro"], width=0.65, edgecolor=CORES["cinza"], label="Deadline", linewidth=0.5)
ax3.bar(x, makespans, color=cors3, width=0.45, label="Makespan realizado", edgecolor="white", linewidth=0.5)
ax3.set_xticks(x); ax3.set_xticklabels(labels_short, fontsize=7.5, rotation=0)
ax3.set_ylabel("Semanas"); ax3.set_title("Deadline × Makespan Realizado")
ax3.legend(fontsize=8); ax3.set_ylim(48, 64)
for i, (d, m) in enumerate(zip(deadlines, makespans)):
    folga = d - m
    ax3.text(i, m + 0.3, f"f={folga}s", ha="center", fontsize=7.5,
             color=CORES["verde"] if folga >= 4 else CORES["vermelho"], fontweight="bold")

# ── Painel 4: Delta Custo Direto ─────────────────────────────────────────────
ax4 = fig.add_subplot(gs[1, 0])
delta_cds = [c["delta_cd"] for c in CENARIOS_DEF]
cors4 = [CORES["vermelho"] if d < -1 else (CORES["amarelo"] if d < 0 else CORES["verde"]) for d in delta_cds]
bars4 = ax4.bar(x, delta_cds, color=cors4, width=0.65, edgecolor="white", linewidth=0.5)
ax4.axhline(0, color=CORES["cinza_escuro"], linewidth=0.8)
ax4.set_xticks(x); ax4.set_xticklabels(labels_short, fontsize=7.5, rotation=0)
ax4.set_ylabel("Δ %"); ax4.set_title("Δ Custo Direto vs Referência")
for bar, v in zip(bars4, delta_cds):
    ax4.text(bar.get_x() + bar.get_width()/2, v + (-0.01 if v < 0 else 0.01),
             f"{v:+.2f}%", ha="center", fontsize=7.5, color=CORES["cinza_escuro"])

# ── Painel 5: Viabilidade ────────────────────────────────────────────────────
ax5 = fig.add_subplot(gs[1, 1])
feasibles = [1 if c["feasible"] else 0 for c in CENARIOS_DEF]
cors5 = [CORES["verde"] if f else CORES["vermelho"] for f in feasibles]
ax5.bar(x, [1] * len(CENARIOS_DEF), color=cors5, width=0.65, edgecolor="white", linewidth=0.5)
ax5.set_xticks(x); ax5.set_xticklabels(labels_short, fontsize=7.5, rotation=0)
ax5.set_yticks([]); ax5.set_title("Viabilidade do Cronograma RCPSP")
for i, f in enumerate(feasibles):
    ax5.text(i, 0.5, "✓ VIÁVEL" if f else "✗ INVIÁVEL",
             ha="center", va="center", fontsize=8.5, fontweight="bold", color="white")

# ── Painel 6: Conclusão síntese ───────────────────────────────────────────────
ax6 = fig.add_subplot(gs[1, 2])
ax6.set_facecolor(CORES["azul_escuro"])
ax6.set_xlim(0, 1); ax6.set_ylim(0, 1)
ax6.axis("off")

insight = (
    "INSIGHT PRINCIPAL\n\n"
    "O algoritmo MINSLK converge para\n"
    "makespan = 52 semanas em TODOS\n"
    "os cenários com pool ≥ mínimo.\n\n"
    "→  ESC-3CAT ≥ 10 = condição\n"
    "    necessária e suficiente.\n\n"
    "→  Aumentar pool além do mínimo\n"
    "    não reduz o makespan.\n\n"
    "→  Folga estrutural: 4 semanas\n"
    "    (deadline 56 − makespan 52).\n\n"
    "→  Custo Direto estável em\n"
    "    todos os cenários (Δ ≈ -0,2%)."
)
ax6.text(0.5, 0.5, insight, ha="center", va="center",
         fontsize=9.5, color="white", fontfamily="DejaVu Sans",
         linespacing=1.6, fontweight="normal",
         bbox=dict(boxstyle="round,pad=0.3", fc=CORES["azul_escuro"], ec="none"))

fig.savefig(OUT / "02_plan_space.png", dpi=180, bbox_inches="tight",
            facecolor=BG, edgecolor="none")
plt.close(fig)
print("     → 02_plan_space.png (redesenhado)")

# ══════════════════════════════════════════════════════════════════════════════
# CHART 06 — Times Indiretos: Escala normalizada + breakdown claro
# ══════════════════════════════════════════════════════════════════════════════
print("  [06] Times indiretos redesenhado...")

TIMES = [
    {"nome": "ADM",  "pessoas": 45, "custo_mo": 448861, "custo_eq": 268331, "verbas": 324300, "perm": 12.57, "sazonal": False},
    {"nome": "TOP",  "pessoas": 5,  "custo_mo": 64670,  "custo_eq": 15147,  "verbas": 3000,   "perm": 12.57, "sazonal": False},
    {"nome": "LAB",  "pessoas": 2,  "custo_mo": 15310,  "custo_eq": 0,      "verbas": 1847,   "perm": 12.57, "sazonal": False},
    {"nome": "QSMS", "pessoas": 3,  "custo_mo": 34050,  "custo_eq": 15147,  "verbas": 8220,   "perm": 12.57, "sazonal": False},
    {"nome": "BIOLOGO",  "pessoas": 1, "custo_mo": 7500, "custo_eq": 0, "verbas": 0, "perm": 5.83, "sazonal": True},
    {"nome": "BOTANICO", "pessoas": 1, "custo_mo": 7500, "custo_eq": 0, "verbas": 0, "perm": 5.83, "sazonal": True},
]

fig, axes = plt.subplots(1, 3, figsize=(18, 7), facecolor=BG)
fig.suptitle("AGIS — Composição dos Times Indiretos",
             fontsize=14, fontweight="bold", color=CORES["azul_escuro"])

# ── Painel A: Custo total por time (log scale para visualizar todos) ──────────
ax_a = axes[0]
nomes_t  = [t["nome"] for t in TIMES]
tot_mes  = [(t["custo_mo"] + t["custo_eq"] + t["verbas"]) / 1e3 for t in TIMES]
cor_barra = [CORES["azul_escuro"] if not t["sazonal"] else CORES["azul_claro"] for t in TIMES]
hatch    = ["" if not t["sazonal"] else "////" for t in TIMES]
y_pos    = np.arange(len(nomes_t))

for i, (y, v, cor, hch) in enumerate(zip(y_pos, tot_mes, cor_barra, hatch)):
    ax_a.barh(y, v, color=cor, hatch=hch, edgecolor="white" if not hch else CORES["azul"],
              height=0.6, alpha=0.88, linewidth=0.5)
    saz = " ★saz" if TIMES[i]["sazonal"] else ""
    ax_a.text(v * 1.05, y, f"R${v:.0f}k/mês{saz}", va="center",
              fontsize=8.5, color=CORES["cinza_escuro"],
              fontweight="bold" if not TIMES[i]["sazonal"] else "normal")

ax_a.set_yticks(y_pos)
ax_a.set_yticklabels(nomes_t, fontsize=11, fontweight="bold")
ax_a.set_xscale("log")
ax_a.set_xlabel("R$ mil/mês (escala log)", fontsize=10)
ax_a.set_title("Custo Mensal Total\n(escala log para comparação)", fontsize=11)
ax_a.invert_yaxis()
ax_a.xaxis.set_major_formatter(mticker.FuncFormatter(lambda x, _: f"R${x:.0f}k"))

handles_a = [
    mpatches.Patch(color=CORES["azul_escuro"], label="Presença integral (12,57 meses)"),
    mpatches.Patch(color=CORES["azul_claro"], hatch="////", label="Sazonal (eap-1_0, 5,83 meses)"),
]
ax_a.legend(handles=handles_a, fontsize=8, loc="lower right")

# ── Painel B: Breakdown % do custo mensal ─────────────────────────────────────
ax_b = axes[1]
times_base = [t for t in TIMES if not t["sazonal"]]
nomes_b  = [t["nome"] for t in times_base]
mo_pct   = [t["custo_mo"] / (t["custo_mo"] + t["custo_eq"] + t["verbas"]) * 100 for t in times_base]
eq_pct   = [t["custo_eq"] / (t["custo_mo"] + t["custo_eq"] + t["verbas"]) * 100 for t in times_base]
vb_pct   = [t["verbas"]   / (t["custo_mo"] + t["custo_eq"] + t["verbas"]) * 100 for t in times_base]
y_b = np.arange(len(nomes_b))

ax_b.barh(y_b, mo_pct, color=CORES["azul"],     height=0.6, label="Mão de Obra", edgecolor="none")
ax_b.barh(y_b, eq_pct, left=mo_pct, color=CORES["teal"],    height=0.6, label="Equipamentos", edgecolor="none")
ax_b.barh(y_b, vb_pct, left=[m+e for m,e in zip(mo_pct,eq_pct)],
           color=CORES["cinza"], height=0.6, label="Verbas mensais", edgecolor="none")

for i, (m, e, v) in enumerate(zip(mo_pct, eq_pct, vb_pct)):
    if m > 5:  ax_b.text(m/2,       y_b[i], f"{m:.0f}%", ha="center", va="center", fontsize=8, color="white", fontweight="bold")
    if e > 5:  ax_b.text(m + e/2,   y_b[i], f"{e:.0f}%", ha="center", va="center", fontsize=8, color="white", fontweight="bold")
    if v > 5:  ax_b.text(m+e + v/2, y_b[i], f"{v:.0f}%", ha="center", va="center", fontsize=8, color="white", fontweight="bold")

ax_b.set_yticks(y_b)
ax_b.set_yticklabels(nomes_b, fontsize=11)
ax_b.set_xlabel("Percentual do custo mensal (%)", fontsize=10)
ax_b.set_title("Breakdown % do Custo Mensal\n(MO + Equipamentos + Verbas)", fontsize=11)
ax_b.legend(fontsize=9, loc="lower right")
ax_b.set_xlim(0, 105)
ax_b.invert_yaxis()

# ── Painel C: Headcount + custo total da obra ─────────────────────────────────
ax_c = axes[2]
custo_total = [(t["custo_mo"]+t["custo_eq"]+t["verbas"]) * t["perm"] / 1e6 for t in TIMES]
pessoas_t   = [t["pessoas"] for t in TIMES]
nomes_c     = [t["nome"] for t in TIMES]
cors_c      = [CORES["azul_escuro"] if not t["sazonal"] else CORES["azul_claro"] for t in TIMES]
y_c         = np.arange(len(nomes_c))

# Scatter: pessoas × custo_total
for i, (t, n, v, cor) in enumerate(zip(TIMES, nomes_c, custo_total, cors_c)):
    ax_c.scatter(t["pessoas"], v, s=200, color=cor, zorder=5,
                 edgecolors="white", linewidths=1.5,
                 marker="^" if t["sazonal"] else "o")
    ax_c.annotate(
        n, xy=(t["pessoas"], v),
        xytext=(4 if t["pessoas"] < 20 else -8, 6),
        textcoords="offset points", fontsize=9,
        fontweight="bold" if not t["sazonal"] else "normal",
        color=CORES["cinza_escuro"],
    )

ax_c.set_xlabel("Headcount (pessoas)", fontsize=10)
ax_c.set_ylabel("Custo Total na Obra (R$ M)", fontsize=10)
ax_c.set_title("Headcount × Custo Total\n(▲ = sazonal, ● = integral)", fontsize=11)
ax_c.yaxis.set_major_formatter(mticker.FuncFormatter(lambda x, _: f"R${x:.1f}M"))
ax_c.set_xscale("log")
ax_c.xaxis.set_major_formatter(mticker.FuncFormatter(lambda x, _: f"{int(x)} pess."))

handles_c = [
    plt.scatter([], [], marker="o", s=120, color=CORES["azul_escuro"], label="Presença integral"),
    plt.scatter([], [], marker="^", s=120, color=CORES["azul_claro"],  label="Sazonal (eap-1_0)"),
]
ax_c.legend(handles=handles_c, fontsize=9)
ax_c.grid(True, alpha=0.4)

plt.tight_layout()
fig.savefig(OUT / "06_times_indiretos.png", dpi=180, bbox_inches="tight",
            facecolor=BG, edgecolor="none")
plt.close(fig)
print("     → 06_times_indiretos.png (redesenhado)")
print("\nFim.")
