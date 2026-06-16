#!/usr/bin/env python3
"""Calibra o catálogo rfi-r02 para os 11 CPUs usados pelo benchmark AGIS.

Abordagem híbrida (melhor dos dois catálogos):
  • Composição de equipe + produtividade  → mendeslobo  (calibrado no campo AGIS)
  • Preços unitários de insumos (R$/h)   → RFI-R02      (mercado mai/2026)

Mapeamento AGIS-* → RFI E/P codes:
  Funções (AGIS-FN-*):
    OPER-ESCAV      → P0040 (Operador de Escavadeira)
    OPER-TRAT-EST   → P0048 (Operador de Trator de Esteiras)
    OPER-TRAT-PNEU  → P0049 (Operador de Trator de Pneu)
    OPER-ROLO       → P0046 (Operador de Rolo Compactador)
    OPER-MOTON      → P0043 (Operador de Motoniveladora)
    OPER-MOTOSSERRA → P0062 (Operador de Motosserra)
    MOTOR-BASC      → P0032 (Motorista Caminhão Basculante)
    MOTOR-PIPA      → P0033 (Motorista Caminhão Pipa)
    AJUD            → P0001 (Ajudante)
    ENCAR           → P0022 (Encarregado de Terraplenagem)
    GREDISTA        → P0029 (Gredista)
    APONTADOR       → P0072 (Apontador)
    SINALEIRO       → P0079 (Sinaleiro)

  Equipamentos (AGIS-*):
    ESCAV-22T / E0015  → E0016 (Escavadeira Hidráulica 22t, R$202.50/h)
    E0016 (escav 38t)  → E0018 (Escavadeira Hidráulica 38t, R$292.77/h)
    E0002 (cam 14m³)   → E0007 (Caminhão Basculante 14m³, R$142.80/h)
    E0004 (cam 16m³)   → E0008 (Caminhão Basculante 16m³, R$227.75/h)
    TRAT-EST-20T       → E0024 (Trator Esteiras 20t, R$281.12/h)
    TRAT-EST-40T       → E0025 (Trator Esteiras 30t/440HP, R$413.50/h — mais próximo 40t)
    ROLO-PC-10T        → E0035 (Rolo Pé-de-Carneiro 10t, R$123.20/h)
    ROLO-LISO          → E0036 (Rolo Liso 10t, R$100.80/h)
    TRATOR-PNEU-GRADE  → E0039 (Trator Agrícola 75HP c/ Grade, R$115.36/h)
    MOTON-140K         → E0029 (Motoniveladora 140HP, R$246.18/h)
    CAM-PIPA-18K       → E0010 (Caminhão Pipa 10.000L, R$110.00/h)
    MOTOSSERRA         → E0031 (Motosserra, R$36.00/h)

Decisão sobre ATI-003:
  Usa composição + produtividade mendeslobo (738 m²/h).
  Justificativa: AGIS é ferrovia no Nordeste (caatinga/cerrado), não mata fechada.
  A especificação RFI "DAP≥30cm e arbustos" é mais restritiva que o serviço real.
"""

from __future__ import annotations
import json
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
RFI_DIR = REPO / "config/catalogos/rfi-r02"
DATA_REF = "2026-05-08"

# ── Tabelas de mapeamento ──────────────────────────────────────────────────────

FN_MAP: dict[str, str] = {
    "AGIS-FN-OPER-ESCAV":      "P0040",
    "AGIS-FN-OPER-TRAT-EST":   "P0048",
    "AGIS-FN-OPER-TRAT-PNEU":  "P0049",
    "AGIS-FN-OPER-ROLO":       "P0046",
    "AGIS-FN-OPER-MOTON":      "P0043",
    "AGIS-FN-OPER-MOTOSSERRA":  "P0062",
    "AGIS-FN-MOTOR-BASC":      "P0032",
    "AGIS-FN-MOTOR-PIPA":      "P0033",
    "AGIS-FN-AJUD":            "P0001",
    "AGIS-FN-ENCAR":           "P0022",
    "AGIS-FN-GREDISTA":        "P0029",
    "AGIS-FN-APONTADOR":       "P0072",
    "AGIS-FN-SINALEIRO":       "P0079",
}

