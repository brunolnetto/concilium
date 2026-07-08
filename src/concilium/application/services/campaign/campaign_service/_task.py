"""ADR-070 — Campaign service (parte extraída de campaign_service.py)."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

from concilium.domain.models.campaign.campaign import (
    CenarioAvaliado,
    PerfilExpectativas,
    VetorEspacoEF,
    VetorEspacoO,
    ViabilidadeStatus,
)

from ._classificacao import classificar_EF, classificar_O
from ._grid import _apply_post_load_overrides, cenario_id
from ._vetores import extrair_vetor_EF, extrair_vetor_O


@dataclass
class _CampaignTask:
    """Contexto completo para um cenário — picklável para multiprocessing."""

    spec_v: dict
    variados: dict
    config_root: str
    projects_root: str
    prazo_contratual: int | None
    perfil: PerfilExpectativas
    procurement_intent: str
    do_reset: bool


def _prepare_scenario_spec(task: _CampaignTask, cid: str) -> tuple[dict, str]:
    """Monta o spec com slug/id/meta únicos para o cenário. Retorna (spec_with_id, scenario_slug)."""
    spec_with_id = dict(task.spec_v)
    base_slug = spec_with_id.get("slug") or spec_with_id.get("id") or "UNKNOWN"
    scenario_slug = f"{base_slug}-{cid[:6]}"
    # Definir TANTO "slug" QUANTO "id" — spec_loader usa ref.get("id") para o slug do projeto.
    # Sem "id", _infer_slug_from_path leria o nome do tmpdir e criaria um projeto com
    # esse nome em projetos/ (ex: campaign_AGIS-054483_ajeczz9t), impossibilitando a limpeza.
    spec_with_id["slug"] = scenario_slug
    spec_with_id["id"] = scenario_slug
    meta = dict(spec_with_id.get("meta") or {})
    base_nome = meta.get("projeto", base_slug)
    meta["projeto"] = f"{base_nome} [{cid[:6]}]"
    spec_with_id["meta"] = meta
    return spec_with_id, scenario_slug


def _load_canonical_do_cenario(scenario_projects_root: Path, actual_project_slug: str) -> dict:
    canonical: dict = {}
    for _try in (actual_project_slug, actual_project_slug.upper(), actual_project_slug.lower()):
        _can = scenario_projects_root / _try / "v1" / "canonical.json"
        if _can.exists():
            canonical = json.loads(_can.read_text())
            break
    return canonical


def _map_viabilidade_decision(decision: str) -> ViabilidadeStatus:
    via_map: dict[str, ViabilidadeStatus] = {
        "APROVADO": "APROVADO",
        "APROVADO_COM_RESSALVAS": "APROVADO_COM_RESSALVAS",
        "BLOQUEADO_COM_INVESTIGACAO": "BLOQUEADO_COM_INVESTIGACAO",
        "BLOQUEADO": "BLOQUEADO",
    }
    return via_map.get(decision, "ERRO")


def _cleanup_scenario_projects(
    scenario_projects_root: Path,
    scenario_slug: str,
    actual_project_slug: str | None,
) -> None:
    import shutil

    # Limpar projeto de cenário em projetos/ usando o slug REAL (não o esperado).
    # O spec_loader pode ter derivado um slug diferente do scenario_slug se "id"
    # não estava definido — agora está, mas o finally usa actual_project_slug
    # como defesa contra futuras inconsistências.
    slugs_to_clean = {scenario_slug, actual_project_slug} if actual_project_slug else {scenario_slug}
    for _slug_clean in slugs_to_clean:
        for _try in (_slug_clean, _slug_clean.upper(), _slug_clean.lower()):
            _proj = scenario_projects_root / _try
            if _proj.exists():
                shutil.rmtree(_proj, ignore_errors=True)


def _run_campaign_task(task: _CampaignTask) -> CenarioAvaliado:
    """Avalia um cenário da campanha — module-level para ser picklável."""
    from concilium.application.benchmarks.execution.runner import BenchmarkRunner
    from concilium.application.benchmarks.report.report_builder import BenchmarkReportBuilder
    from concilium.application.benchmarks.report.report_printer import BenchmarkReportPrinter
    from concilium.application.benchmarks.spec.spec_loader import load_spec_from_dict

    class _Silent(BenchmarkReportPrinter):
        def print(self, report: dict) -> None:  # noqa: A003
            pass

    import tempfile

    cid = cenario_id(task.variados)
    spec_with_id, scenario_slug = _prepare_scenario_spec(task, cid)

    scenario_projects_root = Path(task.projects_root)
    actual_project_slug: str | None = None  # rastreado para cleanup preciso

    with tempfile.TemporaryDirectory() as tmp_dir:
        ref_path = Path(tmp_dir) / "referencia.json"
        ref_path.write_text(json.dumps(spec_with_id, ensure_ascii=False, default=str))

        try:
            spec_obj = load_spec_from_dict(spec_with_id, ref_path)
            actual_project_slug = spec_obj.slug  # slug real após normalização do spec_loader
            _apply_post_load_overrides(spec_obj, task.variados)
            runner = BenchmarkRunner(
                config_root=Path(task.config_root),
                projects_root=scenario_projects_root,
                report_builder=BenchmarkReportBuilder(),
                report_printer=_Silent(),
            )
            report = runner.run(
                spec_obj,
                reset=task.do_reset,
                skip_artifacts=True,
                procurement_intent=task.procurement_intent,
            )
            canonical = _load_canonical_do_cenario(scenario_projects_root, actual_project_slug)

            v_O = extrair_vetor_O(canonical, task.prazo_contratual)
            v_EF = extrair_vetor_EF(canonical, report)
            decision = (report.get("quality_gates") or {}).get("decision") or "BLOQUEADO"
            viabilidade = _map_viabilidade_decision(decision)
            result = CenarioAvaliado(
                cenario_id=cid,
                parametros_variados=task.variados,
                viabilidade=viabilidade,
                vetor_O=v_O,
                vetor_EF=v_EF,
                classificacao_O=classificar_O(v_O, task.perfil),
                classificacao_EF=classificar_EF(v_EF, task.perfil),
            )
        except Exception as exc:
            result = CenarioAvaliado(
                cenario_id=cid,
                parametros_variados=task.variados,
                viabilidade="ERRO",
                vetor_O=VetorEspacoO(),
                vetor_EF=VetorEspacoEF(),
                classificacao_O="CRITICO",
                classificacao_EF="FORA_EXPECTATIVA",
                erro=str(exc),
            )
        finally:
            _cleanup_scenario_projects(scenario_projects_root, scenario_slug, actual_project_slug)

    return result


