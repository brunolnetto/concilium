"""ADR-182 D5: adiciona `metodo_custo_total: "custo_total_ja_incluido"` aos
insumos MAO_OBRA de `unidade: "h"` que ainda não têm o campo formal.

Contexto: `pu_calculator._acumular_custo_mo` tratava TODO insumo MAO_OBRA com
`unidade == "h"` como all-in via heurística implícita (sem checar nenhum
campo). A ADR-182 substitui essa heurística por `custo_ja_inclui_encargos()`
(campo estruturado `metodo_custo_total`) — sem esta migração, os insumos que
dependiam só da heurística (nenhum texto "inclui encargos", nenhum campo)
regrediriam.

34 insumos migrados: séries `SV-P00XX-D/N`, `AGIS-FN-*` (mendeslobo) e
`MO-SERVENTE-USINA-H` (mendeslobo + rfi-r02) — todos com `nota`/`nota_encargos`
"inclui encargos" OU `descricao` explícita "taxa horária com encargos".

**Exclusão deliberada — 7 insumos `SV-OUV-MO-*` (mendeslobo):**
`SV-OUV-MO-SINALEIRO/OPER-ESCAV/AJUDANTE/OPER-PA/MOTOR-BASC/OPER-MOTOSSERRA/
OPER-TRAT-EST` têm `unidade: "h"` mas `atributos_especificos.memoria_calculo`
diz explicitamente o OPOSTO de all-in: *"Valor é SALÁRIO BASE (sem encargos) —
encargos aplicados via pipeline (resolver_encargo/ENCARGOS_CLT), não incluídos
aqui."* — ou seja, a heurística antiga de `pu_calculator` (unidade=="h" → all-in)
já era um bug PARA ESSES 7 códigos especificamente, silenciosamente omitindo
~106-177,7% de encargo em todo CPU que os referencia (7 códigos, 4-9 CPUs reais
cada, ver ADR-182). Migrar o campo para eles teria apenas formalizado/perpetuado
esse bug pré-existente. NÃO adicionar `metodo_custo_total` a esses 7 — deixar
`_alpha()` aplicar o encargo completo corretamente (comportamento novo e
correto, não regressão).

Não há tool MCP de rascunho que cubra edição de `atributos_especificos` de
insumo já existente (`atualizar_preco_insumo` só aceita preço/
`novos_funcoes_aplicaveis` — ADR-145 D1) — edição direta do JSON é o fluxo
real já usado nas migrações anteriores desta natureza.

Uso:
    python scripts/catalog/adr182_metodo_custo_total_h_unit.py --dry-run
    python scripts/catalog/adr182_metodo_custo_total_h_unit.py --apply
"""

from __future__ import annotations

import argparse
import glob
import json
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
CAMPO = "metodo_custo_total"
VALOR = "custo_total_ja_incluido"

# Confirmado via memoria_calculo: "Valor é SALÁRIO BASE (sem encargos) — encargos
# aplicados via pipeline" — o oposto de all-in. Ver docstring do módulo.
EXCLUIDOS = {
    "SV-OUV-MO-SINALEIRO",
    "SV-OUV-MO-OPER-ESCAV",
    "SV-OUV-MO-AJUDANTE",
    "SV-OUV-MO-OPER-PA",
    "SV-OUV-MO-MOTOR-BASC",
    "SV-OUV-MO-OPER-MOTOSSERRA",
    "SV-OUV-MO-OPER-TRAT-EST",
}


def _encontrar_alvos() -> list[Path]:
    alvos = []
    for cat_dir in sorted(glob.glob(str(REPO_ROOT / "config/catalogos/*/insumos/mao_obra"))):
        for f in sorted(glob.glob(f"{cat_dir}/*.json")):
            path = Path(f)
            try:
                d = json.loads(path.read_text(encoding="utf-8"))
            except Exception:
                continue
            if d.get("tipo") != "MAO_OBRA":
                continue
            if (d.get("unidade") or "").strip().lower() != "h":
                continue
            if d.get("codigo") in EXCLUIDOS:
                continue
            atrib = d.get("atributos_especificos") or {}
            if atrib.get(CAMPO) == VALOR:
                continue  # já migrado — idempotente
            alvos.append(path)
    return alvos


def _aplicar(path: Path) -> None:
    d = json.loads(path.read_text(encoding="utf-8"))
    atrib = d.setdefault("atributos_especificos", {})
    atrib[CAMPO] = VALOR
    novo_conteudo = json.dumps(d, indent=2, ensure_ascii=False)
    path.write_text(novo_conteudo, encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--dry-run", action="store_true")
    group.add_argument("--apply", action="store_true")
    args = parser.parse_args()

    alvos = _encontrar_alvos()
    print(f"{len(alvos)} insumo(s) a migrar:")
    for path in alvos:
        rel = path.relative_to(REPO_ROOT)
        print(f"  {rel}")

    if args.apply:
        for path in alvos:
            _aplicar(path)
        print(f"\n{len(alvos)} arquivo(s) atualizados com {CAMPO}={VALOR!r}.")
    else:
        print("\n(dry-run — nenhum arquivo alterado; rode com --apply para aplicar)")


if __name__ == "__main__":
    main()
