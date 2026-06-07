"""Semantic CPU mapping for cronograma items to catalog CPUs.

Uses catalog search to intelligently map cronograma item descriptions
to actual CPUs that exist in the catalog context.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from concilium.application.runtime import Runtime


class CpuMapper:
    """Maps cronograma item descriptions to catalog CPUs using semantic search."""

    def __init__(self, contexto_id: str = "mendeslobo", config_root: Path | None = None):
        """Initialize mapper with catalog context.

        Args:
            contexto_id: Catalog context ID (e.g., "mendeslobo")
            config_root: Path to Concilium config root (auto-detected if None)
        """
        self.contexto_id = contexto_id

        # Auto-detect config root if not provided
        if config_root is None:
            config_root = Path(__file__).parent.parent.parent.parent / "config"

        self.runtime = Runtime(config_root)
        self._cpu_cache: dict[str, str] = {}
        self._load_catalog()

    def _load_catalog(self) -> None:
        """Load catalog and index CPUs for faster lookup."""
        try:
            ctx = self.runtime.load_contexto(self.contexto_id)
            self.catalogo = self.runtime.load_catalogo(ctx.catalogo_id)
            self.contexto = ctx
        except Exception as e:
            raise RuntimeError(f"Failed to load catalog context {self.contexto_id}: {e}")

    def search_cpus(self, query: str, limit: int = 5) -> list[dict[str, Any]]:
        """Search for CPUs matching a query.

        Args:
            query: Search term (e.g., "Aterro", "Escavação")
            limit: Maximum results to return

        Returns:
            List of matching CPUs with codigo, descricao, unidade
        """
        query_norm = query.lower()
        matches = []

        for cpu in self.catalogo.get("cpus", []):
            cod = str(cpu.get("codigo", "")).lower()
            desc = str(cpu.get("descricao", "")).lower()

            # Calculate relevance score
            score = 0
            if query_norm in cod:
                score += 100
            if query_norm in desc:
                score += 50
            # Partial matches on description
            for word in query_norm.split():
                if word in desc:
                    score += 10

            if score > 0:
                matches.append(
                    {
                        "cpu_id": cpu.get("codigo"),
                        "descricao": cpu.get("descricao"),
                        "unidade": cpu.get("unidade"),
                        "categoria": cpu.get("categoria"),
                        "_score": score,
                    }
                )

        # Sort by relevance and limit results
        matches.sort(key=lambda x: x["_score"], reverse=True)
        return [
            {k: v for k, v in m.items() if not k.startswith("_")}
            for m in matches[:limit]
        ]

    def map_item_to_cpu(self, item_id: str, descricao: str) -> str | None:
        """Map a cronograma item to best matching CPU in catalog.

        Uses cached results for performance.

        Args:
            item_id: Item ID (e.g., "2.1")
            descricao: Item description

        Returns:
            CPU ID if match found, None otherwise
        """
        # Check cache first
        if item_id in self._cpu_cache:
            return self._cpu_cache[item_id]

        # Try direct search with item description
        results = self.search_cpus(descricao, limit=1)
        if results:
            cpu_id = results[0]["cpu_id"]
            self._cpu_cache[item_id] = cpu_id
            return cpu_id

        # Fallback: try searching for key terms from description
        for word in descricao.split():
            if len(word) > 3:  # Skip short words
                results = self.search_cpus(word, limit=1)
                if results:
                    cpu_id = results[0]["cpu_id"]
                    self._cpu_cache[item_id] = cpu_id
                    return cpu_id

        # No match found
        return None

    def map_items_batch(
        self, items: list[dict[str, Any]]
    ) -> dict[str, str | None]:
        """Map multiple items to CPUs.

        Args:
            items: List of dicts with 'item_id' and 'descricao' keys

        Returns:
            Dict mapping item_id → cpu_id (or None if no match)
        """
        mappings = {}
        for item in items:
            item_id = item.get("item_id", "")
            descricao = item.get("descricao", "")
            cpu_id = self.map_item_to_cpu(item_id, descricao)
            mappings[item_id] = cpu_id

        return mappings

    def get_available_cpus(self) -> list[dict[str, Any]]:
        """Get list of all available CPUs in catalog.

        Returns:
            List of CPUs with codigo, descricao, unidade, categoria
        """
        cpus = []
        for cpu in self.catalogo.get("cpus", []):
            cpus.append(
                {
                    "cpu_id": cpu.get("codigo"),
                    "descricao": cpu.get("descricao"),
                    "unidade": cpu.get("unidade"),
                    "categoria": cpu.get("categoria"),
                }
            )
        return cpus

    def get_mapping_stats(self) -> dict[str, Any]:
        """Get statistics about mappings performed.

        Returns:
            Dict with mapped count, unmapped count, success rate
        """
        total = len(self._cpu_cache)
        mapped = sum(1 for v in self._cpu_cache.values() if v is not None)
        unmapped = total - mapped

        return {
            "total_items_processed": total,
            "successfully_mapped": mapped,
            "failed_mappings": unmapped,
            "success_rate": (mapped / total * 100) if total > 0 else 0,
        }