EQ_MAP: dict[str, str] = {
    "AGIS-ESCAV-22T":        "E0016",  # Escavadeira 22t → 22t RFI
    "AGIS-E0015":            "E0016",  # idem
    "AGIS-E0016":            "E0018",  # Escavadeira 38t (3ªcat)
    "AGIS-E0002":            "E0007",  # Cam Basculante 14m³
    "AGIS-E0004":            "E0008",  # Cam Basculante 16m³ (3ªcat)
    "AGIS-TRAT-EST-20T":     "E0024",  # Trator Esteiras 20t
    "AGIS-TRAT-EST-40T":     "E0025",  # Trator Esteiras 40t → 30t/440HP (mais próximo)
    "AGIS-ROLO-PC-10T":      "E0035",  # Rolo Pé-de-Carneiro 10t
    "AGIS-ROLO-LISO":        "E0036",  # Rolo Liso 10t
    "AGIS-TRATOR-PNEU-GRADE":"E0039",  # Trator Pneu c/ Grade
    "AGIS-MOTON-140K":       "E0029",  # Motoniveladora 140HP
    "AGIS-CAM-PIPA-18K":     "E0010",  # Caminhão Pipa (10k → mais próximo 18k)
    "AGIS-MOTOSSERRA":       "E0031",  # Motosserra
}

def map_fn(agis_id: str) -> str:
    if agis_id in FN_MAP:
        return FN_MAP[agis_id]
    # Se já é P-code, retorna direto
    if agis_id.startswith("P0"):
        return agis_id
    raise ValueError(f"Funcao não mapeada: {agis_id!r}")

def map_eq(agis_id: str) -> str:
    if agis_id in EQ_MAP:
        return EQ_MAP[agis_id]
    if agis_id.startswith("E0"):
        return agis_id
    raise ValueError(f"Equipamento não mapeado: {agis_id!r}")

# ── Composições calibradas (mendeslobo → RFI codes) ───────────────────────────
# Estrutura: {cpu_id: {valor_horario, unidade, funcoes: [(id,n)], equip: [(id,n)]}}

