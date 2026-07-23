"""ADR-130 F4 — rfi-r02, cluster 2 (E0002+E0026+E0027): grafo de sinergia real
para 8 CPUs de bueiro celular de concreto armado moldado in loco (BSCC/BDCC/BTCC).

TDD: testes escritos antes de popular os 8 arquivos reais.

Contexto: diferente dos clusters anteriores (ESCO-CARGA: carga/transporte em
paralelo; cluster 1: escavação+assentamento em série), este é um processo de
construção civil completo (escavação → lastro → [armação+forma → concretagem]
× 3 camadas: fundo/paredes/laje superior → cura/desforma → reaterro,
DNIT 025/2025-ES).

Duas rodadas de pesquisa confirmaram que armação+forma (mão de obra, não
equipamento) é o estágio provavelmente dominante, mas não encontraram taxa de
armadura (kg de aço/m) publicada e validada para bueiro celular por classe de
carga/aterro — apenas analogias fracas (22-100 kg/m³, faixa explicitamente
marcada como "premissa a validar com calculista estrutural", não dado firme).

Decisão: calibração reversa no elemento crítico (Montador, P0037) —
capacidade_horaria = valor_horario / num_montadores, fonte="medicao_obra".
Retroescavadeira (E0026), mini escavadeira (E0027) e betoneira (E0002) usam
estimativas aproximadas (fonte="fabricante") só para confirmar que têm folga
(não são o gargalo) — não foram derivadas com o mesmo rigor, e a
justificativa deixa isso explícito.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

_ROOT = Path(__file__).resolve().parent.parent.parent.parent.parent
_PRODUTIVIDADES = _ROOT / "config" / "catalogos" / "rfi-r02" / "produtividades"

_CLUSTER2_FILES = [
    "CPU-TERRA-ATI-033-PROD-001.json",
    # ATI-034 removida — Producao duplicata de ATI-033 (mesma composição/valor_horario/
    # grafo_sinergia), consolidada via CPU.producao_id_ref (ver
    # test_adr130_producao_consolidacao_duplicatas.py)
    "CPU-TERRA-ATI-035-PROD-001.json",
    "CPU-TERRA-ATI-036-PROD-001.json",
    # ATI-037 removida — Producao duplicata de ATI-036
    "CPU-TERRA-ATI-038-PROD-001.json",
    "CPU-TERRA-ATI-039-PROD-001.json",
    "CPU-TERRA-ATI-040-PROD-001.json",
]


def _build_validators():
    from concilium.presentation.cli._commands_manage_helpers_d import _build_schema_validators

    return _build_schema_validators(_ROOT / "config" / "schemas" / "catalog")


def _errors(validator, item: dict) -> list[str]:
    return [".".join(str(x) for x in err.absolute_path) + f" -> {err.message}" for err in validator.iter_errors(item)]


class TestCluster2SchemaEReconciliacao:
    @pytest.mark.parametrize("filename", _CLUSTER2_FILES)
    def test_arquivo_real_tem_grafo_sinergia_valido(self, filename):
        _, prod_v, _ = _build_validators()
        data = json.loads((_PRODUTIVIDADES / filename).read_text(encoding="utf-8"))
        assert data.get("grafo_sinergia") is not None, f"{filename}: grafo_sinergia ausente"
        erros = _errors(prod_v, data)
        assert erros == [], f"{filename}: {erros}"

    @pytest.mark.parametrize("filename", _CLUSTER2_FILES)
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

    @pytest.mark.parametrize("filename", _CLUSTER2_FILES)
    def test_gargalo_e_o_montador_nao_o_equipamento(self, filename):
        """Confirma a hipótese de pesquisa: armação/montagem (mão de obra) é o
        elemento crítico, não retroescavadeira/mini/betoneira."""
        from concilium.domain.models.catalog.catalogo import ComposicaoPadraoEquipe
        from concilium.domain.models.catalog.producao import GrafoSinergiaEquipe
        from concilium.domain.services.sinergia_equipe import derivar_producao_horaria

        data = json.loads((_PRODUTIVIDADES / filename).read_text(encoding="utf-8"))
        composicao = ComposicaoPadraoEquipe(**data["composicao_padrao_equipe"])
        grafo = GrafoSinergiaEquipe(**data["grafo_sinergia"])
        derivacao = derivar_producao_horaria(grafo, composicao)
        assert derivacao.gargalo_derivado == "P0037", filename

    @pytest.mark.parametrize("filename", _CLUSTER2_FILES)
    def test_todos_elementos_tem_justificativa_e_fonte_valida(self, filename):
        data = json.loads((_PRODUTIVIDADES / filename).read_text(encoding="utf-8"))
        capacidades = data["grafo_sinergia"]["capacidades"]
        assert len(capacidades) == 4, filename
        for cap in capacidades:
            assert cap.get("justificativa"), f"{filename}: {cap['elemento_id']} sem justificativa"
            assert cap["fonte"] in ("fabricante", "medicao_obra"), filename

    @pytest.mark.parametrize("filename", _CLUSTER2_FILES)
    def test_montador_e_medicao_obra_demais_sao_fabricante(self, filename):
        data = json.loads((_PRODUTIVIDADES / filename).read_text(encoding="utf-8"))
        capacidades = {c["elemento_id"]: c for c in data["grafo_sinergia"]["capacidades"]}
        assert capacidades["P0037"]["fonte"] == "medicao_obra", filename
        for eid in ("E0026", "E0027", "E0002"):
            assert capacidades[eid]["fonte"] == "fabricante", f"{filename}: {eid}"

    @pytest.mark.parametrize("filename", _CLUSTER2_FILES)
    def test_gargalo_declarado_coincide_com_derivado(self, filename):
        """gargalo_declarado="P0037" foi setado explicitamente — VAL-SINERGIA-03
        (ADR-130 D2) deve confirmar, não conflitar."""
        data = json.loads((_PRODUTIVIDADES / filename).read_text(encoding="utf-8"))
        assert data["grafo_sinergia"]["gargalo_declarado"] == "P0037", filename
