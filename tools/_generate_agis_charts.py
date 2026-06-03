"""
Geração de imagens PNG para o benchmark AGIS.

Gráficos gerados em benchmarks/data/AGIS/outputs/:
  01_gantt_cronograma.png       — Gantt das 11 atividades (via highcharts_gantt + fallback matplotlib)
  02_plan_space.png             — Comparação dos 12 cenários RCPSP (makespan × Δcusto)
  03_waterfall_financeiro.png   — Cascata de custo: direto → indireto → total → venda
  04_eap_criticidade.png        — Custo por item EAP com criticidade (A/B/C)
  05_indiretos_composicao.png   — Composição dos custos indiretos por categoria
  06_times_indiretos.png        — Pessoas e custo mensal por time indireto (ADM/TOP/LAB/QSMS)
"""
import io, json, sys, os
from pathlib import Path

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
os.environ["MPLBACKEND"] = "Agg"   # non-interactive backend

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.patches as mpatches
from matplotlib.patches import FancyBboxPatch
import matplotlib.ticker as mticker
import numpy as np

ROOT   = Path(__file__).resolve().parents[1]
BENCH  = ROOT / "benchmarks/data/AGIS"
OUT    = BENCH / "outputs"
INTER  = BENCH / "artifacts/intermediate"
REF    = BENCH / "referencia.json"

OUT.mkdir(parents=True, exist_ok=True)

# ── Paleta de cores corporativa ───────────────────────────────────────────────
CORES = {
    "azul_escuro":  "#1B3A6B",
    "azul":         "#2563EB",
    "azul_claro":   "#60A5FA",
    "teal":         "#0D9488",
    "verde":        "#16A34A",
    "verde_claro":  "#86EFAC",
    "laranja":      "#EA580C",
    "vermelho":     "#DC2626",
    "amarelo":      "#CA8A04",
    "cinza_escuro": "#374151",
    "cinza":        "#6B7280",
    "cinza_claro":  "#F3F4F6",
    "branco":       "#FFFFFF",
}
BG = "#F8FAFC"
GRID_COLOR = "#E5E7EB"

def _estilo():
    """Aplica estilo base a todos os gráficos."""
    plt.rcParams.update({
        "figure.facecolor":     BG,
        "axes.facecolor":       BG,
        "axes.edgecolor":       GRID_COLOR,
        "axes.grid":            True,
        "grid.color":           GRID_COLOR,
        "grid.linewidth":       0.7,
        "grid.alpha":           0.8,
        "font.family":          "DejaVu Sans",
        "font.size":            10,
        "axes.titlesize":       13,
        "axes.titleweight":     "bold",
        "axes.titlecolor":      CORES["azul_escuro"],
        "axes.labelcolor":      CORES["cinza_escuro"],
        "xtick.color":          CORES["cinza"],
        "ytick.color":          CORES["cinza"],
        "text.color":           CORES["cinza_escuro"],
        "figure.dpi":           150,
    })

_estilo()

# ── Dados ─────────────────────────────────────────────────────────────────────
ref = json.loads(REF.read_text(encoding="utf-8"))

