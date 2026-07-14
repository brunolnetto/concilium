"""ADR-139 F4 — Cura de insumos com código trocado na importação AGIS (mendeslobo).

Diagnóstico (dossiê no PR #104): os CÓDIGOS de alguns insumos foram deslocados na
importação da planilha AGIS, mas descrição + preço + consumo das CPUs são coerentes
entre si — o código aponta para outro material:

  | Código (mentiroso)      | Conteúdo real (desc+preço)      | Consumidor           |
  |-------------------------|---------------------------------|----------------------|
  | MA-EMULSAO-RR-1C        | CCR 360,05/m³                   | ATI-019 aterro CCR   |
  | MA-EMULSAO-RR-2C        | CAP 50/70 5.300/t               | ATI-058/061 (massa!) |
  | MA-CONCRETO-FCP-20MPA   | Emulsão RR-2C 3.850/t           | ATI-062 TSD          |
  | MA-BRITA-GRADUADA       | BGTC 360,05/m³ (duplicata)      | ATI-023              |

**Erro crítico de preço corrigido**: CPU-PAVIM-ATI-058 (CBUQ 3 cm) e ATI-061
(recomposição) consomem MASSA asfáltica (72 kg/m², coerente com 3 cm × 2,4 t/m³) mas
pagavam preço de CAP puro (R$ 5.300/t) → material R$ 381,60/m², ~10× o real. Passam a
consumir `MA-CBUQ-FAIXA-C` (massa usinada, gerada internamente pela usinagem a
R$ 484,26/t) → material ≈ R$ 34,87/m². Isso também fecha o produtor-consumidor do
CBUQ (usinagem → aplicação), como já feito para BGTC.

Correções (repoint de consumidor + insumo canônico novo onde preciso; códigos
mentirosos ficam SEM consumidor e recebem nota `_superseded_por` — remoção é decisão
do editor):
  1. ATI-058, ATI-061: MA-EMULSAO-RR-2C → MA-CBUQ-FAIXA-C (massa gerada).
  2. ATI-023: MA-BRITA-GRADUADA → MA-BGTC-MIX (BGTC gerada; elimina a duplicata).
  3. ATI-019: MA-EMULSAO-RR-1C → novo MA-CCR (CCR usinado comprado, 360,05/m³ —
     sem usina de CCR modelada no catálogo: AQUISICAO_EXTERNA no recorte).
  4. ATI-062: MA-CONCRETO-FCP-20MPA → novo MA-EMULSAO-RR2C-GRANEL (emulsão RR-2C a
     granel, 3.850/t, AQUISICAO_EXTERNA).

FORA desta cura (relatório para o editor — exigem decisão de preço): duplicatas de
agregados com preços divergentes (Areia média lavada 68 × 110/m³; pedrisco 145 ×
184,71/m³; brita 1 78 × 172,79/m³) e renomeio dos códigos MA-{BSTC,BDTC,BTTC}-CORPO-*
que carregam agregados com preço plausível (código errado, preço certo).

Uso:
    python scripts/catalog/cure_insumos_agis_codigo_trocado.py --dry-run   # padrão
    python scripts/catalog/cure_insumos_agis_codigo_trocado.py --apply
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[2]
CAT_DIR = REPO_ROOT / "config" / "catalogos" / "mendeslobo"
_DATA_REF = "2026-07-14"

_INSUMOS_NOVOS: list[dict[str, Any]] = [
    {
        "codigo": "MA-CCR",
        "tipo": "MATERIAL",
        "descricao": "CCR (Concreto Compactado com Rolo) — usinado, compra externa",
        "unidade": "m³",
        "preco_unitario": 360.05,
        "fonte_preco": "tabela_referencia",
        "origem_material": "AQUISICAO_EXTERNA",
        "data_referencia_preco": _DATA_REF,
        "categoria": "TERRAPLENAGEM",
        "_migrado_de": "MA-EMULSAO-RR-1C (código trocado na importação AGIS — ver PR #104)",
    },
    {
        "codigo": "MA-EMULSAO-RR2C-GRANEL",
        "tipo": "MATERIAL",
        "descricao": "Emulsão asfáltica catiônica RR-2C a granel (banho de TSD)",
        "unidade": "t",
        "preco_unitario": 3850.0,
        "fonte_preco": "tabela_referencia",
        "origem_material": "AQUISICAO_EXTERNA",
        "data_referencia_preco": _DATA_REF,
        "categoria": "PAVIMENTACAO",
        "_migrado_de": "MA-CONCRETO-FCP-20MPA (código trocado na importação AGIS — ver PR #104)",
    },
]

# producao (produtividades/) -> {insumo_antigo: (insumo_novo, justificativa)}
_REPOINTS: dict[str, dict[str, tuple[str, str]]] = {
    "CPU-PAVIM-ATI-058-PROD-001": {
        "MA-EMULSAO-RR-2C": (
            "MA-CBUQ-FAIXA-C",
            "consumo é MASSA asfáltica (72 kg/m² = 3 cm × 2,4 t/m³), não CAP puro — corrige preço "
            "10× inflado (381,60 → ~34,87 R$/m² de material) e fecha usinagem→aplicação",
        )
    },
    "CPU-PAVIM-ATI-061-PROD-001": {
        "MA-EMULSAO-RR-2C": (
            "MA-CBUQ-FAIXA-C",
            "recomposição consome massa asfáltica usinada (72 kg/m²), não CAP puro",
        )
    },
    "CPU-TERRA-ATI-023-PROD-001": {
        "MA-BRITA-GRADUADA": (
            "MA-BGTC-MIX",
            "consolida duplicata de BGTC no material gerado pela usinagem (PROD-USINAGEM-BGTC-001)",
        )
    },
    "CPU-TERRA-ATI-019-PROD-001": {
        "MA-EMULSAO-RR-1C": ("MA-CCR", "código trocado: o conteúdo real do insumo é CCR (desc+preço)"),
    },
    "CPU-PAVIM-ATI-062-PROD-001": {
        "MA-CONCRETO-FCP-20MPA": (
            "MA-EMULSAO-RR2C-GRANEL",
            "código trocado: o conteúdo real do insumo é emulsão RR-2C (desc+preço; TSD ~1 kg/m²)",
        ),
    },
}

_SUPERSEDED: dict[str, str] = {
    "MA-EMULSAO-RR-1C": "MA-CCR",
    "MA-EMULSAO-RR-2C": "MA-CAP-50-70",
    "MA-CONCRETO-FCP-20MPA": "MA-EMULSAO-RR2C-GRANEL",
    "MA-BRITA-GRADUADA": "MA-BGTC-MIX",
}


def _load(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8-sig"))


def _write(path: Path, data: Any) -> None:
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def run_cure(cat_dir: Path = CAT_DIR, apply: bool = False) -> dict[str, int]:
    stats = {"insumos_criados": 0, "repoints": 0, "superseded_marcados": 0}

    for payload in _INSUMOS_NOVOS:
        path = cat_dir / "insumos" / "material" / f"{payload['codigo']}.json"
        if path.exists():
            continue
        stats["insumos_criados"] += 1
        print(f"  [INSUMO   ] {payload['codigo']}: {payload['descricao'][:60]} (R${payload['preco_unitario']})")
        if apply:
            _write(path, payload)

    for pid, mapa in _REPOINTS.items():
        path = cat_dir / "produtividades" / f"{pid}.json"
        data = _load(path)
        equipe = data.get("composicao_padrao_equipe") or data.get("equipe") or {}
        mudou = False
        for m in equipe.get("materiais") or []:
            antigo = m.get("insumo_id")
            if antigo in mapa:
                novo, justificativa = mapa[antigo]
                stats["repoints"] += 1
                mudou = True
                print(f"  [REPOINT  ] {pid}: {antigo} → {novo} ({justificativa[:70]}…)")
                m["insumo_id"] = novo
                m["descricao"] = f"repoint AGIS: era {antigo} — {justificativa} (ADR-139 F4 cura)"
        if apply and mudou:
            _write(path, data)

    for antigo, novo in _SUPERSEDED.items():
        path = cat_dir / "insumos" / "material" / f"{antigo}.json"
        if not path.exists():
            continue
        data = _load(path)
        if data.get("_superseded_por"):
            continue
        stats["superseded_marcados"] += 1
        print(f"  [SUPERSEDE] {antigo} → {novo} (sem consumidores; remoção é decisão do editor)")
        if apply:
            data["_superseded_por"] = novo
            data["_nota_superseded"] = (
                "código trocado na importação AGIS (dossiê PR #104); consumidores repontados em "
                f"{_DATA_REF} — manter apenas como histórico"
            )
            _write(path, data)

    return stats


def main() -> int:
    parser = argparse.ArgumentParser(description="ADR-139 F4: cura de insumos AGIS com código trocado")
    group = parser.add_mutually_exclusive_group()
    group.add_argument("--dry-run", action="store_true", help="apenas relata (padrão)")
    group.add_argument("--apply", action="store_true", help="grava as correções")
    args = parser.parse_args()

    stats = run_cure(apply=args.apply)
    modo = "APLICADO" if args.apply else "DRY-RUN (use --apply para gravar)"
    print(
        f"[{modo}] {stats['insumos_criados']} insumo(s) novo(s), {stats['repoints']} repoint(s), "
        f"{stats['superseded_marcados']} superseded"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
