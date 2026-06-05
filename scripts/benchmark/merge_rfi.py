#!/usr/bin/env python3
"""
Merge entre catálogo Concilium e PLANILHA PADRÃO RFI.xlsm

Uso:
    python tools/merge_rfi.py --contexto mendeslobo          # dry-run (relatório)
    python tools/merge_rfi.py --contexto mendeslobo --apply  # aplica merge

Operações de comparação (como JOIN):
    LEFT_ONLY   : no catálogo, não na planilha   → mantém (sem alteração)
    RIGHT_ONLY  : na planilha, não no catálogo   → candidato a inclusão
    INNER_HIGH  : match confiante (score ≥ 0.85) → atualiza preço/dados se diferente
    INNER_LOW   : match incerto  (0.50–0.85)     → reporta para revisão manual

Heurística de matching:
    1. Código direto              → score 1.0
    2. Overlap de tokens          → score 0.0–1.0 (após normalização ASCII)
    3. Boost +0.10 se mesma unidade E preço dentro de ±30%
    Limiar HIGH ≥ 0.85 / LOW 0.50–0.85 / NO_MATCH < 0.50
"""
from __future__ import annotations

import argparse
import io
import json
import re
import sys
import unicodedata
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace")

try:
    import openpyxl
except ImportError:
    print("openpyxl não encontrado. Execute: uv add openpyxl", file=sys.stderr)
    sys.exit(2)

ROOT = Path(__file__).resolve().parents[1]
XLSM = ROOT / "docs/product/3-reference_files/catalogos/PLANILHA PADRÃO RFI.xlsm"
HEADER_ROW = 3  # linha real do header nas abas BD_* (1-indexed)

# ── Constantes de matching ────────────────────────────────────────────────────
THRESHOLD_HIGH = 0.85
THRESHOLD_LOW  = 0.50
PRICE_TOLERANCE = 0.30       # ±30%
CODE_COLLISION_DESC_MIN = 0.28  # código igual mas desc muito divergente → INNER_LOW

# ── Normalização de unidades ──────────────────────────────────────────────────
# Mapeia variantes gráficas para forma canônica ASCII
_UNIT_CANON: dict[str, str] = {
    "m²": "m2", "m³": "m3",
    "M²": "m2", "M³": "m3",
    "M2": "m2", "M3": "m3",
    "m2": "m2", "m3": "m3",
    "UND": "un", "und": "un", "UN": "un", "Und": "un",
    "KG":  "kg", "Kg":  "kg",
    "TON": "t",  "Ton": "t",
    "H":   "h",  "Hr":  "h",
    "L":   "l",  "Lt":  "l",
}

def _norm_unit(u: str | None) -> str:
    if not u:
        return ""
    s = u.strip()
    # Substitui caracteres superscript unicode → ASCII equivalente
    s = s.replace("²", "2").replace("³", "3")  # ² → 2, ³ → 3
    return _UNIT_CANON.get(s, s.lower())

# ── Normalização de texto ─────────────────────────────────────────────────────
_STOP = {"de", "do", "da", "dos", "das", "e", "a", "o", "em", "com", "para", "por"}

# Abreviações técnicas de construção → forma expandida
# Permite que "Esc/carg/transp" bata com "Escavação, carga e transporte"
_ABBREV = {
    "esc":     "escavacao",
    "carg":    "carga",
    "transp":  "transporte",
    "compac":  "compactacao",
    "compact": "compactacao",
    "regul":   "regularizacao",
    "subl":    "subleito",
    "sublet":  "subleito",
    "sub":     "subleito",
    "reg":     "regularizacao",
    "bgtc":    "brita graduada tratada cimento",
    "bgsc":    "brita graduada sem cimento",
    "cbuq":    "concreto betuminoso usinado quente",
    "pn":      "proctor normal",
    "pi":      "proctor intermediario",
    "dmt":     "distancia media transporte",
    "dn":      "diametro nominal",
    "pba":     "pba",
    "cat":     "categoria",
}

