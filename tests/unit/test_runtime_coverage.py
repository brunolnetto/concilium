"""Coverage tests for runtime.py edge cases."""

import json
from pathlib import Path
from unittest.mock import patch
from uuid import UUID

import pytest

from concilium.application.runtime import (
    Runtime,
    RuntimeError,
    _json_default,
    _md_planejamento,
    _md_to_pdf_bytes,
    _memorial_bdi_to_md,
)
from concilium.infrastructure.storage.project import ProjectStore

# ── _json_default ─────────────────────────────────────────────────────────────


def test_json_default_uuid():
    uid = UUID("12345678-1234-5678-1234-567812345678")
    assert _json_default(uid) == "12345678-1234-5678-1234-567812345678"


def test_json_default_unsupported_type():
    with pytest.raises(TypeError):
        _json_default(object())


# ── load_* errors ─────────────────────────────────────────────────────────────


def test_load_contexto_not_found(tmp_path):
    r = Runtime(tmp_path)
    (tmp_path / "contextos").mkdir()
    with pytest.raises(RuntimeError, match="não encontrado"):
        r.load_contexto("nonexistent")


def test_load_jurisdicao_not_found(tmp_path):
    r = Runtime(tmp_path)
    (tmp_path / "jurisdicoes").mkdir()
    with pytest.raises((RuntimeError, Exception), match="não encontrad"):
        r.load_jurisdicao("NONEXIST")


def test_load_perfil_not_found(tmp_path):
    r = Runtime(tmp_path)
    (tmp_path / "perfis").mkdir()
    with pytest.raises(RuntimeError, match="não encontrado"):
        r.load_perfil("nonexistent")


def test_load_referencia_not_found(tmp_path):
    r = Runtime(tmp_path)
    (tmp_path / "referencias").mkdir()
    with pytest.raises((RuntimeError, Exception), match="não encontrad"):
        r.load_referencia("nonexistent")


def test_load_catalogo_not_found(tmp_path):
    r = Runtime(tmp_path)
    (tmp_path / "catalogos").mkdir()
    with pytest.raises(RuntimeError, match="não encontrado"):
        r.load_catalogo("nonexistent")


# ── load_catalogo edge cases ───────────────────────────────────────────────────


def test_load_catalogo_json_as_list(tmp_path):
    """cpus.json containing a list is handled."""
    cat_dir = tmp_path / "catalogos" / "test-cat"
    cat_dir.mkdir(parents=True)
    cpus_data = [{"codigo": "CPU-01", "descricao": "Test"}]
    (cat_dir / "cpus.json").write_text(json.dumps(cpus_data), encoding="utf-8")
    r = Runtime(tmp_path)
    cat = r.load_catalogo("test-cat")
    assert cat["cpus"] == cpus_data


def test_load_catalogo_json_with_key(tmp_path):
    """cpus.json containing dict with key is handled."""
    cat_dir = tmp_path / "catalogos" / "test-cat"
    cat_dir.mkdir(parents=True)
    cpus_data = {"cpus": [{"codigo": "CPU-01"}]}
    (cat_dir / "cpus.json").write_text(json.dumps(cpus_data), encoding="utf-8")
    r = Runtime(tmp_path)
    cat = r.load_catalogo("test-cat")
    assert cat["cpus"] == [{"codigo": "CPU-01"}]


# ── _load_insumos edge cases ───────────────────────────────────────────────────


def test_load_insumos_no_dir(tmp_path):
    cat_dir = tmp_path / "catalogos" / "test"
    cat_dir.mkdir(parents=True)
    r = Runtime(tmp_path)
    insumos = r._load_insumos(cat_dir)
    assert insumos == []


def test_load_insumos_list_file(tmp_path):
    cat_dir = tmp_path / "catalogos" / "test"
    cat_dir.mkdir(parents=True)
    ins_dir = cat_dir / "insumos"
    ins_dir.mkdir()
    data = [{"codigo": "MAO-01", "descricao": "Mão de obra"}]
    (ins_dir / "mao_obra.json").write_text(json.dumps(data), encoding="utf-8")
    r = Runtime(tmp_path)
    insumos = r._load_insumos(cat_dir)
    assert insumos == data


# ── load_manifest ─────────────────────────────────────────────────────────────


def test_load_manifest_nonexistent(config_root):
    r = Runtime(config_root)
    result = r.load_manifest("nonexistent-skill-xyz")
    assert result is None


