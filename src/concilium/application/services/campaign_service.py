"""ADR-070 — Campaign service: grid generation, evaluation, Pareto, shortlist curation."""
from __future__ import annotations

import concurrent.futures
import copy
import hashlib
import itertools
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import TYPE_CHECKING

from concilium.domain.models.campaign import (
    CampaignOutputBundle,
    CampaignStatus,
    CenarioAvaliado,
    CenarioRankeado,
    ClassificacaoEF,
    ClassificacaoO,
    GoResearchCampaignBundle,
    JustificativaCenario,
    ParametroSweep,
    PerfilExpectativas,
    VetorEspacoEF,
    VetorEspacoO,
    ViabilidadeStatus,
)

# ---------------------------------------------------------------------------
# F1 — Grid generation
# ---------------------------------------------------------------------------


def gerar_grid(bundle: GoResearchCampaignBundle) -> list[tuple[dict, dict]]:
    """Returns list of (spec_variant, parametros_variados). Applies sweep."""
    if not bundle.sweep:
        return [(bundle.base_spec, {})]
    keys = [s.campo for s in bundle.sweep]
    value_lists = [s.valores for s in bundle.sweep]
    results = []
    for combo in itertools.product(*value_lists):
        variados = dict(zip(keys, combo))
        spec_v = _apply_overrides(copy.deepcopy(bundle.base_spec), variados)
        results.append((spec_v, variados))
    return results


def _apply_overrides(spec: dict, overrides: dict) -> dict:
    """Apply dot-path overrides. Supports nested paths with '.'."""
    for key_path, value in overrides.items():
        # Campos que começam com "inputs_" são aplicados APÓS o carregamento do spec
        # (via _apply_post_load_overrides). Ignorar aqui.
        if key_path.startswith("inputs_"):
            continue
        parts = key_path.split(".")
        d = spec
        for i, part in enumerate(parts[:-1]):
            if part not in d:
                d[part] = {}
            elif not isinstance(d[part], dict):
                d[part] = {}
            d = d[part]
        last = parts[-1]
        # Merge dict values instead of replacing (preserva campos existentes)
        if isinstance(value, dict) and isinstance(d.get(last), dict):
            d[last] = {**d[last], **value}
        else:
            d[last] = value
    return spec


def _apply_post_load_overrides(spec_obj: object, variados: dict) -> None:
    """Aplica overrides com prefixo 'inputs_' diretamente no ProjectSpec carregado."""
    for key_path, value in variados.items():
        if not key_path.startswith("inputs_"):
            continue
        parts = key_path.split(".")
        # spec_obj.{attr} é o primeiro nível
        attr = parts[0]
        d = getattr(spec_obj, attr, None)
        if not isinstance(d, dict):
            continue
        for part in parts[1:-1]:
            if part not in d:
                d[part] = {}
            d = d[part]
        last = parts[-1]
        if isinstance(value, dict) and isinstance(d.get(last), dict):
            d[last] = {**d[last], **value}
        else:
            d[last] = value


def cenario_id(variados: dict) -> str:
    return hashlib.sha1(json.dumps(variados, sort_keys=True, default=str).encode()).hexdigest()[:10]


# ---------------------------------------------------------------------------
# F2 — Vector extraction
# ---------------------------------------------------------------------------


def extrair_vetor_O(canonical: dict, prazo_contratual: int | None) -> VetorEspacoO:
    cron = canonical.get("cronograma") or {}
    prazo = cron.get("makespan_semanas")
    # Fallback: max end_week from scheduled_activities
    if prazo is None:
        acts = cron.get("scheduled_activities") or []
        if acts:
            prazo = max((a.get("end_week") or 0) for a in acts)

    folga = (prazo_contratual - prazo) if (prazo is not None and prazo_contratual) else None

    pes = canonical.get("ponto_equilibrio") or []
    fe_list = [
        pe.get("frentes_equivalentes_necessarias")
        for pe in pes
        if pe.get("frentes_equivalentes_necessarias") is not None
    ]
    fe_med = sum(fe_list) / len(fe_list) if fe_list else None
    n_crit = sum(1 for fe in fe_list if fe > 1.25) if fe_list else 0
    itens_crit_pct = n_crit / len(fe_list) if fe_list else None
    gap_pool = round(sum(pe.get("gap_pool_overhead") or 0 for pe in pes), 2)

    eqs = canonical.get("equipes_diretas") or []
    mob_window = round(sum(e.get("custo_inst_mob_demob") or 0 for e in eqs), 2)

    return VetorEspacoO(
        prazo_semanas=prazo,
        folga_semanas=round(folga, 1) if folga is not None else None,
        fe_nec_medio=round(fe_med, 3) if fe_med is not None else None,
        itens_criticos_pct=round(itens_crit_pct, 3) if itens_crit_pct is not None else None,
        gap_pool_total=gap_pool,
        custo_mob_window_total=mob_window,
    )