ATIVIDADES = [
    {"id": "eap-1_0",  "nome": "Desmatamento",          "inicio": 1,  "fim": 25, "recurso": "DESMAT",  "frentes": 5},
    {"id": "eap-1_1",  "nome": "Esc 1aCat ≤2km",        "inicio": 1,  "fim": 10, "recurso": "ESC-1CAT","frentes": 1},
    {"id": "eap-1_2",  "nome": "Esc 1aCat 2-3km",       "inicio": 1,  "fim": 32, "recurso": "ESC-1CAT","frentes": 1},
    {"id": "eap-1_3",  "nome": "Esc 2aCat ≤2km",        "inicio": 1,  "fim": 7,  "recurso": "ESC-2CAT","frentes": 2},
    {"id": "eap-1_4",  "nome": "Esc 2aCat 2-3km",       "inicio": 1,  "fim": 43, "recurso": "ESC-2CAT","frentes": 2},
    {"id": "eap-1_5",  "nome": "Esc 3aCat ≤2km",        "inicio": 1,  "fim": 11, "recurso": "ESC-3CAT","frentes": 4},
    {"id": "eap-1_6",  "nome": "Esc 3aCat 2-3km",       "inicio": 1,  "fim": 25, "recurso": "ESC-3CAT","frentes": 4},
    {"id": "eap-1_7",  "nome": "Compactação PN",         "inicio": 1,  "fim": 46, "recurso": "ATERRO",  "frentes": 3},
    {"id": "eap-1_8",  "nome": "Compactação PI",         "inicio": 7,  "fim": 9,  "recurso": "ATERRO",  "frentes": 2},
    {"id": "eap-1_9",  "nome": "Corpo aterro 3aCat",    "inicio": 1,  "fim": 48, "recurso": "ESC-3CAT","frentes": 2},
    {"id": "eap-1_10", "nome": "Compactação rocha",     "inicio": 1,  "fim": 6,  "recurso": "ATERRO",  "frentes": 1},
]

CORES_RECURSO = {
    "DESMAT":   "#8B5CF6",
    "ESC-1CAT": "#2563EB",
    "ESC-2CAT": "#0D9488",
    "ESC-3CAT": "#EA580C",
    "ATERRO":   "#16A34A",
}

EAP_DADOS = [
    {"id": "eap-1_0",  "nome": "Desmatamento",         "crit": "B", "custo": 2529041,  "venda": 2529041,  "pe_op": 14192824},
    {"id": "eap-1_1",  "nome": "Esc 1aCat ≤2km",       "crit": "C", "custo": 935298,   "venda": 935298,   "pe_op": 1056039},
    {"id": "eap-1_2",  "nome": "Esc 1aCat 2-3km",      "crit": "C", "custo": 3242006,  "venda": 3242006,  "pe_op": 1056039},
    {"id": "eap-1_3",  "nome": "Esc 2aCat ≤2km",       "crit": "C", "custo": 1207022,  "venda": 1207022,  "pe_op": 4165159},
    {"id": "eap-1_4",  "nome": "Esc 2aCat 2-3km",      "crit": "C", "custo": 7077172,  "venda": 7077172,  "pe_op": 4165159},
    {"id": "eap-1_5",  "nome": "Esc 3aCat ≤2km",       "crit": "A", "custo": 5107453,  "venda": 5107453,  "pe_op": 16188650},
    {"id": "eap-1_6",  "nome": "Esc 3aCat 2-3km",      "crit": "A", "custo": 13912325, "venda": 13912325, "pe_op": 16188650},
    {"id": "eap-1_7",  "nome": "Compactação PN",        "crit": "B", "custo": 11620268, "venda": 11620268, "pe_op": 12611777},
    {"id": "eap-1_8",  "nome": "Compactação PI",        "crit": "C", "custo": 393487,   "venda": 393487,   "pe_op": 503052},
    {"id": "eap-1_9",  "nome": "Corpo aterro 3aCat",   "crit": "B", "custo": 6435974,  "venda": 6435974,  "pe_op": 4290608},
    {"id": "eap-1_10", "nome": "Compactação rocha",    "crit": "C", "custo": 425538,   "venda": 425538,   "pe_op": 122435},
]

CORES_CRIT = {"A": CORES["vermelho"], "B": CORES["laranja"], "C": CORES["cinza"]}

# ── GRÁFICO 1: GANTT ──────────────────────────────────────────────────────────
print("  [1/6] Gantt cronograma...")
fig, (ax_gantt, ax_res) = plt.subplots(
    2, 1, figsize=(16, 10), gridspec_kw={"height_ratios": [3, 1]}, facecolor=BG
)
fig.suptitle("AGIS — Cronograma de Execução (RCPSP MINSLK · 52 semanas)",
             fontsize=14, fontweight="bold", color=CORES["azul_escuro"], y=0.98)

