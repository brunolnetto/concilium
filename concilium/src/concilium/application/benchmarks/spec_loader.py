from __future__ import annotations

import json
import os
import re
import unicodedata
from dataclasses import dataclass, field
from datetime import date, timedelta
from pathlib import Path
from typing import Any

from concilium.infrastructure.catalog.catalog_loader import CatalogLoader

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


def _norm_ref_projeto_block(out: dict[str, Any], projeto_block: dict[str, Any]) -> None:
    if not projeto_block:
        return
    nome = projeto_block.get("nome") or projeto_block.get("projeto")
    if nome and not isinstance(out.get("projeto"), str):
        out["projeto"] = nome
    if projeto_block.get("localizacao") and not out.get("localizacao"):
        out["localizacao"] = projeto_block.get("localizacao")
    if projeto_block.get("coordenadas") and not out.get("coordenadas"):
        out["coordenadas"] = projeto_block.get("coordenadas")


def _norm_ref_datas_block(out: dict[str, Any], datas_block: dict[str, Any]) -> None:
    if not datas_block:
        return
    if datas_block.get("data_inicio") and not out.get("data_inicio"):
        out["data_inicio"] = datas_block.get("data_inicio")
    if datas_block.get("data_termino") and not out.get("data_termino"):
        out["data_termino"] = datas_block.get("data_termino")


def _norm_ref_atividade_item(atividade: Any, idx: int) -> dict[str, Any] | None:
    if not isinstance(atividade, dict):
        return None
    item_id = atividade.get("item_id")
    cpu_id = atividade.get("cpu_id")
    if not item_id or not cpu_id:
        return None
    return {
        "item_id": str(item_id),
        "ordem": int(atividade.get("ordem") or idx),
        "cpu_id": str(cpu_id),
        "descricao": str(atividade.get("descricao") or item_id),
        "unidade": str(atividade.get("unidade") or "un"),
        "quantitativo": float(atividade.get("quantitativo") or 0.0),
    }


def _norm_ref_atividades_to_eap(out: dict[str, Any]) -> None:
    atividades = out.get("atividades")
    if not isinstance(atividades, list) or not atividades:
        return
    if out.get("eap") or (out.get("cpus") or {}).get("itens_eap"):
        return
    eap = [item for item in (_norm_ref_atividade_item(a, i) for i, a in enumerate(atividades, 1)) if item is not None]
    if eap:
        out["eap"] = eap


def _norm_ref_metas_confronto(out: dict[str, Any]) -> None:
    metas = out.get("metas_confronto") if isinstance(out.get("metas_confronto"), dict) else {}
    if not metas:
        return
    resultado = out.get("resultado") if isinstance(out.get("resultado"), dict) else {}
    if "benchmark_confronto_referencia" not in resultado:  # type: ignore[operator]
        resultado["benchmark_confronto_referencia"] = {  # type: ignore[index]
            "custo_direto": metas.get("custo_direto"),
            "custo_indireto": metas.get("custo_indireto"),
            "custo_total": metas.get("custo_total"),
            "preco_venda": metas.get("preco_venda"),
        }
    out["resultado"] = resultado


def _norm_ref_parse_atividade_duration(atividade: dict[str, Any], weeks: list[str]) -> int:
    duration = atividade.get("duration_weeks") or atividade.get("duracao_semanas")
    try:
        return int(duration) if duration is not None else max(1, len(weeks))
    except Exception:
        return max(1, len(weeks))


def _norm_ref_build_rcpsp_activities(out: dict[str, Any], weeks: list[str]) -> list[dict[str, Any]]:
    atividades = out.get("atividades") if isinstance(out.get("atividades"), list) else []
    activities: list[dict[str, Any]] = []
    for atividade in atividades:  # type: ignore[union-attr]
        if not isinstance(atividade, dict):
            continue
        item_id = atividade.get("item_id")
        if not item_id:
            continue
        required_resources = atividade.get("required_resources")
        if not isinstance(required_resources, dict):
            required_resources = atividade.get("recursos") if isinstance(atividade.get("recursos"), dict) else {}
        activities.append(
            {
                "item_id": str(item_id),
                "descricao": str(atividade.get("descricao") or item_id),
                "duration_weeks": max(1, _norm_ref_parse_atividade_duration(atividade, weeks)),
                "required_resources": required_resources,
            }
        )
    return activities


