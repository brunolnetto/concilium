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
"""

from __future__ import annotations

import argparse
import json
import re
import sys
import unicodedata
from collections import defaultdict
from datetime import UTC, datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[4]

# ── Constantes ────────────────────────────────────────────────────────────────
SALARIO_MINIMO_MENSAL = 1_518.0  # R$ Brasil 2025
HORAS_MES_PADRAO = 220.0
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
    return datetime.now(UTC).strftime("%Y-%m-%d")


def _norm(text: str) -> str:
    t = unicodedata.normalize("NFD", str(text).lower())
    t = "".join(c for c in t if unicodedata.category(c) != "Mn")
    return re.sub(r"\s+", " ", t).strip()


def _is_estagiario(ins: dict) -> bool:
    desc = _norm(ins.get("descricao", ""))
    cod = _norm(ins.get("codigo", ""))
    return any(k in desc or k in cod for k in ESTAGIARIO_KEYWORDS)


def _horas_mes(ins: dict) -> float:
    attrs = ins.get("atributos_especificos") or {}
    h = attrs.get("horas_mes")
    try:
        return float(h) if h else HORAS_MES_PADRAO
    except (TypeError, ValueError):
        return HORAS_MES_PADRAO


class CureReport:
    def __init__(self) -> None:
        self.fixed: list[str] = []
        self.manual: list[str] = []
        self.skipped: list[str] = []

    def add_fixed(self, msg: str) -> None:
        self.fixed.append(msg)

    def add_manual(self, msg: str) -> None:
        self.manual.append(msg)

    def add_skipped(self, msg: str) -> None:
        self.skipped.append(msg)


# ── 1. Erros físicos ─────────────────────────────────────────────────────────


def cure_erros_fisicos(insumos: list[dict], report: CureReport, apply: bool) -> list[dict]:
    changed = [dict(i) for i in insumos]

    for ins in changed:
        cod = ins.get("codigo", "")
        tipo = ins.get("tipo", "")
        if tipo != "MAO_OBRA":
            continue

        attrs = ins.get("atributos_especificos") or {}

        # a) percentual_encargos_local armazenado como α (> 1.5) em vez de α-1
        enc = attrs.get("percentual_encargos_local")
        if enc is not None:
            try:
                enc_f = float(enc)
                if enc_f > ALPHA_MAX:
                    correto = enc_f - 1.0
                    report.add_fixed(
                        f"INSUMO {cod}: percentual_encargos_local {enc_f} → {correto:.3f} "
                        f"(era α armazenado como enc_local; corrigido para α-1)"
                    )
                    if apply:
                        attrs["percentual_encargos_local"] = round(correto, 4)
                        ins["atributos_especificos"] = attrs
            except (TypeError, ValueError):
                pass

        # b) preco_unitario abaixo do mínimo mensal (ignora estagiários)
        preco = float(ins.get("preco_unitario") or 0)
        hm = _horas_mes(ins)
        preco_h = preco / hm if hm > 0 else 0

        if not _is_estagiario(ins) and 0 < preco_h < (SALARIO_MINIMO_MENSAL / HORAS_MES_PADRAO) * 0.95:
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

    return changed if apply else insumos


# ── 2. Duplicatas P#### → MO-NOME ─────────────────────────────────────────────


def _build_dup_map(insumos: list[dict]) -> dict[str, str]:
    """Retorna {p_code: canonical_code} para todos os duplicados detectados."""
    grupos: dict[tuple, list[str]] = defaultdict(list)
    for ins in insumos:
        if ins.get("tipo") != "MAO_OBRA":
            continue
        key = (_norm(ins.get("descricao", "")), ins.get("preco_unitario"))
        grupos[key].append(ins["codigo"])

    dup_map: dict[str, str] = {}
    for codes in grupos.values():
        if len(codes) < 2:
            continue
        # Canônico: prefere MO-NOME (não começa com P ou MO-P)
        canonical = next((c for c in codes if not re.match(r"^(MO-P|P)\d+$", c)), codes[0])
        for c in codes:
            if c != canonical:
                dup_map[c] = canonical
    return dup_map


def cure_duplicatas(
    insumos: list[dict],
    producoes: list[dict],
    report: CureReport,
    apply: bool,
) -> tuple[list[dict], list[dict]]:
    """Remove P#### duplicados, adiciona codigo_referencia_externa, atualiza producoes."""
    dup_map = _build_dup_map(insumos)

    if not dup_map:
        return insumos, producoes

    report.add_fixed(f"Duplicatas detectadas: {len(dup_map)} P#### → MO-NOME")

    # Adiciona codigo_referencia_externa ao canônico
    ins_by_code = {i["codigo"]: dict(i) for i in insumos}
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

    # Remove P#### do índice
    if apply:
        codigos_para_remover = set(dup_map.keys())
        new_insumos = [i for i in ins_by_code.values() if i["codigo"] not in codigos_para_remover]
        report.add_fixed(f"  Removidos {len(codigos_para_remover)} insumos duplicados")
    else:
        for p_code, canonical in list(dup_map.items())[:5]:
            report.add_fixed(f"  {p_code} → {canonical} (seria removido)")
        if len(dup_map) > 5:
            report.add_fixed(f"  ... e mais {len(dup_map) - 5} remoções")
        new_insumos = insumos

    # Atualiza funcao_id nas producoes
    updated_prods: list[dict] = []
    refs_updated = 0
    for prod in producoes:
        p = dict(prod)
        equipe = dict(p.get("composicao_padrao_equipe") or p.get("equipe") or {})
        changed_equipe = False
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
        updated_prods.append(p)

    if refs_updated and not apply:
        report.add_fixed(f"  {refs_updated} referência(s) de funcao_id seriam atualizadas")

    return (new_insumos if apply else insumos), (updated_prods if apply else producoes)