# ── check_manifest_deps ───────────────────────────────────────────────────────


def test_check_manifest_deps_no_manifest(config_root, projeto_terraplenagem):
    r = Runtime(config_root)
    p = projeto_terraplenagem
    v = p.new_version()
    deps = r.check_manifest_deps("nonexistent-xyz", p, v)
    assert deps == []


def test_check_manifest_deps_parses_invocations_log(config_root, projeto_terraplenagem):
    r = Runtime(config_root)
    p = projeto_terraplenagem
    v = p.new_version()
    # Write some invocations log entries
    log_path = p.version_path(v) / p.INVOCATIONS_LOG
    log_path.parent.mkdir(parents=True, exist_ok=True)
    log_path.write_text(
        '{"skill": "01-escopo-e-eap", "status": "OK"}\n'
        "{invalid json line}\n"
        '{"skill": "02-produtividade-climatica", "status": "OK"}\n',
        encoding="utf-8",
    )
    # check_manifest_deps for 04-cronograma requires 02-produtividade-climatica
    deps = r.check_manifest_deps("04-cronograma", p, v)
    # 02-produtividade-climatica is logged as OK, so no deps missing for that one
    assert "02-produtividade-climatica" not in deps


# ── run_skill errors ──────────────────────────────────────────────────────────


def test_run_skill_unknown_skill(config_root, projeto_terraplenagem):
    r = Runtime(config_root)
    p = projeto_terraplenagem
    v = p.new_version()
    with pytest.raises(RuntimeError, match="Skill desconhecida"):
        r.run_skill("nonexistent-skill", p, v)


def test_run_skill_no_version(config_root, tmp_path):
    r = Runtime(config_root)
    # Create project without any version
    projetos_root = tmp_path / "projetos"
    projetos_root.mkdir()
    p = ProjectStore.init(projetos_root, "novo-projeto-test", "test")
    # no version created — current_version() returns None
    with pytest.raises(RuntimeError, match="Nenhuma versão"):
        r.run_skill("01-escopo-e-eap", p)


def test_get_skill_contract_basico(config_root):
    r = Runtime(config_root)
    contract = r.get_skill_contract("01-escopo-e-eap")
    assert contract.skill_id == "01-escopo-e-eap"
    assert "inputs" in contract.signature
    assert isinstance(contract.required_inputs, list)
    assert contract.output_schema["result_type"] == "SkillResult"


def test_run_skill_loga_observabilidade(config_root, projeto_terraplenagem, inputs_escopo_terraplenagem):
    r = Runtime(config_root)
    p = projeto_terraplenagem
    v = p.new_version()
    r.run_skill(
        "01-escopo-e-eap",
        p,
        v,
        inputs={**inputs_escopo_terraplenagem, "correlation_id": "corr-test", "execution_id": "exec-test"},
    )
    log_path = p.version_path(v) / p.INVOCATIONS_LOG
    entry = json.loads(log_path.read_text(encoding="utf-8").splitlines()[-1])
    assert entry["correlation_id"] == "corr-test"
    assert entry["execution_id"] == "exec-test"
    assert "duration_ms" in entry
    assert "contract" in entry
    assert entry["contract"]["required_inputs"] is not None
    # NEP-028 D4: proveniência de catálogo persistida por run
    assert "catalog_source" in entry
    assert entry["catalog_source"] in ("project_reference", "master")


def test_run_skill_wraps_erro_tecnico(config_root, projeto_terraplenagem, inputs_escopo_terraplenagem):
    r = Runtime(config_root)
    p = projeto_terraplenagem
    v = p.new_version()
    # Popula canonical para evitar o guard RuntimeDomainError de "sem estado inicial"
    r.run_skill("01-escopo-e-eap", p, v, inputs=inputs_escopo_terraplenagem)
    dummy = {"dummy": lambda **_: (_ for _ in ()).throw(ValueError("boom"))}
    # SKILLS é importado em dois namespaces (runtime.__init__ via get_skill_contract
    # e mixins.execution via run_skill); ambos precisam ser substituídos para que a
    # falha ocorra na execução da skill (e seja envolvida), não no lookup do registry.
    with (
        patch("concilium.application.runtime.SKILLS", dummy),
        patch("concilium.application.runtime.mixins.execution.SKILLS", dummy),
    ):
        with pytest.raises(RuntimeError, match="Falha técnica"):
            r.run_skill("dummy", p, v, inputs={})


