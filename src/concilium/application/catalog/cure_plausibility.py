"""
Curação cirúrgica de anomalias de plausibilidade do catálogo Concilium.

Uso:
    python -m concilium.application.catalog.cure_plausibility --contexto mendeslobo
    python -m concilium.application.catalog.cure_plausibility --contexto mendeslobo --apply

Ações automáticas:
  1. ERROS FÍSICOS
     a. preco_unitario < salário mínimo mensal → corrige via referência RFI
     b. percentual_encargos_local > 1.5 → corrige α armazenado como se fosse α-1
  2. DUPLICATAS (P#### com canônico MO-NOME)
     a. Adiciona codigo_referencia_externa ao código canônico
     b. Atualiza funcao_id nos funcoes das producoes
     c. Remove P#### do catálogo
  3. STALE com _rfi_updated_at → atualiza data_referencia_preco
  4. EQUIPAMENTO sem valor_locacao_mensal → deriva preco_unitario × horas_mes
  5. Insumos estagiário → corrige plausibility_checker (não é CLT)

Não automáticas (reportadas apenas):
  - Outliers estatísticos extremos (podem ser corretos)
  - Produções CAP sem composição (necessitam dados de campo)
  - P0058 "Sala Técnica" — erro semântico que requer redesign

Persistência (--apply): escreve nos arquivos individuais (insumos/{tipo}/{codigo}.json,
producoes|produtividades/{id}.json, templates.json) — NUNCA no .catalog_bundle.json
diretamente. Mesma lição da ADR-177 (mesclar_catalogo): escrever só no bundle cria
um fix fantasma que desaparece na próxima invalidação de cache (qualquer outra
escrita de catálogo que toque um arquivo individual depois). A próxima leitura via
Runtime.load_catalogo() reconstrói o bundle a partir dos arquivos individuais
corretos.
"""

from __future__ import annotations

import argparse
import copy
import json
import re
import sys
import unicodedata
from collections import defaultdict
from datetime import UTC, datetime
from pathlib import Path

from concilium.domain.constants import HORAS_MES_CLT as HORAS_MES_PADRAO
from concilium.domain.constants import SALARIO_MINIMO_MENSAL

from .similarity import find_candidate_duplicates

ROOT = Path(__file__).resolve().parents[4]

# ── Constantes ────────────────────────────────────────────────────────────────
# SALARIO_MINIMO_MENSAL e HORAS_MES_PADRAO vêm de domain/constants.py (fonte única —
# esse arquivo tinha valor de 2025 hardcoded e desatualizado; ver domain/constants.py:1-9).
SMM = SALARIO_MINIMO_MENSAL  # R$/mês — piso para MAO_OBRA regular

# Estagiários são isentos do SMM CLT (bolsa-auxílio, não salário)
ESTAGIARIO_KEYWORDS = {"estagi", "intern", "bolsist"}

# Preços de referência RFI para correção manual (P#### → salario_mensal_correto)
# Extraídos da planilha BD_MÃO_DE_OBRA última versão
RFI_PRECO_REFERENCIA: dict[str, float] = {
    "MO-P0001": 1830.51,  # Ajudante (P0001 na planilha)
}

# Fator CLT horista padrão como referência para α > 1.5 (α armazenado errado)
ALPHA_CLT = 1.777
ALPHA_MAX = 1.5  # se percentual_encargos_local > ALPHA_MAX → provavelmente armazenado α ao invés de α-1


# ── Helpers ───────────────────────────────────────────────────────────────────


def _now_iso() -> str:
    """Return current UTC time as ISO date string (YYYY-MM-DD)."""
    return datetime.now(UTC).strftime("%Y-%m-%d")


def _norm(text: str) -> str:
    """Normalize text for comparison.
    
    Args:
        text: Input string to normalize
    
    Returns:
        str: Normalized text (lowercase, no diacritics, single spaces)
    """
    t = unicodedata.normalize("NFD", str(text).lower())
    t = "".join(c for c in t if unicodedata.category(c) != "Mn")
    return re.sub(r"\s+", " ", t).strip()


def _is_estagiario(ins: dict) -> bool:
    """Check if insumo is an internship role.
    
    Args:
        ins: Insumo dict to check
    
    Returns:
        bool: True if matches internship keywords
    """
    desc = _norm(ins.get("descricao", ""))
    cod = _norm(ins.get("codigo", ""))
    return any(k in desc or k in cod for k in ESTAGIARIO_KEYWORDS)


def _horas_mes(ins: dict) -> float:
    """Extract horas_mes from insumo.
    
    Args:
        ins: Insumo dict
    
    Returns:
        float: Hours per month (default 176 CLT)
    """
    attrs = ins.get("atributos_especificos") or {}
    h = attrs.get("horas_mes")
    try:
        return float(h) if h else HORAS_MES_PADRAO
    except (TypeError, ValueError):
        return HORAS_MES_PADRAO


