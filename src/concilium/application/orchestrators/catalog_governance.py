from __future__ import annotations

from pathlib import Path
from typing import Any

from concilium.domain.validations.cpu_insumo import ValidadorCPUInsumo
from concilium.infrastructure.repositories.insumo import RepositorioInsumo


class CatalogGovernanceError(ValueError):
    """Erro de governança para operações de leitura/escrita de catálogo."""


def collect_catalog_critical_errors(catalogo: dict[str, Any]) -> list[dict[str, str]]:
    """Retorna erros críticos de integridade por CPU no catálogo."""
    validador = ValidadorCPUInsumo(RepositorioInsumo(catalogo))
    erros: list[dict[str, str]] = []
    for cpu in catalogo.get("cpus", []):
        codigo = str(cpu.get("codigo", "?"))
        for res in validador.validar_cpu_completa(cpu):
            if res.status == "ERRO":
                erros.append({"cpu": codigo, "erro": res.mensagem or ""})
    return erros


def assert_catalog_healthy(catalogo_id: str, catalogo: dict[str, Any]) -> None:
    """Bloqueia execução quando o catálogo possui erros críticos."""
    erros = collect_catalog_critical_errors(catalogo)
    if not erros:
        return
    detalhes = [f"CPU {e['cpu']}: {e['erro']}" for e in erros[:3]]
    raise CatalogGovernanceError(
        f"Bloqueio de Governança (ADR-035): O catálogo '{catalogo_id}' possui erros críticos "
        f"que impedem o avanço do planejamento: {detalhes}... (Total: {len(erros)})"
    )


def validate_and_resolve_insumo_file(catalog_root: Path, insumo_id: str, novo_preco: float) -> Path:
    """Valida escrita de preço e resolve o arquivo do insumo no catálogo mestre."""
    if novo_preco < 0:
        raise CatalogGovernanceError("novo_preco deve ser maior ou igual a zero.")
    for p in (catalog_root / "insumos").rglob(f"{insumo_id}.json"):
        return p
    raise CatalogGovernanceError(f"Insumo {insumo_id} não encontrado no catálogo mestre.")


def validate_and_resolve_producao_file(catalog_root: Path, producao_id: str, valor_horario: float) -> Path:
    """Valida escrita de variante de produção e resolve o arquivo no catálogo mestre."""
    if valor_horario <= 0:
        raise CatalogGovernanceError("valor_horario deve ser maior que zero.")
    for folder in ("producoes", "produtividades"):
        candidate = catalog_root / folder / f"{producao_id}.json"
        if candidate.exists():
            return candidate
    raise CatalogGovernanceError(f"Metodologia {producao_id} não encontrada no catálogo mestre.")
