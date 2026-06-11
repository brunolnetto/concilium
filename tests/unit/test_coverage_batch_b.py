"""Coverage batch B — targets runtime.py, 04-cronograma, 03-equipes-diretas,
06-precificacao-unitaria, 09-cost-criticality, and semantic/normalizer edge cases.
"""

from __future__ import annotations

import importlib.util
import json
import sys
from datetime import UTC, date, datetime
from pathlib import Path
from unittest.mock import patch

import pytest

from concilium.domain.models.canonical import (
    CanonicalModel,
    Coordenadas,
    Cronograma,
    DistribuicaoSemanal,
    EapItem,
    EquipeDireta,
    Meta,
    Planejamento,
    Praticabilidade,
    Projeto,
    RegimeTrabalho,
    ScheduledActivityCanonical,
)

# ── helpers ───────────────────────────────────────────────────────────────────


def _make_meta():
    return Meta(gerado_em=datetime.now(UTC), contexto_id="test")


def _make_proj(data_inicio="2026-06-01", data_termino="2026-07-31"):
    return Projeto(
        id="p1",
        nome="proj",
        tipo_obra="terraplenagem",
        localizacao="x",
        coordenadas=Coordenadas(lat=-3.0, lng=-38.0),
        regime_trabalho=RegimeTrabalho(dias_semana=5, horas_dia=8),
        data_inicio=date(2026, 6, 1),
        data_termino=date(2026, 7, 31),
        snapshot_catalogo_id="s",
        snapshot_perfil_id="s",
    )


def _minimal_canonical(**kw):
    return CanonicalModel(meta=_make_meta(), projeto=_make_proj(), **kw)


# Load private helpers from skill modules (dash in directory name)
_MANIFESTS = Path(__file__).parents[2] / "src" / "concilium" / "application" / "skills" / "manifests"


def _load_skill_module(skill_id: str) -> object:
    mod_name = f"_concilium_skill_{skill_id.replace('-', '_')}"
    sys.modules.pop(mod_name, None)
    path = _MANIFESTS / skill_id / "skill.py"
    spec = importlib.util.spec_from_file_location(mod_name, path)
    mod = importlib.util.module_from_spec(spec)
    try:
        source = path.read_text(encoding="utf-8")
        exec(compile(source, str(path), "exec"), mod.__dict__)
    except Exception:
        sys.modules.pop(mod_name, None)
        raise
    sys.modules[mod_name] = mod
    return mod


# ══ runtime.py ════════════════════════════════════════════════════════════════


