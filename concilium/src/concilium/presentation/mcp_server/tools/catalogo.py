"""Ferramentas MCP de Catálogo — Simplificadas (ADR-037)."""

from __future__ import annotations

import json
from datetime import date
from pathlib import Path
from typing import Any

from mcp.server.fastmcp import FastMCP

from concilium.application.orchestrators.catalog_governance import (
    CatalogGovernanceError,
    collect_catalog_critical_errors,
    validate_and_resolve_insumo_file,
    validate_and_resolve_producao_file,
)
from concilium.presentation.mcp_server._context import _config_root, _projetos_root, _runtime, _wrap_response


def _catalog_root(config_dir: Path, catalogo_id: str) -> Path:
    return config_dir / "catalogos" / catalogo_id


def register(server: FastMCP) -> None:
    """Registra as ferramentas consolidadas de catálogo."""

    @server.tool()
    def listar_contextos() -> dict[str, Any]:
        """Lista os contextos estratégicos disponíveis (ex: mendeslobo, bbid, etc)."""
        rt = _runtime()
        contextos_dir = _config_root() / "contextos"
        if not contextos_dir.exists():
            return {"contextos": []}

        contextos = []
        for p in sorted(contextos_dir.glob("*.json")):
            ctx = rt.load_contexto(p.stem)
            raw = json.loads(p.read_text(encoding="utf-8"))
            contextos.append(
                {
                    "id": ctx.id,
                    "nome": raw.get("nome", ctx.id),
                    "descricao": raw.get("descricao", raw.get("$comment", "")),
                }
            )
        return _wrap_response({"contextos": contextos})

    @server.tool()
    def pesquisar_catalogo(
        contexto_id: str,
        query: str | None = None,
        tipo_obra: str | None = None,
        limite: int = 20,
    ) -> dict[str, Any]:
        """Pesquisa inteligente no catálogo: busca CPUs ou sugere EAP (templates).

        Args:
            contexto_id: ID do contexto (ex.: "mendeslobo").
            query: Opcional. Termo de busca para CPUs (ex: "Aterro").
            tipo_obra: Opcional. Se informado, retorna a EAP sugerida para este tipo
                (terraplenagem, pavimentacao, saneamento).
            limite: Máximo de resultados para busca textual (padrão 20).
        """
        rt = _runtime()
        try:
            ctx = rt.load_contexto(contexto_id)
            catalogo = rt.load_catalogo(ctx.catalogo_id)
        except Exception as e:
            return {"erro": str(e)}

        result: dict[str, Any] = {"contexto_id": contexto_id, "catalogo_id": ctx.catalogo_id}
        cpus_lookup = {cpu.get("codigo"): cpu for cpu in catalogo.get("cpus", [])}

        # 1. Templates de EAP (ADR-014)
        if tipo_obra:
            tipo_upper = tipo_obra.upper()
            for tmpl in catalogo.get("templates", []):
                if tmpl.get("tipo_obra", "").upper() == tipo_upper:
                    servicos = []
                    for s in tmpl.get("servicos_sugeridos", []):
                        cid = s.get("cpu_id")
                        cpu = cpus_lookup.get(cid, {})
                        servicos.append(
                            {
                                "cpu_id": cid,
                                "descricao": cpu.get("descricao", cid),
                                "unidade": cpu.get("unidade", ""),
                                "obrigatoriedade": s.get("obrigatoriedade", "tipico"),
                            }
                        )
                    result["eap_sugerida"] = servicos
                    break

        # 2. Busca Textual
        if query:
            query_norm = query.lower()
            matches = []
            for cpu in catalogo.get("cpus", []):
                cod = str(cpu.get("codigo", "")).lower()
                desc = str(cpu.get("descricao", "")).lower()
                if query_norm in cod or query_norm in desc:
                    matches.append(
                        {
                            "cpu_id": cpu.get("codigo"),
                            "descricao": cpu.get("descricao"),
                            "unidade": cpu.get("unidade"),
                            "categoria": cpu.get("categoria"),
                        }
                    )
                    if len(matches) >= limite:
                        break
            result["busca_resultados"] = matches

        return _wrap_response(result)

    @server.tool()
    def consultar_saude_catalogo(contexto_id: str) -> dict[str, Any]:
        """Audita o catálogo em busca de erros de governança (ADR-035).

        Verifica integridade de CPUs, insumos e produção. Útil para debugar bloqueios de pipeline.
        """
        rt = _runtime()
        try:
            ctx = rt.load_contexto(contexto_id)
            catalogo = rt.load_catalogo(ctx.catalogo_id)
        except Exception as e:
            return {"erro": str(e)}

        erros = collect_catalog_critical_errors(catalogo)

        return _wrap_response(
            {
                "contexto_id": contexto_id,
                "catalogo_id": ctx.catalogo_id,
                "status": "SAUDAVEL" if not erros else "DEGRADADO",
                "erros_criticos": erros,
                "total_cpus": len(catalogo.get("cpus", [])),
            }
        )

    @server.tool()
    def atualizar_preco_insumo(
        contexto_id: str,
        insumo_id: str,
        novo_preco: float,
        projeto_id: str | None = None,
        jurisdicao_id: str | None = None,
        nota: str | None = None,
    ) -> dict[str, Any]:
        """Atualiza o preço de um insumo (Base ou Regional).

        Se projeto_id for informado, a alteração é salva como um 'override' local do projeto,
        sem afetar o catálogo mestre corporativo (ADR-038).

        Args:
            contexto_id: ID do contexto (mendeslobo).
            insumo_id: Código do insumo.
            novo_preco: O valor atualizado.
            projeto_id: Opcional. Se informado, salva apenas para este projeto.
            jurisdicao_id: Opcional. Região específica.
            nota: Opcional. Justificativa.
        """
        rt = _runtime()
        config_dir = _config_root()
        projects_dir = _projetos_root()

        ctx = rt.load_contexto(contexto_id)
        try:
            insumo_file = validate_and_resolve_insumo_file(
                _catalog_root(config_dir, ctx.catalogo_id),
                insumo_id,
                novo_preco,
            )
        except CatalogGovernanceError as exc:
            return {"erro": str(exc)}

        if projeto_id:
            # Camada de Projeto (Project Layer Overrides)
            proj_path = projects_dir / projeto_id
            if not proj_path.exists():
                return {"erro": f"Projeto {projeto_id} não encontrado."}

            overrides_file = proj_path / "overrides" / "catalog_prices.json"
            overrides_file.parent.mkdir(parents=True, exist_ok=True)

            try:
                overrides = {}
                if overrides_file.exists():
                    overrides = json.loads(overrides_file.read_text(encoding="utf-8"))

                key = f"{insumo_id}::{jurisdicao_id or 'BASE'}"
                overrides[key] = {
                    "preco": novo_preco,
                    "nota": nota or "Calibração local de projeto",
                    "jurisdicao": jurisdicao_id,
                }

                overrides_file.write_text(json.dumps(overrides, indent=2, ensure_ascii=False), encoding="utf-8")
                return _wrap_response(
                    {"status": "SUCESSO", "layer": "PROJETO", "projeto_id": projeto_id, "insumo": insumo_id}
                )
            except Exception as e:
                return {"erro": f"Erro ao salvar override de projeto: {e}"}

        # Camada Master (Master Layer)
        try:
            data = json.loads(insumo_file.read_text(encoding="utf-8"))
            if jurisdicao_id:
                if "regionalizacao" not in data:
                    data["regionalizacao"] = {}
                data["regionalizacao"][jurisdicao_id] = {"preco": novo_preco, "nota": nota}
            else:
                data["preco_unitario"] = novo_preco
                if nota:
                    data["nota_calibracao"] = nota

            insumo_file.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
            return _wrap_response({"status": "SUCESSO", "layer": "MASTER", "insumo_id": insumo_id})
        except Exception as e:
            return {"erro": f"Falha ao persistir no mestre: {e}"}

    @server.tool()
    def consultar_preco_insumo_temporal(
        contexto_id: str,
        insumo_id: str,
        data_referencia: str,
        projeto_id: str | None = None,
        jurisdicao_id: str | None = None,
    ) -> dict[str, Any]:
        """Consulta preço de insumo em data de referência com rastreabilidade de fonte (ADR-041).

        Args:
            contexto_id: ID do contexto (ex.: mendeslobo).
            insumo_id: Código do insumo.
            data_referencia: Data de arbitragem (YYYY-MM-DD).
            projeto_id: Opcional. Se informado, aplica layer de overrides do projeto (ADR-040).
            jurisdicao_id: Opcional. Região para fallback SICRO regional.
        """
        from concilium.infrastructure.repositories.insumo import RepositorioInsumo

        rt = _runtime()
        projects_dir = _projetos_root()

        try:
            dt_ref = date.fromisoformat(data_referencia)
        except ValueError:
            return {"erro": f"data_referencia inválida: {data_referencia}. Use YYYY-MM-DD."}

        try:
            ctx = rt.load_contexto(contexto_id)
            catalogo = rt.load_catalogo(ctx.catalogo_id)
        except Exception as e:
            return {"erro": str(e)}

        repo = RepositorioInsumo(catalogo)

        overrides: dict[str, Any] | None = None
        if projeto_id:
            proj_path = projects_dir / projeto_id
            if not proj_path.exists():
                return {"erro": f"Projeto {projeto_id} não encontrado."}
            overrides_file = proj_path / "overrides" / "insumos_override.json"
            if overrides_file.exists():
                try:
                    raw = json.loads(overrides_file.read_text(encoding="utf-8"))
                    if isinstance(raw, dict):
                        overrides = raw
                except Exception:
                    overrides = None

        preco, fonte = repo.resolver_preco(
            insumo_id,
            jurisdicao_id=jurisdicao_id,
            overrides=overrides,
            data_referencia=dt_ref,
        )

        return _wrap_response(
            {
                "status": "SUCESSO",
                "contexto_id": contexto_id,
                "catalogo_id": ctx.catalogo_id,
                "insumo_id": insumo_id,
                "data_referencia": dt_ref.isoformat(),
                "preco_unitario": preco,
                "fonte_preco": fonte,
                "projeto_id": projeto_id,
                "jurisdicao_id": jurisdicao_id,
            }
        )

    @server.tool()
    def adicionar_variante_producao(
        contexto_id: str,
        producao_id: str,
        variante_id: str,
        nome_variante: str,
        valor_horario: float,
        equipe_json: str,
        projeto_id: str | None = None,
    ) -> dict[str, Any]:
        """Adiciona ou atualiza uma variante de produtividade (Master ou Projeto).

        Args:
            contexto_id: ID do contexto.
            producao_id: ID da metodologia.
            variante_id: ID único da variante.
            nome_variante: Nome legível.
            valor_horario: Produtividade benchmark.
            equipe_json: String JSON com a composição.
            projeto_id: Opcional. Se informado, salva como override local do projeto.
        """
        rt = _runtime()
        config_dir = _config_root()
        projects_dir = _projetos_root()

        try:
            equipe_data = json.loads(equipe_json)

            if projeto_id:
                # Camada de Projeto
                proj_path = projects_dir / projeto_id
                if not proj_path.exists():
                    return {"erro": f"Projeto {projeto_id} não encontrado."}

                overrides_file = proj_path / "overrides" / "production_variants.json"
                overrides_file.parent.mkdir(parents=True, exist_ok=True)

                overrides = {}
                if overrides_file.exists():
                    overrides = json.loads(overrides_file.read_text(encoding="utf-8"))

                key = f"{producao_id}::{variante_id}"
                overrides[key] = {"nome": nome_variante, "valor_horario": valor_horario, "equipe": equipe_data}
                overrides_file.write_text(json.dumps(overrides, indent=2, ensure_ascii=False), encoding="utf-8")
                return _wrap_response(
                    {"status": "SUCESSO", "layer": "PROJETO", "projeto_id": projeto_id, "producao": producao_id}
                )

            # Camada Master
            ctx = rt.load_contexto(contexto_id)
            try:
                prod_file = validate_and_resolve_producao_file(
                    _catalog_root(config_dir, ctx.catalogo_id),
                    producao_id,
                    valor_horario,
                )
            except CatalogGovernanceError as exc:
                return {"erro": str(exc)}

            data = json.loads(prod_file.read_text(encoding="utf-8"))
            if "variantes" not in data:
                data["variantes"] = []
            data["variantes"] = [v for v in data["variantes"] if v["id"] != variante_id]
            data["variantes"].append(
                {"id": variante_id, "nome": nome_variante, "valor_horario": valor_horario, "equipe": equipe_data}
            )
            prod_file.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
            return _wrap_response({"status": "SUCESSO", "layer": "MASTER", "producao_id": producao_id})
        except Exception as e:
            return {"erro": f"Erro ao adicionar variante: {e}"}

    # ── Ferramentas de Merge RFI + Integridade ────────────────────────────────

    @server.tool()
    def tendencia_precos_catalogo(
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

    @server.tool()
    def comparar_rfi_catalogo(
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
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)  # type: ignore[union-attr]

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

        def _summarize(rep: Any) -> dict:
            return {
                "inner_high": len(rep.inner_high),
                "inner_high_com_delta": sum(1 for i in rep.inner_high if i["delta"]),
                "inner_low": len(rep.inner_low),
                "right_only": len(rep.right_only),
                "left_only": len(rep.left_only),
                "deltas_amostra": [
                    {
                        "codigo": i["catalog"].get("codigo") or i["catalog"].get("id"),
                        "delta": i["delta"],
                    }
                    for i in rep.inner_high
                    if i["delta"]
                ][:20],
                "colisoes": [
                    {
                        "cat_codigo": i["catalog"].get("codigo") or i["catalog"].get("id"),
                        "cat_descricao": i["catalog"].get("descricao", "")[:60],
                        "rfi_codigo": i["rfi"].get("codigo") or i["rfi"].get("id"),
                        "rfi_descricao": i["rfi"].get("descricao", "")[:60],
                        "score": i["score"],
                        "acao": f"RFI-{i['rfi'].get('codigo') or i['rfi'].get('id')} será criado",
                    }
                    for i in rep.inner_low
                ],
                "novos": [
                    {
                        "codigo": i["rfi"].get("codigo") or i["rfi"].get("id"),
                        "descricao": i["rfi"].get("descricao", "")[:60],
                        "unidade": i["rfi"].get("unidade"),
                    }
                    for i in rep.right_only
                ][:30],
            }

        result = {
            "mode": "DRY_RUN" if dry_run else "APPLIED",
            "contexto_id": contexto_id,
            "catalogo_atual": {"insumos": len(cat_insumos), "producoes": len(cat_producoes)},
            "rfi": {"insumos": len(rfi["insumos"]), "producoes": len(rfi["producoes"])},
            "insumos": _summarize(rep_ins),
            "producoes": _summarize(rep_prod),
            "resumo": {
                "atualizacoes_preco": sum(1 for i in rep_ins.inner_high if i["delta"]),
                "novos_total": len(rep_ins.right_only) + len(rep_prod.right_only),
                "colisoes_total": len(rep_ins.inner_low) + len(rep_prod.inner_low),
            },
        }

        if not dry_run:
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

        return _wrap_response(result)

    @server.tool()
    def calcular_pu_producao(
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

    @server.tool()
    def avaliar_plausibilidade_catalogo(
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

    @server.tool()
    def verificar_integridade_catalogo(
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
        insumo_codigos = {ins["codigo"] for ins in insumos if ins.get("codigo")}
        cpu_refs_faltantes: list[dict] = []
        for cpu in cpus:
            for item in cpu.get("composicao_itens", []):
                iid = item.get("insumo_id", "")
                if iid and iid not in insumo_codigos:
                    cpu_refs_faltantes.append({"cpu": cpu.get("codigo"), "insumo_id_faltante": iid})

        # 3. Referências de CPU → Producao
        prod_ids = {p.get("id") for p in producoes if p.get("id")}
        cpu_prod_faltantes: list[dict] = []
        for cpu in cpus:
            pid = cpu.get("producao_id_ref")
            if pid and pid not in prod_ids:
                cpu_prod_faltantes.append({"cpu": cpu.get("codigo"), "producao_id_ref": pid})

        # 4. Insumos RFI importados sem referências (prefixados RFI-)
        rfi_insumos = [ins for ins in insumos if (ins.get("codigo") or "").startswith("RFI-")]
        rfi_producoes = [p for p in producoes if (p.get("id") or "").startswith("RFI-")]

        problemas: list[dict] = []
        for r in pu_result["referencias_faltantes"]:
            problemas.append({"severidade": "ERRO", "tipo": "REF_INSUMO_FALTANTE", **r})
        for r in pu_result["pu_divergentes"]:
            problemas.append({"severidade": "AVISO", "tipo": "PU_DIVERGENTE", **r})
        for r in cpu_refs_faltantes:
            problemas.append({"severidade": "ERRO", "tipo": "CPU_INSUMO_FALTANTE", **r})
        for r in cpu_prod_faltantes:
            problemas.append({"severidade": "AVISO", "tipo": "CPU_PROD_REF_FALTANTE", **r})

        return _wrap_response(
            {
                "contexto_id": contexto_id,
                "ok": not any(p["severidade"] == "ERRO" for p in problemas),
                "resumo": {
                    "total_insumos": len(insumos),
                    "total_producoes": len(producoes),
                    "total_cpus": len(cpus),
                    "producoes_com_composicao": pu_result["com_composicao"],
                    "erros": sum(1 for p in problemas if p["severidade"] == "ERRO"),
                    "avisos": sum(1 for p in problemas if p["severidade"] == "AVISO"),
                    "insumos_rfi_pendentes": len(rfi_insumos),
                    "producoes_rfi_pendentes": len(rfi_producoes),
                },
                "problemas": problemas[:50],
                "rfi_pendentes": {
                    "insumos": [
                        {"codigo": i.get("codigo"), "descricao": i.get("descricao", "")[:50]} for i in rfi_insumos[:20]
                    ],
                    "producoes": [
                        {"id": p.get("id"), "descricao": p.get("descricao", "")[:50]} for p in rfi_producoes[:20]
                    ],
                    "nota": "Entradas RFI- são colisões de código importadas — revisar e renomear se necessário.",
                },
            }
        )
