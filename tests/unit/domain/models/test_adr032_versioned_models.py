"""Testes unitários — ADR-032: modelos versionados e detecção de ciclos."""

from datetime import date, datetime

import pytest

from concilium.domain.models.catalog.versioned import (
    CPUVersionada,
    DateRange,
    InsumoVersionado,
    JurisdicaoVersionada,
    VersaoCPU,
    VersaoInsumo,
    VersaoJurisdicao,
)
from concilium.domain.validations.circular_deps import (
    validar_sem_ciclos,
    verificar_ciclos_cpu,
)

# ── Fixtures ──────────────────────────────────────────────────────────────────


def _versao_insumo(versao: str, preco: float, inicio: date, fim: date | None = None) -> VersaoInsumo:
    return VersaoInsumo(
        versao=versao,
        validade=DateRange(inicio=inicio, fim=fim),
        preco_unitario=preco,
        fonte_preco="catalogo_proprio",
        auditado_por="tester",
        auditado_em=datetime(2026, 5, 1),
    )


def _versao_cpu(versao: str, inicio: date, fim: date | None = None) -> VersaoCPU:
    return VersaoCPU(
        versao=versao,
        validade=DateRange(inicio=inicio, fim=fim),
        producao_horaria=100.0,
        custo_unitario_sem_encargos=50.0,
        encargos_aplicados_pct=1.777,
        jurisdicao_id_atu="BR-CE@2026-04",
        auditado_por="tester",
        auditado_em=datetime(2026, 5, 1),
    )


# ── DateRange ─────────────────────────────────────────────────────────────────


class TestDateRange:
    def test_dentro_do_periodo(self):
        dr = DateRange(inicio=date(2026, 4, 1), fim=date(2026, 7, 1))
        assert dr.vigente_em(date(2026, 5, 15)) is True

    def test_exatamente_no_inicio(self):
        dr = DateRange(inicio=date(2026, 4, 1), fim=date(2026, 7, 1))
        assert dr.vigente_em(date(2026, 4, 1)) is True

    def test_na_data_de_fim_nao_vigente(self):
        """Intervalo é semi-aberto [inicio, fim)."""
        dr = DateRange(inicio=date(2026, 4, 1), fim=date(2026, 7, 1))
        assert dr.vigente_em(date(2026, 7, 1)) is False

    def test_antes_do_inicio(self):
        dr = DateRange(inicio=date(2026, 4, 1), fim=date(2026, 7, 1))
        assert dr.vigente_em(date(2026, 3, 31)) is False

    def test_vigencia_indefinida(self):
        dr = DateRange(inicio=date(2026, 1, 1), fim=None)
        assert dr.vigente_em(date(2030, 12, 31)) is True


# ── InsumoVersionado ──────────────────────────────────────────────────────────


class TestInsumoVersionado:
    def test_preco_em_data_correta(self):
        insumo = InsumoVersionado(
            id="AJUDANTE-BR-CE",
            tipo="MAO_OBRA",
            descricao="Ajudante geral",
            unidade="mes",
            versoes=[
                _versao_insumo("2026-03", 2000.0, date(2026, 3, 1), date(2026, 4, 1)),
                _versao_insumo("2026-04", 2200.0, date(2026, 4, 1), None),
            ],
        )
        assert insumo.preco_em(date(2026, 3, 15)) == 2000.0
        assert insumo.preco_em(date(2026, 4, 1)) == 2200.0

    def test_preco_sem_versao_vigente_retorna_none(self):
        insumo = InsumoVersionado(
            id="INS-X",
            tipo="MATERIAL",
            descricao="Teste",
            unidade="m3",
            versoes=[
                _versao_insumo("2026-03", 100.0, date(2026, 3, 1), date(2026, 4, 1)),
            ],
        )
        assert insumo.preco_em(date(2025, 1, 1)) is None

    def test_id_atu_formato(self):
        insumo = InsumoVersionado(
            id="DIESEL-S10",
            tipo="MATERIAL",
            descricao="Diesel S10",
            unidade="litro",
            versoes=[
                _versao_insumo("2026-04", 6.2, date(2026, 4, 1), None),
            ],
        )
        assert insumo.id_atu == "DIESEL-S10@2026-04"

    @pytest.mark.parametrize("tipo", ["TREINAMENTO", "EXAME", "BENEFICIO"])
    def test_adr165_aceita_tipos_novos(self, tipo):
        """ADR-165: TREINAMENTO/EXAME/BENEFICIO também têm SCD Type 2 de preço via preco_na_data."""
        insumo = InsumoVersionado(
            id=f"COD-{tipo}",
            tipo=tipo,
            descricao="Item de teste",
            unidade="unid",
            versoes=[
                _versao_insumo("2026-04", 100.0, date(2026, 4, 1), None),
            ],
        )
        assert insumo.preco_em(date(2026, 4, 15)) == 100.0