ax_gantt.set_facecolor(BG)
ax_res.set_facecolor(BG)

# Barras do Gantt
for i, atv in enumerate(ATIVIDADES):
    dur   = atv["fim"] - atv["inicio"]
    cor   = CORES_RECURSO[atv["recurso"]]
    y_pos = len(ATIVIDADES) - 1 - i

    # Sombra
    shadow = FancyBboxPatch(
        (atv["inicio"] + 0.15, y_pos - 0.32), dur, 0.64,
        boxstyle="round,pad=0.02", linewidth=0, color="#00000015"
    )
    ax_gantt.add_patch(shadow)

    # Barra principal
    bar = FancyBboxPatch(
        (atv["inicio"], y_pos - 0.30), dur, 0.60,
        boxstyle="round,pad=0.02",
        linewidth=0.8, edgecolor=cor, facecolor=cor + "CC"
    )
    ax_gantt.add_patch(bar)

    # Label de duração
    if dur > 4:
        ax_gantt.text(atv["inicio"] + dur / 2, y_pos,
                      f"{dur}s", ha="center", va="center",
                      fontsize=8.5, fontweight="bold", color="white")

    # Frentes
    ax_gantt.text(atv["fim"] + 0.4, y_pos, f"×{atv['frentes']}",
                  va="center", fontsize=7.5, color=CORES["cinza"])

ax_gantt.set_yticks(range(len(ATIVIDADES)))
ax_gantt.set_yticklabels(
    [a["nome"] for a in reversed(ATIVIDADES)], fontsize=9
)
ax_gantt.set_xlim(0, 56)
ax_gantt.set_ylim(-0.6, len(ATIVIDADES) - 0.4)
ax_gantt.set_xlabel("Semana ISO", fontsize=9)
ax_gantt.axvline(52, color=CORES["vermelho"], linewidth=1.5, linestyle="--", alpha=0.7)
ax_gantt.text(52.3, len(ATIVIDADES) - 0.3, "Makespan\n52sem", fontsize=7.5,
              color=CORES["vermelho"], va="top")
ax_gantt.axvline(56, color=CORES["amarelo"], linewidth=1, linestyle=":", alpha=0.7)
ax_gantt.text(56.3, len(ATIVIDADES) - 0.3, "Deadline\n56sem", fontsize=7.5,
              color=CORES["amarelo"], va="top")

# Legenda de recursos
handles = [mpatches.Patch(color=c, label=r) for r, c in CORES_RECURSO.items()]
ax_gantt.legend(handles=handles, loc="lower right", fontsize=8,
                framealpha=0.9, ncol=5, title="Recurso", title_fontsize=8)

# Histograma de uso de recursos por semana
rec_por_semana = {r: [0] * 52 for r in CORES_RECURSO}
for atv in ATIVIDADES:
    for s in range(atv["inicio"] - 1, min(atv["fim"], 52)):
        rec_por_semana[atv["recurso"]][s] += atv["frentes"]

semanas = list(range(1, 53))
bottom = np.zeros(52)
for recurso, vals in rec_por_semana.items():
    ax_res.bar(semanas, vals, bottom=bottom, color=CORES_RECURSO[recurso] + "BB",
               label=recurso, width=0.85)
    bottom += np.array(vals, dtype=float)

ax_res.set_xlim(0, 56)
ax_res.set_xlabel("Semana", fontsize=9)
ax_res.set_ylabel("Frentes\nativos", fontsize=8)
ax_res.set_title("Utilização de Recursos por Semana", fontsize=9, pad=4)

plt.tight_layout(rect=[0, 0, 1, 0.97])
fig.savefig(OUT / "01_gantt_cronograma.png", dpi=180, bbox_inches="tight",
            facecolor=BG, edgecolor="none")
plt.close(fig)
print("     → 01_gantt_cronograma.png")

# ── GRÁFICO 2: PLAN SPACE ────────────────────────────────────────────────────
print("  [2/6] Plan space sensitivity...")

