"""
Correções manuais dos 18 erros residuais do catálogo mendeslobo.

Ações:
  1. Funcoes duplicadas: mescla entrada duplicada somando num_pessoas
  2. valor_horario estimado: produtividade típica SINAPI/SICRO por equipe
  3. unidade: derivada do tipo de serviço
  4. Normaliza códigos com acentos → ASCII puro e atualiza referências
  5. MA-AGIS-*: encurta código acima de 40 chars
  6. EQ-HIDROSSEMEADORA: adiciona fonte_preco
"""
from __future__ import annotations

import io, json, sys
from collections import defaultdict
from pathlib import Path

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

ROOT = Path(__file__).resolve().parents[1]
BUNDLE_PATH = ROOT / "config/catalogos/mendeslobo/.catalog_bundle.json"

bundle = json.loads(BUNDLE_PATH.read_text(encoding="utf-8"))
prods   = bundle.get("producoes", []) or bundle.get("produtividades", [])
insumos = bundle.get("insumos", [])
cpus    = bundle.get("cpus", [])

# ── 1. Normalização de códigos ────────────────────────────────────────────────
# Mapeamento: código antigo → código normalizado ASCII
RENAME = {
    "MO-AUXILIAR-DE-SERVIÇOS":               "MO-AUXILIAR-SERVICOS",
    "MO-ESTAGIÁRIO":                          "MO-ESTAGIARIO",
    "MO-MECÂNICO":                            "MO-MECANICO",
    "MO-MOTORISTA-DE-CAMINHÃ":               "MO-MOTORISTA-MUNCK",
    # Descrição: "Técnico de Enfermagem do Trabalho"
    "MO-TÉCNICO-DE-ENFERMAGE":               "MO-TECNICO-ENFERMAGEM",
    # Descrição: "Técnico de Planejamento"
    "MO-TÉCNICO-DE-PLANEJAME":               "MO-TECNICO-PLANEJAMENTO",
    "MO-TÉCNICO-DE-QSMS":                    "MO-TECNICO-QSMS",
    # 42 chars → 29 chars; prefixo AGIS mantido no campo fonte_preco
    "MA-AGIS-CPU-TERRA-ENCHIMENTO-REBAIXO-ROCHA": "MA-ENCHIMENTO-REBAIXO-ROCHA",
}

renamed = 0
for ins in insumos:
    old = ins.get("codigo", "")
    if old in RENAME:
        new = RENAME[old]
        ins["codigo"] = new
        print(f"  [INSUMO] {old} → {new}")
        renamed += 1

# Atualiza referências em producoes (funcao_id em funcoes e materiais)
refs_updated = 0
for p in prods:
    equipe = p.get("composicao_padrao_equipe") or {}
    for funcao in equipe.get("funcoes", []):
        if funcao.get("funcao_id") in RENAME:
            old = funcao["funcao_id"]
            funcao["funcao_id"] = RENAME[old]
            refs_updated += 1
    for mat in equipe.get("materiais", []):
        if mat.get("insumo_id") in RENAME:
            old = mat["insumo_id"]
            mat["insumo_id"] = RENAME[old]
            refs_updated += 1

# Atualiza referências em CPUs (composicao_itens.insumo_id)
for cpu in cpus:
    for item in cpu.get("composicao_itens", []):
        if item.get("insumo_id") in RENAME:
            old = item["insumo_id"]
            item["insumo_id"] = RENAME[old]
            refs_updated += 1

print(f"  → {renamed} insumos renomeados, {refs_updated} referências atualizadas\n")

# ── 2. EQ-HIDROSSEMEADORA: fonte_preco faltante ──────────────────────────────
for ins in insumos:
    if ins.get("codigo") == "EQ-HIDROSSEMEADORA" and not ins.get("fonte_preco"):
        ins["fonte_preco"] = "catalogo_proprio"
        print(f"  [INSUMO] EQ-HIDROSSEMEADORA: fonte_preco = 'catalogo_proprio'")

# ── 3. Funcoes duplicadas: mescla somando num_pessoas ────────────────────────
# IDs das producoes afetadas (após migração equipe→composicao_padrao_equipe)
DUPL_PROD_IDS = {
    "ATI-017",
    "CPU-PAVIM-ATI-060-PROD-001",
    "CPU-TERRA-ATI-017-PROD-001",
    "CPU-TERRA-ATI-019-PROD-001",
}

def deduplicate_funcoes(funcoes: list[dict]) -> list[dict]:
    """Mescla entradas com mesmo funcao_id somando num_pessoas."""
    merged: dict[str, dict] = {}
    for f in funcoes:
        fid = f.get("funcao_id", "")
        if fid in merged:
            merged[fid]["num_pessoas"] += f.get("num_pessoas", 1)
        else:
            merged[fid] = dict(f)
    return list(merged.values())

