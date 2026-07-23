"""ADR-130 F4 — rfi-r02, cluster 7 (final): grafo de sinergia real para os
últimos 14 CPUs (todos singletons de 1 CPU cada), completando as 75 CPUs do
catálogo rfi-r02.

TDD: testes escritos antes de popular os 14 arquivos reais.

Destaques:

  - Família de supressão vegetal restante (ATI-001/005/007): motosserra
    domina em corte unitário de grande porte e em densidade média; escavadeira
    domina em destocamento (volume de toco/raiz, não área).
  - ATI-009/CORPO-ATERRO-3CAT: trator de esteiras 30t/440HP — gargalo em
    corte/destocamento isolado, mas com folga em espalhamento de aterro
    (rolo pé-de-carneiro permanece o gargalo, mesmo padrão de subleito/base).
  - ATI-019 (CCR): achado de possível inconsistência técnica — CCR deveria
    usar rolo liso vibratório, não pé-de-carneiro (registrado na
    justificativa, não corrigido — fora do escopo desta mudança).
  - ATI-024/052: motoniveladora domina em operações de precisão/acabamento
    fino (camada de pó de pedra, regularização geométrica) — rolo liso tem
    folga (papel de acabamento, não de compactação pesada).
  - ATI-060: escavadeira+rompedor hidráulico modelados como unidade
    acoplada única (mesma capacidade nos 2 elementos).
  - ATI-062 (TSD): espargidor domina o comboio de 2 camadas completas
    (razão ~2,95x frente à pintura de ligação de camada única, já resolvida
    em cluster 6).
  - ATI-063/064: mão de obra já presente na composição (Montador, Montador
    de Meio Fio) é o gargalo — mesmo padrão de bocas de bueiro.
  - ATI-070: implantação de eixo (topografia) — Topógrafo é o gargalo, sem
    pesquisa necessária (mesmo padrão do cluster E0001/terceirizado).
  - COMPAC-FINAL-ROCHA: rolo LISO (não pé-de-carneiro) é o gargalo
    tecnicamente correto para compactação de camada final de rocha.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

_ROOT = Path(__file__).resolve().parent.parent.parent.parent.parent
_PRODUTIVIDADES = _ROOT / "config" / "catalogos" / "rfi-r02" / "produtividades"

_ALL_FILES = [
    "CPU-TERRA-ATI-001-PROD-001.json",
    "CPU-TERRA-ATI-005-PROD-001.json",
    "CPU-TERRA-ATI-007-PROD-001.json",
    "CPU-TERRA-ATI-009-PROD-001.json",
    "CPU-TERRA-ATI-019-PROD-001.json",
    "CPU-TERRA-ATI-024-PROD-001.json",
    "CPU-TERRA-ATI-052-PROD-001.json",
    "CPU-TERRA-ATI-060-PROD-001.json",
    "CPU-TERRA-ATI-062-PROD-001.json",
    "CPU-TERRA-ATI-063-PROD-001.json",
    "CPU-TERRA-ATI-064-PROD-001.json",
    "CPU-TERRA-ATI-070-PROD-001.json",
    "CPU-TERRA-COMPAC-FINAL-ROCHA-PROD-001.json",
    "CPU-TERRA-CORPO-ATERRO-3CAT-PROD-001.json",
]


def _build_validators():
    from concilium.presentation.cli._commands_manage_helpers_d import _build_schema_validators

    return _build_schema_validators(_ROOT / "config" / "schemas" / "catalog")


def _errors(validator, item: dict) -> list[str]:
    return [".".join(str(x) for x in err.absolute_path) + f" -> {err.message}" for err in validator.iter_errors(item)]


def _composicao_de(data: dict):
    """Constrói ComposicaoPadraoEquipe tolerando o campo legado
    'consumo_litros_hora' (typo pré-existente em várias CPUs — o campo correto
    no modelo é 'consumo_litros_hora_estimado'). Bug de dados pré-existente,
    fora do escopo do grafo de sinergia."""
    from concilium.domain.models.catalog.catalogo import ComposicaoPadraoEquipe

    raw = dict(data["composicao_padrao_equipe"])
    raw["equipamentos"] = [{k: v for k, v in eq.items() if k != "consumo_litros_hora"} for eq in raw["equipamentos"]]
    return ComposicaoPadraoEquipe(**raw)


class TestCluster7SchemaEReconciliacao:
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
        valor_horario = data["valor_horario"]
        composicao = _composicao_de(data)
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

    @pytest.mark.parametrize(
        ("filename", "gargalo"),
        [
            ("CPU-TERRA-ATI-001-PROD-001.json", "E0031"),
            ("CPU-TERRA-ATI-005-PROD-001.json", "E0016"),
            ("CPU-TERRA-ATI-007-PROD-001.json", "E0031"),
            ("CPU-TERRA-ATI-009-PROD-001.json", "E0025"),
            ("CPU-TERRA-ATI-019-PROD-001.json", "E0035"),
            ("CPU-TERRA-ATI-024-PROD-001.json", "E0028"),
            ("CPU-TERRA-ATI-052-PROD-001.json", "E0028"),
            ("CPU-TERRA-ATI-060-PROD-001.json", "E0016"),
            ("CPU-TERRA-ATI-062-PROD-001.json", "E0020"),
            ("CPU-TERRA-ATI-063-PROD-001.json", "P0037"),
            ("CPU-TERRA-ATI-064-PROD-001.json", "P0039"),
            ("CPU-TERRA-ATI-070-PROD-001.json", "P0057"),
            ("CPU-TERRA-COMPAC-FINAL-ROCHA-PROD-001.json", "E0036"),
            ("CPU-TERRA-CORPO-ATERRO-3CAT-PROD-001.json", "E0035"),
        ],
    )
    def test_gargalo_declarado_e_o_esperado(self, filename, gargalo):
        data = json.loads((_PRODUTIVIDADES / filename).read_text(encoding="utf-8"))
        assert data["grafo_sinergia"]["gargalo_declarado"] == gargalo, filename

    def test_ati060_escavadeira_e_rompedor_tem_mesma_capacidade(self):
        """Unidade acoplada — escavadeira e rompedor hidráulico não operam
        independentemente, devem carregar a mesma capacidade."""
        data = json.loads((_PRODUTIVIDADES / "CPU-TERRA-ATI-060-PROD-001.json").read_text(encoding="utf-8"))
        capacidades = {c["elemento_id"]: c for c in data["grafo_sinergia"]["capacidades"]}
        assert capacidades["E0016"]["capacidade_horaria"] == capacidades["E0050"]["capacidade_horaria"]

    @pytest.mark.parametrize("filename", ["CPU-TERRA-ATI-063-PROD-001.json", "CPU-TERRA-ATI-064-PROD-001.json"])
    def test_mao_de_obra_ja_presente_na_composicao_e_o_gargalo(self, filename):
        """Diferente do cluster de bocas de bueiro (que exigiu adicionar
        Montador como capacidade), aqui o papel de mão de obra já existia na
        composição de funções e é usado diretamente como gargalo."""
        data = json.loads((_PRODUTIVIDADES / filename).read_text(encoding="utf-8"))
        composicao = data["composicao_padrao_equipe"]
        gargalo = data["grafo_sinergia"]["gargalo_declarado"]
        funcao_ids = {f["funcao_id"] for f in composicao["funcoes"]}
        assert gargalo in funcao_ids, filename

    @pytest.mark.parametrize("filename", _ALL_FILES)
    def test_capacidades_cobrem_todos_os_equipamentos_referenciados(self, filename):
        data = json.loads((_PRODUTIVIDADES / filename).read_text(encoding="utf-8"))
        equip_ids = {e["equip_id"] for e in data["composicao_padrao_equipe"]["equipamentos"]}
        cap_ids = {c["elemento_id"] for c in data["grafo_sinergia"]["capacidades"]}
        assert equip_ids <= cap_ids, filename
