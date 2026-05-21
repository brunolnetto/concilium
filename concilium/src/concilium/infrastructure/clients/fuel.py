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
    value = value.strip().lower()

    aliases = {
        "go": State.GO,
        "goias": State.GO,
        "sp": State.SP,
        "sao paulo": State.SP,
        "br": State.BR,
        "brasil": State.BR,
    }

    if value not in aliases:
        raise ValueError(f"Unknown state: {value}")

    return aliases[value]


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

    def _load(self):
        now = datetime.now()

        if self._cache and self._loaded_at:
            if now - self._loaded_at < self.TTL:
                return

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

    def _validate(self, cache: dict[str, dict[str, float]]):
        for fuel, states in cache.items():
            for state, price in states.items():
                if price < 3 or price > 15:
                    raise ValueError(f"Suspicious price detected: {fuel} {state}={price}")

    # =========================
    # Public API
    # =========================

    def get_price(self, state: State, fuel: FuelType) -> float:
        self._load()
        return self._cache[fuel.value][state.value]  # type: ignore[index]

    def get_all(self, fuel: FuelType) -> dict[str, float]:
        self._load()
        return self._cache[fuel.value]  # type: ignore[index]

    def get_metadata(self) -> dict:
        self._load()
        return self._metadata  # type: ignore[return-value]

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
