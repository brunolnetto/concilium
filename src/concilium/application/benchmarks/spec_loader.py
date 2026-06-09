from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import date, timedelta
from pathlib import Path
from typing import Any

from concilium.infrastructure.catalog.catalog_loader import CatalogLoader

from ._spec_loader_helpers_a import (
    _ebr_apply_fallbacks,
    _ebr_from_por_item,
    _ebr_from_stats,
    _norm_ref_atividades_to_eap,
    _norm_ref_datas_block,
    _norm_ref_ensure_rcpsp_spec,
    _norm_ref_metas_confronto,
    _norm_ref_projeto_block,
)
from ._spec_loader_helpers_b import (
    _bii_build_detalhe_por_cat,
    _bii_build_entry,
    _bii_scale_categories,
    _bs_lfd_build_bdi_section,
    _ea_normalize_itens_eap,
    _eei_find_best_match,
    _lfd_parse_raw_row,
)
from .input_derivation import BenchmarkInputDeriver


@dataclass
class ProjectSpec:
    """Especificacao completa de um projeto para benchmark."""

    nome: str
    slug: str
    contexto_id: str = "mendeslobo"
    contexto_version: str | None = None  # ADR-062: version resolved at load time
    perfil_id: str | None = None  # ADR-062: from versioned context
    perfil_version: str | None = None  # ADR-062: version resolved at load time
    referencia_path: Path | None = None
    inputs_escopo: dict = field(default_factory=dict)
    inputs_01A: dict = field(default_factory=dict)
    inputs_cronograma: dict = field(default_factory=dict)
    inputs_indiretos: dict = field(default_factory=dict)
    extra_inputs: dict = field(default_factory=dict)


def iso_weeks(start: str, end: str) -> list[str]:
    """Gera lista de chaves ISO-week entre duas datas."""

    current = date.fromisoformat(start)
    end_date = date.fromisoformat(end)
    seen: dict[str, None] = {}
    while current <= end_date:
        iso = current.isocalendar()
        seen[f"{iso.year}-W{iso.week:02d}"] = None
        current += timedelta(weeks=1)
    return list(seen.keys())


# ── Helpers para _normalize_reference_schema ─────────────────────────────────
# ─────────────────────────────────────────────────────────────────────────────
_EBR_KEY_MAP: dict[str, str] = {
    "materiais": "material",
    "material": "material",
    "diesel": "diesel",
    "mao_obra": "mao_obra",
    "equipamentos": "equipamentos",
    "servicos": "servicos",
    "indireto": "indireto",
}