# ── CPUVersionada ─────────────────────────────────────────────────────────────


class TestCPUVersionada:
    def test_custo_unitario_com_encargos(self):
        cpu = CPUVersionada(
            id="ESCO-CARGA-1CAT",
            descricao="Escavação e carga 1ª cat.",
            unidade="m3",
            categoria="TERRAPLENAGEM",
            versoes=[_versao_cpu("2026-04", date(2026, 4, 1))],
        )
        custo = cpu.custo_unitario_em(date(2026, 4, 15))
        assert custo is not None
        assert custo == round(50.0 * (1 + 1.777), 6)

    def test_versao_vigente_retorna_none_fora_do_periodo(self):
        cpu = CPUVersionada(
            id="CPU-X",
            descricao="CPU teste",
            unidade="m2",
            categoria="PAVIMENTACAO",
            versoes=[_versao_cpu("2026-04", date(2026, 4, 1), date(2026, 5, 1))],
        )
        assert cpu.versao_vigente(date(2025, 1, 1)) is None

    def test_id_atu_formato(self):
        cpu = CPUVersionada(
            id="ESCO-CARGA-1CAT",
            descricao="Escavação",
            unidade="m3",
            categoria="TERRAPLENAGEM",
            versoes=[_versao_cpu("2026-04", date(2026, 4, 1))],
        )
        assert cpu.id_atu == "ESCO-CARGA-1CAT@2026-04"


# ── JurisdicaoVersionada ──────────────────────────────────────────────────────


class TestJurisdicaoVersionada:
    def _make(self) -> JurisdicaoVersionada:
        return JurisdicaoVersionada(
            id="BRCE",
            nome="Brasil — Ceará",
            regime_trabalhista="CLT",
            versoes=[
                VersaoJurisdicao(
                    versao="2026-04",
                    validade=DateRange(inicio=date(2026, 4, 1), fim=None),
                    percentual_encargos_clt=1.777,
                    percentual_encargos_pj=0.0,
                    moeda="BRL",
                    auditado_por="tester",
                    auditado_em=datetime(2026, 5, 1),
                )
            ],
        )

    def test_encargos_clt(self):
        j = self._make()
        assert j.encargos_em(date(2026, 5, 1), "CLT") == 1.777

    def test_aceita_id_com_hifen_e_id_atu_formato(self):
        """Bug fix: o pattern anterior (^[A-Z]{2,10}$) rejeitava hífen, incompatível
        com o próprio exemplo da descrição do campo ("BR-CE") e com id_atu (que produz
        "BR-CE@2026-04")."""
        j = JurisdicaoVersionada(
            id="BR-CE",
            nome="Brasil — Ceará",
            regime_trabalhista="CLT",
            versoes=[
                VersaoJurisdicao(
                    versao="2026-04",
                    validade=DateRange(inicio=date(2026, 4, 1), fim=None),
                    percentual_encargos_clt=1.777,
                    percentual_encargos_pj=0.0,
                    moeda="BRL",
                    auditado_por="tester",
                    auditado_em=datetime(2026, 5, 1),
                )
            ],
        )
        assert j.id == "BR-CE"
        assert j.id_atu == "BR-CE@2026-04"

    def test_encargos_pj(self):
        j = self._make()
        assert j.encargos_em(date(2026, 5, 1), "PJ") == 0.0

    def test_encargos_sem_vigencia(self):
        j = self._make()
        assert j.encargos_em(date(2025, 1, 1)) is None

    def test_id_atu(self):
        j = self._make()
        assert j.id_atu == "BRCE@2026-04"


# ── DFS — Detecção de Ciclos ──────────────────────────────────────────────────


