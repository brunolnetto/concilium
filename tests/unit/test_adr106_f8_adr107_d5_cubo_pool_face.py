"""ADR-106 F8 + ADR-107 D5 — CuboPoolFace e dimensão tipo_combustivel.

TDD: testes para estrutura de dados CuboPoolFace e CuboCombustivelFace.

ADR-106 F8: Pool occupancy face com dimensões item_id × semana × tipo_recurso
  e medidas horas_ativas, horas_idle, custo_ativo, custo_idle, estado.

ADR-107 D5: tipo_combustivel como dimensão no cubo analítico quando
  categoria_insumo == "COMBUSTIVEL".

Invariantes:
  - CuboPoolFace exporta tipos_recurso e semanas corretos
  - CelulaOcupacaoPool.utilizacao ∈ [0.0, 1.0]
  - custo_total_ativo() + custo_total_idle() == soma de todas as células
  - CuboCombustivelFace.custo_por_tipo() retorna breakdown por tipo
  - _build_cubo_pool_face retorna CuboPoolFace válido (stub)
"""

from __future__ import annotations

import pytest


# ---------------------------------------------------------------------------
# CelulaOcupacaoPool — estrutura de dados
# ---------------------------------------------------------------------------


class TestCelulaOcupacaoPool:
    def test_import_existe(self):
        from concilium.domain.models.cubo_pool import CelulaOcupacaoPool

        assert CelulaOcupacaoPool is not None

    def test_instanciavel_com_campos_obrigatorios(self):
        from concilium.domain.models.cubo_pool import CelulaOcupacaoPool

        c = CelulaOcupacaoPool(
            item_id="EAP-001",
            semana="S001",
            tipo_recurso="EQUIP-ESCAV-22T",
        )
        assert c.item_id == "EAP-001"
        assert c.semana == "S001"
        assert c.tipo_recurso == "EQUIP-ESCAV-22T"

    def test_defaults_zero(self):
        from concilium.domain.models.cubo_pool import CelulaOcupacaoPool

        c = CelulaOcupacaoPool(item_id="X", semana="S001", tipo_recurso="EQUIP-A")
        assert c.horas_ativas == pytest.approx(0.0)
        assert c.horas_idle == pytest.approx(0.0)
        assert c.custo_ativo == pytest.approx(0.0)
        assert c.custo_idle == pytest.approx(0.0)

    def test_estado_default_ativo(self):
        from concilium.domain.models.cubo_pool import CelulaOcupacaoPool

        c = CelulaOcupacaoPool(item_id="X", semana="S001", tipo_recurso="R")
        assert c.estado == "ativo"

    def test_estados_aceitos(self):
        from concilium.domain.models.cubo_pool import CelulaOcupacaoPool

        for estado in ("mobilizando", "ativo", "idle", "desmobilizando", "off"):
            c = CelulaOcupacaoPool(item_id="X", semana="S001", tipo_recurso="R", estado=estado)
            assert c.estado == estado

    def test_utilizacao_ativa(self):
        from concilium.domain.models.cubo_pool import CelulaOcupacaoPool

        c = CelulaOcupacaoPool(
            item_id="X",
            semana="S001",
            tipo_recurso="R",
            horas_ativas=48.0,
            horas_idle=0.0,
        )
        assert c.utilizacao == pytest.approx(1.0)

    def test_utilizacao_parcial(self):
        from concilium.domain.models.cubo_pool import CelulaOcupacaoPool

        c = CelulaOcupacaoPool(
            item_id="X",
            semana="S001",
            tipo_recurso="R",
            horas_ativas=24.0,
            horas_idle=24.0,
        )
        assert c.utilizacao == pytest.approx(0.5, abs=0.01)

    def test_utilizacao_zero_sem_horas(self):
        from concilium.domain.models.cubo_pool import CelulaOcupacaoPool

        c = CelulaOcupacaoPool(item_id="X", semana="S001", tipo_recurso="R")
        assert c.utilizacao == pytest.approx(0.0)

    def test_custo_total_soma_ativo_mais_idle(self):
        from concilium.domain.models.cubo_pool import CelulaOcupacaoPool

        c = CelulaOcupacaoPool(
            item_id="X",
            semana="S001",
            tipo_recurso="R",
            custo_ativo=5_000.0,
            custo_idle=1_200.0,
        )
        assert c.custo_total == pytest.approx(6_200.0, abs=0.01)