def _normalize(text: str) -> set[str]:
    """Converte texto em conjunto de tokens ASCII normalizados com expansão de abreviações."""
    t = unicodedata.normalize("NFD", str(text).lower())
    t = "".join(c for c in t if unicodedata.category(c) != "Mn")  # remove acentos
    t = re.sub(r"[^a-z0-9\s]", " ", t)
    tokens = {w for w in t.split() if w not in _STOP and len(w) > 1}
    # Expande abreviações: substitui token abreviado pelos tokens expandidos (multi-palavra)
    expanded: set[str] = set()
    for tok in tokens:
        expansion = _ABBREV.get(tok, tok)
        if expansion == tok:
            expanded.add(tok)
        else:
            # Expansão multi-palavra: divide e filtra cada palavra individualmente
            for word in expansion.split():
                if word not in _STOP and len(word) > 1:
                    expanded.add(word)
    return expanded

def _similarity(a: str, b: str) -> float:
    """Jaccard similarity entre tokens normalizados."""
    ta, tb = _normalize(a), _normalize(b)
    if not ta or not tb:
        return 0.0
    return len(ta & tb) / len(ta | tb)

def _match_score(rfi: dict, cat: dict) -> float:
    """Score de matching entre uma entidade RFI e uma do catálogo."""
    # 0. Tipos incompatíveis → sem match (evita cross-type MATERIAL vs TERCEIRIZADO, etc.)
    tipo_rfi = rfi.get("tipo")
    tipo_cat = cat.get("tipo")
    if tipo_rfi and tipo_cat and tipo_rfi != tipo_cat:
        return 0.0

    desc_sim = _similarity(rfi.get("descricao", ""), cat.get("descricao", ""))

    # 1. Código direto (usa codigo com fallback para id — producoes podem ter só id)
    rfi_code = rfi.get("codigo") or rfi.get("id", "")
    cat_code = cat.get("codigo") or cat.get("id", "")
    if rfi_code and rfi_code == cat_code:
        # Protege contra code collision: código igual mas conteúdo divergente
        if desc_sim < CODE_COLLISION_DESC_MIN:
            return 0.70  # força INNER_LOW para revisão manual
        return 1.0

    # 2. Similaridade de descrição
    score = desc_sim

    # 3. Boost por unidade + preço (usa unidades normalizadas)
    u_rfi = _norm_unit(rfi.get("unidade"))
    u_cat = _norm_unit(cat.get("unidade"))
    if u_rfi and u_rfi == u_cat:
        p_rfi = rfi.get("preco_unitario") or 0
        p_cat = cat.get("preco_unitario") or 0
        if p_cat > 0 and abs(p_rfi - p_cat) / p_cat <= PRICE_TOLERANCE:
            score = min(1.0, score + 0.10)

    return round(score, 4)

def _categorize(score: float, rfi: dict, cat: dict | None) -> str:
    if cat is None:
        return "RIGHT_ONLY"
    if score >= THRESHOLD_HIGH:
        return "INNER_HIGH"
    if score >= THRESHOLD_LOW:
        return "INNER_LOW"
    return "NO_MATCH"  # tratar como RIGHT_ONLY

# ── Mapeamento de fonte ───────────────────────────────────────────────────────
_FONTE_MAP = {
    "cotação mercado": "cotacao_mercado",
    "cotacao mercado": "cotacao_mercado",
    "sinapi": "tabela_referencia",
    "sicro": "tabela_referencia",
    "tabela referencia": "tabela_referencia",
    "negociado": "negociado",
    "catalogo": "catalogo_proprio",
    "proprio": "catalogo_proprio",
}

def _map_fonte(raw: str | None) -> str:
    if not raw:
        return "catalogo_proprio"
    key = unicodedata.normalize("NFD", str(raw).lower())
    key = "".join(c for c in key if unicodedata.category(c) != "Mn")
    for k, v in _FONTE_MAP.items():
        if k in key:
            return v
    return "catalogo_proprio"

