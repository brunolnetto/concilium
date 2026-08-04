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


# ── Resolução de arquivo individual (mesma convenção de catalog_governance.py /
# _catalogo_tools_helpers_b.py — insumos/{tipo_lower}/{codigo}.json,
# producoes|produtividades/{id}.json) — cure_plausibility.py é standalone (fora do
# Runtime/MCP), replica localmente em vez de importar os helpers do MCP (que
# arrastam Runtime/ProjectHandle no import).


def _caminho_insumo_individual(catalog_root: Path, tipo: str, codigo: str) -> Path:
    """Resolve o arquivo de um insumo — existente (rglob, não presume nome de
    subpasta) ou, se novo, a convenção canônica insumos/{tipo_lower}/{codigo}.json."""
    insumos_dir = catalog_root / "insumos"
    for existente in insumos_dir.rglob(f"{codigo}.json"):
        return existente
    return insumos_dir / str(tipo).lower() / f"{codigo}.json"


def _caminho_producao_individual(catalog_root: Path, producao_id: str) -> Path:
    """producoes/ e produtividades/ coexistem (legado) — usa o que já existir,
    default producoes/ para item novo."""
    for sub in ("producoes", "produtividades"):
        candidato = catalog_root / sub / f"{producao_id}.json"
        if candidato.exists():
            return candidato
    return catalog_root / "producoes" / f"{producao_id}.json"


def _persistir_insumos_individuais(
    catalog_root: Path, insumos_originais: list[dict], insumos_finais: list[dict], removidos: set[str]
) -> tuple[int, int]:
    """Escreve cada insumo alterado no arquivo individual — nunca no bundle (ver
    docstring do módulo). Remove o arquivo dos insumos deletados (duplicata
    fundida) — sem precedente no repo para isso; `_persistir_merge_em_arquivos_
    individuais` da ADR-177 não cobre remoção porque `mesclar_catalogo` nunca
    remove entidade, só `cure_duplicatas` remove."""
    originais_by_code = {i["codigo"]: i for i in insumos_originais if i.get("codigo")}

    escritos = 0
    for ins in insumos_finais:
        cod = ins.get("codigo", "")
        if not cod or originais_by_code.get(cod) == ins:
            continue
        caminho = _caminho_insumo_individual(catalog_root, ins.get("tipo", ""), cod)
        caminho.parent.mkdir(parents=True, exist_ok=True)
        caminho.write_text(json.dumps(ins, indent=2, ensure_ascii=False), encoding="utf-8")
        escritos += 1

    removidos_ok = 0
    for cod in removidos:
        original = originais_by_code.get(cod)
        if original is None:
            continue
        caminho = _caminho_insumo_individual(catalog_root, original.get("tipo", ""), cod)
        if caminho.exists():
            caminho.unlink()
            removidos_ok += 1
    return escritos, removidos_ok


def _persistir_producoes_individuais(
    catalog_root: Path, producoes_originais: list[dict], producoes_finais: list[dict]
) -> int:
    originais_by_id = {p.get("id", p.get("codigo", "")): p for p in producoes_originais if p.get("id") or p.get("codigo")}
    escritos = 0
    for p in producoes_finais:
        pid = p.get("id") or p.get("codigo", "")
        if not pid or originais_by_id.get(pid) == p:
            continue
        caminho = _caminho_producao_individual(catalog_root, pid)
        caminho.parent.mkdir(parents=True, exist_ok=True)
        caminho.write_text(json.dumps(p, indent=2, ensure_ascii=False), encoding="utf-8")
        escritos += 1
    return escritos


def _cure_templates_estruturas_indiretas(
    catalog_root: Path, dup_map: dict[str, str], report: CureReport, apply: bool
) -> None:
    """Atualiza funcao_id em templates.json/estruturas_indiretas conforme dup_map
    — superfície de referência que producoes/produtividades NÃO cobre (achado
    real: MO-AUX-ADM referenciado 3x em estruturas_indiretas, nunca visto por
    _update_producoes_funcao_ids, ficaria órfão após a remoção da duplicata)."""
    if not dup_map:
        return
    path = catalog_root / "templates.json"
    if not path.exists():
        return
    original_bytes = path.read_bytes()
    usa_crlf = b"\r\n" in original_bytes  # templates.json é CRLF no mendeslobo; insumos/producoes são LF
    data = json.loads(original_bytes.decode("utf-8"))
    estruturas = data.get("estruturas_indiretas") or []
    mudou = False
    for estrutura in estruturas:
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
    if apply and mudou:
        texto = json.dumps(data, indent=2, ensure_ascii=False)
        if usa_crlf:
            texto = texto.replace("\n", "\r\n")
        path.write_text(texto, encoding="utf-8", newline="")


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


