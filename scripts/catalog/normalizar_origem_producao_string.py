"""Normaliza `Producao.origem` de string solta para o dict `OrigemProducao`.

Contexto (bug real, PR #156): 119 das 169 produções do catálogo mendeslobo
tinham `origem` como string solta (ex.: `"PROPRIA"`) em vez do dict
`{tipo, fonte_id, data_calibracao, referencia}` que o modelo `Producao.origem`
exige — legado de como foram enriquecidas com `grafo_sinergia` (ADR-179).
Isso causava `AttributeError: 'str' object has no attribute 'get'` em
`_build_producao_para_sinergia` (skill-05) sempre que a produção também tinha
`grafo_sinergia` populado — já corrigido defensivamente (a skill-05 agora
tolera o dado malformado), mas o dado em si continuava com o formato errado.

Este script corrige o dado na origem, sem perda de informação: a string
original vira `referencia`; `tipo="estimado"` (as capacidades desses CPUs
foram derivadas de especificação de equipamento/manual DNIT-SICRO2 — ADR-179 —
não calibradas contra obra real, nem vindas de planilha/tabela externa);
`fonte_id` é o próprio id da produção (não há fonte externa registrada);
`data_calibracao` é sintética (data desta normalização — não existe data de
calibração original registrada em nenhum desses arquivos).

Uso:
    uv run python scripts/catalog/normalizar_origem_producao_string.py --dry-run
    uv run python scripts/catalog/normalizar_origem_producao_string.py --apply
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "src"))
sys.path.insert(0, str(REPO_ROOT))

CAT_DIR = REPO_ROOT / "config" / "catalogos" / "mendeslobo"


def _load(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8-sig"))


def _write(path: Path, data: Any) -> None:
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def run_normalize(apply: bool = False) -> dict[str, Any]:
    stats: dict[str, Any] = {"normalizados": 0}
    agora = datetime.now(UTC).isoformat()

    for path in sorted((CAT_DIR / "produtividades").glob("*.json")):
        data = _load(path)
        origem = data.get("origem")
        if not isinstance(origem, str):
            continue

        nova_origem = {
            "tipo": "estimado",
            "fonte_id": data.get("id", ""),
            "data_calibracao": agora,
            "referencia": origem,
        }
        stats["normalizados"] += 1
        print(f"  [ORIGEM] {data.get('id')}: {origem!r} -> {nova_origem}")
        if apply:
            data["origem"] = nova_origem
            _write(path, data)

    return stats


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Normaliza Producao.origem de string solta (ex.: 'PROPRIA') para o dict OrigemProducao"
    )
    group = parser.add_mutually_exclusive_group()
    group.add_argument("--dry-run", action="store_true", help="apenas relata (padrão)")
    group.add_argument("--apply", action="store_true", help="grava as alterações")
    args = parser.parse_args()

    stats = run_normalize(apply=args.apply)
    modo = "APLICADO" if args.apply else "DRY-RUN (use --apply para gravar)"
    print(f"\n[{modo}] {stats['normalizados']} origem(ns) normalizada(s)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