def _preco_hora(ins: dict) -> float:
    """Normaliza preco_unitario para R$/h respeitando `unidade` (mesma convenção de
    pu_calculator._acumular_custo_mo e _plausibility_checks._mo_preco_hora).

    `unidade == "h"/"hr"` → preco_unitario já é taxa horária, usa direto — NÃO divide
    por horas_mes de novo (bug: gerava falso "abaixo do mínimo" para insumos AGIS/turno).
    """
    preco = float(ins.get("preco_unitario") or 0)
    unidade = (ins.get("unidade") or "mes").strip().lower()
    if unidade in ("h", "hr"):
        return preco
    hm = _horas_mes(ins)
    return preco / hm if hm > 0 else 0.0


# ── Blob I/O por backend + resolução de caminho individual ──────────────────────


def _write_blob(catalog_root: Path, relative: str, content: bytes) -> None:
    """Write catalog blob via filesystem or remote backend (configured by catalog_storage_backend)."""
    from concilium.application.runtime.mixins._catalog_storage import (
        catalog_storage_backend,
        gravar_catalogo_blob,
    )

    if catalog_storage_backend() == "filesystem":
        dest = catalog_root / relative
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_bytes(content)
    else:
        gravar_catalogo_blob(catalog_root.parent.parent, catalog_root.name, relative, content)


def _read_blob(catalog_root: Path, relative: str) -> bytes:
    """Read catalog blob via filesystem or remote backend (configured)."""
    from concilium.application.runtime.mixins._catalog_storage import (
        catalog_storage_backend,
        ler_catalogo_blob,
    )

    if catalog_storage_backend() == "filesystem":
        return (catalog_root / relative).read_bytes()
    return ler_catalogo_blob(catalog_root.parent.parent, catalog_root.name, relative)


def _delete_blob(catalog_root: Path, relative: str) -> bool:
    """Remove catalog blob via filesystem or remote backend. Returns True if deleted."""
    from concilium.application.runtime.mixins._catalog_storage import (
        catalog_storage_backend,
        deletar_catalogo_blob,
    )

    if catalog_storage_backend() == "filesystem":
        p = catalog_root / relative
        if p.exists():
            p.unlink()
            return True
        return False
    deletar_catalogo_blob(catalog_root.parent.parent, catalog_root.name, relative)
    return True


def _caminho_insumo_individual(catalog_root: Path, tipo: str, codigo: str) -> Path:
    """Resolve path for individual insumo file (existing via rglob, or canonical new path).

    Priority: find existing insumos/{*}/{codigo}.json, else default insumos/{tipo}/{codigo}.json.
    """
    insumos_dir = catalog_root / "insumos"
    for existente in insumos_dir.rglob(f"{codigo}.json"):
        return existente
    return insumos_dir / str(tipo).lower() / f"{codigo}.json"


def _caminho_producao_individual(catalog_root: Path, producao_id: str) -> Path:
    """Resolve path for individual producao/produtividade file.

    Checks both producoes/ and produtividades/ directories (legacy coexistence),
    defaults to producoes/ for new items.
    """
    for sub in ("producoes", "produtividades"):
        candidato = catalog_root / sub / f"{producao_id}.json"
        if candidato.exists():
            return candidato
    return catalog_root / "producoes" / f"{producao_id}.json"


def _persistir_insumos_individuais(
    catalog_root: Path, insumos_originais: list[dict], insumos_finais: list[dict], removidos: set[str]
) -> tuple[int, int]:
    """Persist individual insumo files and remove deleted entries.

    Writes modified insumos to individual files (never bundle). Deletes removed files.
    Returns (count_written, count_deleted).
    """
    originais_by_code = {i["codigo"]: i for i in insumos_originais if i.get("codigo")}

    escritos = 0
    for ins in insumos_finais:
        cod = ins.get("codigo", "")
        if not cod or originais_by_code.get(cod) == ins:
            continue
        caminho = _caminho_insumo_individual(catalog_root, ins.get("tipo", ""), cod)
        _write_blob(catalog_root, str(caminho.relative_to(catalog_root)),
                    json.dumps(ins, indent=2, ensure_ascii=False).encode("utf-8"))
        escritos += 1

    removidos_ok = 0
    for cod in removidos:
        original = originais_by_code.get(cod)
        if original is None:
            continue
        caminho = _caminho_insumo_individual(catalog_root, original.get("tipo", ""), cod)
        if _delete_blob(catalog_root, str(caminho.relative_to(catalog_root))):
            removidos_ok += 1
    return escritos, removidos_ok