def extrair_vetor_EF(canonical: dict, report: dict) -> VetorEspacoEF:
    resultado = canonical.get("resultado") or {}
    custo = resultado.get("custo") or {}
    venda = resultado.get("venda") or {}

    margem = resultado.get("margem_pct")
    custo_pool = custo.get("direto_equipes")
    custo_ind = round(
        sum(v for k, v in custo.items() if "indireto" in k and isinstance(v, (int, float))),
        2,
    )
    preco_venda = venda.get("total_com_bdi")
    pu_q = venda.get("total_sem_bdi")
    ratio = round(custo_pool / pu_q, 4) if (custo_pool and pu_q and pu_q > 0) else None

    gates = (report.get("quality_gates") or {}) if report else {}
    decision = gates.get("decision")
    fidelidade = decision in {"APROVADO", "APROVADO_COM_RESSALVAS"} if decision else None

    return VetorEspacoEF(
        margem_pct=round(margem, 4) if margem is not None else None,
        custo_execucao_pool=custo_pool,
        custo_indireto=custo_ind if custo_ind else None,
        preco_venda=preco_venda,
        ratio_pool_vs_cat=ratio,
        fidelidade_gates=fidelidade,
    )


# ---------------------------------------------------------------------------
# F2 — Classification
# ---------------------------------------------------------------------------


def classificar_O(v: VetorEspacoO, perfil: PerfilExpectativas) -> ClassificacaoO:
    scores = []
    if v.folga_semanas is not None:
        scores.append(
            "IDEAL" if v.folga_semanas >= 0 else ("ATENCAO" if v.folga_semanas >= -2 else "CRITICO")
        )
    if v.fe_nec_medio is not None:
        scores.append(
            "IDEAL" if v.fe_nec_medio <= 1.0 else ("ATENCAO" if v.fe_nec_medio <= 1.25 else "CRITICO")
        )
    if v.itens_criticos_pct is not None:
        scores.append(
            "IDEAL"
            if v.itens_criticos_pct == 0
            else ("ATENCAO" if v.itens_criticos_pct <= 0.20 else "CRITICO")
        )
    if not scores:
        return "ATENCAO"
    if "CRITICO" in scores:
        return "CRITICO"
    if "ATENCAO" in scores:
        return "ATENCAO"
    return "IDEAL"


def classificar_EF(v: VetorEspacoEF, perfil: PerfilExpectativas) -> ClassificacaoEF:
    scores = []
    if v.margem_pct is not None:
        meta = perfil.meta_margem_pct
        tol = perfil.tolerancia_margem
        scores.append(
            "DENTRO_EXPECTATIVA"
            if v.margem_pct >= meta
            else ("ATENCAO" if v.margem_pct >= meta - tol else "FORA_EXPECTATIVA")
        )
    if v.ratio_pool_vs_cat is not None:
        scores.append(
            "DENTRO_EXPECTATIVA"
            if v.ratio_pool_vs_cat <= 1.0
            else ("ATENCAO" if v.ratio_pool_vs_cat <= 1.10 else "FORA_EXPECTATIVA")
        )
    if v.fidelidade_gates is not None:
        scores.append("DENTRO_EXPECTATIVA" if v.fidelidade_gates else "FORA_EXPECTATIVA")
    if not scores:
        return "ATENCAO"
    if "FORA_EXPECTATIVA" in scores:
        return "FORA_EXPECTATIVA"
    if "ATENCAO" in scores:
        return "ATENCAO"
    return "DENTRO_EXPECTATIVA"


# ---------------------------------------------------------------------------
# F3 — Pareto computation
# ---------------------------------------------------------------------------


