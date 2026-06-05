#!/usr/bin/env python3
"""
price_resolver.py — Stage 2 do Pipeline ADR-045

Resolve preços de insumos usando SICRO/SINAPI/ANP e injeta no catálogo Concilium.
Gera/atualiza `config/referencias/price_source_policy.yaml` e `relatorio_cobertura.json`.

Uso:
    python scripts/price_resolver.py --uf CE --dry-run
    python scripts/price_resolver.py --uf CE --apply
    python scripts/price_resolver.py --uf CE --auto-map --apply   # gera mapeamento automático
    python scripts/price_resolver.py --uf CE --relatorio-apenas
"""
from __future__ import annotations

import argparse
import io
import json
import re
import sys
import unicodedata
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

try:
    import yaml
except ImportError:
    yaml = None  # type: ignore

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace")

ROOT = Path(__file__).resolve().parents[1]

# ── Thresholds ────────────────────────────────────────────────────────────────
MATCH_THRESHOLD_HIGH   = 0.72   # aceita automaticamente
MATCH_THRESHOLD_LOW    = 0.50   # propõe para revisão
VARIACAO_MAX_PCT       = 40.0   # suspende atualização se variação > 40%
VARIACAO_AVISO_PCT     = 15.0   # registra conflito se variação > 15%

# ── Normalização de texto ─────────────────────────────────────────────────────
_STOP = {"de", "do", "da", "dos", "das", "e", "a", "o", "em", "com", "para", "por",
         "com", "sem", "sobre", "tipo", "modelo", "ref", "referencia"}
_ABBREV = {
    "cam":  "caminhao", "basculante": "basculante",
    "escav": "escavadora", "hidraul": "hidraulica",
    "motoniveladora": "motoniveladora", "motonivel": "motoniveladora",
    "rolo":  "rolo", "compac": "compactador", "comp": "compactador",
    "trator": "trator", "esteiras": "esteiras", "pneus": "pneus",
    "bulldozer": "bulldozer", "retro": "retroescavadeira",
    "vibroacab": "vibroacabadora", "asfalto": "asfalto",
    "compressor": "compressor", "guindaste": "guindaste",
    "ajudante": "ajudante", "operador": "operador",
    "motorista": "motorista", "encarregado": "encarregado",
    "engenheiro": "engenheiro", "tecnico": "tecnico",
    "areia": "areia", "brita": "brita", "cimento": "cimento",
    "aco": "aco", "tubo": "tubo", "pvc": "pvc",
    "diesel": "diesel", "oleo": "oleo", "combustivel": "combustivel",
    "m3": "m3", "m2": "m2", "t": "tonelada",
}

def _norm(text: str) -> set[str]:
    t = unicodedata.normalize("NFD", str(text).lower())
    t = "".join(c for c in t if unicodedata.category(c) != "Mn")
    t = re.sub(r"[^a-z0-9\s]", " ", t)
    tokens = {w for w in t.split() if w not in _STOP and len(w) > 1}
    expanded: set[str] = set()
    for tok in tokens:
        exp = _ABBREV.get(tok, tok)
        if exp == tok:
            expanded.add(tok)
        else:
            expanded.update(w for w in exp.split() if w not in _STOP and len(w) > 1)
    return expanded

def _jaccard(a: str, b: str) -> float:
    ta, tb = _norm(a), _norm(b)
    if not ta or not tb:
        return 0.0
    return len(ta & tb) / len(ta | tb)

def _norm_unit(u: str | None) -> str:
    if not u: return ""
    return u.strip().lower().replace("³", "3").replace("²", "2")

# ── Estruturas ────────────────────────────────────────────────────────────────
@dataclass
class MatchResult:
    cat_codigo: str
    cat_descricao: str
    cat_tipo: str
    cat_preco_atual: float
    cat_unidade: str
    sicro_codigo: str
    sicro_descricao: str
    sicro_preco: float
    sicro_unidade: str
    score: float
    variacao_pct: float
    status: str  # OK | AVISO | SUSPENSO | UNIDADE_DIVERGENTE