def _fmt_date(val: Any) -> str | None:
    if val is None:
        return None
    if isinstance(val, datetime):
        return val.strftime("%Y-%m-%d")
    s = str(val)
    m = re.match(r"(\d{4}-\d{2}-\d{2})", s)
    return m.group(1) if m else None

# ── Parsing de composições  "P0062×1, P0001×3" ───────────────────────────────
def _parse_mo(raw: str | None) -> list[dict]:
    if not raw or str(raw).strip() in ("—", "-", "", "None"):
        return []
    items = []
    for part in re.split(r"[,;]", str(raw)):
        m = re.match(r"\s*([A-Z0-9]+)\s*[x×]\s*(\d+)", part.strip(), re.IGNORECASE)
        if m:
            items.append({"funcao_id": m.group(1), "num_pessoas": int(m.group(2))})
    return items

def _parse_eq(raw: str | None) -> list[dict]:
    if not raw or str(raw).strip() in ("—", "-", "", "None"):
        return []
    items = []
    for part in re.split(r"[,;]", str(raw)):
        m = re.match(r"\s*([A-Z0-9]+)\s*[x×]\s*(\d+)", part.strip(), re.IGNORECASE)
        if m:
            items.append({"equip_id": f"EQ-{m.group(1)}", "num_unidades": int(m.group(2))})
    return items

def _parse_mat(raw: str | None) -> list[dict]:
    if not raw or str(raw).strip() in ("—", "-", "", "None"):
        return []
    items = []
    for part in re.split(r"[,;]", str(raw)):
        m = re.match(r"\s*([A-Z0-9]+)\s*[x×]\s*([\d.]+)", part.strip(), re.IGNORECASE)
        if m:
            items.append({"insumo_id": f"MA-{m.group(1)}", "consumo_por_hora": float(m.group(2)), "unidade": "un"})
    return items

# ── Extractor ─────────────────────────────────────────────────────────────────

def _read_sheet(wb: Any, name: str, header_row: int = HEADER_ROW) -> list[dict]:
    """Lê uma aba como lista de dicts (ignora linhas all-None)."""
    if name not in wb.sheetnames:
        return []
    ws = wb[name]
    rows = list(ws.iter_rows(min_row=header_row, values_only=True))
    if not rows:
        return []
    headers = [str(h).strip() if h is not None else f"_col{i}" for i, h in enumerate(rows[0])]
    result = []
    for row in rows[1:]:
        if all(c is None for c in row):
            continue
        d = {headers[i]: row[i] for i in range(min(len(headers), len(row)))}
        result.append(d)
    return result

def _clean_entity(e: dict) -> dict:
    """Normaliza unidade e remove espaços extras de descrição."""
    if "unidade" in e:
        e["unidade"] = _norm_unit(e["unidade"]) or e["unidade"]
    if "descricao" in e and e["descricao"]:
        e["descricao"] = e["descricao"].strip()
    return e

def _is_valid(e: dict, min_desc_len: int = 3) -> bool:
    """Filtra entidades sem descrição real (linhas em branco/incompletas da planilha)."""
    desc = (e.get("descricao") or "").strip()
    return len(desc) >= min_desc_len and bool(e.get("codigo", "").strip())