CALIBRATED: dict[str, dict] = {
    "CPU-TERRA-ATI-003": {
        "valor_horario": 738.0,
        "unidade": "m2",
        "nota_calibracao": (
            "Produtividade/composição da planilha AGIS 2026-05 (mendeslobo). "
            "Correto para área de caatinga/cerrado do Nordeste. "
            "RFI (250 m²/h) é para mata fechada DAP≥30cm — não aplicável ao AGIS."
        ),
        "funcoes": [
            ("AGIS-FN-OPER-TRAT-EST", 1),
            ("AGIS-FN-OPER-ESCAV",    1),
            ("AGIS-FN-OPER-MOTOSSERRA", 1),
            ("AGIS-FN-AJUD",          1),
            ("AGIS-FN-ENCAR",         1),
            ("AGIS-FN-APONTADOR",     1),
            ("AGIS-FN-SINALEIRO",     1),
        ],
        "equip": [
            ("AGIS-TRAT-EST-20T", 1),
            ("AGIS-ESCAV-22T",    1),
            ("AGIS-MOTOSSERRA",   1),
        ],
    },
    "CPU-TERRA-ESCO-CARGA-1CAT-DMT2000": {
        "valor_horario": 231.87,
        "unidade": "m3",
        "nota_calibracao": "Comboio ferrovia AGIS: 1 escav 22t + 7 cam 14m³. Frota campo mai/2026.",
        "funcoes": [
            ("AGIS-FN-OPER-ESCAV",   1),
            ("AGIS-FN-AJUD",         1),
            ("AGIS-FN-ENCAR",        1),
            ("AGIS-FN-MOTOR-BASC",   7),
        ],
        "equip": [
            ("AGIS-E0015", 1),  # Escav 22t
            ("AGIS-E0002", 7),  # Cam 14m³
        ],
    },
    "CPU-TERRA-ESCO-CARGA-1CAT-DMT3000": {
        "valor_horario": 230.91,
        "unidade": "m3",
        "nota_calibracao": "Comboio ferrovia AGIS: 1 escav 22t + 8 cam 14m³ (DMT maior = mais caminhões).",
        "funcoes": [
            ("AGIS-FN-OPER-ESCAV",   1),
            ("AGIS-FN-AJUD",         1),
            ("AGIS-FN-ENCAR",        1),
            ("AGIS-FN-MOTOR-BASC",   8),
        ],
        "equip": [
            ("AGIS-E0015", 1),
            ("AGIS-E0002", 8),
        ],
    },
    "CPU-TERRA-ESCO-CARGA-2CAT-DMT2000": {
        "valor_horario": 158.28,
        "unidade": "m3",
        "nota_calibracao": "2ªcat: mesma escav 22t, mas 6 cam (solo mais duro → menor produção).",
        "funcoes": [
            ("AGIS-FN-OPER-ESCAV",   1),
            ("AGIS-FN-AJUD",         1),
            ("AGIS-FN-ENCAR",        1),
            ("AGIS-FN-MOTOR-BASC",   6),
        ],
        "equip": [
            ("AGIS-E0015", 1),
            ("AGIS-E0002", 6),
        ],
    },
    "CPU-TERRA-ESCO-CARGA-2CAT-DMT3000": {
        "valor_horario": 158.78,
        "unidade": "m3",
        "nota_calibracao": "2ªcat DMT3000: mesma escav 22t, 7 cam (distância maior).",
        "funcoes": [
            ("AGIS-FN-OPER-ESCAV",   1),
            ("AGIS-FN-AJUD",         1),
            ("AGIS-FN-ENCAR",        1),
            ("AGIS-FN-MOTOR-BASC",   7),
        ],
        "equip": [
            ("AGIS-E0015", 1),
            ("AGIS-E0002", 7),
        ],
    },
    "CPU-TERRA-ESCO-CARGA-3CAT-DMT2000": {
        "valor_horario": 142.02,
        "unidade": "m3",
        "nota_calibracao": "3ªcat: escav 38t (rocha) + 6 cam 16m³.",
        "funcoes": [
            ("AGIS-FN-OPER-ESCAV",   1),
            ("AGIS-FN-AJUD",         1),
            ("AGIS-FN-MOTOR-BASC",   6),
        ],
        "equip": [
            ("AGIS-E0016", 1),  # Escav 38t
            ("AGIS-E0004", 6),  # Cam 16m³
        ],
    },
    "CPU-TERRA-ESCO-CARGA-3CAT-DMT3000": {
        "valor_horario": 142.16,
        "unidade": "m3",
        "nota_calibracao": "3ªcat DMT3000: escav 38t + 8 cam 16m³.",
        "funcoes": [
            ("AGIS-FN-OPER-ESCAV",   1),
            ("AGIS-FN-AJUD",         1),
            ("AGIS-FN-MOTOR-BASC",   8),
        ],
        "equip": [
            ("AGIS-E0016", 1),
            ("AGIS-E0004", 8),
        ],
    },
    "CPU-TERRA-COMPAC-PN": {
        "valor_horario": 173.01,
        "unidade": "m3",
        "nota_calibracao": (
            "Frota ferrovia: 2 rolos PC + trator pneu c/ grade + motoniveladora + pipa. "
            "Sem trator de pneu o PN não atinge adensamento ferroviário."
        ),
        "funcoes": [
            ("AGIS-FN-OPER-ROLO",       2),
            ("AGIS-FN-OPER-TRAT-PNEU",  1),
            ("AGIS-FN-OPER-MOTON",      1),
            ("AGIS-FN-MOTOR-PIPA",      1),
            ("AGIS-FN-AJUD",            2),
            ("AGIS-FN-GREDISTA",        1),
            ("AGIS-FN-ENCAR",           1),
        ],
        "equip": [
            ("AGIS-ROLO-PC-10T",       2),
            ("AGIS-TRATOR-PNEU-GRADE", 1),
            ("AGIS-MOTON-140K",        1),
            ("AGIS-CAM-PIPA-18K",      1),
        ],
    },
    "CPU-TERRA-COMPAC-PI": {
        "valor_horario": 132.32,
        "unidade": "m3",
        "nota_calibracao": (
            "PI exige mais passadas que PN → mesma frota, menor produtividade. "
            "Frota calibrada campo AGIS."
        ),
        "funcoes": [
            ("AGIS-FN-OPER-ROLO",       2),
            ("AGIS-FN-OPER-TRAT-PNEU",  1),
            ("AGIS-FN-OPER-MOTON",      1),
            ("AGIS-FN-MOTOR-PIPA",      1),
            ("AGIS-FN-AJUD",            2),
            ("AGIS-FN-GREDISTA",        1),
            ("AGIS-FN-ENCAR",           1),
        ],
        "equip": [
            ("AGIS-ROLO-PC-10T",       2),
            ("AGIS-TRATOR-PNEU-GRADE", 1),
            ("AGIS-MOTON-140K",        1),
            ("AGIS-CAM-PIPA-18K",      1),
        ],
    },
    "CPU-TERRA-COMPAC-FINAL-ROCHA": {
        "valor_horario": 100.0,
        "unidade": "m3",
        "nota_calibracao": "Compactação de camada final de aterro de rocha. Composição calibrada AGIS.",
        "funcoes": [
            ("AGIS-FN-OPER-TRAT-EST", 1),
            ("AGIS-FN-OPER-ROLO",     3),
            ("AGIS-FN-MOTOR-PIPA",    1),
            ("AGIS-FN-AJUD",          2),
        ],
        "equip": [
            ("AGIS-TRAT-EST-20T",  1),
            ("AGIS-ROLO-LISO",     2),
            ("AGIS-CAM-PIPA-18K",  1),
            ("AGIS-ROLO-PC-10T",   1),
        ],
    },
    "CPU-TERRA-CORPO-ATERRO-3CAT": {
        "valor_horario": 214.92,
        "unidade": "m3",
        "nota_calibracao": "Corpo de aterro 3ªcat. Trator esteiras grande + 2 rolos. Calibrado AGIS.",
        "funcoes": [
            ("AGIS-FN-OPER-ROLO",     2),
            ("AGIS-FN-OPER-TRAT-EST", 1),
            ("AGIS-FN-AJUD",          2),
            ("AGIS-FN-GREDISTA",      1),
            ("AGIS-FN-ENCAR",         1),
        ],
        "equip": [
            ("AGIS-ROLO-PC-10T",  2),
            ("AGIS-TRAT-EST-40T", 1),  # → E0025 (30t/440HP)
        ],
    },
}