@dataclass
class CoverageReport:
    uf: str
    data_referencia: str
    executado_em: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    atualizados: list[dict] = field(default_factory=list)
    suspensos:   list[dict] = field(default_factory=list)
    conflitos:   list[dict] = field(default_factory=list)
    sem_match:   list[dict] = field(default_factory=list)
    unidade_div: list[dict] = field(default_factory=list)
    novos_mapeamentos: list[dict] = field(default_factory=list)

    def resumo(self) -> dict:
        return {
            "atualizados":        len(self.atualizados),
            "suspensos":          len(self.suspensos),
            "conflitos":          len(self.conflitos),
            "sem_match":          len(self.sem_match),
            "unidade_divergente": len(self.unidade_div),
            "novos_mapeamentos":  len(self.novos_mapeamentos),
        }


# ── Carregamento de dados ─────────────────────────────────────────────────────

def _load_sicro(uf: str) -> list[dict]:
    path = ROOT / f"config/referencias/SICRO/BR-{uf}/insumos.json"
    if not path.exists():
        print(f"  [AVISO] SICRO BR-{uf} não encontrado: {path}", file=sys.stderr)
        return []
    data = json.loads(path.read_text(encoding="utf-8"))
    return data.get("insumos", [])

def _load_anp(uf: str) -> dict | None:
    path = ROOT / f"config/referencias/ANP/BR-{uf}/diesel.json"
    if path.exists():
        return json.loads(path.read_text(encoding="utf-8"))
    return None

def _load_policy(path: Path) -> list[dict]:
    """Carrega price_source_policy.yaml ou retorna lista vazia."""
    if not path.exists():
        return []
    if yaml is None:
        # Fallback: lê como JSON se possível
        return []
    with path.open(encoding="utf-8") as f:
        doc = yaml.safe_load(f) or {}
    return doc.get("mappings", [])

def _policy_index(mappings: list[dict]) -> dict[str, dict]:
    return {m["concilium_id"]: m for m in mappings if m.get("concilium_id")}


# ── Matcher SICRO ↔ Catálogo ──────────────────────────────────────────────────

def _best_sicro_match(
    cat_ins: dict,
    sicro_ins: list[dict],
    tipo: str,
) -> tuple[dict | None, float]:
    """Retorna (sicro_item, score) com melhor match por Jaccard."""
    cat_desc = cat_ins.get("descricao", "")
    best_item, best_score = None, 0.0
    for s in sicro_ins:
        if s.get("tipo") != tipo:
            continue
        score = _jaccard(cat_desc, s.get("descricao", ""))
        if score > best_score:
            best_score = score
            best_item = s
    return best_item, best_score


def _resolve_preco(cat_ins: dict, sicro_item: dict, tipo: str) -> tuple[float, str]:
    """Extrai o preço relevante do item SICRO conforme o tipo."""
    if tipo == "EQUIPAMENTO":
        return float(sicro_item.get("custo_produtivo") or 0), "h"
    elif tipo == "MAO_OBRA":
        return float(sicro_item.get("preco_publicado") or 0), "h"
    else:  # MATERIAL
        return float(sicro_item.get("preco_publicado") or 0), \
               str(sicro_item.get("unidade") or "un")


# ── Processamento principal ────────────────────────────────────────────────────