# ── 3. Atualiza data_referencia_preco dos itens atualizados pelo merge ─────────


def cure_stale_rfi(insumos: list[dict], report: CureReport, apply: bool) -> list[dict]:
    """Para insumos com _rfi_updated_at ou _rfi_imported_at, propaga a data ao campo oficial."""
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


def cure_locacao_mensal(insumos: list[dict], report: CureReport, apply: bool) -> list[dict]:
    changed = [dict(i) for i in insumos]
    n = 0
    for ins in changed:
        if ins.get("tipo") != "EQUIPAMENTO":
            continue
        preco_h = float(ins.get("preco_unitario") or 0)
        if preco_h <= 0:
            continue
        attrs = dict(ins.get("atributos_especificos") or {})
        if attrs.get("valor_locacao_mensal"):
            continue
        hm = float(attrs.get("horas_mes") or HORAS_MES_PADRAO)
        vlm = round(preco_h * hm, 2)
        n += 1
        report.add_fixed(f"INSUMO {ins['codigo']}: valor_locacao_mensal ← {preco_h} × {hm} = {vlm} R$/mês (derivado)")
        if apply:
            attrs["valor_locacao_mensal"] = vlm
            ins["atributos_especificos"] = attrs
    if n == 0:
        report.add_skipped("EQUIPAMENTO: todos têm valor_locacao_mensal ou preco_unitario=0")
    return changed if apply else insumos


# ── 5. Manual: não-automatizáveis ────────────────────────────────────────────


def report_manual(insumos: list[dict], producoes: list[dict], report: CureReport) -> None:
    # Produções sem composição
    for prod in producoes:
        eq = prod.get("composicao_padrao_equipe") or prod.get("equipe") or {}
        if not (eq.get("funcoes") or eq.get("equipamentos")):
            pid = prod.get("id", "?")
            report.add_manual(
                f"PROD {pid}: sem composição de equipe (vh={prod.get('valor_horario')}) — dados de campo necessários"
            )

    # Insumos semanticamente suspeitos
    for ins in insumos:
        desc = (ins.get("descricao") or "").lower()
        if any(k in desc for k in ("sala ", "equipe ", "time ", "team ")):
            if ins.get("tipo") == "MAO_OBRA":
                report.add_manual(
                    f"INSUMO {ins['codigo']}: '{ins.get('descricao')}' — "
                    f"insumo MAO_OBRA com nome de grupo/sala; revisar modelagem"
                )