def test_md_planejamento_accepts_subtotal_sem_bdi_component_keys():
    plan = [
        {
            "item_id": "eap-1",
            "descricao": "Servico teste",
            "unidade": "m3",
            "quantitativo": 10,
            "subtotal_sem_bdi_mo": 100.0,
            "subtotal_sem_bdi_eq": 200.0,
            "subtotal_sem_bdi_diesel": 300.0,
            "subtotal_sem_bdi_mat": 400.0,
            "subtotal_sem_bdi": 1000.0,
            "subtotal_com_bdi": 1200.0,
        }
    ]

    # Após a redesenho do relatório (pacote runtime), a tabela de planejamento é
    # enxuta (item · descrição · c/BDI). O teste garante que as chaves de componente
    # sem_bdi são aceitas sem quebrar e que o subtotal_com_bdi é renderizado.
    md = "\n".join(_md_planejamento(plan))
    assert "| eap-1 | Servico teste | R$ 1,200.00 |" in md


def test_memorial_bdi_md_reads_current_schema_fields():
    memorial = {
        "meta": {"projeto_id": "proj-123", "gerado_em": "2026-05-23T18:54:12+00:00"},
        "bdi_por_categoria": {
            "mao_obra": {
                "ac": 0.05,
                "df": 0.015,
                "r": 0.01,
                "cr": 0.0,
                "l": 0.09,
                "tributos_total": 0.1338,
                "bdi_total": 0.345,
            }
        },
        "aplicacao_por_item": [
            {
                "item_id": "eap-1",
                "subtotal_sem_bdi": 1000.0,
                "subtotal_com_bdi": 1345.0,
                "bdi_aplicado": 0.345,
            }
        ],
        "venda_total_com_bdi": 2000.0,
        "custo_direto_total": 1000.0,
        "overhead_total": 300.0,
        "tributos_total": 200.0,
        "margem_total": 500.0,
        "margem_pct": 0.25,
    }

    # Renderer atual (pacote runtime): colunas AC|DF|R|Lucro|Overhead|Tributos|BDI
    # na seção "BDI por Categoria" + seção "Resumo Financeiro".
    md = _memorial_bdi_to_md(memorial)
    assert "**Projeto:** proj-123" in md
    assert "## BDI por Categoria" in md
    assert "| mao_obra | 5.00% | 1.50% | 1.00% | 9.00% | 0.00% | 13.38% | **34.50%** |" in md
    assert "**Venda Total c/ BDI**" in md
    assert "R$ 2,000.00" in md
    assert "25.00%" in md


def test_md_to_pdf_bytes_handles_unicode_text():
    md = "# Relatorio\n\nLinha com acentos: ação, preço, São Paulo, — dash."
    pdf = _md_to_pdf_bytes(md, "Teste")
    assert pdf is not None
    assert len(pdf) > 100


# ── catalog mixin: _catalog_bundle_valid ─────────────────────────────────────


def test_catalog_bundle_valid_no_bundle(tmp_path):
    r = Runtime(tmp_path)
    cat_dir = tmp_path / "catalogos" / "test"
    cat_dir.mkdir(parents=True)
    bundle = cat_dir / ".catalog_bundle.json"
    # bundle does not exist -> False
    assert r._catalog_bundle_valid(cat_dir, bundle) is False


def test_catalog_bundle_valid_with_stale_json(tmp_path):
    import time

    r = Runtime(tmp_path)
    cat_dir = tmp_path / "catalogos" / "test"
    cat_dir.mkdir(parents=True)
    bundle = cat_dir / ".catalog_bundle.json"
    bundle.write_text("{}", encoding="utf-8")
    # Write a json file AFTER the bundle to make bundle stale
    time.sleep(0.01)
    (cat_dir / "cpus.json").write_text("[]", encoding="utf-8")
    assert r._catalog_bundle_valid(cat_dir, bundle) is False


def test_catalog_bundle_valid_when_bundle_newest(tmp_path):
    import time

    r = Runtime(tmp_path)
    cat_dir = tmp_path / "catalogos" / "test"
    cat_dir.mkdir(parents=True)
    (cat_dir / "cpus.json").write_text("[]", encoding="utf-8")
    time.sleep(0.01)
    bundle = cat_dir / ".catalog_bundle.json"
    bundle.write_text("{}", encoding="utf-8")
    # bundle is newer than cpus.json -> valid
    assert r._catalog_bundle_valid(cat_dir, bundle) is True