def resolve(
    uf: str,
    contexto_id: str,
    auto_map: bool,
    apply: bool,
    relatorio_apenas: bool,
) -> CoverageReport:
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    report = CoverageReport(uf=uf, data_referencia=today)

    # Carrega dados
    bundle_path = ROOT / f"config/catalogos/{contexto_id}/.catalog_bundle.json"
    if not bundle_path.exists():
        print(f"Bundle não encontrado: {bundle_path}", file=sys.stderr)
        sys.exit(1)
    bundle    = json.loads(bundle_path.read_text(encoding="utf-8"))
    insumos   = bundle.get("insumos", [])
    ins_idx   = {i["codigo"]: i for i in insumos if i.get("codigo")}

    sicro_data = _load_sicro(uf)
    anp_data   = _load_anp(uf)

    policy_path = ROOT / "config/referencias/price_source_policy.yaml"
    policy_list = _load_policy(policy_path)
    policy_idx  = _policy_index(policy_list)

    stale  = [i for i in insumos if (i.get("data_referencia_preco") or "") <= "2025-12-31"]
    print(f"\n  Insumos stale (≤ 2025-12-31): {len(stale)}")
    print(f"  SICRO BR-{uf}: {len(sicro_data)} itens")

    new_mappings: list[dict] = []

    for cat_ins in stale:
        cod  = cat_ins.get("codigo", "")
        tipo = cat_ins.get("tipo", "")
        if tipo not in ("EQUIPAMENTO", "MAO_OBRA", "MATERIAL"):
            continue

        # 1. Verifica mapeamento explícito
        policy = policy_idx.get(cod)
        if policy:
            sicro_cod = policy.get("sicro_codigo")
            sicro_item = next((s for s in sicro_data if s.get("codigo_referencia") == sicro_cod), None)
            score = 1.0
        elif auto_map:
            sicro_item, score = _best_sicro_match(cat_ins, sicro_data, tipo)
            if score < MATCH_THRESHOLD_LOW:
                report.sem_match.append({
                    "concilium_id": cod,
                    "descricao": cat_ins.get("descricao", ""),
                    "tipo": tipo,
                    "melhor_score": round(score, 3),
                })
                continue
        else:
            report.sem_match.append({"concilium_id": cod, "descricao": cat_ins.get("descricao", ""), "tipo": tipo})
            continue

        if sicro_item is None:
            report.sem_match.append({"concilium_id": cod, "motivo": "sicro_item_nao_encontrado"})
            continue

        sicro_preco, sicro_unidade = _resolve_preco(cat_ins, sicro_item, tipo)
        if sicro_preco <= 0:
            continue

        cat_preco   = float(cat_ins.get("preco_unitario") or 0)
        cat_unidade = _norm_unit(cat_ins.get("unidade"))

        # Verifica compatibilidade de unidade
        if tipo != "MAO_OBRA":  # MAO_OBRA: SICRO=h, Cat=mes — divergência esperada
            if _norm_unit(sicro_unidade) != cat_unidade and cat_unidade not in ("h", ""):
                report.unidade_div.append({
                    "concilium_id": cod, "unidade_cat": cat_unidade, "unidade_sicro": sicro_unidade,
                })
                continue

        # Variação
        variacao_pct = abs(sicro_preco - cat_preco) / cat_preco * 100 if cat_preco > 0 else 0

        # Para MAO_OBRA: só injeta em regionalizacao (não atualiza preco_unitario)
        # Para EQ/MAT: atualiza preco_unitario quando mesma unidade
        atualiza_base = tipo in ("EQUIPAMENTO", "MATERIAL")

        if variacao_pct > VARIACAO_MAX_PCT and atualiza_base:
            report.suspensos.append({
                "concilium_id": cod, "preco_atual": cat_preco, "preco_sicro": sicro_preco,
                "variacao_pct": round(variacao_pct, 1),
                "descricao": cat_ins.get("descricao", "")[:50],
            })
            continue

        if variacao_pct > VARIACAO_AVISO_PCT:
            report.conflitos.append({
                "concilium_id": cod, "preco_atual": cat_preco, "preco_sicro": sicro_preco,
                "variacao_pct": round(variacao_pct, 1), "score": round(score, 3),
            })

        # Registra mapeamento novo
        if auto_map and not policy:
            new_entry = {
                "concilium_id": cod,
                "descricao": cat_ins.get("descricao", ""),
                "tipo": tipo,
                "sicro_codigo": sicro_item.get("codigo_referencia"),
                "sicro_descricao": sicro_item.get("descricao", ""),
                "score_match": round(score, 3),
                "status": "auto" if score >= MATCH_THRESHOLD_HIGH else "revisar",
            }
            new_mappings.append(new_entry)
            report.novos_mapeamentos.append(new_entry)

        # Aplica
        if apply and not relatorio_apenas:
            ins = ins_idx.get(cod)
            if ins is None:
                continue

            # regionalizacao → dict format (ADR-045 D4)
            regz = ins.get("regionalizacao")
            if isinstance(regz, list):
                regz_dict = {r.get("jurisdicao_id", "?"): r for r in regz}
            elif isinstance(regz, dict):
                regz_dict = regz
            else:
                regz_dict = {}

            regz_dict[f"BR-{uf}"] = {
                "preco": round(sicro_preco, 4),
                "fonte_provedor": "SICRO",
                "fonte_codigo_externo": sicro_item.get("codigo_referencia"),
                "data_referencia": sicro_data[0].get("data_vigencia", "2026-01-01") if sicro_data else today,
                "versao_tabela": "2026-01",
                "conflito_detectado": variacao_pct > VARIACAO_AVISO_PCT,
                "atualizado_em": datetime.now(timezone.utc).isoformat(),
            }
            ins["regionalizacao"] = regz_dict

            if atualiza_base and score >= MATCH_THRESHOLD_HIGH:
                ins["preco_unitario"]       = round(sicro_preco, 4)
                ins["data_referencia_preco"] = sicro_data[0].get("data_vigencia", today)[:10] if sicro_data else today
                ins["fonte_preco"]           = "tabela_referencia"

        report.atualizados.append({
            "concilium_id": cod,
            "sicro_codigo": sicro_item.get("codigo_referencia"),
            "preco_anterior": cat_preco,
            "preco_novo": round(sicro_preco, 4),
            "variacao_pct": round(variacao_pct, 1),
            "score": round(score, 3),
            "atualiza_base": atualiza_base,
        })

    # Diesel via ANP
    diesel_cod = "MA-DIESEL-S10"
    if anp_data and diesel_cod in ins_idx:
        preco_anp = None
        for comb in anp_data.get("combustiveis", []):
            if comb.get("produto") == "DIESEL_S10":
                preco_anp = comb.get("preco_medio_ponderado")
                break
        if preco_anp:
            ins = ins_idx[diesel_cod]
            if apply and not relatorio_apenas:
                ins["preco_unitario"]        = round(preco_anp, 4)
                ins["data_referencia_preco"] = anp_data.get("data_vigencia", today)[:10]
                ins["fonte_preco"]           = "cotacao_mercado"
                regz = ins.get("regionalizacao") or {}
                if isinstance(regz, list):
                    regz = {r.get("jurisdicao_id", "?"): r for r in regz}
                regz[f"BR-{uf}"] = {
                    "preco": round(preco_anp, 4),
                    "fonte_provedor": "ANP",
                    "data_referencia": anp_data.get("data_vigencia", today),
                    "versao_tabela": anp_data.get("versao", "?"),
                    "atualizado_em": datetime.now(timezone.utc).isoformat(),
                }
                ins["regionalizacao"] = regz
            report.atualizados.append({
                "concilium_id": diesel_cod, "fonte": "ANP",
                "preco_novo": round(preco_anp, 4),
            })
            print(f"  [ANP] {diesel_cod}: R${preco_anp:.4f}/L")

    # Salva bundle
    if apply and not relatorio_apenas:
        bundle_path.write_text(json.dumps(bundle, indent=2, ensure_ascii=False), encoding="utf-8")
        print(f"\n  Bundle atualizado: {bundle_path}")

    # Salva novos mapeamentos no policy file
    if new_mappings and (apply or relatorio_apenas):
        _save_new_mappings(policy_path, new_mappings)

    # Relatório de cobertura
    cov_dir = ROOT / "config/referencias/pesquisas/logs"
    cov_dir.mkdir(parents=True, exist_ok=True)
    cov_path = cov_dir / f"cobertura_{uf}_{today}.json"
    cov_data = {
        "uf": uf, "data_referencia": today, "executado_em": report.executado_em,
        "modo": "APPLY" if apply else "DRY_RUN",
        "resumo": report.resumo(),
        "atualizados":  report.atualizados[:50],
        "suspensos":    report.suspensos,
        "conflitos":    report.conflitos,
        "sem_match":    report.sem_match[:30],
        "unidade_div":  report.unidade_div,
        "novos_mapeamentos": report.novos_mapeamentos[:100],
    }
    cov_path.write_text(json.dumps(cov_data, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"  Relatório salvo: {cov_path}")

    return report


def _save_new_mappings(policy_path: Path, new_mappings: list[dict]) -> None:
    """Anexa novos mapeamentos ao price_source_policy.yaml (ou cria o arquivo)."""
    if yaml is None:
        # Fallback: salva como JSON
        fallback = policy_path.with_suffix(".json")
        existing = json.loads(fallback.read_text(encoding="utf-8")) if fallback.exists() else {"mappings": []}
        codes = {m["concilium_id"] for m in existing["mappings"]}
        existing["mappings"] += [m for m in new_mappings if m["concilium_id"] not in codes]
        fallback.write_text(json.dumps(existing, indent=2, ensure_ascii=False), encoding="utf-8")
        print(f"  Mapeamentos salvos (JSON): {fallback}")
        return

    existing = []
    if policy_path.exists():
        with policy_path.open(encoding="utf-8") as f:
            doc = yaml.safe_load(f) or {}
        existing = doc.get("mappings", [])

    codes = {m["concilium_id"] for m in existing}
    added = [m for m in new_mappings if m["concilium_id"] not in codes]
    all_mappings = existing + added

    policy_path.parent.mkdir(parents=True, exist_ok=True)
    with policy_path.open("w", encoding="utf-8") as f:
        yaml.dump(
            {"meta": {"versao": "2.0", "atualizado_em": datetime.now(timezone.utc).strftime("%Y-%m-%d")},
             "mappings": all_mappings},
            f, allow_unicode=True, sort_keys=False, default_flow_style=False,
        )
    print(f"  Mapeamentos salvos: {policy_path} ({len(added)} novos)")


# ── Main ──────────────────────────────────────────────────────────────────────

def main() -> None:
    p = argparse.ArgumentParser(description="ADR-045 Stage 2: Resolve e injeta preços no catálogo")
    p.add_argument("--uf",       required=True, help="UF (ex: CE)")
    p.add_argument("--contexto", default="mendeslobo", help="ID do contexto")
    p.add_argument("--apply",    action="store_true", help="Aplica (padrão: dry-run)")
    p.add_argument("--auto-map", action="store_true", dest="auto_map",
                   help="Gera mapeamento automático por similaridade de descrição")
    p.add_argument("--relatorio-apenas", action="store_true", dest="relatorio_apenas",
                   help="Apenas gera relatório, sem atualizar bundle")
    args = p.parse_args()

    mode = "APPLY" if args.apply else "DRY-RUN"
    print(f"\n{'='*60}")
    print(f"  price_resolver [{mode}] — UF: {args.uf}, contexto: {args.contexto}")
    if args.auto_map:
        print(f"  AUTO-MAP habilitado (threshold={MATCH_THRESHOLD_HIGH})")
    print(f"{'='*60}")

    report = resolve(
        uf=args.uf,
        contexto_id=args.contexto,
        auto_map=args.auto_map,
        apply=args.apply,
        relatorio_apenas=args.relatorio_apenas,
    )

    print(f"\n  Resumo:")
    for k, v in report.resumo().items():
        print(f"    {k:<25}: {v}")

    if report.suspensos:
        print(f"\n  SUSPENSOS (variação > {VARIACAO_MAX_PCT}%):")
        for s in report.suspensos:
            print(f"    {s['concilium_id']}: {s['preco_atual']} → {s['preco_sicro']} ({s['variacao_pct']:+.1f}%)")

    if not args.apply:
        print(f"\n  Dry-run — use --apply para aplicar")


if __name__ == "__main__":
    main()
