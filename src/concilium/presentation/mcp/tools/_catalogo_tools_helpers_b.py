"""MCP catalogo tool implementations — Part B."""

from __future__ import annotations

import json
from collections.abc import Callable
from pathlib import Path
from typing import Any, Protocol, cast

from concilium.presentation.mcp._context import _config_root, _wrap_response


class _MergeReport(Protocol):
    """Formato de retorno de mod._merge_entities() — mod é carregado via importlib
    de um script externo (merge_rfi.py), então seu tipo real não é conhecido
    estaticamente. Descreve a forma esperada pro consumo tipado do relatório."""

    inner_high: list[dict[str, Any]]
    inner_low: list[dict[str, Any]]
    right_only: list[dict[str, Any]]
    left_only: list[dict[str, Any]]


class _MergeRfiModule(Protocol):
    """Superfície esperada de tools/merge_rfi.py — script externo carregado via
    importlib (não importável estaticamente). O cast único no ponto de load dá
    checagem real a todos os acessos, no lugar de N supressões."""

    XLSM: Path
    ROOT: Path
    extract_rfi: Callable[[Any], dict[str, Any]]
    _merge_entities: Callable[..., tuple[_MergeReport, Any]]
    _apply_merge: Callable[..., list[Any]]


def _catalog_root(config_dir: Path, catalogo_id: str) -> Path:
    return config_dir / "catalogos" / catalogo_id


# _catalog_root defined below (avoids circular import)


def _impl_tendencia_precos_catalogo(
    contexto_id: str,
    jurisdicao_id: str | None = None,
) -> dict[str, Any]:
    """Índice de Tendência de Preços do catálogo por categoria (ADR-041 §D5 — Skill 20).

    Calcula a variação de preço de cada insumo usando historico_precos (SCD Type 2)
    e preços SICRO regionais. Identifica categorias com inflação acima da média.
    Útil para subsidiar revisões de BDI e repactuação contratual.

    Args:
        contexto_id:   ID do contexto (ex.: "mendeslobo").
        jurisdicao_id: Opcional. UF (ex.: "BR-CE") — usa preços SICRO regionais.
    """
    import dataclasses

    from concilium.application.catalog.price_trend import calcular_tendencia

    config_dir = _config_root()
    bundle_path = config_dir / "catalogos" / contexto_id / ".catalog_bundle.json"
    if not bundle_path.exists():
        return {"erro": f"Bundle não encontrado: {bundle_path}"}

    bundle = json.loads(bundle_path.read_text(encoding="utf-8"))
    insumos = bundle.get("insumos", [])

    relatorio = calcular_tendencia(insumos, jurisdicao_id=jurisdicao_id, contexto_id=contexto_id)

    # Serializa para dict (dataclasses são não-JSON-nativos)
    result = dataclasses.asdict(relatorio)
    # Limita insumos por categoria para não sobrecarregar a resposta MCP
    for idx in result.get("indices_por_categoria", []):
        top = sorted(idx.get("insumos", []), key=lambda x: abs(x.get("variacao_pct") or 0), reverse=True)
        idx["insumos"] = top[:10]  # top 10 por categoria
        idx["insumos_omitidos"] = max(0, len(idx.get("insumos", [])) - 10)

    return _wrap_response(result)


def _rfi_deltas_amostra(inner_high: list) -> list:
    return [
        {"codigo": i["catalog"].get("codigo") or i["catalog"].get("id"), "delta": i["delta"]}
        for i in inner_high
        if i["delta"]
    ][:20]


def _rfi_colisoes(inner_low: list) -> list:
    return [
        {
            "cat_codigo": i["catalog"].get("codigo") or i["catalog"].get("id"),
            "cat_descricao": i["catalog"].get("descricao", "")[:60],
            "rfi_codigo": i["rfi"].get("codigo") or i["rfi"].get("id"),
            "rfi_descricao": i["rfi"].get("descricao", "")[:60],
            "score": i["score"],
            "acao": f"RFI-{i['rfi'].get('codigo') or i['rfi'].get('id')} será criado",
        }
        for i in inner_low
    ]