def extract_rfi(wb: Any) -> dict:
    """Extrai todas as entidades da planilha RFI no formato do catálogo."""
    insumos: list[dict] = []
    producoes: list[dict] = []

    # ── MAO_OBRA ──────────────────────────────────────────────────────────────
    for row in _read_sheet(wb, "BD_MÃO_DE_OBRA"):
        cod = str(row.get("Código") or "").strip()
        if not cod or cod.lower() == "código":
            continue
        descricao = str(row.get("Função") or "").strip()
        tipo_ct = str(row.get("Tipo\n(CLT/PJ)") or row.get("Tipo") or "CLT").strip().upper()
        sal_mensal = row.get("Salário\nMensal (R$)") or row.get("Salário Mensal (R$)") or 0
        horas_mes = row.get("Horas\n/Mês") or row.get("Horas/Mês") or 220
        encargos = row.get("Encargos\nAplicados") or row.get("Encargos Aplicados") or 0
        data_ref = _fmt_date(row.get("Data Atualização"))
        try:
            sal_mensal = float(sal_mensal)
            horas_mes = float(horas_mes)
            encargos = float(encargos)
        except (TypeError, ValueError):
            sal_mensal = 0; horas_mes = 220; encargos = 0
        insumos.append({
            "codigo": cod,
            "tipo": "MAO_OBRA",
            "descricao": descricao,
            "unidade": "mes",
            "preco_unitario": round(sal_mensal, 4),
            "fonte_preco": "negociado",
            "data_referencia_preco": data_ref,
            "atributos_especificos": {
                "tipo_contrato": "CLT" if "CLT" in tipo_ct else "PJ",
                "salario_mensal": sal_mensal,
                "horas_mes": horas_mes,
                "percentual_encargos_local": encargos,
            },
            "_fonte_rfi": "BD_MÃO_DE_OBRA",
        })

    # ── EQUIPAMENTO ──────────────────────────────────────────────────────────
    for row in _read_sheet(wb, "BD_EQUIPAMENTOS"):
        cod = str(row.get("Código") or "").strip()
        if not cod or cod.lower() == "código":
            continue
        descricao = str(row.get("Descrição") or "").strip()
        tipo_prop_raw = str(row.get("Tipo\n(próprio/loc.)") or row.get("Tipo") or "locação").strip().lower()
        tipo_prop = "locacao" if "loc" in tipo_prop_raw else "proprio"
        custo_prod = row.get("Custo Produtivo\n(R$/h)") or row.get("Custo Produtivo (R$/h)") or 0
        pct_manut  = row.get("% Manutenção") or 0
        custo_mensal = row.get("Custo Mensal\n(R$/mês)") or row.get("Custo Mensal (R$/mês)") or 0
        data_ref = _fmt_date(row.get("Data Atualização"))
        try:
            custo_prod = float(custo_prod); pct_manut = float(pct_manut); custo_mensal = float(custo_mensal)
        except (TypeError, ValueError):
            custo_prod = 0; pct_manut = 0; custo_mensal = 0
        # codigo: E0001 → EQ-E0001
        codigo_cat = f"EQ-{cod}" if not cod.startswith("EQ-") else cod
        insumos.append({
            "codigo": codigo_cat,
            "tipo": "EQUIPAMENTO",
            "descricao": descricao,
            "unidade": "h",
            "preco_unitario": round(custo_prod, 4),
            "fonte_preco": "catalogo_proprio",
            "data_referencia_preco": data_ref,
            "atributos_especificos": {
                "tipo_propriedade": tipo_prop,
                "valor_locacao_mensal": round(custo_mensal, 4) if custo_mensal else None,
                "pct_manutencao": pct_manut if pct_manut else None,
            },
            "_fonte_rfi": "BD_EQUIPAMENTOS",
        })

    # ── MATERIAL ──────────────────────────────────────────────────────────────
    for row in _read_sheet(wb, "BD_MATERIAIS"):
        cod = str(row.get("Código") or "").strip()
        if not cod or cod.lower() == "código":
            continue
        descricao = str(row.get("Descrição") or "").strip()
        unidade   = str(row.get("Unidade") or "un").strip()
        preco     = row.get("Preço Unitário\n(R$)") or row.get("Preço Unitário (R$)") or 0
        fornec    = str(row.get("Fornecedor\nReferência") or row.get("Fornecedor Referência") or "").strip()
        fonte_raw = str(row.get("Fonte/Origem") or "").strip()
        data_ref  = _fmt_date(row.get("Data Atualização"))
        try:
            preco = float(preco)
        except (TypeError, ValueError):
            preco = 0
        codigo_cat = f"MA-{cod}" if not cod.startswith("MA-") else cod
        insumos.append({
            "codigo": codigo_cat,
            "tipo": "MATERIAL",
            "descricao": descricao,
            "unidade": unidade,
            "preco_unitario": round(preco, 4),
            "fonte_preco": _map_fonte(fonte_raw),
            "data_referencia_preco": data_ref,
            "atributos_especificos": {
                "fornecedor_referencia": fornec or None,
            },
            "_fonte_rfi": "BD_MATERIAIS",
        })

    # ── TERCEIRIZADOS ─────────────────────────────────────────────────────────
    for row in _read_sheet(wb, "SERVIÇOS TERCEIRIZADOS", header_row=2):
        cod = str(row.get("CÓDIGO") or "").strip()
        if not cod or cod.lower() in ("código", ""):
            continue
        descricao = str(row.get("DESCRIÇÃO") or "").strip()
        unidade   = str(row.get("UNID.") or "un").strip()
        preco     = row.get("R$ UNITÁRIO") or 0
        try:
            preco = float(preco)
        except (TypeError, ValueError):
            preco = 0
        insumos.append({
            "codigo": cod,
            "tipo": "TERCEIRIZADO",
            "descricao": descricao,
            "unidade": unidade,
            "preco_unitario": round(preco, 4),
            "fonte_preco": "negociado",
            "_fonte_rfi": "SERVIÇOS TERCEIRIZADOS",
        })

    # ── PRODUTIVIDADES ────────────────────────────────────────────────────────
    for row in _read_sheet(wb, "BD_PRODUTIVIDADES"):
        cod = str(row.get("Código") or "").strip()
        if not cod or cod.lower() == "código":
            continue
        descricao = str(row.get("Descrição do Serviço") or "").strip()
        unidade   = str(row.get("Unidade") or "un").strip()
        prod_raw  = row.get("Produtividade\n(un/h)") or row.get("Produtividade (un/h)") or 0
        mo_comp   = str(row.get("Composição MO\n(cód. BD_MO)") or row.get("Composição MO (cód. BD_MO)") or "").strip()
        eq_comp   = str(row.get("Composição Equip.\n(cód. BD_EQ)") or row.get("Composição Equip. (cód. BD_EQ)") or "").strip()
        mat_comp  = str(row.get("Material Principal\n(cód. BD_MAT)") or row.get("Material Principal (cód. BD_MAT)") or "").strip()
        try:
            valor_horario = float(prod_raw)
        except (TypeError, ValueError):
            valor_horario = 0
        funcoes      = _parse_mo(mo_comp)
        equipamentos = _parse_eq(eq_comp)
        materiais    = _parse_mat(mat_comp)
        producoes.append({
            "id": cod,
            "codigo": cod,
            "descricao": descricao,
            "valor_horario": round(valor_horario, 6) if valor_horario else None,
            "unidade": unidade,
            "origem": "PROPRIA",
            "composicao_padrao_equipe": {
                "funcoes": funcoes,
                "equipamentos": equipamentos,
                "materiais": materiais,
            },
            "_fonte_rfi": "BD_PRODUTIVIDADES",
        })

    # Normaliza e filtra entidades incompletas
    insumos   = [_clean_entity(e) for e in insumos   if _is_valid(e)]
    producoes = [_clean_entity(e) for e in producoes if _is_valid(e)]

    return {"insumos": insumos, "producoes": producoes}

