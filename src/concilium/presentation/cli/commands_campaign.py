"""Comandos CLI para exploração de campanha GO — concilium project campaign."""

from __future__ import annotations

from pathlib import Path

import typer


def campaign(
    project_id: str = typer.Argument(..., help="ID ou slug do projeto (ex: AGIS)"),
    campaign_file: Path = typer.Option(
        None,
        "--campaign", "-c",
        help="Arquivo campaign_v{i}.json. Default: projetos/{slug}/campaigns/campaign_v1.json",
    ),
    config_root: Path = typer.Option(None, "--config", help="Diretório de configuração"),
    projects_root: Path = typer.Option(None, "--projects", help="Diretório de projetos"),
    workers: int = typer.Option(4, "--workers", "-w", help="Número de workers paralelos"),
    reset: bool = typer.Option(True, "--reset/--no-reset", help="Forçar re-avaliação dos cenários"),
) -> None:
    """Explora o espaço de configuração operacional de um projeto (ADR-070).

    Lê a campanha em projetos/{slug}/campaigns/campaign_v{i}.json,
    executa o sweep paramétrico e salva relatório em
    projetos/{slug}/artifacts/campaign/.

    Exemplo:
        concilium project campaign AGIS
        concilium project campaign AGIS --campaign projetos/AGIS/campaigns/campaign_v2.json
    """
    import json
    from concilium.application.services.campaign_service import construir_cubo, executar_campanha
    from concilium.application.services.campaign_report import (
        render_campaign_report_md,
        render_campaign_report_pdf,
        serialize_campaign_report,
    )
    from concilium.domain.models.campaign import GoResearchCampaignBundle, ParametroSweep, PerfilExpectativas

    # Resolver paths
    _cfg = config_root or _default_config_root()
    _proj = projects_root or _default_projects_root()

    slug = project_id.upper()

    # Resolver campaign file
    if campaign_file is None:
        campaign_file = _proj / slug / "campaigns" / "campaign_v1.json"

    if not campaign_file.exists():
        typer.echo(f"[ERRO] Arquivo de campanha não encontrado: {campaign_file}", err=True)
        raise typer.Exit(1)

    # Carregar campaign config
    cfg = json.loads(campaign_file.read_text(encoding="utf-8"))
    typer.echo(f"[INFO] Campanha: {cfg.get('descricao', campaign_file.name)}")

    # Construir base_spec a partir do canonical mais recente do projeto
    # (ProjetoSpec canônico — não referencia.json de benchmark)
    base_spec = _load_project_base_spec(_proj, slug)
    if base_spec is None:
        typer.echo(f"[ERRO] Projeto '{slug}' não encontrado ou sem canonical.", err=True)
        raise typer.Exit(1)

    # Montar bundle
    perf_raw = cfg.get("perfil_expectativas") or {}
    perfil = PerfilExpectativas(
        meta_margem_pct=perf_raw.get("meta_margem_pct", 0.10),
        tolerancia_margem=perf_raw.get("tolerancia_margem", 0.03),
        prazo_contratual_semanas=perf_raw.get("prazo_contratual_semanas"),
    )
    sweep = [ParametroSweep(campo=s["campo"], valores=s["valores"]) for s in (cfg.get("sweep") or [])]
    bundle = GoResearchCampaignBundle(
        base_spec=base_spec,
        sweep=sweep,
        perfil_expectativas=perfil,
        top_k=cfg.get("top_k", 5),
        campaign_version=cfg.get("campaign_version", "v1"),
    )

    n_cenarios = 1
    for s in bundle.sweep:
        n_cenarios *= len(s.valores)
    typer.echo(f"[INFO] Grid: {len(bundle.sweep)} dimensões × {n_cenarios} cenários | {workers} workers")

    # Executar
    result = executar_campanha(bundle, config_root=_cfg, projects_root=_proj, num_workers=workers, reset=reset)
    cube = construir_cubo(bundle, result)

    typer.echo(f"\n[RESULTADO] {result.status} — {result.n_cenarios_viaveis}/{result.n_cenarios_avaliados} viáveis")
    if result.shortlist:
        for r in result.shortlist:
            j = r.justificativa
            destaques = " · ".join((j.destaques_EF + j.destaques_O)[:3])
            typer.echo(f"  #{r.rank} {r.cenario.cenario_id} ({j.motivo_inclusao}): {destaques}")

    # Persistir como artefato de projeto versionado
    from concilium.infrastructure.storage.campaign_store import CampaignRunStore
    import dataclasses

    store = CampaignRunStore(_proj / slug)
    run = store.new_run()
    typer.echo(f"\n[STORE] Novo run: {run}")

    report = serialize_campaign_report(result, cube)
    md = render_campaign_report_md(report)
    pdf = render_campaign_report_pdf(report, md)

    store.save_bundle(run, report)
    store.save_cube(run, report.get("cubo") or {})
    store.save_report(run, report, md, pdf)
    store.save_meta(run, {
        "campaign_version": result.campaign_version,
        "status": result.status,
        "n_avaliados": result.n_cenarios_avaliados,
        "n_viaveis": result.n_cenarios_viaveis,
        "n_falhas": result.n_falhas,
    })

    run_path = store.run_path(run)
    typer.echo(f"[SAVE] {run_path}/bundle.json")
    typer.echo(f"[SAVE] {run_path}/campaign_report.json")
    typer.echo(f"[SAVE] {run_path}/campaign_report.md")
    if pdf:
        typer.echo(f"[SAVE] {run_path}/campaign_report.pdf")
    typer.echo(f"[SAVE] {run_path}/meta.json")
    typer.echo(f"\n[INFO] Runs disponíveis: {store.list_runs()}")


def _load_project_base_spec(projects_root: Path, slug: str) -> dict | None:
    """Carrega o ProjetoSpec do projeto como base_spec para a campanha.

    Tenta o canonical mais recente do projeto como fonte primária.
    Para benchmarks sem ProjetoSpec canônico, fallback para referencia.json
    na pasta de dados correspondente (se existir).
    """
    import json

    # Primário: canonical do projeto
    for _try in (slug, slug.upper(), slug.lower()):
        can = projects_root / _try / "v1" / "canonical.json"
        if can.exists():
            data = json.loads(can.read_text())
            return _canonical_to_base_spec(data, _try)

    # Fallback: referencia.json em data/ (benchmarks com spec v2)
    benchmarks_data = projects_root.parent / "data" / slug
    ref = benchmarks_data / "referencia.json"
    if ref.exists():
        return json.loads(ref.read_text())

    return None


def _canonical_to_base_spec(canonical: dict, slug: str) -> dict:
    """Extrai campos relevantes do canonical para montar um base_spec de campanha."""
    projeto = canonical.get("projeto") or {}
    regime = projeto.get("regime_trabalho") or {}
    return {
        "slug": slug,
        "meta": {
            "projeto": projeto.get("nome", slug),
            "data_inicio": projeto.get("data_inicio", ""),
            "data_termino": projeto.get("data_termino", ""),
            "regime_trabalho": regime,
        },
    }


def _default_config_root() -> Path:
    here = Path(__file__).resolve()
    for p in here.parents:
        if (p / "config").exists():
            return p / "config"
    return Path("config")


def _default_projects_root() -> Path:
    here = Path(__file__).resolve()
    for p in here.parents:
        if (p / "benchmarks" / "projetos").exists():
            return p / "benchmarks" / "projetos"
        if (p / "projetos").exists():
            return p / "projetos"
    return Path("projetos")
