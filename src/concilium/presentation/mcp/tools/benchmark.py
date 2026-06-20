"""Ferramentas MCP de Benchmark — empacotamento e download de artefatos.

ADR-116: `listar_benchmarks` e `executar_benchmark` foram removidas (duplicatas do
módulo `benchmark_nep039`, que oferece store versionado + imutabilidade). Use
`listar_benchmarks_nep039` e `executar_benchmark_nep039`. Este módulo mantém apenas
empacotamento/download, que não têm equivalente no NEP-039.
"""

from __future__ import annotations

import base64
from typing import Any

from mcp.server.fastmcp import FastMCP

from concilium.presentation.mcp._context import _config_root, _wrap_response


def register(server: FastMCP) -> None:
    """Registra as ferramentas de empacotamento/download de benchmark no servidor MCP."""

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
        from concilium.application.benchmarks.charts.output_packager import empacotar_outputs

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
            from concilium.application.benchmarks.charts.output_packager import empacotar_outputs

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

    # ADR-116: executar_benchmark removida — usar executar_benchmark_nep039 (store versionado).
