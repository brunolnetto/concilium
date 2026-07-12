"""ADR-130 F4 — rfi-r02, cluster 1 (E0026+E0027): grafo de sinergia real para
17 CPUs de instalação de bueiro/tubo (retroescavadeira 75HP + mini escavadeira 2t).

TDD: testes escritos antes de popular os 17 arquivos reais.

Contexto: diferente do piloto ESCO-CARGA (mendeslobo, carga/transporte
paralelo), este cluster é um processo em DUAS ETAPAS EM SÉRIE — a
retroescavadeira (E0026) abre a vala, a mini escavadeira/equipe (E0027) faz o
nivelamento do berço e assentamento do tubo/bueiro. O gargalo é o mínimo entre
as duas etapas, cada uma convertida para m/h (unidade de produção da CPU) via
geometria da vala (que varia por diâmetro/classe).

Pesquisa (4 rodadas) estabeleceu:
  - Retroescavadeira 75HP: 15,7 m³/h nominal (convergência composição SINAPI
    102299 + fórmula de engenharia), com fator de 0.75× em valas confinadas
    (largura < 0,8m — SINAPI 102299 é calibrado para 0,8-1,5m).
  - Assentamento de bueiro SIMPLES (BSTC): usa a própria escavadeira/mini já
    na vala (sem guindauto dedicado) — achado-chave, corroborado pela
    composição SINAPI 92813 (assentamento com escavadeira integrada).
  - Assentamento de bueiro DUPLO/TRIPLO de D=1,20m (BDTC/BTTC): usa caminhão
    guindauto dedicado (SICRO 0804055/0819899) — peça mais pesada exige
    içamento formal.
  - BDTC D=1,00m e PVC/DEFOFO D=250/300mm: nenhuma composição de referência
    reconcilia bem com o dado real — aceito o valor real como capacidade
    calibrada (fonte="medicao_obra"), análogo à calibração reversa da
    escavadeira no piloto ESCO-CARGA (SINAPI é estruturalmente conservador,
    documentado — não é dado a "corrigir").

Todas as 17 CPUs reconciliam dentro do limiar de divergência ADR-130 D4
(15%) com essa modelagem de 2 estágios em série.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

_ROOT = Path(__file__).resolve().parent.parent.parent
_PRODUTIVIDADES = _ROOT / "config" / "catalogos" / "rfi-r02" / "produtividades"

_CLUSTER1_FILES = [
    "CPU-TERRA-ATI-025-PROD-001.json",
    # ATI-026 removida — Producao duplicata de ATI-025 (mesma composição/valor_horario/
    # grafo_sinergia), consolidada via CPU.producao_id_ref (ver
    # test_adr130_producao_consolidacao_duplicatas.py)
    "CPU-TERRA-ATI-027-PROD-001.json",
    # ATI-028 removida — Producao duplicata de ATI-027
    "CPU-TERRA-ATI-029-PROD-001.json",
    # ATI-030 removida — Producao duplicata de ATI-029
    "CPU-TERRA-ATI-031-PROD-001.json",
    "CPU-TERRA-ATI-032-PROD-001.json",
    "CPU-TERRA-ATI-043-PROD-001.json",
    "CPU-TERRA-ATI-044-PROD-001.json",
    "CPU-TERRA-ATI-045-PROD-001.json",
    # ATI-046 removida — Producao duplicata de ATI-045
    "CPU-TERRA-ATI-047-PROD-001.json",
    # ATI-048 removida — Producao duplicata de ATI-047
    "CPU-TERRA-ATI-049-PROD-001.json",
    "CPU-TERRA-ATI-050-PROD-001.json",
    "CPU-TERRA-ATI-051-PROD-001.json",
]


def _build_validators():
    from concilium.presentation.cli._commands_manage_helpers_d import _build_schema_validators

    return _build_schema_validators(_ROOT / "config" / "schemas" / "catalog")


def _errors(validator, item: dict) -> list[str]:
    return [".".join(str(x) for x in err.absolute_path) + f" -> {err.message}" for err in validator.iter_errors(item)]


class TestCluster1SchemaEReconciliacao:
    @pytest.mark.parametrize("filename", _CLUSTER1_FILES)
    def test_arquivo_real_tem_grafo_sinergia_valido(self, filename):
        _, prod_v, _ = _build_validators()
        data = json.loads((_PRODUTIVIDADES / filename).read_text(encoding="utf-8"))
        assert data.get("grafo_sinergia") is not None, f"{filename}: grafo_sinergia ausente"
        erros = _errors(prod_v, data)
        assert erros == [], f"{filename}: {erros}"

    @pytest.mark.parametrize("filename", _CLUSTER1_FILES)
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

    @pytest.mark.parametrize("filename", _CLUSTER1_FILES)
    def test_ambos_elementos_tem_justificativa(self, filename):
        data = json.loads((_PRODUTIVIDADES / filename).read_text(encoding="utf-8"))
        capacidades = data["grafo_sinergia"]["capacidades"]
        assert len(capacidades) == 2, filename
        for cap in capacidades:
            assert cap.get("justificativa"), f"{filename}: {cap['elemento_id']} sem justificativa"
            assert cap["fonte"] in ("fabricante", "medicao_obra"), filename

    @pytest.mark.parametrize("filename", _CLUSTER1_FILES)
    def test_retroescavadeira_e_mini_ambos_presentes(self, filename):
        """Confirma que o grafo cobre os 2 elementos reais da composição (E0026+E0027)."""
        data = json.loads((_PRODUTIVIDADES / filename).read_text(encoding="utf-8"))
        equip_ids = {e["equip_id"] for e in data["composicao_padrao_equipe"]["equipamentos"]}
        cap_ids = {c["elemento_id"] for c in data["grafo_sinergia"]["capacidades"]}
        assert equip_ids == {"E0026", "E0027"}, filename
        assert cap_ids == equip_ids, filename