CENARIOS = []
for slug in ["M0_BASE_MANUAL","A0_BASE_AUTO","A1_ESC3_8","A2_ESC3_12","A3_ESC3_14",
             "A4_ATERRO_6","A5_ESC2_6","A6_ESC1_4","A7_DEADLINE_52","A8_DEADLINE_60",
             "A9_ESC3_10_ATERRO_6","A11_FULL_RELAX"]:
    p = INTER / f"{slug}.benchmark_report.json"
    if not p.exists():
        continue
    r = json.loads(p.read_text(encoding="utf-8"))
    rcpsp   = r.get("rcpsp_schedule") or {}
    confronto = r.get("confronto") or {}
    deltas  = confronto.get("deltas") or {}
    CENARIOS.append({
        "slug":        slug,
        "makespan":    rcpsp.get("makespan_weeks") or 52,
        "folga":       rcpsp.get("folga_semanas") or 4,
        "feasible":    rcpsp.get("is_feasible", True),
        "delta_venda": (deltas.get("preco_venda") or {}).get("percentual") or 0,
        "delta_cd":    (deltas.get("custo_direto") or {}).get("percentual") or 0,
    })

LABELS_CURTOS = {
    "M0_BASE_MANUAL":           "M0 Manual",
    "A0_BASE_AUTO":             "A0 Auto",
    "A1_ESC3_8":                "A1 ESC3=8",
    "A2_ESC3_12":               "A2 ESC3=12",
    "A3_ESC3_14":               "A3 ESC3=14",
    "A4_ATERRO_6":              "A4 ATR=6",
    "A5_ESC2_6":                "A5 ESC2=6",
    "A6_ESC1_4":                "A6 ESC1=4",
    "A7_DEADLINE_52":           "A7 D=52s",
    "A8_DEADLINE_60":           "A8 D=60s",
    "A9_ESC3_10_ATERRO_6":      "A9 Dual",
    "A11_FULL_RELAX":           "A11 Full",
}

fig, ax = plt.subplots(figsize=(14, 7), facecolor=BG)
fig.suptitle("AGIS — Espaço de Plano: Makespan × Δ Preço de Venda (12 cenários)",
             fontsize=14, fontweight="bold", color=CORES["azul_escuro"])

for i, c in enumerate(CENARIOS):
    label = LABELS_CURTOS.get(c["slug"], c["slug"])
    is_m0 = c["slug"] == "M0_BASE_MANUAL"
    is_feasible = c["feasible"]
    cor   = CORES["azul_escuro"] if is_m0 else (CORES["verde"] if is_feasible else CORES["vermelho"])
    size  = 180 if is_m0 else 120

    ax.scatter(c["makespan"], c["delta_venda"],
               s=size, color=cor, zorder=5,
               alpha=0.9, edgecolors="white", linewidths=1.5)
    offset_y = 0.08 if i % 2 == 0 else -0.15
    ax.annotate(label,
                xy=(c["makespan"], c["delta_venda"]),
                xytext=(3, 8 if offset_y > 0 else -16),
                textcoords="offset points",
                fontsize=8, color=CORES["cinza_escuro"],
                fontweight="bold" if is_m0 else "normal")

ax.axhline(0, color=CORES["cinza"], linewidth=0.8, linestyle="--", alpha=0.6)
ax.axvline(52, color=CORES["vermelho"], linewidth=1, linestyle=":", alpha=0.5)
ax.axvline(56, color=CORES["amarelo"], linewidth=1, linestyle=":", alpha=0.5)
ax.text(52.3, ax.get_ylim()[0] if CENARIOS else -1, " Makespan\n atual", fontsize=7.5, color=CORES["vermelho"])
ax.text(56.3, ax.get_ylim()[0] if CENARIOS else -1, " Deadline\n limite", fontsize=7.5, color=CORES["amarelo"])