def _rfi_novos(right_only: list) -> list:
    return [
        {
            "codigo": i["rfi"].get("codigo") or i["rfi"].get("id"),
            "descricao": i["rfi"].get("descricao", "")[:60],
            "unidade": i["rfi"].get("unidade"),
        }
        for i in right_only
    ][:30]


def _rfi_summarize_report(rep: _MergeReport) -> dict:
    """Sumariza um _MergeReport (insumos ou producoes) para a resposta de comparar_rfi_catalogo."""
    return {
        "inner_high": len(rep.inner_high),
        "inner_high_com_delta": sum(1 for i in rep.inner_high if i["delta"]),
        "inner_low": len(rep.inner_low),
        "right_only": len(rep.right_only),
        "left_only": len(rep.left_only),
        "deltas_amostra": _rfi_deltas_amostra(rep.inner_high),
        "colisoes": _rfi_colisoes(rep.inner_low),
        "novos": _rfi_novos(rep.right_only),
    }


def _build_comparar_rfi_result(
    dry_run: bool,
    contexto_id: str,
    cat_insumos: list,
    cat_producoes: list,
    rfi: dict,
    rep_ins: _MergeReport,
    rep_prod: _MergeReport,
) -> dict:
    """Monta o dict de resultado (sem aplicar merge) de comparar_rfi_catalogo."""
    return {
        "mode": "DRY_RUN" if dry_run else "APPLIED",
        "contexto_id": contexto_id,
        "catalogo_atual": {"insumos": len(cat_insumos), "producoes": len(cat_producoes)},
        "rfi": {"insumos": len(rfi["insumos"]), "producoes": len(rfi["producoes"])},
        "insumos": _rfi_summarize_report(rep_ins),
        "producoes": _rfi_summarize_report(rep_prod),
        "resumo": {
            "atualizacoes_preco": sum(1 for i in rep_ins.inner_high if i["delta"]),
            "novos_total": len(rep_ins.right_only) + len(rep_prod.right_only),
            "colisoes_total": len(rep_ins.inner_low) + len(rep_prod.inner_low),
        },
    }


def _apply_rfi_merge(
    mod: _MergeRfiModule,
    bundle: dict,
    bundle_path: Path,
    cat_insumos: list,
    cat_producoes: list,
    rfi: dict,
    rep_ins: _MergeReport,
    rep_prod: _MergeReport,
    result: dict,
) -> None:
    """Aplica o merge RFI no bundle (persistindo em disco) e anota `result["aplicado"]`."""
    new_ins = mod._apply_merge(cat_insumos, rfi["insumos"], rep_ins)
    new_prod = mod._apply_merge(cat_producoes, rfi["producoes"], rep_prod, id_key="id")
    if "producoes" in bundle:
        bundle["producoes"] = new_prod
    else:
        bundle["produtividades"] = new_prod
    bundle["insumos"] = new_ins
    bundle_path.write_text(json.dumps(bundle, indent=2, ensure_ascii=False), encoding="utf-8")
    result["aplicado"] = {
        "insumos_novos": len(new_ins) - len(cat_insumos),
        "producoes_novas": len(new_prod) - len(cat_producoes),
    }


