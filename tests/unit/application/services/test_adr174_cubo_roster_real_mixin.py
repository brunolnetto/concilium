"""Testes para _CuboRosterRealMixin (ADR-174 F5, ConciliumService).

Espelha o padrão de TestGetCuboEstoqueConsumivelProjectionWithCanonical
(test_fat_concilium_service.py) — desvio: este mixin também precisa carregar
o Escopo (roster nunca é baked-in no canonical, ADR-174 D6), então os testes
cobrem esse carregamento à parte.
"""

from __future__ import annotations

from datetime import date
from pathlib import Path
from unittest.mock import MagicMock, patch

from concilium.application.services.concilium_service import ConciliumService
from concilium.domain.models.canonical import AtivoEquipamentoReal, MembroEquipeReal
from concilium.domain.models.project.escopo import Escopo


def _make_svc(config_root: Path | None = None):
    deps = MagicMock()
    if config_root is not None:
        deps.input_builder._config_root = config_root
    else:
        deps.input_builder._config_root = Path("/nonexistent_fake_root_abc123")
    deps.override_service.get_cpu_contexto.return_value = None
    svc = ConciliumService(dependencies=deps)
    return svc, deps


def _make_project_mock(meta: dict | None = None, current_version: str = "v1") -> MagicMock:
    p = MagicMock()
    p.meta = meta or {}
    p.current_version.return_value = current_version
    return p


def _make_escopo(roster_mo=None, roster_eq=None) -> Escopo:
    return Escopo(
        escopo_id="esc-1",
        projeto_id="proj-1",
        nome="Escopo",
        tipo_obra="terraplenagem",
        localizacao="BR",
        coordenadas_lat=0.0,
        coordenadas_lng=0.0,
        data_inicio=date(2026, 1, 1),
        data_termino=date(2026, 12, 31),
        roster_mo=roster_mo or [],
        roster_eq=roster_eq or [],
    )


class TestGetCuboRosterRealProjectionContract:
    def test_returns_dict(self):
        result = ConciliumService.get_cubo_roster_real_projection_contract()
        assert isinstance(result, dict)
        assert "faces" in result
        assert result["default_face"] == "resumo_por_instancia"


class TestGetCuboRosterRealProjectionWithCanonical:
    def test_returns_empty_projection_when_canonical_none(self):
        svc, deps = _make_svc()
        project = _make_project_mock()
        project.load_canonical.return_value = None
        deps.repository.get_project.return_value = project

        result = svc.get_cubo_roster_real_projection("p1")
        assert result["rows"] == []
        assert result["invariantes_ok"] is True

    def test_returns_projection_when_canonical_and_roster_exist(self):
        svc, deps = _make_svc()
        canonical = MagicMock()
        project = _make_project_mock()
        project.load_canonical.return_value = canonical
        deps.repository.get_project.return_value = project

        mock_proj = {"face": "resumo_por_instancia", "rows": [{"instancia_id": "mo-001"}], "version": "v1"}
        with patch(
            "concilium.application.services.analytics.cubo_roster_real_projection.resolve_cubo_roster_real_projection",
            return_value=mock_proj,
        ):
            result = svc.get_cubo_roster_real_projection("p1", face="resumo_por_instancia")
        assert result["face"] == "resumo_por_instancia"

    def test_carrega_roster_do_escopo_e_repassa_para_resolve(self):
        svc, deps = _make_svc()
        canonical = MagicMock()
        project = _make_project_mock()
        project.load_canonical.return_value = canonical
        membro = MembroEquipeReal(
            individuo_id="mo-001", funcao_id="MO-ARMADOR", salario_base_mensal=3000.0, data_admissao=date(2026, 1, 1)
        )
        ativo = AtivoEquipamentoReal(
            ativo_id="eq-001",
            equip_id="EQ-ESCAVADEIRA",
            custo_locacao_mensal_real=12000.0,
            data_contrato_inicio=date(2026, 1, 1),
        )
        project.escopo.return_value.to_escopo.return_value = _make_escopo(roster_mo=[membro], roster_eq=[ativo])
        deps.repository.get_project.return_value = project

        with patch(
            "concilium.application.services.analytics.cubo_roster_real_projection.resolve_cubo_roster_real_projection",
            return_value={"rows": []},
        ) as mock_resolve:
            svc.get_cubo_roster_real_projection("p1", escopo_id="esc-1")

        args, kwargs = mock_resolve.call_args
        assert args[1] == [membro]
        assert args[2] == [ativo]
        project.escopo.assert_called_with("esc-1")

    def test_escopo_ausente_nao_lanca_erro_roster_vazio(self):
        svc, deps = _make_svc()
        canonical = MagicMock()
        project = _make_project_mock()
        project.load_canonical.return_value = canonical
        project.escopo.return_value.to_escopo.return_value = None
        deps.repository.get_project.return_value = project

        with patch(
            "concilium.application.services.analytics.cubo_roster_real_projection.resolve_cubo_roster_real_projection",
            return_value={"rows": []},
        ) as mock_resolve:
            svc.get_cubo_roster_real_projection("p1")

        args, kwargs = mock_resolve.call_args
        assert args[1] == []
        assert args[2] == []

    def test_repository_indisponivel_nao_lanca_erro(self):
        """_load_roster_real/_load_catalogo_best_effort degradam para
        vazio/None quando repository não está disponível — nunca lançam."""
        svc, deps = _make_svc()
        deps.repository = None
        svc._dependencies = deps

        assert svc._load_roster_real("p1", "default") == ([], [])
        assert svc._load_catalogo_best_effort("p1") is None
