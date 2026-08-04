"""Coverage sweep 8 — cube_projection_views, side_effects, escopo_store, etapa_diffs."""

from __future__ import annotations

import pytest

# ─── application/runtime/deliverables/side_effects.py ────────────────────────


class TestSideEffects:
    def test_json_default_unserializable_raises(self):
        from concilium.application.runtime.deliverables.side_effects import _json_default

        with pytest.raises(TypeError):
            _json_default(object())

    def test_dedup_insumos_removes_duplicates(self):
        from concilium.application.runtime.deliverables.side_effects import _dedup_insumos

        insumos = [
            {"codigo": "I1", "preco": 100},
            {"codigo": "I1", "preco": 100},
            {"codigo": "I2", "preco": 200},
        ]
        result = _dedup_insumos(insumos)
        assert len(result) == 2

    def test_append_png_gallery_empty(self):
        from concilium.application.runtime.deliverables.side_effects import _append_png_gallery

        result = _append_png_gallery("# Report\n\nContent.", [])
        assert isinstance(result, str)
        assert "# Report" in result

    def test_append_png_gallery_with_pngs(self):
        from concilium.application.runtime.deliverables.side_effects import _append_png_gallery

        result = _append_png_gallery("Content.", ["chart1.png", "chart2.png"])
        assert isinstance(result, str)

    def test_load_insumos_subdir_empty(self, tmp_path):
        from concilium.application.runtime.deliverables.side_effects import _load_insumos_subdir

        insumos = []
        _load_insumos_subdir(tmp_path, insumos)
        assert insumos == []


# ─── _PlanoAsVersionedProject ──────────────────────────────────────────────
#
# Antes deste adapter, run_skill_on_plano passava o ProjectHandle do PROJETO
# junto com plano_store.plano_id como se fosse uma versão flat vN — os side
# effects (relatórios, PDFs, artefatos, schedules_weekly.json) acabavam
# gravados soltos em {project_id}/{plano_id}/... (pasta UUID órfã na raiz do
# projeto) em vez de dentro da árvore real do plano
# ({project_id}/escopos/{escopo_id}/planos/{plano_id}/...).


class TestPlanoAsVersionedProject:
    def _make_plano(self, tmp_path):
        from concilium.infrastructure.storage.store_factory import build_project_repository

        project = build_project_repository(tmp_path).create_project("Test", "ctx")
        es = project.create_escopo(
            escopo_id="esc-1",
            nome="Escopo Teste",
            tipo_obra="terraplenagem",
            localizacao="SP",
            coordenadas_lat=0.0,
            coordenadas_lng=0.0,
            data_inicio="2026-01-01",
            data_termino="2026-12-31",
        )
        return project, es.create_plan(nome="Plano 1")

    def test_save_output_file_writes_inside_plano_tree_not_project_root(self, tmp_path):
        from concilium.application.runtime.deliverables.side_effects import _PlanoAsVersionedProject

        project, plano = self._make_plano(tmp_path)
        adapter = _PlanoAsVersionedProject(plano)

        # version (2º arg) é ignorada — o plano já se auto-escopa.
        adapter.save_output_file(b"conteudo", "versao-ignorada", "relatorio.pdf")

        assert plano.load_output_file("relatorio.pdf") == b"conteudo"
        # Nada foi gravado solto em {project_id}/{plano_id}/... na raiz do projeto.
        assert not project.exists(f"{plano.plano_id}/outputs/reports/relatorio.pdf")

    def test_save_intermediate_file_writes_inside_plano_tree(self, tmp_path):
        from concilium.application.runtime.deliverables.side_effects import _PlanoAsVersionedProject

        project, plano = self._make_plano(tmp_path)
        adapter = _PlanoAsVersionedProject(plano)

        adapter.save_intermediate_file("schedules_weekly.json", b'{"a": 1}', "versao-ignorada")

        assert plano.load_intermediate_file("schedules_weekly.json") == b'{"a": 1}'
        assert not project.exists(f"{plano.plano_id}/intermediate/schedules_weekly.json")

    def test_write_json_strips_version_prefix_and_writes_to_plano(self, tmp_path):
        from concilium.application.runtime.deliverables.side_effects import _PlanoAsVersionedProject

        project, plano = self._make_plano(tmp_path)
        adapter = _PlanoAsVersionedProject(plano)

        adapter.write_json(f"{plano.plano_id}/artifacts/abc.json", {"k": "v"})

        assert plano.read_json("artifacts/abc.json", None) == {"k": "v"}
        assert not project.exists(f"{plano.plano_id}/artifacts/abc.json")

    def test_load_canonical_ignores_version_param(self, tmp_path):
        from concilium.application.runtime.deliverables.side_effects import _PlanoAsVersionedProject
        from concilium.domain.models.canonical import CanonicalModel

        _project, plano = self._make_plano(tmp_path)
        canonical = CanonicalModel.model_validate(
            {
                "meta": {"gerado_em": "2026-01-01T00:00:00Z", "contexto_id": "ctx"},
                "projeto": {
                    "id": "proj-1",
                    "nome": "Teste",
                    "tipo_obra": "terraplenagem",
                    "localizacao": "SP",
                    "coordenadas": {"lat": 0.0, "lng": 0.0},
                    "regime_trabalho": {"dias_semana": 6, "horas_dia": 8},
                    "data_inicio": "2026-01-01",
                    "data_termino": "2026-12-31",
                    "snapshot_catalogo_id": "cat-v1",
                    "snapshot_perfil_id": "perf-v1",
                },
            }
        )
        plano.save_canonical(canonical)

        adapter = _PlanoAsVersionedProject(plano)
        assert adapter.load_canonical("versao-ignorada") is not None
        assert adapter.load_canonical("versao-ignorada").projeto.nome == "Teste"