def _impl_comparar_rfi_catalogo(
    contexto_id: str,
    dry_run: bool = True,
) -> dict[str, Any]:
    """Compara o catálogo com a PLANILHA PADRÃO RFI e retorna relatório estruturado.

    Útil para o agente iterar sobre divergências antes de aplicar o merge.
    Retorna INNER_HIGH (matches confiantes), INNER_LOW (colisões), RIGHT_ONLY (novos).

    Args:
        contexto_id: ID do contexto (ex.: "mendeslobo").
        dry_run: Se True (padrão), não altera nada. Se False, aplica o merge.
    """
    import importlib.util

    config_dir = _config_root()
    tools_dir = config_dir.parents[1] / "tools"
    merge_path = tools_dir / "merge_rfi.py"

    if not merge_path.exists():
        return {"erro": f"merge_rfi.py não encontrado em {tools_dir}"}

    try:
        import openpyxl
    except ImportError:
        return {"erro": "openpyxl não instalado — execute: uv add openpyxl"}

    spec = importlib.util.spec_from_file_location("merge_rfi", merge_path)
    assert spec is not None and spec.loader is not None
    raw_mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(raw_mod)
    mod = cast("_MergeRfiModule", raw_mod)

    bundle_path = config_dir / "catalogos" / contexto_id / ".catalog_bundle.json"
    if not bundle_path.exists():
        return {"erro": f"Bundle não encontrado: {bundle_path}"}

    bundle = json.loads(bundle_path.read_text(encoding="utf-8"))
    cat_insumos = bundle.get("insumos", [])
    cat_producoes = bundle.get("producoes", []) or bundle.get("produtividades", [])

    if not mod.XLSM.exists():
        return {"erro": f"Planilha RFI não encontrada: {mod.XLSM}"}

    wb = openpyxl.load_workbook(mod.XLSM, data_only=True, keep_vba=False)
    rfi = mod.extract_rfi(wb)
    wb.close()

    rep_ins, _ = mod._merge_entities(cat_insumos, rfi["insumos"])
    rep_prod, _ = mod._merge_entities(cat_producoes, rfi["producoes"], id_key="id")

    result = _build_comparar_rfi_result(dry_run, contexto_id, cat_insumos, cat_producoes, rfi, rep_ins, rep_prod)

    if not dry_run:
        _apply_rfi_merge(mod, bundle, bundle_path, cat_insumos, cat_producoes, rfi, rep_ins, rep_prod, result)

    return _wrap_response(result)


def _impl_calcular_pu_producao(
    contexto_id: str,
    producao_id: str,
    alpha_clt: float = 1.777,
    alpha_pj: float = 1.06,
    preco_diesel: float = 6.50,
    horas_mes: float = 208.0,
) -> dict[str, Any]:
    """Calcula o Preço Unitário teórico de uma produção a partir da composição.

    PU = custo_total_horario / producao.valor_horario
    Verifica integridade referencial (insumos existem?) e retorna breakdown.

    Args:
        contexto_id: ID do contexto.
        producao_id: ID da produção (ex.: "ATI-011").
        alpha_clt: Fator de encargos CLT (default 1.777).
        alpha_pj: Fator de encargos PJ (default 1.06).
        preco_diesel: Preço do diesel R$/L (default 6.50).
        horas_mes: Horas produtivas/mês (default 208 — regime 6×8h).
    """
    from concilium.application.catalog.pu_calculator import ParametrosCalculo, calcular_pu

    config_dir = _config_root()
    bundle_path = config_dir / "catalogos" / contexto_id / ".catalog_bundle.json"
    if not bundle_path.exists():
        return {"erro": f"Bundle não encontrado: {bundle_path}"}

    bundle = json.loads(bundle_path.read_text(encoding="utf-8"))
    insumos = bundle.get("insumos", [])
    producoes = bundle.get("producoes", []) or bundle.get("produtividades", [])

    prod = next((p for p in producoes if p.get("id") == producao_id or p.get("codigo") == producao_id), None)
    if prod is None:
        return {"erro": f"Produção '{producao_id}' não encontrada no catálogo."}

    insumo_index = {ins["codigo"]: ins for ins in insumos if ins.get("codigo")}
    params = ParametrosCalculo(
        alpha_clt=alpha_clt,
        alpha_pj=alpha_pj,
        preco_diesel=preco_diesel,
        horas_mes=horas_mes,
    )
    resultado = calcular_pu(prod, insumo_index, params)
    return _wrap_response(resultado.to_dict())