def _norm_ref_build_default_rcpsp_spec(out: dict[str, Any], rcpsp_block: dict[str, Any]) -> dict[str, Any]:
    data_ini = out.get("data_inicio", "2025-01-01")
    data_fim = out.get("data_termino", "2025-06-30")
    weeks = iso_weeks(data_ini, data_fim)
    activities = _norm_ref_build_rcpsp_activities(out, weeks)
    resource_pool: dict[str, Any] = out.get("resource_pool") if isinstance(out.get("resource_pool"), dict) else {}  # type: ignore[assignment]
    if not resource_pool:
        restr = out.get("restricao_equipes")
        if isinstance(restr, dict):
            resource_pool = restr
    return {
        "deadline_weeks": int(rcpsp_block.get("deadline_weeks") or len(weeks) or 1),  # type: ignore[union-attr]
        "activities": activities,
        "resource_pool": resource_pool,
        "precedence": rcpsp_block.get("precedence") or [],  # type: ignore[union-attr]
    }


def _norm_ref_ensure_rcpsp_spec(out: dict[str, Any]) -> None:
    if out.get("rcpsp_spec"):
        return
    rcpsp_block = out.get("rcpsp") if isinstance(out.get("rcpsp"), dict) else {}
    params_block = out.get("parametros_simulacao") if isinstance(out.get("parametros_simulacao"), dict) else {}
    rcpsp_from_params = (
        params_block.get("rcpsp_spec") if isinstance(params_block.get("rcpsp_spec"), dict) else {}  # type: ignore[union-attr]
    )
    rcpsp_spec = dict(rcpsp_block or rcpsp_from_params)  # type: ignore[arg-type]
    if not rcpsp_spec:
        rcpsp_spec = _norm_ref_build_default_rcpsp_spec(out, rcpsp_block)  # type: ignore[arg-type]
    out["rcpsp_spec"] = rcpsp_spec


# ─────────────────────────────────────────────────────────────────────────────


def _ebr_as_float(v: Any) -> float | None:
    try:
        return None if v is None else float(v)
    except Exception:
        return None


_EBR_KEY_MAP: dict[str, str] = {
    "materiais": "material",
    "material": "material",
    "diesel": "diesel",
    "mao_obra": "mao_obra",
    "equipamentos": "equipamentos",
    "servicos": "servicos",
    "indireto": "indireto",
}


def _ebr_from_stats(stats: Any) -> dict[str, float]:
    if not isinstance(stats, dict):
        return {}
    result: dict[str, float] = {}
    for src_key, dst_key in _EBR_KEY_MAP.items():
        raw = stats.get(src_key)
        if isinstance(raw, dict):
            rate = _ebr_as_float(raw.get("media"))
            if rate is not None:
                result[dst_key] = rate
    return result


def _ebr_from_por_item(bdi_ref: dict[str, Any]) -> dict[str, float]:
    por_item = bdi_ref.get("por_item") or []
    if not (isinstance(por_item, list) and por_item):
        return {}
    sample = por_item[0] if isinstance(por_item[0], dict) else {}
    bdi_item = sample.get("bdi") if isinstance(sample, dict) else {}
    if not isinstance(bdi_item, dict):
        return {}
    result: dict[str, float] = {}
    for src_key, dst_key in _EBR_KEY_MAP.items():
        rate = _ebr_as_float(bdi_item.get(src_key))
        if rate is not None:
            result[dst_key] = rate
    return result