# ---------------------------------------------------------------------------
# CuboPoolFace — container
# ---------------------------------------------------------------------------


class TestCuboPoolFace:
    def _make_face(self):
        from concilium.domain.models.cubo_pool import CelulaOcupacaoPool, CuboPoolFace

        celulas = (
            CelulaOcupacaoPool(
                item_id="EAP-001",
                semana="S001",
                tipo_recurso="EQUIP-ESCAV-22T",
                horas_ativas=48.0,
                custo_ativo=12_000.0,
                estado="ativo",
            ),
            CelulaOcupacaoPool(
                item_id="EAP-001",
                semana="S002",
                tipo_recurso="EQUIP-ESCAV-22T",
                horas_ativas=40.0,
                horas_idle=8.0,
                custo_ativo=10_000.0,
                custo_idle=2_000.0,
                estado="idle",
            ),
            CelulaOcupacaoPool(
                item_id="EAP-002",
                semana="S001",
                tipo_recurso="FUNC-OPER-ESCAV",
                horas_ativas=48.0,
                custo_ativo=3_000.0,
                estado="ativo",
            ),
        )
        return CuboPoolFace(projeto_id="PROJ-001", gerado_em="2026-06-11", celulas=celulas)

    def test_instanciavel(self):
        from concilium.domain.models.cubo_pool import CuboPoolFace

        f = CuboPoolFace(projeto_id="P", gerado_em="2026-01-01")
        assert f.projeto_id == "P"

    def test_campos_obrigatorios(self):
        face = self._make_face()
        assert hasattr(face, "projeto_id")
        assert hasattr(face, "gerado_em")
        assert hasattr(face, "celulas")

    def test_dimensoes_tipo_recurso(self):
        """tipos_recurso() deve retornar lista de tipos presentes."""
        face = self._make_face()
        tipos = face.tipos_recurso()
        assert "EQUIP-ESCAV-22T" in tipos
        assert "FUNC-OPER-ESCAV" in tipos

    def test_dimensoes_semana(self):
        """semanas() deve retornar lista ordenada de semanas."""
        face = self._make_face()
        semanas = face.semanas()
        assert "S001" in semanas
        assert "S002" in semanas
        assert semanas == sorted(semanas)

    def test_custo_total_ativo(self):
        face = self._make_face()
        esperado = 12_000.0 + 10_000.0 + 3_000.0
        assert face.custo_total_ativo() == pytest.approx(esperado, abs=0.01)

    def test_custo_total_idle(self):
        face = self._make_face()
        assert face.custo_total_idle() == pytest.approx(2_000.0, abs=0.01)

    def test_por_semana_chaves_corretas(self):
        face = self._make_face()
        por_sem = face.por_semana()
        assert "S001" in por_sem
        assert "S002" in por_sem
        assert len(por_sem["S001"]) == 2  # dois recursos na semana S001

    def test_por_tipo_recurso(self):
        face = self._make_face()
        por_tipo = face.por_tipo_recurso()
        assert "EQUIP-ESCAV-22T" in por_tipo
        assert len(por_tipo["EQUIP-ESCAV-22T"]) == 2  # 2 semanas


# ---------------------------------------------------------------------------
# CuboCombustivelFace + CelulaCombustivel (ADR-107 D5)
# ---------------------------------------------------------------------------


class TestCelulaCombustivel:
    def test_import_existe(self):
        from concilium.domain.models.cubo_pool import CelulaCombustivel

        assert CelulaCombustivel is not None

    def test_instanciavel(self):
        from concilium.domain.models.cubo_pool import CelulaCombustivel

        c = CelulaCombustivel(
            item_id="EAP-001",
            semana="S001",
            tipo_combustivel="diesel_s10",
            custo=2_500.0,
        )
        assert c.tipo_combustivel == "diesel_s10"
        assert c.custo == pytest.approx(2_500.0)

    def test_defaults(self):
        from concilium.domain.models.cubo_pool import CelulaCombustivel

        c = CelulaCombustivel(item_id="X", semana="S001", tipo_combustivel="eletrico")
        assert c.custo == pytest.approx(0.0)
        assert c.volume_litros == pytest.approx(0.0)


