"""ADR-173 F2 — Propagação ponta a ponta: Escopo.roster_mo -> inputs["roster_mo"].

Prova que o mecanismo genérico de `Runtime.run_skill_on_plano` (spread de
`escopo.json` em `base_inputs`, `execution.py:120-127`) — o mesmo que já serve
`logistica_consumiveis` (ADR-128) — também carrega `roster_mo` para qualquer
skill, sem nenhum código de propagação dedicado. Fecha uma lacuna de teste que
`logistica_consumiveis` também tinha (nunca provado ponta a ponta pelo Runtime,
só por chamada direta da função da skill).
"""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

from concilium.application.runtime.mixins.execution import ExecutionMixin
from concilium.application.skills.base import SkillResult
from concilium.domain.models.canonical import CanonicalModel
from concilium.infrastructure.storage.project import ProjectStore


class _FakeRuntime(ExecutionMixin):
    def __init__(self):
        self.captured_kwargs: dict | None = None

    def get_skill_contract(self, skill_id):
        return SimpleNamespace(depends_on_skills=[])

    def _load_context(self, escopo_meta, project):
        return MagicMock(), {}, {}

    def _apply_runtime_defaults(self, skill_id, project, contexto, base_inputs):
        return dict(base_inputs)

    def _build_skill_kwargs(self, contract, **kwargs):
        self.captured_kwargs = kwargs
        return {}

    def _build_log_entry(self, *args, **kwargs):
        return {}

    def _process_side_effects(self, *args, **kwargs):
        pass


def _make_canonical() -> CanonicalModel:
    return CanonicalModel.model_validate(
        {
            "meta": {"gerado_em": "2026-01-01T00:00:00Z", "contexto_id": "ctx-test"},
            "projeto": {
                "id": "proj-test",
                "nome": "Test Project",
                "tipo_obra": "terraplenagem",
                "localizacao": "SP",
                "coordenadas": {"lat": -23.5, "lng": -46.6},
                "regime_trabalho": {"dias_semana": 6, "horas_dia": 8},
                "data_inicio": "2026-01-01",
                "data_termino": "2026-12-31",
                "snapshot_catalogo_id": "cat-v1",
                "snapshot_perfil_id": "perf-v1",
            },
        }
    )


@pytest.fixture
def project_store(tmp_path: Path) -> ProjectStore:
    proj_root = tmp_path / "proj-1"
    proj_root.mkdir()
    (proj_root / "snapshots").mkdir()
    meta = {"id": "proj-1", "nome": "Projeto Teste", "contexto_id": "ctx-test", "current_version": None}
    import json

    (proj_root / ProjectStore.META_FILE).write_text(json.dumps(meta), encoding="utf-8")
    return ProjectStore(proj_root)


class TestRosterMoPropagacaoPontaAPonta:
    def test_roster_mo_chega_em_inputs_via_create_escopo_real(self, project_store: ProjectStore):
        roster = [
            {
                "individuo_id": "mo-001",
                "funcao_id": "MO-ARMADOR",
                "salario_base_mensal": 3200.0,
                "data_admissao": "2026-01-05",
            }
        ]
        es = project_store.create_escopo(
            escopo_id="esc-1",
            nome="Lote A",
            tipo_obra="terraplenagem",
            localizacao="Fortaleza-CE",
            coordenadas_lat=-3.7172,
            coordenadas_lng=-38.5433,
            data_inicio="2026-01-01",
            data_termino="2026-12-31",
            roster_mo=roster,
        )
        plano_store = es.create_plan(nome="Plano 1")
        (plano_store.root / plano_store.CANONICAL_FILE).write_text(
            _make_canonical().model_dump_json(indent=2), encoding="utf-8"
        )

        runtime = _FakeRuntime()
        project = MagicMock()
        project.meta = {"id": "proj-1"}

        with (
            patch(
                "concilium.application.runtime.mixins.execution.SKILLS",
                {"04-cronograma": MagicMock()},
            ),
            patch(
                "concilium.application.runtime.mixins.execution._execute_skill",
                return_value=SkillResult(_make_canonical(), []),
            ),
        ):
            runtime.run_skill_on_plano("04-cronograma", project, plano_store)

        assert runtime.captured_kwargs is not None
        assert runtime.captured_kwargs["inputs"]["roster_mo"] == roster

    def test_sem_roster_mo_inputs_traz_lista_vazia(self, project_store: ProjectStore):
        es = project_store.create_escopo(
            escopo_id="esc-2",
            nome="Lote B",
            tipo_obra="terraplenagem",
            localizacao="Fortaleza-CE",
            coordenadas_lat=-3.7172,
            coordenadas_lng=-38.5433,
            data_inicio="2026-01-01",
            data_termino="2026-12-31",
        )
        plano_store = es.create_plan(nome="Plano 1")
        (plano_store.root / plano_store.CANONICAL_FILE).write_text(
            _make_canonical().model_dump_json(indent=2), encoding="utf-8"
        )

        runtime = _FakeRuntime()
        project = MagicMock()
        project.meta = {"id": "proj-1"}

        with (
            patch(
                "concilium.application.runtime.mixins.execution.SKILLS",
                {"04-cronograma": MagicMock()},
            ),
            patch(
                "concilium.application.runtime.mixins.execution._execute_skill",
                return_value=SkillResult(_make_canonical(), []),
            ),
        ):
            runtime.run_skill_on_plano("04-cronograma", project, plano_store)

        assert runtime.captured_kwargs["inputs"]["roster_mo"] == []