# ── Merge ─────────────────────────────────────────────────────────────────────

class MergeReport:
    def __init__(self) -> None:
        self.inner_high: list[dict] = []
        self.inner_low:  list[dict] = []
        self.right_only: list[dict] = []
        self.left_only:  list[dict] = []

def _merge_entities(
    catalog_list: list[dict],
    rfi_list: list[dict],
    id_key: str = "codigo",
) -> tuple[MergeReport, list[dict]]:
    """
    Compara duas listas de entidades e retorna relatório + lista mergeada.
    Estratégia INNER_HIGH: preço do catálogo é atualizado com o da RFI se diferente.
    """
    report = MergeReport()
    cat_by_code = {e.get(id_key, ""): e for e in catalog_list}
    rfi_matched: set[str] = set()
    result = list(catalog_list)  # começa com tudo do catálogo

    for rfi in rfi_list:
        rfi_code = rfi.get(id_key, "")
        best_score = 0.0
        best_cat   = None

        # Procura melhor match no catálogo
        for cat in catalog_list:
            s = _match_score(rfi, cat)
            if s > best_score:
                best_score = s
                best_cat = cat

        category = _categorize(best_score, rfi, best_cat)

        if category == "RIGHT_ONLY" or category == "NO_MATCH":
            report.right_only.append({"rfi": rfi, "score": best_score})
        elif category == "INNER_HIGH":
            rfi_matched.add(best_cat.get(id_key, ""))
            delta = _delta(best_cat, rfi)
            report.inner_high.append({
                "catalog": best_cat, "rfi": rfi,
                "score": best_score, "delta": delta,
            })
        elif category == "INNER_LOW":
            report.inner_low.append({
                "catalog": best_cat, "rfi": rfi,
                "score": best_score,
            })

    # LEFT_ONLY: no catálogo mas não matchou com nada na RFI
    matched_cat_codes = {e["catalog"].get(id_key, "") for e in report.inner_high}
    matched_cat_codes |= {e["catalog"].get(id_key, "") for e in report.inner_low}
    for cat in catalog_list:
        if cat.get(id_key, "") not in matched_cat_codes:
            report.left_only.append({"catalog": cat})

    return report, result