ax.set_xlabel("Makespan (semanas)", fontsize=11)
ax.set_ylabel("Δ Preço de Venda vs Referência (%)", fontsize=11)

handles_l = [
    mpatches.Patch(color=CORES["azul_escuro"], label="M0 — Baseline manual"),
    mpatches.Patch(color=CORES["verde"],       label="AUTO — viável"),
    mpatches.Patch(color=CORES["vermelho"],    label="AUTO — inviável"),
]
ax.legend(handles=handles_l, fontsize=9, loc="upper right")
ax.grid(True, alpha=0.4)

plt.tight_layout()
fig.savefig(OUT / "02_plan_space.png", dpi=180, bbox_inches="tight",
            facecolor=BG, edgecolor="none")
plt.close(fig)
print("     → 02_plan_space.png")

# ── GRÁFICO 3: WATERFALL FINANCEIRO ─────────────────────────────────────────
print("  [3/6] Waterfall financeiro...")

WATERFALL_ITEMS = [
    ("MO direto",   16934378,  CORES["azul"]),
    ("Diesel",      29837052,  CORES["teal"]),
    ("Custo Direto",0,         CORES["azul_escuro"]),   # subtotal
    ("ADM",         13695825,  CORES["cinza_escuro"]),
    ("TOP",         858758,    CORES["cinza"]),
    ("LAB",         139568,    CORES["cinza"]),
    ("QSMS",        755778,    CORES["cinza"]),
    ("MOB",         4054600,   CORES["cinza"]),
    ("Custo Total", 0,         CORES["laranja"]),       # subtotal
    ("Margem (BDI)",10478021,  CORES["verde"]),
    ("Preço Venda", 0,         CORES["verde_claro"]),   # total
]

# Calcula posições cumulativas
cumsum   = 0
bases    = []
heights  = []
labels   = []
cores_b  = []
subtotais = {"Custo Direto": 46771430, "Custo Total": 66275960, "Preço Venda": 76753981}

for nome, val, cor in WATERFALL_ITEMS:
    if nome in subtotais:
        h = subtotais[nome]
        bases.append(0)
        heights.append(h)
        cores_b.append(cor)
        cumsum = h
    else:
        bases.append(cumsum)
        heights.append(val)
        cores_b.append(cor)
        cumsum += val
    labels.append(nome)

fig, ax = plt.subplots(figsize=(15, 7), facecolor=BG)
fig.suptitle("AGIS — Cascata Financeira: Composição de Custo e Preço de Venda",
             fontsize=14, fontweight="bold", color=CORES["azul_escuro"])

x = np.arange(len(labels))
for i, (b, h, cor, nome) in enumerate(zip(bases, heights, cores_b, labels)):
    is_subtotal = nome in subtotais
    alpha  = 1.0 if is_subtotal else 0.85
    lw     = 1.5 if is_subtotal else 0.5
    ec     = CORES["cinza_escuro"] if is_subtotal else cor

    ax.bar(i, h, bottom=b, color=cor, alpha=alpha,
           edgecolor=ec, linewidth=lw, width=0.7)

    val_text = f"R$ {h/1e6:.1f}M"
    top_y = b + h
    ax.text(i, top_y + 0.3e6, val_text,
            ha="center", va="bottom", fontsize=7.5, fontweight="bold" if is_subtotal else "normal",
            color=CORES["cinza_escuro"])

    # Linha de conexão ao próximo
    if i < len(labels) - 1 and labels[i + 1] not in subtotais:
        ax.plot([i + 0.35, i + 0.65], [top_y, top_y],
                color=CORES["cinza"], linewidth=0.8, linestyle="--", alpha=0.5)

ax.set_xticks(x)
ax.set_xticklabels(labels, rotation=20, ha="right", fontsize=9)
ax.yaxis.set_major_formatter(mticker.FuncFormatter(lambda x, _: f"R${x/1e6:.0f}M"))
ax.set_ylabel("Valor (R$ Milhões)", fontsize=10)
ax.set_ylim(0, 85e6)

