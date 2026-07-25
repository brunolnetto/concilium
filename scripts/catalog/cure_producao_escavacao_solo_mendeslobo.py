"""ADR-139 F5-ter — Vincula produção de solo às escavações do catálogo mendeslobo.

Diagnóstico (achado 2026-07-25, investigação profunda do benchmark AGIS infeasible mesmo
após ADR-139 F5-bis e ADR-128 F7): instrumentando `apply_replenishable_delay`, confirmei
que `producao_por_semana` está **vazio** para `MA-SOLO-ESCAVADO-{1,2,3}CAT` no projeto
AGIS — ou seja, essas atividades de compactação/aterro consomem material que **nenhuma
atividade produz**, tornando o estoque negativo desde a primeira semana de consumo e
crescendo sem limite (não é problema de timing, pool ou horizonte: é ausência total de
produtor vinculado).

Causa raiz no catálogo: as 6 produtividades de escavação (`CPU-TERRA-ESCO-CARGA-{1,2,3}CAT-
DMT{2000,3000}-PROD-001`) em `config/catalogos/mendeslobo/produtividades/` nunca declaram
`materiais_gerados` — ao contrário das produtividades equivalentes em `rfi-r02`, que JÁ
têm esse campo (piloto corte→aterro E2E citado em ADR-139 F4). Confirmação numérica: os
`valor_horario` do mendeslobo (231.87 / 230.91 / 158.28 / 158.78 / 142.02 / 142.16) batem
exatos com os `geracao_por_hora` já usados em rfi-r02 — rfi-r02 herdou esses dados de
mendeslobo (ver ADR-139 F4-quater), mas o campo `materiais_gerados` nunca foi replicado de
volta para a fonte.

Correção: replica o mesmo padrão já correto de rfi-r02 (coeficiente 1 m³ escavado = 1 m³
de material, `geracao_por_hora` = `valor_horario`) para as 6 produtividades de escavação
do mendeslobo.

Uso:
    python scripts/catalog/cure_producao_escavacao_solo_mendeslobo.py --dry-run  # padrão
    python scripts/catalog/cure_producao_escavacao_solo_mendeslobo.py --apply
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[2]
CAT_DIR = REPO_ROOT / "config" / "catalogos" / "mendeslobo"

# produtividade_id -> insumo_id gerado
_ESCAVACOES: dict[str, str] = {
    "CPU-TERRA-ESCO-CARGA-1CAT-DMT2000-PROD-001": "MA-SOLO-ESCAVADO-1CAT",
    "CPU-TERRA-ESCO-CARGA-1CAT-DMT3000-PROD-001": "MA-SOLO-ESCAVADO-1CAT",
    "CPU-TERRA-ESCO-CARGA-2CAT-DMT2000-PROD-001": "MA-SOLO-ESCAVADO-2CAT",
    "CPU-TERRA-ESCO-CARGA-2CAT-DMT3000-PROD-001": "MA-SOLO-ESCAVADO-2CAT",
    "CPU-TERRA-ESCO-CARGA-3CAT-DMT2000-PROD-001": "MA-SOLO-ESCAVADO-3CAT",
    "CPU-TERRA-ESCO-CARGA-3CAT-DMT3000-PROD-001": "MA-SOLO-ESCAVADO-3CAT",
}

_CATEGORIA_TXT = {
    "MA-SOLO-ESCAVADO-1CAT": "1ª categoria",
    "MA-SOLO-ESCAVADO-2CAT": "2ª categoria",
    "MA-SOLO-ESCAVADO-3CAT": "3ª categoria",
}


def _load(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8-sig"))


def _write(path: Path, data: Any) -> None:
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def run_cure(cat_dir: Path = CAT_DIR, apply: bool = False) -> dict[str, int]:
    stats = {"produtoras_vinculadas": 0}

    for pid, insumo_id in _ESCAVACOES.items():
        path = cat_dir / "produtividades" / f"{pid}.json"
        data = _load(path)
        if data.get("materiais_gerados"):
            print(f"  [OK       ] {pid}: já tem materiais_gerados — nada a fazer (idempotente)")
            continue

        stats["produtoras_vinculadas"] += 1
        geracao = data["valor_horario"]
        print(f"  [VINCULAR ] {pid} → {insumo_id} @ {geracao} m³/h")
        if apply:
            data["materiais_gerados"] = [
                {
                    "insumo_id": insumo_id,
                    "geracao_por_hora": geracao,
                    "unidade": "m3",
                    "descricao": (
                        "1 m³ escavado → 1 m³ de material, sem fator de empolamento — "
                        f"escavação {_CATEGORIA_TXT[insumo_id]} (ADR-139 F5-ter — "
                        "replicado de rfi-r02, achado 2026-07-25: AGIS consumia este "
                        "material sem nenhum produtor vinculado, estoque sempre negativo)"
                    ),
                }
            ]
            _write(path, data)

    return stats


def main() -> int:
    parser = argparse.ArgumentParser(
        description="ADR-139 F5-ter: vincula produção de solo às escavações do mendeslobo"
    )
    group = parser.add_mutually_exclusive_group()
    group.add_argument("--dry-run", action="store_true", help="apenas relata (padrão)")
    group.add_argument("--apply", action="store_true", help="grava a correção")
    args = parser.parse_args()

    stats = run_cure(apply=args.apply)
    modo = "APLICADO" if args.apply else "DRY-RUN (use --apply para gravar)"
    print(f"[{modo}] {stats['produtoras_vinculadas']} produtora(s) vinculada(s)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