def _ebr_apply_fallbacks(mapped: dict[str, float]) -> None:
    if "servicos" not in mapped and "equipamentos" in mapped:
        mapped["servicos"] = mapped["equipamentos"]
    if "servicos" not in mapped and "mao_obra" in mapped:
        mapped["servicos"] = mapped["mao_obra"]


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

    def load_from_dict(self, ref: dict[str, Any], path: Path | str) -> ProjectSpec:
        """Carrega ProjectSpec a partir de um dict ja parseado (sem re-ler o disco)."""
        path = Path(path).resolve()
        ref = self._normalize_reference_schema(ref)

        # ADR-062: resolve versioned context and merge its config fields into ref
        contexto_id = ref.get("contexto_id") or "mendeslobo"
        _ctx_version: str | None = None
        _perfil_id: str | None = None
        _perfil_version: str | None = None
        try:
            from concilium.application.services.contexto_version_service import (
                ContextoVersionService,
                PerfilVersionService,
            )

            ctx_svc = ContextoVersionService(self._config_root)
            versioned_ctx = ctx_svc.resolve(contexto_id)
            if versioned_ctx:
                _ctx_version = versioned_ctx.get("version")
                # Merge versioned context fields into ref (versioned wins for catalog/jurisdiction)
                for k in ("catalogo_id", "jurisdicao_id", "perfil_id", "referencia_id"):
                    if k in versioned_ctx and versioned_ctx[k] and not ref.get(k):
                        ref[k] = versioned_ctx[k]
                _perfil_id = versioned_ctx.get("perfil_id")
                if _perfil_id:
                    perf_svc = PerfilVersionService(self._config_root)
                    versioned_perf = perf_svc.resolve(_perfil_id)
                    if versioned_perf:
                        _perfil_version = versioned_perf.get("version")
        except Exception:
            pass

        data_ini = ref.get("data_inicio", "2025-01-01")
        data_fim = ref.get("data_termino", "2025-06-30")
        weeks = iso_weeks(data_ini, data_fim)
        eap = self._extract_eap(ref)
        eap = self._enrich_eap_with_cpu_ids(eap)

        res = ref.get("resultado", {})
        bdi_meta = res.get("bdi_lucro_impostos", 0.15)
        slug = ref.get("id") or self._infer_slug_from_path(path)

        num_equipes_por_item = self._input_deriver.derive_num_equipes_por_item(ref, eap, weeks)

        bdi_ref = ref.get("bdi", {})
        # Importante: não injetar totais de referência no motor de consolidação.
        # Mantemos apenas entradas inevitáveis (ex.: BDI), para exercitar cálculo real.
        consolidacao_inputs = {
            "bdi_lucro_impostos": bdi_meta,
        }
        extra_inputs = {
            "06-consolidar": consolidacao_inputs,
            "08-consolidacao-financeira": consolidacao_inputs,
        }

        if bdi_ref:
            ref_bdi_rates = self._extract_bdi_rates(ref)

            def to_comp(cat_key: str, default_vals: dict[str, float]) -> dict[str, float]:
                raw = bdi_ref.get(cat_key, {})
                if raw:
                    return {
                        "ac": raw.get("ac", default_vals["ac"]),
                        "df": raw.get("df", default_vals["df"]),
                        "r": raw.get("r", default_vals["r"]),
                        "cr": raw.get("cr", default_vals["cr"]),
                        "l": raw.get("lucro", default_vals["l"]),
                        "cofins": raw.get("cofins", default_vals["cofins"]),
                        "iss": raw.get("iss", default_vals["iss"]),
                        "pis": raw.get("pis", default_vals["pis"]),
                        "cssl": raw.get("cssl", default_vals["cssl"]),
                        "ir": raw.get("ir", default_vals["ir"]),
                    }

                # Fallback para referências que trazem apenas BDI final por categoria.
                # Nesse caso, preservamos o percentual no campo AC para manter o total efetivo.
                flat_rate = ref_bdi_rates.get(cat_key)
                if flat_rate is not None:
                    return {
                        "ac": float(flat_rate),
                        "df": 0.0,
                        "r": 0.0,
                        "cr": 0.0,
                        "l": 0.0,
                        "cofins": 0.0,
                        "iss": 0.0,
                        "pis": 0.0,
                        "cssl": 0.0,
                        "ir": 0.0,
                    }

                return {
                    "ac": default_vals["ac"],
                    "df": default_vals["df"],
                    "r": default_vals["r"],
                    "cr": default_vals["cr"],
                    "l": default_vals["l"],
                    "cofins": default_vals["cofins"],
                    "iss": default_vals["iss"],
                    "pis": default_vals["pis"],
                    "cssl": default_vals["cssl"],
                    "ir": default_vals["ir"],
                }

            default_vals = {
                "ac": 0.05,
                "df": 0.015,
                "r": 0.01,
                "cr": 0.0,
                "l": 0.09,
                "cofins": 0.03,
                "iss": 0.05,
                "pis": 0.0065,
                "cssl": 0.0199,
                "ir": 0.0274,
            }
            tabela_bdi = {
                "mao_obra": to_comp("mao_obra", default_vals),
                "material": to_comp(
                    "material",
                    {
                        "ac": 0.05,
                        "df": 0.0,
                        "r": 0.0,
                        "cr": 0.0,
                        "l": 0.0,
                        "cofins": 0.0,
                        "iss": 0.0,
                        "pis": 0.0,
                        "cssl": 0.0,
                        "ir": 0.0,
                    },
                ),
                "servicos": to_comp("servicos", default_vals),
                "indireto": to_comp("indireto", default_vals),
                "diesel": to_comp("diesel", default_vals),
                "data_vigencia": "2026-04-01",
            }
            s04_inputs = extra_inputs.get("06-precificacao-unitaria", {})
            s04_inputs["tabela_bdi"] = tabela_bdi
            extra_inputs["06-precificacao-unitaria"] = s04_inputs

        # ADR-042: derivação estrutural completa como padrão.
        # Quando a referencia.json contiver "planejamento_item_overrides" (preços unitários
        # extraídos diretamente da planilha-fonte), esses valores são injetados no Skill 04
        # para que direto_catalogo corresponda exatamente à referência.
        # Benchmarks sem essa chave continuam com derivação estrutural (backward-compatible).
        ref_item_overrides = ref.get("planejamento_item_overrides")
        if isinstance(ref_item_overrides, dict) and ref_item_overrides:
            s04 = extra_inputs.get("06-precificacao-unitaria", {})
            s04["planejamento_item_overrides"] = ref_item_overrides
            extra_inputs["06-precificacao-unitaria"] = s04

        ind_ref = ref.get("indiretos_detalhamento", {})
        if not ind_ref:
            indiretos_block = ref.get("indiretos") or {}
            raw_indiretos = indiretos_block.get("raw_indiretos") if isinstance(indiretos_block, dict) else None
            if isinstance(raw_indiretos, list):
                converted: dict[str, dict[str, float]] = {}
                fallback_meses = max(len(weeks) / 4.34, 1.0)
                for row in raw_indiretos:
                    if not isinstance(row, dict):
                        continue
                    cat = str(row.get("categoria") or "").strip().upper()
                    if not cat:
                        continue
                    try:
                        custo_total = float(row.get("custo_total") or 0)
                    except Exception:
                        continue
                    try:
                        permanencia = float(row.get("permanencia_meses") or fallback_meses)
                    except Exception:
                        permanencia = fallback_meses
                    if permanencia <= 0:
                        permanencia = fallback_meses
                    if cat == "MOB":
                        # MOB é custo one_time — preserva o total sem rateio mensal
                        converted[cat] = {"custo_fixo_total": round(custo_total, 2)}
                    else:
                        converted[cat] = {
                            "custo_fixo_mensal_total": round(custo_total / permanencia, 2),
                        }
                if converted:
                    ind_ref = converted
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
                "localizacao": ref.get("localizacao", "Brasil"),
                "coordenadas": ref.get("coordenadas", {"lat": 0, "lng": 0}),
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
        """
        if not isinstance(ref, dict):
            return ref
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
        if isinstance(itens_eap, list) and itens_eap:
            normalized: list[dict[str, Any]] = []
            for i, item in enumerate(itens_eap, start=1):
                if not isinstance(item, dict):
                    continue
                item_id = item.get("item_id")
                cpu_id = item.get("cpu_id")
                desc = item.get("descricao")
                unidade = item.get("unidade")
                quantitativo = item.get("quantitativo")
                if not (item_id and cpu_id and desc and unidade and quantitativo):
                    continue
                ordem_raw = item.get("ordem")
                ordem = int(ordem_raw) if isinstance(ordem_raw, (int, float)) else i
                normalized.append(
                    {
                        "item_id": str(item_id),
                        "ordem": ordem,
                        "cpu_id": str(cpu_id),
                        "descricao": str(desc),
                        "unidade": str(unidade),
                        "quantitativo": float(quantitativo),
                    }
                )
            return normalized

        return []

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

        # Fast path: if all items already have cpu_id, skip the full catalog load.
        # This avoids a redundant 600+ file read on every benchmark run when the
        # referencia.json was extracted with explicit CPU mappings (e.g. from planilha).
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
            print(f"  [WARN] Falha ao carregar catálogo para normalizar EAP: {exc}")
            return eap

        cpus = snapshot.cpus or []
        cpu_by_codigo = {cpu.get("codigo"): cpu for cpu in cpus if cpu.get("codigo")}

        def normalize_text(value: str) -> str:
            value = unicodedata.normalize("NFKD", value).encode("ascii", "ignore").decode("ascii")
            value = value.lower()
            value = re.sub(r"[^a-z0-9]+", " ", value)
            return value.strip()

        def normalize_unit(value: str) -> str:
            normalized = normalize_text(value).replace(" ", "")
            normalized = normalized.replace("metros", "m").replace("metro", "m")
            normalized = normalized.replace("quadrados", "2").replace("quadrado", "2")
            normalized = normalized.replace("cubicos", "3").replace("cubico", "3")
            return normalized

        for item in eap:
            cpu_id = item.get("cpu_id")
            if cpu_id and cpu_id in cpu_by_codigo:
                continue

            item_desc = normalize_text(str(item.get("descricao", "")))
            item_unit = normalize_unit(str(item.get("unidade", "")))
            if not item_desc:
                continue

            best_cpu = None
            best_score = -1.0
            item_tokens = set(item_desc.split())

            for cpu in cpus:
                cpu_codigo = cpu.get("codigo")
                cpu_desc = normalize_text(str(cpu.get("descricao", "")))
                if not cpu_codigo or not cpu_desc:
                    continue

                cpu_tokens = set(cpu_desc.split())
                common = len(item_tokens & cpu_tokens)
                if common == 0:
                    continue

                score = common / max(1, len(item_tokens))

                cpu_unit = normalize_unit(str(cpu.get("unidade", "")))
                if item_unit and cpu_unit and item_unit == cpu_unit:
                    score += 0.35
                elif item_unit and cpu_unit and item_unit != cpu_unit:
                    score -= 0.25

                if "dmt" in item_desc and "dmt" in cpu_desc:
                    score += 0.25
                if "regulariz" in item_desc and "subleito" in item_desc and "subleito" in cpu_desc:
                    score += 0.2

                if score > best_score:
                    best_score = score
                    best_cpu = cpu_codigo

            if best_cpu and best_score >= 0.45:
                item["cpu_id"] = best_cpu

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

        # Lookup de composição detalhada por categoria (de equipes_indiretas, se disponível)
        detalhe_por_cat: dict[str, dict] = {}
        for eq in equipes_indiretas or []:
            cat_key = str(eq.get("categoria") or "").upper()
            if cat_key:
                detalhe_por_cat[cat_key] = eq

        permanencia_meses = len(weeks) / 4.34
        categorias_config: list[dict[str, Any]] = []
        for cat, data in ind_ref.items():
            if not data:
                continue
            if cat == "MOB":
                # MOB é one_time — usa custo_fixo_total diretamente
                custo_total_mob = data.get("custo_fixo_total") or data.get("custo_fixo_mensal_total", 0)
                categorias_config.append(
                    {
                        "categoria": cat,
                        "driver": "one_time",
                        "custo_fixo_total": float(custo_total_mob or 0),
                    }
                )
            else:
                custo_mensal = data.get("custo_fixo_mensal_total") or data.get("mao_de_obra_mensal", 0)
                entry: dict[str, Any] = {
                    "categoria": cat,
                    "driver": "permanencia",
                    "custo_fixo_mensal": float(custo_mensal or 0),
                }
                # Inclui composição detalhada de equipes_indiretas quando disponível
                eq_detail = detalhe_por_cat.get(cat)
                if eq_detail and eq_detail.get("mao_obra"):
                    itens = [
                        {
                            "funcao": p.get("funcao", ""),
                            "quantidade": int(p.get("quantidade", 1)),
                            "custo_mensal": float(p.get("custo_unitario", 0) * int(p.get("quantidade", 1))),
                            "salario_base": float(p.get("salario_base", 0)),
                            "tipo_contratacao": p.get("tipo_contratacao", ""),
                        }
                        for p in eq_detail["mao_obra"]
                        if p.get("funcao") or p.get("codigo")
                    ]
                    custo_mo = sum(i["custo_mensal"] for i in itens)
                    entry["mao_de_obra"] = {
                        "nome": f"MO {cat}",
                        "custo_fixo_mensal": round(custo_mo, 2),
                        "itens": itens,
                    }
                categorias_config.append(entry)

        if not categorias_config:
            return {}

        if (
            isinstance(referencia_indireto_total, (int, float))
            and referencia_indireto_total > 0
            and permanencia_meses > 0
        ):
            total_atual = sum(c["custo_fixo_mensal"] * permanencia_meses for c in categorias_config)
            if total_atual > 0:
                fator = float(referencia_indireto_total) / total_atual
                if abs(fator - 1.0) > 0.1:
                    for categoria in categorias_config:
                        categoria["custo_fixo_mensal"] *= fator

        return {"categorias_config": categorias_config}


def load_spec_from_json(path: Path | str) -> ProjectSpec:
    config_root = Path(os.environ.get("CONCILIUM_CONFIG_ROOT", Path.cwd() / "config"))
    return BenchmarkSpecLoader(config_root).load(path)


def load_spec_from_dict(ref: dict[str, Any], path: Path | str) -> ProjectSpec:
    """Carrega ProjectSpec a partir de um dict ja em memoria (sem I/O de disco)."""
    config_root = Path(os.environ.get("CONCILIUM_CONFIG_ROOT", Path.cwd() / "config"))
    return BenchmarkSpecLoader(config_root).load_from_dict(ref, path)
