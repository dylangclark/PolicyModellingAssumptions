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
