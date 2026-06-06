"""Testes de integração: multi-escopo e planos paralelos (ADR-031)."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from concilium.domain.models.resultado_consolidado import BreakdownEscopo, ResultadoConsolidadoProjeto
from concilium.infrastructure.storage.escopo_store import EscopoStore, PlanoStore
from concilium.infrastructure.storage.project import ProjectStore

# ── Fixtures ────────────────────────────────────────────────────────────────


@pytest.fixture
def projeto_novo(tmp_path: Path) -> ProjectStore:
    """ProjectStore novo (pré-ADR-031, sem vN/ nem escopos/)."""
    p = tmp_path / "projetos" / "proj-teste"
    p.mkdir(parents=True)
    meta = {
        "id": "proj-teste",
        "nome": "Projeto Teste Multi-Escopo",
        "contexto_id": "test",
        "current_version": None,
        "snapshot_catalogo_id": "",
        "snapshot_perfil_id": "",
    }
    (p / "meta.json").write_text(json.dumps(meta), encoding="utf-8")
    (p / "snapshots").mkdir()
    return ProjectStore(p)


@pytest.fixture
def projeto_legado(tmp_path: Path) -> ProjectStore:
    """ProjectStore com estrutura legada vN/ (pré-ADR-031)."""
    p = tmp_path / "projetos" / "proj-legado"
    p.mkdir(parents=True)
    meta = {
        "id": "proj-legado",
        "nome": "Projeto Legado",
        "contexto_id": "test",
        "current_version": "v1",
        "snapshot_catalogo_id": "",
        "snapshot_perfil_id": "",
        "approved_versions": [],
    }
    (p / "meta.json").write_text(json.dumps(meta), encoding="utf-8")
    (p / "snapshots").mkdir()
    # Cria versão legada
    v1 = p / "v1"
    v1.mkdir()
    (v1 / "outputs").mkdir()
    (v1 / "invocations.log").touch()
    return ProjectStore(p)


# ── create_escopo / list_escopos ─────────────────────────────────────────────


class TestEscopos:
    def test_criar_escopo_cria_diretorio(self, projeto_novo):
        es = projeto_novo.create_escopo(
            escopo_id="lote-a",
            nome="Lote A",
            tipo_obra="terraplenagem",
            localizacao="Aracoiaba, CE",
            coordenadas_lat=-4.36,
            coordenadas_lng=-38.81,
            data_inicio="2026-06-01",
            data_termino="2026-12-31",
        )
        assert es.root.exists()
        assert (es.root / "planos").exists()
        assert (es.root / EscopoStore.ESCOPO_FILE).exists()

    def test_criar_escopo_registra_meta(self, projeto_novo):
        projeto_novo.create_escopo(
            escopo_id="lote-b",
            nome="Lote B — Pavimentação",
            tipo_obra="pavimentacao",
            localizacao="Maranguape, CE",
            coordenadas_lat=-3.88,
            coordenadas_lng=-38.68,
            data_inicio="2026-01-01",
            data_termino="2026-09-30",
        )
        es = projeto_novo.escopo("lote-b")
        m = es.meta
        assert m["nome"] == "Lote B — Pavimentação"
        assert m["tipo_obra"] == "pavimentacao"
        assert m["status"] == "RASCUNHO"

    def test_criar_escopo_duplicado_lanca_excecao(self, projeto_novo):
        projeto_novo.create_escopo(
            escopo_id="lote-a",
            nome="Lote A",
            tipo_obra="terraplenagem",
            localizacao="Aracoiaba, CE",
            coordenadas_lat=-4.36,
            coordenadas_lng=-38.81,
            data_inicio="2026-06-01",
            data_termino="2026-12-31",
        )
        with pytest.raises(FileExistsError, match="lote-a"):
            projeto_novo.create_escopo(
                escopo_id="lote-a",
                nome="Lote A duplicado",
                tipo_obra="terraplenagem",
                localizacao="Aracoiaba, CE",
                coordenadas_lat=-4.36,
                coordenadas_lng=-38.81,
                data_inicio="2026-06-01",
                data_termino="2026-12-31",
            )

    def test_list_escopos_retorna_ids_ordenados(self, projeto_novo):
        for eid in ("lote-c", "lote-a", "lote-b"):
            projeto_novo.create_escopo(
                escopo_id=eid,
                nome=f"Escopo {eid}",
                tipo_obra="terraplenagem",
                localizacao="Teste",
                coordenadas_lat=0,
                coordenadas_lng=0,
                data_inicio="2026-01-01",
                data_termino="2026-12-31",
            )
        assert projeto_novo.list_escopos() == ["lote-a", "lote-b", "lote-c"]


# ── PlanoStore ───────────────────────────────────────────────────────────────


class TestPlanos:
    def _make_escopo(self, projeto_novo) -> EscopoStore:
        return projeto_novo.create_escopo(
            escopo_id="lote-a",
            nome="Lote A",
            tipo_obra="terraplenagem",
            localizacao="Aracoiaba, CE",
            coordenadas_lat=-4.36,
            coordenadas_lng=-38.81,
            data_inicio="2026-06-01",
            data_termino="2026-12-31",
        )

    def test_criar_plano_cria_diretorio(self, projeto_novo):
        es = self._make_escopo(projeto_novo)
        ps = es.create_plan("Plano Agressivo", hipotese="Equipe dupla")
        assert ps.root.exists()
        assert (ps.root / PlanoStore.PLANO_FILE).exists()
        assert (ps.root / "outputs").exists()

    def test_criar_plano_meta_inicial(self, projeto_novo):
        es = self._make_escopo(projeto_novo)
        ps = es.create_plan("Plano Conservador", hipotese="Equipe simples")
        assert ps.meta["nome"] == "Plano Conservador"
        assert ps.meta["status"] == "RASCUNHO"
        assert ps.meta["hipotese"] == "Equipe simples"
        assert ps.meta["versao_iteracao"] == 1

    def test_list_plans(self, projeto_novo):
        es = self._make_escopo(projeto_novo)
        ps1 = es.create_plan("P1")
        ps2 = es.create_plan("P2")
        plans = es.list_plans()
        assert len(plans) == 2
        assert ps1.plano_id in plans
        assert ps2.plano_id in plans

    def test_approved_plan_none_sem_aprovacao(self, projeto_novo):
        es = self._make_escopo(projeto_novo)
        es.create_plan("Plano A")
        assert es.approved_plan() is None

    def test_approve_plan_marca_aprovado(self, projeto_novo):
        es = self._make_escopo(projeto_novo)
        ps = es.create_plan("Plano Principal")
        # precisa de canonical.json para poder aprovar (chmod 444 é optional se não existir)
        (ps.root / PlanoStore.CANONICAL_FILE).write_text("{}", encoding="utf-8")
        (ps.root / PlanoStore.INVOCATIONS_LOG).write_text("", encoding="utf-8")
        es.approve_plan(ps.plano_id)
        assert es.approved_plan() is not None
        assert es.approved_plan().plano_id == ps.plano_id
        assert es.plan(ps.plano_id).status == "APROVADO"

    def test_approve_plan_arquiva_outros(self, projeto_novo):
        es = self._make_escopo(projeto_novo)
        ps1 = es.create_plan("Plano A")
        ps2 = es.create_plan("Plano B")
        ps3 = es.create_plan("Plano C")
        for ps in (ps1, ps2, ps3):
            (ps.root / PlanoStore.CANONICAL_FILE).write_text("{}", encoding="utf-8")
            (ps.root / PlanoStore.INVOCATIONS_LOG).write_text("", encoding="utf-8")
        arquivados = es.approve_plan(ps2.plano_id)
        assert sorted(arquivados) == sorted([ps1.plano_id, ps3.plano_id])
        assert es.plan(ps1.plano_id).status == "ARQUIVADO"
        assert es.plan(ps2.plano_id).status == "APROVADO"
        assert es.plan(ps3.plano_id).status == "ARQUIVADO"

    def test_active_plan_retorna_aprovado_se_existir(self, projeto_novo):
        es = self._make_escopo(projeto_novo)
        ps = es.create_plan("Único")
        (ps.root / PlanoStore.CANONICAL_FILE).write_text("{}", encoding="utf-8")
        (ps.root / PlanoStore.INVOCATIONS_LOG).write_text("", encoding="utf-8")
        es.approve_plan(ps.plano_id)
        assert es.active_plan().plano_id == ps.plano_id

    def test_active_plan_retorna_rascunho_se_sem_aprovado(self, projeto_novo):
        es = self._make_escopo(projeto_novo)
        ps = es.create_plan("Rascunho")
        assert es.active_plan().plano_id == ps.plano_id

    def test_log_invocation_e_read(self, projeto_novo):
        es = self._make_escopo(projeto_novo)
        ps = es.create_plan("Plano Log")
        ps.log_invocation({"skill": "01-escopo-e-eap", "status": "OK"})
        ps.log_invocation({"skill": "02-produtividade-climatica", "status": "ERRO"})
        invocations = ps.read_invocations()
        assert len(invocations) == 2
        assert invocations[0]["skill"] == "01-escopo-e-eap"

    def test_save_output_file(self, projeto_novo):
        es = self._make_escopo(projeto_novo)
        ps = es.create_plan("Plano Output")
        p = ps.save_output_file(b"dummy-xlsx-data", "resultado.xlsm")
        assert p.exists()
        assert ps.load_output_file("resultado.xlsm") == b"dummy-xlsx-data"
        assert "resultado.xlsm" in ps.list_output_files()

    def test_new_iteration_incrementa_versao(self, projeto_novo):
        es = self._make_escopo(projeto_novo)
        ps = es.create_plan("Plano Original")
        ps2 = ps.new_iteration()
        assert ps2.meta["versao_iteracao"] == 2
        assert ps2.plano_id != ps.plano_id
        assert ps2.meta["status"] == "RASCUNHO"


# ── ResultadoConsolidadoProjeto ───────────────────────────────────────────────


class TestResultadoConsolidado:
    def _make_breakdown(self, escopo_id: str, nome: str, venda: float, custo: float) -> BreakdownEscopo:
        resultado = venda - custo
        margem = resultado / venda if venda > 0 else 0.0
        return BreakdownEscopo(
            escopo_id=escopo_id,
            nome=nome,
            plano_id="plano-abc",
            status_plano="APROVADO",
            venda_com_bdi=venda,
            custo_total=custo,
            resultado_financeiro=resultado,
            margem_pct=margem,
            status_margem="VERDE" if margem >= 0.08 else ("AMARELO" if margem >= 0.04 else "VERMELHO"),
            peso_relativo=0.0,
        )

    def test_calcular_agregacao_basica(self):
        b1 = self._make_breakdown("lote-a", "Lote A", 1_000_000, 900_000)
        b2 = self._make_breakdown("lote-b", "Lote B", 500_000, 450_000)
        rc = ResultadoConsolidadoProjeto.calcular("proj-x", [b1, b2])
        assert rc.venda_total_com_bdi == 1_500_000
        assert rc.custo_total == 1_350_000
        assert rc.resultado_financeiro == 150_000

    def test_calcular_margem_pct(self):
        b1 = self._make_breakdown("lote-a", "Lote A", 1_000_000, 900_000)
        rc = ResultadoConsolidadoProjeto.calcular("proj-x", [b1])
        assert abs(rc.margem_pct - 0.10) < 0.0001

    def test_calcular_status_verde(self):
        b = self._make_breakdown("lote-a", "A", 100, 90)
        rc = ResultadoConsolidadoProjeto.calcular("p", [b])
        assert rc.status_margem == "VERDE"

    def test_calcular_status_amarelo(self):
        b = self._make_breakdown("lote-a", "A", 100, 95)
        rc = ResultadoConsolidadoProjeto.calcular("p", [b])
        assert rc.status_margem == "AMARELO"

    def test_calcular_status_vermelho(self):
        b = self._make_breakdown("lote-a", "A", 100, 98)
        rc = ResultadoConsolidadoProjeto.calcular("p", [b])
        assert rc.status_margem == "VERMELHO"

    def test_calcular_peso_relativo(self):
        b1 = self._make_breakdown("lote-a", "A", 1_000_000, 900_000)
        b2 = self._make_breakdown("lote-b", "B", 1_000_000, 900_000)
        rc = ResultadoConsolidadoProjeto.calcular("p", [b1, b2])
        for item in rc.breakdown:
            assert abs(item.peso_relativo - 0.5) < 0.001

    def test_calcular_com_escopos_excluidos(self):
        b = self._make_breakdown("lote-a", "A", 500_000, 450_000)
        rc = ResultadoConsolidadoProjeto.calcular(
            "p",
            [b],
            escopos_excluidos=["lote-b"],
            avisos=["lote-b sem pipeline completo"],
        )
        assert "lote-b" in rc.escopos_excluidos
        assert len(rc.avisos) == 1

    def test_calcular_lista_vazia_retorna_zero(self):
        rc = ResultadoConsolidadoProjeto.calcular("p", [])
        assert rc.venda_total_com_bdi == 0
        assert rc.custo_total == 0
        assert rc.margem_pct == 0.0
        assert rc.status_margem == "VERMELHO"
