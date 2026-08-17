"""ADR-139/ADR-130 — Composições de usinagem BGTC e CBUQ que CONCLUEM o preço dos usinados.

Substitui os preços opacos de `MA-BGTC-MIX` (R$ 92,50/m³) e `MA-CBUQ-FAIXA-C` (R$ 385/t)
por preços CONCLUÍDOS por composição de usinagem, com a produção horária DERIVADA pelo
grafo de sinergia (ADR-130: capacidades → gargalo → produção), não declarada à mão:

    preço = custo_horário(equipe + equipamentos + materiais) ÷ produção_derivada(grafo)

Referência física: SICRO 4ª ed. v1.1, snapshot 202604-SP (coeficientes são fixos da
edição; preços dos insumos SICRO entram como `tabela_referencia` com
`codigo_referencia_externa` e devem ser substituídos por cotações da empresa — o preço
re-conclui sozinho ao atualizar os insumos):

  - BGTC: SICRO 6416042 (usina de solos 300 t/h, brita comercial). Produção derivada:
    300 t/h ÷ 2,20 t/m³ (densidade compactada SICRO) × 0,83 (eficiência) = 113,18 m³/h.
    Cimento 88 kg/m³ (4,0% em massa). Referência de conferência: R$ 308,83/m³
    (202604-SP, com tempo fixo + FIC que NÃO modelamos → esperado ~R$ 301/m³).
  - CBUQ faixa C: SICRO 6416078 (usina gravimétrica 100/140 t/h, agregados comerciais).
    Produção derivada: (100+140)/2 = 120 t/h × 0,83 = 99,60 t/h. CAP 50/70 a 5,545% em
    massa; CAP não é cotado no SICRO (R$ 0,00) — usamos R$ 5.200/t (ANP 2025/2026 com
    impostos, faixa R$ 5.000–5.415/t). Referência: R$ 199,84/t sem CAP → com CAP
    esperado ~R$ 484/t (faixa de mercado posto-usina 2025: R$ 495–680/t).

Efeitos no catálogo `mendeslobo` (idempotente, dry-run padrão):
  1. Cria insumos SICRO-referenciados (usinas, geradores, carregadeiras, tanque,
     aquecedor, agregados, cimento/cal a granel, CAP, óleo A1, servente horário).
  2. Cria `PROD-USINAGEM-BGTC-001` e `PROD-USINAGEM-CBUQ-001` com composição completa,
     `materiais_gerados` (lado produtor — ADR-139) e `grafo_sinergia` (ADR-130) com
     capacidade justificada, dimensionamento usina→apoio e `precondicao` do ligante
     (ponte ADR-130→ADR-128/139).
  3. Reclassifica MA-BGTC-MIX/MA-CBUQ-FAIXA-C → GERACAO_INTERNA (a produção passa a
     estar modelada no catálogo — supera a decisão F1-bis "compra no recorte"),
     preserva o preço antigo em `historico_precos` e grava o preço CONCLUÍDO por
     `derivar_precos_unitarios_sbdi` após validar `resolver_producao_efetiva`
     (declarado == derivado; grafo sem VAL-SINERGIA-01).

Uso:
    PYTHONPATH=src python scripts/catalog/build_usinagem_bgtc_cbuq.py --dry-run
    PYTHONPATH=src python scripts/catalog/build_usinagem_bgtc_cbuq.py --apply
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "src"))

CAT_DIR = REPO_ROOT / "config" / "catalogos" / "mendeslobo"
_DATA_REF = "2026-07-14"
_SICRO_REF = "SICRO 202604-SP (4ª ed. v1.1)"

# ── Insumos novos (preços de referência SICRO/ANP — substituir por cotações da empresa) ──
# (codigo, tipo, descricao, unidade, preco, fonte, codigo_ref_externa)
_INSUMOS_NOVOS: list[tuple[str, str, str, str, float, str, str | None]] = [
    # Equipamentos — preco_unitario em R$/h efetivo da linha SICRO (utilização operativa aplicada)
    (
        "EQ-USINA-SOLOS-300TH",
        "EQUIPAMENTO",
        "Usina misturadora de solos 300 t/h - 44 kW",
        "h",
        375.99,
        "tabela_referencia",
        "E9615",
    ),
    (
        "EQ-USINA-ASFALTO-GRAV-120TH",
        "EQUIPAMENTO",
        "Usina de asfalto a quente gravimétrica 100/140 t/h - 260 kW",
        "h",
        1913.65,
        "tabela_referencia",
        "E9689",
    ),
    ("EQ-GERADOR-456KVA", "EQUIPAMENTO", "Grupo gerador 456 kVA", "h", 492.90, "tabela_referencia", "E9021"),
    ("EQ-GERADOR-113KVA", "EQUIPAMENTO", "Grupo gerador 113 kVA", "h", 127.01, "tabela_referencia", "E9779"),
    (
        "EQ-CARREG-PNEUS-340M3",
        "EQUIPAMENTO",
        "Carregadeira de pneus 3,40 m³ - 195 kW (custo horário efetivo a 55% de utilização — SICRO)",
        "h",
        421.60,
        "tabela_referencia",
        "E9511",
    ),
    (
        "EQ-CARREG-PNEUS-172M3",
        "EQUIPAMENTO",
        "Carregadeira de pneus 1,72 m³ - 113 kW (custo horário efetivo a 86% de utilização — SICRO)",
        "h",
        199.69,
        "tabela_referencia",
        "E9584",
    ),
    (
        "EQ-TANQUE-ASFALTO-30000L",
        "EQUIPAMENTO",
        "Tanque de estocagem de asfalto 30.000 L",
        "h",
        95.81,
        "tabela_referencia",
        "E9558",
    ),
    (
        "EQ-AQUECEDOR-FLUIDO-12KW",
        "EQUIPAMENTO",
        "Aquecedor de fluido térmico 12 kW",
        "h",
        168.09,
        "tabela_referencia",
        "E9559",
    ),
    # Mão de obra horária (encargos inclusos — convenção SICRO)
    (
        "MO-SERVENTE-USINA-H",
        "MAO_OBRA",
        "Servente (taxa horária com encargos — apoio de usina)",
        "h",
        30.62,
        "tabela_referencia",
        "P9824",
    ),
    # Materiais (agregados comerciais / ligantes)
    ("MA-BRITA-0-PEDRISCO", "MATERIAL", "Brita 0 (pedrisco)", "m³", 184.71, "tabela_referencia", "M1098"),
    (
        "MA-BRITA-1-SICRO",
        "MATERIAL",
        "Brita 1 (referência SICRO p/ usinagem)",
        "m³",
        172.79,
        "tabela_referencia",
        "M0191",
    ),
    ("MA-BRITA-2", "MATERIAL", "Brita 2", "m³", 170.77, "tabela_referencia", "M0192"),
    ("MA-BRITA-3", "MATERIAL", "Brita 3", "m³", 162.63, "tabela_referencia", "M0193"),
    ("MA-PO-DE-PEDRA", "MATERIAL", "Pó de pedra", "m³", 160.63, "tabela_referencia", "M1135"),
    (
        "MA-AREIA-MEDIA-SICRO",
        "MATERIAL",
        "Areia média (referência SICRO p/ usinagem)",
        "m³",
        140.84,
        "tabela_referencia",
        "M0028",
    ),
    (
        "MA-CIMENTO-GRANEL-CPII",
        "MATERIAL",
        "Cimento Portland CP II-32 a granel",
        "kg",
        0.56,
        "tabela_referencia",
        "M1954",
    ),
    ("MA-CAL-HIDRATADA-GRANEL", "MATERIAL", "Cal hidratada a granel (fíler)", "kg", 0.46, "tabela_referencia", "M0344"),
    (
        "MA-CAP-50-70",
        "MATERIAL",
        "CAP 50/70 (cimento asfáltico de petróleo) — ANP 2025/2026 com impostos, faixa R$ 5.000–5.415/t",
        "t",
        5200.0,
        "cotacao_mercado",
        "M1943",
    ),
    (
        "MA-OLEO-COMBUSTIVEL-A1",
        "MATERIAL",
        "Óleo combustível tipo A1 (queima na usina)",
        "l",
        6.50,
        "tabela_referencia",
        "M1941",
    ),
]

_VH_BGTC = 113.18  # m³/h — 300 t/h ÷ 2,20 t/m³ × 0,83 (SICRO 6416042)
_VH_CBUQ = 99.60  # t/h — 120 t/h nominal médio × 0,83 (SICRO 6416078)


def _mat(insumo_id: str, coef: float, vh: float, unidade: str, just: str) -> dict[str, Any]:
    return {
        "insumo_id": insumo_id,
        "consumo_por_hora": round(coef * vh, 6),
        "unidade": unidade,
        "descricao": f"coef. SICRO {coef} × {vh} = consumo/h — {just} (ADR-139 F4 usinagem)",
        "origem_entrada": "bom_convertido",
    }


def _producao_payload_bgtc() -> dict[str, Any]:
    vh = _VH_BGTC
    return {
        "id": "PROD-USINAGEM-BGTC-001",
        "codigo": "USINAGEM-BGTC",
        "descricao": "Usinagem de BGTC (brita comercial) em usina de solos 300 t/h — composição SICRO 6416042",
        "producao_horaria": vh,
        "unidade": "m3",
        "origem": {
            "tipo": "tabela_referencia",
            "fonte_id": "SICRO-6416042",
            "data_calibracao": f"{_DATA_REF}T00:00:00+00:00",
            "referencia": f"{_SICRO_REF} — produção derivada pelo grafo de sinergia (ADR-130)",
        },
        "condicoes_calibracao": {
            "notas": "Coeficientes físicos SICRO 4ª ed. v1.1; preços de insumo substituíveis por cotação"
        },
        "qualidade": {
            "confianca_pct": 85,
            "intervalo_confianca": [0.9 * vh, 1.05 * vh],
            "quantidade_amostras": 1,
            "desvio_padrao": 0.0,
        },
        "composicao_padrao_equipe": {
            "funcoes": [{"funcao_id": "MO-SERVENTE-USINA-H", "num_pessoas": 3}],
            "equipamentos": [
                {"equip_id": "EQ-USINA-SOLOS-300TH", "num_unidades": 1},
                {"equip_id": "EQ-CARREG-PNEUS-340M3", "num_unidades": 2},
                {"equip_id": "EQ-GERADOR-113KVA", "num_unidades": 1},
            ],
            "materiais": [
                _mat("MA-BRITA-0-PEDRISCO", 0.24933, vh, "m3", "brita 0 por m³ compactado"),
                _mat("MA-BRITA-1-SICRO", 0.44733, vh, "m3", "brita 1 por m³ compactado"),
                _mat("MA-BRITA-2", 0.14667, vh, "m3", "brita 2 por m³ compactado"),
                _mat("MA-BRITA-3", 0.07333, vh, "m3", "brita 3 por m³ compactado"),
                _mat("MA-PO-DE-PEDRA", 0.49134, vh, "m3", "pó de pedra por m³ compactado"),
                _mat("MA-CIMENTO-GRANEL-CPII", 88.0, vh, "kg", "cimento 88 kg/m³ = 4,0% em massa (2,20 t/m³)"),
            ],
        },
        "materiais_gerados": [
            {
                "insumo_id": "MA-BGTC-MIX",
                "geracao_por_hora": vh,
                "unidade": "m3",
                "descricao": "BGTC usinada — produção da usina de solos, derivada pelo grafo de sinergia (ADR-139 F4)",
            }
        ],
        "grafo_sinergia": {
            "relacoes": [
                {
                    "tipo": "dimensionamento",
                    "origem": "EQ-USINA-SOLOS-300TH",
                    "destino": "EQ-CARREG-PNEUS-340M3",
                    "razao": 2.0,
                    "descricao": "2 carregadeiras 3,40 m³ a 55% de utilização por usina (SICRO 6416042)",
                },
                {
                    "tipo": "precondicao",
                    "origem": "MA-CIMENTO-GRANEL-CPII",
                    "destino": "EQ-USINA-SOLOS-300TH",
                    "descricao": "cimento a granel disponível é precondição de usinagem (ADR-128/ADR-139)",
                },
            ],
            "capacidades": [
                {
                    "elemento_id": "EQ-USINA-SOLOS-300TH",
                    "capacidade_horaria": vh,
                    "unidade": "m3",
                    "fonte": "fabricante",
                    "justificativa": (
                        "300 t/h nominal ÷ 2,20 t/m³ (densidade compactada SICRO, verificada pela soma "
                        "das massas por m³) × 0,83 (fator de eficiência SICRO) = 113,18 m³/h — SICRO 6416042"
                    ),
                }
            ],
            "gargalo_declarado": "EQ-USINA-SOLOS-300TH",
        },
        "auditoria": {
            "criado_por": "ADR-139 F4 (build_usinagem_bgtc_cbuq.py)",
            "data_criacao": f"{_DATA_REF}T00:00:00+00:00",
            "ultima_modificacao": f"{_DATA_REF}T00:00:00+00:00",
            "modificado_por": "ADR-139 F4",
            "versao": "1.0",
        },
    }


def _producao_payload_cbuq() -> dict[str, Any]:
    vh = _VH_CBUQ
    return {
        "id": "PROD-USINAGEM-CBUQ-001",
        "codigo": "USINAGEM-CBUQ-FAIXA-C",
        "descricao": (
            "Usinagem de CBUQ faixa C (agregados comerciais) em usina gravimétrica 100/140 t/h "
            "— composição SICRO 6416078"
        ),
        "producao_horaria": vh,
        "unidade": "t",
        "origem": {
            "tipo": "tabela_referencia",
            "fonte_id": "SICRO-6416078",
            "data_calibracao": f"{_DATA_REF}T00:00:00+00:00",
            "referencia": (
                f"{_SICRO_REF} — produção derivada pelo grafo de sinergia (ADR-130); CAP cotado à parte (ANP)"
            ),
        },
        "condicoes_calibracao": {
            "notas": "Coeficientes físicos SICRO 4ª ed. v1.1; CAP 5,545% em massa; preços substituíveis por cotação"
        },
        "qualidade": {
            "confianca_pct": 85,
            "intervalo_confianca": [0.9 * vh, 1.05 * vh],
            "quantidade_amostras": 1,
            "desvio_padrao": 0.0,
        },
        "composicao_padrao_equipe": {
            "funcoes": [{"funcao_id": "MO-SERVENTE-USINA-H", "num_pessoas": 4}],
            "equipamentos": [
                {"equip_id": "EQ-USINA-ASFALTO-GRAV-120TH", "num_unidades": 1},
                {"equip_id": "EQ-GERADOR-456KVA", "num_unidades": 1},
                {"equip_id": "EQ-CARREG-PNEUS-172M3", "num_unidades": 1},
                {"equip_id": "EQ-TANQUE-ASFALTO-30000L", "num_unidades": 2},
                {"equip_id": "EQ-AQUECEDOR-FLUIDO-12KW", "num_unidades": 1},
            ],
            "materiais": [
                _mat("MA-AREIA-MEDIA-SICRO", 0.02701, vh, "m3", "areia média por t de massa"),
                _mat("MA-BRITA-0-PEDRISCO", 0.14790, vh, "m3", "brita 0 por t de massa"),
                _mat("MA-BRITA-1-SICRO", 0.12218, vh, "m3", "brita 1 por t de massa"),
                _mat("MA-PO-DE-PEDRA", 0.33631, vh, "m3", "pó de pedra por t de massa"),
                _mat("MA-CAL-HIDRATADA-GRANEL", 14.4636, vh, "kg", "cal hidratada (fíler) por t de massa"),
                _mat("MA-CAP-50-70", 0.05545, vh, "t", "CAP 50/70 — teor faixa C 5,545% em massa (SICRO)"),
                _mat("MA-OLEO-COMBUSTIVEL-A1", 8.0, vh, "l", "óleo A1 de queima na usina por t de massa"),
            ],
        },
        "materiais_gerados": [
            {
                "insumo_id": "MA-CBUQ-FAIXA-C",
                "geracao_por_hora": vh,
                "unidade": "t",
                "descricao": (
                    "CBUQ faixa C usinado — produção da usina gravimétrica, derivada pelo "
                    "grafo de sinergia (ADR-139 F4)"
                ),
            }
        ],
        "grafo_sinergia": {
            "relacoes": [
                {
                    "tipo": "dimensionamento",
                    "origem": "EQ-USINA-ASFALTO-GRAV-120TH",
                    "destino": "EQ-TANQUE-ASFALTO-30000L",
                    "razao": 2.0,
                    "descricao": "2 tanques de 30.000 L por usina gravimétrica (SICRO 6416078)",
                },
                {
                    "tipo": "precondicao",
                    "origem": "MA-CAP-50-70",
                    "destino": "EQ-USINA-ASFALTO-GRAV-120TH",
                    "descricao": "CAP disponível nos tanques é precondição de usinagem (ADR-128/ADR-139)",
                },
            ],
            "capacidades": [
                {
                    "elemento_id": "EQ-USINA-ASFALTO-GRAV-120TH",
                    "capacidade_horaria": vh,
                    "unidade": "t",
                    "fonte": "fabricante",
                    "justificativa": (
                        "usina gravimétrica 100/140 t/h → nominal médio 120 t/h × 0,83 "
                        "(fator de eficiência SICRO) = 99,60 t/h — SICRO 6416078"
                    ),
                }
            ],
            "gargalo_declarado": "EQ-USINA-ASFALTO-GRAV-120TH",
        },
        "auditoria": {
            "criado_por": "ADR-139 F4 (build_usinagem_bgtc_cbuq.py)",
            "data_criacao": f"{_DATA_REF}T00:00:00+00:00",
            "ultima_modificacao": f"{_DATA_REF}T00:00:00+00:00",
            "modificado_por": "ADR-139 F4",
            "versao": "1.0",
        },
    }


_USINADOS = {
    "MA-BGTC-MIX": ("PROD-USINAGEM-BGTC-001", _producao_payload_bgtc),
    "MA-CBUQ-FAIXA-C": ("PROD-USINAGEM-CBUQ-001", _producao_payload_cbuq),
}


def _load(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8-sig"))


def _write(path: Path, data: Any) -> None:
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def _insumo_payload(row: tuple) -> dict[str, Any]:
    codigo, tipo, descricao, unidade, preco, fonte, ref = row
    payload: dict[str, Any] = {
        "codigo": codigo,
        "tipo": tipo,
        "descricao": descricao,
        "unidade": unidade,
        "preco_unitario": preco,
        "fonte_preco": fonte,
        "data_referencia_preco": _DATA_REF,
        "categoria": "PAVIMENTACAO",
        "_referencia": _SICRO_REF,
    }
    if ref:
        payload["codigo_referencia_externa"] = ref
    if tipo == "MATERIAL":
        # Agregados/ligantes comprados de fornecedor (ADR-139 D1)
        payload["origem_material"] = "AQUISICAO_EXTERNA"
    return payload


def _dir_por_tipo(tipo: str) -> str:
    return {"EQUIPAMENTO": "equipamento", "MAO_OBRA": "mao_obra", "MATERIAL": "material"}[tipo]


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


def concluir_preco(producao: dict[str, Any], insumo_index: dict[str, dict]) -> float:
    """Valida grafo (derivado == declarado) e conclui o PU total via bottom-up."""
    from concilium.application.catalog.pu_calculator import derivar_precos_unitarios_sbdi
    from concilium.domain.models.catalog.producao import Producao
    from concilium.domain.services.sinergia_equipe import resolver_producao_efetiva

    modelo = Producao.model_validate(producao)
    resolucao = resolver_producao_efetiva(modelo)
    if resolucao.fonte != "derivado" or abs(resolucao.valor - producao["producao_horaria"]) > 1e-6:
        raise ValueError(
            f"grafo de sinergia de {producao['id']} não deriva o valor declarado: "
            f"fonte={resolucao.fonte!r}, valor={resolucao.valor} × declarado="
            f"{producao['producao_horaria']} — dado inconsistente"
        )
    sbdi = derivar_precos_unitarios_sbdi(producao, insumo_index)
    total = float(sbdi.get("total") or 0)
    if total <= 0 or sbdi.get("_meta", {}).get("referencias_faltantes"):
        raise ValueError(f"conclusão de preço de {producao['id']} falhou: {sbdi.get('_meta')}")
    return round(total, 2)


def run_build(apply: bool = False) -> dict[str, Any]:
    stats: dict[str, Any] = {"insumos_criados": 0, "producoes_criadas": 0, "precos_concluidos": {}}

    for row in _INSUMOS_NOVOS:
        path = CAT_DIR / "insumos" / _dir_por_tipo(row[1]) / f"{row[0]}.json"
        if path.exists():
            continue
        stats["insumos_criados"] += 1
        print(f"  [INSUMO   ] {row[0]} ({row[1]}, R${row[4]}/{row[3]}, ref {row[6] or '-'})")
        if apply:
            _write(path, _insumo_payload(row))

    payloads: dict[str, dict[str, Any]] = {}
    for _insumo, (pid, builder) in _USINADOS.items():
        path = CAT_DIR / "produtividades" / f"{pid}.json"
        payloads[pid] = _load(path) if path.exists() else builder()
        if not path.exists():
            stats["producoes_criadas"] += 1
            print(
                f"  [PRODUCAO ] {pid} (vh={payloads[pid]['producao_horaria']} "
                f"{payloads[pid]['unidade']}/h, grafo de sinergia)"
            )
            if apply:
                _write(path, payloads[pid])

    # Conclusão de preço: usa o index REAL + os insumos novos (mesmo em dry-run)
    index = _insumo_index()
    for row in _INSUMOS_NOVOS:
        index.setdefault(row[0], _insumo_payload(row))

    for insumo_id, (pid, _builder) in _USINADOS.items():
        preco = concluir_preco(payloads[pid], index)
        stats["precos_concluidos"][insumo_id] = preco
        ins_path = CAT_DIR / "insumos" / "material" / f"{insumo_id}.json"
        ins = _load(ins_path)
        antigo = ins.get("preco_unitario")
        print(
            f"  [PRECO    ] {insumo_id}: R${antigo} → R${preco} (concluído por {pid}; "
            f"origem_material → GERACAO_INTERNA)"
        )
        if not apply or (ins.get("origem_material") == "GERACAO_INTERNA" and antigo == preco):
            continue
        historico = ins.setdefault("historico_precos", [])
        if antigo is not None and not any(h.get("preco_unitario") == antigo for h in historico):
            ja_concluido = ins.get("origem_material") == "GERACAO_INTERNA"
            fonte_antiga = (
                "conclusão anterior (insumos da composição reprecificados — re-conclusão ADR-139)"
                if ja_concluido
                else "legado catalogo_proprio (pré-ADR-139; abaixo da faixa SICRO — ver PR #104)"
            )
            historico.append(
                {
                    "preco_unitario": antigo,
                    "data_inicio_vigencia": str(ins.get("data_referencia_preco") or "2026-03-01"),
                    "data_fim_vigencia": _DATA_REF,
                    "fonte": fonte_antiga,
                }
            )
        ins["preco_unitario"] = preco
        ins["fonte_preco"] = "catalogo_proprio"
        ins["origem_material"] = "GERACAO_INTERNA"
        ins["data_referencia_preco"] = _DATA_REF
        ins["_conclusao_preco"] = (
            f"custo interno de produção concluído por {pid} (bottom-up ÷ produção derivada pelo "
            f"grafo de sinergia — ADR-130/ADR-139; ref. física {_SICRO_REF})"
        )
        _write(ins_path, ins)

    return stats


def main() -> int:
    parser = argparse.ArgumentParser(description="ADR-139 F4: composições de usinagem BGTC/CBUQ concluem o preço")
    group = parser.add_mutually_exclusive_group()
    group.add_argument("--dry-run", action="store_true", help="apenas relata (padrão)")
    group.add_argument("--apply", action="store_true", help="grava insumos, producoes e preços concluídos")
    args = parser.parse_args()

    stats = run_build(apply=args.apply)
    modo = "APLICADO" if args.apply else "DRY-RUN (use --apply para gravar)"
    print(
        f"[{modo}] {stats['insumos_criados']} insumo(s), {stats['producoes_criadas']} "
        f"producao(oes), preços: {stats['precos_concluidos']}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
