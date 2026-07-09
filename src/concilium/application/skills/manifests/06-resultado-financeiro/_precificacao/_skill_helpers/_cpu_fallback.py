"""Skill 06 (_precificacao) — Planejamento e BDI.

Resolução de CPU com fallback e composição alternativa.
"""

from __future__ import annotations

from typing import Any

from concilium.domain.models.canonical import (
    ValidacaoItem,
)
from concilium.infrastructure.repositories.insumo import RepositorioInsumo

from ._cpu_helpers import _create_synthetic_cpu  # ty: ignore[unresolved-import]
from ._preco_cpu import _compute_preco_cat_from_cpu  # ty: ignore[unresolved-import]


def _resolve_cpu_com_fallback(item: Any, cpu_lookup: dict, validacoes: list, erros_eap: list) -> dict | None:
    """Resolve o CPU do item, criando um CPU sintético quando não encontrado no catálogo.

    ADR-108: Fallback para CPUs sintetizados não encontrados no catálogo — cria CPU
    sintético com composição padrão para permitir pipeline continuar.
    """
    cpu = cpu_lookup.get(item.cpu_id)
    if cpu is not None:
        return cpu

    if not item.cpu_id.startswith("CPU-"):
        erros_eap.append(item.cpu_id)
        return None

    cpu = _create_synthetic_cpu(item.cpu_id, validacoes)
    if not cpu:
        erros_eap.append(item.cpu_id)
        return None

    validacoes.append(
        ValidacaoItem(
            codigo="VAL-CPU-SINTETICO",
            status="AVISO",
            mensagem=(
                f"CPU '{item.cpu_id}' não encontrado em catálogo. Usando CPU sintético com producao_id_ref padrão."
            ),
        )
    )
    return cpu


def _validar_producao_id_ref(cpu: dict, prod_lookup: dict, validacoes: list) -> bool:
    """Valida que o CPU tem producao_id_ref e que ela existe em prod_lookup."""
    prod_id_ref = cpu.get("producao_id_ref")
    if not prod_id_ref:
        validacoes.append(
            ValidacaoItem(
                codigo="VAL-PLAN-PROD-REF-01", status="ERRO", mensagem=f"CPU '{cpu.get('codigo')}' sem producao_id_ref."
            )
        )
        return False
    if prod_lookup.get(prod_id_ref) is None:
        validacoes.append(
            ValidacaoItem(
                codigo="VAL-PLAN-PROD-REF-02",
                status="ERRO",
                mensagem=f"CPU '{cpu.get('codigo')}' referencia producao_id_ref inexistente: {prod_id_ref}.",
            )
        )
        return False
    return True


def _avisar_sbdi_presenca(cpu: dict, validacoes: list) -> None:
    """NEP-029: rastrear presença/ausência de precos_unitarios_sbdi para auditoria."""
    if cpu.get("precos_unitarios_sbdi"):
        validacoes.append(
            ValidacaoItem(
                codigo="VAL-PLAN-SBDI",
                status="INFO",
                mensagem=f"CPU '{cpu.get('codigo')}': precos_unitarios_sbdi disponível "
                f"(informativo; cálculo usa composicao_itens).",
            )
        )
    else:
        validacoes.append(
            ValidacaoItem(
                codigo="VAL-PLAN-SBDI-MISSING",
                status="AVISO",
                mensagem=(
                    f"CPU '{cpu.get('codigo')}': precos_unitarios_sbdi ausente. "
                    "Usando composicao_itens como fonte de precificação."
                ),
            )
        )


def _preco_cat_fallback_composicao(
    cpu: dict,
    insumo_lookup: dict,
    repo: RepositorioInsumo,
    jurisdicao_id: str | None,
    overrides: dict | None,
    data_base: Any,
    erros_insumo: set,
    validacoes: list,
) -> tuple[dict[str, float] | None, set[str]]:
    """Fonte 2: composicao_itens × preco_insumo (fallback quando bottom-up é vazio)."""
    from concilium.domain.models.catalog.catalogo import CPU

    cpu_model = CPU.model_validate(cpu)
    preco_cat, equip_sem_decomp_item = _compute_preco_cat_from_cpu(
        cpu_model,
        insumo_lookup,
        repo,
        jurisdicao_id,
        overrides,
        data_base,
        cpu.get("codigo") or "",
        erros_insumo,
        validacoes,
    )
    validacoes.append(
        ValidacaoItem(
            codigo="VAL-PLAN-COMPOSICAO-FALLBACK",
            status="AVISO",
            mensagem=(
                f"CPU '{cpu.get('codigo')}': precificação bottom-up retornou vazio; "
                "usando composicao_itens como fallback. "
                "Verifique valor_horario na produção e composicao_padrao_equipe."
            ),
        )
    )
    _avisar_sbdi_presenca(cpu, validacoes)
    return preco_cat, equip_sem_decomp_item