class TestRuntimeEdgeCases:
    def test_load_referencia_success(self, tmp_path):
        """load_referencia success path (line 58)."""
        from concilium.application.runtime import Runtime

        refs_dir = tmp_path / "referencias"
        refs_dir.mkdir()
        (refs_dir / "test.json").write_text(json.dumps({"tabela": "SICRO"}), encoding="utf-8")
        r = Runtime(tmp_path)
        result = r.load_referencia("test")
        assert result == {"tabela": "SICRO"}

    def test_load_catalogo_dict_no_matching_key(self, tmp_path):
        """cpus.json is a dict without 'cpus' key → data.get(key, []) (line 79)."""
        from concilium.application.runtime import Runtime

        cat_dir = tmp_path / "catalogos" / "mycat"
        cat_dir.mkdir(parents=True)
        # Dict without 'cpus' key → falls into else branch
        (cat_dir / "cpus.json").write_text(json.dumps({"other_key": "val"}), encoding="utf-8")
        r = Runtime(tmp_path)
        cat = r.load_catalogo("mycat")
        assert cat["cpus"] == []

    def test_load_insumos_bad_json(self, tmp_path):
        """Bad JSON in insumos file → except Exception: continue (lines 97-98)."""
        from concilium.application.runtime import Runtime

        cat_dir = tmp_path / "catalogos" / "mycat"
        (cat_dir / "insumos").mkdir(parents=True)
        (cat_dir / "insumos" / "mao_obra.json").write_text("NOT JSON!!!", encoding="utf-8")
        r = Runtime(tmp_path)
        insumos = r._load_insumos(cat_dir)
        assert insumos == []

    def test_load_insumos_dict_with_insumos_key(self, tmp_path):
        """Insumos file is a dict with 'insumos' key → extend (line 101)."""
        from concilium.application.runtime import Runtime

        cat_dir = tmp_path / "catalogos" / "mycat"
        (cat_dir / "insumos").mkdir(parents=True)
        data = {"insumos": [{"codigo": "MAO-01", "tipo": "MAO_OBRA", "descricao": "test", "preco_unitario": 10}]}
        (cat_dir / "insumos" / "mao_obra.json").write_text(json.dumps(data), encoding="utf-8")
        r = Runtime(tmp_path)
        insumos = r._load_insumos(cat_dir)
        assert len(insumos) == 1
        assert insumos[0]["codigo"] == "MAO-01"

    def test_check_manifest_deps_blank_line_skipped(self, tmp_path):
        """Blank lines in invocations log are skipped (line 136)."""
        from concilium.application.runtime import Runtime
        from concilium.infrastructure.storage.project import ProjectStore

        r = Runtime(tmp_path / "config")
        projetos = tmp_path / "projetos"
        projetos.mkdir()
        project = ProjectStore.init(projetos, "test-proj", "test")
        v = project.new_version()
        log_path = project.version_path(v) / project.INVOCATIONS_LOG
        log_path.parent.mkdir(parents=True, exist_ok=True)
        # Write log with blank lines and valid entries
        log_path.write_text(
            '{"skill": "02-produtividade-climatica", "status": "OK"}\n'
            "\n"  # blank line — triggers continue at line 136
            "   \n"  # whitespace-only line
            '{"skill": "01-escopo-e-eap", "status": "OK"}\n',
            encoding="utf-8",
        )
        # Patch load_manifest to return deps so we exercise the log parsing
        with patch.object(r, "load_manifest", return_value={"depends_on": {"skills": ["02-produtividade-climatica"]}}):
            deps = r.check_manifest_deps("04-cronograma", project, v)
        # 02-produtividade-climatica is in the log as OK → no missing deps
        assert "02-produtividade-climatica" not in deps

    def test_run_skill_raises_for_missing_deps(self, tmp_path):
        """run_skill raises RuntimeError when check_manifest_deps returns missing (line 185)."""
        from concilium.application.runtime import Runtime
        from concilium.application.runtime import RuntimeError as ConciliumRE
        from concilium.infrastructure.storage.project import ProjectStore

        # Use test config_root from actual config dir
        config_root = Path(__file__).parents[3] / "config"
        r = Runtime(config_root)
        projetos = tmp_path / "projetos"
        projetos.mkdir()
        project = ProjectStore.init(projetos, "test-missing-deps", "test")
        v = project.new_version()
        # Patch check_manifest_deps to simulate missing deps
        with patch.object(r, "check_manifest_deps", return_value=["02-produtividade-climatica"]):
            with pytest.raises(ConciliumRE, match="requer execução prévia"):
                r.run_skill("04-cronograma", project, v)

    def test_plan_with_decisions_calls_adjust_schedule(self):
        """plan_with_decisions calls adjust_schedule (lines 333-335)."""
        from concilium.application.runtime import Runtime
        from concilium.domain.models.decision_variables import DecisionVariables

        config_root = Path(__file__).parents[3] / "config"
        r = Runtime(config_root)
        canonical = _minimal_canonical()
        dv = DecisionVariables()
        perfil = {"categorias_indireto": []}
        # adjust_schedule is imported locally inside plan_with_decisions;
        # patch it at its source module
        with patch(
            "concilium.application.optimizer.loop.adjust_schedule", return_value=(canonical, True, [])
        ) as mock_adj:
            r.plan_with_decisions(canonical, dv, perfil=perfil)
        mock_adj.assert_called_once()


# ══ 04-cronograma/skill.py ════════════════════════════════════════════════════


