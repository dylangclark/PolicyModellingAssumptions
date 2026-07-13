from __future__ import annotations

from typing import Type

from .base import SourceAdapter
from .boc_valet import BankOfCanadaValetAdapter
from .eia_v2 import EIAOpenDataAdapter
from .statcan_wds import StatisticsCanadaWDSAdapter
from .world_bank_pink_sheet import WorldBankPinkSheetAdapter

ADAPTERS: dict[str, Type[SourceAdapter]] = {
    "boc_valet": BankOfCanadaValetAdapter,
    "statcan_wds": StatisticsCanadaWDSAdapter,
    "eia_v2": EIAOpenDataAdapter,
    "world_bank_pink_sheet": WorldBankPinkSheetAdapter,
}


def get_adapter(name: str) -> Type[SourceAdapter]:
    try:
        return ADAPTERS[name]
    except KeyError as exc:
        available = ", ".join(sorted(ADAPTERS))
        raise KeyError(f"Unknown adapter {name!r}. Available adapters: {available}") from exc


__all__ = ["ADAPTERS", "SourceAdapter", "get_adapter"]
