"""ADR-130 F4 — rfi-r02, cluster 5: grafo de sinergia real para 11 CPUs
pesquisados em paralelo (3 famílias distintas de equipamento/processo).

TDD: testes escritos antes de popular os 11 arquivos reais.

Famílias:

  - ESCO-CARGA rfi (E0007+E0016, 4 CPUs): mesmo padrão de processo já validado
    no piloto mendeslobo — escavadeira 22t é o gargalo volumétrico (fórmula
    caçamba×enchimento×ciclo×eficiência reconcilia <1%), frota de caminhões
    14m³ tem folga estrutural (N unidades dimensionadas acima do mínimo).
  - E0016 sozinha (ATI-002/004, limpeza de camada vegetal, 2 CPUs): composição
    SICRO análoga (5502985) confirma o processo mas sem número exato — sem
    fonte firme o bastante para forward, calibração reversa.
  - E0026 sozinha (ATI-010 canaleta, ATI-059 dreno, 2 CPUs): canaleta é
    plausível pela geometria mas sem confirmação numérica direta; dreno de
    pavimento tem gargalo real no processo de instalação (mão de
    obra/logística), não na escavação — ambos calibração reversa.
  - E0008+E0010+E0028+E0035 (ATI-053/054/055, subleito/sub-base/base, 3
    CPUs): fonte SICRO (composição análoga 4011219) confirma textualmente que
    o rolo pé-de-carneiro é "o equipamento com menor produção horária,
    limitando a produtividade da equipe" — gargalo entre capacidades
    independentes, rolo calibrado reverso, demais elementos com folga.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

_ROOT = Path(__file__).resolve().parent.parent.parent.parent.parent
_PRODUTIVIDADES = _ROOT / "config" / "catalogos" / "rfi-r02" / "produtividades"

_ESCO_CARGA_FILES = [
    "CPU-TERRA-ESCO-CARGA-1CAT-DMT2000-PROD-001.json",
    "CPU-TERRA-ESCO-CARGA-1CAT-DMT3000-PROD-001.json",
    "CPU-TERRA-ESCO-CARGA-2CAT-DMT2000-PROD-001.json",
    "CPU-TERRA-ESCO-CARGA-2CAT-DMT3000-PROD-001.json",
]
# ATI-004 removida — Producao duplicata de ATI-002 (mesma composição/producao_horaria/
# grafo_sinergia), consolidada via CPU.producao_id_ref (ver
# test_adr130_producao_consolidacao_duplicatas.py)
_LIMPEZA_VEGETAL_FILES = ["CPU-TERRA-ATI-002-PROD-001.json"]
_E0026_SOLO_FILES = ["CPU-TERRA-ATI-010-PROD-001.json", "CPU-TERRA-ATI-059-PROD-001.json"]
# ATI-055 removida — Producao duplicata de ATI-054
_SUBLEITO_FILES = [
    "CPU-TERRA-ATI-053-PROD-001.json",
    "CPU-TERRA-ATI-054-PROD-001.json",
]
_ALL_FILES = _ESCO_CARGA_FILES + _LIMPEZA_VEGETAL_FILES + _E0026_SOLO_FILES + _SUBLEITO_FILES


def _build_validators():
    from concilium.presentation.cli._commands_manage_helpers_d import _build_schema_validators

    return _build_schema_validators(_ROOT / "config" / "schemas" / "catalog")


def _errors(validator, item: dict) -> list[str]:
    return [".".join(str(x) for x in err.absolute_path) + f" -> {err.message}" for err in validator.iter_errors(item)]


def _composicao_de(data: dict):
    """Constrói ComposicaoPadraoEquipe tolerando o campo legado
    'consumo_litros_hora' (typo pré-existente nos 4 CPUs ESCO-CARGA-rfi — o
    campo correto no modelo é 'consumo_litros_hora_estimado'; não lido por
    ComposicaoPadraoEquipe, apenas por pu_calculator via dict bruto). Bug de
    dados pré-existente, fora do escopo do grafo de sinergia — não corrigido
    aqui para não expandir o escopo desta mudança."""
    from concilium.domain.models.catalog.catalogo import ComposicaoPadraoEquipe

    raw = dict(data["composicao_padrao_equipe"])
    raw["equipamentos"] = [{k: v for k, v in eq.items() if k != "consumo_litros_hora"} for eq in raw["equipamentos"]]
    return ComposicaoPadraoEquipe(**raw)


class TestCluster5SchemaEReconciliacao:
    @pytest.mark.parametrize("filename", _ALL_FILES)
    def test_arquivo_real_tem_grafo_sinergia_valido(self, filename):
        _, prod_v, _ = _build_validators()
        data = json.loads((_PRODUTIVIDADES / filename).read_text(encoding="utf-8"))
        assert data.get("grafo_sinergia") is not None, f"{filename}: grafo_sinergia ausente"
        erros = _errors(prod_v, data)
        assert erros == [], f"{filename}: {erros}"

    @pytest.mark.parametrize("filename", _ALL_FILES)
    def test_gargalo_derivado_reconcilia_com_valor_horario(self, filename):
        from concilium.domain.models.catalog.producao import GrafoSinergiaEquipe
        from concilium.domain.services.sinergia_equipe import derivar_producao_horaria

        data = json.loads((_PRODUTIVIDADES / filename).read_text(encoding="utf-8"))
        producao_horaria = data["producao_horaria"]
        composicao = _composicao_de(data)
        grafo = GrafoSinergiaEquipe(**data["grafo_sinergia"])

        derivacao = derivar_producao_horaria(grafo, composicao)
        assert derivacao.producao_horaria_derivada is not None, f"{filename}: gargalo não computável"

        divergencia = abs(derivacao.producao_horaria_derivada - producao_horaria) / producao_horaria
        assert divergencia < 0.15, (
            f"{filename}: derivado={derivacao.producao_horaria_derivada} vs "
            f"producao_horaria={producao_horaria} (divergência {divergencia:.1%})"
        )

    @pytest.mark.parametrize("filename", _ALL_FILES)
    def test_capacidades_tem_justificativa_e_fonte_valida(self, filename):
        data = json.loads((_PRODUTIVIDADES / filename).read_text(encoding="utf-8"))
        for cap in data["grafo_sinergia"]["capacidades"]:
            assert cap.get("justificativa"), f"{filename}: {cap['elemento_id']} sem justificativa"
            assert cap["fonte"] in ("fabricante", "medicao_obra"), filename

    @pytest.mark.parametrize("filename", _ESCO_CARGA_FILES)
    def test_esco_carga_escavadeira_e_gargalo_fabricante_forward(self, filename):
        data = json.loads((_PRODUTIVIDADES / filename).read_text(encoding="utf-8"))
        grafo = data["grafo_sinergia"]
        assert grafo["gargalo_declarado"] == "E0016"
        capacidades = {c["elemento_id"]: c for c in grafo["capacidades"]}
        assert capacidades["E0016"]["fonte"] == "fabricante"
        assert capacidades["E0007"]["fonte"] == "fabricante"

    @pytest.mark.parametrize("filename", _LIMPEZA_VEGETAL_FILES)
    def test_limpeza_vegetal_e0016_sozinha_medicao_obra(self, filename):
        data = json.loads((_PRODUTIVIDADES / filename).read_text(encoding="utf-8"))
        grafo = data["grafo_sinergia"]
        assert grafo["gargalo_declarado"] == "E0016"
        assert len(grafo["capacidades"]) == 1
        assert grafo["capacidades"][0]["fonte"] == "medicao_obra"

    @pytest.mark.parametrize("filename", _E0026_SOLO_FILES)
    def test_e0026_sozinha_medicao_obra(self, filename):
        data = json.loads((_PRODUTIVIDADES / filename).read_text(encoding="utf-8"))
        grafo = data["grafo_sinergia"]
        assert grafo["gargalo_declarado"] == "E0026"
        assert len(grafo["capacidades"]) == 1
        assert grafo["capacidades"][0]["fonte"] == "medicao_obra"

    @pytest.mark.parametrize("filename", _SUBLEITO_FILES)
    def test_subleito_rolo_e_gargalo_demais_sao_fabricante(self, filename):
        data = json.loads((_PRODUTIVIDADES / filename).read_text(encoding="utf-8"))
        grafo = data["grafo_sinergia"]
        assert grafo["gargalo_declarado"] == "E0035"
        capacidades = {c["elemento_id"]: c for c in grafo["capacidades"]}
        assert capacidades["E0035"]["fonte"] == "medicao_obra"
        for elem in ("E0028", "E0010", "E0008"):
            assert capacidades[elem]["fonte"] == "fabricante", f"{filename}: {elem}"

    @pytest.mark.parametrize("filename", _ALL_FILES)
    def test_capacidades_cobrem_todos_os_equipamentos_da_composicao(self, filename):
        data = json.loads((_PRODUTIVIDADES / filename).read_text(encoding="utf-8"))
        equip_ids = {e["equip_id"] for e in data["composicao_padrao_equipe"]["equipamentos"]}
        cap_ids = {c["elemento_id"] for c in data["grafo_sinergia"]["capacidades"]}
        assert cap_ids == equip_ids, filename
