"""Pacote semântico — Camada Semântica v1.0 (ADR-001).

Expõe os tipos e pipelines de extração semântica.
"""

from __future__ import annotations

from pathlib import Path

from concilium.application.semantic.extractor import SemanticExtractor
from concilium.application.semantic.intent import (
    Dimension,
    DomainType,
    ExtractionConfidence,
    SemanticIntent,
    SemanticParseError,
)
from concilium.application.semantic.normalizer import (
    AttributeNormalizer,
    CatalogNormalizer,
    VocabularyLoader,
)

# Diretório padrão de vocabulários
VOCAB_DIR = Path(__file__).parent / "vocabularies"

# Cache de unit aliases (construído na importação para evitar re-leitura)
_UNIT_ALIASES_CACHE: dict[str, str] = {}


def _build_unit_cache() -> None:
    """Constrói cache de aliases de unidades no carregamento do pacote."""
    global _UNIT_ALIASES_CACHE
    try:
        loader = VocabularyLoader(VOCAB_DIR)
        _UNIT_ALIASES_CACHE = loader.unit_aliases()
    except Exception:
        _UNIT_ALIASES_CACHE = {}


_build_unit_cache()


def make_extractor(
    *,
    allow_llm_fallback: bool = False,
    llm_client: object | None = None,
    vocab_dir: Path | None = None,
) -> SemanticExtractor:
    """Factory que cria SemanticExtractor com o diretório de vocabulário padrão."""
    return SemanticExtractor(
        vocab_path=vocab_dir or VOCAB_DIR,
        allow_llm_fallback=allow_llm_fallback,
        llm_client=llm_client,
    )


__all__ = [
    "Dimension",
    "DomainType",
    "ExtractionConfidence",
    "SemanticIntent",
    "SemanticParseError",
    "SemanticExtractor",
    "AttributeNormalizer",
    "CatalogNormalizer",
    "VocabularyLoader",
    "VOCAB_DIR",
    "make_extractor",
]