def _impl_avaliar_plausibilidade_catalogo(
    contexto_id: str,
) -> dict[str, Any]:
    """Avalia plausibilidade física e estatística dos dados do catálogo.

    Detecta outliers estatísticos (z-score), violações físicas (consumo diesel × potência CV,
    salário abaixo do mínimo legal, encargos fora do range), duplicatas, dados desatualizados
    e composições incompletas.

    Args:
        contexto_id: ID do contexto (ex.: "mendeslobo").
    """
    from concilium.application.catalog.plausibility_checker import verificar_plausibilidade

    config_dir = _config_root()
    bundle_path = config_dir / "catalogos" / contexto_id / ".catalog_bundle.json"
    if not bundle_path.exists():
        return {"erro": f"Bundle não encontrado: {bundle_path}"}

    bundle = json.loads(bundle_path.read_text(encoding="utf-8"))
    insumos = bundle.get("insumos", [])
    producoes = bundle.get("producoes", []) or bundle.get("produtividades", [])
    cpus = bundle.get("cpus", [])

    resultado = verificar_plausibilidade(insumos, producoes, cpus)
    return _wrap_response(resultado)


def _cpu_refs_faltantes(cpus: list[dict], insumos: list[dict]) -> list[dict]:
    """Referências de CPU → Insumo (composicao_itens) que não existem no catálogo."""
    insumo_codigos = {ins["codigo"] for ins in insumos if ins.get("codigo")}
    faltantes: list[dict] = []
    for cpu in cpus:
        for item in cpu.get("composicao_itens", []):
            iid = item.get("insumo_id", "")
            if iid and iid not in insumo_codigos:
                faltantes.append({"cpu": cpu.get("codigo"), "insumo_id_faltante": iid})
    return faltantes


def _cpu_prod_faltantes(cpus: list[dict], producoes: list[dict]) -> list[dict]:
    """Referências de CPU → Producao que não existem no catálogo."""
    prod_ids = {p.get("id") for p in producoes if p.get("id")}
    faltantes: list[dict] = []
    for cpu in cpus:
        pid = cpu.get("producao_id_ref")
        if pid and pid not in prod_ids:
            faltantes.append({"cpu": cpu.get("codigo"), "producao_id_ref": pid})
    return faltantes


def _build_problemas_integridade(
    pu_result: dict[str, Any], cpu_refs_faltantes: list[dict], cpu_prod_faltantes: list[dict]
) -> list[dict]:
    """Consolida os problemas de integridade categorizados por severidade."""
    problemas: list[dict] = []
    for r in pu_result["referencias_faltantes"]:
        problemas.append({"severidade": "ERRO", "tipo": "REF_INSUMO_FALTANTE", **r})
    for r in pu_result["pu_divergentes"]:
        problemas.append({"severidade": "AVISO", "tipo": "PU_DIVERGENTE", **r})
    for r in cpu_refs_faltantes:
        problemas.append({"severidade": "ERRO", "tipo": "CPU_INSUMO_FALTANTE", **r})
    for r in cpu_prod_faltantes:
        problemas.append({"severidade": "AVISO", "tipo": "CPU_PROD_REF_FALTANTE", **r})
    return problemas


def _rfi_pendentes_section(rfi_insumos: list[dict], rfi_producoes: list[dict]) -> dict[str, Any]:
    """Monta a seção rfi_pendentes do relatório de integridade."""
    return {
        "insumos": [{"codigo": i.get("codigo"), "descricao": i.get("descricao", "")[:50]} for i in rfi_insumos[:20]],
        "producoes": [{"id": p.get("id"), "descricao": p.get("descricao", "")[:50]} for p in rfi_producoes[:20]],
        "nota": "Entradas RFI- são colisões de código importadas — revisar e renomear se necessário.",
    }


