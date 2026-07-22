"""Repositório de insumos baseada no catálogo carregado."""

from __future__ import annotations

from datetime import date
from typing import Any, Literal

# Fonte de resolução de preço (cascata ADR-038/ADR-040)
FontePreco = Literal["PROJECT_OVERRIDE", "SICRO_REGIONAL", "HISTORICO_SCD2", "MASTER_BASE"]


def _rp_check_override(
    codigo: str,
    overrides: dict | None,
    jurisdicao_id: str | None,
) -> tuple[float, FontePreco] | None:
    """Layer 1: PROJECT_OVERRIDE — checks direct and composite-key overrides."""
    if not overrides:
        return None
    if codigo in overrides:
        override = overrides[codigo]
        preco = override.get("preco_calibrado") or override.get("preco_unitario", 0.0)
        return float(preco), "PROJECT_OVERRIDE"
    composite_key = f"{codigo}::{jurisdicao_id or 'BASE'}"
    if composite_key in overrides:
        override = overrides[composite_key]
        preco = override.get("preco_calibrado") or override.get("preco_unitario") or override.get("preco") or 0.0
        return float(preco), "PROJECT_OVERRIDE"
    return None


def _rp_sicro_regional(
    insumo: dict,
    jurisdicao_id: str | None,
) -> tuple[float, FontePreco] | None:
    """Layer 2: SICRO_REGIONAL — checks regionalizacao block."""
    if not (jurisdicao_id and "regionalizacao" in insumo):
        return None
    regz = insumo["regionalizacao"]
    if isinstance(regz, dict):
        reg = regz.get(jurisdicao_id)
    elif isinstance(regz, list):
        reg = next((r for r in regz if r.get("jurisdicao_id") == jurisdicao_id), None)
    else:
        reg = None
    if reg and reg.get("preco") is not None:
        return float(reg["preco"]), "SICRO_REGIONAL"
    return None


def _rp_historico_scd2(
    insumo: dict,
    data_referencia: object | None,
) -> tuple[float, FontePreco] | None:
    """Layer 3a: HISTORICO_SCD2 — SCD Type-2 date-ranged lookup."""
    from datetime import date as _date

    if data_referencia is None or not insumo.get("historico_precos"):
        return None
    try:
        data_ref = data_referencia if isinstance(data_referencia, _date) else _date.fromisoformat(str(data_referencia))
        for registro in reversed(insumo["historico_precos"]):
            d_inicio = _date.fromisoformat(registro["data_inicio_vigencia"])
            d_fim_raw = registro.get("data_fim_vigencia")
            d_fim = _date.fromisoformat(d_fim_raw) if d_fim_raw else _date.max
            if d_inicio <= data_ref <= d_fim:
                return float(registro["preco_unitario"]), "HISTORICO_SCD2"
    except (ValueError, KeyError):
        pass
    return None


def _lookup_preco_historico(historico: list, data_referencia) -> float | None:
    try:
        data_ref = data_referencia if isinstance(data_referencia, date) else date.fromisoformat(str(data_referencia))
        for registro in reversed(historico):
            d_inicio = date.fromisoformat(registro["data_inicio_vigencia"])
            d_fim_raw = registro.get("data_fim_vigencia")
            d_fim = date.fromisoformat(d_fim_raw) if d_fim_raw else date.max
            if d_inicio <= data_ref <= d_fim:
                return registro["preco_unitario"]
    except (ValueError, KeyError):
        pass
    return None


