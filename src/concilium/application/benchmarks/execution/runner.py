from __future__ import annotations

import importlib
import json
import logging
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Any

from concilium.application.runtime import Runtime

from ..inference import BenchmarkInferenceService  # noqa: F401 — needed for monkeypatching in tests
from ..report.report_builder import BenchmarkReportBuilder
from ..report.report_printer import BenchmarkReportPrinter
from ..spec.spec_loader import ProjectSpec

logger = logging.getLogger(__name__)

if TYPE_CHECKING:
    from concilium.application.skills.phase_classifier import PipelineMode


def _emit_business_telemetry(spec: Any, report: dict, mode: Any) -> None:
    """Emite métricas de negócio (margem, custo direto) ao OTel após pipeline completo."""
    try:
        from concilium.infrastructure.telemetry import record_project_margin

        ferramenta = (report.get("resultado") or {}).get("ferramenta") or {}
        margem_raw = ferramenta.get("margem_pct")
        custo_direto = ferramenta.get("custo_direto")
        if margem_raw is None:
            return
        record_project_margin(
            project_id=getattr(spec, "benchmark_id", None) or str(getattr(spec, "project_slug", "unknown")),
            margem_pct=float(margem_raw),
            custo_direto=float(custo_direto) if custo_direto is not None else None,
            pipeline_mode=getattr(mode, "value", str(mode)),
        )
    except Exception:
        pass


def _load_inference_service() -> Any:
    mod = importlib.import_module("concilium.application.benchmarks.inference")
    svc_cls = getattr(mod, "BenchmarkInferenceService", None)
    if svc_cls is None:
        raise RuntimeError("BenchmarkInferenceService indisponivel")
    return svc_cls


