"""Ferramentas MCP de Campanha GO — ADR-070: exploração do espaço de configuração."""

from __future__ import annotations

from typing import Any

from mcp.server.fastmcp import FastMCP


def register(server: FastMCP) -> None:
    """Registra as ferramentas de campanha no servidor MCP."""

    @server.tool()
    def explorar_configuracoes_go(
        project_id: str,
        parametros_sweep: list[dict],
        meta_margem_pct: float = 0.10,
        prazo_contratual_semanas: int | None = None,
        top_k: int = 5,
        workers: int = 4,
        reset: bool = True,
    ) -> dict[str, Any]:
        """Explora o espaço de configuração operacional de um projeto (ADR-070).

        Executa uma campanha de sweep paramétrico sobre o projeto especificado.
        Retorna o CampaignOutputBundle com shortlist dos melhores cenários Pareto.

        Cada item em parametros_sweep: {campo: str, valores: list, scope?: str, item_ids?: list}
        Escopos: "global" (padrão), "per_item" (k^n cenários), "cpu_alternativo"

        Args:
            project_id: ID (slug) do projeto, ex: "AGIS".
            parametros_sweep: Lista de dimensões do sweep. Cada dict deve conter
                ``campo`` (dot-path no spec, ex: "meta.regime_trabalho.dias_semana")
                e ``valores`` (lista de valores a testar). Opcionalmente ``scope``
                ("global", "per_item", "cpu_alternativo") e ``item_ids``.
            meta_margem_pct: Meta de margem líquida (default 0.10 = 10%).
            prazo_contratual_semanas: Prazo contratual em semanas. None = derivado
                de data_termino - data_inicio do projeto.
            top_k: Número de cenários na shortlist final (default 5).
            workers: Workers paralelos para avaliação de cenários (default 4).
            reset: Se True, reavalia todos os cenários mesmo que já existam em cache.
        """
        import json
        from pathlib import Path

        from concilium.application.services.campaign.campaign_report import (
            render_campaign_report_md,
            render_campaign_report_pdf,
            serialize_campaign_report,
        )
        from concilium.application.services.campaign.campaign_service import construir_cubo, executar_campanha
        from concilium.domain.models.campaign.campaign import GoResearchCampaignBundle, ParametroSweep, PerfilExpectativas
        from concilium.infrastructure.settings import get_storage
        from concilium.infrastructure.storage.campaign_store import CampaignRunStore
        from concilium.presentation.cli.commands_campaign import _load_project_base_spec
        from concilium.presentation.cli.shared import _tools_root

        try:
            storage = get_storage()
            projects_root = storage.projects_root
            if projects_root is None:
                projects_root = _tools_root() / "projetos"
            projects_root = Path(projects_root)
            config_root = Path(storage.config_root)

            slug = project_id.upper()

            base_spec = _load_project_base_spec(projects_root, slug)
            if base_spec is None:
                return {"erro": f"Projeto '{slug}' não encontrado ou sem canonical."}

            perfil = PerfilExpectativas(
                meta_margem_pct=meta_margem_pct,
                tolerancia_margem=0.03,
                prazo_contratual_semanas=prazo_contratual_semanas,
            )

            sweep: list[ParametroSweep] = []
            for s in parametros_sweep:
                sweep.append(
                    ParametroSweep(
                        campo=s["campo"],
                        valores=s["valores"],
                        scope=s.get("scope", "global"),
                        item_ids=s.get("item_ids"),
                    )
                )

            bundle = GoResearchCampaignBundle(
                base_spec=base_spec,
                sweep=sweep,
                perfil_expectativas=perfil,
                top_k=top_k,
                campaign_version="v1",
            )

            result = executar_campanha(
                bundle,
                config_root=config_root,
                projects_root=projects_root,
                num_workers=workers,
                reset=reset,
            )
            cube = construir_cubo(bundle, result)
            report = serialize_campaign_report(result, cube)
            md = render_campaign_report_md(report)
            pdf = render_campaign_report_pdf(report, md)

            # Persist to store
            store = CampaignRunStore(projects_root / slug)
            run_id = store.new_run()
            store.save_config(run_id, {"sweep": parametros_sweep, "top_k": top_k})
            store.save_bundle(run_id, report)
            store.save_cube(run_id, report.get("cubo") or {})
            store.save_report(run_id, report, md, pdf)
            store.save_meta(
                run_id,
                {
                    "campaign_version": result.campaign_version,
                    "status": result.status,
                    "n_avaliados": result.n_cenarios_avaliados,
                    "n_viaveis": result.n_cenarios_viaveis,
                    "n_falhas": result.n_falhas,
                },
            )

            # Build compact response
            shortlist_items = []
            for r in result.shortlist:
                j = r.justificativa
                shortlist_items.append(
                    {
                        "rank": r.rank,
                        "cenario_id": r.cenario.cenario_id,
                        "viabilidade": r.cenario.viabilidade,
                        "classificacao_O": r.cenario.classificacao_O,
                        "classificacao_EF": r.cenario.classificacao_EF,
                        "pareto_intersecao": r.cenario.pareto_intersecao,
                        "parametros_variados": r.cenario.parametros_variados,
                        "motivo_inclusao": j.motivo_inclusao,
                        "destaques": (j.destaques_EF + j.destaques_O)[:5],
                        "alertas": j.alertas,
                    }
                )

            return {
                "run_id": run_id,
                "status": result.status,
                "n_avaliados": result.n_cenarios_avaliados,
                "n_viaveis": result.n_cenarios_viaveis,
                "n_falhas": result.n_falhas,
                "shortlist": shortlist_items,
            }
        except Exception as exc:
            return {"erro": f"Erro ao executar campanha: {exc}"}

    @server.tool()
    def listar_runs_campanha(project_id: str) -> list[dict[str, Any]]:
        """Lista todos os runs de campanha para um projeto.

        Retorna [{run_id, status, n_avaliados, gerado_em}] em ordem reversa
        (mais recente primeiro).

        Args:
            project_id: ID (slug) do projeto, ex: "AGIS".
        """
        from pathlib import Path

        from concilium.infrastructure.settings import get_storage
        from concilium.infrastructure.storage.campaign_store import CampaignRunStore
        from concilium.presentation.cli.shared import _tools_root

        try:
            storage = get_storage()
            projects_root = storage.projects_root
            if projects_root is None:
                projects_root = _tools_root() / "projetos"
            projects_root = Path(projects_root)

            slug = project_id.upper()
            store = CampaignRunStore(projects_root / slug)

            items = []
            for run_id in reversed(store.list_runs()):
                meta = store.load_meta(run_id) or {}
                items.append(
                    {
                        "run_id": run_id,
                        "campaign_version": meta.get("campaign_version"),
                        "status": meta.get("status"),
                        "n_avaliados": meta.get("n_avaliados"),
                        "n_viaveis": meta.get("n_viaveis"),
                        "gerado_em": meta.get("gerado_em"),
                    }
                )
            return items
        except Exception as exc:
            return [{"erro": f"Erro ao listar runs: {exc}"}]

    @server.tool()
    def obter_resultado_campanha(
        project_id: str,
        run_id: str | None = None,
    ) -> dict[str, Any]:
        """Retorna o bundle + resumo analítico de um run de campanha.

        Inclui shortlist, status e breakdown por dimensão de sweep.

        Args:
            project_id: ID (slug) do projeto, ex: "AGIS".
            run_id: ID do run específico (ex: "run-001"). None = run mais recente.
        """
        from pathlib import Path

        from concilium.infrastructure.settings import get_storage
        from concilium.infrastructure.storage.campaign_store import CampaignRunStore
        from concilium.presentation.cli.shared import _tools_root

        try:
            storage = get_storage()
            projects_root = storage.projects_root
            if projects_root is None:
                projects_root = _tools_root() / "projetos"
            projects_root = Path(projects_root)

            slug = project_id.upper()
            store = CampaignRunStore(projects_root / slug)

            # Resolve run_id
            resolved = run_id or store.current_run()
            if resolved is None:
                return {
                    "erro": f"Nenhum run de campanha encontrado para o projeto '{slug}'.",
                    "dica": "Execute explorar_configuracoes_go primeiro para gerar um run.",
                }

            if resolved not in store.list_runs():
                return {"erro": f"Run '{resolved}' não encontrado para projeto '{slug}'."}

            meta = store.load_meta(resolved) or {}
            bundle = store.load_bundle(resolved)

            if bundle is None:
                return {
                    "run_id": resolved,
                    "meta": meta,
                    "bundle": None,
                    "aviso": "Bundle ainda não disponível — run pode estar em andamento.",
                }

            # Extract shortlist summary from bundle
            shortlist = bundle.get("shortlist") or []
            shortlist_resumo = [
                {
                    "rank": s.get("rank"),
                    "cenario_id": s.get("cenario", {}).get("cenario_id"),
                    "viabilidade": s.get("cenario", {}).get("viabilidade"),
                    "classificacao_O": s.get("cenario", {}).get("classificacao_O"),
                    "classificacao_EF": s.get("cenario", {}).get("classificacao_EF"),
                    "pareto_intersecao": s.get("cenario", {}).get("pareto_intersecao"),
                    "motivo_inclusao": s.get("justificativa", {}).get("motivo_inclusao"),
                }
                for s in shortlist
            ]

            return {
                "run_id": resolved,
                "meta": meta,
                "shortlist": shortlist_resumo,
                "n_cenarios": len(bundle.get("cenarios") or []),
            }
        except Exception as exc:
            return {"erro": f"Erro ao obter resultado de campanha: {exc}"}

    # ADR-101: _meta.ui para MCP Apps (Fase 1)
    _ui_metas = {
        "explorar_configuracoes_go": {"ui": {"resourceUri": "ui://concilium/diagnostico-pe", "permissions": []}},
    }
    for tool_name, meta in _ui_metas.items():
        try:
            tool = server._tool_manager._tools.get(tool_name)
            if tool is not None:
                tool.meta = meta
        except Exception:
            pass
