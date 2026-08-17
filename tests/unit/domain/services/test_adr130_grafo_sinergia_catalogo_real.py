"""ADR-130 F4 — Piloto: grafo de sinergia real para a família ESCO-CARGA (AGIS).

TDD: testes escritos antes de (a) estender o JSON Schema com
grafo_sinergia/RelacaoSinergia/CapacidadeElemento e (b) popular os 6 arquivos
reais de PROD-*-ESCO-CARGA-*CAT-DMT*.json com o grafo calibrado.

Contexto: as 6 CPUs da família (1CAT/2CAT/3CAT × DMT2000/DMT3000) compartilham
só 4 equipamentos (2 escavadeiras + 2 variantes de caminhão). Calibração
reversa a partir do producao_horaria real (não estimativa de fabricante) mostra
que a escavadeira é sempre o elemento gargalo em todas as 6 composições — a
frota de caminhões tem folga generosa (55-130 m³/h acima do producao_horaria)
em todos os casos. A capacidade real da escavadeira varia por categoria de
solo (1ª/2ª/3ª), mesmo usando o mesmo item de catálogo (AGIS-E0015):

  - 38T, 1ª categoria (CPUs 1CAT):     ~231.4 m³/h
  - 38T, 2ª categoria (CPUs 2CAT):     ~158.5 m³/h
  - 48T, 3ª categoria/rocha (CPUs 3CAT): ~142.1 m³/h

Caminhões usam capacidade estimada de especificação de fabricante
(fonte="fabricante") — nunca são o gargalo, então o valor exato importa
menos; a escavadeira usa fonte="medicao_obra" (calibração reversa a partir
do dado real de campo), com justificativa explicando o método.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

_ROOT = Path(__file__).resolve().parent.parent.parent.parent.parent
_SCHEMA_ROOT = _ROOT / "config" / "schemas" / "catalog"
_PRODUTIVIDADES = _ROOT / "config" / "catalogos" / "mendeslobo" / "produtividades"

_ESCO_CARGA_FILES = [
    "CPU-TERRA-ESCO-CARGA-1CAT-DMT2000-PROD-001.json",
    "CPU-TERRA-ESCO-CARGA-1CAT-DMT3000-PROD-001.json",
    "CPU-TERRA-ESCO-CARGA-2CAT-DMT2000-PROD-001.json",
    "CPU-TERRA-ESCO-CARGA-2CAT-DMT3000-PROD-001.json",
    "CPU-TERRA-ESCO-CARGA-3CAT-DMT2000-PROD-001.json",
    "CPU-TERRA-ESCO-CARGA-3CAT-DMT3000-PROD-001.json",
]


def _build_validators():
    from concilium.presentation.cli._commands_manage_helpers_d import _build_schema_validators

    return _build_schema_validators(_SCHEMA_ROOT)


def _errors(validator, item: dict) -> list[str]:
    return [".".join(str(x) for x in err.absolute_path) + f" -> {err.message}" for err in validator.iter_errors(item)]


class TestSchemaGrafoSinergia:
    """JSON Schema deve aceitar grafo_sinergia (mesma forma do modelo Pydantic,
    incluindo o campo justificativa recém-adicionado a CapacidadeElemento)."""

    def _base_producao(self, **overrides) -> dict:
        base = {
            "id": "PROD-TEST-GRAFO-1",
            "codigo": "PROD-TEST-GRAFO-1",
            "descricao": "teste",
            "producao_horaria": 100.0,
            "unidade": "m3/h",
            "categoria": "TERRAPLENAGEM",
            "origem": "PROPRIA",
        }
        base.update(overrides)
        return base

    def test_grafo_sinergia_completo_valida(self):
        _, prod_v, _ = _build_validators()
        item = self._base_producao(
            grafo_sinergia={
                "relacoes": [
                    {"tipo": "acoplamento", "origem": "EQ-A", "destino": "EQ-B", "descricao": "teste"},
                ],
                "capacidades": [
                    {
                        "elemento_id": "EQ-A",
                        "capacidade_horaria": 231.4,
                        "unidade": "m3/h",
                        "fonte": "medicao_obra",
                        "justificativa": "calibração reversa a partir do producao_horaria real.",
                    },
                    {"elemento_id": "EQ-B", "capacidade_horaria": 48.1, "unidade": "m3/h", "fonte": "fabricante"},
                ],
                "gargalo_declarado": None,
            }
        )
        assert _errors(prod_v, item) == []

    def test_grafo_sinergia_sem_relacoes_valida(self):
        """relacoes pode ser lista vazia — gargalo simplesmente o mínimo das capacidades."""
        _, prod_v, _ = _build_validators()
        item = self._base_producao(
            grafo_sinergia={
                "relacoes": [],
                "capacidades": [
                    {"elemento_id": "EQ-A", "capacidade_horaria": 231.4, "unidade": "m3/h"},
                ],
            }
        )
        assert _errors(prod_v, item) == []

    def test_grafo_sinergia_ausente_continua_valido(self):
        """Retrocompat: producao sem grafo_sinergia continua válida (campo opcional)."""
        _, prod_v, _ = _build_validators()
        item = self._base_producao()
        assert _errors(prod_v, item) == []

    def test_capacidade_elemento_sem_justificativa_valida(self):
        """justificativa é opcional no schema também."""
        _, prod_v, _ = _build_validators()
        item = self._base_producao(
            grafo_sinergia={
                "relacoes": [],
                "capacidades": [{"elemento_id": "EQ-A", "capacidade_horaria": 10.0, "unidade": "m3/h"}],
            }
        )
        assert _errors(prod_v, item) == []

    def test_capacidade_horaria_zero_invalida(self):
        _, prod_v, _ = _build_validators()
        item = self._base_producao(
            grafo_sinergia={
                "relacoes": [],
                "capacidades": [{"elemento_id": "EQ-A", "capacidade_horaria": 0.0, "unidade": "m3/h"}],
            }
        )
        assert _errors(prod_v, item)

    def test_fonte_invalida_rejeitada(self):
        _, prod_v, _ = _build_validators()
        item = self._base_producao(
            grafo_sinergia={
                "relacoes": [],
                "capacidades": [
                    {"elemento_id": "EQ-A", "capacidade_horaria": 10.0, "unidade": "m3/h", "fonte": "chute"}
                ],
            }
        )
        assert _errors(prod_v, item)

    def test_tipo_relacao_invalido_rejeitado(self):
        _, prod_v, _ = _build_validators()
        item = self._base_producao(
            grafo_sinergia={
                "relacoes": [{"tipo": "outro_tipo_qualquer", "origem": "A", "destino": "B"}],
                "capacidades": [],
            }
        )
        assert _errors(prod_v, item)

    def test_campo_desconhecido_em_capacidade_elemento_rejeitado(self):
        _, prod_v, _ = _build_validators()
        item = self._base_producao(
            grafo_sinergia={
                "relacoes": [],
                "capacidades": [
                    {
                        "elemento_id": "EQ-A",
                        "capacidade_horaria": 10.0,
                        "unidade": "m3/h",
                        "campo_totalmente_desconhecido": 1,
                    }
                ],
            }
        )
        assert _errors(prod_v, item)


class TestGrafoSinergiaEscoCargaReal:
    """Regressão direta: os 6 arquivos reais da família ESCO-CARGA devem ter
    grafo_sinergia populado, validar contra o schema, e o gargalo derivado
    deve reconciliar com o producao_horaria real (dentro do limiar de
    divergência ADR-130 D4 — LIMIAR_DIVERGENCIA_SINERGIA=0.15)."""

    @pytest.mark.parametrize("filename", _ESCO_CARGA_FILES)
    def test_arquivo_real_tem_grafo_sinergia_valido(self, filename):
        _, prod_v, _ = _build_validators()
        data = json.loads((_PRODUTIVIDADES / filename).read_text(encoding="utf-8"))
        assert data.get("grafo_sinergia") is not None, f"{filename}: grafo_sinergia ausente"
        erros = _errors(prod_v, data)
        assert erros == [], f"{filename}: {erros}"

    @pytest.mark.parametrize("filename", _ESCO_CARGA_FILES)
    def test_gargalo_derivado_reconcilia_com_valor_horario(self, filename):
        from concilium.domain.models.catalog.catalogo import ComposicaoPadraoEquipe
        from concilium.domain.models.catalog.producao import GrafoSinergiaEquipe
        from concilium.domain.services.sinergia_equipe import derivar_producao_horaria

        data = json.loads((_PRODUTIVIDADES / filename).read_text(encoding="utf-8"))
        producao_horaria = data["producao_horaria"]
        composicao = ComposicaoPadraoEquipe(**data["composicao_padrao_equipe"])
        grafo = GrafoSinergiaEquipe(**data["grafo_sinergia"])

        derivacao = derivar_producao_horaria(grafo, composicao)
        assert derivacao.producao_horaria_derivada is not None, f"{filename}: gargalo não computável"

        divergencia = abs(derivacao.producao_horaria_derivada - producao_horaria) / producao_horaria
        assert divergencia < 0.15, (
            f"{filename}: derivado={derivacao.producao_horaria_derivada} vs "
            f"producao_horaria={producao_horaria} (divergência {divergencia:.1%})"
        )

    @pytest.mark.parametrize("filename", _ESCO_CARGA_FILES)
    def test_gargalo_derivado_e_a_escavadeira(self, filename):
        """Confirma a hipótese verificada manualmente: a escavadeira (não os
        caminhões) é o elemento gargalo em toda a família ESCO-CARGA."""
        from concilium.domain.models.catalog.catalogo import ComposicaoPadraoEquipe
        from concilium.domain.models.catalog.producao import GrafoSinergiaEquipe
        from concilium.domain.services.sinergia_equipe import derivar_producao_horaria

        data = json.loads((_PRODUTIVIDADES / filename).read_text(encoding="utf-8"))
        composicao = ComposicaoPadraoEquipe(**data["composicao_padrao_equipe"])
        grafo = GrafoSinergiaEquipe(**data["grafo_sinergia"])

        derivacao = derivar_producao_horaria(grafo, composicao)
        gargalo_equip = next(e for e in composicao.equipamentos if e.equip_id == derivacao.gargalo_derivado)
        # Escavadeiras neste catálogo têm sempre num_unidades=1 (item único, gargalo natural);
        # caminhões aparecem em quantidade >= 6.
        assert gargalo_equip.num_unidades == 1, (
            f"{filename}: esperava a escavadeira (num_unidades=1) como gargalo, achou "
            f"{derivacao.gargalo_derivado} (num_unidades={gargalo_equip.num_unidades})"
        )

    @pytest.mark.parametrize("filename", _ESCO_CARGA_FILES)
    def test_capacidade_escavadeira_tem_fonte_medicao_obra_e_justificativa(self, filename):
        data = json.loads((_PRODUTIVIDADES / filename).read_text(encoding="utf-8"))
        composicao = data["composicao_padrao_equipe"]
        equip_unico = next(e for e in composicao["equipamentos"] if e["num_unidades"] == 1)
        cap = next(c for c in data["grafo_sinergia"]["capacidades"] if c["elemento_id"] == equip_unico["equip_id"])
        assert cap["fonte"] == "medicao_obra", filename
        assert cap.get("justificativa"), f"{filename}: escavadeira sem justificativa"

    @pytest.mark.parametrize("filename", _ESCO_CARGA_FILES)
    def test_capacidade_caminhao_tem_fonte_fabricante_e_justificativa(self, filename):
        data = json.loads((_PRODUTIVIDADES / filename).read_text(encoding="utf-8"))
        composicao = data["composicao_padrao_equipe"]
        equip_caminhao = next(e for e in composicao["equipamentos"] if e["num_unidades"] > 1)
        cap = next(c for c in data["grafo_sinergia"]["capacidades"] if c["elemento_id"] == equip_caminhao["equip_id"])
        assert cap["fonte"] == "fabricante", filename
        assert cap.get("justificativa"), f"{filename}: caminhão sem justificativa"