@dataclass
class BenchmarkRunner:
    config_root: Path
    projects_root: Path
    report_builder: BenchmarkReportBuilder
    report_printer: BenchmarkReportPrinter

    @classmethod
    def from_settings(
        cls,
        report_builder: BenchmarkReportBuilder | None = None,
        report_printer: BenchmarkReportPrinter | None = None,
    ) -> BenchmarkRunner:
        """Constrói BenchmarkRunner a partir de concilium.infrastructure.settings.

        Usa CONCILIUM__CONFIG_ROOT e CONCILIUM__BENCHMARK_PROJECTS_ROOT (ou derivados).
        Elimina a necessidade de passar caminhos explícitos ou patchear env vars manualmente.
        """
        from concilium.infrastructure.settings import get_storage

        storage = get_storage()
        config_root = storage.config_root
        projects_root = storage.benchmark_projects_root or (storage.root / "benchmarks" / "projetos")
        return cls(
            config_root=config_root,
            projects_root=projects_root,
            report_builder=report_builder or BenchmarkReportBuilder(),
            report_printer=report_printer or BenchmarkReportPrinter(),
        )

    def _load_existing_report_if_fresh(self, spec: ProjectSpec, store: Any, reset: bool) -> dict[str, Any] | None:
        """Short-circuit: retorna o benchmark_report existente se reset não foi solicitado e o canônico existe."""
        if reset:
            return None
        v = store.current_version()
        if v is None or store.load_canonical(v) is None:
            return None
        audit_dir = self._artifact_output_dir(spec).parent / "audit"
        report_file = audit_dir / "benchmark_report.json"
        if not report_file.exists():
            return None
        return json.loads(report_file.read_text(encoding="utf-8"))

    def _resolve_procurement_profile(
        self, spec: ProjectSpec, procurement_intent: str, store: Any, get_pipeline_profile_for_intent: Any
    ) -> Any:
        """Resolve o profile RFX para o intent informado e valida a baseline de procurement (ADR-115 D4/D6)."""
        # No benchmark, a baseline é a referência seed (read-only): existe
        # independentemente de `reset`, que apenas recomputa os artefatos.
        # Fallback: versão corrente do store (cenário sem referência seed).
        from concilium.domain.models.procurement import validate_procurement_baseline

        profile = get_pipeline_profile_for_intent(procurement_intent)
        if spec.referencia_path and spec.referencia_path.exists():
            _baseline_ref = str(spec.referencia_path)
        else:
            _baseline_ref = store.current_version()
        validate_procurement_baseline(procurement_intent, _baseline_ref)
        return profile

    def _resolve_run_mode_and_skills(
        self,
        spec: ProjectSpec,
        mode: PipelineMode | None,
        skip_artifacts: bool,
        procurement_intent: str | None,
        store: Any,
        pipeline_mode_cls: Any,
        get_pipeline_profile_for_intent: Any,
        get_skills_for_mode: Any,
    ) -> tuple[Any, Any, Any]:
        """Resolve (mode, profile, skill_sequence) a partir de procurement_intent, ou de mode/skip_artifacts legado."""
        if procurement_intent:
            profile = self._resolve_procurement_profile(
                spec, procurement_intent, store, get_pipeline_profile_for_intent
            )
            return profile.mode, profile, profile.skill_sequence
        # Resolve modo de execução: mode= tem precedência sobre skip_artifacts legado
        if mode is None:
            mode = pipeline_mode_cls.OLTP if skip_artifacts else pipeline_mode_cls.OLAP
        return mode, None, get_skills_for_mode(mode)

    def _persist_rfx_declared_deliverables(self, store: Any, artifacts_dir: Path, profile: Any) -> None:
        """Materializa os entregáveis declarados no perfil RFX no diretório de artefatos."""
        v = store.current_version()
        declared = set(profile.deliverables)
        for fname in store.list_output_files(v):
            if fname not in declared:
                continue
            data = store.load_output_file(v, fname)
            if data is None:
                continue
            subdir = self._get_output_subdir(fname)
            subdir_path = artifacts_dir / subdir
            subdir_path.mkdir(parents=True, exist_ok=True)
            try:
                (subdir_path / fname).write_bytes(data)
            except PermissionError:
                print(f"  [WARN] {fname} em uso — artefato ignorado")

    def _save_non_olap_report_and_artifacts(
        self, spec: ProjectSpec, store: Any, report: dict[str, Any], profile: Any
    ) -> None:
        """Modo OLTP/LIGHT: sempre salva benchmark_report; com perfil RFX, materializa entregáveis declarados."""
        artifacts_dir = self._artifact_output_dir(spec)
        audit_dir = artifacts_dir.parent / "audit"
        audit_dir.mkdir(parents=True, exist_ok=True)
        (audit_dir / "benchmark_report.json").write_text(
            json.dumps(report, indent=2, default=str, ensure_ascii=False), encoding="utf-8"
        )
        if profile is not None:
            self._persist_rfx_declared_deliverables(store, artifacts_dir, profile)

    def _copy_olap_output_files(self, store: Any, artifacts_dir: Path) -> list[str]:
        """Copia outputs relevantes (markdown, PDF, imagens etc.) do project store para artifacts_dir."""
        v = store.current_version()
        saved: list[str] = ["benchmark_report.json"]
        keep_names = {
            "relatorio.json",
            "relatorio.md",
            "relatorio.pdf",
            "memorial_bdi.md",
            "memorial_bdi.pdf",
            "resumo_executivo.md",  # ADR-093 D5
        }
        for fname in store.list_output_files(v):
            if fname.endswith(".png") or fname.startswith("resultado_planejamento") or fname in keep_names:
                data = store.load_output_file(v, fname)
                if data is not None:
                    try:
                        # Organiza em subpastas: visualizations/ para imagens, reports/ para PDFs/XLSXs
                        subdir = self._get_output_subdir(fname)
                        subdir_path = artifacts_dir / subdir
                        subdir_path.mkdir(parents=True, exist_ok=True)
                        (subdir_path / fname).write_bytes(data)
                        saved.append(fname)
                    except PermissionError:
                        print(f"  [WARN] {fname} em uso — artefato ignorado")
        return saved

    def _save_olap_report_and_artifacts(self, spec: ProjectSpec, store: Any, report: dict[str, Any]) -> None:
        """Modo OLAP: salva benchmark_report.json em audit/ e copia outputs relevantes para artifacts_dir."""
        # Caminho organizado por benchmark slug (unico destino de artefatos).
        artifacts_dir = self._artifact_output_dir(spec)
        artifacts_dir.mkdir(parents=True, exist_ok=True)

        # benchmark_report.json → audit/
        audit_dir = artifacts_dir.parent / "audit"
        audit_dir.mkdir(parents=True, exist_ok=True)
        report_file = audit_dir / "benchmark_report.json"
        report_file.write_text(json.dumps(report, indent=2, default=str, ensure_ascii=False), encoding="utf-8")

        # Copia outputs relevantes do project store para artifacts_dir.
        # Inclui markdown e PDF para manter paridade de artefatos auditaveis.
        saved = self._copy_olap_output_files(store, artifacts_dir)

        print(f"\n  [SAVE] Artefatos em: {artifacts_dir}")
        for f in saved:
            print(f"  [SAVE]   {f}")

    def run(
        self,
        spec: ProjectSpec,
        *,
        reset: bool = False,
        skip_artifacts: bool = False,
        mode: PipelineMode | None = None,
        procurement_intent: str | None = None,
    ) -> dict[str, Any]:
        """Executa o benchmark com o modo de pipeline especificado.

        Args:
            mode:           PipelineMode.OLTP (01-06), LIGHT (01-06+relatorio) ou
                            OLAP (01-11 completo, padrão). Tem precedência sobre skip_artifacts.
            procurement_intent:
                            Linguagem RFX (`rfi|rfp`) resolvida no core da
                            pipeline para definir caminho e entregáveis.
                            Quando informado, tem precedência sobre `mode` e
                            `skip_artifacts`.
            skip_artifacts: Legado — equivale a mode=PipelineMode.OLTP quando True.
        """
        from concilium.application.skills.phase_classifier import (
            PipelineMode,
            get_pipeline_profile_for_intent,
            get_skills_for_mode,
        )

        store = self._find_or_create(spec.nome, spec.slug, spec.contexto_id, reset)

        # Short-circuit: canonical + relatório já existem e reset não foi solicitado.
        existing_report = self._load_existing_report_if_fresh(spec, store, reset)
        if existing_report is not None:
            return existing_report

        runtime = Runtime(self.config_root)
        ref_data = self._load_referencia(spec)
        svc_cls = _load_inference_service()
        inference_pack = svc_cls.derive(ref_data)

        if store.current_version() is None:
            store.new_version()

        mode, profile, _skill_seq = self._resolve_run_mode_and_skills(
            spec,
            mode,
            skip_artifacts,
            procurement_intent,
            store,
            PipelineMode,
            get_pipeline_profile_for_intent,
            get_skills_for_mode,
        )

        results_log = runtime.run_pipeline(
            store,
            self._prepare_inputs(spec, ref_data, inference_pack),
            skill_sequence=_skill_seq,
        )
        report = self.report_builder.build(
            spec=spec,
            version=store.current_version(),
            results_log=results_log,
            ref=ref_data,
            canonical=store.load_canonical(),
            inference_pack=inference_pack,
        )
        if profile is not None:
            report.setdefault("rfx", {})
            report["rfx"].update(
                {
                    "intent": profile.intent.value,
                    "path_name": profile.path_name,
                    "pipeline_mode": profile.mode.value,
                    "deliverables": profile.deliverables,
                }
            )
        self.report_printer.print(report)
        _emit_business_telemetry(spec, report, mode)

        if mode != PipelineMode.OLAP:
            self._save_non_olap_report_and_artifacts(spec, store, report, profile)
            return report

        self._save_olap_report_and_artifacts(spec, store, report)
        return report

    @staticmethod
    def _get_output_subdir(filename: str) -> str:
        """Determina o subdiretório baseado na extensão do arquivo.

        returns: "visualizations" para imagens, "reports" para PDFs/XLSXs
        """
        from pathlib import Path

        ext = Path(filename).suffix.lower()
        if ext in (".png", ".jpg", ".jpeg", ".gif", ".svg", ".webp"):
            return "visualizations"
        if ext in (".pdf", ".xlsx", ".xls", ".csv"):
            return "reports"
        return "reports"  # fallback

    def _artifact_output_dir(self, spec: ProjectSpec) -> Path:
        # Entregáveis computados vivem em projetos/ (sorvedouro), não em data/ (fonte).
        # data/{slug}/ é somente leitura: referencia.json, campaign_v{i}.json, artifacts/raw/.
        return self.projects_root / spec.slug / "artifacts" / "outputs"

    def _benchmark_repository(self):
        from concilium.infrastructure.storage.store_factory import build_local_project_repository

        return build_local_project_repository(self.projects_root)

    def _reset_project(self, handle, repo, nome: str, benchmark_id: str, contexto_id: str):
        """Recria o projeto do zero preservando overrides/ (calibrações de projeto)."""
        print(f"  [DEL] Removendo projeto anterior: {benchmark_id}")
        overrides_backup: dict[str, bytes] = {}
        for fname in handle.list_file_names("overrides"):
            data = handle.read_bytes(f"overrides/{fname}")
            if data is not None:
                overrides_backup[fname] = data
        handle.delete_tree("")
        fresh = repo.create_project(nome, contexto_id, project_id=benchmark_id)
        for fname, data in overrides_backup.items():
            fresh.write_bytes(f"overrides/{fname}", data)
        return fresh

    def _find_or_create(self, nome: str, benchmark_id: str, contexto_id: str, reset: bool):
        repo = self._benchmark_repository()
        try:
            handle = repo.get_project(benchmark_id)
        except FileNotFoundError:
            handle = None

        if handle is not None:
            if handle.meta.get("nome") == nome:
                if reset:
                    return self._reset_project(handle, repo, nome, benchmark_id, contexto_id)
                print(f"  [OK]  Projeto existente: {benchmark_id}")
                return handle

        print(f"  [NEW] Criando '{nome}'...")
        return repo.create_project(nome, contexto_id, project_id=benchmark_id)

    def _load_referencia(self, spec: ProjectSpec) -> dict[str, Any] | None:
        if spec.referencia_path and spec.referencia_path.exists():
            return json.loads(spec.referencia_path.read_text(encoding="utf-8"))
        return None

    def _prepare_inputs(
        self,
        spec: ProjectSpec,
        ref: dict[str, Any] | None = None,
        inference_pack: Any | None = None,
    ) -> dict[str, dict]:
        skill_inputs: dict[str, dict] = {}
        if spec.inputs_escopo:
            if "contexto_id" not in spec.inputs_escopo:
                spec.inputs_escopo["contexto_id"] = spec.contexto_id
            skill_inputs["01-escopo-e-eap"] = spec.inputs_escopo
            skill_inputs["00-escopo"] = spec.inputs_escopo
        if spec.inputs_01A:
            skill_inputs["03-catalogo-de-recursos"] = spec.inputs_01A
        if spec.inputs_cronograma:
            skill_inputs["04-cronograma"] = spec.inputs_cronograma
        skill_inputs.update(spec.extra_inputs)
        # NEP-041 F4: indiretos e consolidação compartilham a chave unificada —
        # mesclar por cima de extra_inputs (que pode trazer consolidacao_inputs do spec)
        # em vez de substituir o dict inteiro.
        if spec.inputs_indiretos:
            skill_inputs.setdefault("06-resultado-financeiro", {}).update(spec.inputs_indiretos)

        # Em contexto de benchmark, a análise bridge (ADR-039) não deve usar custo
        # operacional de equipes (N4) — a comparação é catalog-vs-reference, não
        # deployment-vs-reference. Sem isso, skill-08 propaga VERMELHO → skill-15
        # falha com ERRO → status_final=INVIAVEL mesmo quando o plano é viável.
        skill_inputs.setdefault("05-equipes-e-alocacao", {})["benchmark_mode"] = True
        if isinstance(ref, dict) and isinstance(ref.get("planejamento"), list):
            skill_inputs.setdefault("05-equipes-e-alocacao", {})["planejamento_ref"] = ref.get("planejamento")
        skill_inputs.setdefault("06-resultado-financeiro", {})["benchmark_mode"] = True

        svc_cls = _load_inference_service()
        pack = inference_pack or svc_cls.derive(ref)
        skill_inputs = svc_cls.apply_to_skill_inputs(skill_inputs, pack)
        return skill_inputs