# ── Main ──────────────────────────────────────────────────────────────────────


def main() -> None:
    parser = argparse.ArgumentParser(description="Curação cirúrgica de plausibilidade do catálogo")
    parser.add_argument("--contexto", required=True, help="ID do contexto (ex: mendeslobo)")
    parser.add_argument("--apply", action="store_true", help="Aplica correções (padrão: dry-run)")
    args = parser.parse_args()

    mode = "APPLY" if args.apply else "DRY-RUN"
    print(f"\n{'=' * 65}")
    print(f"  Curação de Plausibilidade [{mode}] — contexto: {args.contexto}")
    print(f"{'=' * 65}\n")

    bundle_path = ROOT / f"config/catalogos/{args.contexto}/.catalog_bundle.json"
    if not bundle_path.exists():
        print(f"Bundle não encontrado: {bundle_path}", file=sys.stderr)
        sys.exit(1)

    bundle = json.loads(bundle_path.read_text(encoding="utf-8"))
    insumos = bundle.get("insumos", [])
    producoes = bundle.get("producoes", []) or bundle.get("produtividades", [])

    report = CureReport()

    # Etapas de curação
    print("[1/5] Erros físicos (encargos + salário mínimo) ...")
    insumos = cure_erros_fisicos(insumos, report, args.apply)

    print("[2/5] Duplicatas (P#### → MO-NOME) ...")
    insumos, producoes = cure_duplicatas(insumos, producoes, report, args.apply)

    print("[3/5] Datas desatualizadas via merge RFI ...")
    insumos = cure_stale_rfi(insumos, report, args.apply)

    print("[4/5] Equipamento sem valor_locacao_mensal ...")
    insumos = cure_locacao_mensal(insumos, report, args.apply)

    print("[5/5] Itens não-automatizáveis ...")
    report_manual(insumos, producoes, report)

    # Relatório
    print(f"\n{'─' * 65}")
    print(f"  Correções automáticas: {len(report.fixed)}")
    print(f"  Intervenção manual:    {len(report.manual)}")
    print()
    for msg in report.fixed:
        prefix = "  ✓" if args.apply else "  →"
        print(f"{prefix} {msg}")
    if report.manual:
        print("\n  Intervenção manual necessária:")
        for msg in report.manual:
            print(f"  ⚠ {msg}")
    if report.skipped:
        for msg in report.skipped:
            print(f"  · {msg}")

    if args.apply:
        if "producoes" in bundle:
            bundle["producoes"] = producoes
        else:
            bundle["produtividades"] = producoes
        bundle["insumos"] = insumos
        bundle_path.write_text(json.dumps(bundle, indent=2, ensure_ascii=False), encoding="utf-8")
        print(f"\n  Bundle salvo: {bundle_path}")
        print(f"  Insumos:   {len(insumos)}")
        print(f"  Producoes: {len(producoes)}")

        # Valida plausibilidade pós-curação
        sys.path.insert(0, str(ROOT / "src"))
        from concilium.application.catalog.plausibility_checker import verificar_plausibilidade

        pos = verificar_plausibilidade(insumos, producoes)
        r = pos["resumo"]
        print(f"\n  Pós-curação: {r['erros']} erros | {r['avisos']} avisos | {r['infos']} infos")
        if r["erros"] == 0:
            print("  Status: OK — nenhum erro crítico residual")
        else:
            print("  Status: ATENÇÃO — erros residuais precisam de revisão manual")
    else:
        print("\n  Dry-run — use --apply para aplicar as correções")

    if not args.apply:
        sys.exit(1 if report.manual else 0)


if __name__ == "__main__":
    main()
