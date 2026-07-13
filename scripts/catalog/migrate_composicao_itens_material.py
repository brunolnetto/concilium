"""ADR-138 Fase 2: migra BOM real de `CPU.composicao_itens` (MATERIAL) para
`Producao.composicao_padrao_equipe.materiais` (`MaterialEquipe`, ADR-030 D2).

Contexto: censo do catálogo `mendeslobo` (ADR-138) identificou 70 CPUs com
linhas `composicao_itens` categoria MATERIAL que são dead data hoje — a
hierarquia de fontes de precificação (NEP-032 D1, `_resolve_preco_cat_item`)
é winner-take-all: como a Fonte 1 (bottom-up via `Producao.composicao_padrao_
equipe`) já resolve MAO_OBRA/EQUIPAMENTO para essas CPUs, a Fonte 2
(`composicao_itens`) nunca é consultada — nem mesmo para MATERIAL, que fica
silenciosamente em 0.0.

Dessas 70, 40 usam um insumo placeholder sintético `MA-AGIS-CPU-<codigo>` cujo
preço é o preço unitário legado da própria CPU (não material real — migrar
duplicaria custo, contando a CPU inteira como se fosse um "material" dela
mesma). Este script EXCLUI deliberadamente essas 40 e migra apenas as 30 com
BOM real (cimento, areia, brita, tubos, emulsão asfáltica, pavers, etc.).

Fórmula de conversão (ADR-138 Fase 2, price-preserving por construção):

    consumo_por_hora = coeficiente × Producao.valor_horario

`coeficiente` é quantidade por unidade de produto da CPU; `valor_horario` (ρ)
é unidades de produto por hora; o produto é quantidade por hora — a definição
exata de `MaterialEquipe.consumo_por_hora`. Prova algébrica: a Fonte 1 calcula
`Σ(consumo_por_hora × preco_insumo) / valor_horario`; substituindo a fórmula
acima, isso se reduz a `Σ(coeficiente × preco_insumo)` — exatamente o que a
Fonte 2 já calculava direto de `composicao_itens`. Ver
docs/engineering/2-architecture/adrs/adr-138-composicao-itens-restrito-material-diesel.md
(Fase 2) para o levantamento completo.

Cada linha migrada é REMOVIDA de `composicao_itens` (mesmo padrão de
consolidação de fonte única já aplicado pela Fase 1 a MAO_OBRA/EQUIPAMENTO via
`strip_composicao_itens_mo_eq.py`) — evita a divergência silenciosa entre as
duas representações que a Fase 1 já eliminou para as outras categorias.

Escopo: exclusivamente `config/catalogos/mendeslobo` (único catálogo com
linhas MATERIAL genuínas de BOM — `rfi-r02` tem zero linhas MATERIAL em
`composicao_itens`; `samples`/`test` não são tocados, mesma justificativa de
escopo da Fase 1 — ver ADR-138 §D4/§D6/§P5).

Uso:
    # Ver o que seria alterado, sem tocar nos arquivos (padrão):
    python scripts/catalog/migrate_composicao_itens_material.py --dry-run

    # Aplicar de fato:
    python scripts/catalog/migrate_composicao_itens_material.py --apply
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[2]
CATALOGOS_DIR = REPO_ROOT / "config" / "catalogos"

# ADR-138 Fase 2: apenas mendeslobo tem linhas composicao_itens MATERIAL
# genuínas (não-placeholder) hoje — ver docstring do módulo.
_CATALOGOS_ELEGIVEIS = {"mendeslobo"}

_AGIS_PLACEHOLDER_PREFIX = "MA-AGIS-CPU-"


def _load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8-sig"))


def _write_json(path: Path, data: Any) -> None:
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def _iter_cpu_files(cat_dir: Path) -> list[Path]:
    cpus_dir = cat_dir / "cpus"
    if cpus_dir.exists() and cpus_dir.is_dir():
        return sorted(cpus_dir.glob("*.json"))
    cpus_file = cat_dir / "cpus.json"
    if cpus_file.exists():
        return [cpus_file]
    return []


def _index_producoes_by_id(cat_dir: Path) -> dict[str, Path]:
    """Indexa arquivos producoes/*.json + produtividades/*.json por `id`."""
    index: dict[str, Path] = {}
    for sub in ("producoes", "produtividades"):
        for f in (cat_dir / sub).glob("*.json"):
            try:
                raw = _load_json(f)
            except (json.JSONDecodeError, OSError):
                continue
            items = raw if isinstance(raw, list) else [raw]
            for item in items:
                if isinstance(item, dict) and item.get("id"):
                    index[item["id"]] = f
    return index


def _index_insumos_unidade(cat_dir: Path) -> dict[str, str]:
    """Mapa insumo_id -> unidade, para preencher `MaterialEquipe.unidade` (campo obrigatório)."""
    unidades: dict[str, str] = {}
    insumos_dir = cat_dir / "insumos"
    if not insumos_dir.exists():
        return unidades
    files = list(insumos_dir.glob("*.json"))
    for sub in insumos_dir.iterdir():
        if sub.is_dir():
            files.extend(sub.glob("*.json"))
    for f in files:
        try:
            raw = _load_json(f)
        except (json.JSONDecodeError, OSError):
            continue
        items = raw if isinstance(raw, list) else raw.get("insumos", [raw]) if isinstance(raw, dict) else []
        for item in items:
            if isinstance(item, dict) and item.get("codigo") and item.get("unidade"):
                unidades[item["codigo"]] = item["unidade"]
    return unidades


def _genuine_material_rows(composicao_itens: list) -> list[dict]:
    """Linhas MATERIAL cujo insumo_id NÃO é o placeholder sintético MA-AGIS-CPU-*."""
    out = []
    for item in composicao_itens:
        if not isinstance(item, dict):
            continue
        if str(item.get("categoria_custo") or "").upper() != "MATERIAL":
            continue
        insumo_id = str(item.get("insumo_id") or "")
        if insumo_id.startswith(_AGIS_PLACEHOLDER_PREFIX):
            continue
        out.append(item)
    return out


def _migrate_cpu(
    cpu: dict,
    prod_index: dict[str, Path],
    unidade_by_insumo: dict[str, str],
    prod_cache: dict[Path, dict],
    stats: dict[str, int],
    warnings: list[str],
) -> tuple[bool, Path | None, dict | None]:
    """Migra uma única CPU. Retorna (mudou, prod_path, prod_json) para escrita pelo caller.

    `prod_cache` garante que, se duas CPUs referenciarem o mesmo arquivo de
    Producao, a segunda migração parte do estado já modificado pela primeira
    (em vez de reler do disco e perder a alteração anterior).
    """
    codigo = cpu.get("codigo", "<sem código>")
    composicao_itens = cpu.get("composicao_itens")
    if not isinstance(composicao_itens, list) or not composicao_itens:
        return False, None, None

    genuine_rows = _genuine_material_rows(composicao_itens)
    if not genuine_rows:
        return False, None, None

    prod_id_ref = cpu.get("producao_id_ref")
    prod_path = prod_index.get(prod_id_ref) if prod_id_ref else None
    if prod_path is None:
        warnings.append(f"[AVISO] {codigo}: producao_id_ref='{prod_id_ref}' não encontrado — não migrado")
        return False, None, None

    if prod_path not in prod_cache:
        prod_cache[prod_path] = _load_json(prod_path)
    prod = prod_cache[prod_path]
    valor_horario = prod.get("valor_horario")
    if not valor_horario or float(valor_horario) <= 0:
        warnings.append(f"[AVISO] {codigo}: Producao '{prod_id_ref}' sem valor_horario > 0 — não migrado")
        return False, None, None
    valor_horario = float(valor_horario)

    comp = prod.get("composicao_padrao_equipe")
    if not isinstance(comp, dict):
        comp = {"funcoes": [], "equipamentos": []}
        prod["composicao_padrao_equipe"] = comp
    materiais = comp.setdefault("materiais", [])
    existentes_ids = {m.get("insumo_id") for m in materiais if isinstance(m, dict)}

    novas_materiais = 0
    rows_a_remover: list[dict] = []
    for row in genuine_rows:
        insumo_id = row["insumo_id"]
        unidade = unidade_by_insumo.get(insumo_id)
        if not unidade:
            # Não migra (e não remove) — dado incompleto no catálogo de insumos
            # não deve resultar em BOM silenciosamente perdido.
            warnings.append(
                f"[AVISO] {codigo}: insumo '{insumo_id}' sem 'unidade' no catálogo — não migrado"
            )
            continue
        if insumo_id in existentes_ids:
            # Idempotência: já migrado em execução anterior — não duplica em
            # materiais, mas a linha composicao_itens correspondente (se ainda
            # presente) é removida da mesma forma.
            rows_a_remover.append(row)
            continue
        coeficiente = float(row["coeficiente"])
        consumo_por_hora = round(coeficiente * valor_horario, 6)
        materiais.append(
            {
                "insumo_id": insumo_id,
                "consumo_por_hora": consumo_por_hora,
                "unidade": unidade,
            }
        )
        existentes_ids.add(insumo_id)
        novas_materiais += 1
        rows_a_remover.append(row)

    novo_composicao_itens = [item for item in composicao_itens if item not in rows_a_remover]
    linhas_removidas = len(composicao_itens) - len(novo_composicao_itens)

    if novas_materiais == 0 and linhas_removidas == 0:
        return False, None, None

    cpu["composicao_itens"] = novo_composicao_itens
    stats["cpus_migrados"] = stats.get("cpus_migrados", 0) + 1
    stats["materiais_adicionados"] = stats.get("materiais_adicionados", 0) + novas_materiais
    stats["linhas_removidas"] = stats.get("linhas_removidas", 0) + linhas_removidas
    print(
        f"  [MIGRA] {codigo} -> {prod_path.name}: "
        f"{novas_materiais} materiais adicionados, {linhas_removidas} linha(s) composicao_itens removida(s)"
    )
    return True, prod_path, prod


def _process_cpu_file(
    path: Path,
    prod_index: dict[str, Path],
    unidade_by_insumo: dict[str, str],
    apply: bool,
    stats: dict[str, int],
    warnings: list[str],
    prod_cache: dict[Path, dict],
    prod_writes: set[Path],
) -> None:
    raw = _load_json(path)
    cpus = raw["cpus"] if isinstance(raw, dict) and "cpus" in raw else [raw]
    mudou_arquivo = False
    for cpu in cpus:
        if not isinstance(cpu, dict):
            continue
        mudou, prod_path, _ = _migrate_cpu(cpu, prod_index, unidade_by_insumo, prod_cache, stats, warnings)
        if mudou:
            mudou_arquivo = True
            if prod_path is not None:
                prod_writes.add(prod_path)
    if mudou_arquivo and apply:
        _write_json(path, raw)


def main() -> int:
    parser = argparse.ArgumentParser(
        description="ADR-138 Fase 2: migra composicao_itens MATERIAL (BOM real) para MaterialEquipe"
    )
    parser.add_argument(
        "--dry-run", action="store_true", default=True, help="Apenas exibe o que seria alterado (padrão)"
    )
    parser.add_argument("--apply", action="store_true", help="Aplica a migração nos arquivos JSON")
    parser.add_argument("--catalog", default=None, help="Filtrar por catálogo específico (mendeslobo)")
    args = parser.parse_args()

    if args.apply:
        args.dry_run = False

    catalogos = sorted(_CATALOGOS_ELEGIVEIS)
    if args.catalog:
        if args.catalog not in _CATALOGOS_ELEGIVEIS:
            print(f"Catálogo '{args.catalog}' não é elegível para esta migração.")
            return 1
        catalogos = [args.catalog]

    print(f"{'=' * 70}")
    print("ADR-138 Fase 2 — Migração de composicao_itens MATERIAL (BOM real)")
    print(f"{'=' * 70}")

    total_stats: dict[str, int] = {}
    total_warnings: list[str] = []

    for cat_name in catalogos:
        cat_dir = CATALOGOS_DIR / cat_name
        if not cat_dir.exists():
            print(f"  [AVISO] Catálogo '{cat_name}' não encontrado em {cat_dir}")
            continue
        prod_index = _index_producoes_by_id(cat_dir)
        unidade_by_insumo = _index_insumos_unidade(cat_dir)
        stats: dict[str, int] = {}
        warnings: list[str] = []
        prod_cache: dict[Path, dict] = {}
        prod_writes: set[Path] = set()

        for f in _iter_cpu_files(cat_dir):
            _process_cpu_file(
                f, prod_index, unidade_by_insumo, not args.dry_run, stats, warnings, prod_cache, prod_writes
            )

        if not args.dry_run:
            for prod_path in prod_writes:
                _write_json(prod_path, prod_cache[prod_path])

        for k, v in stats.items():
            total_stats[k] = total_stats.get(k, 0) + v
        total_warnings.extend(warnings)

        print(f"{'-' * 70}")
        print(
            f"  {cat_name}: {stats.get('cpus_migrados', 0)} CPU(s) migrada(s), "
            f"{stats.get('materiais_adicionados', 0)} MaterialEquipe adicionada(s), "
            f"{stats.get('linhas_removidas', 0)} linha(s) composicao_itens removida(s)"
        )

    if total_warnings:
        print(f"{'-' * 70}")
        print("Avisos:")
        for w in total_warnings:
            print(f"  {w}")

    print(f"{'-' * 70}")
    print(
        f"TOTAL: {total_stats.get('cpus_migrados', 0)} CPUs, "
        f"{total_stats.get('materiais_adicionados', 0)} materiais adicionados, "
        f"{total_stats.get('linhas_removidas', 0)} linhas removidas"
    )

    if args.dry_run:
        print(f"\n{'-' * 70}")
        print("MODO DRY-RUN — nenhuma alteração aplicada. Use --apply para aplicar.")
    print(f"{'=' * 70}\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