# Anotações
ax.annotate("Margem: 13,65%\nStatus: VERDE",
            xy=(9, 66275960 + 10478021 / 2), fontsize=9,
            color=CORES["verde"], fontweight="bold",
            ha="center", va="center")

plt.tight_layout()
fig.savefig(OUT / "03_waterfall_financeiro.png", dpi=180, bbox_inches="tight",
            facecolor=BG, edgecolor="none")
plt.close(fig)
print("     → 03_waterfall_financeiro.png")

# ── GRÁFICO 4: EAP CRITICIDADE ───────────────────────────────────────────────
print("  [4/6] EAP por criticidade...")

fig, ax = plt.subplots(figsize=(13, 8), facecolor=BG)
fig.suptitle("AGIS — Custo por Item EAP com Criticidade e Ponto de Equilíbrio",
             fontsize=14, fontweight="bold", color=CORES["azul_escuro"])

nomes   = [d["nome"] for d in EAP_DADOS]
custos  = [d["custo"] / 1e6 for d in EAP_DADOS]
pe_ops  = [d["pe_op"] / 1e6 for d in EAP_DADOS]
crits   = [d["crit"] for d in EAP_DADOS]
cores_c = [CORES_CRIT[c] for c in crits]
y_pos   = np.arange(len(nomes))

# Barra de custo
bars = ax.barh(y_pos, custos, color=cores_c, alpha=0.85,
               edgecolor="white", linewidth=0.5, height=0.55, label="Custo/Venda")

# Marcador PE operacional
for i, pe in enumerate(pe_ops):
    ax.plot(pe, y_pos[i], marker="|", markersize=14,
            color=CORES["cinza_escuro"], linewidth=2.5, zorder=5)
    if pe > custos[i]:
        ax.annotate("", xy=(pe, y_pos[i]), xytext=(custos[i], y_pos[i]),
                    arrowprops=dict(arrowstyle="->", color=CORES["vermelho"] + "80", lw=1))

# Valores nas barras
for i, (bar, c_m, crit) in enumerate(zip(bars, custos, crits)):
    ax.text(c_m + 0.1, y_pos[i], f"R${c_m:.1f}M  [{crit}]",
            va="center", fontsize=8.5, color=CORES["cinza_escuro"],
            fontweight="bold" if crit == "A" else "normal")

ax.set_yticks(y_pos)
ax.set_yticklabels(nomes, fontsize=9)
ax.set_xlabel("Valor (R$ Milhões)", fontsize=10)
ax.xaxis.set_major_formatter(mticker.FuncFormatter(lambda x, _: f"R${x:.0f}M"))

handles_l = [
    mpatches.Patch(color=CORES["vermelho"],  label="Criticidade A (alta)"),
    mpatches.Patch(color=CORES["laranja"],   label="Criticidade B (média)"),
    mpatches.Patch(color=CORES["cinza"],     label="Criticidade C (baixa)"),
    plt.Line2D([0], [0], marker="|", color=CORES["cinza_escuro"],
               markersize=12, linewidth=2.5, label="Ponto de Equilíbrio Operacional"),
]
ax.legend(handles=handles_l, fontsize=9, loc="lower right")
ax.invert_yaxis()

plt.tight_layout()
fig.savefig(OUT / "04_eap_criticidade.png", dpi=180, bbox_inches="tight",
            facecolor=BG, edgecolor="none")
plt.close(fig)
print("     → 04_eap_criticidade.png")

# ── GRÁFICO 5: INDIRETOS COMPOSIÇÃO (DONUT) ──────────────────────────────────
print("  [5/6] Indiretos composição...")

INDIR_DADOS = {
    "ADM":  13695825,
    "TOP":  858758,
    "LAB":  139568,
    "QSMS": 755778,
    "MOB":  4054600,
}
CORES_INDIR = {
    "ADM":  CORES["azul_escuro"],
    "TOP":  CORES["teal"],
    "LAB":  CORES["verde"],
    "QSMS": CORES["laranja"],
    "MOB":  CORES["cinza"],
}

