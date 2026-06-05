"""NEP-005: Reclassificação das CPUs em categoria DIVERSOS.

Uso:
    # Gerar proposta (sem aplicar):
    python scripts/reclassificar_diversos.py --dry-run

    # Aplicar reclassificações aprovadas:
    python scripts/reclassificar_diversos.py --apply

    # Filtrar por catálogo específico:
    python scripts/reclassificar_diversos.py --catalog mendeslobo --dry-run
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

# ── Config root ──────────────────────────────────────────────────────────────
REPO_ROOT = Path(__file__).resolve().parents[1]
CONFIG_ROOT = REPO_ROOT / "config"
CATALOGOS_DIR = CONFIG_ROOT / "catalogos"

# ── Keyword → categoria sugerida ─────────────────────────────────────────────
_RULES: list[tuple[list[str], str]] = [
    # Terraplenagem especial
    (["aceiro", "destoca", "destocamento", "limpeza vegeta", "capina"], "TERRAPLANAGEM_ESPECIAL"),
    # Infraestrutura geral
    (["cerca", "geotêxtil", "geotextil", "eixo", "manta", "tela", "grade"], "INFRAESTRUTURA_GERAL"),
    # Pavimentação
    (["piso", "calçada", "calcada", "intertravado", "bloquete", "paviment"], "PAVIMENTACAO"),
    # Sinalização
    (["placas", "sinaliz", "demarcaç", "demarcac"], "SINALIZACAO"),
    # Drenagem
    (["drenagem", "valeta", "sarjeta", "sarjeta", "bueiro", "boca de lobo"], "DRENAGEM"),
    # Obras de arte
    (["pontes", "viaduto", "bueiro tubular", "bueiro celular"], "OBRAS_DE_ARTE"),
]

_NOVAS_CATEGORIAS = {"TERRAPLANAGEM_ESPECIAL", "INFRAESTRUTURA_GERAL"}


def _sugerir_categoria(descricao: str) -> str | None:
    desc_lower = descricao.lower()
    for keywords, categoria in _RULES:
        if any(kw in desc_lower for kw in keywords):
            return categoria
    return None


def _processar_catalogo(catalog_path: Path) -> list[dict]:
    """Retorna lista de propostas para CPUs DIVERSOS nesse catálogo."""
    bundle = catalog_path / ".catalog_bundle.json"
    cpus_dir = catalog_path / "cpus"

    cpus: list[dict] = []
    if bundle.exists():
        try:
            data = json.loads(bundle.read_text(encoding="utf-8"))
            cpus = data.get("cpus") or []
        except Exception:
            pass
    elif cpus_dir.exists():
        for f in cpus_dir.glob("*.json"):
            try:
                cpus.append(json.loads(f.read_text(encoding="utf-8")))
            except Exception:
                pass

    propostas = []
    for cpu in cpus:
        if not isinstance(cpu, dict):
            continue
        if str(cpu.get("categoria", "")).upper() != "DIVERSOS":
            continue
        codigo = cpu.get("codigo", "?")
        descricao = cpu.get("descricao", "")
        sugestao = _sugerir_categoria(descricao)
        propostas.append({
            "catalogo": catalog_path.name,
            "codigo": codigo,
            "descricao": descricao,
            "categoria_atual": "DIVERSOS",
            "categoria_sugerida": sugestao or "MANTER_DIVERSOS",
            "arquivo": str(cpus_dir / f"{codigo}.json"),
        })
    return propostas


def _aplicar(proposta: dict) -> bool:
    """Aplica a reclassificação diretamente no arquivo JSON da CPU."""
    if proposta["categoria_sugerida"] == "MANTER_DIVERSOS":
        return False
    cpu_file = Path(proposta["arquivo"])
    if not cpu_file.exists():
        print(f"  ⚠️  Arquivo não encontrado: {cpu_file}")
        return False
    try:
        data = json.loads(cpu_file.read_text(encoding="utf-8"))
        data["categoria"] = proposta["categoria_sugerida"]
        cpu_file.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
        return True
    except Exception as e:
        print(f"  ✗ Erro ao escrever {cpu_file}: {e}")
        return False


def main() -> int:
    parser = argparse.ArgumentParser(description="Reclassificação de CPUs DIVERSOS")
    parser.add_argument("--dry-run", action="store_true", default=True,
                        help="Apenas exibe propostas sem aplicar (padrão)")
    parser.add_argument("--apply", action="store_true",
                        help="Aplica a reclassificação nos arquivos JSON")
    parser.add_argument("--catalog", default=None,
                        help="Filtrar por catálogo específico (ex: mendeslobo)")
    args = parser.parse_args()

    if args.apply:
        args.dry_run = False

    if not CATALOGOS_DIR.exists():
        print(f"Diretório de catálogos não encontrado: {CATALOGOS_DIR}")
        return 1

    cat_dirs = [d for d in CATALOGOS_DIR.iterdir() if d.is_dir() and not d.name.startswith(".")]
    if args.catalog:
        cat_dirs = [d for d in cat_dirs if d.name == args.catalog]
        if not cat_dirs:
            print(f"Catálogo '{args.catalog}' não encontrado.")
            return 1

    todas_propostas: list[dict] = []
    for cat_dir in sorted(cat_dirs):
        todas_propostas.extend(_processar_catalogo(cat_dir))

    if not todas_propostas:
        print("Nenhuma CPU DIVERSOS encontrada.")
        return 0

    # ── Relatório ────────────────────────────────────────────────────────
    sem_sugestao = [p for p in todas_propostas if p["categoria_sugerida"] == "MANTER_DIVERSOS"]
    com_sugestao = [p for p in todas_propostas if p["categoria_sugerida"] != "MANTER_DIVERSOS"]

    print(f"\n{'=' * 70}")
    print(f"RELATÓRIO DE RECLASSIFICAÇÃO — {len(todas_propostas)} CPUs DIVERSOS")
    print(f"{'=' * 70}")
    print(f"  Com sugestão de reclassificação:  {len(com_sugestao)}")
    print(f"  Sem match (manter DIVERSOS):       {len(sem_sugestao)}")

    if com_sugestao:
        print(f"\n{'─' * 70}")
        print("RECLASSIFICAÇÕES SUGERIDAS:")
        print(f"{'─' * 70}")
        for p in com_sugestao:
            marker = "✓ APLICADO" if not args.dry_run and _aplicar(p) else "→ PROPOSTA"
            print(f"  {marker}  [{p['catalogo']}] {p['codigo']}")
            print(f"           Desc: {p['descricao'][:60]}")
            print(f"           DIVERSOS → {p['categoria_sugerida']}")

    if sem_sugestao:
        print(f"\n{'─' * 70}")
        print("SEM SUGESTÃO (revisão manual necessária):")
        print(f"{'─' * 70}")
        for p in sem_sugestao:
            print(f"  [{p['catalogo']}] {p['codigo']}: {p['descricao'][:60]}")

    if args.dry_run:
        print(f"\n{'─' * 70}")
        print("MODO DRY-RUN — nenhuma alteração aplicada.")
        print("Use --apply para aplicar as reclassificações sugeridas.")

    # Salva relatório JSON para auditoria
    report_path = REPO_ROOT / "scripts" / "_reclassificar_diversos_report.json"
    report_path.write_text(
        json.dumps(todas_propostas, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(f"\nRelatório salvo em: {report_path}")
    print(f"{'=' * 70}\n")

    return 0


if __name__ == "__main__":
    sys.exit(main())