def _delta(cat: dict, rfi: dict) -> dict:
    """Computa diferenças relevantes entre catálogo e RFI (ignora variações gráficas)."""
    d: dict = {}
    for field in ("preco_unitario", "descricao", "unidade", "fonte_preco"):
        v_cat = cat.get(field)
        v_rfi = rfi.get(field)
        if v_rfi is None:
            continue
        # Normaliza unidades antes de comparar (m³ == m3, etc.)
        if field == "unidade":
            if _norm_unit(str(v_cat or "")) == _norm_unit(str(v_rfi or "")):
                continue  # mesma unidade, variação gráfica apenas
        # Normaliza descrições
        if field == "descricao":
            t_cat = _normalize(str(v_cat or ""))
            t_rfi = _normalize(str(v_rfi or ""))
            if t_cat == t_rfi:
                continue  # idênticas após normalização
            # RFI é subconjunto do catálogo: catálogo é mais completo → manter catálogo
            if t_rfi and t_rfi.issubset(t_cat):
                continue
        if v_cat != v_rfi:
            d[field] = {"catalog": v_cat, "rfi": v_rfi}
            if field == "preco_unitario" and v_cat and v_rfi:
                try:
                    pct = (float(v_rfi) - float(v_cat)) / float(v_cat) * 100
                    d[field]["delta_pct"] = round(pct, 2)
                except (TypeError, ZeroDivisionError):
                    pass
    return d

def _apply_merge(
    catalog_list: list[dict],
    rfi_list: list[dict],
    report: MergeReport,
    id_key: str = "codigo",
    include_right_only: bool = True,
) -> list[dict]:
    """Aplica merge: atualiza INNER_HIGH, adiciona RIGHT_ONLY ao catálogo."""
    result = {e.get(id_key, ""): dict(e) for e in catalog_list}

    # Atualiza INNER_HIGH
    for item in report.inner_high:
        cat_code = item["catalog"].get(id_key, "")
        if cat_code in result and item["delta"]:
            for field, chg in item["delta"].items():
                result[cat_code][field] = chg["rfi"]
            result[cat_code]["_rfi_updated_at"] = datetime.now(timezone.utc).strftime("%Y-%m-%d")

    # Adiciona RIGHT_ONLY
    if include_right_only:
        for item in report.right_only:
            rfi = item["rfi"]
            cod = rfi.get(id_key, "")
            if not cod:
                continue
            # Se o código já existe no catálogo (colisão verdadeira), importa com prefixo RFI-
            if cod in result:
                cod = f"RFI-{cod}"
            clean = {k: v for k, v in rfi.items() if not k.startswith("_")}
            clean[id_key] = cod
            clean["_rfi_imported_at"] = datetime.now(timezone.utc).strftime("%Y-%m-%d")
            result[cod] = clean

    # Converte INNER_LOW colisões reais em RIGHT_ONLY com prefixo RFI-
    # (código bate mas conteúdo diverge completamente — não sobrescreve catálogo)
    for item in report.inner_low:
        rfi_e = item["rfi"]
        cat_e = item["catalog"]
        rfi_cod = rfi_e.get(id_key, "")
        cat_cod = cat_e.get(id_key, "")
        if rfi_cod == cat_cod and rfi_cod:
            # True collision: importa RFI com novo código prefixado
            new_cod = f"RFI-{rfi_cod}"
            if new_cod not in result:
                clean = {k: v for k, v in rfi_e.items() if not k.startswith("_")}
                clean[id_key] = new_cod
                clean["_rfi_collision_original_code"] = rfi_cod
                clean["_rfi_imported_at"] = datetime.now(timezone.utc).strftime("%Y-%m-%d")
                result[new_cod] = clean

    return list(result.values())