def _persistir_producoes_individuais(
    catalog_root: Path, producoes_originais: list[dict], producoes_finais: list[dict]
) -> int:
    """Persist individual production/productivity files. Returns count written."""
    originais_by_id = {
        p.get("id", p.get("codigo", "")): p
        for p in producoes_originais
        if p.get("id") or p.get("codigo")
    }
    escritos = 0
    for p in producoes_finais:
        pid = p.get("id") or p.get("codigo", "")
        if not pid or originais_by_id.get(pid) == p:
            continue
        caminho = _caminho_producao_individual(catalog_root, pid)
        _write_blob(catalog_root, str(caminho.relative_to(catalog_root)),
                    json.dumps(p, indent=2, ensure_ascii=False).encode("utf-8"))
        escritos += 1
    return escritos


def _cte_process_estrutura_items(
    estrutura: dict,
    dup_map: dict[str, str],
    report: CureReport,
    apply: bool,
) -> bool:
    """Update mao_de_obra funcao_id references in estrutura per dup_map.

    Returns True if any changes made (used for dirty-flag). Logs updates to report.
    """
    mudou = False
    for item in estrutura.get("mao_de_obra") or []:
        antigo = item.get("funcao_id")
        if antigo in dup_map:
            novo = dup_map[antigo]
            report.add_fixed(
                f"  templates.json [{estrutura.get('codigo', '?')}]: funcao_id {antigo} → {novo}"
            )
            if apply:
                item["funcao_id"] = novo
                mudou = True
    return mudou


def _cure_templates_estruturas_indiretas(
    catalog_root: Path, dup_map: dict[str, str], report: CureReport, apply: bool
) -> None:
    """Update funcao_id in templates.json/estruturas_indiretas per dup_map.

    Handles indirect structure references not covered by _update_producoes_funcao_ids.
    Preserves CRLF vs. LF line endings (mendeslobo convention).
    """
    if not dup_map:
        return
    try:
        original_bytes = _read_blob(catalog_root, "templates.json")
    except FileNotFoundError:
        return
    usa_crlf = b"\r\n" in original_bytes  # templates.json é CRLF no mendeslobo; insumos/producoes são LF
    data = json.loads(original_bytes.decode("utf-8"))
    estruturas = data.get("estruturas_indiretas") or []
    mudou = False
    for estrutura in estruturas:
        if _cte_process_estrutura_items(estrutura, dup_map, report, apply):
            mudou = True
    if apply and mudou:
        texto = json.dumps(data, indent=2, ensure_ascii=False)
        if usa_crlf:
            texto = texto.replace("\n", "\r\n")
        _write_blob(catalog_root, "templates.json", texto.encode("utf-8"))


class CureReport:
    """Accumulator for cure actions (fixed, manual review, skipped)."""
    def __init__(self) -> None:
        self.fixed: list[str] = []
        self.manual: list[str] = []
        self.skipped: list[str] = []

    def add_fixed(self, msg: str) -> None:
        """Log a fixed (automated correction) item."""
        self.fixed.append(msg)

    def add_manual(self, msg: str) -> None:
        """Log a manual review item (human decision required)."""
        self.manual.append(msg)

    def add_skipped(self, msg: str) -> None:
        """Log a skipped item (already correct or non-applicable)."""
        self.skipped.append(msg)


# ── 1. Erros físicos ─────────────────────────────────────────────────────────


def _cure_encargos_alpha(ins: dict, cod: str, attrs: dict, report: CureReport, apply: bool) -> None:
    """Fix percentual_encargos_local stored as α (> 1.5) instead of α-1.

    Mutates copy of attrs to avoid aliasing. See docstring above for context.
    """
    enc = attrs.get("percentual_encargos_local")
    if enc is None:
        return
    try:
        enc_f = float(enc)
        if enc_f > ALPHA_MAX:
            correto = enc_f - 1.0
            report.add_fixed(
                f"INSUMO {cod}: percentual_encargos_local {enc_f} → {correto:.3f} "
                f"(era α armazenado como enc_local; corrigido para α-1)"
            )
            if apply:
                novos_attrs = dict(attrs)
                novos_attrs["percentual_encargos_local"] = round(correto, 4)
                ins["atributos_especificos"] = novos_attrs
    except (TypeError, ValueError):
        pass


def _cure_preco_minimo(ins: dict, cod: str, report: CureReport, apply: bool) -> None:
    """Fix preco_unitario below legal minimum (ignores interns, unidade='h').

    Attempts correction via RFI reference table, else reports for manual review.
    """
    preco = float(ins.get("preco_unitario") or 0)
    preco_h = _preco_hora(ins)

    if _is_estagiario(ins) or not (0 < preco_h < (SALARIO_MINIMO_MENSAL / HORAS_MES_PADRAO) * 0.95):
        return

    # Tenta correção via referência RFI
    ref = RFI_PRECO_REFERENCIA.get(cod)
    if ref:
        report.add_fixed(
            f"INSUMO {cod}: preco_unitario {preco} → {ref} "
            f"(referência RFI; preco_h={preco_h:.2f}/h era abaixo do mínimo)"
        )
        if apply:
            ins["preco_unitario"] = ref
            ins["_cure_preco_at"] = _now_iso()
    else:
        report.add_manual(
            f"INSUMO {cod}: preco_unitario {preco} R$/mês → R${preco_h:.2f}/h "
            f"abaixo do mínimo legal (R${SALARIO_MINIMO_MENSAL / HORAS_MES_PADRAO:.2f}/h) — "
            f"sem referência RFI para correção automática"
        )


