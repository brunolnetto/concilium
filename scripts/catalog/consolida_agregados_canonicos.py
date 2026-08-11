"""ADR-139 F4-ter — Consolidação de agregados em insumos canônicos (mendeslobo).

Resolve as duplicatas de agregado com preços divergentes SEM inventar preço, por uma
regra derivada da própria hierarquia de fontes do catálogo (NEP-032: dado da empresa >
tabela de referência) + validade temporal (VAL-INS-VIG):

  As "duplicatas" são três GERAÇÕES de preço do mesmo material físico:
    cotação empresa 2025-05 (areia média 68, brita 1 78)  ← únicas p/ esses materiais
    cotação AGIS 2026 (pedrisco 145, brita 2 145, brita 3 140, rachão 147, pó 165)
    referência SICRO 202604-SP (140,84 / 184,71 / 170,77 / 162,63 / — / 160,63)

  Regra: UM insumo canônico por material; preço vigente = cotação de mercado mais
  recente da empresa; o preço SICRO vai para `historico_precos` (referência de
  sanidade, com fonte); divergência >25% vs SICRO ou defasagem >12 meses ganham
  `_alerta_preco` explícito para recotação pelo editor. Nada é apagado: códigos
  antigos ficam `_superseded_por` sem consumidores (remoção = decisão do editor).

Consequência intencional: as composições de usinagem (BGTC/CBUQ) passam a referenciar
os canônicos e seus preços RE-CONCLUEM na base de cotação da empresa (rodar
`build_usinagem_bgtc_cbuq.py --apply` após esta consolidação).

Uso:
    python scripts/catalog/consolida_agregados_canonicos.py --dry-run   # padrão
    python scripts/catalog/consolida_agregados_canonicos.py --apply
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[2]
CAT_DIR = REPO_ROOT / "config" / "catalogos" / "mendeslobo"
_DATA_REF = "2026-07-14"
_SICRO_FONTE = "SICRO 202604-SP (referência de sanidade — consolidação ADR-139 F4-ter)"

# Canônicos que JÁ existem com código limpo (criados p/ usinagem com preço SICRO):
# adotar cotação de mercado mais recente da empresa como vigente; SICRO → histórico.
# codigo -> (preco_vigente, fonte_vigente, data_vigente, alerta|None)
_ATUALIZA_CANONICO: dict[str, tuple[float, str, str, str | None]] = {
    "MA-BRITA-0-PEDRISCO": (145.0, "cotacao_mercado", "2026-03-01", None),
    "MA-BRITA-2": (145.0, "cotacao_mercado", "2026-03-01", None),
    "MA-BRITA-3": (140.0, "cotacao_mercado", "2026-03-01", None),
    "MA-PO-DE-PEDRA": (165.0, "cotacao_mercado", "2026-03-01", None),
}

# Canônicos novos absorvendo conteúdo de códigos trocados/órfãos.
_CANONICOS_NOVOS: list[dict[str, Any]] = [
    {
        "codigo": "MA-BRITA-4-RACHAO",
        "tipo": "MATERIAL",
        "descricao": "Brita 4 (rachão)",
        "unidade": "m³",
        "preco_unitario": 147.0,
        "fonte_preco": "cotacao_mercado",
        "origem_material": "AQUISICAO_EXTERNA",
        "data_referencia_preco": "2026-03-01",
        "categoria": "TERRAPLENAGEM",
        "_migrado_de": "MA-BDTC-CORPO-DN1200-PA2 (código de bueiro, conteúdo de agregado — ADR-139 F4-ter)",
    },
    {
        "codigo": "MA-AREIA-GROSSA-LAVADA",
        "tipo": "MATERIAL",
        "descricao": "Areia grossa lavada",
        "unidade": "m³",
        "preco_unitario": 120.0,
        "fonte_preco": "cotacao_mercado",
        "origem_material": "AQUISICAO_EXTERNA",
        "data_referencia_preco": "2026-03-01",
        "categoria": "DIVERSOS",
        "_migrado_de": "MA-BSTC-CORPO-DN1000-PA1 (órfão consolidado — ADR-139 F4-ter)",
    },
    {
        "codigo": "MA-AREIA-FINA",
        "tipo": "MATERIAL",
        "descricao": "Areia fina",
        "unidade": "m³",
        "preco_unitario": 100.0,
        "fonte_preco": "cotacao_mercado",
        "origem_material": "AQUISICAO_EXTERNA",
        "data_referencia_preco": "2026-03-01",
        "categoria": "DIVERSOS",
        "_migrado_de": "MA-BSTC-CORPO-DN1200-PA2 (órfão consolidado — ADR-139 F4-ter)",
    },
]

# Alertas de defasagem nos canônicos de cotação única 2025-05 (não muda o preço —
# recotação é decisão do editor; o histórico carrega o SICRO p/ dimensionar o delta).
_ALERTAS_DEFASAGEM: dict[str, tuple[float, str]] = {
    "MA-BRITA-1": (
        172.79,
        "cotação única de 2025-05 (R$ 78) diverge −55% da referência SICRO 202604-SP "
        "(R$ 172,79) — recotar antes da próxima proposta",
    ),
    "MA-AREIA-MEDIA": (
        140.84,
        "cotação única de 2025-05 (R$ 68) diverge −52% da referência SICRO 202604-SP "
        "(R$ 140,84) — recotar antes da próxima proposta",
    ),
}

# Repoints de consumidores para canônicos: producao -> {antigo: novo}
_REPOINTS: dict[str, dict[str, str]] = {
    # usinagens: gêmeos SICRO → canônicos
    "produtividades/PROD-USINAGEM-BGTC-001.json": {"MA-BRITA-1-SICRO": "MA-BRITA-1"},
    "produtividades/PROD-USINAGEM-CBUQ-001.json": {
        "MA-BRITA-1-SICRO": "MA-BRITA-1",
        "MA-AREIA-MEDIA-SICRO": "MA-AREIA-MEDIA",
    },
    # códigos de bueiro com conteúdo de agregado → canônicos
    "produtividades/CPU-PAVIM-ATI-053-PROD-001.json": {"MA-BSTC-CORPO-DN1200-PA3": "MA-BRITA-0-PEDRISCO"},
    "produtividades/CPU-PAVIM-ATI-054-PROD-001.json": {"MA-BDTC-CORPO-DN1000-PA1": "MA-BRITA-2"},
    "produtividades/CPU-PAVIM-ATI-055-PROD-001.json": {"MA-BDTC-CORPO-DN1000-PA2": "MA-BRITA-3"},
    "produtividades/CPU-TERRA-ATI-022-PROD-001.json": {"MA-BDTC-CORPO-DN1200-PA2": "MA-BRITA-4-RACHAO"},
    "produtividades/CPU-TERRA-ATI-020-PROD-001.json": {"MA-BTTC-CORPO-DN1200-PA2": "MA-PO-DE-PEDRA"},
    "produtividades/CPU-TERRA-ATI-024-PROD-001.json": {"MA-BTTC-CORPO-DN1200-PA2": "MA-PO-DE-PEDRA"},
}

_SUPERSEDED: dict[str, str] = {
    "MA-BRITA-1-SICRO": "MA-BRITA-1",
    "MA-AREIA-MEDIA-SICRO": "MA-AREIA-MEDIA",
    "MA-BSTC-CORPO-DN1200-PA3": "MA-BRITA-0-PEDRISCO",
    "MA-BDTC-CORPO-DN1000-PA1": "MA-BRITA-2",
    "MA-BDTC-CORPO-DN1000-PA2": "MA-BRITA-3",
    "MA-BDTC-CORPO-DN1200-PA2": "MA-BRITA-4-RACHAO",
    "MA-BTTC-CORPO-DN1200-PA2": "MA-PO-DE-PEDRA",
    "MA-BSTC-CORPO-DN1000-PA1": "MA-AREIA-GROSSA-LAVADA",
    "MA-BSTC-CORPO-DN1000-PA2": "MA-AREIA-MEDIA",  # órfão "Areia Média Lavada" 110 (AGIS)
    "MA-BSTC-CORPO-DN1200-PA2": "MA-AREIA-FINA",
}

# Preços antigos absorvidos nos históricos dos canônicos (rastro completo).
_HISTORICO_EXTRA: dict[str, list[tuple[float, str, str]]] = {
    # canonico -> [(preco, data_inicio, fonte)]
    "MA-AREIA-MEDIA": [(110.0, "2026-03-01", "cotação AGIS 2026 (órfão MA-BSTC-CORPO-DN1000-PA2 consolidado)")],
}


def _load(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8-sig"))


def _write(path: Path, data: Any) -> None:
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def _push_historico(ins: dict[str, Any], preco: float, data_inicio: str, fonte: str) -> None:
    historico = ins.setdefault("historico_precos", [])
    if not any(h.get("preco_unitario") == preco and h.get("fonte") == fonte for h in historico):
        historico.append(
            {
                "preco_unitario": preco,
                "data_inicio_vigencia": data_inicio,
                "data_fim_vigencia": _DATA_REF,
                "fonte": fonte,
            }
        )


def run_consolidation(cat_dir: Path = CAT_DIR, apply: bool = False) -> dict[str, int]:
    stats = {"canonicos_atualizados": 0, "canonicos_criados": 0, "repoints": 0, "superseded_marcados": 0, "alertas": 0}
    mat_dir = cat_dir / "insumos" / "material"

    for codigo, (preco, fonte, data, _alerta) in _ATUALIZA_CANONICO.items():
        path = mat_dir / f"{codigo}.json"
        ins = _load(path)
        if ins.get("preco_unitario") == preco and ins.get("fonte_preco") == fonte:
            continue
        stats["canonicos_atualizados"] += 1
        print(
            f"  [CANONICO ] {codigo}: R${ins.get('preco_unitario')} (SICRO) → R${preco} (cotação empresa mais recente)"
        )
        if apply:
            _push_historico(
                ins,
                float(ins.get("preco_unitario") or 0),
                str(ins.get("data_referencia_preco") or _DATA_REF),
                _SICRO_FONTE,
            )
            ins["preco_unitario"] = preco
            ins["fonte_preco"] = fonte
            ins["data_referencia_preco"] = data
            _write(path, ins)

    for payload in _CANONICOS_NOVOS:
        path = mat_dir / f"{payload['codigo']}.json"
        if path.exists():
            continue
        stats["canonicos_criados"] += 1
        print(f"  [NOVO     ] {payload['codigo']}: {payload['descricao']} R${payload['preco_unitario']}")
        if apply:
            _write(path, payload)

    for codigo, (preco_sicro, alerta) in _ALERTAS_DEFASAGEM.items():
        path = mat_dir / f"{codigo}.json"
        ins = _load(path)
        if ins.get("_alerta_preco"):
            continue
        stats["alertas"] += 1
        print(f"  [ALERTA   ] {codigo}: {alerta[:80]}…")
        if apply:
            _push_historico(ins, preco_sicro, "2026-04-01", _SICRO_FONTE)
            ins["_alerta_preco"] = alerta
            _write(path, ins)

    for codigo, extras in _HISTORICO_EXTRA.items():
        path = mat_dir / f"{codigo}.json"
        ins = _load(path)
        mudou = False
        for preco, data_inicio, fonte in extras:
            if not any(
                h.get("preco_unitario") == preco and h.get("fonte") == fonte for h in ins.get("historico_precos") or []
            ):
                mudou = True
                if apply:
                    _push_historico(ins, preco, data_inicio, fonte)
        if apply and mudou:
            _write(path, ins)

    for rel, mapa in _REPOINTS.items():
        path = cat_dir / rel
        data = _load(path)
        equipe = data.get("composicao_padrao_equipe") or data.get("equipe") or {}
        mudou = False
        for m in equipe.get("materiais") or []:
            antigo = m.get("insumo_id")
            if antigo in mapa:
                stats["repoints"] += 1
                mudou = True
                print(f"  [REPOINT  ] {data.get('id')}: {antigo} → {mapa[antigo]}")
                m["insumo_id"] = mapa[antigo]
        if apply and mudou:
            _write(path, data)

    for antigo, novo in _SUPERSEDED.items():
        path = mat_dir / f"{antigo}.json"
        if not path.exists():
            continue
        ins = _load(path)
        if ins.get("_superseded_por"):
            continue
        stats["superseded_marcados"] += 1
        print(f"  [SUPERSEDE] {antigo} → {novo}")
        if apply:
            ins["_superseded_por"] = novo
            ins["_nota_superseded"] = (
                f"consolidação de agregados em canônicos (ADR-139 F4-ter, {_DATA_REF}); "
                "sem consumidores — manter apenas como histórico"
            )
            _write(path, ins)

    return stats


def main() -> int:
    parser = argparse.ArgumentParser(description="ADR-139 F4-ter: consolidação de agregados canônicos")
    group = parser.add_mutually_exclusive_group()
    group.add_argument("--dry-run", action="store_true", help="apenas relata (padrão)")
    group.add_argument("--apply", action="store_true", help="grava a consolidação")
    args = parser.parse_args()

    stats = run_consolidation(apply=args.apply)
    modo = "APLICADO" if args.apply else "DRY-RUN (use --apply para gravar)"
    print(f"[{modo}] {stats}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
