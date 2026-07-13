# Authoritative source register

This document describes the first production acquisition layer. Configuration is executable in `config/sources.yml`; this file explains why each source is included, what is published, and what remains gated.

## Publication principle

A source may be collected without being released publicly. The controls are separate:

- `enabled`: the Raspberry Pi collector may acquire and normalize the source.
- `publish_enabled`: validated records may enter `data/export/` and `site/data/`.
- `required`: the source must pass collection, coverage and freshness checks before a complete release can be published.
- `collection_stale_after_days`: maximum age of the latest successful collection run.
- `stale_after_days`: maximum age of the newest reference period, set at source, dataset, series or output level.

A failed or partial source, a missing configured output, stale data, any rejected record, or a skipped required source causes the CLI to return a non-zero status and skip the export refresh. The weekly script therefore leaves the last committed GitHub dataset unchanged. Selective source runs are diagnostic and cannot publish a partial release.

## Implemented sources

### Bank of Canada Valet API

Source ID: `bank_of_canada_valet`

Official interface: `https://www.bankofcanada.ca/valet/docs`

Configured series:

| Valet series | Registry variable | Frequency | Canonical unit |
|---|---|---:|---|
| `V39079` | Bank of Canada target overnight rate | daily | percent |
| `BD.CDN.10YR.DQ.YLD` | Government of Canada 10-year benchmark yield | daily | percent |
| `FXUSDCAD` | Canadian dollars per U.S. dollar | daily | CAD per USD |

The adapter requests the configured series together, archives the exact JSON response, and uses a 45-day lookback after bootstrap to capture recent revisions. If a new series is added to an existing source, it backfills from the configured start date instead of silently collecting only the recent lookback.

### Statistics Canada Web Data Service

Source ID: `statistics_canada_wds`

Official interface: `https://www.statcan.gc.ca/en/developers/wds`

Configured tables:

| Table | Registry outputs | Frequency | Geography |
|---|---|---:|---|
| `17-10-0009-01` / PID `17100009` | population level and year-over-year growth | quarterly | British Columbia |
| `14-10-0287-01` / PID `14100287` | employment and labour-force levels and year-over-year growth | monthly | British Columbia |
| `18-10-0004-01` / PID `18100004` | all-items CPI and inflation | monthly | British Columbia |
| `18-10-0289-01` / PID `18100289` | non-residential building construction price index and inflation | quarterly | Vancouver |

The adapter does not hard-code vectors. It downloads cube metadata, resolves one coordinate from anchored dimension/member selectors, resolves the current vector, and caches that mapping with the table issue date. A changed label, ambiguous selector, archived table, or unresolved coordinate fails loudly.

Statistics Canada returns the decimal in the data value but provides the scalar separately. The adapter applies the official scalar-code multiplier before unit validation. The construction-price configuration records `18-10-0289-01` as the successor to archived table `18-10-0276-01`.

### CMHC housing starts via Statistics Canada

Source ID: `cmhc_via_statistics_canada`

Configured table: `34-10-0158-01` / PID `34100158`

Output: British Columbia housing starts, seasonally adjusted at an annual rate.

Collection is enabled, but `publish_enabled` is false. The values remain internal until the CMHC licence and downstream redistribution terms are documented. This gate is intentional and should not be removed solely because the table is accessible through a Statistics Canada interface.

### U.S. Energy Information Administration Open Data API

Source ID: `eia_open_data`

Official interface: `https://www.eia.gov/opendata/`

Configured monthly series:

| EIA series | Registry variable | Canonical unit |
|---|---|---|
| `RNGWHHD` | Henry Hub natural gas spot price | USD/MMBtu |
| `RWTC` | WTI crude oil spot price | USD/barrel |
| `RBRTE` | Brent crude oil spot price | USD/barrel |

The adapter uses API v2, archives one response per series, redacts the API key from URLs, request metadata, exceptions, run logs and public provenance, and looks back three months on incremental runs. It is required for the phase-one complete release, so `EIA_API_KEY` must be configured on the Pi.

### World Bank Commodity Price Data (Pink Sheet)

Source ID: `world_bank_pink_sheet`

Official page: `https://www.worldbank.org/en/research/commodity-markets`

Official monthly workbook: `https://www.worldbank.org/content/dam/Worldbank/GEP/GEPcommodities/CMO-Historical-Data-Monthly.xlsx`

Configured columns:

| Workbook column | Registry variable | Canonical unit |
|---|---|---|
| Copper | copper price | USD/metric tonne |
| LNG, Japan | Japan LNG import-price proxy | USD/MMBtu |

The Japan LNG column is explicitly flagged `proxy_series` and `not_jkm`. It must not be displayed or analyzed as Platts JKM. The adapter selects the monthly sheet by configured regular expression, matches headers exactly, and fails or warns rather than guessing between multiple columns.

## Staged authoritative sources

The following source registrations are present but disabled until an adapter and fixture tests are added:

- Government of British Columbia household estimates and projections;
- Canada Energy Regulator electricity trade summaries;
- official B.C./federal carbon-price schedules;
- ICBC or Statistics Canada zero-emission vehicle stock;
- B.C. River Forecast Centre snowpack indicators; and
- public or licensed AECO benchmark data.

## Onboarding checklist

An authoritative source is enabled only after all of the following are recorded:

1. authoritative publisher and stable acquisition route;
2. exact series/table identifiers and variable definitions;
3. original and canonical units, including currency and price-year treatment;
4. licence, automated-access, and redistribution notes;
5. archived raw response with SHA-256 and sanitized request context;
6. deterministic parser and fixture-based tests;
7. revision lookback or vintage strategy;
8. expected-value bounds and quality flags;
9. public-release gate; and
10. failure behavior that cannot publish a partial refresh.

## First live-run acceptance checks

For each source, the operator should verify:

- the resolved source label and unit match the configuration;
- the newest period agrees with the publisher's public page;
- at least two historical points agree with the source;
- the first incremental run produces unchanged rather than duplicate records;
- a deliberately altered fixture is rejected;
- no credential appears in `data/raw`, SQLite run errors, exports, or Git history; and
- source failures leave the previously committed export unchanged.
