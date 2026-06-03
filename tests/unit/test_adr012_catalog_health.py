"""Tests for ADR-012: Catalog Completeness System."""

from __future__ import annotations

import pytest

from concilium.domain.models.catalog_health import (
    CatalogGap,
    CatalogHealthReport,
    CoberturaConfig,
    FonteAutoritativa,
    GrupoCoberturaServico,
)
from concilium.infrastructure.catalog.completeness import CatalogGapDetector, CatalogGapResolver


class TestFonteAutoritativa:
    def test_create(self):
        f = FonteAutoritativa(
            id="SICRO_2024",
            nome="SICRO",
            entidade="DNIT",
            jurisdicao="BR",
            dominio=["rodovias_federais"],
            granularidade="cpu_completa",
            ciclo_atualizacao="mensal",
            prioridade=1,
        )
        assert f.id == "SICRO_2024"
        assert f.prioridade == 1


class TestCatalogGapDetector:
    def _make_cpus(self):
        return [
            {"codigo": "ESCO-1CAT", "descricao": "Escavação 1ª categoria", "unidade": "m3", "producao_id": "PROD-001"},
            {"codigo": "COMPACT", "descricao": "Compactação aterro 100% PN", "unidade": "m3", "producao_id": None},
        ]

    def _make_cobertura_config(self):
        return CoberturaConfig(
            dominio="rodovias_federais",
            jurisdicao="BR",
            fonte_referencia="SICRO",
            grupos_servico={
                "TERRAPLENAGEM": GrupoCoberturaServico(
                    nome="Terraplenagem",
                    servicos_esperados=[
                        "Escavação 1ª categoria",
                        "Compactação aterro 100% PN",
                        "Regularização sub-leito",
                    ],
                    fonte_preenchimento="SICRO",
                )
            },
        )

    def test_detects_absent_cpu(self):
        detector = CatalogGapDetector()
        gaps = detector.detect_gaps("rodovias_federais", self._make_cpus(), self._make_cobertura_config())
        ausentes = [g for g in gaps if g.status == "AUSENTE"]
        assert any("Regularização" in g.servico_esperado for g in ausentes)

    def test_detects_cpu_without_produtividade(self):
        detector = CatalogGapDetector()
        gaps = detector.detect_gaps("rodovias_federais", self._make_cpus(), self._make_cobertura_config())
        sem_prod = [g for g in gaps if g.status == "SEM_PRODUTIVIDADE"]
        assert any("Compactação" in g.servico_esperado for g in sem_prod)

    def test_no_gap_when_cpu_complete(self):
        detector = CatalogGapDetector()
        config = CoberturaConfig(
            dominio="test",
            jurisdicao="BR",
            fonte_referencia="SICRO",
            grupos_servico={
                "TERRAPL": GrupoCoberturaServico(
                    nome="T",
                    servicos_esperados=["Escavação 1ª categoria"],
                    fonte_preenchimento="SICRO",
                )
            },
        )
        producoes = [{"id": "PROD-001", "qualidade": {"confianca_pct": 90}}]
        gaps = detector.detect_gaps("test", self._make_cpus(), config, producoes=producoes)
        assert all(g.status != "AUSENTE" or "Escavação" not in g.servico_esperado for g in gaps)

    def test_detects_low_confidence(self):
        cpus = [
            {"codigo": "ESCO-1CAT", "descricao": "Escavação 1ª categoria", "unidade": "m3", "producao_id": "PROD-LOW"}
        ]
        producoes = [{"id": "PROD-LOW", "qualidade": {"confianca_pct": 40}}]
        config = CoberturaConfig(
            dominio="test",
            jurisdicao="BR",
            fonte_referencia="SICRO",
            grupos_servico={
                "G": GrupoCoberturaServico(
                    nome="G",
                    servicos_esperados=["Escavação 1ª categoria"],
                    fonte_preenchimento="SICRO",
                )
            },
        )
        detector = CatalogGapDetector()
        gaps = detector.detect_gaps("test", cpus, config, producoes=producoes)
        baixa = [g for g in gaps if g.status == "BAIXA_CONFIANCA"]
        assert len(baixa) == 1
        assert baixa[0].confianca_atual == 40

    def test_health_report_completo(self):
        cpus = [
            {"codigo": "A", "descricao": "Serviço A", "unidade": "m3", "producao_id": "P1"},
            {"codigo": "B", "descricao": "Serviço B", "unidade": "m2", "producao_id": "P2"},
        ]
        producoes = [
            {"id": "P1", "origem": {"tipo": "calibrado_contra_obra_real"}, "qualidade": {"confianca_pct": 95}},
            {"id": "P2", "origem": {"tipo": "tabela_referencia"}, "qualidade": {"confianca_pct": 85}},
        ]
        detector = CatalogGapDetector()
        report = detector.build_health_report("test", "BR", [], 2, cpus, producoes)
        assert report.cobertura_pct == 100.0
        assert report.status in ("COMPLETO", "ADEQUADO")

    def test_health_report_insuficiente(self):
        detector = CatalogGapDetector()
        gaps = [CatalogGap(grupo="G", servico_esperado=f"S{i}", status="AUSENTE") for i in range(8)]
        report = detector.build_health_report("test", "BR", gaps, 10, [], [])
        assert report.cobertura_pct < 60
        assert report.status == "INSUFICIENTE"


class TestCatalogGapResolver:
    def test_resolve_not_found(self):
        fonte = FonteAutoritativa(
            id="SICRO",
            nome="SICRO",
            entidade="DNIT",
            jurisdicao="BR",
            dominio=[],
            granularidade="cpu_completa",
            ciclo_atualizacao="mensal",
            prioridade=1,
        )
        gap = CatalogGap(grupo="G", servico_esperado="S", status="AUSENTE")
        resolver = CatalogGapResolver()
        proposal = resolver.resolve(gap, fonte, dados_fonte=None)
        assert proposal.status == "NAO_ENCONTRADO"

    def test_resolve_proposto(self):
        fonte = FonteAutoritativa(
            id="SICRO",
            nome="SICRO",
            entidade="DNIT",
            jurisdicao="BR",
            dominio=[],
            granularidade="cpu_completa",
            ciclo_atualizacao="mensal",
            prioridade=1,
        )
        gap = CatalogGap(grupo="G", servico_esperado="S", status="AUSENTE")
        resolver = CatalogGapResolver()
        proposal = resolver.resolve(
            gap,
            fonte,
            dados_fonte={"codigo": "NEW-CPU", "producao_horaria": 150.0, "custo_unitario": 8.5, "unidade": "m3"},
        )
        assert proposal.status == "PROPOSTO"
        assert proposal.cpu_codigo_proposto == "NEW-CPU"
        assert proposal.requer_aprovacao is True


class TestCatalogHealthReportStatus:
    @pytest.mark.parametrize(
        "cobertura,confianca,expected",
        [
            (95, 80, "COMPLETO"),
            (85, 75, "ADEQUADO"),
            (65, 50, "PARCIAL"),
            (55, 40, "INSUFICIENTE"),
        ],
    )
    def test_compute_status(self, cobertura, confianca, expected):
        assert CatalogHealthReport.compute_status(cobertura, confianca) == expected