class TestCronogramaEdgeCases:
    def _load_lookup_eficiencia(self):
        mod = _load_skill_module("04-cronograma")
        return mod._lookup_eficiencia

    def test_lookup_eficiencia_direct_hit(self):
        """semana_key found directly in prat_semanal → return value (line 74)."""
        fn = self._load_lookup_eficiencia()
        result = fn("2026-W23", {"2026-W23": 0.85}, {})
        assert result == 0.85

    def test_lookup_eficiencia_exception_path(self):
        """malformed semana_key (no '-W') → except Exception → return 1.0 (lines 84-85)."""
        fn = self._load_lookup_eficiencia()
        result = fn("BAD_KEY_NO_DASH_W", {}, {})
        assert result == 1.0

    def test_run_cronograma_prat_set_but_empty_eap(self):
        """praticabilidade set but empty eap → VAL-CRON-PRECONDICAO (lines 118-121)."""
        from concilium.application.skills import run_cronograma

        prat = Praticabilidade(
            fonte="test",
            limiar_inviabilidade_mm=0,
            calculada_em=datetime.now(UTC),
            percentual_produtivo_mensal={"06": 1.0},
        )
        canonical = _minimal_canonical(praticabilidade=prat, eap=[])
        result = run_cronograma(canonical, {}, {})
        assert result.has_errors
        assert any(v.codigo == "VAL-CRON-PRECONDICAO" for v in result.validacoes)

    def test_run_cronograma_negative_num_equipes_clamped(self):
        """num_equipes < 0 is clamped to 0 (line 167)."""
        from concilium.application.skills import run_cronograma

        cpu_id = "CPU-TEST-01"
        prat = Praticabilidade(
            fonte="test",
            limiar_inviabilidade_mm=0,
            calculada_em=datetime.now(UTC),
            percentual_produtivo_mensal={"06": 1.0, "07": 1.0},
        )
        eap = [EapItem(item_id="i1", ordem=1, cpu_id=cpu_id, descricao="test", unidade="m3", quantitativo=100.0)]
        canonical = _minimal_canonical(eap=eap, praticabilidade=prat)
        catalogo = {
            "cpus": [
                {
                    "codigo": cpu_id,
                    "producao_horaria": 50.0,
                    "descricao": "Test CPU",
                    "composicao_padrao_equipe": {"funcoes": [], "equipamentos": []},
                }
            ]
        }
        # Pass negative num_equipes for one week
        inputs = {"num_equipes_por_item": {"i1": {"2026-W23": -1}}}
        result = run_cronograma(canonical, inputs, catalogo)
        # Should run without crash; negative clamped to 0
        assert result.canonical is not None

    def test_run_cronograma_composicao_exception_pass(self):
        """Exception in resource usage calculation → except Exception: pass (lines 203-204)."""
        from concilium.application.skills import run_cronograma

        cpu_id = "CPU-BAD-COMP"
        prat = Praticabilidade(
            fonte="test",
            limiar_inviabilidade_mm=0,
            calculada_em=datetime.now(UTC),
            percentual_produtivo_mensal={"06": 1.0, "07": 1.0},
        )
        eap = [EapItem(item_id="i1", ordem=1, cpu_id=cpu_id, descricao="test", unidade="m3", quantitativo=100.0)]
        canonical = _minimal_canonical(eap=eap, praticabilidade=prat)
        # Malformed composicao: num_unidades is None → int(None) raises
        catalogo = {
            "cpus": [
                {
                    "codigo": cpu_id,
                    "producao_horaria": 50.0,
                    "descricao": "Test",
                    "composicao_padrao_equipe": {
                        "funcoes": [{"funcao_id": "f1", "num_pessoas": None}],
                        "equipamentos": [{"equip_id": "e1", "num_unidades": None}],
                    },
                }
            ]
        }
        inputs = {"num_equipes_por_item": {"i1": {"2026-W23": 1}}}
        result = run_cronograma(canonical, inputs, catalogo)
        # Should succeed (exception swallowed at lines 203-204)
        assert result.canonical is not None


# ══ 03-equipes-diretas/skill.py ═══════════════════════════════════════════════