def cure_erros_fisicos(insumos: list[dict], report: CureReport, apply: bool) -> list[dict]:
    """Apply physical error corrections (encargos alpha, preco_minimo) to MAO_OBRA insumos.

    Returns modified copy if apply, else original list.
    """
    changed = [dict(i) for i in insumos]

    for ins in changed:
        cod = ins.get("codigo", "")
        tipo = ins.get("tipo", "")
        if tipo != "MAO_OBRA":
            continue

        attrs = ins.get("atributos_especificos") or {}
        _cure_encargos_alpha(ins, cod, attrs, report, apply)
        _cure_preco_minimo(ins, cod, report, apply)

    return changed if apply else insumos


# ── 2. Duplicatas P#### → MO-NOME ─────────────────────────────────────────────


def _eh_codigo_p(codigo: str) -> bool:
    """Check if codigo matches P#### or MO-P#### pattern (legacy/duplicate format)."""
    return bool(re.match(r"^(MO-P|P)\d+$", codigo))


# Faixas de razão de preço (max/min) liberadas para fusão AUTOMÁTICA — validadas
# manualmente contra o catálogo mendeslobo real nesta sessão (ADR-179):
#   ~1,0   → preço idêntico, sem ambiguidade (25 pares no mendeslobo).
#   1,9-2,2 → padrão de encargos confirmado (Sala Técnica R$24.720/R$12.000=2,06,
#             Encarregado de Drenagem R$20.600/R$10.000=2,06, etc. — 17 pares).
# Fora dessas faixas (validado: 63 pares em 1,05-1,9 com razões sistemáticas como
# 1,335/1,2/1,325 repetidas dezenas de vezes, +51 pares >2,2) a origem é
# desconhecida — pode ser o mesmo padrão de import duplicado (mesclar é seguro)
# OU duas tabelas de preço intencionalmente paralelas (mesclar apagaria dado
# válido). Usuário optou por não mesclar automaticamente até investigar a origem
# — fica em report.manual para revisão humana, não desaparece silenciosamente.
_RATIO_IDENTICO_MAX = 1.05
_RATIO_ENCARGOS_CONFIRMADO = (1.9, 2.2)


def _razao_preco_liberada_para_fusao(pa: float, pb: float) -> bool:
    """Check if price ratio between two inputs is within approved merge tolerance.

    Approved ranges: identical (≤1.05) or confirmed overhead pattern (1.9-2.2).
    """
    if pa <= 0 or pb <= 0:
        return False
    ratio = max(pa, pb) / min(pa, pb)
    if ratio <= _RATIO_IDENTICO_MAX:
        return True
    lo, hi = _RATIO_ENCARGOS_CONFIRMADO
    return lo <= ratio <= hi


def _escolher_canonico(codes: list[str], ins_by_code: dict[str, dict]) -> str:
    """Select canonical code from cluster: prefers minimum preco_unitario, then non-P#### codes.

    Deterministic ordering (sorts before min) independent of dict iteration order.
    """

    def chave(c: str) -> tuple[float, int]:
        preco = float(ins_by_code[c].get("preco_unitario") or 0)
        return (preco, 1 if _eh_codigo_p(c) else 0)

    return min(sorted(codes), key=chave)


def _process_exact_dup_groups(
    mo: list[dict],
    parent: dict[str, str],
    participantes: set[str],
) -> None:
    """Process clusters with exact match (normalized descricao + preco) via union-find."""
    def union(a: str, b: str) -> None:
        def find(x: str) -> str:
            parent.setdefault(x, x)
            while parent[x] != x:
                x = parent[x]
            return x
        ra, rb = find(a), find(b)
        if ra != rb:
            parent[ra] = rb

    grupos_exatos: dict[tuple, list[str]] = defaultdict(list)
    for ins in mo:
        key = (_norm(ins.get("descricao", "")), ins.get("preco_unitario"))
        grupos_exatos[key].append(ins["codigo"])

    for codes in grupos_exatos.values():
        if len(codes) < 2:
            continue
        participantes.update(codes)
        for c in codes[1:]:
            union(codes[0], c)


def _psc_calc_preco_ratio(pa: float, pb: float) -> float | None:
    """Calculate price ratio between two values. Returns None if either <= 0."""
    return max(pa, pb) / min(pa, pb) if pa > 0 and pb > 0 else None


