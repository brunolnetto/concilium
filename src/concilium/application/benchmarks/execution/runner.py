from __future__ import annotations

import importlib
import json
import logging
import shutil
from dataclasses import dataclass
from datetime import UTC
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

from concilium.application.runtime import Runtime

from ..inference import BenchmarkInferenceService  # noqa: F401 — needed for monkeypatching in tests
from ..report.report_builder import BenchmarkReportBuilder
from ..report.report_printer import BenchmarkReportPrinter
from ..spec.spec_loader import ProjectSpec


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
                            Linguagem RFX (`rfi|rfp|rfq`) resolvida no core da
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
        if not reset:
            v = store.current_version()
            if v is not None and store.load_canonical(v) is not None:
                audit_dir = self._artifact_output_dir(spec).parent / "audit"
                report_file = audit_dir / "benchmark_report.json"
                if report_file.exists():
                    return json.loads(report_file.read_text(encoding="utf-8"))

        runtime = Runtime(self.config_root)
        ref_data = self._load_referencia(spec)
        svc_cls = _load_inference_service()
        inference_pack = svc_cls.derive(ref_data)

        if store.current_version() is None:
            store.new_version()

        profile = None
        if procurement_intent:
            profile = get_pipeline_profile_for_intent(procurement_intent)
            # ADR-115 D4/D6: RFQ exige baseline congelada (RFI/RFP previamente definidos).
            # No benchmark, a baseline é a referência seed (read-only): existe
            # independentemente de `reset`, que apenas recomputa os artefatos.
            # Fallback: versão corrente do store (cenário sem referência seed).
            from concilium.domain.models.procurement import validate_procurement_baseline

            if spec.referencia_path and spec.referencia_path.exists():
                _baseline_ref = str(spec.referencia_path)
            else:
                _baseline_ref = store.current_version()
            validate_procurement_baseline(procurement_intent, _baseline_ref)
            mode = profile.mode
            _skill_seq = profile.skill_sequence
        else:
            # Resolve modo de execução: mode= tem precedência sobre skip_artifacts legado
            if mode is None:
                mode = PipelineMode.OLTP if skip_artifacts else PipelineMode.OLAP
            _skill_seq = get_skills_for_mode(mode)

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

        # Registrar execução no BenchmarkStore para auditabilidade (NEP-039).
        self._log_execution(spec, report, store_project=store)

        if mode != PipelineMode.OLAP:
            # Modo OLTP/LIGHT: sempre salva benchmark_report; quando houver perfil RFX
            # explícito, materializa também os entregáveis declarados no perfil.
            artifacts_dir = self._artifact_output_dir(spec)
            audit_dir = artifacts_dir.parent / "audit"
            audit_dir.mkdir(parents=True, exist_ok=True)
            (audit_dir / "benchmark_report.json").write_text(
                json.dumps(report, indent=2, default=str, ensure_ascii=False), encoding="utf-8"
            )
            if profile is not None:
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
            return report

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

        print(f"\n  [SAVE] Artefatos em: {artifacts_dir}")
        for f in saved:
            print(f"  [SAVE]   {f}")
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

    def _log_execution(self, spec: ProjectSpec, report: dict, store_project: Any) -> None:
        """Registra execução no FileSystemBenchmarkStore para auditabilidade (NEP-039).

        Falha silenciosa: log de auditoria não deve quebrar o fluxo principal.
        """
        try:
            import uuid
            from datetime import datetime

            from concilium.domain.benchmark.models import BenchmarkExecution, BenchmarkState
            from concilium.infrastructure.storage.benchmark_store import FileSystemBenchmarkStore

            nep039_root = self.projects_root / ".nep039"
            nep039_root.mkdir(parents=True, exist_ok=True)
            benchmark_store = FileSystemBenchmarkStore.from_path(nep039_root)

            gates = report.get("quality_gates") or {}
            decision = gates.get("decision") or "N/A"
            status = (
                BenchmarkState.SUCESSO if decision in {"APROVADO", "APROVADO_COM_RESSALVAS"} else BenchmarkState.FALHA
            )

            execution = BenchmarkExecution(
                execution_id=str(uuid.uuid4()),
                benchmark_id=spec.slug,
                versao=1,
                projeto_id=str(store_project.root) if store_project else "",
                status=status,
                executado_em=datetime.now(UTC),
                discrepancia_sumario={
                    "decision": decision,
                    "worst_severity": gates.get("worst_severity"),
                    "n_gates": len(gates.get("items") or []),
                },
            )
            benchmark_store.log_execution(execution)
        except Exception as e:
            logger.warning(
                "Falha ao registrar execução no benchmark store (não bloqueia o fluxo): %s", e, exc_info=True
            )

    def _find_or_create(self, nome: str, benchmark_id: str, contexto_id: str, reset: bool):

        from concilium.infrastructure.storage.benchmark_store import FileSystemBenchmarkStore
        from concilium.infrastructure.storage.project import ProjectStore

        # Load benchmark metadata if available
        benchmark_versao = None
        benchmark_execution_id = None
        nep039_root = self.projects_root / ".nep039"
        if nep039_root.exists():
            try:
                store = FileSystemBenchmarkStore.from_path(nep039_root)
                meta = store.get_metadata(benchmark_id)
                if meta:
                    benchmark_versao = meta.versao
            except Exception as e:
                logger.warning(
                    "Falha ao carregar metadata do benchmark store (continuando sem linkage): %s", e, exc_info=True
                )

        if self.projects_root.exists():
            for project_dir in self.projects_root.iterdir():
                meta_path = project_dir / "meta.json"
                if not project_dir.is_dir() or not meta_path.exists():
                    continue
                meta = json.loads(meta_path.read_text(encoding="utf-8"))
                if meta.get("nome") == nome:
                    if reset:
                        print(f"  [DEL] Removendo projeto anterior: {project_dir.name}")
                        # Preservar overrides/ — contém calibrações de projeto (cpus, insumos, producoes)
                        overrides_dir = project_dir / "overrides"
                        overrides_backup = {}
                        if overrides_dir.exists():
                            for f in overrides_dir.iterdir():
                                overrides_backup[f.name] = f.read_bytes()
                        shutil.rmtree(project_dir, ignore_errors=True)
                        if project_dir.exists():
                            print(
                                f"  [AVISO] Nao foi possivel remover completamente {project_dir.name}. Continuando..."
                            )
                        # Restaurar overrides/
                        if overrides_backup:
                            overrides_dir.mkdir(parents=True, exist_ok=True)
                            for fname, content in overrides_backup.items():
                                (overrides_dir / fname).write_bytes(content)
                        break
                    print(f"  [OK]  Projeto existente: {project_dir.name}")
                    return ProjectStore(project_dir)

        print(f"  [NEW] Criando '{nome}'...")
        self.projects_root.mkdir(parents=True, exist_ok=True)
        return ProjectStore.init(
            self.projects_root,
            nome,
            contexto_id,
            derivado_de_benchmark=benchmark_id,
            benchmark_versao=benchmark_versao,
            benchmark_execution_id=benchmark_execution_id,
        )

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