# ── Helpers ───────────────────────────────────────────────────────────────────

def get_equip_cost(e_code: str) -> float:
    """Retorna preco_unitario do insumo de equipamento RFI."""
    f = RFI_DIR / "insumos/equipamento" / f"{e_code}.json"
    if not f.exists():
        raise FileNotFoundError(f"Equipamento RFI não encontrado: {e_code}")
    return json.load(open(f)).get("preco_unitario", 0.0)


def get_mo_cost_hora(p_code: str) -> float:
    """Retorna custo horário c/ encargos (atributo da planilha)."""
    f = RFI_DIR / "insumos/mao_obra" / f"{p_code}.json"
    if not f.exists():
        raise FileNotFoundError(f"MO RFI não encontrado: {p_code}")
    d = json.load(open(f))
    return d.get("atributos_especificos", {}).get("custo_hora_com_encargos_planilha", 0.0)


def write_json(path: Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"  ✓ {path.relative_to(REPO)}")


# ── Geração ───────────────────────────────────────────────────────────────────

def calibrar_cpu(cpu_id: str, info: dict) -> None:
    prod_id = f"{cpu_id}-PROD-001"

    # Traduzir composição
    funcoes_rfi = []
    custo_mo_h = 0.0
    for agis_fn, n in info["funcoes"]:
        p = map_fn(agis_fn)
        ch = get_mo_cost_hora(p)
        custo_mo_h += ch * n
        funcoes_rfi.append({"funcao_id": p, "num_pessoas": n})

    equip_rfi = []
    custo_eq_h = 0.0
    for agis_eq, n in info["equip"]:
        e = map_eq(agis_eq)
        ce = get_equip_cost(e)
        custo_eq_h += ce * n
        equip_rfi.append({"equip_id": e, "num_unidades": n})

    vh = info["valor_horario"]
    pu = round((custo_mo_h + custo_eq_h) / vh, 4) if vh > 0 else 0.0

    # Produtividade
    producao = {
        "id": prod_id,
        "codigo": cpu_id,
        "descricao": next(
            (json.load(open(f)).get("descricao", cpu_id)
             for f in (RFI_DIR / "produtividades").glob(f"{prod_id}*")), cpu_id
        ),
        "valor_horario": vh,
        "unidade": info["unidade"],
        "origem": {
            "tipo": "calibrado_agis_rfi",
            "data_calibracao": DATA_REF,
            "referencia": (
                "Híbrido: composição/produtividade mendeslobo (campo AGIS 2026-05) "
                "+ preços unitários RFI-R02 (mercado mai/2026)."
            ),
        },
        "composicao_padrao_equipe": {
            "funcoes": funcoes_rfi,
            "equipamentos": equip_rfi,
        },
        "custos_equipe_rfi": {
            "custo_mo_h":    round(custo_mo_h, 2),
            "custo_equip_h": round(custo_eq_h, 2),
            "total_h":       round(custo_mo_h + custo_eq_h, 2),
            "pu_calculado":  pu,
        },
        "_nota_calibracao": info["nota_calibracao"],
        "categoria": "TERRAPLENAGEM",
    }
    write_json(RFI_DIR / "produtividades" / f"{prod_id}.json", producao)

    # CPU
    cpu = {
        "codigo": cpu_id,
        "descricao": producao["descricao"],
        "unidade": info["unidade"],
        "categoria": "TERRAPLENAGEM",
        "origem": "PROPRIA",
        "producao_id_ref": prod_id,
        "composicao_itens": [],
        "_nota": (
            f"Calibrado AGIS-RFI. "
            f"PU = (MO R${custo_mo_h:.2f} + EQ R${custo_eq_h:.2f}) / {vh} {info['unidade']}/h "
            f"= R${pu:.4f}/{info['unidade']}. "
            f"{info['nota_calibracao']}"
        ),
    }
    write_json(RFI_DIR / "cpus" / f"{cpu_id}.json", cpu)

    return custo_mo_h, custo_eq_h, pu


