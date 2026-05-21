from __future__ import annotations

import json
import shutil
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from concilium.application.runtime import Runtime

from .report_builder import BenchmarkReportBuilder
from .report_printer import BenchmarkReportPrinter
from .spec_loader import ProjectSpec


@dataclass
class BenchmarkRunner:
    config_root: Path
    projects_root: Path
    report_builder: BenchmarkReportBuilder
    report_printer: BenchmarkReportPrinter

    def run(self, spec: ProjectSpec, *, reset: bool = False) -> dict[str, Any]:
        store = self._find_or_create(spec.nome, spec.contexto_id, reset)
        runtime = Runtime(self.config_root)

        if store.current_version() is None:
            store.new_version()

        results_log = runtime.run_pipeline(store, self._prepare_inputs(spec))
        report = self.report_builder.build(
            spec=spec,
            version=store.current_version(),
            results_log=results_log,
            ref=self._load_referencia(spec),
            canonical=store.load_canonical(),
        )
        self.report_printer.print(report)

        # Caminho organizado por benchmark slug (unico destino de artefatos).
        artifacts_dir = self._artifact_output_dir(spec)
        artifacts_dir.mkdir(parents=True, exist_ok=True)

        # benchmark_report.json → audit/
        audit_dir = artifacts_dir.parent / "audit"
        audit_dir.mkdir(parents=True, exist_ok=True)
        report_file = audit_dir / "benchmark_report.json"
        report_file.write_text(json.dumps(report, indent=2, default=str, ensure_ascii=False), encoding="utf-8")

        # Copia outputs do project store para artifacts_dir (Excel principal, relatorio.json, relatorio.md)
        v = store.current_version()
        saved: list[str] = ["benchmark_report.json"]
        for fname in store.list_output_files(v):
            if fname.startswith("resultado_planejamento") or fname in ("relatorio.json", "relatorio.md"):
                data = store.load_output_file(v, fname)
                if data is not None:
                    try:
                        (artifacts_dir / fname).write_bytes(data)
                        saved.append(fname)
                    except PermissionError:
                        print(f"  [WARN] {fname} em uso — artefato ignorado")

        print(f"\n  [SAVE] Artefatos em: {artifacts_dir}")
        for f in saved:
            print(f"  [SAVE]   {f}")
        return report

    def _artifact_output_dir(self, spec: ProjectSpec) -> Path:
        if spec.referencia_path is not None:
            p = spec.referencia_path.parent
            # If referencia lives inside …/artifacts/inputs/, step up to …/artifacts/
            if p.name == "inputs" and p.parent.name == "artifacts":
                p = p.parent
            return p / "outputs"
        return Path("benchmarks") / "data" / spec.slug / "artifacts" / "outputs"

    def _find_or_create(self, nome: str, contexto_id: str, reset: bool):
        from concilium.infrastructure.storage.project import ProjectStore

        if self.projects_root.exists():
            for project_dir in self.projects_root.iterdir():
                meta_path = project_dir / "meta.json"
                if not project_dir.is_dir() or not meta_path.exists():
                    continue
                meta = json.loads(meta_path.read_text(encoding="utf-8"))
                if meta.get("nome") == nome:
                    if reset:
                        print(f"  [DEL] Removendo projeto anterior: {project_dir.name}")
                        shutil.rmtree(project_dir, ignore_errors=True)
                        if project_dir.exists():
                            print(
                                f"  [AVISO] Nao foi possivel remover completamente {project_dir.name}. Continuando..."
                            )
                        break
                    print(f"  [OK]  Projeto existente: {project_dir.name}")
                    return ProjectStore(project_dir)

        print(f"  [NEW] Criando '{nome}'...")
        self.projects_root.mkdir(parents=True, exist_ok=True)
        return ProjectStore.init(self.projects_root, nome, contexto_id)

    def _load_referencia(self, spec: ProjectSpec) -> dict[str, Any] | None:
        if spec.referencia_path and spec.referencia_path.exists():
            return json.loads(spec.referencia_path.read_text(encoding="utf-8"))
        return None

    def _prepare_inputs(self, spec: ProjectSpec) -> dict[str, dict]:
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
        if spec.inputs_indiretos:
            skill_inputs["07-custos-indiretos"] = spec.inputs_indiretos
        skill_inputs.update(spec.extra_inputs)
        return skill_inputs
