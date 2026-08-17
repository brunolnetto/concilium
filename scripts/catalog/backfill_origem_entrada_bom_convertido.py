"""ADR-139 F1: backfill de `MaterialEquipe.origem_entrada = "bom_convertido"`.

A migração da ADR-138 Fase 2 (`migrate_composicao_itens_material.py`) criou 33
entradas `MaterialEquipe` em 30 Producoes de `mendeslobo` a partir do BOM de
`composicao_itens` (conversão `consumo_por_hora = coeficiente × producao_horaria`),
sem nenhum sinal de proveniência no dado — a nota de design da ADR-138 §D7.

A ADR-139 D2 introduz `origem_entrada: "consumo_operacional" | "bom_convertido"`.
Este script marca como `bom_convertido` toda entrada `MaterialEquipe` ainda não
classificada (`origem_entrada` ausente) nos catálogos elegíveis. O backfill é
determinístico porque, verificado no censo da ADR-139, TODAS as entradas
`MaterialEquipe` hoje existentes em `mendeslobo` (33) vieram daquela migração —
não havia consumo operacional pré-existente. Entradas já classificadas nunca
são sobrescritas (o script é idempotente).

Uso:
    # Ver o que seria alterado, sem tocar nos arquivos (padrão):
    python scripts/catalog/backfill_origem_entrada_bom_convertido.py --dry-run

    # Aplicar de fato:
    python scripts/catalog/backfill_origem_entrada_bom_convertido.py --apply
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[2]
CATALOGOS_DIR = REPO_ROOT / "config" / "catalogos"

# ADR-139 F1: apenas mendeslobo recebeu entradas MaterialEquipe da ADR-138 F2
# (rfi-r02 tem zero; samples/test não foram migrados — ver ADR-138 §D4/§D6).
_CATALOGOS_ELEGIVEIS = {"mendeslobo"}


def _load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8-sig"))


def _write_json(path: Path, data: Any) -> None:
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def _backfill_producao(data: dict[str, Any]) -> int:
    """Marca entradas `materiais` sem classificação; retorna quantas foram marcadas."""
    equipe = data.get("composicao_padrao_equipe") or data.get("equipe") or {}
    materiais = equipe.get("materiais") or []
    marcadas = 0
    for entrada in materiais:
        if not isinstance(entrada, dict):
            continue
        if entrada.get("origem_entrada"):
            continue  # nunca sobrescreve classificação existente
        entrada["origem_entrada"] = "bom_convertido"
        marcadas += 1
    return marcadas


def run_backfill(catalogos_dir: Path = CATALOGOS_DIR, apply: bool = False) -> dict[str, int]:
    """Executa o backfill sobre os catálogos elegíveis; retorna estatísticas."""
    stats = {"arquivos_alterados": 0, "entradas_marcadas": 0}
    for catalogo in sorted(_CATALOGOS_ELEGIVEIS):
        cat_dir = catalogos_dir / catalogo
        if not cat_dir.is_dir():
            continue
        for path in sorted(cat_dir.rglob("*.json")):
            data = _load_json(path)
            if not isinstance(data, dict) or not ("composicao_padrao_equipe" in data or "equipe" in data):
                continue
            marcadas = _backfill_producao(data)
            if not marcadas:
                continue
            stats["arquivos_alterados"] += 1
            stats["entradas_marcadas"] += marcadas
            if apply:
                _write_json(path, data)
    return stats


def main() -> int:
    parser = argparse.ArgumentParser(
        description="ADR-139 F1: marca MaterialEquipe da migração ADR-138 F2 como bom_convertido"
    )
    group = parser.add_mutually_exclusive_group()
    group.add_argument("--dry-run", action="store_true", help="apenas relata (padrão)")
    group.add_argument("--apply", action="store_true", help="grava as alterações nos JSONs")
    args = parser.parse_args()

    stats = run_backfill(apply=args.apply)
    modo = "APLICADO" if args.apply else "DRY-RUN (use --apply para gravar)"
    print(
        f"[{modo}] {stats['arquivos_alterados']} arquivo(s) com alteração, "
        f"{stats['entradas_marcadas']} entrada(s) MaterialEquipe marcada(s) como bom_convertido"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
