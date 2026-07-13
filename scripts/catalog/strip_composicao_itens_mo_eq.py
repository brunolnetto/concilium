"""ADR-138: Remove linhas MAO_OBRA/EQUIPAMENTO redundantes de CPU.composicao_itens.

Contexto: censo do catálogo `mendeslobo` (ADR-138) mostrou que 230 das 317 linhas
de composicao_itens (133 MAO_OBRA + 97 EQUIPAMENTO) são idênticas a entradas já
presentes em Producao.composicao_padrao_equipe da mesma CPU — a fonte primária
de precificação bottom-up (NEP-032 D1, Fonte 1). Verificação empírica (Step 0,
script de snapshot de preços) confirma que a Fonte 1 resolve com sucesso para
100% das CPUs de `mendeslobo` e `rfi-r02` hoje — a Fonte 2 (composicao_itens ×
preco_insumo) é dead code real nesses dois catálogos.

Este script remove exclusivamente linhas com categoria_custo em
{MAO_OBRA, EQUIPAMENTO} de composicao_itens, preservando MATERIAL e DIESEL
(que não têm outra fonte no modelo atual — Fase 2, fora de escopo aqui).

Catálogos deliberadamente EXCLUÍDOS desta migração:

  - config/catalogos/test/ — fixture viva de dezenas de testes de integração
    (via tests/conftest.py); a Fonte 1 também resolve normalmente ali (cada CPU
    embute `producao_horaria`+`composicao_padrao_equipe` sintetizados em
    Producao), então não há necessidade nem ganho de segurança em migrar.

  - config/catalogos/samples/ — ACHADO EMPÍRICO (Step 0): ao contrário de
    mendeslobo/rfi-r02, a Fonte 1 FALHA para as 11 CPUs de `samples` (os
    arquivos em samples/produtividades/*.json têm `valor_horario` mas NÃO têm
    `composicao_padrao_equipe` — custo da equipe fica 0, sbdi.total <= 0). Isso
    força 100% das CPUs de `samples` pela Fonte 2 hoje, tornando
    composicao_itens (incluindo as linhas EQUIPAMENTO) a fonte real e ativa de
    preço — não redundante. Migrar `samples` quebraria o argumento de
    "byte-idêntico" e, combinado com o fail-loud da Fase 1 (VAL-PLAN-MO-EQ-SEM-FONTE),
    faria essas 11 CPUs deixarem de ser precificadas. Ver ADR-138 §P5/§Alternativas
    Rejeitadas — fora de escopo desta migração (é um problema de dado incompleto
    em `samples`, não de redundância).

Uso:
    # Ver o que seria alterado, sem tocar nos arquivos (padrão):
    python scripts/catalog/strip_composicao_itens_mo_eq.py --dry-run

    # Aplicar de fato:
    python scripts/catalog/strip_composicao_itens_mo_eq.py --apply

    # Filtrar por catálogo específico:
    python scripts/catalog/strip_composicao_itens_mo_eq.py --catalog mendeslobo --apply
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
CATALOGOS_DIR = REPO_ROOT / "config" / "catalogos"

# Catálogos elegíveis para a migração (ADR-138 Fase 1). config/catalogos/test/ e
# config/catalogos/samples/ são deliberadamente excluídos — ver docstring do módulo.
_CATALOGOS_ELEGIVEIS = {"mendeslobo", "rfi-r02"}

_CATEGORIAS_REMOVIDAS = {"MAO_OBRA", "EQUIPAMENTO"}


def _iter_cpu_files(cat_dir: Path) -> list[Path]:
    """Retorna os arquivos que contêm CPUs para este catálogo.

    Suporta os dois layouts observados: diretório `cpus/*.json` (mendeslobo,
    rfi-r02) e arquivo único `cpus.json` (samples).
    """
    cpus_dir = cat_dir / "cpus"
    if cpus_dir.exists() and cpus_dir.is_dir():
        return sorted(cpus_dir.glob("*.json"))
    cpus_file = cat_dir / "cpus.json"
    if cpus_file.exists():
        return [cpus_file]
    return []


def _strip_categorias(itens: list, removidos_por_categoria: dict[str, int]) -> list:
    kept = []
    for item in itens:
        if not isinstance(item, dict):
            kept.append(item)
            continue
        categoria = str(item.get("categoria_custo") or "").upper()
        if categoria in _CATEGORIAS_REMOVIDAS:
            removidos_por_categoria[categoria] = removidos_por_categoria.get(categoria, 0) + 1
            continue
        kept.append(item)
    return kept


def _process_cpu_dict(cpu: dict, removidos_por_categoria: dict[str, int]) -> tuple[dict, int]:
    """Retorna (cpu_atualizado, linhas_removidas) para uma única CPU."""
    itens = cpu.get("composicao_itens")
    if not isinstance(itens, list) or not itens:
        return cpu, 0
    antes = len(itens)
    novo = _strip_categorias(itens, removidos_por_categoria)
    if len(novo) == antes:
        return cpu, 0
    cpu["composicao_itens"] = novo
    return cpu, antes - len(novo)


def _process_file(path: Path, apply: bool, removidos_por_categoria: dict[str, int]) -> tuple[int, int]:
    """Processa um arquivo (CPU única ou {'cpus': [...]}). Retorna (cpus_alterados, linhas_removidas)."""
    raw = json.loads(path.read_text(encoding="utf-8-sig"))

    cpus_alterados = 0
    linhas_removidas = 0

    if isinstance(raw, dict) and "cpus" in raw and isinstance(raw["cpus"], list):
        for cpu in raw["cpus"]:
            if not isinstance(cpu, dict):
                continue
            _, removidas = _process_cpu_dict(cpu, removidos_por_categoria)
            if removidas:
                cpus_alterados += 1
                linhas_removidas += removidas
        if apply and linhas_removidas:
            path.write_text(json.dumps(raw, ensure_ascii=False, indent=2), encoding="utf-8")
    elif isinstance(raw, dict) and "codigo" in raw:
        _, removidas = _process_cpu_dict(raw, removidos_por_categoria)
        if removidas:
            cpus_alterados += 1
            linhas_removidas += removidas
            if apply:
                path.write_text(json.dumps(raw, ensure_ascii=False, indent=2), encoding="utf-8")
    return cpus_alterados, linhas_removidas


def main() -> int:
    parser = argparse.ArgumentParser(
        description="ADR-138: remove composicao_itens MAO_OBRA/EQUIPAMENTO redundantes"
    )
    parser.add_argument(
        "--dry-run", action="store_true", default=True, help="Apenas exibe o que seria alterado (padrão)"
    )
    parser.add_argument("--apply", action="store_true", help="Aplica a remoção nos arquivos JSON")
    parser.add_argument(
        "--catalog", default=None, help="Filtrar por catálogo específico (mendeslobo|rfi-r02)"
    )
    args = parser.parse_args()

    if args.apply:
        args.dry_run = False

    catalogos = sorted(_CATALOGOS_ELEGIVEIS)
    if args.catalog:
        if args.catalog not in _CATALOGOS_ELEGIVEIS:
            print(f"Catálogo '{args.catalog}' não é elegível para esta migração (ou é 'test', que é excluído).")
            return 1
        catalogos = [args.catalog]

    total_arquivos_tocados = 0
    total_cpus_alterados = 0
    total_linhas_removidas = 0
    removidos_por_categoria: dict[str, int] = {}

    print(f"{'=' * 70}")
    print("ADR-138 — Remoção de composicao_itens MAO_OBRA/EQUIPAMENTO")
    print(f"{'=' * 70}")

    for cat_name in catalogos:
        cat_dir = CATALOGOS_DIR / cat_name
        if not cat_dir.exists():
            print(f"  [AVISO] Catálogo '{cat_name}' não encontrado em {cat_dir}")
            continue
        arquivos = _iter_cpu_files(cat_dir)
        cat_arquivos_tocados = 0
        cat_cpus_alterados = 0
        cat_linhas_removidas = 0
        for f in arquivos:
            cpus_alterados, linhas_removidas = _process_file(
                f, apply=not args.dry_run, removidos_por_categoria=removidos_por_categoria
            )
            if linhas_removidas:
                cat_arquivos_tocados += 1
                cat_cpus_alterados += cpus_alterados
                cat_linhas_removidas += linhas_removidas
        print(
            f"  {cat_name}: {cat_arquivos_tocados} arquivo(s) tocado(s), "
            f"{cat_cpus_alterados} CPU(s) alterada(s), {cat_linhas_removidas} linha(s) removida(s)"
        )
        total_arquivos_tocados += cat_arquivos_tocados
        total_cpus_alterados += cat_cpus_alterados
        total_linhas_removidas += cat_linhas_removidas

    print(f"{'-' * 70}")
    print(f"TOTAL: {total_arquivos_tocados} arquivos, {total_cpus_alterados} CPUs, {total_linhas_removidas} linhas")
    for cat, n in sorted(removidos_por_categoria.items()):
        print(f"  {cat}: {n}")

    if args.dry_run:
        print(f"\n{'-' * 70}")
        print("MODO DRY-RUN — nenhuma alteração aplicada. Use --apply para aplicar.")
    print(f"{'=' * 70}\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
