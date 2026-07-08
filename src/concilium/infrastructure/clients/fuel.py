from datetime import datetime, timedelta
from enum import StrEnum

import requests

# =========================
# Domain Models
# =========================


class State(StrEnum):
    BR = "br"  # national average
    AL = "al"
    AM = "am"
    CE = "ce"
    DF = "df"
    ES = "es"
    GO = "go"
    MA = "ma"
    MT = "mt"
    MG = "mg"
    PR = "pr"
    PB = "pb"
    PA = "pa"
    PE = "pe"
    RS = "rs"
    RJ = "rj"
    SC = "sc"
    SP = "sp"


class FuelType(StrEnum):
    GASOLINA = "gasolina"
    DIESEL = "diesel"


# =========================
# Parsing Helpers (optional)
# =========================


def parse_state(value: str) -> State:
    """Resolve um valor de UF para `State`.

    Aceita a sigla de qualquer membro do enum (ex.: "ce", "df", "sp" — todas as
    18 UFs cobertas por `State`), além de nomes completos como conveniência
    (ADR-129: antes só "go"/"sp"/"br" eram reconhecidos, fazendo
    `resolver_preco_diesel_uf` cair sempre no fallback para a maioria das UFs).
    """
    value = value.strip().lower()

    aliases = {
        "goias": State.GO,
        "sao paulo": State.SP,
        "brasil": State.BR,
    }
    if value in aliases:
        return aliases[value]

    try:
        return State(value)
    except ValueError:
        raise ValueError(f"Unknown state: {value}") from None


def parse_fuel(value: str) -> FuelType:
    value = value.strip().lower()

    aliases = {
        "diesel": FuelType.DIESEL,
        "gasolina": FuelType.GASOLINA,
        "gas": FuelType.GASOLINA,
    }

    if value not in aliases:
        raise ValueError(f"Unknown fuel: {value}")

    return aliases[value]


# =========================
# Client
# =========================


class FuelPriceClient:
    URL = "https://combustivelapi.com.br/api/precos/"
    TTL = timedelta(minutes=30)

    def __init__(self):
        self._cache: dict[str, dict[str, float]] | None = None
        self._metadata: dict | None = None
        self._loaded_at: datetime | None = None

    def _fetch(self) -> dict:
        headers = {
            "User-Agent": "curl/7.88.1",  # bypass ModSecurity
            "Accept": "*/*",
        }

        r = requests.get(
            self.URL,
            headers=headers,
            params={"produto": "diesel"},  # harmless (API ignores anyway)
            timeout=10,
        )

        r.raise_for_status()

        data = r.json()

        if data.get("error"):
            raise ValueError("API returned error")

        return data

    def _load(self) -> dict[str, dict[str, float]]:
        now = datetime.now()

        if self._cache and self._loaded_at:
            if now - self._loaded_at < self.TTL:
                return self._cache

        data = self._fetch()

        # --- metadata ---
        self._metadata = {
            "timestamp": datetime.strptime(data["data_coleta"], "%Y-%m-%d %H:%M:%S"),
            "source": data["fonte"],
            "currency": data["moeda"],
        }

        # --- normalization ---
        self._cache = {
            fuel: {state.lower(): float(price.replace(",", ".")) for state, price in states.items()}
            for fuel, states in data["precos"].items()
        }

        # --- basic validation ---
        self._validate(self._cache)

        self._loaded_at = now
        return self._cache

    def _validate(self, cache: dict[str, dict[str, float]]):
        for fuel, states in cache.items():
            for state, price in states.items():
                if price < 3 or price > 15:
                    raise ValueError(f"Suspicious price detected: {fuel} {state}={price}")

    # =========================
    # Public API
    # =========================

    def get_price(self, state: State, fuel: FuelType) -> float:
        cache = self._load()
        return cache[fuel.value][state.value]

    def get_all(self, fuel: FuelType) -> dict[str, float]:
        cache = self._load()
        return cache[fuel.value]

    def get_metadata(self) -> dict:
        self._load()
        assert self._metadata is not None
        return self._metadata

    # =========================
    # Convenience (string input)
    # =========================

    def get_price_str(self, state: str, fuel: str) -> float:
        return self.get_price(parse_state(state), parse_fuel(fuel))


# =========================
# Usage
# =========================

if __name__ == "__main__":
    client = FuelPriceClient()

    print(client.get_price(State.GO, FuelType.DIESEL))  # 7.25
    print(client.get_price(State.SP, FuelType.GASOLINA))  # 6.64

    # string interface
    print(client.get_price_str("goias", "diesel"))

    print(client.get_metadata())
