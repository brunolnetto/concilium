"""ADR-070 — Campaign service (parte extraída de campaign_service.py)."""

from __future__ import annotations

from typing import TYPE_CHECKING

from concilium.domain.models.campaign.campaign import (
    CampaignBundleCube,
    CampaignOutputBundle,
    CelulaAnalitica,
    CenarioAvaliado,
    CuboDimensao,
    FaceAnalitica,
    GoResearchCampaignBundle,
    ResumoMarginal,
)

from ._grid import cenario_id, gerar_grid

if TYPE_CHECKING:
    from concilium.domain.models.campaign.campaign import TendenciaMarginal


_METRICAS_O = [
    "prazo_semanas",
    "fe_nec_medio",
    "itens_criticos_pct",
    "gap_pool_total",
    "utilizacao_recursos_pct",
    "paralelismo_medio",
]


_METRICAS_EF = [
    "margem_pct",
    "ratio_pool_vs_cat",
    "custo_indireto",
    "share_mo_pct",
    "share_eq_pct",
    "share_comb_pct",
    "concentracao_atividade",
]


def _get_metrica(c: CenarioAvaliado, metrica: str) -> float | None:
    vo, vef = c.vetor_O, c.vetor_EF
    return getattr(vo, metrica, None) or getattr(vef, metrica, None)


def _label_variados(variados: dict) -> str:
    """Extrai label legível dos parâmetros variados."""
    parts = []
    for campo, valor in variados.items():
        nome = campo.split(".")[-1]
        if isinstance(valor, dict):
            parts.append(", ".join(f"{k}={v}" for k, v in valor.items()))
        else:
            parts.append(f"{nome}={valor}")
    return " | ".join(parts) if parts else str(variados)


def _tendencia(valores_ord: list, medias: list[float | None]) -> TendenciaMarginal:
    from concilium.domain.models.campaign.campaign import TendenciaMarginal  # noqa: F401

    valid = [(v, m) for v, m in zip(valores_ord, medias, strict=False) if m is not None]
    if len(valid) < 2:
        return "indeterminado"
    ms = [m for _, m in valid]
    if all(ms[i] <= ms[i + 1] for i in range(len(ms) - 1)):
        return "crescente"
    if all(ms[i] >= ms[i + 1] for i in range(len(ms) - 1)):
        return "decrescente"
    return "nao_monotona"


def _construir_dimensoes_cubo(bundle: GoResearchCampaignBundle) -> list[CuboDimensao]:
    return [
        CuboDimensao(
            nome=s.campo.split(".")[-1],
            campo=s.campo,
            valores=s.valores,
        )
        for s in bundle.sweep
    ]


def _montar_celula_cubo(
    variados: dict,
    dims: list[CuboDimensao],
    cenario_por_id: dict[str, CenarioAvaliado],
) -> CelulaAnalitica:
    cid = cenario_id(variados)
    c = cenario_por_id.get(cid)
    dimensoes = {d.nome: variados.get(d.campo) for d in dims}
    if c:
        return CelulaAnalitica(
            dimensoes=dimensoes,
            cenario_id=cid,
            vetor_O=c.vetor_O,
            vetor_EF=c.vetor_EF,
            classificacao_O=c.classificacao_O,
            classificacao_EF=c.classificacao_EF,
            viabilidade=c.viabilidade,
            pareto_O=c.pareto_O,
            pareto_EF=c.pareto_EF,
            pareto_intersecao=c.pareto_intersecao,
        )
    return CelulaAnalitica(
        dimensoes=dimensoes,
        cenario_id=None,
        vetor_O=None,
        vetor_EF=None,
        classificacao_O=None,
        classificacao_EF=None,
        viabilidade=None,
        pareto_O=False,
        pareto_EF=False,
        pareto_intersecao=False,
    )


def _construir_celulas_cubo(
    bundle: GoResearchCampaignBundle,
    dims: list[CuboDimensao],
    cenario_por_id: dict[str, CenarioAvaliado],
) -> list[CelulaAnalitica]:
    grid_list = list(gerar_grid(bundle))
    return [_montar_celula_cubo(variados, dims, cenario_por_id) for _sv, variados in grid_list]


def _grade_face_cubo(
    celulas: list[CelulaAnalitica],
    cenario_por_id: dict[str, CenarioAvaliado],
    dx: CuboDimensao,
    dy: CuboDimensao,
    metrica: str,
) -> list[list[float | None]]:
    grade: list[list[float | None]] = []
    for vy in dy.valores:
        row = []
        for vx in dx.valores:
            matching = [
                ce
                for ce in celulas
                if ce.dimensoes.get(dx.nome) == vx and ce.dimensoes.get(dy.nome) == vy and ce.cenario_id
            ]
            if matching:
                # matching[0].cenario_id só é truthy quando a célula foi
                # construída a partir de um `c` presente em cenario_por_id
                # (ver loop de --- 2. Células --- acima); logo o lookup
                # abaixo sempre resolve — sem fallback necessário.
                cid = matching[0].cenario_id
                assert cid is not None, "cenario_id deve ser não-None após filtro"
                c_match = cenario_por_id[cid]
                row.append(_get_metrica(c_match, metrica))
            else:
                row.append(None)
        grade.append(row)
    return grade


