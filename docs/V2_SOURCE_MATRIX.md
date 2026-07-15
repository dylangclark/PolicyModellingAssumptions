# Version 2 source matrix

| Source family | Evidence type | Variables | Status in rc2 |
|---|---|---|---|
| B.C. Budgets 2021-2026 | Government forecast | GDP, employment, unemployment, population growth, CPI, retail sales, housing starts, exports, rates and exchange rate | Enabled; six official PDFs regression-tested |
| B.C. household estimates/projections | Observation and government forecast | Household level and growth | Enabled |
| BC Hydro service plans 2021-2026 | Utility forecast | Sales, load growth, exports, generation, imports, purchases, water, market prices, rates and capex | Enabled; six official PDFs regression-tested |
| BC Hydro annual reports 2020/21-2024/25 | Observation | Electricity sales and capex actuals | Enabled; five official PDFs regression-tested |
| BC Hydro-FortisBC collaboration | Utility forecast | Regional customer-growth and electrification-load assumptions | Enabled; current document recipe |
| FortisBC annual MD&A 2021-2025 | Observation, utility forecast and approved regulatory assumption | Sales, costs, actual/forecast capex, customers, rate base, ROE, equity and pension discount rate | Enabled optional; ten-document discovery and multi-year parser tests |
| B.C. transportation benefit-cost guidance | Government policy assumption | Social discount rate and decision context | Enabled optional; historical guidance flag |
| CER provincial gas production | Observation | B.C. marketable gas production | Enabled |
| CER electricity trade | Observation | Canada/B.C. trade indicators where available | Enabled |
| ICBC vehicle population | Observation and derived | BEV/PHEV stock and growth | Adapter ready; endpoint gate |
| BCER production archive | Observation | Gross reported B.C. natural-gas production | Adapter ready; schema/unit gate |
| BC Hydro Quick Facts | Observation | Historical peak demand | Parser ready; current-document gate |
| FortisBC rate reviews | Utility proposal and approved regulatory assumption | Sales, customers, capex, rate base, rate changes and escalation | Regulatory template staged |
| BCUC financial decisions | Approved regulatory assumption | ROE, equity, cost of debt, WACC and context-specific discount rates | Direct proceeding extraction staged |
| BC Hydro IRP filings | Utility forecast and scenario | Peak, energy/capacity gap, reserve margin, ELCC and DSM | Regulatory template staged |
| Bank of Canada expectations | Central-bank forecast and market consensus | GDP, inflation, rates, FX and recession probability | Current actuals enabled; expectation documents staged |
| Finance Canada consensus | Market consensus | Macro and commodity forecasts | Staged |
| CER Energy Futures | Scenario | Demand, production, generation and commodity assumptions | Staged |
| ECCC projections | Government scenario | Emissions, activity and policy assumptions | Staged |
| CMHC outlooks | Government forecast | Starts, completions, prices, vacancy and rents | Historical actuals enabled; outlook documents staged |
| Crown service plans | Government/Crown forecast | Service demand, fleet, building and capital plans | Framework staged |
| Selected SEDAR+ guidance | Private-sector guidance | Production, capex, unit costs, schedules and sensitivities | Targeted-entity framework staged |
| NREL ATB | Scenario and cost estimate | Battery, wind and solar costs/performance | Structured ingest staged |

Major-project inventories and realization modelling are not part of rc2.