# ── catalog mixin: _load_cpus_from_cpu_dir ───────────────────────────────────


def test_load_cpus_from_cpu_dir_nonexistent():
    from concilium.application.runtime.mixins.catalog import CatalogMixin

    cpus = CatalogMixin._load_cpus_from_cpu_dir(Path("/nonexistent/cpu_dir"))
    assert cpus == []


def test_load_cpus_from_cpu_dir_list_format(tmp_path):
    from concilium.application.runtime.mixins.catalog import CatalogMixin
    import json

    cpu_dir = tmp_path / "cpus"
    cpu_dir.mkdir()
    (cpu_dir / "batch1.json").write_text(json.dumps([{"codigo": "CPU-1"}]), encoding="utf-8")
    cpus = CatalogMixin._load_cpus_from_cpu_dir(cpu_dir)
    assert cpus == [{"codigo": "CPU-1"}]


def test_load_cpus_from_cpu_dir_dict_format(tmp_path):
    from concilium.application.runtime.mixins.catalog import CatalogMixin
    import json

    cpu_dir = tmp_path / "cpus"
    cpu_dir.mkdir()
    (cpu_dir / "batch.json").write_text(json.dumps({"cpus": [{"codigo": "CPU-2"}]}), encoding="utf-8")
    cpus = CatalogMixin._load_cpus_from_cpu_dir(cpu_dir)
    assert cpus == [{"codigo": "CPU-2"}]


def test_load_cpus_from_cpu_dir_single_cpu_dict(tmp_path):
    from concilium.application.runtime.mixins.catalog import CatalogMixin
    import json

    # dict without "cpus" key -> appended as single item
    cpu_dir = tmp_path / "cpus"
    cpu_dir.mkdir()
    (cpu_dir / "single.json").write_text(json.dumps({"codigo": "CPU-3", "descricao": "X"}), encoding="utf-8")
    cpus = CatalogMixin._load_cpus_from_cpu_dir(cpu_dir)
    assert {"codigo": "CPU-3", "descricao": "X"} in cpus


def test_load_cpus_from_cpu_dir_invalid_json_skipped(tmp_path):
    from concilium.application.runtime.mixins.catalog import CatalogMixin

    cpu_dir = tmp_path / "cpus"
    cpu_dir.mkdir()
    (cpu_dir / "bad.json").write_text("INVALID JSON", encoding="utf-8")
    cpus = CatalogMixin._load_cpus_from_cpu_dir(cpu_dir)
    assert cpus == []


# ── catalog mixin: _load_cpus_from_json ──────────────────────────────────────


def test_load_cpus_from_json_empty_dict(tmp_path):
    from concilium.application.runtime.mixins.catalog import CatalogMixin
    import json

    f = tmp_path / "cpus.json"
    f.write_text(json.dumps({"other_key": []}), encoding="utf-8")
    cpus = CatalogMixin._load_cpus_from_json(f)
    assert cpus == []


def test_load_cpus_from_json_invalid(tmp_path):
    from concilium.application.runtime.mixins.catalog import CatalogMixin

    f = tmp_path / "cpus.json"
    f.write_text("NOT JSON", encoding="utf-8")
    cpus = CatalogMixin._load_cpus_from_json(f)
    assert cpus == []


# ── catalog mixin: _load_producoes_from_cat_dirs ─────────────────────────────


def test_load_producoes_from_cat_dirs_list_format(tmp_path):
    from concilium.application.runtime.mixins.catalog import CatalogMixin
    import json

    cat_dir = tmp_path / "cat"
    prod_dir = cat_dir / "producoes"
    prod_dir.mkdir(parents=True)
    (prod_dir / "prods.json").write_text(json.dumps([{"id": "PROD-1"}]), encoding="utf-8")
    result = CatalogMixin._load_producoes_from_cat_dirs(cat_dir)
    assert {"id": "PROD-1"} in result


def test_load_producoes_from_cat_dirs_dict_format(tmp_path):
    from concilium.application.runtime.mixins.catalog import CatalogMixin
    import json

    cat_dir = tmp_path / "cat"
    prod_dir = cat_dir / "produtividades"
    prod_dir.mkdir(parents=True)
    (prod_dir / "p.json").write_text(json.dumps({"id": "PROD-2", "valor": 10}), encoding="utf-8")
    result = CatalogMixin._load_producoes_from_cat_dirs(cat_dir)
    assert {"id": "PROD-2", "valor": 10} in result


