"""ADR-139 F4 — Enriquecimento produtor-consumidor dos catálogos (`rfi-r02` e `mendeslobo`).

Mesmo molde do enriquecimento de dados da ADR-130 F4: mapeamento declarativo por
catálogo, com justificativa registrada em cada entrada, aplicado por script idempotente
(dry-run padrão). Nada é inventado sem rastro — cada ligação produtora→material→
consumidora cita a evidência: descrição da CPU, norma DNIT (108/2009-ES aterros,
138/2010-ES reforço do subleito — revisão F1-bis de 2026-07-14 com equipamento da
composição como evidência interna: rolo pé-de-carneiro = solos, rolo liso = rocha)
ou, quando restar juízo de projeto, marcação explícita para o editor.

Materiais gerados (Insumo GERACAO_INTERNA, preço 0.0 — convenção ADR-139 D1), criados
em cada catálogo mapeado: MA-SOLO-ESCAVADO-{1,2,3}CAT.

Regras de conversão:
  - geracao_por_hora/consumo_por_hora = valor_horario da produtividade (1 m³/m³, sem
    fator de empolamento), salvo taxa explícita no mapeamento (ex.: rebaixo de 20 cm,
    m²/h × 0,20 m = m³/h).

Deliberadamente FORA (sem par produtor-consumidor defensável) — decisões registradas:
  - Valas de assentamento de tubo (ATI-043..051, unidade m de tubo): sem dado de seção
    de vala, não há conversão volumétrica honesta.
  - Supressão/destocamento/limpeza vegetal: resíduo vegetal, não material de construção.
  - Demolição de pavimento (ATI-060): gera entulho/fresado — resíduo sem reaproveitamento
    modelado neste catálogo (candidato a ADR futura de resíduos).
  - Rachão, BGTC, areia, pó de pedra, CCR: agregados/misturas usinadas — aquisição
    externa (já coberta por MaterialEquipe de compra quando aplicável).
  - Rejeito filtrado (PROD-REJEITO-COMP-EQ1..4): fornecido pela planta do cliente —
    reabastecimento EXTERNO (caso ADR-128, `taxa_reabastecimento_max`), não produção
    de atividade do contrato.
  - Regularização de subleito (m²): conforma material existente, não consome volume.
  - Base/sub-base estabilizada granulometricamente: mistura granulométrica específica,
    sem evidência de origem no dado.

Uso:
    python scripts/catalog/enrich_produtor_consumidor.py --dry-run   # padrão
    python scripts/catalog/enrich_produtor_consumidor.py --apply
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[2]
CATALOGOS_DIR = REPO_ROOT / "config" / "catalogos"

_PILHA_PADRAO_M3 = 50000.0  # bota-espera generosa; ajuste por projeto quando houver dado real

_NORMA_ATERRO_1CAT = (
    "DNIT 108/2009-ES §5.1: aterro com solo de corte/empréstimo (1ª/2ª categoria; ensaio Proctor "
    "aplica-se a solos, 3ª cat só por exceção); composição usa rolo pé-de-carneiro; 2ª categoria "
    "também admissível — pareamento de projeto decide (D5)"
)

_NORMA_REFORCO_SUBLEITO = (
    "DNIT 138/2010-ES §5.1: reforço com solos de qualidade superior à do subleito "
    "(ISC de projeto, expansão ≤ 1%), de corte selecionado ou jazida"
)

_INSUMOS_GERADOS: dict[str, str] = {
    "MA-SOLO-ESCAVADO-1CAT": (
        "Solo de 1ª categoria oriundo de corte — gerado internamente pela escavação (ADR-139 F4)"
    ),
    "MA-SOLO-ESCAVADO-2CAT": (
        "Solo de 2ª categoria oriundo de corte — gerado internamente pela escavação (ADR-139 F4)"
    ),
    "MA-SOLO-ESCAVADO-3CAT": (
        "Solo/rocha de 3ª categoria oriundo de corte — gerado internamente pela escavação "
        "(ADR-139 F4, piloto corte→aterro)"
    ),
}

# Por catálogo: caminho relativo da produtividade -> (insumo, taxa m³/h ou None=valor_horario, justificativa)
_PRODUTORAS: dict[str, dict[str, tuple[str, float | None, str]]] = {
    "rfi-r02": {
        "produtividades/CPU-TERRA-ESCO-CARGA-1CAT-DMT2000-PROD-001.json": (
            "MA-SOLO-ESCAVADO-1CAT",
            None,
            "descrição: escavação 1ª categoria",
        ),
        "produtividades/CPU-TERRA-ESCO-CARGA-1CAT-DMT3000-PROD-001.json": (
            "MA-SOLO-ESCAVADO-1CAT",
            None,
            "descrição: escavação 1ª categoria",
        ),
        "produtividades/CPU-TERRA-ESCO-CARGA-2CAT-DMT2000-PROD-001.json": (
            "MA-SOLO-ESCAVADO-2CAT",
            None,
            "descrição: escavação 2ª categoria",
        ),
        "produtividades/CPU-TERRA-ESCO-CARGA-2CAT-DMT3000-PROD-001.json": (
            "MA-SOLO-ESCAVADO-2CAT",
            None,
            "descrição: escavação 2ª categoria",
        ),
        "produtividades/CPU-TERRA-ESCO-CARGA-3CAT-DMT2000-PROD-001.json": (
            "MA-SOLO-ESCAVADO-3CAT",
            None,
            "descrição: escavação 3ª categoria",
        ),
        "produtividades/CPU-TERRA-ESCO-CARGA-3CAT-DMT3000-PROD-001.json": (
            "MA-SOLO-ESCAVADO-3CAT",
            None,
            "descrição: escavação 3ª categoria",
        ),
        "produtividades/CPU-TERRA-ATI-010-PROD-001.json": (
            "MA-SOLO-ESCAVADO-1CAT",
            None,
            "descrição: escavação de canaletas (m³) — categoria estimada 1ª, revisável",
        ),
        "produtividades/CPU-TERRA-ATI-021-PROD-001.json": (
            "MA-SOLO-ESCAVADO-1CAT",
            31.45,
            "descrição: rebaixo terreno argiloso 20 cm — 157,25 m²/h × 0,20 m = 31,45 m³/h",
        ),
    },
    "mendeslobo": {
        "producoes/PROD-ATI-011.json": (
            "MA-SOLO-ESCAVADO-1CAT",
            None,
            "descrição: escavação, carga e transporte — 1ª categoria",
        ),
        "producoes/PROD-ATI-012.json": (
            "MA-SOLO-ESCAVADO-1CAT",
            None,
            "descrição: escavação, carga e transporte — 1ª categoria",
        ),
        "producoes/PROD-ESCO-CARGA-1CAT-001.json": (
            "MA-SOLO-ESCAVADO-1CAT",
            None,
            "descrição: escavação 1ª categoria (inclui espalhamento — material entregue no destino "
            "fica disponível para compactação)",
        ),
        "producoes/PROD-ESCO-CARGA-2CAT-001.json": (
            "MA-SOLO-ESCAVADO-2CAT",
            None,
            "descrição: escavação 2ª categoria (inclui espalhamento — material entregue no destino "
            "fica disponível para compactação)",
        ),
        "producoes/PROD-ESCO-CARGA-3CAT-001.json": (
            "MA-SOLO-ESCAVADO-3CAT",
            None,
            "descrição: escavação 3ª categoria/rocha (inclui espalhamento — material entregue no "
            "destino fica disponível para compactação)",
        ),
        "produtividades/CPU-DREN-ESCAV-VALA-1CAT-PROD-001.json": (
            "MA-SOLO-ESCAVADO-1CAT",
            None,
            "descrição: escavação de vala em 1ª categoria",
        ),
    },
}

_CONSUMIDORAS: dict[str, dict[str, tuple[str, float | None, str]]] = {
    "rfi-r02": {
        "produtividades/CPU-TERRA-CORPO-ATERRO-3CAT-PROD-001.json": (
            "MA-SOLO-ESCAVADO-3CAT",
            None,
            "descrição explícita: material de 3ª categoria oriundo de corte",
        ),
        "produtividades/CPU-TERRA-COMPAC-FINAL-ROCHA-PROD-001.json": (
            "MA-SOLO-ESCAVADO-3CAT",
            None,
            "descrição: camada final de aterro de rocha (rocha = 3ª categoria)",
        ),
        "produtividades/CPU-TERRA-COMPAC-PN-PROD-001.json": (
            "MA-SOLO-ESCAVADO-1CAT",
            None,
            _NORMA_ATERRO_1CAT,
        ),
        "produtividades/CPU-TERRA-COMPAC-PI-PROD-001.json": (
            "MA-SOLO-ESCAVADO-1CAT",
            None,
            _NORMA_ATERRO_1CAT,
        ),
        "produtividades/CPU-TERRA-ATI-053-PROD-001.json": (
            "MA-SOLO-ESCAVADO-1CAT",
            None,
            _NORMA_REFORCO_SUBLEITO,
        ),
    },
    "mendeslobo": {
        "producoes/PROD-ATI-017.json": ("MA-SOLO-ESCAVADO-1CAT", None, _NORMA_ATERRO_1CAT),
        "producoes/PROD-COMPACT-ATERRO-100PN-001.json": ("MA-SOLO-ESCAVADO-1CAT", None, _NORMA_ATERRO_1CAT),
        "produtividades/CPU-TERRA-COMPAC-PN-PROD-001.json": ("MA-SOLO-ESCAVADO-1CAT", None, _NORMA_ATERRO_1CAT),
        "produtividades/CPU-TERRA-COMPAC-PI-PROD-001.json": ("MA-SOLO-ESCAVADO-1CAT", None, _NORMA_ATERRO_1CAT),
        "produtividades/CPU-TERRA-COMPAC-FINAL-ROCHA-PROD-001.json": (
            "MA-SOLO-ESCAVADO-3CAT",
            None,
            "descrição: compactação de camada final de aterro de rocha (rocha = 3ª categoria)",
        ),
        "produtividades/CPU-TERRA-CORPO-ATERRO-3CAT-PROD-001.json": (
            "MA-SOLO-ESCAVADO-3CAT",
            None,
            "descrição explícita: corpo de aterro 3ª categoria",
        ),
        "produtividades/CPU-DREN-REATERRO-COMPAC-PROD-001.json": (
            "MA-SOLO-ESCAVADO-1CAT",
            None,
            "reaterro de vala usa o solo da própria escavação da vala (par com CPU-DREN-ESCAV-VALA-1CAT)",
        ),
    },
}


def _load(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8-sig"))


def _write(path: Path, data: Any) -> None:
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def _insumo_payload(codigo: str, descricao: str) -> dict[str, Any]:
    return {
        "codigo": codigo,
        "tipo": "MATERIAL",
        "descricao": descricao,
        "unidade": "m³",
        "preco_unitario": 0.0,
        "fonte_preco": "catalogo_proprio",
        "origem_material": "GERACAO_INTERNA",
        "atributos_especificos": {
            "disponibilidade": {"estoque_inicial": 0.0, "capacidade_armazenamento": _PILHA_PADRAO_M3}
        },
        "data_referencia_preco": "2026-07-14",
        "categoria": "TERRAPLENAGEM",
    }


def run_enrichment(catalogos_dir: Path = CATALOGOS_DIR, apply: bool = False) -> dict[str, int]:
    stats = {"insumos_criados": 0, "produtoras_enriquecidas": 0, "consumidoras_enriquecidas": 0}

    for catalogo in sorted(set(_PRODUTORAS) | set(_CONSUMIDORAS)):
        cat_dir = catalogos_dir / catalogo
        if not cat_dir.is_dir():
            continue

        insumos_usados = {i for i, _, _ in _PRODUTORAS[catalogo].values()} | {
            i for i, _, _ in _CONSUMIDORAS[catalogo].values()
        }
        mat_dir = cat_dir / "insumos" / "material"
        for codigo in sorted(insumos_usados):
            path = mat_dir / f"{codigo}.json"
            if path.exists():
                continue
            stats["insumos_criados"] += 1
            print(f"  [INSUMO   ] {catalogo}: {codigo} (GERACAO_INTERNA, preço 0.0)")
            if apply:
                _write(path, _insumo_payload(codigo, _INSUMOS_GERADOS[codigo]))

        for rel, (insumo_id, taxa, justificativa) in _PRODUTORAS[catalogo].items():
            path = cat_dir / rel
            data = _load(path)
            gerados = data.setdefault("materiais_gerados", [])
            if any(g.get("insumo_id") == insumo_id for g in gerados):
                continue
            geracao = taxa if taxa is not None else data["valor_horario"]
            stats["produtoras_enriquecidas"] += 1
            print(f"  [PRODUTORA] {catalogo}: {data['id']} → {insumo_id} @ {geracao} m³/h ({justificativa})")
            if apply:
                gerados.append(
                    {
                        "insumo_id": insumo_id,
                        "geracao_por_hora": geracao,
                        "unidade": "m3",
                        "descricao": f"{justificativa} (ADR-139 F4)",
                    }
                )
                _write(path, data)

        for rel, (insumo_id, taxa, justificativa) in _CONSUMIDORAS[catalogo].items():
            path = cat_dir / rel
            data = _load(path)
            equipe = data.get("composicao_padrao_equipe") or data.get("equipe")
            if not isinstance(equipe, dict):
                print(f"  [PULADA   ] {catalogo}: {data.get('id')} sem composicao_padrao_equipe — consumo não anexado")
                continue
            materiais = equipe.setdefault("materiais", [])
            if any(m.get("insumo_id") == insumo_id for m in materiais):
                continue
            consumo = taxa if taxa is not None else data["valor_horario"]
            stats["consumidoras_enriquecidas"] += 1
            print(f"  [CONSUMIDORA] {catalogo}: {data['id']} ← {insumo_id} @ {consumo} m³/h ({justificativa})")
            if apply:
                materiais.append(
                    {
                        "insumo_id": insumo_id,
                        "consumo_por_hora": consumo,
                        "unidade": "m3",
                        "descricao": (
                            f"BOM 1 m³/m³ convertido via coeficiente × valor_horario — {justificativa} (ADR-139 F4)"
                        ),
                        "origem_entrada": "bom_convertido",
                    }
                )
                _write(path, data)

    return stats


def main() -> int:
    parser = argparse.ArgumentParser(
        description="ADR-139 F4: enriquecimento produtor-consumidor (rfi-r02 + mendeslobo)"
    )
    group = parser.add_mutually_exclusive_group()
    group.add_argument("--dry-run", action="store_true", help="apenas relata (padrão)")
    group.add_argument("--apply", action="store_true", help="grava as alterações nos JSONs")
    args = parser.parse_args()

    stats = run_enrichment(apply=args.apply)
    modo = "APLICADO" if args.apply else "DRY-RUN (use --apply para gravar)"
    print(
        f"[{modo}] {stats['insumos_criados']} insumo(s) criado(s), "
        f"{stats['produtoras_enriquecidas']} produtora(s) e "
        f"{stats['consumidoras_enriquecidas']} consumidora(s) enriquecida(s)"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
