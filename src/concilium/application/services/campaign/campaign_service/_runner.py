"""ADR-070 — Campaign service (parte extraída de campaign_service.py)."""

from __future__ import annotations

import concurrent.futures
from datetime import UTC, datetime
from pathlib import Path

from concilium.domain.models.campaign.campaign import (
    CampaignOutputBundle,
    CenarioAvaliado,
    GoResearchCampaignBundle,
)

from ._grid import gerar_grid
from ._shortlist import classificar_bundle, curar_shortlist
from ._task import _CampaignTask, _run_campaign_task


def executar_campanha(
    bundle: GoResearchCampaignBundle,
    config_root: str | Path,
    projects_root: str | Path,
    procurement_intent: str = "rfp",
    num_workers: int = 3,
    reset: bool = True,
) -> CampaignOutputBundle:
    """Execute a full campaign: generate grid, evaluate, curate, return bundle.

    ADR-109: verifica fronteira de tratabilidade antes de executar.
    O limiar é configurável via CONCILIUM__CAMPAIGN_CARDINALITY_THRESHOLD (default: 10.000).
    """
    import warnings

    from concilium.infrastructure.settings import get_campaign as _get_campaign_settings

    cfg = _get_campaign_settings()
    n_card = bundle.cardinality()
    if n_card > cfg.cardinality_threshold:
        _w = num_workers or cfg.max_workers
        _s = cfg.seconds_per_scenario
        warnings.warn(
            f"GoResearchCampaignBundle.cardinality={n_card:,} excede fronteira de "
            f"tratabilidade ({cfg.cardinality_threshold:,}). "
            f"Busca exaustiva levaria ~{n_card * _s // _w // 3600:.0f}h "
            f"com {_w} workers ({_s}s/cenário). "
            f"Considere reduzir dimensões ou usar busca guiada. "
            f"Ajuste CONCILIUM__CAMPAIGN_CARDINALITY_THRESHOLD para suprimir este aviso.",
            stacklevel=2,
        )

    grid = gerar_grid(bundle)
    cenarios: list[CenarioAvaliado] = []
    prazo_cont = bundle.perfil_expectativas.prazo_contratual_semanas

    tasks = [
        _CampaignTask(
            spec_v=sv,
            variados=var,
            config_root=str(config_root),
            projects_root=str(projects_root),
            prazo_contratual=prazo_cont,
            perfil=bundle.perfil_expectativas,
            procurement_intent=procurement_intent,
            do_reset=reset,
        )
        for sv, var in grid
    ]

    # ThreadPoolExecutor: correto para este workload (I/O-bound com leitura de canonical,
    # config e catálogo; escrita de JSON). ProcessPoolExecutor com fork causa race conditions
    # em acesso compartilhado ao filesystem de projetos/ resultando em canonical vazio.
    # O speedup medido (3.7×) era real — o bottleneck era o _store_lock removido, não o GIL.
    with concurrent.futures.ThreadPoolExecutor(max_workers=num_workers) as executor:
        futures = {executor.submit(_run_campaign_task, t): t for t in tasks}
        for future in concurrent.futures.as_completed(futures):
            cenarios.append(future.result())

    shortlist = curar_shortlist(cenarios, bundle.top_k, bundle.perfil_expectativas)
    status = classificar_bundle(cenarios)
    viaveis = [c for c in cenarios if c.viabilidade in {"APROVADO", "APROVADO_COM_RESSALVAS"}]

    output = CampaignOutputBundle(
        campaign_id=bundle.campaign_id,
        campaign_version=bundle.campaign_version,
        gerado_em=datetime.now(UTC),
        n_cenarios_avaliados=len(cenarios),
        n_cenarios_viaveis=len(viaveis),
        n_falhas=sum(1 for c in cenarios if c.erro),
        status=status,
        cenarios=cenarios,
        shortlist=shortlist,
    )
    return output