def _psc_build_rejection_motivo(
    m: object,  # tipo Match do similarity module
    ratio: float | None,
) -> str:
    """Build human-readable rejection reason for insumo pair (low confidence or price out of range)."""
    if m.classificacao == "revisar":
        return f"revisar, score={m.score:.2f}"
    return (
        f"duplicata_provavel (score={m.score:.2f}) mas razão de preço "
        f"{ratio:.3f} fora das faixas validadas — origem não confirmada"
    )


def _process_similar_candidates(
    mo: list[dict],
    ins_by_code: dict[str, dict],
    parent: dict[str, str],
    participantes: set[str],
    report: CureReport | None,
) -> None:
    """Process similarity-based candidates (ADR-179) with union-find clustering.

    Merges only if price ratio within approved ranges, logs rejections to report.
    """
    def find(x: str) -> str:
        parent.setdefault(x, x)
        while parent[x] != x:
            x = parent[x]
        return x

    def union(a: str, b: str) -> None:
        ra, rb = find(a), find(b)
        if ra != rb:
            parent[ra] = rb

    for m in find_candidate_duplicates(mo):
        if m.classificacao is None:
            continue

        pa = float(ins_by_code[m.codigo_a].get("preco_unitario") or 0)
        pb = float(ins_by_code[m.codigo_b].get("preco_unitario") or 0)

        if m.classificacao == "duplicata_provavel" and _razao_preco_liberada_para_fusao(pa, pb):
            participantes.add(m.codigo_a)
            participantes.add(m.codigo_b)
            union(m.codigo_a, m.codigo_b)
        elif report is not None:
            ratio = _psc_calc_preco_ratio(pa, pb)
            motivo = _psc_build_rejection_motivo(m, ratio)
            report.add_manual(
                f"INSUMO {m.codigo_a}/{m.codigo_b}: {motivo} — "
                f"'{ins_by_code[m.codigo_a].get('descricao')}' (R${pa}) vs "
                f"'{ins_by_code[m.codigo_b].get('descricao')}' (R${pb}) — "
                "não fundido automaticamente"
            )


def _bdmfc_process_candidate(
    c: str,
    canonical: str,
    ins_by_code: dict[str, dict],
    dup_map: dict[str, str],
    report: CureReport | None,
) -> None:
    """Process single candidate against cluster canonical (price ratio validation).

    Adds to dup_map if ratio approved, else logs to report.manual.
    """
    preco_c = float(ins_by_code[c].get("preco_unitario") or 0)
    preco_canon = float(ins_by_code[canonical].get("preco_unitario") or 0)

    if _razao_preco_liberada_para_fusao(preco_c, preco_canon):
        dup_map[c] = canonical
    elif report is not None:
        ratio = (
            max(preco_c, preco_canon) / min(preco_c, preco_canon)
            if preco_c > 0 and preco_canon > 0
            else None
        )
        report.add_manual(
            f"INSUMO {c}/{canonical}: conectados via cadeia transitiva mas razão "
            f"direta {ratio:.3f} fora das faixas validadas — não fundido"
        )


def _build_dup_map_from_clusters(
    participantes: set[str],
    ins_by_code: dict[str, dict],
    parent: dict[str, str],
    report: CureReport | None,
) -> dict[str, str]:
    """Build dup_map from union-find clusters with transitive revalidation.

    Returns {codigo: canonical_code} dict for merge operation.
    """
    def find(x: str) -> str:
        parent.setdefault(x, x)
        while parent[x] != x:
            x = parent[x]
        return x

    clusters: dict[str, list[str]] = defaultdict(list)
    for code in sorted(participantes):
        clusters[find(code)].append(code)

    dup_map: dict[str, str] = {}
    for codes in clusters.values():
        if len(codes) < 2:
            continue

        canonical = _escolher_canonico(codes, ins_by_code)
        for c in codes:
            if c != canonical:
                _bdmfc_process_candidate(c, canonical, ins_by_code, dup_map, report)

    return dup_map


def _build_dup_map(insumos: list[dict], report: CureReport | None = None) -> dict[str, str]:
    """Build duplicate map from exact matches + similarity candidates (ADR-179).

    Returns {codigo: canonical_code}. Combines two sources via union-find:
    (a) Exact (normalized descricao, preco), (b) similarity score >= 0.80.
    Rejects low-confidence and transitive price mismatches to report.manual.
    """
    mo = [i for i in insumos if i.get("tipo") == "MAO_OBRA"]
    if not mo:
        return {}

    ins_by_code = {i["codigo"]: i for i in mo}
    parent: dict[str, str] = {}
    participantes: set[str] = set()

    _process_exact_dup_groups(mo, parent, participantes)
    _process_similar_candidates(mo, ins_by_code, parent, participantes, report)

    return _build_dup_map_from_clusters(participantes, ins_by_code, parent, report)