def _unpack_v2_schema(ref: dict[str, Any]) -> dict[str, Any]:
    """Converte schema v2 (meta+spec+resultado) para formato v1-compatível com o pipeline.

    Schema v2 é detectado pela presença da chave 'spec' no dict raiz.
    A estrutura v2 é mais limpa e compacta; esta função expande para o formato
    que o resto do pipeline (spec_loader + input_deriver) já sabe consumir.

    Mapeamento:
        meta.*                  → campos raiz (projeto, data_inicio, …)
        spec.eap                → ref["eap"]
        spec.rcpsp_spec         → ref["rcpsp_spec"]
        spec.cronograma[]       → ref["cronograma"]["atividades"] (+ quantitativo da eap)
        spec.planejamento[]     → ref["planejamento_detalhado"] (subtotal aninhado)
        spec.bdi                → ref["bdi"]
        spec.indiretos[]        → ref["indiretos_detalhamento"] + ref["equipes_indiretas"]
        spec.diretos            → ref["equipes_detalhadas"]
        spec.cenarios           → ref["cenarios"]
        resultado               → ref["resultado"]  (mantido no topo)
    """
    meta = ref.get("meta") or {}
    spec = ref.get("spec") or {}

    out: dict[str, Any] = {}

    # 1. meta → campos raiz
    out["projeto"] = meta.get("projeto", "")
    out["data_inicio"] = meta.get("data_inicio", "")
    out["data_termino"] = meta.get("data_termino", "")
    # localizacao aceita string ("Brasil") ou {lat, lng} — ambos propagados downstream
    out["localizacao"] = meta.get("localizacao", "")
    out["regime_trabalho"] = meta.get("regime_trabalho", {"horas_dia": 8, "dias_semana": 6})
    out["mode"] = meta.get("mode", "benchmark_config")

    # 2. eap direto
    out["eap"] = spec.get("eap") or []
    eap_by_id: dict[str, Any] = {item["item_id"]: item for item in out["eap"] if "item_id" in item}

    # 3. rcpsp_spec (inalterado)
    out["rcpsp_spec"] = spec.get("rcpsp_spec") or {}

    # 4. cronograma: propaga formato compacto E constrói atividades v1 (retrocompat)
    # Formato compacto: {item_id, duration_weeks, equipes: {n_inicial, n_max, taxa_mob, taxa_demob}}
    # Formato legado:   {item_id, producao_diaria, quantitativo, semanas}
    atividades = []
    cron_compacto = []
    for item in spec.get("cronograma") or []:
        item_id = item["item_id"]
        eap_item = eap_by_id.get(item_id, {})
        # Formato compacto (novo) — preserva equipes e duration_weeks
        compact: dict[str, Any] = {"item_id": item_id}
        if "duration_weeks" in item:
            compact["duration_weeks"] = item["duration_weeks"]
        if "equipes" in item:
            compact["equipes"] = item["equipes"]
        if "producao_diaria" in item:
            compact["producao_diaria"] = item["producao_diaria"]
        cron_compacto.append(compact)
        # Legado: mantém compatibilidade com input_deriver e demais consumidores
        atividades.append(
            {
                "item_id": item_id,
                "producao_diaria": item.get("producao_diaria", 0.0),
                "quantitativo": eap_item.get("quantitativo", 0.0),
                "semanas": item.get("semanas") or {},
                # Propaga campos compactos para consumers que os conhecem
                "duration_weeks": item.get("duration_weeks"),
                "equipes": item.get("equipes"),
            }
        )
    out["cronograma"] = {"atividades": atividades}
    # Expõe a lista compacta direta para _norm_ref_build_rcpsp_activities
    out["cronograma_compacto"] = cron_compacto

    # 5. planejamento: flat v2 → subtotal aninhado v1
    planejamento_detalhado = []
    for item in spec.get("planejamento") or []:
        item_id = item["item_id"]
        eap_item = eap_by_id.get(item_id, {})
        planejamento_detalhado.append(
            {
                "item_id": item_id,
                "cpu_id": eap_item.get("cpu_id", ""),
                "quantitativo": eap_item.get("quantitativo", 0.0),
                "subtotal": {
                    "sem_bdi": {"total": item.get("custo_sem_bdi", 0.0)},
                    "com_bdi": {"total": item.get("custo_com_bdi", 0.0)},
                },
            }
        )
    out["planejamento_detalhado"] = planejamento_detalhado

    # 6. bdi
    out["bdi"] = spec.get("bdi") or {}

    # 7. indiretos[] → indiretos_detalhamento (dict) + equipes_indiretas (lista)
    #    driver "mensal"  → custo_fixo_mensal_total  (multiplicado por duração no pipeline)
    #    driver "projeto" → custo_fixo_total          (custo único, ex: mobilização)
    indiretos_detalhamento: dict[str, Any] = {}
    equipes_indiretas: list[dict[str, Any]] = []
    for ind in spec.get("indiretos") or []:
        cat = ind["categoria"]
        driver = ind.get("driver", "mensal")
        if driver == "projeto":
            indiretos_detalhamento[cat] = {"custo_fixo_total": ind.get("custo_fixo_total", 0.0)}
        else:
            indiretos_detalhamento[cat] = {"custo_fixo_mensal_total": ind.get("custo_fixo_mensal_total", 0.0)}
        mao_obra = ind.get("mao_obra") or []
        if mao_obra:
            equipes_indiretas.append({"id": f"INDIR-{cat}", "categoria": cat, "mao_obra": mao_obra})
    out["indiretos_detalhamento"] = indiretos_detalhamento
    out["equipes_indiretas"] = equipes_indiretas

    # 8. diretos → equipes_detalhadas
    out["equipes_detalhadas"] = spec.get("diretos") or []

    # 9. cenarios
    out["cenarios"] = spec.get("cenarios") or []

    # 10. resultado (já está no topo em v2)
    out["resultado"] = ref.get("resultado") or {}

    return out


