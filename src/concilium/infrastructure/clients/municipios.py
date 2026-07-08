"""Cliente de referência municipal — ADR-129 D1.

Fornece coordenadas (centróide) e população por município, insumo básico
para a camada de resolução de preço por proximidade geográfica (ADR-129
D2/D4). Consumido por `application/services/catalog/geo_diesel_resolver.py`.

Fonte de dados
--------------
O piloto (ADR-129) usa um dataset estático embutido (`data/municipios_referencia.json`),
curado a partir de dados públicos do IBGE (população — Censo/estimativa mais
recente disponível — e coordenadas de centróide urbano das capitais estaduais).

A API de localidades do IBGE (`servicodados.ibge.gov.br/api/v1/localidades`)
não expõe coordenadas nem população num único endpoint simples — obter esses
dois atributos por HTTP exigiria compor múltiplas APIs (localidades + malhas
geográficas + agregados do Censo), o que a ADR-129 (§D2) deliberadamente
deixa fora do escopo do piloto. Por isso `MunicipioReferenceClient` isola o
carregamento da fonte via `dataset_path` — permitindo trocar o dataset
estático por uma integração ao vivo no futuro sem alterar os consumidores.

Cache
-----
O dataset é lido do disco uma única vez por instância (cache em memória) —
população e coordenadas de município mudam muito pouco entre atualizações
(mesmo racional de TTL longo usado por `openmeteo.py` para dados quase-estáticos).
"""

from __future__ import annotations

from dataclasses import dataclass
from math import asin, cos, radians, sin, sqrt
from pathlib import Path

_DEFAULT_DATASET_PATH = Path(__file__).parent / "data" / "municipios_referencia.json"

_RAIO_TERRA_KM = 6371.0088

# ADR-129 D4: municípios cuja diferença de distância ao ponto de referência é
# menor que este limiar são tratados como "equidistantes" — desempate por população.
_EPSILON_EMPATE_KM = 0.5


@dataclass(frozen=True)
class MunicipioReferencia:
    """Município de referência (IBGE) — coordenadas de centróide e população."""

    codigo_ibge: str
    nome: str
    uf: str
    latitude: float
    longitude: float
    populacao: int


def haversine_km(lat1: float, lng1: float, lat2: float, lng2: float) -> float:
    """Distância em linha reta (grande círculo) entre dois pontos, em km."""
    rlat1, rlng1, rlat2, rlng2 = (radians(v) for v in (lat1, lng1, lat2, lng2))
    dlat = rlat2 - rlat1
    dlng = rlng2 - rlng1
    a = sin(dlat / 2) ** 2 + cos(rlat1) * cos(rlat2) * sin(dlng / 2) ** 2
    return 2 * _RAIO_TERRA_KM * asin(sqrt(a))


class MunicipioReferenceClient:
    """Cliente de referência municipal com cache em memória (ADR-129 D1)."""

    def __init__(self, dataset_path: Path | str | None = None) -> None:
        self._dataset_path = Path(dataset_path) if dataset_path is not None else _DEFAULT_DATASET_PATH
        self._cache: list[MunicipioReferencia] | None = None

    def _load(self) -> list[MunicipioReferencia]:
        if self._cache is not None:
            return self._cache

        import json

        try:
            raw = json.loads(self._dataset_path.read_text(encoding="utf-8"))
        except FileNotFoundError as exc:
            raise FileNotFoundError(f"Dataset de municípios não encontrado: {self._dataset_path}") from exc
        except json.JSONDecodeError as exc:
            raise ValueError(f"Dataset de municípios corrompido/inválido: {self._dataset_path}") from exc

        municipios = [
            MunicipioReferencia(
                codigo_ibge=str(m["codigo_ibge"]),
                nome=str(m["nome"]),
                uf=str(m["uf"]).upper(),
                latitude=float(m["latitude"]),
                longitude=float(m["longitude"]),
                populacao=int(m["populacao"]),
            )
            for m in raw.get("municipios", [])
        ]
        self._cache = municipios
        return municipios

    def listar_por_uf(self, uf: str) -> list[MunicipioReferencia]:
        """Retorna todos os municípios de referência de uma UF (ex.: 'CE')."""
        uf_norm = uf.strip().upper()
        return [m for m in self._load() if m.uf == uf_norm]

    def municipio_mais_proximo(
        self,
        latitude: float,
        longitude: float,
        raio_km: float | None = None,
    ) -> MunicipioReferencia | None:
        """Resolve o município de referência mais próximo de um ponto (ADR-129 D2/D4).

        Calcula distância haversine do ponto a todos os municípios do dataset.
        Se `raio_km` for informado e nenhum município estiver dentro do raio,
        retorna `None` (o chamador deve cair para o comportamento por UF).

        Desempate (D4): quando dois ou mais municípios estão a distância
        "comparável" do ponto (diferença menor que `_EPSILON_EMPATE_KM`),
        vence o de maior população — maior probabilidade de ter mercado
        líquido/posto de referência estável.
        """
        municipios = self._load()
        if not municipios:
            return None

        distancias = [(m, haversine_km(latitude, longitude, m.latitude, m.longitude)) for m in municipios]
        distancias.sort(key=lambda par: par[1])

        menor_distancia = distancias[0][1]
        if raio_km is not None and menor_distancia > raio_km:
            return None

        candidatos = [m for m, d in distancias if d - menor_distancia <= _EPSILON_EMPATE_KM]
        return max(candidatos, key=lambda m: m.populacao)