fig, (ax_pie, ax_bar) = plt.subplots(1, 2, figsize=(14, 7), facecolor=BG)
fig.suptitle("AGIS — Composição dos Custos Indiretos (R$ 19,5M total)",
             fontsize=14, fontweight="bold", color=CORES["azul_escuro"])

# Donut
vals   = list(INDIR_DADOS.values())
labels_d = list(INDIR_DADOS.keys())
cors_d = [CORES_INDIR[k] for k in labels_d]
total  = sum(vals)

wedges, texts, autotexts = ax_pie.pie(
    vals, labels=labels_d, autopct=lambda p: f"{p:.1f}%",
    colors=cors_d, startangle=90,
    wedgeprops=dict(width=0.55, edgecolor="white", linewidth=2),
    textprops=dict(fontsize=10),
)
for at in autotexts:
    at.set_fontweight("bold")
    at.set_fontsize(9)

ax_pie.text(0, 0, f"R${total/1e6:.1f}M\nTotal Indir.", ha="center", va="center",
            fontsize=10, fontweight="bold", color=CORES["azul_escuro"])
ax_pie.set_title("Distribuição (%)", fontsize=11, pad=12)

# Barras horizontais
cats   = list(INDIR_DADOS.keys())
valores = [v / 1e6 for v in vals]
y_p    = np.arange(len(cats))
bars_i = ax_bar.barh(y_p, valores, color=cors_d, alpha=0.88,
                     edgecolor="white", linewidth=0.5, height=0.55)
for i, (bar, v) in enumerate(zip(bars_i, valores)):
    ax_bar.text(v + 0.1, y_p[i], f"R${v:.2f}M",
                va="center", fontsize=9.5, fontweight="bold", color=CORES["cinza_escuro"])

ax_bar.set_yticks(y_p)
ax_bar.set_yticklabels(cats, fontsize=11)
ax_bar.set_xlabel("R$ Milhões", fontsize=10)
ax_bar.xaxis.set_major_formatter(mticker.FuncFormatter(lambda x, _: f"R${x:.0f}M"))
ax_bar.set_title("Valor Absoluto", fontsize=11, pad=12)
ax_bar.invert_yaxis()

plt.tight_layout()
fig.savefig(OUT / "05_indiretos_composicao.png", dpi=180, bbox_inches="tight",
            facecolor=BG, edgecolor="none")
plt.close(fig)
print("     → 05_indiretos_composicao.png")

# ── GRÁFICO 6: TIMES INDIRETOS ───────────────────────────────────────────────
print("  [6/6] Times indiretos...")

TIMES = [
    {"nome": "ADM",  "pessoas": 45, "custo_mo": 448861, "custo_eq": 268331, "verbas": 324300, "perm": 12.57},
    {"nome": "TOP",  "pessoas": 5,  "custo_mo": 64670,  "custo_eq": 15147,  "verbas": 3000,   "perm": 12.57},
    {"nome": "LAB",  "pessoas": 2,  "custo_mo": 15310,  "custo_eq": 0,      "verbas": 1847,   "perm": 12.57},
    {"nome": "QSMS", "pessoas": 3,  "custo_mo": 34050,  "custo_eq": 15147,  "verbas": 8220,   "perm": 12.57},
]
TIMES_SAZ = [
    {"nome": "BIOLOGO", "pessoas": 1, "custo_mo": 7500, "custo_eq": 0, "verbas": 0, "perm": 5.83, "sazonal": True},
    {"nome": "BOTANICO","pessoas": 1, "custo_mo": 7500, "custo_eq": 0, "verbas": 0, "perm": 5.83, "sazonal": True},
]

fig, axes = plt.subplots(1, 2, figsize=(14, 7), facecolor=BG)
fig.suptitle("AGIS — Composição dos Times Indiretos\n(MO + Equipamentos + Verbas mensais)",
             fontsize=13, fontweight="bold", color=CORES["azul_escuro"])

