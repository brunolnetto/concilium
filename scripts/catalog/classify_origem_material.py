"""ADR-139 F1-bis: classificação assistida de `Insumo.origem_material`.

Classifica materiais do catálogo entre AQUISICAO_EXTERNA e GERACAO_INTERNA
(ADR-139 D1) usando evidência do próprio dado — nunca chuta (A5):

  - `fonte_preco` de compra (cotacao_mercado, tabela_referencia, negociado,
    contrato_volume, referencia_base_original) → AQUISICAO_EXTERNA. O preço vem
    de fornecedor/tabela externa; a origem física é compra.
  - Placeholder AGIS (`MA-AGIS-CPU-*`, ADR-138 §D7) → sem proposta. Não é
    material físico (o preço é o PU legado da própria CPU); classificar origem
    falsearia o dado. Permanece None até o dado ser remodelado.
  - `fonte_preco` ambígua quanto à origem física (ex.: catalogo_proprio —
    usina própria × compra de usina terceira, casos MA-BGTC-MIX/MA-CBUQ-FAIXA-C)
    → sem proposta; listado no relatório para decisão do editor de catálogo.
  - Já classificado → nunca sobrescrito (idempotente).

Nenhum material é proposto como GERACAO_INTERNA automaticamente: geração
interna exige conhecimento de canteiro (existe usina/jazida própria?) que não
está no dado — é sempre decisão explícita do editor.

Uso:
    python scripts/catalog/classify_origem_material.py --dry-run   # relatório (padrão)
    python scripts/catalog/classify_origem_material.py --apply     # grava propostas
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[2]
CATALOGOS_DIR = REPO_ROOT / "config" / "catalogos"

_CATALOGOS_ELEGIVEIS = {"mendeslobo", "rfi-r02"}

# fonte_preco cujo significado implica compra de fornecedor externo.
# planilha_rfi_r02 = cotações da planilha da proposta RFI (compra); ANTT_2026_Nordeste =
# tabela de referência de combustível (compra).
_FONTES_COMPRA = {
    "cotacao_mercado",
    "tabela_referencia",
    "negociado",
    "contrato_volume",
    "referencia_base_original",
    "planilha_rfi_r02",
    "ANTT_2026_Nordeste",
}

_AGIS_PLACEHOLDER_PREFIX = "MA-AGIS-CPU-"

# Decisões revisadas caso a caso (ADR-139 F1-bis, revisão de 2026-07-14): materiais cuja
# fonte_preco é ambígua mas cuja origem foi decidida com dossiê de evidência. Critério do
# recorte do catálogo (ADR-139 D1): origem é relativa ao contrato — a decisão acompanha o
# que o catálogo modela. Histórico: a primeira revisão classificou os usinados como
# AQUISICAO_EXTERNA (sem usina modelada); superada quando as composições de usinagem
# passaram a existir (`build_usinagem_bgtc_cbuq.py`) — a produção agora É modelada e o
# preço é concluído bottom-up com produção derivada pelo grafo de sinergia (ADR-130).
_DECISOES_REVISADAS: dict[str, tuple[str, str]] = {
    "MA-BGTC-MIX": (
        "GERACAO_INTERNA",
        "produzido por PROD-USINAGEM-BGTC-001 (usina de solos 300 t/h, SICRO 6416042); preço = custo "
        "interno concluído bottom-up ÷ produção derivada pelo grafo de sinergia",
    ),
    "MA-CBUQ-FAIXA-C": (
        "GERACAO_INTERNA",
        "produzido por PROD-USINAGEM-CBUQ-001 (usina gravimétrica 100/140 t/h, SICRO 6416078); preço = "
        "custo interno concluído bottom-up ÷ produção derivada pelo grafo de sinergia",
    ),
}


def propose_origem(insumo: dict[str, Any]) -> tuple[str | None, str]:
    """Retorna (proposta, motivo). Proposta None = não classificar automaticamente."""
    codigo = str(insumo.get("codigo") or "")
    if insumo.get("tipo") != "MATERIAL":
        return None, "não é MATERIAL — origem_material não se aplica (VAL-INSUMO-ORIGEM-01)"
    if insumo.get("origem_material"):
        return None, f"já classificado como {insumo['origem_material']!r} — não sobrescrito"
    if codigo.startswith(_AGIS_PLACEHOLDER_PREFIX):
        return None, "placeholder AGIS (ADR-138 §D7) — não é material físico, permanece sem classificação"
    if codigo in _DECISOES_REVISADAS:
        origem, motivo = _DECISOES_REVISADAS[codigo]
        return origem, f"decisão revisada (F1-bis): {motivo}"
    fonte = str(insumo.get("fonte_preco") or "")
    if fonte in _FONTES_COMPRA:
        return "AQUISICAO_EXTERNA", f"fonte_preco={fonte} implica compra de fornecedor externo"
    return None, (
        f"fonte_preco={fonte!r} é ambígua quanto à origem física (usina/jazida própria × compra) — "
        "requer revisão do editor de catálogo"
    )


def run_classification(catalogos_dir: Path = CATALOGOS_DIR, apply: bool = False) -> dict[str, int]:
    """Aplica/relata a classificação; retorna estatísticas por desfecho."""
    stats = {"classificados": 0, "placeholders": 0, "revisao_manual": 0, "ja_classificados": 0}
    relatorio: list[str] = []
    for catalogo in sorted(_CATALOGOS_ELEGIVEIS):
        mat_dir = catalogos_dir / catalogo / "insumos" / "material"
        if not mat_dir.is_dir():
            continue
        for path in sorted(mat_dir.glob("*.json")):
            insumo = json.loads(path.read_text(encoding="utf-8-sig"))
            if not isinstance(insumo, dict):
                continue
            proposta, motivo = propose_origem(insumo)
            codigo = insumo.get("codigo", path.stem)
            if proposta:
                stats["classificados"] += 1
                relatorio.append(f"  [PROPOSTA] {codigo}: {proposta} — {motivo}")
                if apply:
                    insumo["origem_material"] = proposta
                    path.write_text(json.dumps(insumo, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
            elif insumo.get("origem_material"):
                stats["ja_classificados"] += 1
            elif str(codigo).startswith(_AGIS_PLACEHOLDER_PREFIX):
                stats["placeholders"] += 1
            else:
                stats["revisao_manual"] += 1
                relatorio.append(f"  [REVISAR ] {codigo}: {motivo}")
    for linha in relatorio:
        print(linha)
    return stats


def main() -> int:
    parser = argparse.ArgumentParser(description="ADR-139 F1-bis: classificação assistida de origem_material")
    group = parser.add_mutually_exclusive_group()
    group.add_argument("--dry-run", action="store_true", help="apenas relata (padrão)")
    group.add_argument("--apply", action="store_true", help="grava as propostas nos JSONs")
    args = parser.parse_args()

    stats = run_classification(apply=args.apply)
    modo = "APLICADO" if args.apply else "DRY-RUN (use --apply para gravar)"
    print(
        f"[{modo}] {stats['classificados']} classificado(s) AQUISICAO_EXTERNA, "
        f"{stats['placeholders']} placeholder(s) AGIS mantido(s) sem classificação, "
        f"{stats['revisao_manual']} para revisão manual, {stats['ja_classificados']} já classificado(s)"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