class TestCuboCombustivelFace:
    def _make_face(self):
        from concilium.domain.models.cubo_pool import CelulaCombustivel, CuboCombustivelFace

        celulas = (
            CelulaCombustivel(item_id="EAP-001", semana="S001", tipo_combustivel="diesel_s10", custo=3_000.0),
            CelulaCombustivel(item_id="EAP-001", semana="S002", tipo_combustivel="diesel_s10", custo=3_100.0),
            CelulaCombustivel(item_id="EAP-002", semana="S001", tipo_combustivel="eletrico", custo=800.0),
        )
        return CuboCombustivelFace(projeto_id="PROJ-001", gerado_em="2026-06-11", celulas=celulas)

    def test_instanciavel(self):
        from concilium.domain.models.cubo_pool import CuboCombustivelFace

        f = CuboCombustivelFace(projeto_id="P", gerado_em="2026-01-01")
        assert f is not None

    def test_custo_por_tipo_agrupa_corretamente(self):
        face = self._make_face()
        por_tipo = face.custo_por_tipo()
        assert "diesel_s10" in por_tipo
        assert "eletrico" in por_tipo
        assert por_tipo["diesel_s10"] == pytest.approx(6_100.0, abs=0.01)
        assert por_tipo["eletrico"] == pytest.approx(800.0, abs=0.01)

    def test_tipos_presentes(self):
        face = self._make_face()
        tipos = face.tipos_presentes()
        assert "diesel_s10" in tipos
        assert "eletrico" in tipos

    def test_tipos_presentes_ordenados(self):
        face = self._make_face()
        tipos = face.tipos_presentes()
        assert tipos == sorted(tipos)

    def test_tipo_combustivel_como_dimensao(self):
        """A face suporta filtro por tipo_combustivel (dimensão analítica)."""
        face = self._make_face()
        diesel_only = [c for c in face.celulas if c.tipo_combustivel == "diesel_s10"]
        assert len(diesel_only) == 2

    def test_face_vazia(self):
        from concilium.domain.models.cubo_pool import CuboCombustivelFace

        face = CuboCombustivelFace(projeto_id="P", gerado_em="2026-01-01")
        assert face.custo_por_tipo() == {}
        assert face.tipos_presentes() == []


# ---------------------------------------------------------------------------
# _build_cubo_pool_face — stub builder (ADR-106 F8)
# ---------------------------------------------------------------------------


class TestBuildCuboPoolFaceStub:
    def _import_builder(self):
        import importlib.util
        from pathlib import Path

        here = Path(__file__).resolve().parent.parent.parent
        p = (
            here
            / "src"
            / "concilium"
            / "application"
            / "skills"
            / "manifests"
            / "06-resultado-financeiro"
            / "_consolidacao"
            / "_skill_helpers_a.py"
        )
        spec = importlib.util.spec_from_file_location("skill_helpers_a_consolidacao", p)
        mod = importlib.util.module_from_spec(spec)  # type: ignore[arg-type]
        spec.loader.exec_module(mod)  # type: ignore[union-attr]
        return mod._build_cubo_pool_face

    def test_builder_existe(self):
        fn = self._import_builder()
        assert callable(fn)

    def test_retorna_cubo_pool_face(self):
        from concilium.domain.models.cubo_pool import CuboPoolFace

        fn = self._import_builder()
        result = fn(equipes_diretas=[], cronograma=[], projeto_id="PROJ-TEST")
        assert isinstance(result, CuboPoolFace)

    def test_retorna_face_com_projeto_id(self):
        fn = self._import_builder()
        result = fn(equipes_diretas=[], cronograma=[], projeto_id="MINHA-OBRA")
        assert result.projeto_id == "MINHA-OBRA"

    def test_retorna_gerado_em_nao_vazio(self):
        fn = self._import_builder()
        result = fn(equipes_diretas=[], cronograma=[])
        assert result.gerado_em != ""

    def test_stub_retorna_face_vazia(self):
        """Stub ainda retorna células vazias — aguarda ADR-086 extensão."""
        fn = self._import_builder()
        result = fn(equipes_diretas=[], cronograma=[])
        # Stub retorna face vazia (implementação futura)
        assert isinstance(result.celulas, tuple)