for p in prods:
    pid = p.get("id", "")
    if pid not in DUPL_PROD_IDS:
        continue
    equipe = p.get("composicao_padrao_equipe") or {}
    funcoes_antes = equipe.get("funcoes", [])
    funcoes_depois = deduplicate_funcoes(funcoes_antes)
    if len(funcoes_depois) < len(funcoes_antes):
        equipe["funcoes"] = funcoes_depois
        p["composicao_padrao_equipe"] = equipe
        print(f"  [PROD] {pid}: funcoes {len(funcoes_antes)} → {len(funcoes_depois)} (duplicatas mescladas)")

# ── 4. valor_horario e unidade estimados ─────────────────────────────────────
# Estimativas baseadas em equipe, atividade e referências SINAPI/SICRO

ESTIMATES: dict[str, dict] = {
    # Base granular/BGTC: motoniveladora + rolo + 2 cam-basc
    # SICRO: ~150-200 m²/h para espalhamento e compactação de base
    "CPU-PAVIM-PAV-BASE-BGTC-PROD-001": {
        "valor_horario": 160.0,
        "unidade": "m2",
        "_estimativa": "estimado — base BGTC com motoniveladora 140K + rolo + 2 cam-basc 14m3; ref. SICRO 160 m²/h"
    },
    # Manilha DN300: retroescavadeira + 5 operários (encanador, montador, 2 serventes)
    # SINAPI: 4-8 m/h para instalação de tubulação DN300 em vala aberta
    "CPU-SANEA-DREN-MAN-DN300-PROD-001": {
        "valor_horario": 5.0,
        "unidade": "m",
        "_estimativa": "estimado — tubulação DN300 com retro-escavadeira + 5 operários; ref. SINAPI 5 m/h"
    },
    # Poço de visita padrão: 1 oficial + 2 serventes, sem equip. pesado
    # Referência de obra: ~1 poço/dia de 8h = 0.125 un/h
    "CPU-SANEA-POCO-VISITA-PADRAO-PROD-001": {
        "valor_horario": 0.125,
        "unidade": "un",
        "_estimativa": "estimado — poço de visita padrão por equipe manual (1 oficial + 2 serventes); 1 un/8h"
    },
    # Compactação aterro 100% PN: 2 rolos pé-de-carneiro + motoniveladora + cam-pipa
    # 6-8 passadas para PN; cada rolo ≈ 150 m³/h efetivo → 2 rolos ≈ 300 m³/h
    "CPU-TERRA-COMPACT-ATERRO-100PN-PROD-001": {
        "valor_horario": 300.0,
        "unidade": "m3",
        "_estimativa": "estimado — compactação 100%PN; 2 rolos pé-de-carneiro + motonivel + pipa; ref. SICRO ~300 m³/h"
    },
    # Regularização de subleito: motoniveladora + rolo liso
    # SICRO: motoniveladora regularizando subleito ≈ 2000-3000 m²/h
    "CPU-TERRA-REGULARIZACAO-SUBLEITO-PROD-001": {
        "valor_horario": 2000.0,
        "unidade": "m2",
        "_estimativa": "estimado — regularização subleito com motoniveladora 140K + rolo liso; ref. SICRO ~2000 m²/h"
    },
}

for p in prods:
    pid = p.get("id", "")
    if pid not in ESTIMATES:
        continue
    est = ESTIMATES[pid]
    before_vh = p.get("valor_horario")
    before_un = p.get("unidade")
    p["valor_horario"] = est["valor_horario"]
    p["unidade"]       = est["unidade"]
    # Registra nota de estimativa em historico_observacoes
    import datetime
    obs = p.setdefault("historico_observacoes", [])
    obs.append({
        "data": datetime.datetime.now(datetime.timezone.utc).isoformat(),
        "autor": "cure_catalog/fix_manual",
        "descricao": est["_estimativa"],
        "tipo": "calibracao",
    })
    print(
        f"  [PROD] {pid}: valor_horario={before_vh}→{est['valor_horario']} "
        f"unidade={before_un}→{est['unidade']}"
    )

# ── Salva bundle atualizado ───────────────────────────────────────────────────
if "producoes" in bundle:
    bundle["producoes"] = prods
else:
    bundle["produtividades"] = prods
bundle["insumos"] = insumos
bundle["cpus"] = cpus

BUNDLE_PATH.write_text(json.dumps(bundle, indent=2, ensure_ascii=False), encoding="utf-8")
print(f"\n  Bundle salvo: {BUNDLE_PATH}")
