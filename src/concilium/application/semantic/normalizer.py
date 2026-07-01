"""Normalização de atributos e catálogo — Camada Semântica v1.0.

Classes:
    AttributeNormalizer  — normaliza atributos individuais via ATTRIBUTE_REGISTRY
    CatalogNormalizer    — converte CPU do catálogo -> CPUCanonical (ingestão once)
    VocabularyLoader     — carrega vocabulários YAML com cache
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import TYPE_CHECKING, Any

from concilium.application.resolution.registry import ATTRIBUTE_REGISTRY, resolve_alias
from concilium.application.semantic.intent import DomainType

if TYPE_CHECKING:
    from concilium.application.resolution.models import CPUCanonical

try:
    import yaml as _yaml  # type: ignore[import-untyped]

    _HAS_YAML = True
except ImportError:  # pragma: no cover
    _HAS_YAML = False

# Mapping de categoria do catálogo -> DomainType
CATEGORY_TO_DOMAIN: dict[str, DomainType] = {
    "TERRAPLENAGEM": "earthwork",
    "PAVIMENTACAO": "pavement",
    "PAVIMENTAÇÃO": "pavement",
    "SANEAMENTO": "drainage",
    "ESTRUTURA": "structure",
    "ESTRUTURAS": "structure",
    "OBRAS_DE_ARTE": "structure",
}

# Mapping de codigo CPU -> activity_type (para catálogo)
CPU_ACTIVITY_TYPE_MAP: dict[str, str] = {
    "ESCO-CARGA-1CAT-DMT2000": "cut_fill",
    "ESCO-CARGA-1CAT-DMT3000": "cut_fill",
    "ESCO-CARGA-2CAT-DMT2000": "cut_fill",
    "ESCO-CARGA-2CAT-DMT3000": "cut_fill",
    "ESCO-CARGA-3CAT-DMT2000": "cut_fill",
    "ESCO-CARGA-3CAT-DMT3000": "cut_fill",
    "COMPACT-ATERRO": "embankment_compaction",
    "COMPACT-ATERRO-100PN": "embankment_compaction",
    "REGULARIZACAO-SUBLEITO": "subgrade_regularization",
    "PAV-BASE-BGTC": "base_course",
    "PAV-CBUQ-FAIXA-C": "wearing_course",
    "DREN-MAN-DN300": "pipe_collector",
    "POCO-VISITA-PADRAO": "inspection_well",
}

# DMT inferido do código para CPUs de escavação
_DMT_FROM_CODE = re.compile(r"DMT(\d+)$")
_SOIL_CAT_FROM_CODE = re.compile(r"ESCO-CARGA-(\d)CAT")


class VocabularyLoader:
    """Carrega e faz cache de vocabulários YAML."""

    def __init__(self, vocab_dir: Path) -> None:
        self._dir = vocab_dir
        self._cache: dict[str, dict] = {}

    def load(self, name: str) -> dict:
        """Carrega `name.yaml` do diretório de vocabulários."""
        if name in self._cache:
            return self._cache[name]
        path = self._dir / f"{name}.yaml"
        if not path.exists():
            return {}
        if not _HAS_YAML:
            return {}
        with path.open(encoding="utf-8") as f:
            data = _yaml.safe_load(f) or {}
        self._cache[name] = data
        return data

    def unit_aliases(self) -> dict[str, str]:
        """Retorna mapeamento alias_lower -> canonical_unit."""
        units_vocab = self.load("units")
        result: dict[str, str] = {}
        for canonical, info in units_vocab.items():
            if not isinstance(info, dict):
                continue
            result[canonical.lower()] = canonical
            for alias in info.get("aliases", []):
                result[alias.lower()] = canonical
        return result

    def activity_aliases(self) -> dict[str, tuple[str, str]]:
        """Retorna alias_lower -> (domain, activity_type)."""
        acts = self.load("activities")
        result: dict[str, tuple[str, str]] = {}
        for domain, activities in acts.items():
            if not isinstance(activities, dict):
                continue
            for act_id, info in activities.items():
                if not isinstance(info, dict):
                    continue
                full = (domain, act_id)
                result[act_id.lower()] = full
                for alias in info.get("aliases_pt", []) + info.get("aliases_en", []):
                    result[alias.lower()] = full
        return result

    def activity_required_dims(self, activity_type: str) -> list[str]:
        """Retorna required_dimensions para um activity_type."""
        acts = self.load("activities")
        for _domain, activities in acts.items():
            if activity_type in activities:
                return activities[activity_type].get("required_dimensions", [])
        return []

    def activity_optional_dims(self, activity_type: str) -> list[str]:
        """Retorna optional_dimensions para um activity_type."""
        acts = self.load("activities")
        for _domain, activities in acts.items():
            if activity_type in activities:
                return activities[activity_type].get("optional_dimensions", [])
        return []


class AttributeNormalizer:
    """Normaliza atributos individuais usando ATTRIBUTE_REGISTRY."""

    def normalize(
        self,
        raw_name: str,
        raw_value: Any,
        raw_unit: str | None = None,
    ) -> tuple[str, Any]:
        """Normaliza (name, value) para forma canônica.

        Se raw_name não está no registry -> passthrough (não erro).
        Se raw_unit incompatível com canonical_unit -> aplica normalizer.

        Returns:
            (canonical_name, normalized_value)
        """
        canonical = resolve_alias(raw_name)
        if canonical is None:
            return (raw_name, raw_value)

        attr_def = ATTRIBUTE_REGISTRY[canonical]
        try:
            normalized = attr_def.normalizer(raw_value, raw_unit or "")
        except Exception:
            normalized = raw_value

        return (canonical, normalized)

    def normalize_unit(self, raw_unit: str) -> str | None:
        """Mapeia alias de unidade para forma canônica. None se desconhecida."""
        raw_lower = raw_unit.strip().lower()
        from concilium.application.semantic import _UNIT_ALIASES_CACHE

        return _UNIT_ALIASES_CACHE.get(raw_lower)


class CatalogNormalizer:
    """Normaliza CPUs do catálogo para CPUCanonical.

    Deve ser rodado UMA VEZ na ingestão do catálogo, não em runtime.
    O resultado é armazenado junto ao snapshot.
    """

    def __init__(self, vocab_loader: VocabularyLoader | None = None) -> None:
        self._vocab = vocab_loader

    def normalize_cpu(self, cpu: dict[str, Any]) -> CPUCanonical:
        """Converte CPU do catálogo para forma canônica.

        - Mapeia categoria -> DomainType
        - Normaliza unidade para lowercase
        - Infere activity_type do código via CPU_ACTIVITY_TYPE_MAP
        - Infere atributos (dmt_min/max, soil_class) do código e atributos_categoria
        - Determina required_attributes e optional_attributes do vocabulário
        """
        from concilium.application.resolution.models import CPUCanonical  # lazy import (break circular)

        codigo: str = cpu.get("codigo", "")
        categoria: str = cpu.get("categoria", "").upper()
        unidade_raw: str = cpu.get("unidade", "m3")

        domain = CATEGORY_TO_DOMAIN.get(categoria, "other")
        activity_type = _infer_activity_type(codigo)
        unit = unidade_raw.lower().replace("³", "3").replace("²", "2")

        # Normalizar unidade via vocabulário se disponível
        if self._vocab:
            mapped = self._vocab.unit_aliases().get(unit.strip())
            if mapped:
                unit = mapped

        productivity = float(cpu.get("producao_horaria", 0.0))

        # Atributos canônicos da CPU
        attributes: dict[str, float | str | None] = {}
        atributos_cat = cpu.get("atributos_categoria") or {}

        # dmt para CPUs de escavação
        dmt_match = _DMT_FROM_CODE.search(codigo)
        if dmt_match:
            attributes["dmt"] = float(dmt_match.group(1))
        elif "dmt_max_metros" in atributos_cat:
            attributes["dmt"] = float(atributos_cat["dmt_max_metros"])

        # soil_class para CPUs de escavação
        cat_match = _SOIL_CAT_FROM_CODE.match(codigo)
        if cat_match:
            attributes["soil_class"] = f"{cat_match.group(1)}A"

        # pipe_diameter para coletores
        if "DN300" in codigo:
            attributes["pipe_diameter"] = 300.0

        # compaction_rate para compactação (100% PN = padrão)
        if activity_type == "embankment_compaction":
            attributes["compaction_rate"] = 100.0

        # required / optional attributes
        if self._vocab:
            required = self._vocab.activity_required_dims(activity_type)
            optional = self._vocab.activity_optional_dims(activity_type)
        else:
            required, optional = _default_attrs_for_activity(activity_type)

        return CPUCanonical(
            cpu_id=codigo,
            domain=domain,
            activity_type=activity_type,
            unit=unit,
            base_productivity=productivity,
            attributes=attributes,
            required_attributes=required,
            optional_attributes=optional,
        )

    def normalize_catalog(self, cpus: list[dict[str, Any]]) -> list[CPUCanonical]:
        """Normaliza catálogo inteiro. Armazenar resultado no snapshot."""
        return [self.normalize_cpu(cpu) for cpu in cpus]


def _infer_activity_type(codigo: str) -> str:
    """Infere activity_type do código de CPU."""
    # Busca prefixo exato no mapa
    if codigo in CPU_ACTIVITY_TYPE_MAP:
        return CPU_ACTIVITY_TYPE_MAP[codigo]
    # Prefixo fallback
    for key, act in CPU_ACTIVITY_TYPE_MAP.items():
        if codigo.startswith(key):
            return act
    return "unknown"


def _default_attrs_for_activity(activity_type: str) -> tuple[list[str], list[str]]:
    """Fallback quando VocabularyLoader não está disponível."""
    mapping: dict[str, tuple[list[str], list[str]]] = {
        "cut_fill": ([], ["dmt", "soil_class"]),
        "embankment_compaction": ([], ["compaction_rate"]),
        "subgrade_regularization": ([], []),
        "base_course": ([], ["thickness"]),
        "wearing_course": ([], ["thickness"]),
        "pipe_collector": (["pipe_diameter"], ["depth"]),
        "inspection_well": ([], ["depth"]),
    }
    return mapping.get(activity_type, ([], []))


__all__ = ["VocabularyLoader", "AttributeNormalizer", "CatalogNormalizer"]
