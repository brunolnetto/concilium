"""Validate CPU mappings and production compositions for benchmark data.

Ensures that:
1. Mapped CPUs exist in catalog
2. CPUs have producao_id_ref
3. Productions have composicao_padrao_equipe with funcoes/equipamentos
"""

from __future__ import annotations

from typing import Any

from .cpu_mapper import CpuMapper


class CpuValidator:
    """Validates CPU mappings and their production compositions."""

    def __init__(self, contexto_id: str = "mendeslobo"):
        """Initialize validator with catalog context.

        Args:
            contexto_id: Catalog context ID (e.g., "mendeslobo")
        """
        self.mapper = CpuMapper(contexto_id)
        self.catalogo = self.mapper.catalogo

    def validate_cpu_exists(self, cpu_id: str) -> bool:
        """Check if CPU exists in catalog.

        Args:
            cpu_id: CPU codigo to validate

        Returns:
            True if CPU found, False otherwise
        """
        cpus = self.catalogo.get("cpus", [])
        return any(c.get("codigo") == cpu_id for c in cpus)

    def get_cpu(self, cpu_id: str) -> dict[str, Any] | None:
        """Get CPU definition from catalog.

        Args:
            cpu_id: CPU codigo

        Returns:
            CPU dict or None if not found
        """
        cpus = self.catalogo.get("cpus", [])
        for c in cpus:
            if c.get("codigo") == cpu_id:
                return c
        return None

    def get_production(self, prod_id: str) -> dict[str, Any] | None:
        """Get production definition from catalog.

        Args:
            prod_id: Production id

        Returns:
            Production dict or None if not found
        """
        prods = self.catalogo.get("producoes", []) or self.catalogo.get("produtividades", [])
        for p in prods:
            if p.get("codigo") == prod_id or p.get("id") == prod_id:
                return p
        return None

    def validate_cpu_mapping(self, cpu_id: str) -> dict[str, Any]:
        """Validate a complete CPU mapping chain.

        Args:
            cpu_id: CPU codigo to validate

        Returns:
            Dict with validation results:
            - cpu_exists: bool
            - cpu: dict or None
            - has_producao_ref: bool
            - producao_exists: bool
            - producao: dict or None
            - has_composicao: bool
            - errors: list of error messages
        """
        errors: list[str] = []
        result: dict[str, Any] = {
            "cpu_exists": False,
            "cpu": None,
            "has_producao_ref": False,
            "producao_exists": False,
            "producao": None,
            "has_composicao": False,
            "errors": errors,
        }

        # Step 1: Validate CPU exists
        cpu = self.get_cpu(cpu_id)
        if not cpu:
            errors.append(f"CPU '{cpu_id}' não encontrado no catálogo")
            return result

        result["cpu_exists"] = True
        result["cpu"] = cpu

        # Step 2: Check producao_id_ref
        prod_ref = cpu.get("producao_id_ref")
        if not prod_ref:
            errors.append(f"CPU '{cpu_id}' não tem producao_id_ref definido")
            return result

        result["has_producao_ref"] = True

        # Step 3: Validate production exists
        prod = self.get_production(prod_ref)
        if not prod:
            errors.append(f"Produção '{prod_ref}' referenciada por CPU '{cpu_id}' não encontrada")
            return result

        result["producao_exists"] = True
        result["producao"] = prod

        # Step 4: Check composicao_padrao_equipe
        comp = prod.get("composicao_padrao_equipe") or {}
        if not comp:
            errors.append(f"Produção '{prod_ref}' não tem composicao_padrao_equipe definida")
            return result

        funcoes = comp.get("funcoes", [])
        equipamentos = comp.get("equipamentos", [])

        if not funcoes and not equipamentos:
            errors.append(f"Produção '{prod_ref}' tem composicao_padrao_equipe vazia (sem funcoes ou equipamentos)")
            return result

        result["has_composicao"] = True
        return result

    def validate_eap_items(self, eap_items: list[dict[str, Any]]) -> dict[str, Any]:
        """Validate all EAP items' CPU mappings.

        Args:
            eap_items: List of EAP items with cpu_id

        Returns:
            Dict with validation summary:
            - total: number of items
            - valid: number of valid items
            - invalid: number of invalid items
            - items: dict mapping item_id → validation result
        """
        valid = 0
        invalid = 0
        items: dict[str, dict[str, Any]] = {}

        for item in eap_items:
            item_id = item.get("item_id", "?")
            cpu_id = item.get("cpu_id", "?")

            validation = self.validate_cpu_mapping(cpu_id)
            items[item_id] = {
                "cpu_id": cpu_id,
                "validation": validation,
            }

            if validation["errors"]:
                invalid += 1
            else:
                valid += 1

        return {
            "total": len(eap_items),
            "valid": valid,
            "invalid": invalid,
            "items": items,
        }

    def print_validation_report(self, validation: dict[str, Any]) -> None:
        """Print human-readable validation report.

        Args:
            validation: Result from validate_eap_items()
        """
        total = validation["total"]
        valid = validation["valid"]
        invalid = validation["invalid"]

        print(f"\n{'=' * 70}")
        print("VALIDAÇÃO DE MAPEAMENTO DE CPUs")
        print(f"{'=' * 70}")
        print("\nResumo:")
        print(f"  Total items: {total}")
        print(f"  ✓ Válidos: {valid} ({valid / total * 100:.1f}%)")
        print(f"  ✗ Inválidos: {invalid} ({invalid / total * 100:.1f}%)")

        if invalid > 0:
            print("\nDetalhes dos inválidos:")
            for item_id, item_val in validation["items"].items():
                cpu_val = item_val["validation"]
                if cpu_val["errors"]:
                    print(f"\n  Item {item_id} (CPU: {item_val['cpu_id']}):")
                    for error in cpu_val["errors"]:
                        print(f"    ✗ {error}")