def _domina_O(a: CenarioAvaliado, b: CenarioAvaliado) -> bool:
    """a dominates b in O-space (minimizing prazo, fe_nec, gap_pool)."""
    va, vb = a.vetor_O, b.vetor_O
    dims = [
        (va.prazo_semanas, vb.prazo_semanas),
        (va.fe_nec_medio, vb.fe_nec_medio),
        (va.gap_pool_total, vb.gap_pool_total),
    ]
    dims = [(x, y) for x, y in dims if x is not None and y is not None]
    if not dims:
        return False
    no_worse = all(x <= y for x, y in dims)
    strictly_better = any(x < y for x, y in dims)
    return no_worse and strictly_better


def _domina_EF(a: CenarioAvaliado, b: CenarioAvaliado) -> bool:
    """a dominates b in EF-space (maximize margem, minimize custo_indireto)."""
    va, vb = a.vetor_EF, b.vetor_EF
    if va.margem_pct is None or vb.margem_pct is None:
        return False
    margem_ok = va.margem_pct >= vb.margem_pct
    ind_ok = True
    if va.custo_indireto is not None and vb.custo_indireto is not None:
        ind_ok = va.custo_indireto <= vb.custo_indireto
    strictly = va.margem_pct > vb.margem_pct or (
        va.custo_indireto is not None
        and vb.custo_indireto is not None
        and va.custo_indireto < vb.custo_indireto
    )
    return margem_ok and ind_ok and strictly


def calcular_pareto(cenarios: list[CenarioAvaliado], espaco: str) -> set[str]:
    """Returns set of cenario_ids on the Pareto frontier for espaco='O'|'EF'."""
    domina = _domina_O if espaco == "O" else _domina_EF
    pareto_ids = set()
    for c in cenarios:
        dominated = any(domina(other, c) for other in cenarios if other.cenario_id != c.cenario_id)
        if not dominated:
            pareto_ids.add(c.cenario_id)
    return pareto_ids


# ---------------------------------------------------------------------------
# F3 — Shortlist curation
# ---------------------------------------------------------------------------


def _build_justificativa(c: CenarioAvaliado, motivo: str) -> JustificativaCenario:
    v_O, v_EF = c.vetor_O, c.vetor_EF
    destaques_O = []
    if v_O.folga_semanas is not None:
        tag = "OK" if v_O.folga_semanas >= 0 else "WARN"
        destaques_O.append(f"[{tag}] Folga {v_O.folga_semanas:+.0f} sem")
    if v_O.fe_nec_medio is not None:
        destaques_O.append(f"fe_nec medio {v_O.fe_nec_medio:.2f}")
    if v_O.itens_criticos_pct == 0:
        destaques_O.append("0 itens criticos")
    elif v_O.itens_criticos_pct is not None:
        destaques_O.append(f"{v_O.itens_criticos_pct * 100:.0f}% itens criticos")

    destaques_EF = []
    if v_EF.margem_pct is not None:
        destaques_EF.append(f"Margem {v_EF.margem_pct * 100:.1f}%")
    if v_EF.ratio_pool_vs_cat is not None:
        if v_EF.ratio_pool_vs_cat <= 1:
            destaques_EF.append(f"Pool {(1 - v_EF.ratio_pool_vs_cat) * 100:.1f}% abaixo mercado")
        else:
            destaques_EF.append(f"Pool {(v_EF.ratio_pool_vs_cat - 1) * 100:.1f}% acima mercado")

    alertas = []
    if c.classificacao_O == "ATENCAO":
        alertas.append("O-space: atencao em alguma dimensao")
    if c.classificacao_EF == "ATENCAO":
        alertas.append("EF-space: margem proxima da meta")

    return JustificativaCenario(
        motivo_inclusao=motivo,
        destaques_O=destaques_O,
        destaques_EF=destaques_EF,
        alertas=alertas,
        parametros_chave=c.parametros_variados,
    )


