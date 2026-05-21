"""SemanticExtractor — pipeline deterministico-first (ADR-001).

Ordem de processamento:
  1. Extração por regras (regex: números, unidades, dimensões)
  2. Mapeamento por vocabulário controlado (activity_type, domain, materials)
  3. LLM fallback (opcional, deve ser logado e sinalizado com ``used_llm_fallback=True``)
  4. Validação de invariantes -> SemanticIntent ou SemanticParseError

Falha explícita nunca silenciosa.
"""

from __future__ import annotations

import re
import uuid
from pathlib import Path
from typing import Any

from concilium.application.semantic.intent import (
    Dimension,
    DomainType,
    ExtractionConfidence,
    SemanticIntent,
    SemanticParseError,
)
from concilium.application.semantic.normalizer import VocabularyLoader

# ─────────────────────────── Regexes ────────────────────────────────────────

# Número seguido de unidade: "12.5cm", "300 mm", "2.000m", "10m3"
_RE_NUM_UNIT = re.compile(
    r"(\d+(?:[.,]\d+)?)\s*"
    r"(m3|m2|m[²³]|m\^[23]|metros?\s*c[uú]bicos?|metros?\s*quadrados?|"
    r"cm|mm|ton(?:eladas?)?|un(?:id(?:ades?)?)?|%|m\b|ml\b)",
    re.IGNORECASE,
)

# Detecta dimensões embutidas em texto livre (e.g., "espessura 10cm" sem estruturar)
_RE_EMBEDDED_DIM = re.compile(
    r"\b(espessura|thickness|dmt|diametro|di[âa]metro|profundidade|depth|dn)\s+\d",
    re.IGNORECASE,
)

# Números isolados no texto
_RE_NUMBER = re.compile(r"\b(\d+(?:[.,]\d+)?)\b")

# Normalizar separador decimal pt-BR
_RE_PTBR_NUM = re.compile(r"(\d+),(\d+)")

# Mapeamento de nomes de dimensão detectados no texto
_DIM_NAME_MAP: dict[str, str] = {
    "espessura": "thickness",
    "thickness": "thickness",
    "dmt": "dmt",
    "distancia media transporte": "dmt",
    "diametro": "pipe_diameter",
    "diâmetro": "pipe_diameter",
    "dn": "pipe_diameter",
    "profundidade": "depth",
    "depth": "depth",
    "largura": "width",
    "width": "width",
}

# Qualificadores de classe de material
_SOIL_CLASS_MAP: dict[str, str] = {
    "1a": "1A",
    "1ª": "1A",
    "primeira": "1A",
    "2a": "2A",
    "2ª": "2A",
    "segunda": "2A",
    "3a": "3A",
    "3ª": "3A",
    "terceira": "3A",
    "rocha branda": "2A",
    "rocha dura": "3A",
}


