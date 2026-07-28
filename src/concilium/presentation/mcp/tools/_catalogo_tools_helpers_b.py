"""MCP catalogo tool implementations — Part B."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from concilium.presentation.mcp._context import _config_root, _wrap_response


def _catalog_root(config_dir: Path, catalogo_id: str) -> Path:
    return config_dir / "catalogos" / catalogo_id


def _resolve_catalogo_id(config_dir: Path, contexto_id: str) -> str:
    """Resolve contexto_id -> catalogo_id (podem divergir, ex.: mendeslobo-rfi -> rfi-r02).

    Fallback: contexto_id, quando o contexto não existe ou não tem catalogo_id
    (contextos antigos onde catalogo_id == id continuam funcionando).
    """
    contexto_file = config_dir / "contextos" / f"{contexto_id}.json"
    if not contexto_file.exists():
        return contexto_id
    try:
        data = json.loads(contexto_file.read_text(encoding="utf-8"))
    except Exception:
        return contexto_id
    return str(data.get("catalogo_id") or contexto_id)


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
    bundle_path = _catalog_root(config_dir, _resolve_catalogo_id(config_dir, contexto_id)) / ".catalog_bundle.json"
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


# ═══════════════════════════════════════════════════════════════════════════════
# comparar_catalogo / mesclar_catalogo (issue #134) — agnósticos de fonte: cada
# origem pode ser um catálogo (catalogo_id) ou uma planilha PLANILHA PADRÃO RFI
# (.xlsm/.xlsx). Motor de comparação/merge + resolução de fonte compartilhados com
# os comandos CLI equivalentes (`catalog compare`/`catalog merge`) via
# concilium.application.services.catalog.catalog_compare — aqui só a tradução para
# o formato de resposta MCP ({"erro": ...} em vez de typer.Exit) é específica.
# ═══════════════════════════════════════════════════════════════════════════════


def _cc_resolver_tipos(tipo: str) -> list[str]:
    from concilium.application.services.catalog.catalog_compare import resolver_tipos

    return resolver_tipos(tipo)


def _cc_resolver_fonte(origem: str) -> dict[str, list[dict]]:
    from concilium.application.services.catalog.catalog_compare import resolver_fonte_entidades
    from concilium.presentation.mcp._context import _runtime

    rt = _runtime()
    repo_root = rt.config_root.parent
    return resolver_fonte_entidades(origem, rt, repo_root)


def _cc_amostra_deltas(inner_high: list) -> list:
    return [
        {"id": i["catalog"].get("codigo") or i["catalog"].get("id"), "delta": i["delta"]}
        for i in inner_high
        if i["delta"]
    ][:20]


def _cc_amostra_colisoes(inner_low: list) -> list:
    return [
        {
            "base_id": i["catalog"].get("codigo") or i["catalog"].get("id"),
            "base_descricao": i["catalog"].get("descricao", "")[:60],
            "origem_id": i["rfi"].get("codigo") or i["rfi"].get("id"),
            "origem_descricao": i["rfi"].get("descricao", "")[:60],
            "score": i["score"],
        }
        for i in inner_low
    ]


def _cc_amostra_novos(right_only: list) -> list:
    return [
        {
            "id": i["rfi"].get("codigo") or i["rfi"].get("id"),
            "descricao": i["rfi"].get("descricao", "")[:60],
            "unidade": i["rfi"].get("unidade"),
        }
        for i in right_only
    ][:30]


def _cc_sumarizar_relatorio(rep: Any) -> dict:
    """Sumariza um RelatorioComparacao (por tipo de entidade) para a resposta MCP."""
    return {
        "inner_high": len(rep.inner_high),
        "inner_high_com_delta": sum(1 for i in rep.inner_high if i["delta"]),
        "inner_low": len(rep.inner_low),
        "right_only": len(rep.right_only),
        "left_only": len(rep.left_only),
        "deltas_amostra": _cc_amostra_deltas(rep.inner_high),
        "colisoes": _cc_amostra_colisoes(rep.inner_low),
        "novos": _cc_amostra_novos(rep.right_only),
    }


def _impl_comparar_catalogo(
    origem_a: str,
    origem_b: str,
    tipo: str = "todos",
) -> dict[str, Any]:
    """Compara duas fontes de entidades de catálogo e retorna relatório estruturado.

    Útil para o agente iterar sobre divergências antes de aplicar um merge.
    Retorna INNER_HIGH (matches confiantes), INNER_LOW (colisões), RIGHT_ONLY (só em
    origem_b), LEFT_ONLY (só em origem_a) — sempre dry-run, este tool nunca escreve nada.

    Args:
        origem_a: Catálogo (catalogo_id, ex.: "mendeslobo") ou caminho de planilha .xlsm/.xlsx.
        origem_b: Catálogo (catalogo_id) ou caminho de planilha .xlsm/.xlsx.
        tipo: insumos | producoes | cpus | todos (padrão).
    """
    from concilium.application.services.catalog.catalog_compare import eh_planilha, gerar_relatorios

    try:
        tipos = _cc_resolver_tipos(tipo)
    except ValueError as exc:
        return {"erro": str(exc)}

    aviso = None
    if "cpus" in tipos and (eh_planilha(origem_a) or eh_planilha(origem_b)):
        aviso = "cpus: pulado — planilha RFI não modela esse tipo de entidade."
        tipos = [t for t in tipos if t != "cpus"]
    if not tipos:
        return {"erro": "Nenhum tipo válido para comparar."}

    try:
        fonte_a = _cc_resolver_fonte(origem_a)
        fonte_b = _cc_resolver_fonte(origem_b)
    except RuntimeError as exc:
        return {"erro": str(exc)}

    relatorios = gerar_relatorios(fonte_a, fonte_b, tipos)

    result: dict[str, Any] = {
        "origem_a": origem_a,
        "origem_b": origem_b,
        "tamanho_origem_a": {t: len(fonte_a.get(t, [])) for t in tipos},
        "tamanho_origem_b": {t: len(fonte_b.get(t, [])) for t in tipos},
        **{t: _cc_sumarizar_relatorio(rep) for t, rep in relatorios.items()},
        "resumo": {
            "atualizacoes": sum(sum(1 for i in rep.inner_high if i["delta"]) for rep in relatorios.values()),
            "novos_total": sum(len(rep.right_only) for rep in relatorios.values()),
            "colisoes_total": sum(len(rep.inner_low) for rep in relatorios.values()),
        },
    }
    if aviso:
        result["aviso"] = aviso
    return _wrap_response(result)


def _impl_mesclar_catalogo(
    destino: str,
    origem: str,
    dry_run: bool = True,
    tipo: str = "todos",
) -> dict[str, Any]:
    """Mescla uma fonte de origem (catálogo ou planilha RFI) no catálogo de destino.

    dry_run=True (padrão) só calcula o relatório de comparação — nada é escrito.
    dry_run=False escreve direto no `.catalog_bundle.json` do destino (mesma mecânica
    do antigo comparar_rfi_catalogo(dry_run=False) — issue #134 não resolve a
    governança de escrita direta em catálogo, ver ADR-145).

    Args:
        destino: Catálogo de destino (catalogo_id) — precisa ser um catálogo, não planilha.
        origem: Catálogo (catalogo_id) ou caminho de planilha .xlsm/.xlsx de origem.
        dry_run: Se True (padrão), não altera nada. Se False, aplica o merge.
        tipo: insumos | producoes | cpus | todos (padrão).
    """
    from concilium.application.services.catalog.catalog_compare import (
        ID_KEYS,
        aplicar_merge,
        eh_planilha,
        gerar_relatorios,
    )
    from concilium.presentation.mcp._context import _runtime

    if eh_planilha(destino):
        return {"erro": "Destino do merge precisa ser um catálogo — não é possível escrever em uma planilha."}

    try:
        tipos = _cc_resolver_tipos(tipo)
    except ValueError as exc:
        return {"erro": str(exc)}

    aviso = None
    if "cpus" in tipos and eh_planilha(origem):
        aviso = "cpus: pulado — planilha RFI não modela esse tipo de entidade."
        tipos = [t for t in tipos if t != "cpus"]
    if not tipos:
        return {"erro": "Nenhum tipo válido para mesclar."}

    try:
        fonte_destino = _cc_resolver_fonte(destino)
        fonte_origem = _cc_resolver_fonte(origem)
    except RuntimeError as exc:
        return {"erro": str(exc)}

    relatorios = gerar_relatorios(fonte_destino, fonte_origem, tipos)

    result: dict[str, Any] = {
        "mode": "DRY_RUN" if dry_run else "APPLIED",
        "destino": destino,
        "origem": origem,
        **{t: _cc_sumarizar_relatorio(rep) for t, rep in relatorios.items()},
        "resumo": {
            "atualizacoes": sum(sum(1 for i in rep.inner_high if i["delta"]) for rep in relatorios.values()),
            "novos_total": sum(len(rep.right_only) for rep in relatorios.values()),
            "colisoes_total": sum(len(rep.inner_low) for rep in relatorios.values()),
        },
    }
    if aviso:
        result["aviso"] = aviso

    if not dry_run:
        from concilium.application.services.catalog.catalog_compare import resolver_catalogo_id

        rt = _runtime()
        catalogo_id = resolver_catalogo_id(rt, destino)
        bundle = rt.load_catalogo(catalogo_id)
        bundle_path = rt.config_root / "catalogos" / catalogo_id / ".catalog_bundle.json"
        aplicado: dict[str, Any] = {}
        for t in tipos:
            merged = aplicar_merge(fonte_destino.get(t, []), fonte_origem.get(t, []), relatorios[t], id_key=ID_KEYS[t])
            if t == "producoes" and "producoes" not in bundle:
                bundle["produtividades"] = merged
            else:
                bundle[t] = merged
            aplicado[t] = {"total": len(merged), "era": len(fonte_destino.get(t, []))}
        bundle_path.write_text(json.dumps(bundle, indent=2, ensure_ascii=False), encoding="utf-8")
        result["aplicado"] = aplicado

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
    bundle_path = _catalog_root(config_dir, _resolve_catalogo_id(config_dir, contexto_id)) / ".catalog_bundle.json"
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
    bundle_path = _catalog_root(config_dir, _resolve_catalogo_id(config_dir, contexto_id)) / ".catalog_bundle.json"
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
    bundle_path = _catalog_root(config_dir, _resolve_catalogo_id(config_dir, contexto_id)) / ".catalog_bundle.json"
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
