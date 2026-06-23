"""MCP Tools para Benchmarks — NEP-039.

Implementa 1 ferramenta de leitura:
1. consultar_benchmark — lê diretamente de benchmarks/data/ sem store externo
"""

from typing import Any

from mcp.server.fastmcp import FastMCP

from concilium.infrastructure.auth.permission_guard import permission


def register(server: FastMCP) -> None:
    """Registra ferramentas de benchmark no servidor MCP."""

    @server.tool(description=(
        "Consulta benchmarks NEP-039: lista todos ou detalha um específico. "
        "Omita benchmark_id para listar todos; informe-o para obter metadados."
    ))
    @permission("project:read")
    def consultar_benchmark(benchmark_id: str | None = None) -> dict[str, Any]:
        """Lista benchmarks disponíveis ou detalha um benchmark específico.

        Omita benchmark_id para listar todos; informe-o para detalhar um benchmark.
        """
        import json as _json

        from concilium.presentation.mcp._context import _config_root, _wrap_response

        data_dir = _config_root().parent / "benchmarks" / "data"

        if benchmark_id is None:
            if not data_dir.exists():
                return _wrap_response({"total": 0, "benchmarks": []})
            benchmarks = []
            for slug_dir in sorted(data_dir.iterdir()):
                if not slug_dir.is_dir():
                    continue
                ref_file = slug_dir / "referencia.json"
                meta = {}
                if ref_file.exists():
                    try:
                        ref = _json.loads(ref_file.read_text(encoding="utf-8"))
                        proj = ref.get("projeto") or {}
                        meta = {
                            "benchmark_id": slug_dir.name,
                            "nome": proj.get("nome") or slug_dir.name,
                            "tipo_obra": proj.get("tipo_obra"),
                            "gerado_em": (ref.get("meta") or {}).get("gerado_em"),
                        }
                    except Exception:
                        meta = {"benchmark_id": slug_dir.name}
                else:
                    meta = {"benchmark_id": slug_dir.name}
                benchmarks.append(meta)
            return _wrap_response({"total": len(benchmarks), "benchmarks": benchmarks})

        slug_dir = data_dir / benchmark_id
        if not slug_dir.exists():
            return _wrap_response({"erro": f"Benchmark '{benchmark_id}' não encontrado", "status": "NAO_ENCONTRADO"})
        ref_file = slug_dir / "referencia.json"
        if not ref_file.exists():
            return _wrap_response({"benchmark_id": benchmark_id, "referencia": None})
        try:
            ref = _json.loads(ref_file.read_text(encoding="utf-8"))
        except Exception as e:
            return _wrap_response({"erro": str(e)})
        return _wrap_response({
            "benchmark_id": benchmark_id,
            "projeto": ref.get("projeto"),
            "eap_n_itens": len(ref.get("eap", [])),
            "meta": ref.get("meta", {}),
        })