# ── Main ──────────────────────────────────────────────────────────────────────

def main() -> None:
    print("=" * 70)
    print("CALIBRAÇÃO RFI-R02 → AGIS")
    print("Híbrido: composições mendeslobo + preços RFI")
    print("=" * 70)
    print()

    print(f"{'CPU':<42} {'MO/h':>8} {'EQ/h':>8} {'PU':>8}")
    print("-" * 70)

    resultados = []
    for cpu_id, info in CALIBRATED.items():
        print(f"Atualizando {cpu_id}...")
        mo, eq, pu = calibrar_cpu(cpu_id, info)
        resultados.append((cpu_id, info["valor_horario"], mo, eq, pu, info["unidade"]))

    print()
    print("=" * 70)
    print("RESUMO DOS PUs CALIBRADOS")
    print("=" * 70)
    print(f"{'CPU':<42} {'Prod':>7} {'MO/h':>8} {'EQ/h':>8} {'PU':>9}")
    print("-" * 77)
    for cpu_id, vh, mo, eq, pu, un in resultados:
        short = cpu_id.replace("CPU-TERRA-", "")
        print(f"{short:<42} {vh:>7.1f} {mo:>8.2f} {eq:>8.2f} {pu:>9.4f} R$/{un}")

    print()
    print("Próximo passo: concilium benchmark run --slug AGIS-RFI --reset")


if __name__ == "__main__":
    main()
