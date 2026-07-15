# Policy Modelling Assumptions Registry 2.0.0rc2

Version 2 expands the registry from a current-data collector into an evidence and forecast-vintage registry.

## Historical panel available on first full refresh

- B.C. Budget and Fiscal Plan editions from 2021 through 2026.
- BC Hydro service plans from 2021/22 through 2026/27.
- BC Hydro Annual Service Plan Reports from 2020/21 through 2024/25.
- FortisBC Energy Inc. and FortisBC Inc. annual MD&A documents from 2021 through 2025.
- B.C. transportation benefit-cost social discount-rate guidance.

The expected historical manifest contains 28 documents. Each downloaded artifact is hashed. Forecast records retain their publication vintage and target period; later documents do not overwrite earlier forecast vintages.

## Main variables

- Government macroeconomic and population-growth forecasts.
- Utility electricity sales, load growth, generation, imports, purchases and capital plans.
- Actual BC Hydro sales and capital expenditure.
- FortisBC gas and electricity sales, supply costs, actual and forecast capital expenditure, customers and rate base.
- Approved utility ROE and equity structure.
- Social and pension discount-rate parameters with explicit scope.
- Forecast-performance matches where variable, unit, geography, entity and period align.

## Scope limits

- Major-project inventories and realization modelling are excluded.
- ICBC, BCER, BC Hydro Quick Facts and direct BCUC proceeding collectors remain disabled until their live promotion gates pass.
- FortisBC annual history is enabled but optional until a selective Pi run validates all live documents.
- BC Hydro IRP-specific variables such as reserve margin, ELCC and capacity gaps remain staged regulatory recipes.
- Utility customer-growth forecasts are not represented as population-growth forecasts.
- Proprietary demographic inputs referenced by utilities are retained as provenance rather than republished as numeric data.

## Compatibility

The installer merges registries by ID, preserves unrelated source-gap files, creates timestamped backups, updates the Raspberry Pi dependency installer, and adds historical coverage generation to the weekly workflow. Public export schema version is `2.0.0-rc2`.