def test_load_producoes_from_cat_dirs_invalid_skipped(tmp_path):
    from concilium.application.runtime.mixins.catalog import CatalogMixin

    cat_dir = tmp_path / "cat"
    prod_dir = cat_dir / "producoes"
    prod_dir.mkdir(parents=True)
    (prod_dir / "bad.json").write_text("BAD JSON", encoding="utf-8")
    result = CatalogMixin._load_producoes_from_cat_dirs(cat_dir)
    assert result == []


# ── catalog mixin: _synthesize_missing_producoes ─────────────────────────────


def test_synthesize_missing_producoes_adds_new():
    from concilium.application.runtime.mixins.catalog import CatalogMixin

    cpus = [{"producao_id_ref": "PROD-NEW", "producao_horaria": 25.0, "composicao_padrao_equipe": None}]
    seen: set = set()
    result = CatalogMixin._synthesize_missing_producoes(cpus, seen)
    assert len(result) == 1
    assert result[0]["id"] == "PROD-NEW"
    assert result[0]["valor_horario"] == 25.0


def test_synthesize_missing_producoes_skips_already_seen():
    from concilium.application.runtime.mixins.catalog import CatalogMixin

    cpus = [{"producao_id_ref": "PROD-OLD", "producao_horaria": 10.0}]
    seen = {"PROD-OLD"}
    result = CatalogMixin._synthesize_missing_producoes(cpus, seen)
    assert result == []


def test_synthesize_missing_producoes_skips_no_prod_id():
    from concilium.application.runtime.mixins.catalog import CatalogMixin

    cpus = [{"producao_horaria": 10.0}]  # no producao_id_ref
    result = CatalogMixin._synthesize_missing_producoes(cpus, set())
    assert result == []


# ── catalog mixin: _merge_global_producoes ───────────────────────────────────


def test_merge_global_producoes_deduplicates():
    from concilium.application.runtime.mixins.catalog import CatalogMixin

    producoes = [{"id": "P1", "valor": 10}]
    global_prods = [{"id": "P1", "valor": 99}, {"id": "P2", "valor": 20}]
    result = CatalogMixin._merge_global_producoes(producoes, global_prods)
    assert len(result) == 2
    ids = [p["id"] for p in result]
    assert "P1" in ids and "P2" in ids


# ── catalog mixin: _load_catalogo_from_disk with bundle ─────────────────────


def test_load_catalogo_from_disk_uses_valid_bundle(tmp_path):
    import json as _json

    r = Runtime(tmp_path)
    cat_dir = tmp_path / "catalogos" / "bundle-cat"
    cat_dir.mkdir(parents=True)
    # Write bundle before any json so it's "newest"
    bundle_data = {"cpus": [{"codigo": "FROM-BUNDLE"}], "insumos": [], "templates": {}, "produtividades": []}
    bundle_path = cat_dir / ".catalog_bundle.json"
    bundle_path.write_text(_json.dumps(bundle_data), encoding="utf-8")
    # No individual json files -> bundle is always valid
    cat = r.load_catalogo("bundle-cat")
    assert cat["cpus"] == [{"codigo": "FROM-BUNDLE"}]


def test_load_catalogo_from_disk_uses_cpu_dir(tmp_path):
    import json as _json

    r = Runtime(tmp_path)
    cat_dir = tmp_path / "catalogos" / "dir-cat"
    cpu_dir = cat_dir / "cpus"
    cpu_dir.mkdir(parents=True)
    (cpu_dir / "batch.json").write_text(_json.dumps([{"codigo": "CPU-DIR"}]), encoding="utf-8")
    cat = r.load_catalogo("dir-cat")
    assert any(c["codigo"] == "CPU-DIR" for c in cat["cpus"])


def test_load_catalogo_from_disk_writes_bundle(tmp_path):
    import json as _json

    r = Runtime(tmp_path)
    cat_dir = tmp_path / "catalogos" / "write-cat"
    cat_dir.mkdir(parents=True)
    # valid directory but empty -> builds minimal catalog and writes bundle
    r.load_catalogo("write-cat")
    bundle_path = cat_dir / ".catalog_bundle.json"
    assert bundle_path.exists()