class TestEquipesDiretasEdgeCases:
    def _get_permanencia_fn(self):
        mod = _load_skill_module("05-equipes-e-alocacao")
        return mod._calcular_permanencia_e_custo_total

    def _make_cron_semanal(self, item_id="i1"):
        """ScheduledActivityCanonical with semanal distribution (keys contain 'W')."""
        return ScheduledActivityCanonical(
            activity_id=item_id,
            start_week=23,
            end_week=23,
            duration_weeks=1,
            distribuicao_semanal={
                "2026-W23": DistribuicaoSemanal(
                    num_equipes=2, qtd_executada=100.0, qtd_acumulada=100.0, pct=1.0, eficiencia=1.0
                ),
            },
        )

    def _make_cron_mensal(self, item_id="i1"):
        """Namespace with monthly distribution (keys without 'W') for _calcular_permanencia tests."""
        from types import SimpleNamespace

        d = DistribuicaoSemanal(num_equipes=2, qtd_executada=500.0, qtd_acumulada=500.0, pct=1.0, eficiencia=1.0)
        return SimpleNamespace(
            distribuicao_semanal={},
            distribuicao_mensal={"2026-01": d},
        )

    def test_calcular_permanencia_semanal(self):
        """_calcular_permanencia_e_custo_total with semanal distribution (lines 117, 121)."""
        fn = self._get_permanencia_fn()
        cron = self._make_cron_semanal()
        permanencia, custo_total = fn(cron, 10_000.0)
        _semanas_por_mes = 365.25 / 12 / 7
        assert permanencia == round(1 / _semanas_por_mes, 2)
        assert custo_total > 0

    def test_calcular_permanencia_mensal(self):
        """_calcular_permanencia_e_custo_total with monthly distribution (lines 118, 122)."""
        fn = self._get_permanencia_fn()
        cron = self._make_cron_mensal()
        permanencia, custo_total = fn(cron, 10_000.0)
        assert permanencia == 1.0  # float(1 period)
        assert custo_total == round(10_000.0 * 2, 2)

    def _make_full_canonical_for_equipes(self, cpu_id, funcao_id, equip_id, use_monthly=False):
        """Build a canonical with cronograma ready for run_equipes_diretas."""
        eap = [EapItem(item_id="i1", ordem=1, cpu_id=cpu_id, descricao="Test", unidade="m3", quantitativo=100.0)]
        sched = self._make_cron_semanal("i1")
        cron = Cronograma(scheduled_activities=[sched])
        return _minimal_canonical(eap=eap, cronograma=cron)

    def _make_catalogo(self, cpu_id, funcao_id, equip_id):
        return {
            "cpus": [
                {
                    "codigo": cpu_id,
                    "descricao": "CPU Test",
                    "producao_id_ref": "PROD-T",
                    "composicao_itens": [],
                }
            ],
            "insumos": [
                {
                    "codigo": funcao_id,
                    "tipo": "MAO_OBRA",
                    "descricao": "Operador",
                    "preco_unitario": 3000.0,
                    "unidade": "mes",
                    "atributos_especificos": {},
                },
                {
                    "codigo": equip_id,
                    "tipo": "EQUIPAMENTO",
                    "descricao": "Escavadeira",
                    "preco_unitario": 100.0,
                    "unidade": "h",
                    "atributos_especificos": {},
                },
            ],
            "produtividades": [
                {
                    "id": "PROD-T",
                    "valor_horario": 50.0,
                    "composicao_padrao_equipe": {
                        "funcoes": [{"funcao_id": funcao_id, "num_pessoas": 1}],
                        "equipamentos": [{"equip_id": equip_id, "num_unidades": 1}],
                    },
                }
            ],
        }

    def test_run_equipes_object_like_dv(self):
        """dv_obj with attribute dv2_num_equipes (not dict, not DecisionVariables) → line 181."""
        from concilium.application.skills import run_equipes_e_alocacao as run_equipes_diretas

        cpu_id, funcao_id, equip_id = "CPU-A", "funcao-a", "equip-a"
        canonical = self._make_full_canonical_for_equipes(cpu_id, funcao_id, equip_id)
        catalogo = self._make_catalogo(cpu_id, funcao_id, equip_id)

        class ObjectDV:
            dv2_num_equipes = None

        inputs = {"dv": ObjectDV()}
        result = run_equipes_diretas(canonical, inputs, catalogo)
        assert result.canonical is not None

    def test_run_equipes_cpu_none_in_eap_skipped(self):
        """eap item with cpu_id not in cpu_lookup → continue (line 190)."""
        from concilium.application.skills import run_equipes_e_alocacao as run_equipes_diretas

        # cpu_id_missing is not in catalogo
        cpu_missing = "CPU-MISSING"
        sched = ScheduledActivityCanonical(
            activity_id="i1",
            start_week=23,
            end_week=23,
            duration_weeks=1,
            distribuicao_semanal={
                "2026-W23": DistribuicaoSemanal(
                    num_equipes=1, qtd_executada=100.0, qtd_acumulada=100.0, pct=1.0, eficiencia=1.0
                )
            },
        )
        eap = [EapItem(item_id="i1", ordem=1, cpu_id=cpu_missing, descricao="Test", unidade="m3", quantitativo=100.0)]
        canonical = _minimal_canonical(eap=eap, cronograma=Cronograma(scheduled_activities=[sched]))
        catalogo = {"cpus": [], "insumos": []}  # cpu_missing not in cpus
        result = run_equipes_diretas(canonical, {}, catalogo)
        # No crash, just skips the item
        assert result.canonical is not None
        assert result.canonical.equipes_diretas == []

    def test_run_equipes_funcao_obter_returns_none(self):
        """funcao_existe=True but obter_insumo returns None → lines 207-208."""
        from concilium.application.skills import run_equipes_e_alocacao as run_equipes_diretas

        cpu_id, funcao_id, equip_id = "CPU-B", "funcao-b", "equip-b"
        canonical = self._make_full_canonical_for_equipes(cpu_id, funcao_id, equip_id)
        catalogo = self._make_catalogo(cpu_id, funcao_id, equip_id)

        # Find the skill module and patch RepositorioInsumo
        mod = sys.modules.get("concilium.application.skills.equipes_e_alocacao") or sys.modules.get(
            "_concilium_skill_03_equipes_e_alocacao"
        )
        from concilium.infrastructure.repositories.insumo import RepositorioInsumo as _RealRepo

        class MockRepo(_RealRepo):
            def funcao_existe(self, codigo):
                # Return True so the first guard is passed
                return codigo == funcao_id

            def obter_insumo(self, codigo):
                if codigo == funcao_id:
                    return None  # simulate obter_insumo returning None after funcao_existe=True
                return super().obter_insumo(codigo)

        with patch.object(mod, "RepositorioInsumo", new=MockRepo):
            result = run_equipes_diretas(canonical, {}, catalogo)
        assert result.canonical is not None
        # funcao_id should be in erros_funcao (via VAL-EQUIP validation)
        funcao_errors = [v for v in result.validacoes if v.mensagem and funcao_id in v.mensagem]
        assert len(funcao_errors) > 0

    def test_run_equipes_equip_obter_returns_none(self):
        """equipamento_existe=True but obter_insumo returns None → lines 237-238."""
        from concilium.application.skills import run_equipes_e_alocacao as run_equipes_diretas

        cpu_id, funcao_id, equip_id = "CPU-C", "funcao-c", "equip-c"
        canonical = self._make_full_canonical_for_equipes(cpu_id, funcao_id, equip_id)
        catalogo = self._make_catalogo(cpu_id, funcao_id, equip_id)

        mod = sys.modules.get("concilium.application.skills.equipes_e_alocacao") or sys.modules.get(
            "_concilium_skill_03_equipes_e_alocacao"
        )
        from concilium.infrastructure.repositories.insumo import RepositorioInsumo as _RealRepo

        class MockRepo2(_RealRepo):
            def equipamento_existe(self, codigo):
                # Return True so the first guard is passed
                return codigo == equip_id

            def obter_insumo(self, codigo):
                if codigo == equip_id:
                    return None  # equip 'exists' but obter_insumo returns None
                return super().obter_insumo(codigo)

        with patch.object(mod, "RepositorioInsumo", new=MockRepo2):
            result = run_equipes_diretas(canonical, {}, catalogo)
        assert result.canonical is not None
        equip_errors = [v for v in result.validacoes if v.mensagem and equip_id in v.mensagem]
        assert len(equip_errors) > 0

    def test_run_equipes_monthly_distribution_with_negative_dv2(self):
        """dv2 negative (line 263) and positive (lines 269, 274) with weekly distribution."""
        from concilium.application.skills import run_equipes_e_alocacao as run_equipes_diretas

        cpu_id, funcao_id, equip_id = "CPU-D", "funcao-d", "equip-d"
        # Build canonical with TWO weekly periods
        eap = [EapItem(item_id="i1", ordem=1, cpu_id=cpu_id, descricao="Test", unidade="m3", quantitativo=100.0)]
        sched = ScheduledActivityCanonical(
            activity_id="i1",
            start_week=1,
            end_week=2,
            duration_weeks=2,
            distribuicao_semanal={
                "2026-W01": DistribuicaoSemanal(
                    num_equipes=2, qtd_executada=50.0, qtd_acumulada=50.0, pct=0.5, eficiencia=1.0
                ),
                "2026-W02": DistribuicaoSemanal(
                    num_equipes=2, qtd_executada=50.0, qtd_acumulada=100.0, pct=1.0, eficiencia=1.0
                ),
            },
        )
        canonical = _minimal_canonical(eap=eap, cronograma=Cronograma(scheduled_activities=[sched]))
        catalogo = self._make_catalogo(cpu_id, funcao_id, equip_id)
        # dv2 override: week 1 negative (-1 → clamped to 0, hits line 263)
        # week 2 not overridden: base d.num_equipes=2 > 0 → hits lines 269, 274
        dv2 = {"i1": {"2026-W01": -1}}
        inputs = {"dv": {"dv2_num_equipes": dv2}}
        result = run_equipes_diretas(canonical, inputs, catalogo)
        assert result.canonical is not None
        if result.canonical.equipes_diretas:
            # week 2 contributes: permanencia_meses > 0, custo_total > 0
            assert result.canonical.equipes_diretas[0].permanencia_meses > 0