# ── Report printer ────────────────────────────────────────────────────────────

def _print_report(report: MergeReport, label: str) -> None:
    print(f"\n{'─'*65}")
    print(f"  {label}")
    print(f"{'─'*65}")
    print(f"  INNER_HIGH  (match confiante ≥{THRESHOLD_HIGH}): {len(report.inner_high):4d}")
    print(f"  INNER_LOW   (match incerto  ≥{THRESHOLD_LOW}): {len(report.inner_low):4d}  ← requer revisão")
    print(f"  RIGHT_ONLY  (novo na planilha)              : {len(report.right_only):4d}  ← candidatos a inclusão")
    print(f"  LEFT_ONLY   (só no catálogo)                : {len(report.left_only):4d}  ← mantidos")

    if report.inner_high:
        with_delta = [i for i in report.inner_high if i["delta"]]
        print(f"\n  INNER_HIGH com diferenças ({len(with_delta)}):")
        for item in with_delta[:20]:
            cat = item["catalog"]
            rfi = item["rfi"]
            print(f"    [{item['score']:.2f}] {cat.get('codigo'):25} {cat.get('descricao','')[:35]}")
            for field, chg in item["delta"].items():
                pct = f"  Δ{chg['delta_pct']:+.1f}%" if "delta_pct" in chg else ""
                print(f"           {field}: {str(chg['catalog'])[:20]} → {str(chg['rfi'])[:20]}{pct}")
        if len(with_delta) > 20:
            print(f"    ... e mais {len(with_delta)-20} com diferenças")

    if report.inner_low:
        print(f"\n  INNER_LOW — revisar manualmente ({min(len(report.inner_low), 15)} de {len(report.inner_low)}):")
        for item in report.inner_low[:15]:
            cat = item["catalog"]
            rfi = item["rfi"]
            print(f"    [{item['score']:.2f}] CATALOGO: {cat.get('codigo'):20} {cat.get('descricao','')[:30]}")
            print(f"           RFI:      {rfi.get('codigo'):20} {rfi.get('descricao','')[:30]}")

    if report.right_only:
        print(f"\n  RIGHT_ONLY — novos na planilha ({min(len(report.right_only), 15)} de {len(report.right_only)}):")
        for item in report.right_only[:15]:
            rfi = item["rfi"]
            print(f"    {rfi.get('codigo'):25} {rfi.get('descricao','')[:40]}  [{rfi.get('unidade')}]")
        if len(report.right_only) > 15:
            print(f"    ... e mais {len(report.right_only)-15}")

# ── Main ──────────────────────────────────────────────────────────────────────