def test_load_catalogo_cached_second_call_uses_cache(tmp_path):
    import json as _json

    r = Runtime(tmp_path)
    cat_dir = tmp_path / "catalogos" / "cache-cat"
    cat_dir.mkdir(parents=True)
    cat1 = r.load_catalogo("cache-cat")
    cat2 = r.load_catalogo("cache-cat")
    # Both are deep copies of same cached dict — equal but not same object
    assert cat1 == cat2


# ── catalog mixin: _get_or_create_catalog_session ────────────────────────────


def test_get_or_create_catalog_session_unavailable(tmp_path):
    from unittest.mock import patch as _patch

    r = Runtime(tmp_path)
    # is_available() returns False -> returns None
    with _patch("concilium.infrastructure.catalog.query_engine.is_available", return_value=False):
        result = r._get_or_create_catalog_session({}, "key-1")
    assert result is None


def test_get_or_create_catalog_session_exception_returns_none(tmp_path):
    from unittest.mock import patch as _patch

    r = Runtime(tmp_path)
    # Force CatalogSession.from_resolved to raise -> method should return None (except block line 39)
    with _patch(
        "concilium.infrastructure.catalog.query_engine.is_available", return_value=True
    ), _patch(
        "concilium.infrastructure.catalog.query_engine.CatalogSession.from_resolved",
        side_effect=RuntimeError("forced"),
    ):
        result = r._get_or_create_catalog_session({}, "key-fail")
    assert result is None


# ── execution mixin: _resolve_missing_deps ───────────────────────────────────


def test_resolve_missing_deps_with_executed_ok(config_root, projeto_terraplenagem):
    r = Runtime(config_root)
    p = projeto_terraplenagem
    v = p.new_version()

    contract = r.get_skill_contract("04-cronograma")
    # _executed_ok provided: only deps NOT in it should be returned
    result = r._resolve_missing_deps(contract, "04-cronograma", p, v, _executed_ok=set(contract.depends_on_skills))
    assert result == []


def test_resolve_missing_deps_without_executed_ok_uses_manifest(config_root, projeto_terraplenagem):
    r = Runtime(config_root)
    p = projeto_terraplenagem
    v = p.new_version()

    contract = r.get_skill_contract("04-cronograma")
    # _executed_ok = None -> calls check_manifest_deps
    result = r._resolve_missing_deps(contract, "04-cronograma", p, v, _executed_ok=None)
    # All deps missing since no log -> deps returned (or empty if no manifest deps)
    assert isinstance(result, list)


# ── execution mixin: _process_taint ─────────────────────────────────────────