def curar_shortlist(
    cenarios: list[CenarioAvaliado],
    top_k: int,
    perfil: PerfilExpectativas,
) -> list[CenarioRankeado]:
    viaveis = [c for c in cenarios if c.viabilidade in {"APROVADO", "APROVADO_COM_RESSALVAS"}]
    if not viaveis:
        return []

    pareto_O_ids = calcular_pareto(viaveis, "O")
    pareto_EF_ids = calcular_pareto(viaveis, "EF")

    for c in viaveis:
        c.pareto_O = c.cenario_id in pareto_O_ids
        c.pareto_EF = c.cenario_id in pareto_EF_ids
        c.pareto_intersecao = c.pareto_O and c.pareto_EF

    intersecao = [c for c in viaveis if c.pareto_intersecao]
    pool = intersecao if intersecao else ([c for c in viaveis if c.pareto_EF] or viaveis)

    ranked = sorted(
        pool,
        key=lambda c: (
            c.classificacao_O != "IDEAL",
            c.classificacao_EF != "DENTRO_EXPECTATIVA",
            -(c.vetor_EF.margem_pct or 0),
            (c.vetor_O.prazo_semanas or 9999),
            (c.vetor_O.fe_nec_medio or 9999),
            c.cenario_id,
        ),
    )

    shortlist = []
    for i, c in enumerate(ranked[:top_k]):
        c.rank_final = i + 1
        motivo = (
            "pareto_intersecao"
            if c.pareto_intersecao
            else ("pareto_EF" if c.pareto_EF else "melhor_viavel")
        )
        shortlist.append(
            CenarioRankeado(
                rank=i + 1,
                cenario=c,
                justificativa=_build_justificativa(c, motivo),
            )
        )
    return shortlist


def classificar_bundle(cenarios: list[CenarioAvaliado]) -> CampaignStatus:
    viaveis = [c for c in cenarios if c.viabilidade in {"APROVADO", "APROVADO_COM_RESSALVAS"}]
    falhas = [c for c in cenarios if c.erro]
    if not viaveis:
        return "ABORTADO" if len(falhas) == len(cenarios) else "INFEASIBLE"
    intersecao = [c for c in viaveis if c.pareto_intersecao]
    if intersecao:
        return "SUCESSO"
    pareto_O = [c for c in viaveis if c.pareto_O]
    pareto_EF = [c for c in viaveis if c.pareto_EF]
    if pareto_O and pareto_EF and not intersecao:
        return "FRONTEIRA_UNICA"
    return "SUCESSO_PARCIAL"


# ---------------------------------------------------------------------------
# Main runner
# ---------------------------------------------------------------------------


