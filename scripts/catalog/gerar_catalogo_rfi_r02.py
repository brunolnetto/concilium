#!/usr/bin/env python3
"""Gera o catálogo rfi-r02 a partir da planilha PLANILHA PADRÃO RFI - R02.xlsm.

Estrutura gerada:
  config/catalogos/rfi-r02/
    cpus/            → 9 diretos (ATI-003, ATI-011..018) + 2 AGIS-específicos construídos
    insumos/
      mao_obra/      → P-codes (salário mensal sem encargos, unidade=mes)
      equipamento/   → E-codes (custo horário total, unidade=h)
      material/      → M-codes (preço unitário)
    produtividades/  → um por ATI + 2 AGIS-específicos
  config/contextos/mendeslobo-rfi.json
  config/perfis/rfi-r02.json

Premissas:
  - MO: salário mensal BASE (sem encargos). Engine aplica percentual_encargos do perfil.
  - Encargos CLT horista: 61,62% (PARÂMETROS!B28, referenciado pelo BD_MÃO_DE_OBRA).
  - Equipamentos: custo horário TOTAL do BD_EQUIPAMENTOS (inclui manutenção; locação inclui tudo).
  - Para CPUs não existentes na planilha (COMPAC-FINAL-ROCHA, CORPO-ATERRO-3CAT),
    usa produtividades do catálogo mendeslobo e recompõe equipe com códigos RFI.
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

import openpyxl

# ── Caminhos ──────────────────────────────────────────────────────────────────

REPO_ROOT = Path(__file__).resolve().parents[1]
PLANILHA = REPO_ROOT / "docs/product/3-reference_files/catalogos/PLANILHA PADRÃO RFI - R02.xlsm"
CATALOG_DIR = REPO_ROOT / "config/catalogos/rfi-r02"
CONTEXTOS_DIR = REPO_ROOT / "config/contextos"
PERFIS_DIR = REPO_ROOT / "config/perfis"
DATA_REF = "2026-05-08"

# ── Mapeamento CPU AGIS → ATI planilha ────────────────────────────────────────

AGIS_TO_ATI = {
    "CPU-TERRA-ATI-003":               "ATI-003",
    "CPU-TERRA-ESCO-CARGA-1CAT-DMT2000": "ATI-011",
    "CPU-TERRA-ESCO-CARGA-1CAT-DMT3000": "ATI-012",
    "CPU-TERRA-ESCO-CARGA-2CAT-DMT2000": "ATI-013",
    "CPU-TERRA-ESCO-CARGA-2CAT-DMT3000": "ATI-014",
    "CPU-TERRA-ESCO-CARGA-3CAT-DMT2000": "ATI-015",
    "CPU-TERRA-ESCO-CARGA-3CAT-DMT3000": "ATI-016",
    "CPU-TERRA-COMPAC-PN":              "ATI-017",
    "CPU-TERRA-COMPAC-PI":              "ATI-018",
}

ATI_TO_CPU = {v: k for k, v in AGIS_TO_ATI.items()}

# CPUs AGIS-específicos que NÃO existem na planilha: composição manual com RFI codes
AGIS_CUSTOM_CPUS = {
    "CPU-TERRA-COMPAC-FINAL-ROCHA": {
        "descricao": "Compactação de camada final de aterro de rocha",
        "unidade": "m3",
        "categoria": "TERRAPLENAGEM",
        "producao_horaria": 100.0,
        "funcoes": [
            {"funcao_id": "P0048", "num_pessoas": 1},   # Oper. Trator de Esteiras
            {"funcao_id": "P0046", "num_pessoas": 3},   # Oper. Rolo Compactador
            {"funcao_id": "P0033", "num_pessoas": 1},   # Motorista Caminhão Pipa
            {"funcao_id": "P0001", "num_pessoas": 2},   # Ajudante
        ],
        "equipamentos": [
            {"equip_id": "E0024", "num_unidades": 1},   # Trator de Esteiras 20t
            {"equip_id": "E0036", "num_unidades": 2},   # Rolo Compactador Liso 10t
            {"equip_id": "E0010", "num_unidades": 1},   # Caminhão Pipa 10.000L
            {"equip_id": "E0035", "num_unidades": 1},   # Rolo Pé-de-Carneiro 10t
        ],
    },
    "CPU-TERRA-CORPO-ATERRO-3CAT": {
        "descricao": "Construção de corpo de aterro com material de 3ª categoria oriundo de corte",
        "unidade": "m3",
        "categoria": "TERRAPLENAGEM",
        "producao_horaria": 214.92,
        "funcoes": [
            {"funcao_id": "P0046", "num_pessoas": 2},   # Oper. Rolo Compactador
            {"funcao_id": "P0048", "num_pessoas": 1},   # Oper. Trator de Esteiras
            {"funcao_id": "P0001", "num_pessoas": 2},   # Ajudante
            {"funcao_id": "P0029", "num_pessoas": 1},   # Gredista
            {"funcao_id": "P0022", "num_pessoas": 1},   # Encarregado de Terraplenagem
        ],
        "equipamentos": [
            {"equip_id": "E0035", "num_unidades": 2},   # Rolo Pé-de-Carneiro 10t
            {"equip_id": "E0025", "num_unidades": 1},   # Trator de Esteiras 30t (440HP)
        ],
    },
}


# ── Helpers ───────────────────────────────────────────────────────────────────

def parse_composicao(texto: str) -> list[tuple[str, int]]:
    """'P0040×1, P0001×3' → [('P0040', 1), ('P0001', 3)]"""
    if not texto or texto.strip() in ("—", "-", ""):
        return []
    partes = []
    for token in re.split(r"[,;]\s*", texto.strip()):
        token = token.strip()
        if not token:
            continue
        m = re.match(r"([A-Z0-9]+)[×x](\d+)", token)
        if m:
            partes.append((m.group(1), int(m.group(2))))
    return partes


def write_json(path: Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"  ✓ {path.relative_to(REPO_ROOT)}")


# ── Leitura da planilha ───────────────────────────────────────────────────────

def carregar_planilha() -> openpyxl.Workbook:
    print(f"Abrindo planilha: {PLANILHA.name}")
    return openpyxl.load_workbook(str(PLANILHA), read_only=True, keep_vba=True, data_only=True)


def ler_mo(wb: openpyxl.Workbook) -> dict[str, dict]:
    """BD_MÃO_DE_OBRA → {codigo: {funcao, tipo, salario_mensal, horas_mes, salario_base_h}}"""
    ws = wb["BD_MÃO_DE_OBRA"]
    mo = {}
    for row in ws.iter_rows(min_row=4, values_only=True):
        if not row[0] or not str(row[0]).strip():
            continue
        codigo = str(row[0]).strip()
        mo[codigo] = {
            "codigo": codigo,
            "funcao": str(row[1]).strip() if row[1] else "",
            "tipo_contrato": str(row[2]).strip() if row[2] else "CLT",
            "salario_mensal": float(row[3]) if row[3] else 0.0,
            "horas_mes": float(row[4]) if row[4] else 220.0,
            "salario_base_h": float(row[5]) if row[5] else 0.0,
            "custo_h_com_encargos": float(row[7]) if row[7] else 0.0,
        }
    print(f"  BD_MÃO_DE_OBRA: {len(mo)} registros")
    return mo


def ler_equipamentos(wb: openpyxl.Workbook) -> dict[str, dict]:
    """BD_EQUIPAMENTOS → {codigo: {descricao, tipo, custo_produtivo_h, custo_total_h}}"""
    ws = wb["BD_EQUIPAMENTOS"]
    equip = {}
    for row in ws.iter_rows(min_row=4, values_only=True):
        if not row[0] or not str(row[0]).strip():
            continue
        codigo = str(row[0]).strip()
        equip[codigo] = {
            "codigo": codigo,
            "descricao": str(row[1]).strip() if row[1] else "",
            "tipo": str(row[2]).strip() if row[2] else "locação",   # próprio | locação
            "custo_produtivo_h": float(row[3]) if row[3] else 0.0,
            "pct_manutencao": float(row[4]) if row[4] else 0.0,
            "custo_manutencao_h": float(row[5]) if row[5] else 0.0,
            "custo_total_h": float(row[6]) if row[6] else 0.0,
            "custo_mensal": float(row[9]) if row[9] else 0.0,
        }
    print(f"  BD_EQUIPAMENTOS: {len(equip)} registros")
    return equip


def ler_materiais(wb: openpyxl.Workbook) -> dict[str, dict]:
    """BD_MATERIAIS → {codigo: {descricao, unidade, preco_unitario}}"""
    ws = wb["BD_MATERIAIS"]
    mat = {}
    for row in ws.iter_rows(min_row=4, values_only=True):
        if not row[0] or not str(row[0]).strip():
            continue
        codigo = str(row[0]).strip()
        mat[codigo] = {
            "codigo": codigo,
            "descricao": str(row[1]).strip() if row[1] else "",
            "unidade": str(row[2]).strip() if row[2] else "un",
            "preco_unitario": float(row[3]) if row[3] else 0.0,
        }
    print(f"  BD_MATERIAIS: {len(mat)} registros")
    return mat


def ler_produtividades(wb: openpyxl.Workbook) -> list[dict]:
    """BD_PRODUTIVIDADES → lista com todos os 73 serviços."""
    ws = wb["BD_PRODUTIVIDADES"]
    prods = []
    for row in ws.iter_rows(min_row=4, values_only=True):
        if not row[0] or not str(row[0]).strip():
            continue
        prods.append({
            "codigo": str(row[0]).strip(),
            "descricao": str(row[1]).strip() if row[1] else "",
            "unidade": str(row[2]).strip().lower() if row[2] else "m2",
            "produtividade_unh": float(row[3]) if row[3] else 1.0,
            "h_por_un": float(row[4]) if row[4] else 0.0,
            "composicao_mo": str(row[5]) if row[5] else "",
            "qtd_mo": int(row[6]) if row[6] else 0,
            "custo_mo_h": float(row[7]) if row[7] else 0.0,
            "composicao_equip": str(row[8]) if row[8] else "",
            "qtd_equip": int(row[9]) if row[9] else 0,
            "custo_equip_h": float(row[10]) if row[10] else 0.0,
            "material": str(row[11]) if row[11] else "—",
            "custo_mat_un": float(row[12]) if row[12] else 0.0,
        })
    print(f"  BD_PRODUTIVIDADES: {len(prods)} serviços")
    return prods


def ler_bdi(wb: openpyxl.Workbook) -> dict:
    """BDI → componentes por categoria."""
    ws = wb["BDI"]
    # Colunas: MO(A-C), MATERIAIS(E-G), SERVIÇOS(I-K), INDIRETOS(M-O), DIESEL(Q-S)
    categorias = {
        "mao_obra": {},
        "materiais": {},
        "servicos": {},
        "indiretos": {},
        "diesel": {},
    }
    col_map = [
        ("mao_obra", 0, 2),
        ("materiais", 4, 6),
        ("servicos", 8, 10),
        ("indiretos", 12, 14),
        ("diesel", 16, 18),
    ]
    siglas = {
        "AC": "ac", "DF": "df", "R": "r", "L": "l",
        "COFINS": "cofins", "ISS": "iss", "PIS": "pis",
        "CSSL": "cssl", "IR": "ir", "CR": "cr", "TT": "total",
        "T": "tributos",
    }
    for row in ws.iter_rows(min_row=4, values_only=True):
        for cat_name, col_sigla, col_pct in col_map:
            sigla_raw = row[col_sigla]
            # row[col_pct] é a porcentagem
            pct = row[col_pct] if col_pct < len(row) else None
            if sigla_raw and pct is not None:
                sig = str(sigla_raw).strip().upper()
                key = siglas.get(sig, sig.lower())
                categorias[cat_name][key] = float(pct)
            # TT pode estar na última linha via descrição
            if col_sigla + 1 < len(row):
                desc = row[col_sigla + 1]
                if desc and "Total do BDI" in str(desc) and pct:
                    categorias[cat_name]["total"] = float(pct)
    return categorias


# ── Geradores ─────────────────────────────────────────────────────────────────

def gerar_insumos_mo(mo_data: dict[str, dict]) -> None:
    print("\n[MÃO DE OBRA]")
    for codigo, d in mo_data.items():
        insumo = {
            "codigo": codigo,
            "tipo": "MAO_OBRA",
            "descricao": d["funcao"],
            "unidade": "mes",
            "preco_unitario": d["salario_mensal"],   # BASE sem encargos (ADR-009)
            "fonte_preco": "planilha_rfi_r02",
            "atributos_especificos": {
                "tipo_contrato": d["tipo_contrato"],
                "horas_mes": d["horas_mes"],
                "salario_base_hora": round(d["salario_base_h"], 6),
                "custo_hora_com_encargos_planilha": round(d["custo_h_com_encargos"], 4),
                "codigo_planilha": codigo,
            },
            "data_referencia_preco": DATA_REF,
            "categoria": "TERRAPLENAGEM",
        }
        write_json(CATALOG_DIR / "insumos" / "mao_obra" / f"{codigo}.json", insumo)


def gerar_insumos_equipamentos(equip_data: dict[str, dict]) -> None:
    print("\n[EQUIPAMENTOS]")
    for codigo, d in equip_data.items():
        insumo = {
            "codigo": codigo,
            "tipo": "EQUIPAMENTO",
            "descricao": d["descricao"],
            "unidade": "h",
            "preco_unitario": d["custo_total_h"],   # custo horário total (inclui manutenção)
            "fonte_preco": "planilha_rfi_r02",
            "atributos_especificos": {
                "tipo_locacao": d["tipo"],
                "custo_produtivo_h": d["custo_produtivo_h"],
                "pct_manutencao": d["pct_manutencao"],
                "custo_mensal": d["custo_mensal"],
                "codigo_planilha": codigo,
            },
            "data_referencia_preco": DATA_REF,
            "categoria": "TERRAPLENAGEM",
        }
        write_json(CATALOG_DIR / "insumos" / "equipamento" / f"{codigo}.json", insumo)


def gerar_insumos_materiais(mat_data: dict[str, dict]) -> None:
    print("\n[MATERIAIS]")
    for codigo, d in mat_data.items():
        insumo = {
            "codigo": codigo,
            "tipo": "MATERIAL",
            "descricao": d["descricao"],
            "unidade": d["unidade"],
            "preco_unitario": d["preco_unitario"],
            "fonte_preco": "planilha_rfi_r02",
            "atributos_especificos": {
                "codigo_planilha": codigo,
            },
            "data_referencia_preco": DATA_REF,
            "categoria": "TERRAPLENAGEM",
        }
        write_json(CATALOG_DIR / "insumos" / "material" / f"{codigo}.json", insumo)


def gerar_producao_e_cpu(prod: dict) -> None:
    """Gera arquivos de produção + CPU para um serviço da planilha."""
    ati_cod = prod["codigo"]
    cpu_id = ATI_TO_CPU.get(ati_cod, f"CPU-TERRA-{ati_cod}")
    prod_id = f"{cpu_id}-PROD-001"

    # Composição de equipe
    funcoes = []
    for p_code, num in parse_composicao(prod["composicao_mo"]):
        funcoes.append({"funcao_id": p_code, "num_pessoas": num})

    equipamentos = []
    for e_code, num in parse_composicao(prod["composicao_equip"]):
        equipamentos.append({"equip_id": e_code, "num_unidades": num})

    # Producao
    producao = {
        "id": prod_id,
        "codigo": ati_cod,
        "descricao": prod["descricao"],
        "producao_horaria": prod["produtividade_unh"],
        "unidade": prod["unidade"],
        "origem": {
            "tipo": "planilha_rfi_r02",
            "fonte_id": ati_cod,
            "data_calibracao": DATA_REF,
            "referencia": "Planilha Padrão RFI R02 — MendesLôbo Construção",
        },
        "composicao_padrao_equipe": {
            "funcoes": funcoes,
            "equipamentos": equipamentos,
        },
        "custos_equipe_planilha": {
            "custo_mo_h": prod["custo_mo_h"],
            "custo_equip_h": prod["custo_equip_h"],
            "total_h": round(prod["custo_mo_h"] + prod["custo_equip_h"], 2),
            "pu_calculado": round(
                (prod["custo_mo_h"] + prod["custo_equip_h"]) / prod["produtividade_unh"], 4
            ) if prod["produtividade_unh"] > 0 else 0.0,
        },
        "categoria": "TERRAPLENAGEM",
    }
    write_json(CATALOG_DIR / "produtividades" / f"{prod_id}.json", producao)

    # CPU
    cpu = {
        "codigo": cpu_id,
        "descricao": prod["descricao"],
        "unidade": prod["unidade"],
        "categoria": "TERRAPLENAGEM",
        "origem": "PROPRIA",
        "producao_id_ref": prod_id,
        "composicao_itens": [],          # sem diesel destacado: equipamentos de locação já incluem tudo
        "_nota": f"Fonte: Planilha RFI R02, {ati_cod}. Custo horário equipe: "
                 f"MO R${prod['custo_mo_h']:.2f}/h + Equip R${prod['custo_equip_h']:.2f}/h. "
                 f"Produt: {prod['produtividade_unh']} {prod['unidade']}/h.",
    }
    write_json(CATALOG_DIR / "cpus" / f"{cpu_id}.json", cpu)


def gerar_cpus_agis_especificos() -> None:
    """Gera CPUs AGIS-específicos (não existentes na planilha) com códigos RFI."""
    print("\n[CPUs AGIS-ESPECÍFICOS]")
    for cpu_id, info in AGIS_CUSTOM_CPUS.items():
        prod_id = f"{cpu_id}-PROD-001"

        producao = {
            "id": prod_id,
            "codigo": cpu_id,
            "descricao": info["descricao"],
            "producao_horaria": info["producao_horaria"],
            "unidade": info["unidade"],
            "origem": {
                "tipo": "construido_rfi_r02",
                "fonte_id": cpu_id,
                "data_calibracao": DATA_REF,
                "referencia": (
                    "Composto com códigos RFI R02. Produtividade do catálogo mendeslobo. "
                    "Serviço específico AGIS sem equivalente ATI na planilha."
                ),
            },
            "composicao_padrao_equipe": {
                "funcoes": info["funcoes"],
                "equipamentos": info["equipamentos"],
            },
            "categoria": "TERRAPLENAGEM",
        }
        write_json(CATALOG_DIR / "produtividades" / f"{prod_id}.json", producao)

        cpu = {
            "codigo": cpu_id,
            "descricao": info["descricao"],
            "unidade": info["unidade"],
            "categoria": "TERRAPLENAGEM",
            "origem": "PROPRIA",
            "producao_id_ref": prod_id,
            "composicao_itens": [],
            "_nota": (
                f"CPU AGIS-específico construído com códigos RFI R02. "
                f"Produtividade {info['producao_horaria']} {info['unidade']}/h (calibrado catálogo mendeslobo)."
            ),
        }
        write_json(CATALOG_DIR / "cpus" / f"{cpu_id}.json", cpu)


def gerar_perfil(bdi: dict) -> None:
    """Gera config/perfis/rfi-r02.json com BDI e encargos da planilha."""
    perfil = {
        "id": "rfi-r02",
        "nome": "Planilha Padrão RFI R02 — MendesLôbo Construção",
        "descricao": "Parâmetros financeiros extraídos da Planilha RFI R02 (mai/2026).",
        "origem": "planilha_rfi_r02",
        "data_referencia": DATA_REF,
        # BDI por categoria — da aba BDI da planilha
        "bdi": {
            "mao_obra": {
                "ac": bdi["mao_obra"].get("ac", 0.05),
                "df": bdi["mao_obra"].get("df", 0.015),
                "r":  bdi["mao_obra"].get("r", 0.01),
                "l":  bdi["mao_obra"].get("l", 0.09),
                "cofins": bdi["mao_obra"].get("cofins", 0.03),
                "iss":    bdi["mao_obra"].get("iss", 0.05),
                "pis":    bdi["mao_obra"].get("pis", 0.0065),
                "cssl":   bdi["mao_obra"].get("cssl", 0.0199),
                "ir":     bdi["mao_obra"].get("ir", 0.0274),
                "total":  bdi["mao_obra"].get("total", 0.3545),
            },
            "materiais": {
                "l":     bdi["materiais"].get("l", 0.05),
                "total": bdi["materiais"].get("total", 0.05),
            },
            "servicos": {
                "total": bdi["servicos"].get("total", bdi["mao_obra"].get("total", 0.3545)),
            },
            "diesel": {
                "total": bdi["diesel"].get("total", bdi["materiais"].get("total", 0.05)),
            },
        },
        # Encargos sociais — Regime Não Desonerado (referência da planilha: PARÂMETROS!B28)
        "percentual_encargos": 0.6162,              # multiplicador = 1.6162 (PARÂMETROS)
        "percentual_encargos_clt_horista": 0.7770,  # 177.70% — aba ENCARGOS (campo)
        "percentual_encargos_clt_mensalista": 0.06, # 106% — aba ENCARGOS (admin)
        "regime_tributacao": "nao_desonerado",
        # Margem-alvo e demais parâmetros financeiros
        "meta_margem_pct": 0.10,
        "taxa_risco_adicional": 0.0,
    }
    write_json(PERFIS_DIR / "rfi-r02.json", perfil)


def gerar_contexto() -> None:
    """Gera config/contextos/mendeslobo-rfi.json."""
    contexto = {
        "id": "mendeslobo-rfi",
        "nome": "MendesLôbo — Catálogo RFI R02",
        "descricao": "Contexto usando catálogo gerado da Planilha Padrão RFI R02 (mai/2026).",
        "catalogo_id": "rfi-r02",
        "perfil_id": "rfi-r02",
        "jurisdicao_id": "rj",
        "tema_id": "default",
        "data_referencia": DATA_REF,
        "origem": "planilha_rfi_r02",
    }
    write_json(CONTEXTOS_DIR / "mendeslobo-rfi.json", contexto)


# ── Main ──────────────────────────────────────────────────────────────────────

def main() -> None:
    print("=" * 60)
    print("GERAÇÃO DE CATÁLOGO RFI-R02")
    print("=" * 60)

    if not PLANILHA.exists():
        print(f"ERRO: Planilha não encontrada: {PLANILHA}", file=sys.stderr)
        sys.exit(1)

    print("\n[1] Lendo planilha…")
    wb = carregar_planilha()
    mo_data = ler_mo(wb)
    equip_data = ler_equipamentos(wb)
    mat_data = ler_materiais(wb)
    prods = ler_produtividades(wb)
    bdi = ler_bdi(wb)

    print("\n[2] Gerando insumos…")
    gerar_insumos_mo(mo_data)
    gerar_insumos_equipamentos(equip_data)
    gerar_insumos_materiais(mat_data)

    print("\n[3] Gerando produtividades + CPUs (73 ATI)…")
    for prod in prods:
        gerar_producao_e_cpu(prod)

    gerar_cpus_agis_especificos()

    print("\n[4] Gerando perfil…")
    gerar_perfil(bdi)

    print("\n[5] Gerando contexto…")
    gerar_contexto()

    # Resumo
    n_cpus = len(list((CATALOG_DIR / "cpus").glob("*.json")))
    n_prod = len(list((CATALOG_DIR / "produtividades").glob("*.json")))
    n_mo   = len(list((CATALOG_DIR / "insumos/mao_obra").glob("*.json")))
    n_eq   = len(list((CATALOG_DIR / "insumos/equipamento").glob("*.json")))
    n_mat  = len(list((CATALOG_DIR / "insumos/material").glob("*.json")))

    print("\n" + "=" * 60)
    print("CATÁLOGO GERADO COM SUCESSO")
    print("=" * 60)
    print(f"  CPUs:          {n_cpus}")
    print(f"  Produtividades:{n_prod}")
    print(f"  Insumos MO:    {n_mo}")
    print(f"  Insumos Equip: {n_eq}")
    print(f"  Insumos Mat:   {n_mat}")
    print(f"  Perfil:        rfi-r02")
    print(f"  Contexto:      mendeslobo-rfi")
    print(f"\n  Destino: {CATALOG_DIR.relative_to(REPO_ROOT)}")


if __name__ == "__main__":
    main()