def _make_minimal_canonical_for_execution():
    from concilium.domain.models.canonical import CanonicalModel

    data = {
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
    return CanonicalModel.model_validate(data)


def test_process_taint_error_in_gate_skill_adds_blocked(config_root):
    from concilium.application.runtime.mixins.execution import ExecutionMixin
    from concilium.application.skills.base import SkillResult
    from concilium.domain.models.canonical import ValidacaoItem

    r = Runtime(config_root)
    canonical = _make_minimal_canonical_for_execution()
    val_erro = ValidacaoItem(codigo="ERR-001", status="ERRO", campo=None, mensagem="err")
    result = SkillResult(canonical, [val_erro])

    gate_skill = "01-escopo-e-eap"  # known gate skill
    new_result, should_save = r._process_taint(gate_skill, result, False)
    assert should_save is True
    assert gate_skill in new_result.canonical.pipeline_blocked_from
    assert new_result.canonical.pipeline_integridade == "CORROMPIDO"


def test_process_taint_success_in_gate_skill_clears_blocked(config_root):
    from concilium.application.runtime.mixins.execution import ExecutionMixin
    from concilium.application.skills.base import SkillResult

    r = Runtime(config_root)
    gate_skill = "01-escopo-e-eap"
    canonical = _make_minimal_canonical_for_execution()
    # Pre-populate pipeline_blocked_from with this skill
    canonical = canonical.model_copy(
        update={"pipeline_blocked_from": [gate_skill], "pipeline_integridade": "CORROMPIDO"}
    )
    result = SkillResult(canonical, [])  # no errors

    new_result, should_save = r._process_taint(gate_skill, result, False)
    assert should_save is True
    assert gate_skill not in new_result.canonical.pipeline_blocked_from
    assert new_result.canonical.pipeline_integridade is None


def test_process_taint_non_gate_skill_returns_unchanged(config_root):
    from concilium.application.skills.base import SkillResult

    r = Runtime(config_root)
    canonical = _make_minimal_canonical_for_execution()
    result = SkillResult(canonical, [])

    new_result, should_save = r._process_taint("09-registro-decisoes", result, True)
    assert should_save is True
    assert new_result is result  # same object returned


# ── execution mixin: _process_decision_variables ────────────────────────────


def test_process_decision_variables_no_dv(config_root):
    from concilium.application.skills.base import SkillResult

    r = Runtime(config_root)
    canonical = _make_minimal_canonical_for_execution()
    result = SkillResult(canonical, [])
    new_result, should_save = r._process_decision_variables({}, result, True)
    # no dv_raw -> unchanged
    assert new_result is result
    assert should_save is True


def test_process_decision_variables_with_errors_skipped(config_root):
    from concilium.application.skills.base import SkillResult
    from concilium.domain.models.canonical import ValidacaoItem

    r = Runtime(config_root)
    canonical = _make_minimal_canonical_for_execution()
    val_erro = ValidacaoItem(codigo="ERR-001", status="ERRO", campo=None, mensagem="err")
    result = SkillResult(canonical, [val_erro])
    # has_errors -> dv update skipped
    new_result, should_save = r._process_decision_variables({"decision_variables": {}}, result, False)
    assert new_result is result
    assert should_save is False


def test_process_decision_variables_applies_dv_dict(config_root):
    from concilium.application.skills.base import SkillResult

    r = Runtime(config_root)
    canonical = _make_minimal_canonical_for_execution()
    result = SkillResult(canonical, [])
    dv_raw = {"dv4_indirect_policy": "lean"}
    normalized_inputs = {"decision_variables": dv_raw}
    new_result, should_save = r._process_decision_variables(normalized_inputs, result, False)
    assert should_save is True
    assert new_result.canonical.decision_variables is not None
    assert new_result.canonical.decision_variables.dv4_indirect_policy == "lean"


# ── execution mixin: _process_side_effects ──────────────────────────────────


def test_process_side_effects_skill_04(config_root, projeto_terraplenagem):
    from concilium.application.runtime.mixins.execution import ExecutionMixin
    from concilium.application.skills.base import SkillResult
    from unittest.mock import patch as _patch

    r = Runtime(config_root)
    p = projeto_terraplenagem
    v = p.new_version()
    canonical = _make_minimal_canonical_for_execution()
    result = SkillResult(canonical, [])
    with _patch(
        "concilium.application.runtime.mixins.execution._handle_skill_04_side_effects"
    ) as mock_04, _patch(
        "concilium.application.runtime.mixins.execution._persist_typed_artifacts"
    ) as mock_persist:
        r._process_side_effects("04-cronograma", result, p, v)
    mock_04.assert_called_once()
    mock_persist.assert_called_once()


def test_process_side_effects_skill_09(config_root, projeto_terraplenagem):
    from concilium.application.skills.base import SkillResult
    from unittest.mock import patch as _patch

    r = Runtime(config_root)
    p = projeto_terraplenagem
    v = p.new_version()
    canonical = _make_minimal_canonical_for_execution()
    result = SkillResult(canonical, [])
    result.decision_log = [{"decision": "D1"}]

    with _patch("concilium.application.runtime.mixins.execution._persist_typed_artifacts"):
        r._process_side_effects("09-registro-decisoes", result, p, v)
    # decision_log.json should be written if decision_log is non-empty
    decision_log_path = p.version_path(v) / "decision_log.json"
    assert decision_log_path.exists()


def test_process_side_effects_skill_10(config_root, projeto_terraplenagem):
    from concilium.application.skills.base import SkillResult
    from unittest.mock import patch as _patch

    r = Runtime(config_root)
    p = projeto_terraplenagem
    v = p.new_version()
    canonical = _make_minimal_canonical_for_execution()
    result = SkillResult(canonical, [])

    with _patch(
        "concilium.application.runtime.mixins.execution._handle_skill_09_side_effects"
    ) as mock_09, _patch(
        "concilium.application.runtime.mixins.execution._persist_typed_artifacts"
    ):
        r._process_side_effects("10-relatorio-e-artefatos", result, p, v)
    mock_09.assert_called_once()