def _build_integridade_resumo(
    insumos: list, producoes: list, cpus: list, pu_result: dict, problemas: list, rfi_insumos: list, rfi_producoes: list
) -> dict:
    """Monta a seção `resumo` do relatório de integridade do catálogo."""
    return {
        "total_insumos": len(insumos),
        "total_producoes": len(producoes),
        "total_cpus": len(cpus),
        "producoes_com_composicao": pu_result["com_composicao"],
        "erros": sum(1 for p in problemas if p["severidade"] == "ERRO"),
        "avisos": sum(1 for p in problemas if p["severidade"] == "AVISO"),
        "insumos_rfi_pendentes": len(rfi_insumos),
        "producoes_rfi_pendentes": len(rfi_producoes),
    }


def _build_integridade_response(
    contexto_id: str,
    insumos: list,
    producoes: list,
    cpus: list,
    pu_result: dict,
    problemas: list,
    rfi_insumos: list,
    rfi_producoes: list,
) -> dict:
    """Monta a resposta completa de verificar_integridade_catalogo."""
    return {
        "contexto_id": contexto_id,
        "ok": not any(p["severidade"] == "ERRO" for p in problemas),
        "resumo": _build_integridade_resumo(insumos, producoes, cpus, pu_result, problemas, rfi_insumos, rfi_producoes),
        "problemas": problemas[:50],
        "rfi_pendentes": _rfi_pendentes_section(rfi_insumos, rfi_producoes),
    }


def _impl_verificar_integridade_catalogo(
    contexto_id: str,
    alpha_clt: float = 1.777,
    alpha_pj: float = 1.06,
    preco_diesel: float = 6.50,
) -> dict[str, Any]:
    """Verifica integridade completa do catálogo: schema + referências + consistência de PU.

    Retorna lista de problemas encontrados categorizados por severidade.
    Ideal para loop de iteração do agente após merge ou edição de catálogo.

    Args:
        contexto_id: ID do contexto.
        alpha_clt: Fator de encargos CLT (default 1.777).
        alpha_pj: Fator de encargos PJ (default 1.06).
        preco_diesel: Preço do diesel R$/L para cálculo de PU.
    """
    from concilium.application.catalog.pu_calculator import ParametrosCalculo, calcular_catalogo

    config_dir = _config_root()
    bundle_path = config_dir / "catalogos" / contexto_id / ".catalog_bundle.json"
    if not bundle_path.exists():
        return {"erro": f"Bundle não encontrado: {bundle_path}"}

    bundle = json.loads(bundle_path.read_text(encoding="utf-8"))
    insumos = bundle.get("insumos", [])
    producoes = bundle.get("producoes", []) or bundle.get("produtividades", [])
    cpus = bundle.get("cpus", [])

    params = ParametrosCalculo(alpha_clt=alpha_clt, alpha_pj=alpha_pj, preco_diesel=preco_diesel)

    # 1. Integridade referencial + PU
    pu_result = calcular_catalogo(producoes, insumos, params)

    # 2. Referências de CPU → Insumo (composicao_itens)
    cpu_refs_faltantes = _cpu_refs_faltantes(cpus, insumos)

    # 3. Referências de CPU → Producao
    cpu_prod_faltantes = _cpu_prod_faltantes(cpus, producoes)

    # 4. Insumos RFI importados sem referências (prefixados RFI-)
    rfi_insumos = [ins for ins in insumos if (ins.get("codigo") or "").startswith("RFI-")]
    rfi_producoes = [p for p in producoes if (p.get("id") or "").startswith("RFI-")]

    problemas = _build_problemas_integridade(pu_result, cpu_refs_faltantes, cpu_prod_faltantes)

    return _wrap_response(
        _build_integridade_response(
            contexto_id, insumos, producoes, cpus, pu_result, problemas, rfi_insumos, rfi_producoes
        )
    )
