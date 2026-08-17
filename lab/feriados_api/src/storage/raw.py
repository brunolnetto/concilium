import json
from pathlib import Path
from datetime import datetime


def save_raw(
    payload,
    path="data/raw",
):

    Path(path).mkdir(
        parents=True,
        exist_ok=True,
    )

    filename = (
        datetime.utcnow()
        .strftime(
            "%Y%m%d_%H%M%S.json"
        )
    )


    with open(
        Path(path) / filename,
        "w",
        encoding="utf8",
    ) as f:

        json.dump(
            payload,
            f,
            ensure_ascii=False,
            indent=2,
        )