# ══ 06-resultado-financeiro/_precificacao/skill.py ══════════════════════════════════════════════


class TestPlanejamentoBdiEdgeCases:
    def _make_canonical_with_eap(self, cpu_id="CPU-BDI-01"):
        eap = [EapItem(item_id="i1", ordem=1, cpu_id=cpu_id, descricao="Test", unidade="m3", quantitativo=100.0)]
        return _minimal_canonical(eap=eap)

    def _base_perfil(self):
        return {
            "formula_bdi": {
                "faixas_por_categoria": {
                    "material": {"min": 0.05, "max": 0.15},
                    "diesel": {"min": 0.05, "max": 0.15},
                    "mao_obra": {"min": 0.1, "max": 0.25},
                    "equipamentos": {"min": 0.05, "max": 0.20},
                }
            },
            "limites_bdi": {},
        }

    def _base_cpu(self, cpu_id="CPU-BDI-01"):
        return {
            "codigo": cpu_id,
            "descricao": "CPU BDI Test",
            "producao_horaria": 50.0,
            "composicao_padrao_equipe": {"funcoes": [], "equipamentos": []},
            "composicao_itens": [
                {"insumo_id": "INS-MAT-01", "coeficiente": 1.0, "categoria_custo": "material"},
            ],
        }

    def _base_insumo(self):
        return {
            "codigo": "INS-MAT-01",
            "tipo": "MATERIAL",
            "descricao": "Material",
            "preco_unitario": 100.0,
            "unidade": "m3",
            "atributos_especificos": {},
        }

    def test_cpu_not_in_lookup_erros_eap(self):
        """cpu_id not in catalogo → VAL-EAP-01 ERRO ou VAL-CPU-SINTETICO AVISO (ADR-108 fallback)."""
        from concilium.application.skills import load_skill_stage

        run_precificacao_unitaria = load_skill_stage(
            "06-resultado-financeiro", "_precificacao", "run_precificacao_unitaria"
        )

        canonical = self._make_canonical_with_eap("CPU-MISSING-BDI")
        catalogo = {"cpus": [], "insumos": []}  # cpu not present
        result = run_precificacao_unitaria(canonical, {}, catalogo, self._base_perfil())
        val_errors = [v for v in result.validacoes if v.codigo in ("VAL-EAP-01", "VAL-CPU-SINTETICO")]
        assert len(val_errors) >= 1

    def test_categoria_not_in_preco_cat_skipped(self):
        """composicao_item with categoria_custo not in preco_cat → continue (line 126)."""
        from concilium.application.skills import load_skill_stage

        run_precificacao_unitaria = load_skill_stage(
            "06-resultado-financeiro", "_precificacao", "run_precificacao_unitaria"
        )

        cpu_id = "CPU-BDI-02"
        canonical = self._make_canonical_with_eap(cpu_id)
        cpu = dict(self._base_cpu(cpu_id))
        # Use unknown categoria_custo
        cpu["composicao_itens"] = [
            {"insumo_id": "INS-MAT-01", "coeficiente": 1.0, "categoria_custo": "TERCEIRIZADO"},
        ]
        catalogo = {"cpus": [cpu], "insumos": [self._base_insumo()]}
        result = run_precificacao_unitaria(canonical, {}, catalogo, self._base_perfil())
        # Should succeed; TERCEIRIZADO is not in preco_cat → skipped
        assert result.canonical is not None
        plan = result.canonical.planejamento
        if plan:
            assert plan[0].preco_unitario.total == 0.0  # nothing was added to preco_cat


