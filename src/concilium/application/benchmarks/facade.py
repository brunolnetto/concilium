"""BenchmarkFacade — ADR-043.

Ponto de entrada unificado para execução de benchmarks.

Resolve dois problemas:
  1. Scripts em benchmarks/ usavam Path(__file__) para descobrir raízes, bloqueando
     execução de fora do diretório (e em paths com Unicode no Windows).
  2. Cronogramas com chaves numéricas de semana ("1", "2"...) não eram reconhecidos
     pelo BenchmarkInputDeriver que espera ISO-week keys ("2026-W02").

Uso típico via CONCILIUM__ROOT env var:

    import os
    from pathlib import Path
    from concilium.application.benchmarks import BenchmarkFacade

    facade = BenchmarkFacade.from_env()
    report = facade.run_single("AGIS", reset=True)
    print(report["status_final"])
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .batch import BenchmarkBatchRunner
from .input_derivation import normalize_referencia_weeks
from .report_builder import BenchmarkReportBuilder
from .report_printer import BenchmarkReportPrinter
from .runner import BenchmarkRunner
from .spec_loader import load_spec_from_dict


@dataclass
class BenchmarkFacade:
    """Fachada para execução de benchmarks individuais ou em lote.

    Args:
        benchmarks_root: diretório ``benchmarks/data/`` com subpastas por slug.
        config_root:     diretório ``config/`` do catálogo.
        projects_root:   diretório ``projetos/`` para persistência.
    """

    benchmarks_root: Path
    config_root: Path
    projects_root: Path

    # ── Construtores ──────────────────────────────────────────────────────────

    @classmethod
    def from_env(cls) -> BenchmarkFacade:
        """Cria facade a partir de CONCILIUM__ROOT (ou variáveis individuais)."""
        root_str = os.environ.get("CONCILIUM__ROOT")
        if root_str:
            root = Path(root_str)
        else:
            # Fallback: usa cwd como raiz (compatível com scripts legados em benchmarks/)
            root = Path.cwd().parent

        config_root = Path(os.environ.get("CONCILIUM__CONFIG_ROOT", str(root / "config")))
        benchmarks_root = root / "benchmarks" / "data"
        # Projetos de benchmark ficam isolados em benchmarks/projetos/
        # (CONCILIUM__PROJECTS_ROOT sobrescreve apenas para pipelines reais)
        projects_root = Path(os.environ.get("CONCILIUM__BENCHMARK_PROJECTS_ROOT", str(root / "benchmarks" / "projetos")))

        return cls(
            benchmarks_root=benchmarks_root,
            config_root=config_root,
            projects_root=projects_root,
        )

    @classmethod
    def from_root(cls, root: Path | str) -> BenchmarkFacade:
        """Cria facade a partir de um caminho raiz explícito."""
        root = Path(root)
        return cls(
            benchmarks_root=root / "benchmarks" / "data",
            config_root=root / "config",
            projects_root=root / "benchmarks" / "projetos",
        )

    # ── Execução ──────────────────────────────────────────────────────────────

    def run_single(self, slug: str, *, reset: bool = True) -> dict[str, Any]:
        """Executa benchmark de um único projeto pelo slug.

        Normaliza automaticamente semanas numéricas → ISO antes de injetar nos inputs.
        """
        slug_upper = slug.upper()
        benchmark_dir = self.benchmarks_root / slug_upper
        ref_path = benchmark_dir / "referencia.json"

        if not ref_path.exists():
            raise FileNotFoundError(f"referencia.json não encontrado: {ref_path}")

        # Normalizar semanas numéricas → ISO em memória (ADR-043).
        # Não reescreve o arquivo fonte — isolamento entre benchmark e pipeline.
        ref_data = json.loads(ref_path.read_text(encoding="utf-8"))
        normalize_referencia_weeks(ref_data)  # modifica in-place, sem I/O

        spec = load_spec_from_dict(ref_data, ref_path)
        runner = self._make_runner()
        return runner.run(spec, reset=reset)

    def run_all(self, *, reset: bool = True) -> list[dict[str, Any]]:
        """Executa todos os benchmarks descobertos em benchmarks_root."""
        batch = BenchmarkBatchRunner(
            benchmarks_root=self.benchmarks_root,
            config_root=self.config_root,
            projects_root=self.projects_root,
        )
        # run_all delega ao batch que normaliza em memória em discover_specs.
        return batch.run_all(reset=reset)

    def build_summary(self, reports: list[dict[str, Any]]) -> list[dict[str, Any]]:
        """Delega ao BenchmarkBatchRunner.build_summary."""
        batch = BenchmarkBatchRunner(
            benchmarks_root=self.benchmarks_root,
            config_root=self.config_root,
            projects_root=self.projects_root,
        )
        return batch.build_summary(reports)

    # ── Helpers ───────────────────────────────────────────────────────────────

    def _make_runner(self) -> BenchmarkRunner:
        return BenchmarkRunner(
            config_root=self.config_root,
            projects_root=self.projects_root,
            report_builder=BenchmarkReportBuilder(),
            report_printer=BenchmarkReportPrinter(),
        )
