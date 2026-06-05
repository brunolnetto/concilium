"""Coverage tests for runtime.py edge cases."""

import json
from unittest.mock import patch
from uuid import UUID

import pytest

from concilium.application.runtime import (
    Runtime,
    RuntimeError,
    _md_to_pdf_bytes,
    _json_default,
    _md_planejamento,
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


def test_run_skill_wraps_erro_tecnico(config_root, projeto_terraplenagem):
    r = Runtime(config_root)
    p = projeto_terraplenagem
    v = p.new_version()
    dummy = {"dummy": lambda **_: (_ for _ in ()).throw(ValueError("boom"))}
    # SKILLS é importado em dois namespaces (runtime.__init__ via get_skill_contract
    # e mixins.execution via run_skill); ambos precisam ser substituídos para que a
    # falha ocorra na execução da skill (e seja envolvida), não no lookup do registry.
    with patch("concilium.application.runtime.SKILLS", dummy), patch(
        "concilium.application.runtime.mixins.execution.SKILLS", dummy
    ):
        with pytest.raises(RuntimeError, match="Falha técnica ao executar skill"):
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
