"""ValidaÃ§Ã£o de integridade interna do pipeline Concilium (03 â†’ 04 â†’ 06)."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

_DEFAULT_ROOT = Path(__file__).resolve().parents[5]


def _load(p: Path) -> dict[str, Any]:
    return json.loads(p.read_text(encoding="utf-8"))


def _lp_load_meta(meta_path: Path) -> dict | None:
    try:
        return _load(meta_path)
    except Exception:
        return None


def _lp_matches_name(nome_meta: str, project_name: str) -> bool:
    return (
        nome_meta == project_name
        or project_name.upper() in nome_meta.upper()
        or nome_meta.upper() in project_name.upper()
    )


def _lp_check_dir(d: Path, project_name: str) -> tuple[str, Path] | None:
    if not d.is_dir():
        return None
    meta = _lp_load_meta(d / "meta.json")
    if meta is None:
        return None
    nome_meta = str(meta.get("nome") or "")
    if not _lp_matches_name(nome_meta, project_name):
        return None
    return str(meta.get("criado_em") or ""), d


def _latest_project_by_name(project_name: str, projects_root: Path) -> Path | None:
    best: tuple[str, Path] | None = None
    for d in projects_root.iterdir():
        result = _lp_check_dir(d, project_name)
        if result is None:
            continue
        created, path = result
        if best is None or created > best[0]:
            best = (created, path)
    return best[1] if best else None


def _sum_subtotal(itens: list[dict[str, Any]], branch: str) -> float:
    total = 0.0
    for item in itens:
        subtotal = item.get("subtotal") or {}
        branch_obj = subtotal.get(branch) or {}
        try:
            total += float(branch_obj.get("total") or 0)
        except Exception:
            continue
    return round(total, 2)


def _bet_sum_equipes_custo(equipes: list) -> float:
    """Soma custo_total das equipes diretas."""
    total = 0.0
    for eq in equipes:
        try:
            total += float(eq.get("custo_total") or 0)
        except Exception:
            continue
    return total


def _bet_build_indiretos(indiretos: list) -> tuple[float, dict]:
    """Agrega indiretos por categoria e totaliza."""
    por_categoria: dict = {}
    total_indireto = 0.0
    for ind in indiretos:
        cat = ind.get("categoria")
        if not cat:
            continue
        val = float(ind.get("custo_total") or 0)
        por_categoria[cat] = por_categoria.get(cat, 0.0) + val
        total_indireto += val
    return total_indireto, por_categoria


def _bet_extract_resultado(resultado: dict) -> tuple[dict, object]:
    """Formata consolidacao (06) e extrai direto_catalogo."""
    venda = resultado.get("venda") or {}
    custo = resultado.get("custo") or {}
    consolidacao = {
        "venda": {
            "total_sem_bdi": venda.get("total_sem_bdi"),
            "total_com_bdi": venda.get("total_com_bdi"),
            "total_custo_plus_catalogo": venda.get("total_custo_plus_catalogo"),
            "total_custo_plus": venda.get("total_custo_plus"),
        },
        "custo": {
            "total": custo.get("total"),
            "direto_catalogo": custo.get("direto_catalogo"),
            "direto_equipes": custo.get("direto_equipes"),
        },
        "margem_pct": resultado.get("margem_pct"),
    }
    return consolidacao, custo.get("direto_catalogo")


def _build_etapas_from_canonical(canonical: dict[str, Any]) -> dict[str, Any]:
    equipes = canonical.get("equipes_diretas") or []
    planejamento = canonical.get("planejamento") or []
    indiretos = canonical.get("indiretos") or []
    resultado = canonical.get("resultado") or {}
    custo_direto_total = _bet_sum_equipes_custo(equipes)
    total_indireto, por_categoria = _bet_build_indiretos(indiretos)
    res_formatted, direto_catalogo = _bet_extract_resultado(resultado)
    return {
        "03_equipes_e_alocacao": {
            "agregados": {"custo_direto_total_equipes": round(custo_direto_total, 2)},
            "equipes": equipes,
        },
        "04_planejamento_bdi": {
            "subtotal_sem_bdi_total": _sum_subtotal(planejamento, "sem_bdi"),
            "subtotal_com_bdi_total": _sum_subtotal(planejamento, "com_bdi"),
            "itens_planejamento": len(planejamento),
        },
        "05_indiretos": {"total_sem_bdi": round(total_indireto, 2), "por_categoria": por_categoria},
        "06_consolidacao": {"resultado": res_formatted},
        "03_equipes_e_alocacao_catalogo": {"custo_direto_catalogo": direto_catalogo},
    }


def _vpi_load_etapas(data_dir: object, ref: dict, r: object, slug: str) -> dict:
    """Loads etapas from extracao_intermediarios.json or rebuilds from canonical."""
    from pathlib import Path as _Path

    extr_path = _Path(str(data_dir)) / "extracao_intermediarios.json"
    if extr_path.exists():
        extr = _load(extr_path)
        return extr.get("etapas", {})
    projeto_nome = str(ref.get("projeto") or (ref.get("meta") or {}).get("projeto") or slug)
    proj = _latest_project_by_name(projeto_nome, _Path(str(r)) / "benchmarks" / "projetos")
    if proj is None:
        proj = _latest_project_by_name(projeto_nome, _Path(str(r)) / "projetos")
    if proj is None:
        raise FileNotFoundError(
            f"Projeto n\u00e3o encontrado para slug={slug} e nome={projeto_nome} em benchmarks/projetos ou projetos/"
        )
    canonical = _load(_Path(str(proj)) / "v1" / "canonical.json")
    return _build_etapas_from_canonical(canonical)


def _vpi_partition_ref(ref_planej: list) -> tuple[list, list]:
    """Partitions ref_planej into (com_dados, zerados) based on subtotal > 0."""
    ref_com_dados: list = []
    ref_zerados: list = []
    for p in ref_planej:
        subtotal = (p.get("subtotal_sem_bdi") or {}).get("total")
        if subtotal is None:
            subtotal = ((p.get("subtotal") or {}).get("sem_bdi") or {}).get("total", 0)
        if float(subtotal or 0) > 0:
            ref_com_dados.append(p)
        else:
            ref_zerados.append(p)
    return ref_com_dados, ref_zerados


def _vpi_build_checkpoints(e4: dict, e6: dict) -> list:
    """Builds pipeline integrity checkpoints for stages 04->06."""

    def _f(v: object) -> float:
        try:
            return float(v or 0)
        except Exception:
            return 0.0

    return [
        {
            "checkpoint": "04 \u2192 06 (venda sem BDI)",
            "e4_valor": round(_f(e4.get("subtotal_sem_bdi_total")), 2),
            "e6_valor": round(_f(e6.get("venda", {}).get("total_sem_bdi")), 2),
            "delta": round(_f(e6.get("venda", {}).get("total_sem_bdi")) - _f(e4.get("subtotal_sem_bdi_total")), 2),
            "status": "OK"
            if abs(_f(e6.get("venda", {}).get("total_sem_bdi")) - _f(e4.get("subtotal_sem_bdi_total"))) < 0.05
            else "DIVERGENTE",
        },
        {
            "checkpoint": "04 \u2192 06 (venda com BDI = direto+indireto)",
            "e4_direto_com_bdi": round(_f(e4.get("subtotal_com_bdi_total")), 2),
            "e6_total_com_bdi": round(_f(e6.get("venda", {}).get("total_com_bdi")), 2),
            "e6_total_custo_plus_catalogo": round(_f(e6.get("venda", {}).get("total_custo_plus_catalogo")), 2),
            "delta_indireto_adicionado": round(
                _f(e6.get("venda", {}).get("total_com_bdi")) - _f(e4.get("subtotal_com_bdi_total")), 2
            ),
            "status": "OK"
            if abs(
                _f(e6.get("venda", {}).get("total_com_bdi")) - _f(e6.get("venda", {}).get("total_custo_plus_catalogo"))
            )
            < 0.05
            else "DIVERGENTE",
        },
    ]


def _vpi_build_output(
    ref: dict,
    slug: str,
    ref_planej: list,
    ref_com_dados: list,
    ref_zerados: list,
    e3: dict,
    e4: dict,
    e5: dict,
    e6: dict,
    checkpoints: list,
) -> dict:
    """Builds the full output dict for validate_pipeline_integrity."""
    return {
        "projeto": ref.get("projeto"),
        "slug": ref.get("slug") or (ref.get("meta") or {}).get("slug") or slug,
        "analise_base_referencia": {
            "total_atividades": len(ref_planej),
            "atividades_com_dados": len(ref_com_dados),
            "atividades_zeradas": len(ref_zerados),
            "atividades_com_dados_ids": [p.get("item_id") for p in ref_com_dados],
            "atividades_zeradas_ids": [p.get("item_id") for p in ref_zerados],
        },
        "integridade_pipeline_concilium": {
            "03_equipes": {
                "custo_direto_total": e3.get("agregados", {}).get("custo_direto_total_equipes", 0),
                "equipes_count": len(e3.get("equipes", [])),
                "itens_com_equipes": [eq.get("item_id") for eq in e3.get("equipes", [])],
            },
            "04_planejamento": {
                "subtotal_sem_bdi_total": e4.get("subtotal_sem_bdi_total"),
                "subtotal_com_bdi_total": e4.get("subtotal_com_bdi_total"),
                "itens_planejamento": e4.get("itens_planejamento"),
            },
            "05_indiretos": {
                "total_sem_bdi": e5.get("total_sem_bdi"),
                "categorias": list((e5.get("por_categoria") or {}).keys()),
            },
            "06_consolidacao": {
                "venda_total_sem_bdi": e6.get("venda", {}).get("total_sem_bdi"),
                "venda_total_com_bdi": e6.get("venda", {}).get("total_com_bdi"),
                "custo_total": e6.get("custo", {}).get("total"),
                "margem_pct": e6.get("margem_pct"),
            },
        },
        "validacoes_fechamento": checkpoints,
    }


def validate_pipeline_integrity(slug: str, root: Path | None = None) -> dict[str, Any]:
    """Valida integridade interna de um benchmark (fluxo 03â†’04â†’06 fecha?).

    Args:
        slug: ex. "CTC"
        root: raiz do repositÃ³rio (padrÃ£o: detectado automaticamente)

    Returns:
        DicionÃ¡rio com anÃ¡lise e checkpoints de fechamento.
    """
    r = root or _DEFAULT_ROOT
    data_dir = r / "benchmarks" / "data" / slug
    ref = _load(data_dir / "referencia.json")
    etapas = _vpi_load_etapas(data_dir, ref, r, slug)
    e3 = etapas.get("03_equipes_e_alocacao", {})
    e4 = etapas.get("04_planejamento_bdi", {})
    e5 = etapas.get("05_indiretos", {})
    e6 = etapas.get("06_consolidacao", {}).get("resultado", {})
    ref_planej = ref.get("planejamento_detalhado") or (ref.get("planejamento") or {}).get("itens") or []
    ref_com_dados, ref_zerados = _vpi_partition_ref(ref_planej)
    checkpoints = _vpi_build_checkpoints(e4, e6)
    return _vpi_build_output(ref, slug, ref_planej, ref_com_dados, ref_zerados, e3, e4, e5, e6, checkpoints)
