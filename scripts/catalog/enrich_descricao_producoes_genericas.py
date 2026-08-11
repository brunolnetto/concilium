"""Enriquece `descricao` genérica ("Produção CPU-X") das produtividades do mendeslobo.

Diagnóstico (investigação producoes/produtividades, 2026-08-11): 123 dos 169 registros
de produtividade do mendeslobo — 92% de `produtividades/` — tinham `descricao` igual a
apenas `"Produção CPU-<CODIGO>"`: eco do próprio código/id, sem nenhuma informação nova
(viola o `Field(description=...)` de `Producao.descricao`, que exige identificar a
atividade concreta, não repetir o código). Nenhum desses 123 registros tem
`origem.referencia` rico nem `condicoes_calibracao.notas` — `origem` é a string bare
"PROPRIA" em todos os 123 — então as duas fontes recomendadas na investigação
(condicoes_calibracao.notas / origem.referencia) não existem aqui. A única fonte real
disponível é:
  1. a `descricao` da CPU associada (código sem o sufixo `-PROD-NNN`);
  2. a composição de equipe já presente no próprio arquivo (funcoes/equipamentos) —
     que a CPU (pós-ADR-053) NÃO carrega mais, logo incluir a composição aqui é
     informação genuinamente NOVA, não uma repetição do que já está na CPU.

Formato gerado: "<descricao da CPU> — equipe padrão: <funções>; equipamentos: <equip>."

Uso:
    PYTHONPATH=src python scripts/catalog/enrich_descricao_producoes_genericas.py --dry-run
    PYTHONPATH=src python scripts/catalog/enrich_descricao_producoes_genericas.py --apply
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "src"))
sys.path.insert(0, str(REPO_ROOT))

CAT_DIR = REPO_ROOT / "config" / "catalogos" / "mendeslobo"

_CODIGO_CPU_RE = re.compile(r"^(CPU-[A-Z0-9-]+)-PROD-\d+$")
_DESCRICAO_GENERICA_PREFIXO = "Produção CPU-"


def _load(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8-sig"))


def _write(path: Path, data: Any) -> None:
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def _cpu_index() -> dict[str, dict]:
    index: dict[str, dict] = {}
    for p in (CAT_DIR / "cpus").glob("*.json"):
        doc = _load(p)
        if isinstance(doc, dict) and doc.get("codigo"):
            index[doc["codigo"]] = doc
    return index


def _insumo_index() -> dict[str, dict]:
    """Índice codigo → insumo (mão de obra + equipamento — os dois tipos que aparecem
    em composicao_padrao_equipe.funcoes/equipamentos)."""
    index: dict[str, dict] = {}
    for sub in ("mao_obra", "equipamento"):
        d = CAT_DIR / "insumos" / sub
        if d.is_dir():
            for p in d.glob("*.json"):
                doc = _load(p)
                if isinstance(doc, dict) and doc.get("codigo"):
                    index[doc["codigo"]] = doc
    return index


def _resumo_composicao(itens: list[dict], id_key: str, qty_key: str, insumos: dict[str, dict]) -> str:
    partes = []
    for item in itens:
        ref_id = item.get(id_key, "")
        qtd = item.get(qty_key) or 1
        nome = insumos.get(ref_id, {}).get("descricao") or ref_id
        prefixo = f"{qtd:g}× " if qtd != 1 else ""
        partes.append(f"{prefixo}{nome}")
    return " + ".join(partes)


def _nova_descricao(producao: dict, cpu: dict, insumos: dict[str, dict]) -> str:
    cpe = producao.get("composicao_padrao_equipe") or {}
    funcoes = _resumo_composicao(cpe.get("funcoes") or [], "funcao_id", "num_pessoas", insumos)
    equipamentos = _resumo_composicao(cpe.get("equipamentos") or [], "equip_id", "num_unidades", insumos)

    base = cpu.get("descricao") or producao.get("codigo", "")
    extras = []
    if funcoes:
        extras.append(f"equipe padrão: {funcoes}")
    if equipamentos:
        extras.append(f"equipamentos: {equipamentos}")
    return f"{base} — {'; '.join(extras)}" if extras else base


def run_enrich(apply: bool = False) -> dict[str, Any]:
    stats: dict[str, Any] = {"descricoes_atualizadas": 0, "sem_cpu_associada": 0}
    cpus = _cpu_index()
    insumos = _insumo_index()

    for path in sorted((CAT_DIR / "produtividades").glob("*.json")):
        data = _load(path)
        descricao = data.get("descricao", "")
        if not descricao.startswith(_DESCRICAO_GENERICA_PREFIXO):
            continue

        m = _CODIGO_CPU_RE.match(data.get("id", ""))
        cpu_codigo = m.group(1) if m else None
        cpu = cpus.get(cpu_codigo) if cpu_codigo else None
        if cpu is None:
            stats["sem_cpu_associada"] += 1
            print(f"  [SEM CPU  ] {data.get('id')} — descricao genérica não alterada")
            continue

        nova = _nova_descricao(data, cpu, insumos)
        if nova == descricao:
            continue
        stats["descricoes_atualizadas"] += 1
        print(f"  [DESCRICAO] {data['id']}: {descricao!r} → {nova!r}")
        if apply:
            data["descricao"] = nova
            _write(path, data)

    return stats


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Enriquece descricao genérica ('Produção CPU-X') das produtividades do mendeslobo"
    )
    group = parser.add_mutually_exclusive_group()
    group.add_argument("--dry-run", action="store_true", help="apenas relata (padrão)")
    group.add_argument("--apply", action="store_true", help="grava as alterações")
    args = parser.parse_args()

    stats = run_enrich(apply=args.apply)
    modo = "APLICADO" if args.apply else "DRY-RUN (use --apply para gravar)"
    print(
        f"\n[{modo}] {stats['descricoes_atualizadas']} descricao(ões) enriquecida(s), "
        f"{stats['sem_cpu_associada']} sem CPU associada"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
