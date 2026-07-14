"""ADR-139 F4-quater — rfi-r02: usinagem própria de CBUQ + restauração do BOM das CPUs.

Diagnóstico (censo no PR #104): o rfi-r02 tem o inventário de materiais LIMPO
(M0001–M0037, descrições corretas — o mendeslobo herdou esses dados com códigos
embaralhados), mas **38/41 materiais são órfãos**: as CPUs não declaram BOM — o custo
de MATERIAL dessas CPUs é zero hoje (CBUQ, TSD, BGTC, CCR, tubos, piso, guias…).

Parte 1 — Usinagem própria de CBUQ (evidência: a usina de asfalto E0043 JÁ existe no
catálogo rfi-r02, a R$ 392/h — dado da casa): `PROD-USINAGEM-CBUQ-RFI-001` com a
física SICRO 6416078 (99,60 t/h = 120 × 0,83, derivada pelo grafo de sinergia) e
equipamentos da casa onde existem (E0043 usina, E0014 carregadeira, E0053 gerador) +
complementos SICRO (tanques, aquecedor, servente-h, cal, óleo A1). Materiais da casa:
areia M0002, pedrisco M0004, brita M0005, pó M0008, CAP M0012 (R$ 6.091/t da planilha).
Nota de leitura da numeração comercial da planilha ("Brita 01 (Pedrisco)"…"Brita 04
(Rachão)"): 01=brita 0, 02=brita 1, 03=brita 2, 04=rachão — pedrisco e rachão nas
pontas ancoram a leitura. Gera `MA-CBUQ-FAIXA-C` (GERACAO_INTERNA, preço CONCLUÍDO
bottom-up ÷ produção derivada). BGTC permanece comprada (M0010) — não há usina de
solos no rfi (mesmo critério do recorte aplicado no mendeslobo, invertido).

Parte 2 — Restauração de BOM por física documentada (mapeamento declarativo,
justificativa por entrada; `origem_entrada="bom_convertido"`):
  1 m³/m³ ou 1 m/m (identidade física): CCR, BGTC, pó de pedra, rachão compactado,
  tubos PVC/concreto por metro, piso, guia, manta; espessura×densidade: CBUQ 3 cm ×
  2,4 t/m³ = 0,072 t/m²; coeficientes da CPU gêmea mendeslobo (dado ADR-138): pintura
  de ligação 0,39 kg/m², TSD 1,0 kg/m² de emulsão.

Deliberadamente FORA (sem evidência de coeficiente): ATI-047 (tubo PBA 150 mm sem
insumo correspondente), corpos celulares BSCC/BDCC/BTCC (moldados in loco — exigem
BOM de concreto/aço/forma), ATI-054 sub-base estabilizada (mistura granulométrica).

Uso:
    PYTHONPATH=src python scripts/catalog/restore_bom_usinagem_rfi_r02.py --dry-run
    PYTHONPATH=src python scripts/catalog/restore_bom_usinagem_rfi_r02.py --apply
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "src"))
sys.path.insert(0, str(REPO_ROOT))

CAT_DIR = REPO_ROOT / "config" / "catalogos" / "rfi-r02"
_DATA_REF = "2026-07-14"
_VH_CBUQ = 99.60  # t/h — 120 t/h nominal médio × 0,83 (física SICRO 6416078)

_INSUMOS_NOVOS: list[dict[str, Any]] = [
    {
        "codigo": "EQ-TANQUE-ASFALTO-30000L",
        "tipo": "EQUIPAMENTO",
        "descricao": "Tanque de estocagem de asfalto 30.000 L",
        "unidade": "h",
        "preco_unitario": 95.81,
        "fonte_preco": "tabela_referencia",
        "codigo_referencia_externa": "E9558",
        "data_referencia_preco": _DATA_REF,
        "categoria": "PAVIMENTACAO",
    },
    {
        "codigo": "EQ-AQUECEDOR-FLUIDO-12KW",
        "tipo": "EQUIPAMENTO",
        "descricao": "Aquecedor de fluido térmico 12 kW",
        "unidade": "h",
        "preco_unitario": 168.09,
        "fonte_preco": "tabela_referencia",
        "codigo_referencia_externa": "E9559",
        "data_referencia_preco": _DATA_REF,
        "categoria": "PAVIMENTACAO",
    },
    {
        "codigo": "MO-SERVENTE-USINA-H",
        "tipo": "MAO_OBRA",
        "descricao": "Servente (taxa horária com encargos — apoio de usina)",
        "unidade": "h",
        "preco_unitario": 30.62,
        "fonte_preco": "tabela_referencia",
        "codigo_referencia_externa": "P9824",
        "data_referencia_preco": _DATA_REF,
        "categoria": "PAVIMENTACAO",
    },
    {
        "codigo": "MA-CAL-HIDRATADA-GRANEL",
        "tipo": "MATERIAL",
        "descricao": "Cal hidratada a granel (fíler)",
        "unidade": "kg",
        "preco_unitario": 0.46,
        "fonte_preco": "tabela_referencia",
        "codigo_referencia_externa": "M0344",
        "origem_material": "AQUISICAO_EXTERNA",
        "data_referencia_preco": _DATA_REF,
        "categoria": "PAVIMENTACAO",
    },
    {
        "codigo": "MA-OLEO-COMBUSTIVEL-A1",
        "tipo": "MATERIAL",
        "descricao": "Óleo combustível tipo A1 (queima na usina)",
        "unidade": "l",
        "preco_unitario": 6.50,
        "fonte_preco": "tabela_referencia",
        "codigo_referencia_externa": "M1941",
        "origem_material": "AQUISICAO_EXTERNA",
        "data_referencia_preco": _DATA_REF,
        "categoria": "PAVIMENTACAO",
    },
    {
        "codigo": "MA-CBUQ-FAIXA-C",
        "tipo": "MATERIAL",
        "descricao": "CBUQ faixa C usinado — gerado internamente pela usina de asfalto E0043 (ADR-139 F4-quater)",
        "unidade": "t",
        "preco_unitario": 0.0,  # concluído pelo builder abaixo
        "fonte_preco": "catalogo_proprio",
        "origem_material": "GERACAO_INTERNA",
        "data_referencia_preco": _DATA_REF,
        "categoria": "PAVIMENTACAO",
    },
]


def _mat(insumo_id: str, coef: float, vh: float, unidade: str, just: str) -> dict[str, Any]:
    return {
        "insumo_id": insumo_id,
        "consumo_por_hora": round(coef * vh, 6),
        "unidade": unidade,
        "descricao": f"coef. {coef} × {vh} = consumo/h — {just} (ADR-139 F4-quater)",
        "origem_entrada": "bom_convertido",
    }


def _producao_usinagem_cbuq() -> dict[str, Any]:
    vh = _VH_CBUQ
    return {
        "id": "PROD-USINAGEM-CBUQ-RFI-001",
        "codigo": "USINAGEM-CBUQ-FAIXA-C-RFI",
        "descricao": (
            "Usinagem de CBUQ faixa C na usina de asfalto da casa (E0043) — física SICRO 6416078, "
            "equipamentos/insumos do catálogo rfi-r02 onde existem"
        ),
        "valor_horario": vh,
        "unidade": "t",
        "origem": {
            "tipo": "tabela_referencia",
            "fonte_id": "SICRO-6416078",
            "data_calibracao": f"{_DATA_REF}T00:00:00+00:00",
            "referencia": "física SICRO 6416078; produção derivada pelo grafo de sinergia (ADR-130)",
        },
        "condicoes_calibracao": {
            "notas": (
                "Capacidade assume usina classe gravimétrica 100/140 t/h (nominal médio 120 × 0,83). "
                "CONFIRMAR a classe real da usina E0043 (R$ 392/h sugere porte menor) — se for menor, "
                "capacidade e preço re-derivam pelo grafo"
            )
        },
        "qualidade": {
            "confianca_pct": 70,
            "intervalo_confianca": [0.7 * vh, 1.05 * vh],
            "quantidade_amostras": 1,
            "desvio_padrao": 0.0,
        },
        "composicao_padrao_equipe": {
            "funcoes": [{"funcao_id": "MO-SERVENTE-USINA-H", "num_pessoas": 4}],
            "equipamentos": [
                {"equip_id": "E0043", "num_unidades": 1},
                {"equip_id": "E0053", "num_unidades": 1},
                {"equip_id": "E0014", "num_unidades": 1},
                {"equip_id": "EQ-TANQUE-ASFALTO-30000L", "num_unidades": 2},
                {"equip_id": "EQ-AQUECEDOR-FLUIDO-12KW", "num_unidades": 1},
            ],
            "materiais": [
                _mat("M0002", 0.02701, vh, "m3", "areia média por t de massa (SICRO)"),
                _mat("M0004", 0.14790, vh, "m3", "brita 0/pedrisco por t (numeração comercial: 'Brita 01 (Pedrisco)')"),
                _mat("M0005", 0.12218, vh, "m3", "brita 1 por t (numeração comercial: 'Brita 02')"),
                _mat("M0008", 0.33631, vh, "m3", "pó de pedra por t (SICRO)"),
                _mat("MA-CAL-HIDRATADA-GRANEL", 14.4636, vh, "kg", "cal hidratada (fíler) por t (SICRO)"),
                _mat("M0012", 0.05545, vh, "t", "CAP 50/70 — teor faixa C 5,545% em massa (SICRO)"),
                _mat("MA-OLEO-COMBUSTIVEL-A1", 8.0, vh, "l", "óleo A1 de queima por t (SICRO)"),
            ],
        },
        "materiais_gerados": [
            {
                "insumo_id": "MA-CBUQ-FAIXA-C",
                "geracao_por_hora": vh,
                "unidade": "t",
                "descricao": "CBUQ faixa C usinado — produção derivada pelo grafo de sinergia (ADR-139 F4-quater)",
            }
        ],
        "grafo_sinergia": {
            "relacoes": [
                {
                    "tipo": "dimensionamento",
                    "origem": "E0043",
                    "destino": "EQ-TANQUE-ASFALTO-30000L",
                    "razao": 2.0,
                    "descricao": "2 tanques de 30.000 L por usina (SICRO 6416078)",
                },
                {
                    "tipo": "precondicao",
                    "origem": "M0012",
                    "destino": "E0043",
                    "descricao": "CAP disponível nos tanques é precondição de usinagem (ADR-128/ADR-139)",
                },
            ],
            "capacidades": [
                {
                    "elemento_id": "E0043",
                    "capacidade_horaria": vh,
                    "unidade": "t",
                    "fonte": "fabricante",
                    "justificativa": (
                        "classe gravimétrica 100/140 t/h assumida → nominal médio 120 t/h × 0,83 "
                        "(eficiência SICRO) = 99,60 t/h — confirmar classe real da E0043 com o campo"
                    ),
                }
            ],
            "gargalo_declarado": "E0043",
        },
        "auditoria": {
            "criado_por": "ADR-139 F4-quater (restore_bom_usinagem_rfi_r02.py)",
            "data_criacao": f"{_DATA_REF}T00:00:00+00:00",
            "ultima_modificacao": f"{_DATA_REF}T00:00:00+00:00",
            "modificado_por": "ADR-139 F4-quater",
            "versao": "1.0",
        },
    }


# produtividade -> lista de (insumo, taxa_por_hora|None=1:1 com vh, unidade, justificativa)
_BOM: dict[str, list[tuple[str, float | None, str, str]]] = {
    "CPU-TERRA-ATI-019-PROD-001": [("M0011", None, "m3", "aterro em CCR consome CCR usinado 1 m³/m³")],
    "CPU-TERRA-ATI-020-PROD-001": [("M0008", None, "m3", "espalhamento 1 m³/m³ (pó de pedra — gêmea mendeslobo)")],
    "CPU-TERRA-ATI-022-PROD-001": [("M0009", None, "m3", "rachão compactado dedicado, 1 m³/m³")],
    "CPU-TERRA-ATI-023-PROD-001": [
        ("M0010", None, "m3", "BGTC comprada 1 m³/m³ (sem usina de solos no rfi — critério do recorte)")
    ],
    "CPU-TERRA-ATI-024-PROD-001": [("M0008", None, "m3", "espalhamento de pó de pedra 1 m³/m³")],
    "CPU-TERRA-ATI-056-PROD-001": [("M0037", None, "m2", "imprimação — insumo já expresso por m² (0,8 kg/m²)")],
    "CPU-TERRA-ATI-057-PROD-001": [
        ("M0014", 0.3185, "t", "pintura de ligação 0,39 kg/m² × 816,67 m²/h (coef. da gêmea mendeslobo, ADR-138)")
    ],
    "CPU-TERRA-ATI-058-PROD-001": [
        ("MA-CBUQ-FAIXA-C", 58.80024, "t", "CBUQ 3 cm: 0,072 t/m² (3 cm × 2,4 t/m³) × 816,67 m²/h — massa usinada")
    ],
    "CPU-TERRA-ATI-061-PROD-001": [
        ("MA-CBUQ-FAIXA-C", 5.33304, "t", "recomposição: 0,072 t/m² × 74,07 m²/h — massa usinada")
    ],
    "CPU-TERRA-ATI-062-PROD-001": [
        ("M0013", 0.277, "t", "TSD: emulsão RR-2C 1,0 kg/m² × 277 m²/h (coef. da gêmea mendeslobo)")
    ],
    "CPU-TERRA-ATI-063-PROD-001": [("M0031", None, "m2", "piso intertravado 1 m²/m²")],
    "CPU-TERRA-ATI-064-PROD-001": [("M0032", None, "m", "guia de concreto 1 m/m")],
    "CPU-TERRA-ATI-069-PROD-001": [("M0033", None, "m2", "manta geotêxtil 1 m²/m²")],
    "CPU-TERRA-ATI-043-PROD-001": [("M0015", None, "m", "tubo PVC PBA 50 mm — 1 m/m")],
    "CPU-TERRA-ATI-044-PROD-001": [("M0016", None, "m", "tubo PVC PBA 75 mm — 1 m/m")],
    "CPU-TERRA-ATI-045-PROD-001": [("M0017", None, "m", "tubo PVC PBA 100 mm — 1 m/m")],
    "CPU-TERRA-ATI-049-PROD-001": [("M0020", None, "m", "tubo PVC DEFOFO 200 mm — 1 m/m")],
    "CPU-TERRA-ATI-050-PROD-001": [("M0021", None, "m", "tubo PVC DEFOFO 250 mm — 1 m/m")],
    "CPU-TERRA-ATI-051-PROD-001": [("M0022", None, "m", "tubo PVC DEFOFO 300 mm — 1 m/m")],
    "CPU-TERRA-ATI-025-PROD-001": [("M0023", None, "m", "corpo BSTC D=1,00 PA1 — tubo 1 m/m (berço/reaterro fora)")],
    "CPU-TERRA-ATI-027-PROD-001": [("M0025", None, "m", "corpo BSTC D=1,20 PA2 — tubo 1 m/m")],
    "CPU-TERRA-ATI-029-PROD-001": [("M0027", None, "m", "corpo BDTC D=1,00 PA1 — tubo 1 m/m")],
    "CPU-TERRA-ATI-031-PROD-001": [("M0029", None, "m", "corpo BDTC D=1,20 PA2 — tubo 1 m/m")],
    "CPU-TERRA-ATI-032-PROD-001": [("M0030", None, "m", "corpo BTTC D=1,20 PA2 — tubo 1 m/m")],
}


def _load(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8-sig"))


def _write(path: Path, data: Any) -> None:
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def _insumo_index() -> dict[str, dict]:
    index: dict[str, dict] = {}
    for sub in ("material", "equipamento", "mao_obra"):
        d = CAT_DIR / "insumos" / sub
        if d.is_dir():
            for p in d.glob("*.json"):
                doc = _load(p)
                if isinstance(doc, dict) and doc.get("codigo"):
                    index[doc["codigo"]] = doc
    return index


def _dir_por_tipo(tipo: str) -> str:
    return {"EQUIPAMENTO": "equipamento", "MAO_OBRA": "mao_obra", "MATERIAL": "material"}[tipo]


def run_restore(apply: bool = False) -> dict[str, Any]:
    from scripts.catalog.build_usinagem_bgtc_cbuq import concluir_preco

    stats: dict[str, Any] = {"insumos_criados": 0, "producoes_criadas": 0, "bom_entradas": 0, "preco_cbuq": None}

    for payload in _INSUMOS_NOVOS:
        path = CAT_DIR / "insumos" / _dir_por_tipo(payload["tipo"]) / f"{payload['codigo']}.json"
        if path.exists():
            continue
        stats["insumos_criados"] += 1
        print(f"  [INSUMO   ] {payload['codigo']} (R${payload['preco_unitario']}/{payload['unidade']})")
        if apply:
            _write(path, payload)

    prod_path = CAT_DIR / "producoes" / "PROD-USINAGEM-CBUQ-RFI-001.json"
    producao = _load(prod_path) if prod_path.exists() else _producao_usinagem_cbuq()
    if not prod_path.exists():
        stats["producoes_criadas"] += 1
        print(f"  [PRODUCAO ] PROD-USINAGEM-CBUQ-RFI-001 (vh={producao['valor_horario']} t/h, grafo de sinergia)")
        if apply:
            prod_path.parent.mkdir(exist_ok=True)
            _write(prod_path, producao)

    index = _insumo_index()
    for payload in _INSUMOS_NOVOS:
        index.setdefault(payload["codigo"], payload)
    preco = concluir_preco(producao, index)
    stats["preco_cbuq"] = preco
    ins_path = CAT_DIR / "insumos" / "material" / "MA-CBUQ-FAIXA-C.json"
    ins = _load(ins_path) if ins_path.exists() else next(p for p in _INSUMOS_NOVOS if p["codigo"] == "MA-CBUQ-FAIXA-C")
    print(f"  [PRECO    ] MA-CBUQ-FAIXA-C (rfi): R${ins.get('preco_unitario')} → R${preco} (concluído)")
    if apply and ins.get("preco_unitario") != preco:
        ins = _load(ins_path)
        ins["preco_unitario"] = preco
        ins["_conclusao_preco"] = (
            "custo interno concluído por PROD-USINAGEM-CBUQ-RFI-001 (bottom-up ÷ produção derivada "
            "pelo grafo de sinergia — ADR-130/ADR-139; equipamentos da casa + física SICRO 6416078)"
        )
        _write(ins_path, ins)

    for pid, entradas in _BOM.items():
        path = CAT_DIR / "produtividades" / f"{pid}.json"
        data = _load(path)
        equipe = data.get("composicao_padrao_equipe") or data.get("equipe")
        materiais = equipe.setdefault("materiais", [])
        mudou = False
        for insumo_id, taxa, unidade, just in entradas:
            if any(m.get("insumo_id") == insumo_id for m in materiais):
                continue
            consumo = taxa if taxa is not None else data["valor_horario"]
            stats["bom_entradas"] += 1
            mudou = True
            print(f"  [BOM      ] {pid} ← {insumo_id} @ {consumo}/h ({just[:60]}…)")
            materiais.append(
                {
                    "insumo_id": insumo_id,
                    "consumo_por_hora": round(float(consumo), 6),
                    "unidade": unidade,
                    "descricao": f"{just} (ADR-139 F4-quater — restauração de BOM)",
                    "origem_entrada": "bom_convertido",
                }
            )
        if apply and mudou:
            _write(path, data)

    return stats


def main() -> int:
    parser = argparse.ArgumentParser(description="ADR-139 F4-quater: usinagem CBUQ + restauração de BOM no rfi-r02")
    group = parser.add_mutually_exclusive_group()
    group.add_argument("--dry-run", action="store_true", help="apenas relata (padrão)")
    group.add_argument("--apply", action="store_true", help="grava as alterações")
    args = parser.parse_args()

    stats = run_restore(apply=args.apply)
    modo = "APLICADO" if args.apply else "DRY-RUN (use --apply para gravar)"
    print(f"[{modo}] {stats}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
