"""Ferramentas MCP de Benchmark — execução, empacotamento e download de artefatos."""

from __future__ import annotations

import base64
import json
from typing import Any

from mcp.server.fastmcp import FastMCP

from concilium.presentation.mcp_server._context import _config_root, _wrap_response


def register(server: FastMCP) -> None:
    """Registra as ferramentas de benchmark no servidor MCP."""

    @server.tool()
    def listar_benchmarks() -> dict[str, Any]:
        """Lista todos os benchmarks disponíveis com status e artefatos de saída.

        Retorna slug, nome, status, se há ZIP gerado e quantos arquivos de saída existem.
        """
        config_dir = _config_root()
        bench_root = config_dir.parent / "benchmarks" / "data"

        if not bench_root.exists():
            return _wrap_response({"benchmarks": [], "bench_root": str(bench_root)})

        benchmarks = []
        for slug_dir in sorted(bench_root.iterdir()):
            if not slug_dir.is_dir():
                continue
            ref = slug_dir / "referencia.json"
            if not ref.exists():
                ref = slug_dir / "artifacts" / "inputs" / "referencia.json"

            outputs_dir = slug_dir / "outputs"
            pngs = list(outputs_dir.glob("*.png")) if outputs_dir.exists() else []
            zips = list(outputs_dir.glob("*.zip")) if outputs_dir.exists() else []
            art_out = slug_dir / "artifacts" / "outputs"
            reports = list(art_out.glob("*.md")) + list(art_out.glob("*.json")) if art_out.exists() else []
            audit = slug_dir / "artifacts" / "audit" / "benchmark_report.json"

            nome = slug_dir.name
            if ref.exists():
                try:
                    data = json.loads(ref.read_text(encoding="utf-8"))
                    nome = data.get("projeto") or nome
                except Exception:
                    pass

            benchmarks.append(
                {
                    "slug": slug_dir.name,
                    "nome": nome[:80],
                    "tem_referencia": ref.exists(),
                    "tem_audit": audit.exists(),
                    "graficos": len(pngs),
                    "relatorios": len(reports),
                    "zips_disponiveis": [z.name for z in zips],
                }
            )

        return _wrap_response({"benchmarks": benchmarks, "total": len(benchmarks)})

    @server.tool()
    def empacotar_benchmark(
        slug: str,
        gerar_graficos: bool = True,
        incluir_cenarios: bool = False,
    ) -> dict[str, Any]:
        """Empacota os artefatos de saída do benchmark em ZIP.

        Gera PNGs (se não existirem e matplotlib disponível), empacota relatórios,
        audit e gráficos em um arquivo ZIP. Retorna o caminho e metadados do pacote.

        Args:
            slug:              Identificador do benchmark (ex.: "AGIS").
            gerar_graficos:    Gera PNGs analíticos antes de empacotar (requer matplotlib).
            incluir_cenarios:  Inclui JSONs dos cenários intermediários (plan space).
        """
        from concilium.application.benchmarks.output_packager import empacotar_outputs

        try:
            zip_path = empacotar_outputs(
                slug=slug,
                config_root=_config_root(),
                gerar_graficos=gerar_graficos,
                incluir_cenarios=incluir_cenarios,
            )
        except FileNotFoundError as e:
            return {"erro": str(e)}
        except Exception as e:
            return {"erro": f"Falha ao empacotar: {e}"}

        import zipfile

        conteudo: dict[str, list[str]] = {}
        with zipfile.ZipFile(zip_path) as zf:
            for info in zf.infolist():
                pasta = info.filename.split("/")[0]
                conteudo.setdefault(pasta, []).append(info.filename)

        return _wrap_response(
            {
                "zip_path": str(zip_path),
                "tamanho_bytes": zip_path.stat().st_size,
                "tamanho_mb": round(zip_path.stat().st_size / (1024 * 1024), 3),
                "slug": slug.upper(),
                "conteudo": {pasta: len(arqs) for pasta, arqs in conteudo.items()},
                "arquivos": {pasta: arqs for pasta, arqs in conteudo.items()},
                "nota": "Use download_benchmark_zip para obter o conteúdo binário base64.",
            }
        )

    @server.tool()
    def download_benchmark_zip(
        slug: str,
        zip_nome: str = "",
    ) -> dict[str, Any]:
        """Retorna o ZIP do benchmark em base64 para download direto.

        Útil quando o agente precisa transferir o arquivo sem acesso ao filesystem.
        Para arquivos grandes, prefira usar o path retornado por empacotar_benchmark.

        Args:
            slug:     Identificador do benchmark (ex.: "AGIS").
            zip_nome: Nome específico do ZIP (default: mais recente disponível).
        """
        config_dir = _config_root()
        bench_root = config_dir.parent / "benchmarks" / "data"
        slug_dir = bench_root / slug.upper()

        if not slug_dir.exists():
            return {"erro": f"Benchmark '{slug}' não encontrado."}

        outputs_dir = slug_dir / "outputs"
        zips = sorted(outputs_dir.glob("*.zip"), reverse=True) if outputs_dir.exists() else []

        if zip_nome:
            target = outputs_dir / zip_nome
            if not target.exists():
                return {"erro": f"ZIP '{zip_nome}' não encontrado em {outputs_dir}."}
        elif zips:
            target = zips[0]  # mais recente
        else:
            # Gera o ZIP se não existir
            from concilium.application.benchmarks.output_packager import empacotar_outputs

            try:
                target = empacotar_outputs(slug=slug, config_root=config_dir)
            except Exception as e:
                return {"erro": f"Falha ao criar ZIP: {e}"}

        size_mb = target.stat().st_size / (1024 * 1024)
        if size_mb > 20:
            return {
                "aviso": f"ZIP ({size_mb:.1f} MB) é grande para transferência inline.",
                "zip_path": str(target),
                "instrucao": "Leia diretamente do filesystem ou use a rota API GET /api/benchmarks/{slug}/download.",
            }

        conteudo_b64 = base64.b64encode(target.read_bytes()).decode("ascii")
        return _wrap_response(
            {
                "nome_arquivo": target.name,
                "tamanho_mb": round(size_mb, 3),
                "conteudo_base64": conteudo_b64,
                "encoding": "base64",
                "instrucao": "Decodifique base64 e salve como .zip para abrir.",
            }
        )

    @server.tool()
    def executar_benchmark(
        slug: str,
        reset: bool = False,
        gerar_graficos: bool = True,
        empacotar: bool = True,
    ) -> dict[str, Any]:
        """Executa o benchmark e opcionalmente gera gráficos e empacota saídas em ZIP.

        Orquestra: benchmark run → chart generation → pack.
        Equivalente a: `concilium benchmark run --slug SLUG --reset --charts --pack`

        Args:
            slug:            Identificador do benchmark (ex.: "AGIS").
            reset:           Força re-execução mesmo que resultado já exista.
            gerar_graficos:  Gera PNGs analíticos após o run (requer matplotlib).
            empacotar:       Cria ZIP com todos os artefatos ao final.
        """
        from concilium.application.benchmarks import BenchmarkRunner
        from concilium.application.benchmarks.batch import find_benchmark_reference
        from concilium.application.benchmarks.report_builder import BenchmarkReportBuilder
        from concilium.application.benchmarks.report_printer import BenchmarkReportPrinter
        from concilium.application.benchmarks.spec_loader import BenchmarkSpecLoader
        from concilium.presentation.mcp_server._context import _config_root

        config_dir = _config_root()
        bench_root = config_dir.parent / "benchmarks" / "data"

        ref_path = find_benchmark_reference(bench_root, slug.upper())
        if ref_path is None:
            return {"erro": f"Benchmark '{slug}' não encontrado em {bench_root}."}

        class _SilentPrinter(BenchmarkReportPrinter):
            def print(self, report: dict) -> None:
                pass

        spec = BenchmarkSpecLoader(config_dir).load(ref_path)
        runner = BenchmarkRunner(
            config_root=config_dir,
            projects_root=bench_root.parent / "projetos",
            report_builder=BenchmarkReportBuilder(),
            report_printer=_SilentPrinter(),
        )
        try:
            report = runner.run(spec, reset=reset)
        except Exception as e:
            return {"erro": f"Falha na execução: {e}"}

        resultado: dict[str, Any] = {
            "slug": slug.upper(),
            "status": report.get("status_final") or (report.get("quality_gates") or {}).get("decision") or "N/A",
            "delta_venda": (((report.get("confronto") or {}).get("deltas") or {}).get("preco_venda") or {}).get(
                "percentual"
            ),
        }

        if empacotar:
            from concilium.application.benchmarks.output_packager import empacotar_outputs

            try:
                zip_path = empacotar_outputs(slug=slug, config_root=config_dir, gerar_graficos=gerar_graficos)
                resultado["zip_path"] = str(zip_path)
                resultado["zip_mb"] = round(zip_path.stat().st_size / (1024 * 1024), 3)
            except Exception as e:
                resultado["aviso_pack"] = f"Run OK, empacotamento falhou: {e}"

        return _wrap_response(resultado)
