"""ADR-130 F4 — rfi-r02, cluster 6: grafo de sinergia real para 14 CPUs de 7
famílias de equipamento/processo, pesquisados em paralelo.

TDD: testes escritos antes de popular os 14 arquivos reais.

Famílias:

  - Desmatamento (E0016+E0024+E0031, ATI-003/008): trator de esteiras é o
    gargalo em desmatamento geral (738 m²/h, ~metade da referência SICRO2 de
    trator "livre" ~1444 m²/h); motosserra passa a dominar em alta densidade
    de árvores (375 m²/h, corte serial por indivíduo).
  - Roçada (E0031+E0048, ATI-006/068): roçadeira costal é o gargalo em ambas;
    conversão aritmética exata (1428,57 m²/h ÷ 142,86 m/h = 10,0m) confirma
    mesma capacidade subjacente entre as 2 unidades (área vs. linear).
  - Boca de bueiro (E0016+E0026+mão de obra, ATI-041/042): mesmo padrão do
    corpo do bueiro celular já resolvido nesta sessão — Montador (P0037) é o
    gargalo (processo civil de fôrma/armação/concretagem), equipamentos com
    folga.
  - Imprimação/pintura de ligação (E0010+E0020, ATI-056/057): espargidor é o
    gargalo; razão real do catálogo diverge da razão SICRO de mercado
    (divergência documentada, não resolvida — calibração reversa).
  - CBUQ/recomposição (E0008+E0036+E0037+E0041, ATI-058/061): vibroacabadora
    é o gargalo em ambos; recomposição ~11x mais lenta por ser processo
    manual/pontual (corte de borda + preenchimento em caixas), não faixa
    contínua — mecanismo análogo ao "trem sincronizado" de cluster 3.
  - Aterro compactado PI/PN (E0010+E0029+E0035[x2]+E0039): rolo
    pé-de-carneiro é o gargalo (mesmo padrão de subleito/sub-base/base já
    confirmado); PI mais lento que PN por maior energia de compactação.
  - ESCO-CARGA 3ª categoria (E0018+E0008): mesmo padrão de processo
    já validado 2x nesta sessão — escavadeira 38t é o gargalo volumétrico,
    fórmula reconcilia <1%, frota de caminhões com folga.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

_ROOT = Path(__file__).resolve().parent.parent.parent.parent.parent
_PRODUTIVIDADES = _ROOT / "config" / "catalogos" / "rfi-r02" / "produtividades"

_DESMATAMENTO_FILES = ["CPU-TERRA-ATI-003-PROD-001.json", "CPU-TERRA-ATI-008-PROD-001.json"]
_ROCADA_FILES = ["CPU-TERRA-ATI-006-PROD-001.json", "CPU-TERRA-ATI-068-PROD-001.json"]
_BOCA_FILES = ["CPU-TERRA-ATI-041-PROD-001.json", "CPU-TERRA-ATI-042-PROD-001.json"]
_IMPRIMACAO_FILES = ["CPU-TERRA-ATI-056-PROD-001.json", "CPU-TERRA-ATI-057-PROD-001.json"]
_CBUQ_FILES = ["CPU-TERRA-ATI-058-PROD-001.json", "CPU-TERRA-ATI-061-PROD-001.json"]
_COMPAC_FILES = ["CPU-TERRA-COMPAC-PI-PROD-001.json", "CPU-TERRA-COMPAC-PN-PROD-001.json"]
_ESCO_3CAT_FILES = [
    "CPU-TERRA-ESCO-CARGA-3CAT-DMT2000-PROD-001.json",
    "CPU-TERRA-ESCO-CARGA-3CAT-DMT3000-PROD-001.json",
]
_ALL_FILES = (
    _DESMATAMENTO_FILES
    + _ROCADA_FILES
    + _BOCA_FILES
    + _IMPRIMACAO_FILES
    + _CBUQ_FILES
    + _COMPAC_FILES
    + _ESCO_3CAT_FILES
)


def _build_validators():
    from concilium.presentation.cli._commands_manage_helpers_d import _build_schema_validators

    return _build_schema_validators(_ROOT / "config" / "schemas" / "catalog")


def _errors(validator, item: dict) -> list[str]:
    return [".".join(str(x) for x in err.absolute_path) + f" -> {err.message}" for err in validator.iter_errors(item)]


def _composicao_de(data: dict):
    """Constrói ComposicaoPadraoEquipe tolerando o campo legado
    'consumo_litros_hora' (typo pré-existente em várias CPUs — o campo correto
    no modelo é 'consumo_litros_hora_estimado'; não lido por
    ComposicaoPadraoEquipe, apenas por pu_calculator via dict bruto). Bug de
    dados pré-existente, fora do escopo do grafo de sinergia."""
    from concilium.domain.models.catalog.catalogo import ComposicaoPadraoEquipe

    raw = dict(data["composicao_padrao_equipe"])
    raw["equipamentos"] = [{k: v for k, v in eq.items() if k != "consumo_litros_hora"} for eq in raw["equipamentos"]]
    return ComposicaoPadraoEquipe(**raw)


class TestCluster6SchemaEReconciliacao:
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

    @pytest.mark.parametrize(
        ("filename", "gargalo"),
        [("CPU-TERRA-ATI-003-PROD-001.json", "E0024"), ("CPU-TERRA-ATI-008-PROD-001.json", "E0031")],
    )
    def test_desmatamento_gargalo_alterna_por_densidade(self, filename, gargalo):
        data = json.loads((_PRODUTIVIDADES / filename).read_text(encoding="utf-8"))
        assert data["grafo_sinergia"]["gargalo_declarado"] == gargalo

    @pytest.mark.parametrize("filename", _ROCADA_FILES)
    def test_rocada_e0048_e_gargalo(self, filename):
        data = json.loads((_PRODUTIVIDADES / filename).read_text(encoding="utf-8"))
        assert data["grafo_sinergia"]["gargalo_declarado"] == "E0048"

    def test_rocada_conversao_area_linear_e_consistente(self):
        area = json.loads((_PRODUTIVIDADES / "CPU-TERRA-ATI-006-PROD-001.json").read_text(encoding="utf-8"))
        linear = json.loads((_PRODUTIVIDADES / "CPU-TERRA-ATI-068-PROD-001.json").read_text(encoding="utf-8"))
        largura_implicita = area["producao_horaria"] / linear["producao_horaria"]
        assert largura_implicita == pytest.approx(10.0, rel=0.01)

    @pytest.mark.parametrize("filename", _BOCA_FILES)
    def test_boca_montador_e_gargalo_equipamentos_tem_folga(self, filename):
        data = json.loads((_PRODUTIVIDADES / filename).read_text(encoding="utf-8"))
        grafo = data["grafo_sinergia"]
        assert grafo["gargalo_declarado"] == "P0037"
        capacidades = {c["elemento_id"]: c for c in grafo["capacidades"]}
        assert capacidades["P0037"]["fonte"] == "medicao_obra"
        assert capacidades["E0016"]["fonte"] == "fabricante"
        assert capacidades["E0026"]["fonte"] == "fabricante"

    @pytest.mark.parametrize("filename", _IMPRIMACAO_FILES)
    def test_imprimacao_espargidor_e_gargalo(self, filename):
        data = json.loads((_PRODUTIVIDADES / filename).read_text(encoding="utf-8"))
        assert data["grafo_sinergia"]["gargalo_declarado"] == "E0020"

    @pytest.mark.parametrize("filename", _CBUQ_FILES)
    def test_cbuq_vibroacabadora_e_gargalo(self, filename):
        data = json.loads((_PRODUTIVIDADES / filename).read_text(encoding="utf-8"))
        assert data["grafo_sinergia"]["gargalo_declarado"] == "E0041"

    @pytest.mark.parametrize("filename", _COMPAC_FILES)
    def test_compac_rolo_e_gargalo(self, filename):
        data = json.loads((_PRODUTIVIDADES / filename).read_text(encoding="utf-8"))
        assert data["grafo_sinergia"]["gargalo_declarado"] == "E0035"

    def test_compac_pi_mais_lento_que_pn(self):
        pi = json.loads((_PRODUTIVIDADES / "CPU-TERRA-COMPAC-PI-PROD-001.json").read_text(encoding="utf-8"))
        pn = json.loads((_PRODUTIVIDADES / "CPU-TERRA-COMPAC-PN-PROD-001.json").read_text(encoding="utf-8"))
        assert pi["producao_horaria"] < pn["producao_horaria"]

    @pytest.mark.parametrize("filename", _ESCO_3CAT_FILES)
    def test_esco_3cat_escavadeira_e_gargalo_forward(self, filename):
        data = json.loads((_PRODUTIVIDADES / filename).read_text(encoding="utf-8"))
        grafo = data["grafo_sinergia"]
        assert grafo["gargalo_declarado"] == "E0018"
        capacidades = {c["elemento_id"]: c for c in grafo["capacidades"]}
        assert capacidades["E0018"]["fonte"] == "fabricante"
        assert capacidades["E0008"]["fonte"] == "fabricante"

    @pytest.mark.parametrize("filename", _ALL_FILES)
    def test_capacidades_cobrem_todos_os_equipamentos_e_funcoes_referenciados(self, filename):
        data = json.loads((_PRODUTIVIDADES / filename).read_text(encoding="utf-8"))
        composicao = data["composicao_padrao_equipe"]
        elem_ids = {e["equip_id"] for e in composicao["equipamentos"]}
        cap_ids = {c["elemento_id"] for c in data["grafo_sinergia"]["capacidades"]}
        # elementos de mão de obra (papel P0037 etc.) também podem aparecer como capacidade
        assert elem_ids <= cap_ids, filename