class SemanticExtractor:
    """Pipeline deterministico-first para construção de SemanticIntent.

    O extrator nunca "adivinha" — prefere campo ausente explícito (None)
    a inferência silenciosa. Apenas o LLM fallback (desabilitado por padrão)
    preenche campos ambíguos, e sempre com flag ``used_llm_fallback=True``.
    """

    def __init__(
        self,
        vocab_path: Path,
        allow_llm_fallback: bool = False,
        llm_client: Any | None = None,
    ) -> None:
        self._vocab = VocabularyLoader(vocab_path)
        self._allow_llm = allow_llm_fallback
        self._llm = llm_client
        # Caches pré-calculados
        self._unit_aliases = self._vocab.unit_aliases()
        self._activity_aliases = self._vocab.activity_aliases()

    # ── API pública ──────────────────────────────────────────────────────────

    def extract(self, raw_text: str, scope_item_id: str | None = None) -> SemanticIntent:
        """Transforma texto bruto em SemanticIntent estruturado.

        Args:
            raw_text:      Texto original do item de escopo.
            scope_item_id: ID de rastreabilidade (gerado se omitido).

        Returns:
            SemanticIntent com todos os invariantes satisfeitos.

        Raises:
            SemanticParseError: se qualquer invariante não puder ser satisfeito.
        """
        sid = scope_item_id or str(uuid.uuid4())[:8]

        # Passo 1 — extração por regras
        fields = self._rule_based_extraction(raw_text)

        # Passo 2 — mapeamento de vocabulário
        fields = self._vocabulary_mapping(raw_text, fields)

        # Passo 3 — LLM fallback (apenas se necessário e permitido)
        used_llm = False
        if self._needs_fallback(fields) and self._allow_llm and self._llm:
            fields = self._llm_fallback(raw_text, fields)
            used_llm = True

        fields["used_llm_fallback"] = used_llm

        # Passo 4 — construir e validar
        return self._build_and_validate(raw_text, sid, fields)

    def extract_batch(self, items: list[dict[str, str]]) -> list[SemanticIntent | SemanticParseError]:
        """Extrai um lote de itens.

        Args:
            items: Lista de dicts com chaves "raw_text" e opcionalmente "scope_item_id".

        Returns:
            Lista onde cada elemento é SemanticIntent (sucesso) ou SemanticParseError.
        """
        results: list[SemanticIntent | SemanticParseError] = []
        for item in items:
            try:
                intent = self.extract(
                    item["raw_text"],
                    item.get("scope_item_id"),
                )
                results.append(intent)
            except SemanticParseError as e:
                results.append(e)
        return results

    # ── Implementações internas ──────────────────────────────────────────────

    def _rule_based_extraction(self, text: str) -> dict[str, Any]:
        """Extrai números, unidades e dimensões via regex."""
        # Normalizar separador decimal pt-BR
        normalized = _RE_PTBR_NUM.sub(r"\1.\2", text)

        dimensions: list[Dimension] = []
        qualifiers: list[str] = []
        unit: str | None = None
        materials: list[str] = []

        # Detectar dimensões embutidas (e.g. "espessura 15cm")
        for m in _RE_EMBEDDED_DIM.finditer(normalized):
            dim_name_raw = m.group(1).lower()
            canonical_dim = _DIM_NAME_MAP.get(dim_name_raw)
            if canonical_dim is None:
                continue
            # Procurar número + unidade após o nome da dimensão
            rest = normalized[m.end() :]
            num_m = _RE_NUM_UNIT.match(rest.strip())
            if num_m:
                val = float(num_m.group(1).replace(",", "."))
                raw_unit = num_m.group(2).strip().lower()
                canon_unit = self._normalize_unit(raw_unit) or raw_unit
                dimensions.append(Dimension(name=canonical_dim, value=val, unit=canon_unit))

        # Detectar quantidade principal + unidade no texto inteiro
        # (última menção de unidade de medida principal = unidade do item)
        for m in _RE_NUM_UNIT.finditer(normalized):
            raw_unit = m.group(2).strip().lower()
            canon_unit = self._normalize_unit(raw_unit)
            if canon_unit and canon_unit in ("m3", "m2", "m", "ton", "un"):
                unit = canon_unit
                break

        # Detectar classe de solo
        text_lower = text.lower()
        for pattern, soil_class in _SOIL_CLASS_MAP.items():
            if pattern in text_lower:
                qualifiers.append(f"solo_class:{soil_class}")
                break

        return {
            "unit": unit,
            "dimensions": dimensions,
            "qualifiers": qualifiers,
            "materials": materials,
            "method": None,
            "context": {},
            "missing_attributes": [],
        }

    def _vocabulary_mapping(self, text: str, raw_fields: dict) -> dict:
        """Mapeia texto para activity_type, domain via vocabulário controlado."""
        text_lower = text.lower()
        fields = dict(raw_fields)

        domain: DomainType | None = None
        activity_type: str | None = None
        best_match_len = 0

        # Busca por alias (mais longo vence — precisão)
        for alias, (dom, act) in self._activity_aliases.items():
            if alias in text_lower and len(alias) > best_match_len:
                domain = dom  # type: ignore[assignment]
                activity_type = act
                best_match_len = len(alias)

        fields["domain"] = domain or "other"
        fields["activity_type"] = activity_type or "unknown"

        # Mapear qualifiers de solo para contexto
        soil_qualifier = next(
            (q for q in fields.get("qualifiers", []) if q.startswith("solo_class:")),
            None,
        )
        if soil_qualifier:
            soil_class = soil_qualifier.split(":")[1]
            ctx = dict(fields.get("context", {}))
            ctx["soil_class"] = soil_class
            fields["context"] = ctx

        return fields

    def _needs_fallback(self, fields: dict) -> bool:
        """Verdadeiro se unit ou domain estão ausentes após extração determinística."""
        return fields.get("unit") is None or fields.get("domain") in (None, "other")

    def _llm_fallback(self, raw_text: str, fields: dict) -> dict:
        """LLM fallback — apenas se allow_llm_fallback=True.

        Interface mínima: self._llm deve ter método
        ``complete(prompt: str) -> str``.
        """
        # Implementação stub — projeto deve injetar cliente LLM real
        if not hasattr(self._llm, "complete"):
            return fields
        prompt = (
            "Extraia do texto a seguir: unidade de medida (m3/m2/m/ton/un), "
            "domain (earthwork/pavement/drainage/structure/other), "
            "activity_type. Responda em JSON com chaves unit, domain, activity_type.\n"
            f"Texto: {raw_text[:300]}"
        )
        try:
            import json as _json

            response = self._llm.complete(prompt)  # type: ignore[union-attr]
            parsed = _json.loads(response)
            updated = dict(fields)
            if not fields.get("unit") and parsed.get("unit"):
                updated["unit"] = parsed["unit"]
            if fields.get("domain") in (None, "other") and parsed.get("domain"):
                updated["domain"] = parsed["domain"]
            if fields.get("activity_type") in (None, "unknown") and parsed.get("activity_type"):
                updated["activity_type"] = parsed["activity_type"]
            return updated
        except Exception:
            return fields

    def _build_and_validate(
        self,
        raw: str,
        sid: str,
        fields: dict,
    ) -> SemanticIntent:
        """Constrói SemanticIntent e valida invariantes.

        Raises:
            SemanticParseError: se qualquer invariante for violado.
        """
        # Invariante 1: unit obrigatório
        if not fields.get("unit"):
            raise SemanticParseError(raw, "missing_unit", missing=["unit"])

        # Invariante 2: domain "other" sem missing_attributes populado
        domain = fields.get("domain") or "other"
        activity_type = fields.get("activity_type") or "unknown"
        missing_attrs = list(fields.get("missing_attributes", []))

        if domain == "other" and not missing_attrs:
            missing_attrs = ["domain", "activity_type"]

        # Invariante 3: dimensões não embutidas em qualifiers
        for q in fields.get("qualifiers", []):
            if _RE_NUMBER.search(q) and not q.startswith("solo_class:"):
                raise SemanticParseError(
                    raw,
                    "dimension_in_freetext",
                    missing=["dimensions"],
                )

        # Cálculo de confiança
        confidence = ExtractionConfidence(
            domain=0.9 if domain != "other" else 0.3,
            activity_type=0.9 if activity_type != "unknown" else 0.3,
            unit=0.95 if fields.get("unit") else 0.0,
            dimensions=0.8 if fields.get("dimensions") else 0.5,
            materials=0.7 if fields.get("materials") else 0.0,
        )

        return SemanticIntent(
            raw_text=raw,
            scope_item_id=sid,
            domain=domain,  # type: ignore[arg-type]
            activity_type=activity_type,
            unit=fields["unit"],
            dimensions=fields.get("dimensions", []),
            qualifiers=[
                q
                for q in fields.get("qualifiers", [])
                if not q.startswith("solo_class:")  # já movido para context
            ],
            materials=fields.get("materials", []),
            method=fields.get("method"),
            context=fields.get("context", {}),
            extraction_confidence=confidence,
            missing_attributes=missing_attrs,
            used_llm_fallback=fields.get("used_llm_fallback", False),
        )

    def _normalize_unit(self, raw_unit: str) -> str | None:
        """Mapeia alias de unidade para forma canônica."""
        return self._unit_aliases.get(raw_unit.strip().lower())


__all__ = ["SemanticExtractor"]
