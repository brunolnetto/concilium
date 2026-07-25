"""ADR-139 F5-bis — Cura do pareamento de categoria de solo em CPU-TERRA-COMPAC-PN (AGIS).

Diagnóstico (achado 2026-07-25, investigação dos testes de tests/integration/cost/
test_cost_decomposition_adr104.py): `CPU-TERRA-COMPAC-PN` consome hoje 100% do seu BOM
em `MA-SOLO-ESCAVADO-1CAT`, mas o próprio quantitativo do item de EAP que usa essa CPU
(1.135.635,3 m³) bate — casa decimal a casa decimal — com a soma exata da produção real
de 1ª e 2ª categoria na EAP AGIS:

    eap-1_1 + eap-1_2 (1CAT) = 107.463,1053 + 336.915,0947 = 444.378,2 m³
    eap-1_3 + eap-1_4 (2CAT) = 105.311,3323 + 585.945,7677 = 691.257,1 m³
    444.378,2 + 691.257,1    = 1.135.635,3 m³ == quantitativo de eap-1_7 (CPU-TERRA-COMPAC-PN)

Mesmo padrão já correto do par 3ª categoria (eap-1_5+eap-1_6 = 981.153,5 m³ ==
CPU-TERRA-CORPO-ATERRO-3CAT), que consome `MA-SOLO-ESCAVADO-3CAT` sem problema. A nota
já registrada na produtividade ("2ª categoria também admissível — pareamento de projeto
decide (D5)", ADR-139 F4) sinalizava a ambiguidade, mas o BOM nunca foi de fato dividido
— ficou 100% em 1CAT, deixando ~720.668 m³ de déficit de 1CAT e ~691.257 m³ de 2CAT sem
nenhum consumidor. Isso torna o schedule do benchmark AGIS infeasible
(VAL-ESTOQUE-DELAY-02 — reparo de estoque do CP-SAT nunca resolve porque o déficit é
estrutural, não de timing) e zera o custo_direto calculado.

Correção: divide a linha de material de `CPU-TERRA-COMPAC-PN-PROD-001` em duas,
proporcionais à composição real 1CAT/2CAT da EAP (coeficiente segue 1 m³/m³, só a
fração entre os dois materiais muda):

    fração 1CAT = 444.378,2 / 1.135.635,3 = 39,13%  → consumo_por_hora = 173,01 × 0,3913 = 67,70
    fração 2CAT = 691.257,1 / 1.135.635,3 = 60,87%  → consumo_por_hora = 173,01 × 0,6087 = 105,31
    soma = 67,70 + 105,31 = 173,01 (== valor_horario original, sem mudança na produtividade)

`CPU-TERRA-COMPAC-PI` (29.411,0 m³) NÃO é tocado por este script — seu volume não bate
com nenhuma soma residual das categorias (não é derivável objetivamente dos dados
disponíveis; ver achado em ADR-139 F5).

Uso:
    python scripts/catalog/cure_pareamento_solo_compac_pn_agis.py --dry-run   # padrão
    python scripts/catalog/cure_pareamento_solo_compac_pn_agis.py --apply
"""

from __future__ import annotations

import argparse
import json
from decimal import Decimal
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[2]
CAT_DIR = REPO_ROOT / "config" / "catalogos" / "mendeslobo"
PRODUTIVIDADE_ID = "CPU-TERRA-COMPAC-PN-PROD-001"
_DATA_REF = "2026-07-25"

_Q_1CAT = Decimal("444378.2")
_Q_2CAT = Decimal("691257.1")
_Q_TOTAL = _Q_1CAT + _Q_2CAT
_VALOR_HORARIO = Decimal("173.01")

_CONSUMO_1CAT = float(round(_VALOR_HORARIO * _Q_1CAT / _Q_TOTAL, 2))
_CONSUMO_2CAT = float(round(_VALOR_HORARIO * _Q_2CAT / _Q_TOTAL, 2))

_NOTA = (
    "BOM dividido 2026-07-25 (ADR-139 F5-bis): quantitativo do item de EAP que usa esta "
    "CPU (1.135.635,3 m³) bate exato com a soma real de 1ª+2ª categoria na EAP AGIS "
    "(444.378,2 + 691.257,1); antes 100% em 1CAT, deixando 2CAT sem consumidor e 1CAT "
    "com déficit — schedule saía infeasible (VAL-ESTOQUE-DELAY-02). "
    "Coeficiente segue 1 m³/m³, só a fração entre os dois materiais mudou."
)


def _load(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8-sig"))


def _write(path: Path, data: Any) -> None:
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def run_cure(cat_dir: Path = CAT_DIR, apply: bool = False) -> dict[str, int]:
    stats = {"materiais_divididos": 0}

    path = cat_dir / "produtividades" / f"{PRODUTIVIDADE_ID}.json"
    data = _load(path)
    equipe = data.get("composicao_padrao_equipe") or {}
    materiais = equipe.get("materiais") or []

    ja_dividido = any(m.get("insumo_id") == "MA-SOLO-ESCAVADO-2CAT" for m in materiais)
    if ja_dividido:
        print(f"  [OK       ] {PRODUTIVIDADE_ID}: já dividido — nada a fazer (idempotente)")
        return stats

    for m in materiais:
        if m.get("insumo_id") != "MA-SOLO-ESCAVADO-1CAT":
            continue
        stats["materiais_divididos"] += 1
        print(
            f"  [DIVIDIR  ] {PRODUTIVIDADE_ID}: MA-SOLO-ESCAVADO-1CAT "
            f"{m['consumo_por_hora']} → 1CAT={_CONSUMO_1CAT} + 2CAT={_CONSUMO_2CAT}"
        )
        m["consumo_por_hora"] = _CONSUMO_1CAT
        m["descricao"] = _NOTA
        materiais.append(
            {
                "insumo_id": "MA-SOLO-ESCAVADO-2CAT",
                "consumo_por_hora": _CONSUMO_2CAT,
                "unidade": "m3",
                "descricao": _NOTA,
                "origem_entrada": "bom_convertido",
            }
        )

    if apply and stats["materiais_divididos"]:
        _write(path, data)

    return stats


def main() -> int:
    parser = argparse.ArgumentParser(description="ADR-139 F5-bis: cura do pareamento de solo em CPU-TERRA-COMPAC-PN")
    group = parser.add_mutually_exclusive_group()
    group.add_argument("--dry-run", action="store_true", help="apenas relata (padrão)")
    group.add_argument("--apply", action="store_true", help="grava a correção")
    args = parser.parse_args()

    stats = run_cure(apply=args.apply)
    modo = "APLICADO" if args.apply else "DRY-RUN (use --apply para gravar)"
    print(f"[{modo}] {stats['materiais_divididos']} material(is) dividido(s)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