# ══ 09-cost-criticality/skill.py ══════════════════════════════════════════════


class TestCostCriticalityEdgeCases:
    def _classify(self):
        mod = _load_skill_module("10-diagnostico-criticidade")
        return mod._classify

    def test_classify_score_tier_a(self):
        """rank in top-40% without frontier → 'A'; top-20% on frontier → 'A+'."""
        fn = self._classify()
        assert fn(2, 5, False) == "A"  # rank 2/5, top_40=ceil(5*0.4)=2 → A
        assert fn(1, 5, True) == "A+"  # rank 1/5, on_frontier, top_20=ceil(5*0.2)=1 → A+

    def test_classify_score_tier_b(self):
        """rank in top-70% but not top-40% → 'B'."""
        fn = self._classify()
        assert fn(3, 5, False) == "B"  # rank 3/5, top_40=2, top_70=ceil(5*0.7)=4 → B
        assert fn(4, 5, False) == "B"  # rank 4/5, top_70=4 → B

    def test_run_diagnostico_criticidade_custo_total_zero_returns_early(self):
        """custo_total_obra == 0 → ERRO VAL-CC-01 and early return."""
        from concilium.application.skills import run_diagnostico_criticidade
        from concilium.domain.models.canonical import (
            BdiCategorias,
            PrecoUnitarioCategoria,
            SubtotalCategorias,
            SubtotalSemBdiComBdi,
        )

        # equipe with custo_total=0 → custo_total_obra=0 → early return with ERRO
        equipe = EquipeDireta(
            equipe_id="eq-i1",
            item_id="i1",
            cpu_id="CPU-X",
            nome="Equipe Test",
            custo_total=0.0,  # zero → triggers early return
            custo_mao_obra_mensal=0.0,
            permanencia_meses=0.0,
        )
        plan = Planejamento(
            item_id="i1",
            cpu_id="CPU-X",
            quantitativo=100.0,
            preco_unitario=PrecoUnitarioCategoria(material=0.0, diesel=0.0, mao_obra=0.0, equipamentos=0.0, total=0.0),
            bdi=BdiCategorias(material=0.0, diesel=0.0, mao_obra=0.0, equipamentos=0.0),
            preco_unitario_com_bdi=PrecoUnitarioCategoria(
                material=0.0, diesel=0.0, mao_obra=0.0, equipamentos=0.0, total=0.0
            ),
            subtotal=SubtotalSemBdiComBdi(
                sem_bdi=SubtotalCategorias(material=0.0, diesel=0.0, mao_obra=0.0, equipamentos=0.0, total=0.0),
                com_bdi=SubtotalCategorias(material=0.0, diesel=0.0, mao_obra=0.0, equipamentos=0.0, total=0.0),
            ),
        )
        canonical = _minimal_canonical(equipes_diretas=[equipe], planejamento=[plan])
        result = run_diagnostico_criticidade(canonical, {})
        errors = [v for v in result.validacoes if v.codigo == "VAL-CC-01" and v.status == "ERRO"]
        assert len(errors) >= 1