def main() -> None:
    parser = argparse.ArgumentParser(description="Merge catálogo Concilium ↔ PLANILHA PADRÃO RFI")
    parser.add_argument("--contexto", required=True, help="ID do contexto (ex: mendeslobo)")
    parser.add_argument("--apply", action="store_true", help="Aplica merge (padrão: dry-run)")
    parser.add_argument("--include-right-only", action="store_true", default=True,
                        help="Inclui RIGHT_ONLY (novos da planilha) ao catálogo")
    parser.add_argument("--export-rfi", help="Caminho para salvar catálogo extraído da RFI (JSON)")
    args = parser.parse_args()

    mode = "APPLY" if args.apply else "DRY-RUN"
    print(f"\n{'='*65}")
    print(f"  Merge Catálogo ↔ RFI [{mode}] — contexto: {args.contexto}")
    print(f"{'='*65}")

    if not XLSM.exists():
        print(f"[ERRO] Planilha não encontrada: {XLSM}", file=sys.stderr)
        sys.exit(1)

    # 1. Carrega bundle existente
    bundle_path = ROOT / f"config/catalogos/{args.contexto}/.catalog_bundle.json"
    if not bundle_path.exists():
        print(f"[ERRO] Bundle não encontrado: {bundle_path}", file=sys.stderr)
        sys.exit(1)
    bundle = json.loads(bundle_path.read_text(encoding="utf-8"))
    cat_insumos  = bundle.get("insumos", [])
    cat_producoes = bundle.get("producoes", []) or bundle.get("produtividades", [])

    print(f"\n  Catálogo atual: {len(cat_insumos)} insumos, {len(cat_producoes)} producoes")

    # 2. Extrai da planilha RFI
    print(f"  Lendo planilha: {XLSM.name} ...")
    wb = openpyxl.load_workbook(XLSM, data_only=True, keep_vba=False)
    rfi = extract_rfi(wb)
    wb.close()
    rfi_insumos   = rfi["insumos"]
    rfi_producoes = rfi["producoes"]
    print(f"  Planilha RFI:   {len(rfi_insumos)} insumos, {len(rfi_producoes)} producoes")

    if args.export_rfi:
        Path(args.export_rfi).write_text(
            json.dumps(rfi, indent=2, ensure_ascii=False), encoding="utf-8"
        )
        print(f"  RFI extraída salva em: {args.export_rfi}")

    # 3. Merge de insumos
    report_ins, _ = _merge_entities(cat_insumos, rfi_insumos)
    _print_report(report_ins, "INSUMOS")

    # 4. Merge de producoes
    report_prod, _ = _merge_entities(cat_producoes, rfi_producoes, id_key="id")
    _print_report(report_prod, "PRODUCOES")

    # 5. Resumo e decisão
    total_high_delta = sum(1 for i in report_ins.inner_high if i["delta"]) + \
                       sum(1 for i in report_prod.inner_high if i["delta"])
    total_new = len(report_ins.right_only) + len(report_prod.right_only)
    total_low = len(report_ins.inner_low) + len(report_prod.inner_low)

    print(f"\n{'='*65}")
    print(f"  RESUMO")
    print(f"{'='*65}")
    print(f"  Atualizações de preço/dados (INNER_HIGH com delta): {total_high_delta}")
    print(f"  Novos candidatos a inclusão (RIGHT_ONLY):           {total_new}")
    print(f"  Matches incertos para revisão (INNER_LOW):          {total_low}")
    print()

    if not args.apply:
        print("  Modo DRY-RUN — nenhuma alteração feita.")
        print("  Para aplicar: python tools/merge_rfi.py --contexto mendeslobo --apply")
        return

    # 6. Aplica merge
    print("  Aplicando merge...")
    new_insumos   = _apply_merge(cat_insumos, rfi_insumos, report_ins,
                                  include_right_only=args.include_right_only)
    new_producoes = _apply_merge(cat_producoes, rfi_producoes, report_prod,
                                  id_key="id", include_right_only=args.include_right_only)

    if "producoes" in bundle:
        bundle["producoes"] = new_producoes
    else:
        bundle["produtividades"] = new_producoes
    bundle["insumos"] = new_insumos

    bundle_path.write_text(json.dumps(bundle, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"  Bundle atualizado: {bundle_path}")
    print(f"  Total insumos:   {len(new_insumos)}  (era {len(cat_insumos)})")
    print(f"  Total producoes: {len(new_producoes)}  (era {len(cat_producoes)})")


if __name__ == "__main__":
    main()
