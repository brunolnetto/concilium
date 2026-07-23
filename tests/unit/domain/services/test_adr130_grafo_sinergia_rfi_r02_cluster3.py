"""ADR-130 F4 — rfi-r02, cluster 3 (E0028+E0036): grafo de sinergia real para
4 CPUs de espalhamento/regularização/compactação (motoniveladora 120HP + rolo
compactador liso 10t).

TDD: testes escritos antes de popular os 4 arquivos reais.

Contexto: pesquisa encontrou dados reais para 2 das 4 operações (SINAPI 100576
para regularização de subleito argiloso; SICRO 903845 para espalhamento de
rachão), mas em nenhum caso um modelo simples de "gargalo = mínimo entre 2
capacidades independentes" reconcilia sem ajuste:

  - ATI-020 (areia/pó de pedra, camada fina): sem fonte de referência; valor
    real bem abaixo da capacidade bruta de motoniveladora observada em outras
    composições — gargalo é precisão de acabamento, não capacidade mecânica.
  - ATI-021 (rebaixo argiloso, m²): referência SINAPI 100576 (120 m²/h) fica
    ABAIXO do valor real (157,25 m²/h) — indício de que as 2 máquinas
    trabalham em "trem" sincronizado (cada coeficiente SICRO já embute tempo
    de espera mútuo), não uma fila estrita. Um modelo de mínimo simples
    subestimaria a produção real.
  - ATI-022 (rachão): único caso limpo — motoniveladora confirmada com folga
    (SICRO 903845, ~223,63 m³/h vs. real 82,03 m³/h), rolo é o gargalo real
    (sem fonte direta, calibrado reverso).
  - ATI-023 (BGTC): achado normativo forte (DER-SP proíbe motoniveladora para
    BGTC, DNIT 056/2013 impõe janela de pega de 2h) mas sem produtividade
    numérica aplicável ao equipamento real do catálogo — calibrado reverso.

Decisão: para cada operação, o elemento cuja capacidade não tem fonte sólida
o suficiente para reconciliar usa fonte="medicao_obra" (valor real como
capacidade calibrada); o outro usa fonte="fabricante" com valor
suficientemente alto para confirmar que não é o elemento limitante.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

_ROOT = Path(__file__).resolve().parent.parent.parent.parent.parent
_PRODUTIVIDADES = _ROOT / "config" / "catalogos" / "rfi-r02" / "produtividades"

_CLUSTER3_FILES = [
    "CPU-TERRA-ATI-020-PROD-001.json",
    "CPU-TERRA-ATI-021-PROD-001.json",
    "CPU-TERRA-ATI-022-PROD-001.json",
    "CPU-TERRA-ATI-023-PROD-001.json",
]


def _build_validators():
    from concilium.presentation.cli._commands_manage_helpers_d import _build_schema_validators

    return _build_schema_validators(_ROOT / "config" / "schemas" / "catalog")


def _errors(validator, item: dict) -> list[str]:
    return [".".join(str(x) for x in err.absolute_path) + f" -> {err.message}" for err in validator.iter_errors(item)]


class TestCluster3SchemaEReconciliacao:
    @pytest.mark.parametrize("filename", _CLUSTER3_FILES)
    def test_arquivo_real_tem_grafo_sinergia_valido(self, filename):
        _, prod_v, _ = _build_validators()
        data = json.loads((_PRODUTIVIDADES / filename).read_text(encoding="utf-8"))
        assert data.get("grafo_sinergia") is not None, f"{filename}: grafo_sinergia ausente"
        erros = _errors(prod_v, data)
        assert erros == [], f"{filename}: {erros}"

    @pytest.mark.parametrize("filename", _CLUSTER3_FILES)
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

    @pytest.mark.parametrize("filename", _CLUSTER3_FILES)
    def test_ambos_elementos_tem_justificativa(self, filename):
        data = json.loads((_PRODUTIVIDADES / filename).read_text(encoding="utf-8"))
        capacidades = data["grafo_sinergia"]["capacidades"]
        assert len(capacidades) == 2, filename
        for cap in capacidades:
            assert cap.get("justificativa"), f"{filename}: {cap['elemento_id']} sem justificativa"
            assert cap["fonte"] in ("fabricante", "medicao_obra"), filename

    def test_rachao_motoniveladora_e_fabricante_rolo_e_medicao_obra(self):
        """Único caso do cluster com fonte primária limpa para a motoniveladora
        (SICRO 903845) — confirma que o rolo é o elemento calibrado reverso."""
        data = json.loads((_PRODUTIVIDADES / "CPU-TERRA-ATI-022-PROD-001.json").read_text(encoding="utf-8"))
        capacidades = {c["elemento_id"]: c for c in data["grafo_sinergia"]["capacidades"]}
        assert capacidades["E0028"]["fonte"] == "fabricante"
        assert capacidades["E0036"]["fonte"] == "medicao_obra"

    @pytest.mark.parametrize("filename", _CLUSTER3_FILES)
    def test_motoniveladora_e_rolo_ambos_presentes(self, filename):
        data = json.loads((_PRODUTIVIDADES / filename).read_text(encoding="utf-8"))
        equip_ids = {e["equip_id"] for e in data["composicao_padrao_equipe"]["equipamentos"]}
        cap_ids = {c["elemento_id"] for c in data["grafo_sinergia"]["capacidades"]}
        assert equip_ids == {"E0028", "E0036"}, filename
        assert cap_ids == equip_ids, filename