class RepositorioInsumo:
    """Providencia consultas de existência e lookup de insumos."""

    def __init__(self, catalogo: dict[str, Any]):
        self._insumos: dict[str, dict[str, Any]] = {
            item["codigo"]: item for item in catalogo.get("insumos", []) if isinstance(item, dict) and "codigo" in item
        }
        self._producoes: dict[str, dict[str, Any]] = {
            item["id"]: item for item in catalogo.get("producoes", []) if isinstance(item, dict) and "id" in item
        }

    def producao_existe(self, codigo: str) -> bool:
        return codigo in self._producoes

    def obter_producao(self, codigo: str) -> dict[str, Any] | None:
        return self._producoes.get(codigo)

    def obter_insumo(self, codigo: str) -> dict[str, Any] | None:
        return self._insumos.get(codigo)

    def preco_na_data(self, codigo: str, data_referencia: Any = None) -> float | None:
        """Obtém o preço do insumo na data arbitrada do escopo.

        Ordem de resolução:
          1. InsumoVersionado (SCD Type 2 via 'versoes')
          2. historico_precos do Insumo (lista de HistoricoPreco)
          3. preco_unitario flat (legado)
        """
        insumo = self.obter_insumo(codigo)
        if not insumo:
            return None

        # 1. InsumoVersionado com snapshot por período YYYY-MM
        if "versoes" in insumo:
            from concilium.domain.models.catalog.versioned import InsumoVersionado

            try:
                iv = InsumoVersionado.model_validate(insumo)
                return iv.preco_em(data_referencia)
            except Exception:
                pass

        # 2. SCD Type 2 via historico_precos (ADR-041)
        if data_referencia is not None and insumo.get("historico_precos"):
            preco = _lookup_preco_historico(insumo["historico_precos"], data_referencia)
            if preco is not None:
                return preco

        # 3. Fallback plano
        return insumo.get("preco_unitario")

    def resolver_preco(
        self,
        codigo: str,
        jurisdicao_id: str | None = None,
        overrides: dict[str, Any] | None = None,
        data_referencia: date | None = None,
    ) -> tuple[float, FontePreco]:
        """Resolve o preço efetivo com cascata de 3 camadas (ADR-038 §D4 + ADR-040 §D2).

        Prioridade:
          1. PROJECT_OVERRIDE — override de projeto calibrado pelo coordenador
          2. SICRO_REGIONAL   — preço regionalizado via bloco `regionalizacao`
          3. MASTER_BASE      — `historico_precos` SCD-2 ou `preco_unitario` flat

        Returns:
            (preco, fonte) — preço efetivo e string de rastreabilidade da fonte
        """
        result = _rp_check_override(codigo, overrides, jurisdicao_id)
        if result is not None:
            return result

        insumo = self._insumos.get(codigo)
        if not insumo:
            return 0.0, "MASTER_BASE"

        # 2. Preço SICRO regional
        result = _rp_sicro_regional(insumo, jurisdicao_id)
        if result is not None:
            return result

        # 3. Master base: SCD-2 histórico ou flat
        result = _rp_historico_scd2(insumo, data_referencia)
        if result is not None:
            return result

        preco = insumo.get("preco_unitario", 0.0)
        return float(preco) if preco is not None else 0.0, "MASTER_BASE"

    def atualizar_preco(
        self,
        codigo: str,
        novo_preco: float,
        data_vigencia: date,
        fonte: str | None = None,
        nota: str | None = None,
    ) -> bool:
        """Aplica SCD Type 2: fecha registro anterior e abre novo (ADR-041 §D2).

        `nota` (ADR-145 §D4) é gravada no próprio registro histórico — como
        cada chamada abre um novo registro em `historico_precos` (nunca
        sobrescreve), a trilha de justificativas por alteração é append-only
        por construção, sem precisar de um array paralelo.

        Modifica o dict em memória. A persistência fica a cargo do chamador
        (tipicamente um service ou script de migração de catálogo).

        Returns:
            True se o insumo foi encontrado e atualizado; False caso contrário.
        """
        insumo = self._insumos.get(codigo)
        if not insumo:
            return False

        historico: list[dict[str, Any]] = insumo.setdefault("historico_precos", [])
        hoje_iso = data_vigencia.isoformat()

        # Fechar o registro ainda em aberto (sem data_fim_vigencia)
        for registro in historico:
            if registro.get("data_fim_vigencia") is None:
                vigencia_anterior = date.fromisoformat(registro["data_inicio_vigencia"])
                if vigencia_anterior < data_vigencia:
                    registro["data_fim_vigencia"] = hoje_iso

        # Abrir novo registro
        historico.append(
            {
                "preco_unitario": novo_preco,
                "data_inicio_vigencia": hoje_iso,
                "data_fim_vigencia": None,
                "fonte": fonte,
                "nota": nota,
            }
        )

        # Atualizar o campo flat para compatibilidade com código legado
        insumo["preco_unitario"] = novo_preco
        return True

    def insumo_existe(self, codigo: str) -> bool:
        return codigo in self._insumos

    def funcao_existe(self, codigo: str) -> bool:
        return self._insumo_tipo_existe(codigo, "MAO_OBRA")

    def equipamento_existe(self, codigo: str) -> bool:
        return self._insumo_tipo_existe(codigo, "EQUIPAMENTO")

    def _insumo_tipo_existe(self, codigo: str, tipo: str) -> bool:
        insumo = self.obter_insumo(codigo)
        return bool(insumo and insumo.get("tipo") == tipo)
