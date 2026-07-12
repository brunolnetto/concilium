"""ADR-130 F4 — rfi-r02, cluster 4: grafo de sinergia real para 7 CPUs sem
gargalo mecânico a pesquisar — mão de obra especializada pura.

TDD: testes escritos antes de popular os 7 arquivos reais.

Dois grupos, ambos sem etapa mecanizada relevante como elemento limitante:

  - E0001 (veículo leve de apoio) + papel de mão de obra: capacidade do papel
    primário = valor_horario / num_pessoas (calibração reversa direta); E0001
    entra apenas como fonte="fabricante" não-vinculante (nunca é o gargalo).
  - Serviços terceirizados (sem equipamento na composição): capacidade do
    papel primário = valor_horario / num_pessoas, sem segundo elemento.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

_ROOT = Path(__file__).resolve().parent.parent.parent
_PRODUTIVIDADES = _ROOT / "config" / "catalogos" / "rfi-r02" / "produtividades"

_E0001_FILES = {
    "CPU-TERRA-ATI-065-PROD-001.json": "P0064",
    "CPU-TERRA-ATI-066-PROD-001.json": "P0064",
    "CPU-TERRA-ATI-067-PROD-001.json": "P0001",
    "CPU-TERRA-ATI-069-PROD-001.json": "P0001",
}
_TERCEIRIZADO_FILES = {
    "CPU-TERRA-ATI-071-PROD-001.json": "P0037",
    "CPU-TERRA-ATI-072-PROD-001.json": "P0039",
    "CPU-TERRA-ATI-073-PROD-001.json": "P0001",
}
_ALL_FILES = list(_E0001_FILES) + list(_TERCEIRIZADO_FILES)


def _build_validators():
    from concilium.presentation.cli._commands_manage_helpers_d import _build_schema_validators

    return _build_schema_validators(_ROOT / "config" / "schemas" / "catalog")


def _errors(validator, item: dict) -> list[str]:
    return [".".join(str(x) for x in err.absolute_path) + f" -> {err.message}" for err in validator.iter_errors(item)]


class TestCluster4SchemaEReconciliacao:
    @pytest.mark.parametrize("filename", _ALL_FILES)
    def test_arquivo_real_tem_grafo_sinergia_valido(self, filename):
        _, prod_v, _ = _build_validators()
        data = json.loads((_PRODUTIVIDADES / filename).read_text(encoding="utf-8"))
        assert data.get("grafo_sinergia") is not None, f"{filename}: grafo_sinergia ausente"
        erros = _errors(prod_v, data)
        assert erros == [], f"{filename}: {erros}"

    @pytest.mark.parametrize("filename", _ALL_FILES)
    def test_gargalo_derivado_reconcilia_com_valor_horario(self, filename):
        from concilium.domain.models.catalog.catalogo import ComposicaoPadraoEquipe
        from concilium.domain.models.catalog.producao import GrafoSinergiaEquipe
        from concilium.domain.services.sinergia_equipe import derivar_producao_horaria

        data = json.loads((_PRODUTIVIDADES / filename).read_text(encoding="utf-8"))
        valor_horario = data["valor_horario"]
        composicao = ComposicaoPadraoEquipe(**data["composicao_padrao_equipe"])
        grafo = GrafoSinergiaEquipe(**data["grafo_sinergia"])

        derivacao = derivar_producao_horaria(grafo, composicao)
        assert derivacao.producao_horaria_derivada is not None, f"{filename}: gargalo não computável"

        divergencia = abs(derivacao.producao_horaria_derivada - valor_horario) / valor_horario
        assert divergencia < 0.15, (
            f"{filename}: derivado={derivacao.producao_horaria_derivada} vs "
            f"valor_horario={valor_horario} (divergência {divergencia:.1%})"
        )

    @pytest.mark.parametrize("filename", _ALL_FILES)
    def test_capacidades_tem_justificativa_e_fonte_valida(self, filename):
        data = json.loads((_PRODUTIVIDADES / filename).read_text(encoding="utf-8"))
        for cap in data["grafo_sinergia"]["capacidades"]:
            assert cap.get("justificativa"), f"{filename}: {cap['elemento_id']} sem justificativa"
            assert cap["fonte"] in ("fabricante", "medicao_obra"), filename

    @pytest.mark.parametrize(("filename", "papel"), _E0001_FILES.items())
    def test_e0001_papel_e_gargalo_declarado_medicao_obra_carro_e_fabricante(self, filename, papel):
        data = json.loads((_PRODUTIVIDADES / filename).read_text(encoding="utf-8"))
        grafo = data["grafo_sinergia"]
        assert grafo["gargalo_declarado"] == papel
        capacidades = {c["elemento_id"]: c for c in grafo["capacidades"]}
        assert capacidades[papel]["fonte"] == "medicao_obra"
        assert capacidades["E0001"]["fonte"] == "fabricante"

    @pytest.mark.parametrize(("filename", "papel"), _TERCEIRIZADO_FILES.items())
    def test_terceirizado_tem_apenas_o_papel_primario(self, filename, papel):
        data = json.loads((_PRODUTIVIDADES / filename).read_text(encoding="utf-8"))
        grafo = data["grafo_sinergia"]
        assert grafo["gargalo_declarado"] == papel
        assert len(grafo["capacidades"]) == 1
        assert grafo["capacidades"][0]["elemento_id"] == papel
        assert grafo["capacidades"][0]["fonte"] == "medicao_obra"