def _add_referencias_externas(
    dup_map: dict[str, str], ins_by_code: dict[str, dict], report: CureReport, apply: bool
) -> None:
    """Adiciona codigo_referencia_externa ao canônico para cada P#### duplicado."""
    for p_code, canonical in dup_map.items():
        # `canonical` sempre vem de _build_dup_map, que o extrai de `insumos`
        # (o mesmo iterável usado para montar ins_by_code acima), logo é
        # sempre uma chave presente — sem necessidade de guard defensivo.
        canon_ins = ins_by_code[canonical]
        ext = canon_ins.get("codigo_referencia_externa") or ""
        existing = [x.strip() for x in ext.split(",") if x.strip()] if ext else []
        if p_code not in existing:
            existing.append(p_code)
            report.add_fixed(f"  {canonical}: codigo_referencia_externa += '{p_code}'")
            if apply:
                canon_ins["codigo_referencia_externa"] = ", ".join(existing)


def _remove_duplicated_insumos(
    dup_map: dict[str, str], ins_by_code: dict[str, dict], report: CureReport, apply: bool
) -> list[dict]:
    """Remove P#### do índice (ou apenas reporta em dry-run)."""
    if apply:
        codigos_para_remover = set(dup_map.keys())
        new_insumos = [i for i in ins_by_code.values() if i["codigo"] not in codigos_para_remover]
        report.add_fixed(f"  Removidos {len(codigos_para_remover)} insumos duplicados")
        return new_insumos

    for p_code, canonical in list(dup_map.items())[:5]:
        report.add_fixed(f"  {p_code} → {canonical} (seria removido)")
    if len(dup_map) > 5:
        report.add_fixed(f"  ... e mais {len(dup_map) - 5} remoções")
    return []


def _update_producao_funcao_ids(
    prod: dict, dup_map: dict[str, str], report: CureReport, apply: bool
) -> tuple[dict, int]:
    """Update funcao_id references in production/productivity template per dup_map.

    Returns (updated_prod, refs_updated_count).
    """
    p = dict(prod)
    equipe = dict(p.get("composicao_padrao_equipe") or p.get("equipe") or {})
    changed_equipe = False
    refs_updated = 0
    new_funcoes = []
    for func in equipe.get("funcoes", []) or []:
        f = dict(func)
        if f.get("funcao_id") in dup_map:
            old = f["funcao_id"]
            new = dup_map[old]
            if apply:
                f["funcao_id"] = new
            refs_updated += 1
            report.add_fixed(f"  PROD {p.get('id', '?')}: funcao_id {old} → {new}")
            changed_equipe = True
        new_funcoes.append(f)
    if changed_equipe and apply:
        equipe["funcoes"] = new_funcoes
        if "composicao_padrao_equipe" in p:
            p["composicao_padrao_equipe"] = equipe
        else:
            p["equipe"] = equipe
    return p, refs_updated


def _update_producoes_funcao_ids(
    producoes: list[dict], dup_map: dict[str, str], report: CureReport, apply: bool
) -> list[dict]:
    """Update funcao_id references in all productions per dup_map.

    Returns updated_producoes (or original if not apply).
    """
    updated_prods: list[dict] = []
    refs_updated = 0
    for prod in producoes:
        p, n = _update_producao_funcao_ids(prod, dup_map, report, apply)
        refs_updated += n
        updated_prods.append(p)

    if refs_updated and not apply:
        report.add_fixed(f"  {refs_updated} referência(s) de funcao_id seriam atualizadas")

    return updated_prods


def cure_duplicatas(
    insumos: list[dict],
    producoes: list[dict],
    report: CureReport,
    apply: bool,
) -> tuple[list[dict], list[dict], dict[str, str]]:
    """Remove duplicates (exact + similarity ADR-179), merge references.

    Adds codigo_referencia_externa to canonical, updates production funcao_id refs.
    Returns (updated_insumos, updated_producoes, dup_map).
    """
    dup_map = _build_dup_map(insumos, report)

    if not dup_map:
        return insumos, producoes, dup_map

    report.add_fixed(f"Duplicatas detectadas: {len(dup_map)} → código canônico")

    ins_by_code = {i["codigo"]: dict(i) for i in insumos}
    _add_referencias_externas(dup_map, ins_by_code, report, apply)
    new_insumos = _remove_duplicated_insumos(dup_map, ins_by_code, report, apply)
    updated_prods = _update_producoes_funcao_ids(producoes, dup_map, report, apply)

    return (new_insumos if apply else insumos), (updated_prods if apply else producoes), dup_map


# ── 3. Atualiza data_referencia_preco dos itens atualizados pelo merge ─────────


