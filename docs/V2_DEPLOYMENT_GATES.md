# Version 2 deployment and promotion gates

## Local installation gate

```bash
python -m pip install -e '.[dev,regulatory]'
python -m pytest -q
python -m bc_assumptions --root . validate-config
python scripts/validate_v2_release.py --root .
git diff --check
```

Expected package QA result:

- 65 tests pass;
- 117 variables;
- 21 sources;
- 14 enabled sources;
- six Budget documents, eleven BC Hydro documents and ten FortisBC annual documents in the historical manifests.

## Full official-PDF regression gate

Place the reviewed official PDFs in one directory using these filenames:

```text
bc_budget_2021.pdf ... bc_budget_2026.pdf
bchydro_service_plan_2021_22.pdf ... bchydro_service_plan_2026_27.pdf
bchydro_annual_2020_21.pdf ... bchydro_annual_2024_25.pdf
```

Then run:

```bash
python scripts/validate_v2_release.py \
  --root . \
  --live-doc-dir /path/to/historical-pdfs \
  --json-output history-validation.json
```

Expected official-document totals:

- Budget: 326 records;
- BC Hydro plans: 352 records;
- BC Hydro actual reports: 10 records.

Any missing document or structural-parser failure blocks the regression test.

## Pi selective-run gate

Install Poppler and current package dependencies:

```bash
sudo apt-get update
sudo apt-get install -y poppler-utils
sudo -u bcassumptions .venv/bin/pip install -e '.[dev,regulatory]'
```

Run the historical collectors separately:

```bash
.venv/bin/bc-assumptions --root . run --source bc_budget_economic_forecasts --full-refresh --no-export
.venv/bin/bc-assumptions --root . run --source bc_hydro_planning_assumptions --full-refresh --no-export
.venv/bin/bc-assumptions --root . run --source fortisbc_quarterly_financials --full-refresh --no-export
.venv/bin/bc-assumptions --root . run --source bc_moti_benefit_cost_parameters --full-refresh --no-export
.venv/bin/bc-assumptions --root . export
.venv/bin/python scripts/build_history_coverage.py --root .
.venv/bin/bc-assumptions --root . validate-public
```

Review:

- zero rejected records;
- expected document counts;
- variable and unit coverage;
- publication and target periods;
- evidence type and decision context;
- forecast vintages;
- `site/data/history-coverage.json`;
- `data/export/history-coverage.csv`;
- `data/export/forecast_performance.csv`.

Do not start the full weekly service until the selective runs pass.

## Source-promotion gate

A staged source may be enabled only after all applicable checks pass:

1. Stable official download route is identified.
2. Licence and redistribution treatment are recorded.
3. Raw artifacts are content-addressed and hashed.
4. Schema or document guard patterns pass.
5. Units and geography or service territory are explicit.
6. Mixed time bases and aggregation levels fail closed.
7. Plausibility limits and minimum coverage are configured.
8. Regression fixtures cover multiple publication generations.
9. A selective live Pi run completes with zero rejected records.
10. The source remains optional until at least one scheduled cycle succeeds.

## ICBC gate

Do not scrape undocumented Tableau internals. Configure a verified direct CSV or ZIP export. The adapter requires a recognized geography and powertrain, keeps BEVs and PHEVs separate, rejects exact duplicate rows and derives growth only from consecutive annual values.

## BCER gate

Verify the archive member, schema, production concept and units before activation. CER marketable production and BCER gross reported production remain separate variables.

## FortisBC gate

The annual source is enabled but optional. The first Pi run must discover exactly ten annual MD&A documents for 2021-2025 and extract both utilities in every year. A missing year or utility fails the collector. Quarterly filings remain outside this release because annual values provide a cleaner historical panel.

## BCUC gate

Applicant forecasts, updated applications, intervener evidence and BCUC-approved values are distinct evidence states. Direct proceeding recipes remain disabled until publication discovery and document-specific extraction are reviewed. Finance charges must not be reverse-engineered into approved cost of debt or WACC.
