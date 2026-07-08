"""Skill 04 — Planejamento e BDI.

Calcula preço unitário (sem e com BDI) por item da EAP, decomposto em 4 categorias:
material, diesel, mão de obra, equipamentos (ADR-023: BDI auditável via TabelaBdi).

Ordem de precedência para BDI:
    1. inputs["bdi_aplicado"]  — override manual (4 categorias flat)
    2. inputs["tabela_bdi"]    — TabelaBdi serializada (ADR-023)
    3. DEFAULT_BDI_TABELA       — valores padrão da planilha rfi_catalog.xlsm (abril/2026)

Mapeamento de categorias ADR-023 -> modelo flat Planejamento.bdi:
    MAO_OBRA  -> mao_obra
    MATERIAL  -> material
    DIESEL    -> diesel
    SERVICOS  -> equipamentos (via tabela_bdi.servicos)
"""

from ._cpu_fallback import (  # ty: ignore[unresolved-import]
    _avisar_sbdi_presenca,
    _preco_cat_fallback_composicao,
    _resolve_cpu_com_fallback,
    _validar_producao_id_ref,
)
from ._cpu_helpers import (  # ty: ignore[unresolved-import]
    _CATEGORIA_MAP,
    _build_equipe_lookup,
    _create_synthetic_cpu,
    _resolve_insumo_preco,
)
from ._lookups import _build_lookups, _get_bdi_value  # ty: ignore[unresolved-import]
from ._planejamento_entry import (  # ty: ignore[unresolved-import]
    _apply_equip_decomp,
    _build_planejamento_entry,
    _try_early_override,
)
from ._preco_cpu import (  # ty: ignore[unresolved-import]
    _avisar_sbdi_legado,
    _compute_preco_cat_from_cpu,
    _compute_preco_cat_from_production,
    _resolve_producao_valida,
)
from ._process_item import _process_eap_item, _resolve_preco_cat_item  # ty: ignore[unresolved-import]
from ._validacao import (  # ty: ignore[unresolved-import]
    _apply_com_bdi_override,
    _apply_sem_bdi_override,
    _validate_coverage,
    _validate_encargos_separacao,
)

__all__ = [
    "_CATEGORIA_MAP",
    "_apply_com_bdi_override",
    "_apply_equip_decomp",
    "_apply_sem_bdi_override",
    "_avisar_sbdi_legado",
    "_avisar_sbdi_presenca",
    "_build_equipe_lookup",
    "_build_lookups",
    "_build_planejamento_entry",
    "_compute_preco_cat_from_cpu",
    "_compute_preco_cat_from_production",
    "_create_synthetic_cpu",
    "_get_bdi_value",
    "_preco_cat_fallback_composicao",
    "_process_eap_item",
    "_resolve_cpu_com_fallback",
    "_resolve_insumo_preco",
    "_resolve_preco_cat_item",
    "_resolve_producao_valida",
    "_try_early_override",
    "_validar_producao_id_ref",
    "_validate_coverage",
    "_validate_encargos_separacao",
]