def executar_campanha(
    bundle: GoResearchCampaignBundle,
    config_root: str | Path,
    projects_root: str | Path,
    num_workers: int = 3,
    reset: bool = True,
) -> CampaignOutputBundle:
    """Execute a full campaign: generate grid, evaluate, curate, return bundle."""
    import threading

    from concilium.application.benchmarks.report_builder import BenchmarkReportBuilder
    from concilium.application.benchmarks.runner import BenchmarkRunner
    from concilium.application.benchmarks.spec_loader import load_spec_from_dict

    try:
        from concilium.presentation.cli._commands_benchmark_helpers import _make_silent_printer
        silent_printer = _make_silent_printer()
    except Exception:
        from concilium.application.benchmarks.report_printer import BenchmarkReportPrinter

        class _SilentPrinterImpl(BenchmarkReportPrinter):
            def print(self, report: dict) -> None:  # noqa: A003
                pass

        silent_printer = _SilentPrinterImpl()

    # Serialize project-store access to avoid concurrent create races.
    _store_lock = threading.Lock()

    grid = gerar_grid(bundle)
    cenarios: list[CenarioAvaliado] = []
    prazo_cont = bundle.perfil_expectativas.prazo_contratual_semanas

    def _avaliar_um(spec_v: dict, variados: dict) -> CenarioAvaliado:
        cid = cenario_id(variados)
        try:
            # Ensure the slug/id round-trips correctly through the spec loader.
            # v2 schema uses "slug" at the top level; spec_loader uses ref.get("id").
            # Inject "id" from "slug" so _infer_slug_from_path is not needed.
            spec_with_id = dict(spec_v)
            base_slug = spec_with_id.get("slug") or spec_with_id.get("id") or "UNKNOWN"
            # Each scenario needs a unique project name AND slug so the BenchmarkRunner
            # creates a separate project directory (it matches by nome, not slug).
            scenario_slug = f"{base_slug}-{cid[:6]}"
            spec_with_id["slug"] = scenario_slug
            # Patch meta.projeto so the project nome is unique per scenario.
            meta = dict(spec_with_id.get("meta") or {})
            base_nome = meta.get("projeto", base_slug)
            meta["projeto"] = f"{base_nome} [{cid[:6]}]"
            spec_with_id["meta"] = meta
            # Write to unique data dir so _infer_slug_from_path also gives the scenario slug.
            benchmarks_root = Path(projects_root).parent
            scenario_dir = benchmarks_root / "data" / scenario_slug
            scenario_dir.mkdir(parents=True, exist_ok=True)
            ref_path = scenario_dir / "referencia.json"
            ref_path.write_text(json.dumps(spec_with_id, ensure_ascii=False, default=str))
            spec_obj = load_spec_from_dict(spec_with_id, ref_path)
            # Apply post-load overrides (campos com prefixo "inputs_") diretamente no spec_obj
            _apply_post_load_overrides(spec_obj, variados)
            runner = BenchmarkRunner(
                config_root=Path(config_root),
                projects_root=Path(projects_root),
                report_builder=BenchmarkReportBuilder(),
                report_printer=silent_printer,
            )
            # skip_artifacts=True: pula skills pesadas (09 relatório, 10 criticidade)
            # e não gera PNGs/PDFs — suficiente para coletar I_O e I_EF.
            with _store_lock:
                report = runner.run(spec_obj, reset=reset, skip_artifacts=True)
            # Load canonical — try exact slug, uppercase, and lowercase
            _slug = spec_obj.slug
            canonical = {}
            for _try in (_slug, _slug.upper(), _slug.lower()):
                _can = Path(projects_root) / _try / "v1" / "canonical.json"
                if _can.exists():
                    canonical = json.loads(_can.read_text())
                    break

            v_O = extrair_vetor_O(canonical, prazo_cont)
            v_EF = extrair_vetor_EF(canonical, report)
            decision = (report.get("quality_gates") or {}).get("decision") or "BLOQUEADO"
            via_map: dict[str, ViabilidadeStatus] = {
                "APROVADO": "APROVADO",
                "APROVADO_COM_RESSALVAS": "APROVADO_COM_RESSALVAS",
                "BLOQUEADO_COM_INVESTIGACAO": "BLOQUEADO_COM_INVESTIGACAO",
                "BLOQUEADO": "BLOQUEADO",
            }
            viabilidade: ViabilidadeStatus = via_map.get(decision, "ERRO")
            cl_O = classificar_O(v_O, bundle.perfil_expectativas)
            cl_EF = classificar_EF(v_EF, bundle.perfil_expectativas)
            return CenarioAvaliado(
                cenario_id=cid,
                parametros_variados=variados,
                viabilidade=viabilidade,
                vetor_O=v_O,
                vetor_EF=v_EF,
                classificacao_O=cl_O,
                classificacao_EF=cl_EF,
            )
        except Exception as exc:
            return CenarioAvaliado(
                cenario_id=cid,
                parametros_variados=variados,
                viabilidade="ERRO",
                vetor_O=VetorEspacoO(),
                vetor_EF=VetorEspacoEF(),
                classificacao_O="CRITICO",
                classificacao_EF="FORA_EXPECTATIVA",
                erro=str(exc),
            )

    with concurrent.futures.ThreadPoolExecutor(max_workers=num_workers) as executor:
        futures = {executor.submit(_avaliar_um, sv, var): (sv, var) for sv, var in grid}
        for future in concurrent.futures.as_completed(futures):
            cenarios.append(future.result())

    shortlist = curar_shortlist(cenarios, bundle.top_k, bundle.perfil_expectativas)
    status = classificar_bundle(cenarios)
    viaveis = [c for c in cenarios if c.viabilidade in {"APROVADO", "APROVADO_COM_RESSALVAS"}]

    return CampaignOutputBundle(
        campaign_id=bundle.campaign_id,
        campaign_version=bundle.campaign_version,
        gerado_em=datetime.now(timezone.utc),
        n_cenarios_avaliados=len(cenarios),
        n_cenarios_viaveis=len(viaveis),
        n_falhas=sum(1 for c in cenarios if c.erro),
        status=status,
        cenarios=cenarios,
        shortlist=shortlist,
    )