def cure_stale_rfi(insumos: list[dict], report: CureReport, apply: bool) -> list[dict]:
    """Propagate RFI import dates (_rfi_updated_at, _rfi_imported_at) to data_referencia_preco.

    Returns updated_insumos (or original if not apply).
    """
    changed = [dict(i) for i in insumos]
    n = 0
    for ins in changed:
        rfi_date = ins.get("_rfi_updated_at") or ins.get("_rfi_imported_at")
        if not rfi_date:
            continue
        current = ins.get("data_referencia_preco")
        if current != rfi_date:
            n += 1
            if apply:
                ins["data_referencia_preco"] = rfi_date
    if n:
        report.add_fixed(f"STALE: {n} insumo(s) com data_referencia_preco atualizada via _rfi_updated_at/imported_at")
    return changed if apply else insumos


# ── 4. Equipment: deriva valor_locacao_mensal faltante ──────────────────────────


def _cure_locacao_mensal_item(ins: dict, report: CureReport, apply: bool) -> bool:
    """Derive valor_locacao_mensal for EQUIPAMENTO if missing (preco_unitario * horas_mes).

    Returns True if derived.
    """
    if ins.get("tipo") != "EQUIPAMENTO":
        return False
    preco_h = float(ins.get("preco_unitario") or 0)
    if preco_h <= 0:
        return False
    attrs = dict(ins.get("atributos_especificos") or {})
    if attrs.get("valor_locacao_mensal"):
        return False
    hm = float(attrs.get("horas_mes") or HORAS_MES_PADRAO)
    vlm = round(preco_h * hm, 2)
    report.add_fixed(f"INSUMO {ins['codigo']}: valor_locacao_mensal ← {preco_h} × {hm} = {vlm} R$/mês (derivado)")
    if apply:
        attrs["valor_locacao_mensal"] = vlm
        ins["atributos_especificos"] = attrs
    return True


def cure_locacao_mensal(insumos: list[dict], report: CureReport, apply: bool) -> list[dict]:
    changed = [dict(i) for i in insumos]
    n = sum(1 for ins in changed if _cure_locacao_mensal_item(ins, report, apply))
    if n == 0:
        report.add_skipped("EQUIPAMENTO: todos têm valor_locacao_mensal ou preco_unitario=0")
    return changed if apply else insumos


# ── 5. Manual: não-automatizáveis ────────────────────────────────────────────


def _report_producoes_sem_composicao(producoes: list[dict], report: CureReport) -> None:
    for prod in producoes:
        eq = prod.get("composicao_padrao_equipe") or prod.get("equipe") or {}
        if not (eq.get("funcoes") or eq.get("equipamentos")):
            pid = prod.get("id", "?")
            report.add_manual(
                f"PROD {pid}: sem composição de equipe (vh={prod.get('valor_horario')}) — dados de campo necessários"
            )


def _report_insumos_suspeitos(insumos: list[dict], report: CureReport) -> None:
    for ins in insumos:
        desc = (ins.get("descricao") or "").lower()
        if any(k in desc for k in ("sala ", "equipe ", "time ", "team ")) and ins.get("tipo") == "MAO_OBRA":
            report.add_manual(
                f"INSUMO {ins['codigo']}: '{ins.get('descricao')}' — "
                f"insumo MAO_OBRA com nome de grupo/sala; revisar modelagem"
            )


def report_manual(insumos: list[dict], producoes: list[dict], report: CureReport) -> None:
    """Log non-automatable anomalies (productions without composition, suspicious insumo names).
    """


# ── Main ──────────────────────────────────────────────────────────────────────


def main() -> None:
    """CLI entry point: Surgical catalog plausibility curation (5 correction steps).
    
    Steps: (1) Physical errors, (2) Duplicates, (3) Stale RFI dates, (4) Equipment rental,
    (5) Manual review items. Dry-run by default, --apply to persist.
    """
    parser = argparse.ArgumentParser(description="Curação cirúrgica de plausibilidade do catálogo")
    parser.add_argument("--contexto", required=True, help="ID do contexto (ex: mendeslobo)")
    parser.add_argument("--apply", action="store_true", help="Aplica correções (padrão: dry-run)")
    args = parser.parse_args()

    mode = "APPLY" if args.apply else "DRY-RUN"
    print(f"\n{'=' * 65}")
    print(f"  Curação de Plausibilidade [{mode}] — contexto: {args.contexto}")
    print(f"{'=' * 65}\n")

    catalog_root = ROOT / f"config/catalogos/{args.contexto}"

    from concilium.application.runtime.mixins._catalog_storage import (
        catalog_storage_backend,
        invalidar_catalogo_cache,
        load_catalogo_via_storage,
    )
    backend = catalog_storage_backend()

    # Bundle é a fonte de leitura — nunca escrita (ver docstring do módulo).
    if backend == "filesystem":
        bundle_path = catalog_root / ".catalog_bundle.json"
        if not bundle_path.exists():
            print(f"Bundle não encontrado: {bundle_path}", file=sys.stderr)
            sys.exit(1)
        bundle = json.loads(bundle_path.read_text(encoding="utf-8"))
    else:
        remote_cache = catalog_root / ".catalog_bundle_remote.json"
        if remote_cache.exists():
            bundle = json.loads(remote_cache.read_text(encoding="utf-8"))
        else:
            print(f"  Carregando catálogo de backend {backend!r} ...")
            bundle = load_catalogo_via_storage(catalog_root.parent.parent, catalog_root.name, force_refresh=True)
    # deepcopy: alguns cure_* mutam atributos_especificos por referência (achado
    # real, MO-OPERADOR-DE-MOTOSCRA) — sem isso, o snapshot "original" usado pra
    # diff em _persistir_insumos_individuais seria corrompido de volta, e o fix
    # nunca chegaria a disco (comparação vê "nada mudou").
    insumos_originais = copy.deepcopy(bundle.get("insumos", []))
    producoes_originais = copy.deepcopy(bundle.get("producoes", []) or bundle.get("produtividades", []))

    report = CureReport()
    insumos, producoes = _run_cure_steps(catalog_root, insumos_originais, producoes_originais, report, args.apply)
    _print_cure_report(report, args.apply)

    if args.apply:
        _persistir_e_validar(catalog_root, insumos_originais, insumos, producoes_originais, producoes)
        invalidar_catalogo_cache(catalog_root.parent.parent, catalog_root.name)
    else:
        print("\n  Dry-run — use --apply para aplicar as correções")
        sys.exit(1 if report.manual else 0)


