"""ADR-129 D2/D3/D4/D5 — resolução de preço de diesel por proximidade geográfica.

Orquestra três peças introduzidas/reconectadas pela ADR-129:

- `Escopo.coordenadas_lat/lng` + `Escopo.raio_cotacao_km` (D5) — ponto de partida.
- `MunicipioReferenceClient` (D1) — município de referência mais próximo, com
  desempate por população (D4).
- `FuelPriceClient` (D3, reconectado via `pu_calculator.resolver_preco_diesel_uf`)
  — preço real de diesel por UF.

Importante (ADR-129 §D2): o `FuelPriceClient` só expõe preço por **UF**, não por
município. "Município mais próximo" aqui decide *qual UF de referência* usar
quando o sítio de obra está perto da fronteira entre estados — não produz um
preço município-específico (isso dependeria de uma fonte de dado municipal que
ainda não existe no sistema).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Protocol

from concilium.application.catalog.pu_calculator import FontePrecoDiesel, resolver_preco_diesel_uf


class EscopoGeoLike(Protocol):
    """Contrato estrutural mínimo consumido por este módulo.

    `Escopo` (pydantic) satisfaz este protocolo automaticamente. Permite
    chamadores sem um `Escopo` completo (ex.: skill de precificação, que só
    tem os campos de `inputs` dict) passar um objeto leve, sem precisar
    instanciar um `Escopo` inteiro (que exige `escopo_id`, `projeto_id`,
    `data_inicio`, etc. — irrelevantes para a resolução de preço de diesel).
    """

    raio_cotacao_km: float | None
    coordenadas_lat: float
    coordenadas_lng: float
    jurisdicao_id: str | None


@dataclass(frozen=True)
class ParametrosGeoDiesel:
    """Implementação mínima de `EscopoGeoLike` para chamadores sem `Escopo` completo."""

    raio_cotacao_km: float | None = None
    coordenadas_lat: float = 0.0
    coordenadas_lng: float = 0.0
    jurisdicao_id: str | None = None


if TYPE_CHECKING:
    from concilium.infrastructure.clients.fuel import FuelPriceClient
    from concilium.infrastructure.clients.municipios import MunicipioReferenceClient

# ADR-129 §Riscos: coordenadas (0.0, 0.0) — ponto no meio do Atlântico — são o valor
# placeholder usado por várias rotas/tools quando o usuário não informa localização
# real. Tratadas como "sem localização real" mesmo que raio_cotacao_km esteja preenchido.
_COORDENADAS_PLACEHOLDER = (0.0, 0.0)


def _uf_de_jurisdicao(jurisdicao_id: str | None) -> str | None:
    """Extrai a UF de um jurisdicao_id no formato 'BR-CE' (ADR-038). None se ausente/inválido."""
    if not jurisdicao_id or "-" not in jurisdicao_id:
        return None
    _pais, _, uf = jurisdicao_id.partition("-")
    return uf or None


def resolver_uf_por_proximidade(
    escopo: EscopoGeoLike,
    municipio_client: MunicipioReferenceClient,
) -> str | None:
    """ADR-129 D2/D5: resolve a UF de referência a partir de proximidade geográfica.

    Retorna `None` (opt-out) quando:
        - `escopo.raio_cotacao_km` é `None` — camada de proximidade nunca ativa
          por padrão (ADR-129 §Riscos);
        - coordenadas são o placeholder `(0.0, 0.0)`, mesmo com raio preenchido;
        - nenhum município do dataset de referência está dentro do raio.

    Quando `None` é retornado, o chamador deve cair para o comportamento atual
    por UF (`Escopo.jurisdicao_id`, ADR-066).
    """
    if escopo.raio_cotacao_km is None:
        return None

    coordenadas = (escopo.coordenadas_lat, escopo.coordenadas_lng)
    if coordenadas == _COORDENADAS_PLACEHOLDER:
        return None

    resultado = municipio_client.municipio_mais_proximo(
        escopo.coordenadas_lat,
        escopo.coordenadas_lng,
        raio_km=escopo.raio_cotacao_km,
    )
    if resultado is None:
        return None
    return resultado.uf


def resolver_preco_diesel_escopo(
    escopo: EscopoGeoLike,
    municipio_client: MunicipioReferenceClient,
    fuel_client: FuelPriceClient | None,
) -> tuple[float, FontePrecoDiesel]:
    """ADR-129 D2+D3: resolve o preço de diesel para um `Escopo`, ponta a ponta.

    Ordem de resolução da UF de referência:
        1. Proximidade geográfica (D2), se `raio_cotacao_km` estiver ativo e um
           município estiver dentro do raio;
        2. `Escopo.jurisdicao_id` (ex.: "BR-CE" → "CE"), comportamento atual (ADR-066);
        3. Nenhuma UF resolvida — `resolver_preco_diesel_uf` cai para
           `PRECO_DIESEL_REFERENCIA`.

    Delega a consulta em si (e o fallback por indisponibilidade da API externa)
    para `pu_calculator.resolver_preco_diesel_uf` (D3).
    """
    uf = resolver_uf_por_proximidade(escopo, municipio_client) or _uf_de_jurisdicao(escopo.jurisdicao_id)
    return resolver_preco_diesel_uf(uf, fuel_client)


def resolver_preco_diesel(
    *,
    raio_cotacao_km: float | None,
    coordenadas_lat: float,
    coordenadas_lng: float,
    jurisdicao_id: str | None,
    municipio_client: MunicipioReferenceClient,
    fuel_client: FuelPriceClient | None,
) -> tuple[float, FontePrecoDiesel]:
    """Conveniência sobre `resolver_preco_diesel_escopo` para chamadores sem `Escopo`
    completo (ex.: skill de precificação, que só tem valores soltos de `inputs`)."""
    escopo = ParametrosGeoDiesel(
        raio_cotacao_km=raio_cotacao_km,
        coordenadas_lat=coordenadas_lat,
        coordenadas_lng=coordenadas_lng,
        jurisdicao_id=jurisdicao_id,
    )
    return resolver_preco_diesel_escopo(escopo, municipio_client, fuel_client)