def _cure_encargos_alpha(ins: dict, cod: str, attrs: dict, report: CureReport, apply: bool) -> None:
    """a) percentual_encargos_local armazenado como α (> 1.5) em vez de α-1.

    `attrs` chega por referência de `ins["atributos_especificos"]` (não copiado
    em `cure_erros_fisicos`) — mutar em-place aliasaria de volta pro insumo
    ORIGINAL (mesmo objeto dict), fazendo `_persistir_insumos_individuais`
    (que compara por igualdade contra o original) concluir "nada mudou" e
    NUNCA escrever o fix em disco. Achado real: MO-OPERADOR-DE-MOTOSCRA teve o
    α corrigido em memória mas nunca persistido. Copia antes de mutar, mesmo
    padrão de `_cure_locacao_mensal_item`."""
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
    """b) preco_unitario abaixo do mínimo mensal (ignora estagiários e unidade="h")."""
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
    if pa <= 0 or pb <= 0:
        return False
    ratio = max(pa, pb) / min(pa, pb)
    if ratio <= _RATIO_IDENTICO_MAX:
        return True
    lo, hi = _RATIO_ENCARGOS_CONFIRMADO
    return lo <= ratio <= hi


def _escolher_canonico(codes: list[str], ins_by_code: dict[str, dict]) -> str:
    """Canônico do cluster: prefere o MENOR preco_unitario primeiro — para
    unidade="mes", pu_calculator aplica seu próprio α por cima (ADR-009); manter
    o valor já-com-encargos (o lado "P####" tipicamente importado via AGIS)
    causaria dupla contagem de encargos na cadeia de custo. Empate de preço
    (caso comum do dedup exato original, onde ambos os lados já tinham o mesmo
    valor): prefere código que não seja P####/MO-P####, critério original.
    `codes` é ordenado antes do min() para determinismo (independe de ordem de
    iteração de set/dict)."""

    def chave(c: str) -> tuple[float, int]:
        preco = float(ins_by_code[c].get("preco_unitario") or 0)
        return (preco, 1 if _eh_codigo_p(c) else 0)

    return min(sorted(codes), key=chave)