def _construir_faces_cubo(
    dims: list[CuboDimensao],
    celulas: list[CelulaAnalitica],
    cenario_por_id: dict[str, CenarioAvaliado],
) -> list[FaceAnalitica]:
    faces: list[FaceAnalitica] = []
    if len(dims) < 2:
        return faces
    for i, dx in enumerate(dims):
        for dy in dims[i + 1 :]:
            for metrica in _METRICAS_O + _METRICAS_EF:
                grade = _grade_face_cubo(celulas, cenario_por_id, dx, dy, metrica)
                # Only include face if at least some values are non-None
                if any(v is not None for row in grade for v in row):
                    faces.append(
                        FaceAnalitica(
                            dim_x=dx.nome,
                            dim_y=dy.nome,
                            metrica=metrica,
                            valores_x=dx.valores,
                            valores_y=dy.valores,
                            grade=grade,
                        )
                    )
    return faces


def _medias_resumo_dimensao(
    d: CuboDimensao,
    metrica: str,
    celulas: list[CelulaAnalitica],
    cenario_por_id: dict[str, CenarioAvaliado],
) -> list[float | None]:
    medias: list[float | None] = []
    for val in d.valores:
        celulas_val = [ce for ce in celulas if ce.dimensoes.get(d.nome) == val and ce.cenario_id]
        vals_m = []
        for ce in celulas_val:
            # Mesmo invariante do bloco de faces acima: ce.cenario_id truthy
            # garante presença em cenario_por_id.
            cid_m = ce.cenario_id
            assert cid_m is not None, "cenario_id deve ser não-None após filtro"
            c_m = cenario_por_id[cid_m]
            v = _get_metrica(c_m, metrica)
            if v is not None:
                vals_m.append(v)
        medias.append(round(sum(vals_m) / len(vals_m), 4) if vals_m else None)
    return medias


def _construir_resumos_marginais_cubo(
    dims: list[CuboDimensao],
    celulas: list[CelulaAnalitica],
    cenario_por_id: dict[str, CenarioAvaliado],
) -> list[ResumoMarginal]:
    resumos: list[ResumoMarginal] = []
    for d in dims:
        for metrica in _METRICAS_O + _METRICAS_EF:
            medias = _medias_resumo_dimensao(d, metrica, celulas, cenario_por_id)
            if any(m is not None for m in medias):
                resumos.append(
                    ResumoMarginal(
                        dimensao=d.nome,
                        metrica=metrica,
                        valores=d.valores,
                        medias=medias,
                        tendencia=_tendencia(d.valores, medias),
                    )
                )
    return resumos


def construir_cubo(bundle: GoResearchCampaignBundle, output: CampaignOutputBundle) -> CampaignBundleCube:
    """Constrói o CampaignBundleCube a partir do bundle e do output da campanha.

    Dimensões = parâmetros do sweep.
    Células = todas as combinações avaliadas (com cenário) ou ausentes (sem cenário).
    Faces = projeções 2D para cada par de dimensões (se sweep ≥ 2 dimensões).
    Resumos marginais = efeito de cada dimensão em cada métrica.
    """
    # --- 1. Dimensões ---
    dims = _construir_dimensoes_cubo(bundle)

    # Índice de cenários por variados-hash
    cenario_por_id = {c.cenario_id: c for c in output.cenarios}

    # --- 2. Células ---
    celulas = _construir_celulas_cubo(bundle, dims, cenario_por_id)

    n_total = len(celulas)
    n_aval = sum(1 for ce in celulas if ce.cenario_id)
    n_viaveis = sum(1 for ce in celulas if ce.viabilidade in {"APROVADO", "APROVADO_COM_RESSALVAS"})
    n_pareto = sum(1 for ce in celulas if ce.pareto_intersecao)

    # --- 3. Faces (pares de dimensões) ---
    faces = _construir_faces_cubo(dims, celulas, cenario_por_id)

    # --- 4. Resumos marginais ---
    resumos = _construir_resumos_marginais_cubo(dims, celulas, cenario_por_id)

    return CampaignBundleCube(
        campaign_id=output.campaign_id,
        dimensoes=dims,
        celulas=celulas,
        faces=faces,
        resumos_marginais=resumos,
        n_celulas_total=n_total,
        n_celulas_avaliadas=n_aval,
        n_celulas_viaveis=n_viaveis,
        n_celulas_pareto=n_pareto,
        cobertura_pct=round(n_aval / n_total, 4) if n_total else 0.0,
    )