# Painel esquerdo: stacked bar por categoria de custo
cats_t = [t["nome"] for t in TIMES]
mo_v   = [t["custo_mo"] / 1e3 for t in TIMES]
eq_v   = [t["custo_eq"] / 1e3 for t in TIMES]
vb_v   = [t["verbas"] / 1e3 for t in TIMES]
x_t    = np.arange(len(cats_t))

ax_cost = axes[0]
b1 = ax_cost.bar(x_t, mo_v, color=CORES["azul"],     label="MO", width=0.5)
b2 = ax_cost.bar(x_t, eq_v, bottom=mo_v, color=CORES["teal"], label="Equipamentos", width=0.5)
b3 = ax_cost.bar(x_t, vb_v, bottom=[m+e for m,e in zip(mo_v,eq_v)],
                 color=CORES["cinza"], label="Verbas mensais", width=0.5)

totais = [m+e+v for m,e,v in zip(mo_v,eq_v,vb_v)]
for i, tot in enumerate(totais):
    ax_cost.text(i, tot + 5, f"R${tot:.0f}k", ha="center", fontsize=9,
                 fontweight="bold", color=CORES["cinza_escuro"])

ax_cost.set_xticks(x_t)
ax_cost.set_xticklabels(cats_t, fontsize=11)
ax_cost.set_ylabel("R$ mil/mês", fontsize=10)
ax_cost.yaxis.set_major_formatter(mticker.FuncFormatter(lambda x, _: f"R${x:.0f}k"))
ax_cost.legend(fontsize=9, loc="upper right")
ax_cost.set_title("Custo Mensal por Componente", fontsize=11)

# Painel direito: número de pessoas com sazonais destacados
ax_pess = axes[1]
todos   = TIMES + TIMES_SAZ
cat_p   = [t["nome"] for t in todos]
pess_p  = [t["pessoas"] for t in todos]
cor_p   = [CORES["azul_escuro"] if not t.get("sazonal") else CORES["azul_claro"] for t in todos]
hatch_p = ["" if not t.get("sazonal") else "///" for t in todos]
y_p2    = np.arange(len(cat_p))

for i, (y, p, cor, hatch) in enumerate(zip(y_p2, pess_p, cor_p, hatch_p)):
    bar = ax_pess.barh(y, p, color=cor, hatch=hatch,
                       edgecolor="white" if not hatch else CORES["azul"],
                       linewidth=0.5, height=0.55, alpha=0.88)
    saz_label = " (sazonal)" if todos[i].get("sazonal") else ""
    ax_pess.text(p + 0.2, y, f"{p} pessoa{'s' if p > 1 else ''}{saz_label}",
                 va="center", fontsize=9, color=CORES["cinza_escuro"])

ax_pess.set_yticks(y_p2)
ax_pess.set_yticklabels(cat_p, fontsize=11)
ax_pess.set_xlabel("Número de pessoas", fontsize=10)
ax_pess.set_title("Headcount por Time\n(sazonal = apenas fase supressão)", fontsize=11)
ax_pess.invert_yaxis()

handles_p = [
    mpatches.Patch(color=CORES["azul_escuro"], label="Presença integral (12,57 meses)"),
    mpatches.Patch(color=CORES["azul_claro"], hatch="///", label="Sazonal (eap-1_0, ~5,83 meses)"),
]
ax_pess.legend(handles=handles_p, fontsize=9, loc="lower right")

plt.tight_layout()
fig.savefig(OUT / "06_times_indiretos.png", dpi=180, bbox_inches="tight",
            facecolor=BG, edgecolor="none")
plt.close(fig)
print("     → 06_times_indiretos.png")

print("\n✓ Todos os 6 gráficos gerados em:", OUT)
for f in sorted(OUT.glob("*.png")):
    size_kb = f.stat().st_size / 1024
    print(f"  {f.name:<40}  {size_kb:6.1f} KB")
