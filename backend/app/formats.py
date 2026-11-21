from datetime import datetime
from typing import Annotated

from pydantic import BeforeValidator, PlainSerializer

# GG-MM:DD-MM-RRRR  ->  godzina-minuta:dzień-miesiąc-rok
TIMESTAMP_FMT = "%H-%M:%d-%m-%Y"


def _parse_timestamp(v):
    if isinstance(v, str):
        return datetime.strptime(v, TIMESTAMP_FMT)
    return v


ApiTimestamp = Annotated[
    datetime,
    BeforeValidator(_parse_timestamp),
    PlainSerializer(lambda d: d.strftime(TIMESTAMP_FMT), return_type=str),
]
