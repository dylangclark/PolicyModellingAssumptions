# Historical backfill design

## Purpose

The v2 backfill serves two functions:

1. test parsers against multiple publication layouts rather than only the newest document;
2. create an immediate history of forecasts, assumptions and observed results.

## Document manifest

| Source family | Historical span | Expected documents |
|---|---:|---:|
| B.C. Budget and Fiscal Plan | 2021-2026 | 6 |
| BC Hydro service plans | 2021/22-2026/27 vintages | 6 |
| BC Hydro Annual Service Plan Reports | 2020/21-2024/25 | 5 |
| FortisBC annual MD&A | FEI and FBC, 2021-2025 | 10 |
| B.C. benefit-cost guidance | published 2018 guidance | 1 |
| **Total** |  | **28** |

## Vintage preservation

Forecast natural keys include the publication or vintage date. A forecast for the same target year in two successive budgets or service plans is retained as two records. Observations may be revised by a publisher and therefore use the registry revision mechanism.

## Forecast-to-actual matching

Matches require the same:

- variable;
- canonical unit;
- geography;
- entity or utility;
- target/reference period.

The performance layer calculates signed error, absolute error and percentage error only after those scope checks pass.

## Structural generations

- B.C. Budget 2021-2025 uses a stable table family.
- Budget 2026 uses a separate raw-text parser because its PDF table encoding and layout changed.
- BC Hydro plans are tested across early and later table structures.
- FortisBC is tested across 2021, 2023 and 2025 disclosures for both utilities, including the 2023 cost-of-capital transition wording and 2025 actual-versus-forecast capital-expenditure disclosures.

## Coverage outputs

After each export, `scripts/build_history_coverage.py` writes:

- `site/data/history-coverage.json`;
- `data/export/history-coverage.json`;
- `data/export/history-coverage.csv`.

The report lists each expected document, whether records were parsed, the record count, the number of variables and the distribution of forecasts, observations and model parameters.

## Fail-closed behaviour

The collectors stop or mark the source failed when:

- an expected document is missing;
- a parser generation has not been explicitly approved;
- required table sections or year headers are missing;
- annual and quarterly values cannot be distinguished;
- a numeric result fails a plausibility guardrail;
- an unsupported record kind or missing evidence field is generated;
- a non-temporal parameter is assigned a forecast target period.