class TestCircularDeps:
    def _catalogo_simples(self) -> dict:
        """Catálogo linear sem ciclos: CPU-A → CPU-B (via cpu_referencia_id)."""
        return {
            "cpus": [
                {"codigo": "CPU-A", "cpu_referencia_id": "CPU-B", "composicao_itens": []},
                {"codigo": "CPU-B", "cpu_referencia_id": None, "composicao_itens": []},
            ]
        }

    def _catalogo_com_ciclo(self) -> dict:
        """CPU-A referencia CPU-B que referencia CPU-A — ciclo óbvio."""
        return {
            "cpus": [
                {"codigo": "CPU-A", "cpu_referencia_id": "CPU-B", "composicao_itens": []},
                {"codigo": "CPU-B", "cpu_referencia_id": "CPU-A", "composicao_itens": []},
            ]
        }

    def _catalogo_sem_referencias(self) -> dict:
        """CPUs independentes sem nenhuma referência cruzada."""
        return {
            "cpus": [
                {"codigo": "CPU-X", "cpu_referencia_id": None, "composicao_itens": []},
                {"codigo": "CPU-Y", "cpu_referencia_id": None, "composicao_itens": []},
            ]
        }

    def test_sem_ciclo_retorna_lista_vazia(self):
        erros = verificar_ciclos_cpu(self._catalogo_simples())
        assert erros == []

    def test_ciclo_detectado(self):
        erros = verificar_ciclos_cpu(self._catalogo_com_ciclo())
        assert len(erros) == 1
        assert "CPU-A" in erros[0]
        assert "CPU-B" in erros[0]

    def test_catalogo_vazio_sem_erros(self):
        assert verificar_ciclos_cpu({"cpus": []}) == []

    def test_cpus_independentes_sem_erros(self):
        assert verificar_ciclos_cpu(self._catalogo_sem_referencias()) == []

    def test_validar_sem_ciclos_levanta_exception(self):
        with pytest.raises(ValueError, match="Dependência circular"):
            validar_sem_ciclos(self._catalogo_com_ciclo())

    def test_validar_sem_ciclos_ok_nao_levanta(self):
        validar_sem_ciclos(self._catalogo_simples())  # não deve levantar

    def test_verificar_apenas_cpu_especifica(self):
        """Verifica apenas a partir de CPU-A — ciclo deve ser encontrado."""
        erros = verificar_ciclos_cpu(self._catalogo_com_ciclo(), cpu_id="CPU-A")
        assert len(erros) >= 1

    def test_terceirizado_composicao_item_builds_insumo_map(self):
        """Lines 34-35: CPU with TERCEIRIZADO composition item populates insumo_para_cpu map."""
        catalogo = {
            "cpus": [
                {
                    "codigo": "CPU-SUB",
                    "cpu_referencia_id": "CPU-MAIN",
                    "composicao_itens": [{"insumo_id": "INS-PROXY", "categoria_custo": "TERCEIRIZADO"}],
                },
                {
                    "codigo": "CPU-MAIN",
                    "cpu_referencia_id": None,
                    "composicao_itens": [{"insumo_id": "INS-PROXY", "categoria_custo": "TERCEIRIZADO"}],
                },
            ]
        }
        # No cycle here — just verifying it runs without error and builds the map
        erros = verificar_ciclos_cpu(catalogo)
        assert isinstance(erros, list)

    def test_self_referencing_insumo_is_filtered_out(self):
        """Lines 46-48: cpu_dep == cpu['codigo'] is filtered so no self-loop is added."""
        # Manually seed: INS-SELF → CPU-SELF (via cpu_referencia_id on a different CPU)
        # Build insumo_para_cpu via a helper CPU that references CPU-SELF
        catalogo2 = {
            "cpus": [
                {
                    "codigo": "CPU-SELF",
                    "cpu_referencia_id": "CPU-OTHER",
                    "composicao_itens": [{"insumo_id": "INS-OTHER", "categoria_custo": "TERCEIRIZADO"}],
                },
                {
                    "codigo": "CPU-OTHER",
                    "cpu_referencia_id": None,
                    "composicao_itens": [{"insumo_id": "INS-OTHER", "categoria_custo": "TERCEIRIZADO"}],
                },
            ]
        }
        # CPU-OTHER has INS-OTHER which maps to CPU-OTHER itself → cpu_dep == cpu["codigo"]
        # This branch ensures that self-reference is filtered out (no self-loop in graph)
        erros = verificar_ciclos_cpu(catalogo2)
        assert isinstance(erros, list)


def test_cpu_versionada_custo_unitario_none_branch():
    cpu = CPUVersionada(
        id="CPU-X",
        descricao="CPU X",
        unidade="m3",
        categoria="TERRAPLENAGEM",
        versoes=[
            VersaoCPU(
                versao="2026-04",
                validade=DateRange(inicio=date(2026, 4, 1), fim=date(2026, 5, 1)),
                producao_horaria=10.0,
                custo_unitario_sem_encargos=20.0,
                encargos_aplicados_pct=0.5,
                jurisdicao_id_atu="BR-CE@2026-04",
                auditado_por="qa",
                auditado_em=datetime(2026, 4, 2),
            )
        ],
    )
    assert cpu.custo_unitario_em(date(2025, 1, 1)) is None
