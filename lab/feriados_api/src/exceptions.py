from __future__ import annotations


class FeriadosAPIError(Exception):
    def __init__(
        self,
        status: int,
        message: str,
    ):
        self.status = status
        self.message = message

        super().__init__(
            f"Feriados API error ({status}): {message}"
        )