def _run_cure_steps(
    catalog_root: Path, insumos: list[dict], producoes: list[dict], report: CureReport, apply: bool
) -> tuple[list[dict], list[dict]]:
    """Execute all 5 cure steps (physical errors, duplicates, stale dates, equipment, manual).
    
    Returns (updated_insumos, updated_producoes).
    """
    insumos = cure_erros_fisicos(insumos, report, apply)

    print("[2/5] Duplicatas (P#### → MO-NOME) ...")
    insumos, producoes, dup_map = cure_duplicatas(insumos, producoes, report, apply)
    _cure_templates_estruturas_indiretas(catalog_root, dup_map, report, apply)

    print("[3/5] Datas desatualizadas via merge RFI ...")
    insumos = cure_stale_rfi(insumos, report, apply)

    print("[4/5] Equipamento sem valor_locacao_mensal ...")
    insumos = cure_locacao_mensal(insumos, report, apply)

    print("[5/5] Itens não-automatizáveis ...")
    report_manual(insumos, producoes, report)

    return insumos, producoes


def _print_cure_report(report: CureReport, apply: bool) -> None:
    """Print formatted cure report (fixed, manual, skipped items).
    """
    print(f"  Correções automáticas: {len(report.fixed)}")
    print(f"  Intervenção manual:    {len(report.manual)}")
    print()
    for msg in report.fixed:
        prefix = "  ✓" if apply else "  →"
        print(f"{prefix} {msg}")
    if report.manual:
        print("\n  Intervenção manual necessária:")
        for msg in report.manual:
            print(f"  ⚠ {msg}")
    if report.skipped:
        for msg in report.skipped:
            print(f"  · {msg}")


def _persistir_e_validar(
    catalog_root: Path,
    insumos_originais: list[dict],
    insumos: list[dict],
    producoes_originais: list[dict],
    producoes: list[dict],
) -> None:
    """Escreve nos arquivos individuais (nunca no .catalog_bundle.json — ver
    docstring do módulo, mesma lição da ADR-177). Detecta remoção por diferença
    de conjunto de códigos entre original e final (funciona independente de qual
    etapa de cura removeu — não depende de receber dup_map aqui)."""
    codigos_originais = {i["codigo"] for i in insumos_originais if i.get("codigo")}
    codigos_finais = {i["codigo"] for i in insumos if i.get("codigo")}
    removidos = codigos_originais - codigos_finais

    escritos, removidos_ok = _persistir_insumos_individuais(catalog_root, insumos_originais, insumos, removidos)
    escritos_prod = _persistir_producoes_individuais(catalog_root, producoes_originais, producoes)

    print(f"\n  Arquivos individuais persistidos em: {catalog_root}")
    print(f"  Insumos escritos/atualizados: {escritos}  |  removidos: {removidos_ok}  |  producoes: {escritos_prod}")

    # Valida plausibilidade pós-curação (em memória — não depende do bundle em disco)
    from concilium.application.catalog.plausibility_checker import verificar_plausibilidade

    pos = verificar_plausibilidade(insumos, producoes)
    r = pos["resumo"]
    print(f"\n  Pós-curação: {r['erros']} erros | {r['avisos']} avisos | {r['infos']} infos")
    if r["erros"] == 0:
        print("  Status: OK — nenhum erro crítico residual")
    else:
        print("  Status: ATENÇÃO — erros residuais precisam de revisão manual")


if __name__ == "__main__":
    main()
