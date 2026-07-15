from __future__ import annotations

from typing import Type

from .base import SourceAdapter
from .bc_budget import BCBudgetForecastAdapter
from .bc_budget_history import BCBudgetHistoryAdapter
from .bc_households import BCHouseholdsAdapter
from .bc_hydro_quick_facts import BCHydroQuickFactsAdapter
from .bc_hydro_history import BCHydroHistoryAdapter
from .bc_population import BCStatsPopulationAdapter
from .bcer_production import BCERProductionAdapter
from .boc_valet import BankOfCanadaValetAdapter
from .cer_electricity_trade import CERElectricityTradeAdapter
from .cer_gas_production import CERGasProductionAdapter
from .document_assumptions import DocumentAssumptionsAdapter
from .eia_v2 import EIAOpenDataAdapter
from .icbc_vehicle_population import ICBCVehiclePopulationAdapter
from .fortisbc_history import FortisBCHistoryAdapter
from .nrcan_neud import NRCanNEUDAdapter
from .statcan_wds import StatisticsCanadaWDSAdapter
from .world_bank_pink_sheet import WorldBankPinkSheetAdapter

ADAPTERS: dict[str, Type[SourceAdapter]] = {
    "boc_valet": BankOfCanadaValetAdapter,
    "statcan_wds": StatisticsCanadaWDSAdapter,
    "eia_v2": EIAOpenDataAdapter,
    "world_bank_pink_sheet": WorldBankPinkSheetAdapter,
    "cer_electricity_trade": CERElectricityTradeAdapter,
    "cer_gas_production": CERGasProductionAdapter,
    "nrcan_neud": NRCanNEUDAdapter,
    "bc_budget_forecast": BCBudgetForecastAdapter,
    "bc_budget_history": BCBudgetHistoryAdapter,
    "bc_households": BCHouseholdsAdapter,
    "bc_stats_population": BCStatsPopulationAdapter,
    "icbc_vehicle_population": ICBCVehiclePopulationAdapter,
    "bcer_production": BCERProductionAdapter,
    "bc_hydro_quick_facts": BCHydroQuickFactsAdapter,
    "bc_hydro_history": BCHydroHistoryAdapter,
    "document_assumptions": DocumentAssumptionsAdapter,
    "fortisbc_history": FortisBCHistoryAdapter,
}


def get_adapter(name: str) -> Type[SourceAdapter]:
    try:
        return ADAPTERS[name]
    except KeyError as exc:
        available = ", ".join(sorted(ADAPTERS))
        raise KeyError(f"Unknown adapter {name!r}. Available adapters: {available}") from exc


__all__ = ["ADAPTERS", "SourceAdapter", "get_adapter"]