def _build_dup_map(insumos: list[dict], report: CureReport | None = None) -> dict[str, str]:
    """Retorna {codigo: canonical_code} para todos os duplicados detectados.

    Duas fontes, combinadas por union-find (ADR-179):
    (a) match exato de (descrição normalizada, preço) — comportamento original.
    (b) similarity.find_candidate_duplicates, só classificacao="duplicata_provavel"
        (score ≥ 0,80) — pega pares como P0058/MO-SALA-TEC que (a) nunca captura
        porque o preço difere por um fator de encargos, não é igual.

    classificacao="revisar" NÃO é fundido automaticamente (fica para decisão
    humana) — se `report` for passado, cada par de baixa confiança é listado em
    report.manual, para não desaparecer silenciosamente.
    """
    mo = [i for i in insumos if i.get("tipo") == "MAO_OBRA"]
    ins_by_code = {i["codigo"]: i for i in mo}

    parent: dict[str, str] = {}

    def find(x: str) -> str:
        parent.setdefault(x, x)
        while parent[x] != x:
            x = parent[x]
        return x

    def union(a: str, b: str) -> None:
        ra, rb = find(a), find(b)
        if ra != rb:
            parent[ra] = rb

    participantes: set[str] = set()

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

    for m in find_candidate_duplicates(mo):
        if m.classificacao is None:
            continue
        pa = float(ins_by_code[m.codigo_a].get("preco_unitario") or 0)
        pb = float(ins_by_code[m.codigo_b].get("preco_unitario") or 0)
        liberado = m.classificacao == "duplicata_provavel" and _razao_preco_liberada_para_fusao(pa, pb)
        if liberado:
            participantes.add(m.codigo_a)
            participantes.add(m.codigo_b)
            union(m.codigo_a, m.codigo_b)
        elif report is not None:
            ratio = max(pa, pb) / min(pa, pb) if pa > 0 and pb > 0 else None
            if m.classificacao == "revisar":
                motivo = f"revisar, score={m.score:.2f}"
            else:
                motivo = f"duplicata_provavel (score={m.score:.2f}) mas razão de preço {ratio:.3f} fora das faixas validadas — origem não confirmada"
            report.add_manual(
                f"INSUMO {m.codigo_a}/{m.codigo_b}: {motivo} — "
                f"'{ins_by_code[m.codigo_a].get('descricao')}' (R${pa}) vs "
                f"'{ins_by_code[m.codigo_b].get('descricao')}' (R${pb}) — não fundido automaticamente"
            )

    clusters: dict[str, list[str]] = defaultdict(list)
    for code in sorted(participantes):
        clusters[find(code)].append(code)

    dup_map: dict[str, str] = {}
    for codes in clusters.values():
        if len(codes) < 2:
            continue
        canonical = _escolher_canonico(codes, ins_by_code)
        preco_canon = float(ins_by_code[canonical].get("preco_unitario") or 0)
        for c in codes:
            if c == canonical:
                continue
            # Reconfirma a razão contra o CANÔNICO especificamente — a & b podem ter
            # entrado no mesmo cluster via um terceiro nó-ponte (A-B seguro, B-C
            # seguro, mas A-C não) sem que A-C jamais tenha sido validado direto
            # (achado real: P0006/MO-AUX-ADM/MO-P0006, razão direta P0006×MO-P0006
            # = 4,13, bem fora de qualquer faixa, mesmo com os dois links intermediários
            # seguros). Sem essa revalidação, a transitividade do union-find fundiria
            # itens nunca comparados diretamente.
            preco_c = float(ins_by_code[c].get("preco_unitario") or 0)
            if _razao_preco_liberada_para_fusao(preco_c, preco_canon):
                dup_map[c] = canonical
            elif report is not None:
                ratio = max(preco_c, preco_canon) / min(preco_c, preco_canon) if preco_c > 0 and preco_canon > 0 else None
                report.add_manual(
                    f"INSUMO {c}/{canonical}: conectados via cadeia transitiva mas razão "
                    f"direta {ratio:.3f} fora das faixas validadas — não fundido"
                )
    return dup_map


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
    """Atualiza funcao_id de uma produção conforme dup_map; retorna (produção, refs_atualizadas)."""
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
    """Atualiza funcao_id nas producoes para todos os itens em dup_map."""
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
    """Remove duplicados (match exato + similaridade ADR-179), adiciona
    codigo_referencia_externa, atualiza producoes. Retorna também o dup_map —
    quem chama precisa dele para atualizar outras superfícies de referência
    (templates.json/estruturas_indiretas, que producoes não cobre)."""
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


def _cure_locacao_mensal_item(ins: dict, report: CureReport, apply: bool) -> bool:
    """Deriva valor_locacao_mensal para um insumo EQUIPAMENTO; retorna True se derivado."""
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
    _report_producoes_sem_composicao(producoes, report)
    _report_insumos_suspeitos(insumos, report)


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

    catalog_root = ROOT / f"config/catalogos/{args.contexto}"
    bundle_path = catalog_root / ".catalog_bundle.json"
    if not bundle_path.exists():
        print(f"Bundle não encontrado: {bundle_path}", file=sys.stderr)
        sys.exit(1)

    # Bundle é só a FONTE DE LEITURA — nunca escrita (ver docstring do módulo).
    bundle = json.loads(bundle_path.read_text(encoding="utf-8"))
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
    else:
        print("\n  Dry-run — use --apply para aplicar as correções")
        sys.exit(1 if report.manual else 0)


def _run_cure_steps(
    catalog_root: Path, insumos: list[dict], producoes: list[dict], report: CureReport, apply: bool
) -> tuple[list[dict], list[dict]]:
    print("[1/5] Erros físicos (encargos + salário mínimo) ...")
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
    print(f"\n{'─' * 65}")
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
