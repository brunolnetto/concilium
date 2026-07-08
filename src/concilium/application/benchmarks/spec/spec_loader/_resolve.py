"""BenchmarkSpecLoader — resolução de contexto e das peças do reference JSON."""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import TYPE_CHECKING, Any

from .._spec_loader_helpers_b import _bs_lfd_build_bdi_section, _lfd_parse_raw_row
from ._project_spec import ProjectSpec

if TYPE_CHECKING:
    from ._host_protocol import BenchmarkSpecLoaderHost as _Base
else:
    _Base = object

logger = logging.getLogger(__name__)


class _ResolveMixin(_Base):
    def resolve_contexto(self, contexto_id: str, version: str | None = None) -> dict[str, Any] | None:
        """Resolve contexto by id and optional version (ADR-062)."""
        try:
            from concilium.application.services.catalog.contexto_version_service import ContextoVersionService

            svc = ContextoVersionService(self._config_root)
            return svc.resolve(contexto_id, version)
        except Exception as e:
            logger.error("Falha ao resolver contexto %s (versão=%s): %s", contexto_id, version, e, exc_info=True)
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
            from concilium.application.services.catalog.contexto_version_service import (
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


    def _lfd_resolve_projeto_nome(self, ref: dict[str, Any], projeto_block: dict, path: Path) -> str:
        projeto_nome = ref.get("projeto") if isinstance(ref.get("projeto"), str) else None
        if not projeto_nome and projeto_block:
            projeto_nome = projeto_block.get("nome") or projeto_block.get("projeto")
        if not isinstance(projeto_nome, str) or not projeto_nome.strip():
            projeto_nome = self._infer_slug_from_path(path)
        return projeto_nome


    @staticmethod
    def _lfd_resolve_contexto_id(ref: dict[str, Any], meta_block: dict) -> str:
        return ref.get("contexto_id") or (meta_block.get("contexto_id") if meta_block else None) or "mendeslobo"


    @staticmethod
    def _lfd_resolve_datas(ref: dict[str, Any], projeto_block: dict) -> tuple[str, str]:
        data_ini = (
            ref.get("data_inicio") or (projeto_block.get("data_inicio") if projeto_block else None) or "2025-01-01"
        )
        data_fim = (
            ref.get("data_termino") or (projeto_block.get("data_termino") if projeto_block else None) or "2025-06-30"
        )
        return data_ini, data_fim


    @staticmethod
    def _lfd_resolve_localizacao_regime(ref: dict[str, Any], projeto_block: dict) -> tuple[Any, dict]:
        localizacao = ref.get("localizacao")
        if localizacao is None and projeto_block:
            localizacao = projeto_block.get("localizacao")

        regime_trabalho = ref.get("regime_trabalho")
        if not isinstance(regime_trabalho, dict) and projeto_block:
            regime_trabalho = projeto_block.get("regime_trabalho")
        if not isinstance(regime_trabalho, dict):
            regime_trabalho = {"horas_dia": 8, "dias_semana": 6}
        return localizacao, regime_trabalho