# ── Helpers for BenchmarkSpecLoader.load_from_dict ──────────────────────────────
# ── Helpers for BenchmarkSpecLoader._enrich_eap_with_cpu_ids ────────────────────
# ── Helpers for BenchmarkSpecLoader._build_inputs_indiretos ─────────────────────
class BenchmarkSpecLoader:
    """Carrega referencia.json e produz um ProjectSpec compatível com o runner."""

    def __init__(self, config_root: Path) -> None:
        self._config_root = config_root
        self._project_root = self._config_root.parent
        self._input_deriver = BenchmarkInputDeriver(config_root)

    # ADR-062: resolve versioned context before loading spec
    def resolve_contexto(self, contexto_id: str, version: str | None = None) -> dict[str, Any] | None:
        """Resolve contexto by id and optional version (ADR-062)."""
        try:
            from concilium.application.services.contexto_version_service import ContextoVersionService

            svc = ContextoVersionService(self._config_root)
            return svc.resolve(contexto_id, version)
        except Exception:
            return None

    def load(self, path: Path | str) -> ProjectSpec:
        path = Path(path).resolve()
        with open(path, encoding="utf-8") as file_obj:
            ref = json.load(file_obj)
        return self.load_from_dict(ref, path)

    def _lfd_resolve_context(self, ref: dict[str, Any], contexto_id: str) -> tuple:
        """ADR-062: resolve versioned context and merge config fields into ref."""
        ctx_version = None
        perfil_id = None
        perfil_version = None
        try:
            from concilium.application.services.contexto_version_service import (
                ContextoVersionService,
                PerfilVersionService,
            )

            ctx_svc = ContextoVersionService(self._config_root)
            versioned_ctx = ctx_svc.resolve(contexto_id)
            if versioned_ctx:
                ctx_version = versioned_ctx.get("version")
                for k in ("catalogo_id", "jurisdicao_id", "perfil_id", "referencia_id"):
                    if k in versioned_ctx and versioned_ctx[k] and not ref.get(k):
                        ref[k] = versioned_ctx[k]
                perfil_id = versioned_ctx.get("perfil_id")
                if perfil_id:
                    perf_svc = PerfilVersionService(self._config_root)
                    versioned_perf = perf_svc.resolve(perfil_id)
                    if versioned_perf:
                        perfil_version = versioned_perf.get("version")
        except Exception:
            pass
        return ctx_version, perfil_id, perfil_version

    def _lfd_build_bdi_section(self, extra_inputs: dict, ref: dict[str, Any], bdi_ref: dict) -> dict:
        return _bs_lfd_build_bdi_section(self, extra_inputs, ref, bdi_ref)

    def _lfd_build_ind_ref(self, ref: dict[str, Any], weeks: list) -> dict:
        """Converts raw_indiretos list to ind_ref dict when indiretos_detalhamento absent."""
        ind_ref = ref.get("indiretos_detalhamento", {})
        if ind_ref:
            return ind_ref
        indiretos_block = ref.get("indiretos") or {}
        raw_indiretos = indiretos_block.get("raw_indiretos") if isinstance(indiretos_block, dict) else None
        if not isinstance(raw_indiretos, list):
            return {}
        converted: dict = {}
        fallback_meses = max(len(weeks) / 4.34, 1.0)
        for row in raw_indiretos:
            parsed = _lfd_parse_raw_row(row, fallback_meses)
            if parsed is None:
                continue
            cat, custo_total, permanencia = parsed
            if cat == "MOB":
                converted[cat] = {"custo_fixo_total": round(custo_total, 2)}
            else:
                converted[cat] = {"custo_fixo_mensal_total": round(custo_total / permanencia, 2)}
        return converted

    def load_from_dict(self, ref: dict[str, Any], path: Path | str) -> ProjectSpec:
        """Carrega ProjectSpec a partir de um dict ja parseado (sem re-ler o disco)."""
        path = Path(path).resolve()
        ref = self._normalize_reference_schema(ref)

        contexto_id = ref.get("contexto_id") or "mendeslobo"
        _ctx_version, _perfil_id, _perfil_version = self._lfd_resolve_context(ref, contexto_id)

        data_ini = ref.get("data_inicio", "2025-01-01")
        data_fim = ref.get("data_termino", "2025-06-30")
        weeks = iso_weeks(data_ini, data_fim)
        eap = self._extract_eap(ref)
        eap = self._enrich_eap_with_cpu_ids(eap)

        res = ref.get("resultado", {})
        bdi_meta = res.get("bdi_lucro_impostos", 0.15)
        slug = ref.get("id") or self._infer_slug_from_path(path)
        num_equipes_por_item = self._input_deriver.derive_num_equipes_por_item(ref, eap, weeks)

        consolidacao_inputs = {"bdi_lucro_impostos": bdi_meta}
        extra_inputs: dict = {
            "06-consolidar": consolidacao_inputs,
            "08-consolidacao-financeira": consolidacao_inputs,
        }

        # Permite override de BDI por referência quando disponível, com fallback termo-a-termo.
        bdi_ref = ref.get("bdi") or {}
        if isinstance(bdi_ref, dict) and bdi_ref:
            extra_inputs = self._lfd_build_bdi_section(extra_inputs, ref, bdi_ref)

        # NEP-030 D3: planejamento_item_overrides NÃO é mais injetado da referência.
        # Per-item cost overrides substituem o cálculo do algoritmo.
        # Se necessário no futuro, deve ser um mecanismo explícito e separado do arquivo
        # de referência (ex: config/overrides/{projeto}/planejamento.json).

        ind_ref = self._lfd_build_ind_ref(ref, weeks)
        inputs_indiretos = self._build_inputs_indiretos(
            ind_ref=ind_ref,
            weeks=weeks,
            referencia_indireto_total=res.get("custo_indireto_total"),
            equipes_indiretas=ref.get("equipes_indiretas") or [],
        )

        extra_inputs["11-avaliacao-intervencoes"] = {
            "intervencoes_propostas": [
                {
                    "nome": "Baseline Automatica",
                    "custo_estimado": 0,
                    "impacto_prazo_semanas": 0,
                    "justificativa": "Ponto de partida para benchmark de engenharia.",
                }
            ]
        }
        extra_inputs["12-registro-decisoes"] = {
            "objective": "Aprovacao de Baseline para Auditoria Financeira",
            "considered_interventions": [
                {
                    "nome": "Baseline Automatica",
                    "variavel": "baseline",
                    "custo_estimado": 0,
                    "impacto_prazo_semanas": 0,
                    "justificativa": "Ponto de partida para benchmark de engenharia.",
                }
            ],
            "selected_intervention": "baseline",
            "justification": {
                "main_reason": "Alinhamento com dados de referencia historicos.",
                "rejected_reasons": {},
            },
            "decided_by": {
                "type": "system",
                "id": "benchmark_runner",
            },
        }

        # ADR-071: repassa rcpsp_spec para skill-05 para que possa calcular
        # contratos de pool e atribuir custos proporcionalmente ao uso.
        if ref.get("rcpsp_spec"):
            extra_inputs["05-equipes-e-alocacao"] = {"rcpsp_spec": ref["rcpsp_spec"]}

        return ProjectSpec(
            nome=ref.get("projeto", slug),
            slug=slug,
            contexto_id=contexto_id,
            contexto_version=_ctx_version,
            perfil_id=_perfil_id,
            perfil_version=_perfil_version,
            referencia_path=path,
            inputs_escopo={
                "nome": ref.get("projeto", slug),
                "tipo_obra": "terraplenagem",
                # localizacao: string legada OU {lat, lng} normalizado. coordenadas é
                # alias retrocompat — se localizacao já é {lat,lng}, reusa o mesmo dict.
                "localizacao": ref.get("localizacao", "Brasil"),
                "coordenadas": (
                    ref.get("localizacao")
                    if isinstance(ref.get("localizacao"), dict)
                    else ref.get("coordenadas", {"lat": 0.0, "lng": 0.0})
                ),
                "regime_trabalho": ref.get("regime_trabalho", {"horas_dia": 8, "dias_semana": 6}),
                "data_inicio": data_ini,
                "data_termino": data_fim,
                "eap": [item for item in eap if item.get("cpu_id")],
            },
            inputs_cronograma={
                "num_equipes_por_item": num_equipes_por_item,
                **({"rcpsp_spec": ref["rcpsp_spec"]} if ref.get("rcpsp_spec") else {}),
            },
            inputs_indiretos=inputs_indiretos,
            extra_inputs=extra_inputs,
        )

    @staticmethod
    def _infer_slug_from_path(path: Path) -> str:
        """Infere slug do benchmark a partir do caminho da referência.

        Casos suportados:
        - benchmarks/data/<SLUG>/referencia.json
        - benchmarks/data/<SLUG>/artifacts/inputs/referencia.json
        """
        parent = path.parent
        if parent.name.lower() == "inputs" and parent.parent.name.lower() == "artifacts":
            candidate = parent.parent.parent.name
            if candidate:
                return candidate
        return parent.name

    def _normalize_reference_schema(self, ref: dict[str, Any]) -> dict[str, Any]:
        """Normaliza schemas de referência para o formato legado esperado pelo loader.

        Compatibiliza o novo modo `benchmark_config` sem quebrar referências antigas.
        Suporta schema v2 (meta+spec+resultado) quando a chave 'spec' está presente.
        """
        if not isinstance(ref, dict):
            return ref
        # v2: presença de 'spec' indica schema reorganizado → normaliza para v1-compat
        if "spec" in ref:
            ref = _unpack_v2_schema(ref)
        mode = str(ref.get("mode") or "").strip().lower()
        if mode != "benchmark_config":
            return ref
        out = dict(ref)
        projeto_block = out.get("projeto") if isinstance(out.get("projeto"), dict) else {}
        datas_block = out.get("datas") if isinstance(out.get("datas"), dict) else {}
        regime_block = out.get("regime") if isinstance(out.get("regime"), dict) else {}
        _norm_ref_projeto_block(out, projeto_block)  # type: ignore[arg-type]
        _norm_ref_datas_block(out, datas_block)  # type: ignore[arg-type]
        if regime_block and not out.get("regime_trabalho"):
            out["regime_trabalho"] = {
                "horas_dia": regime_block.get("horas_dia", 8),  # type: ignore[union-attr]
                "dias_semana": regime_block.get("dias_semana", 6),  # type: ignore[union-attr]
            }
        _norm_ref_atividades_to_eap(out)
        _norm_ref_metas_confronto(out)
        _norm_ref_ensure_rcpsp_spec(out)
        return out

    @staticmethod
    def _extract_eap(ref: dict[str, Any]) -> list[dict[str, Any]]:
        """Extrai EAP em formatos de referência distintos.

        Suporta:
        - Formato canônico de benchmark: ref["eap"]
        - Formato de iteração extraída: ref["cpus"]["itens_eap"]
        """
        eap_direct = ref.get("eap")
        if isinstance(eap_direct, list) and eap_direct:
            return eap_direct
        itens_eap = (ref.get("cpus") or {}).get("itens_eap")
        if not (isinstance(itens_eap, list) and itens_eap):
            return []
        return _ea_normalize_itens_eap(itens_eap)

    @staticmethod
    def _extract_bdi_rates(ref: dict[str, Any]) -> dict[str, float]:
        """Extrai BDI final por categoria em referências no formato extraído.

        Fontes suportadas:
        - ref["bdi"]["estatisticas_componentes"][<categoria>]["media"]
        - ref["bdi"]["por_item"][*]["bdi"][<categoria>] (fallback)
        """
        bdi_ref = ref.get("bdi") or {}
        stats = bdi_ref.get("estatisticas_componentes") or {}
        mapped = _ebr_from_stats(stats)
        if not mapped:
            mapped = _ebr_from_por_item(bdi_ref)
        _ebr_apply_fallbacks(mapped)
        return mapped

    def _enrich_eap_with_cpu_ids(self, eap: list[dict[str, Any]]) -> list[dict[str, Any]]:
        if not eap:
            return eap
        if all(item.get("cpu_id") for item in eap):
            return eap
        try:
            loader = CatalogLoader(
                config_root=self._config_root,
                project_root=self._project_root,
                offline=False,
                force_refresh=False,
            )
            snapshot, _ = loader.load("mendeslobo")
        except Exception as exc:
            print(f"  [WARN] Falha ao carregar catalogo para normalizar EAP: {exc}")
            return eap
        cpus = snapshot.cpus or []
        cpu_by_codigo = {cpu.get("codigo"): cpu for cpu in cpus if cpu.get("codigo")}
        for item in eap:
            _eei_find_best_match(item, cpus, cpu_by_codigo)
        return eap

    @staticmethod
    def _build_inputs_indiretos(
        ind_ref: dict[str, Any],
        weeks: list[str],
        referencia_indireto_total: float | None,
        equipes_indiretas: list[dict[str, Any]] | None = None,
    ) -> dict[str, Any]:
        if not ind_ref:
            return {}
        detalhe_por_cat = _bii_build_detalhe_por_cat(equipes_indiretas or [])
        permanencia_meses = len(weeks) / 4.34
        categorias_config = [_bii_build_entry(cat, data, detalhe_por_cat) for cat, data in ind_ref.items() if data]
        if not categorias_config:
            return {}
        _bii_scale_categories(categorias_config, referencia_indireto_total, permanencia_meses)
        return {"categorias_config": categorias_config}


def load_spec_from_json(path: Path | str) -> ProjectSpec:
    from concilium.infrastructure.settings import get_storage

    config_root = get_storage().config_root
    return BenchmarkSpecLoader(config_root).load(path)


def load_spec_from_dict(ref: dict[str, Any], path: Path | str) -> ProjectSpec:
    """Carrega ProjectSpec a partir de um dict ja em memoria (sem I/O de disco)."""
    from concilium.infrastructure.settings import get_storage

    config_root = get_storage().config_root
    return BenchmarkSpecLoader(config_root).load_from_dict(ref, path)