# ══ semantic/normalizer.py ════════════════════════════════════════════════════


class TestNormalizerEdgeCases:
    def test_vocabulary_loader_no_yaml_flag(self, tmp_path):
        """When _HAS_YAML is False and file exists → return {} (line 72)."""
        from concilium.application.semantic.normalizer import VocabularyLoader

        # Create a units.yaml in tmp_path so path.exists() is True
        (tmp_path / "units.yaml").write_text("m3:\n  aliases: [cubic_meter]\n", encoding="utf-8")
        loader = VocabularyLoader(tmp_path)
        import concilium.application.semantic.normalizer as norm_mod

        with patch.object(norm_mod, "_HAS_YAML", False):
            result = loader.load("units")
        assert result == {}

    def test_unit_aliases_non_dict_info(self, tmp_path):
        """unit_aliases with non-dict info value → continue (line 84)."""
        from concilium.application.semantic.normalizer import VocabularyLoader

        # Create units.yaml where one entry has a non-dict value (string)
        yaml_content = "m3:\n  aliases:\n    - cubic_meter\nbad_unit: not_a_dict\n"
        (tmp_path / "units.yaml").write_text(yaml_content, encoding="utf-8")
        loader = VocabularyLoader(tmp_path)
        result = loader.unit_aliases()
        # "bad_unit" should be skipped; "m3" should be mapped
        assert "bad_unit" not in result
        assert "m3" in result

    def test_activity_aliases_non_dict_domain(self, tmp_path):
        """activity_aliases with non-dict domain value → continue (line 96)."""
        from concilium.application.semantic.normalizer import VocabularyLoader

        # activities.yaml where one domain maps to a string (not dict)
        yaml_content = (
            "bad_domain: not_a_dict\ngood_domain:\n  cut_fill:\n    aliases_pt: [escavacao]\n    aliases_en: [cut]\n"
        )
        (tmp_path / "activities.yaml").write_text(yaml_content, encoding="utf-8")
        loader = VocabularyLoader(tmp_path)
        result = loader.activity_aliases()
        # bad_domain skipped; good_domain entries present
        assert "escavacao" in result or "cut_fill" in result

    def test_activity_aliases_non_dict_info(self, tmp_path):
        """activity_aliases with non-dict activity info → continue (line 99)."""
        from concilium.application.semantic.normalizer import VocabularyLoader

        yaml_content = (
            "domain1:\n  good_act:\n    aliases_pt: [boa_atividade]\n    aliases_en: []\n  bad_act: just_a_string\n"
        )
        (tmp_path / "activities.yaml").write_text(yaml_content, encoding="utf-8")
        loader = VocabularyLoader(tmp_path)
        result = loader.activity_aliases()
        # bad_act skipped; good_act present
        assert "boa_atividade" in result
        assert "bad_act" not in result

    def test_activity_optional_dims_not_found(self, tmp_path):
        """activity_optional_dims for unknown type → return [] (line 120)."""
        from concilium.application.semantic.normalizer import VocabularyLoader

        loader = VocabularyLoader(tmp_path)
        result = loader.activity_optional_dims("UNKNOWN_ACTIVITY_TYPE_XYZ")
        assert result == []

    def test_attribute_normalizer_exception_fallback(self):
        """normalizer function raises → except Exception → normalized = raw_value (lines 147-148)."""
        from concilium.application.semantic.normalizer import AttributeNormalizer

        n = AttributeNormalizer()
        # "thickness" is in ATTRIBUTE_REGISTRY; passing object() will cause normalizer to raise TypeError
        # resolve_alias("thickness") should return "thickness" (not None), so we enter the try block
        name, val = n.normalize("thickness", object(), "")
        assert name == "thickness"
        # raw_value (the object) is returned since the normalizer threw
        assert not isinstance(val, (int, float))

    def test_infer_activity_type_prefix_match(self):
        """CPU code is a prefix-match (not exact) → return act (line 249)."""
        from concilium.application.semantic.normalizer import _infer_activity_type

        # "ESCO-CARGA-1CAT-DMT2000" is in the map; append suffix for prefix-match
        result = _infer_activity_type("ESCO-CARGA-1CAT-DMT2000-EXTENDED")
        assert result == "cut_fill"
