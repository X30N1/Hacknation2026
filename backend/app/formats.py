from datetime import date, datetime
from typing import Annotated

from pydantic import BeforeValidator, PlainSerializer

# GG-MM:DD-MM-RRRR  ->  godzina-minuta:dzień-miesiąc-rok
TIMESTAMP_FMT = "%H-%M:%d-%m-%Y"
# DD-MM-RRRR
DATE_FMT = "%d-%m-%Y"


def _parse_date(v):
    if isinstance(v, str):
        return datetime.strptime(v, DATE_FMT).date()
    return v


def _parse_timestamp(v):
    if isinstance(v, str):
        return datetime.strptime(v, TIMESTAMP_FMT)
    return v


ApiDate = Annotated[
    date,
    BeforeValidator(_parse_date),
    PlainSerializer(lambda d: d.strftime(DATE_FMT), return_type=str),
]

ApiTimestamp = Annotated[
    datetime,
    BeforeValidator(_parse_timestamp),
    PlainSerializer(lambda d: d.strftime(TIMESTAMP_FMT), return_type=str),
]
