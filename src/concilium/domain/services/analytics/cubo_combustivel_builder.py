"""CuboCombustivelBuilder — constrói CuboCombustivelFace por tipo de combustível (ADR-107 D5).

Permite drill-down analítico por tipo_combustivel no cubo analítico:
  - Qual o custo por tipo de combustível neste projeto?
  - Como mudaria a margem se substituíssemos 30% da frota por elétrico?
  - Qual o impacto de +15% no diesel S-10 vs congelamento do GNV?
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from concilium.domain.models.analytics.cubo_pool import CelulaCombustivel, CuboCombustivelFace
from concilium.domain.models.catalog.catalogo import _infer_tipo_combustivel


def build_cubo_combustivel_face(canonical_in: Any) -> CuboCombustivelFace:
    """Constrói CuboCombustivelFace a partir de equipes_diretas do canonical.

    Dimensões: item_id × permanencia (mês) × tipo_combustivel.
    Cada célula representa o custo de combustível de um equipamento específico
    agregado por tipo para o período de permanência da equipe.

    Backward compat: equipamentos sem tipo_combustivel inferem via insumo_id (ADR-107 D6).
    """
    projeto_id = str(getattr(getattr(canonical_in, "projeto", None), "nome", "?"))
    gerado_em = datetime.now(UTC).isoformat()

    celulas: list[CelulaCombustivel] = []

    for equipe in getattr(canonical_in, "equipes_diretas", []) or []:
        item_id = str(getattr(equipe, "item_id", "?") or "?")
        perm = float(getattr(equipe, "permanencia_meses", 0.0) or 0.0)
        if perm <= 0:
            continue

        for equip in getattr(equipe, "equipamentos", []) or []:
            custo_mensal = float(getattr(equip, "custo_combustivel_mensal", 0.0) or 0.0)
            if custo_mensal <= 0:
                continue

            tc = getattr(equip, "tipo_combustivel", None) or _infer_tipo_combustivel(
                getattr(equip, "equip_id", "") or ""
            )
            custo_total = round(custo_mensal * perm, 2)

            celulas.append(
                CelulaCombustivel(
                    item_id=item_id,
                    semana=f"perm_{perm:.1f}m",  # granularidade: período de permanência
                    tipo_combustivel=str(tc),
                    custo=custo_total,
                    volume_litros=0.0,  # volume disponível somente quando catálogo fornece L/h
                )
            )

    return CuboCombustivelFace(
        projeto_id=projeto_id,
        gerado_em=gerado_em,
        celulas=tuple(celulas),
    )
