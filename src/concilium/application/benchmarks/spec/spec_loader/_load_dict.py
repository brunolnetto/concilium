"""BenchmarkSpecLoader — load_from_dict (montagem completa do ProjectSpec)."""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING, Any

from ._project_spec import ProjectSpec, iso_weeks

if TYPE_CHECKING:
    from ._host_protocol import BenchmarkSpecLoaderHost as _Base
else:
    _Base = object


class _LoadDictMixin(_Base):
    def load_from_dict(self, ref: dict[str, Any], path: Path | str) -> ProjectSpec:
        """Carrega ProjectSpec a partir de um dict ja parseado (sem re-ler o disco)."""
        path = Path(path).resolve()
        ref = self._normalize_reference_schema(ref)

        raw_projeto = ref.get("projeto")
        projeto_block: dict[str, Any] = raw_projeto if isinstance(raw_projeto, dict) else {}
        projeto_nome = self._lfd_resolve_projeto_nome(ref, projeto_block, path)

        raw_meta = ref.get("meta")
        meta_block: dict[str, Any] = raw_meta if isinstance(raw_meta, dict) else {}
        contexto_id = self._lfd_resolve_contexto_id(ref, meta_block)
        _ctx_version, _perfil_id, _perfil_version = self._lfd_resolve_context(ref, contexto_id)

        data_ini, data_fim = self._lfd_resolve_datas(ref, projeto_block)
        weeks = iso_weeks(data_ini, data_fim)
        eap = self._extract_eap(ref)
        eap = self._enrich_eap_with_cpu_ids(eap, contexto_id)

        res = ref.get("resultado", {})
        bdi_meta = res.get("bdi_lucro_impostos", 0.15)
        slug = ref.get("id") or self._infer_slug_from_path(path)
        num_equipes_por_item = self._input_deriver.derive_num_equipes_por_item(ref, eap, weeks)

        consolidacao_inputs = {"bdi_lucro_impostos": bdi_meta}
        extra_inputs: dict = {
            "06-consolidar": consolidacao_inputs,
            "06-resultado-financeiro": consolidacao_inputs,  # NEP-041 F4
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

        extra_inputs.update(self._lfd_static_extra_inputs())

        # ADR-071: repassa rcpsp_spec para skill-05 para que possa calcular
        # contratos de pool e atribuir custos proporcionalmente ao uso.
        if ref.get("rcpsp_spec"):
            extra_inputs["05-equipes-e-alocacao"] = {"rcpsp_spec": ref["rcpsp_spec"]}

        localizacao, regime_trabalho = self._lfd_resolve_localizacao_regime(ref, projeto_block)

        return ProjectSpec(
            nome=projeto_nome,
            slug=slug,
            contexto_id=contexto_id,
            contexto_version=_ctx_version,
            perfil_id=_perfil_id,
            perfil_version=_perfil_version,
            referencia_path=path,
            inputs_escopo=self._lfd_build_inputs_escopo(
                projeto_nome, localizacao, regime_trabalho, data_ini, data_fim, eap, ref
            ),
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


