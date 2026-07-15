# Changelog

## 0.1.1 — 2026-07-13

- Updated Statistics Canada selectors for the current `Total - Gender` and
  `Division composite` member labels.
- Replaced the stale World Bank Pink Sheet download with the current official
  workbook and added support for workbooks whose period-column header is blank.
- Strengthened public artifact validation so licence-gated sources and excluded
  record kinds cannot pass deployment validation.
- Restricted data-driven links in the static browser to HTTP and HTTPS URLs.
- Added regression tests for the current Pink Sheet workbook structure and the
  independent publication gate.

## 0.1.0 — 2026-07-13

- Added the versioned SQLite evidence registry and content-addressed source archive.
- Added Bank of Canada Valet, Statistics Canada WDS, EIA API v2 and World Bank Pink Sheet adapters.
- Added controlled variable and source registries covering the initial B.C. economic and energy-policy scope.
- Added validation, revision tracking, required-series coverage and freshness gates, public artifact validation, CSV/JSON exports and a static GitHub Pages browser.
- Added Raspberry Pi systemd deployment files and a locked, fail-closed weekly Git commit workflow.
- Added a deterministic regulatory-PDF recipe engine and human review queue.
- Migrated the original assumption inventory to a provenance-gated staging CSV.

## 2.0.0rc2

- Added six B.C. Budget forecast vintages covering 2021 through 2026, including official population-growth assumptions.
- Added six BC Hydro service-plan vintages and five Annual Service Plan Reports for forecast-versus-actual analysis.
- Added FortisBC FEI and FBC annual MD&A discovery and 2021-2025 historical extraction.
- Added annual utility sales, supply costs, customer counts, forecast rate base, approved ROE, deemed equity and scoped pension discount assumptions.
- Added non-temporal B.C. social discount-rate guidance with decision-context metadata.
- Added document-level history coverage JSON and CSV outputs to the weekly pipeline.
- Added Poppler installation for layout-preserving historical PDF extraction.
- Added multiple publication-generation fixtures, structural-drift failures and adapter-level record validation tests.
- Preserved staged fail-closed ICBC, BCER, BC Hydro Quick Facts and direct BCUC solutions.
- Excluded major-project tracking, carbon price and the duplicate heat-pump adoption alias.
