# B.C. Assumptions Registry

A versioned evidence registry for economic and energy-policy assumptions used in British Columbia. The project is designed to run weekly on a Raspberry Pi, commit normalized outputs to GitHub, and publish a static browser through GitHub Pages.

This starter release implements the **authoritative structured-source layer** and establishes the review boundary for the later regulatory-filing layer.

## What is implemented

### Authoritative collectors

| Source | Implemented series | Access pattern |
|---|---|---|
| Bank of Canada Valet API | Overnight target (`V39079`), 10-year Government of Canada benchmark yield (`BD.CDN.10YR.DQ.YLD`), CAD per USD (`FXUSDCAD`) | Compact JSON API |
| Statistics Canada WDS | BC population, employment, labour force, CPI/inflation, Vancouver non-residential building construction prices, BC housing starts | Metadata-driven vector resolution and JSON API |
| U.S. EIA Open Data | Henry Hub, WTI and Brent monthly observations | API v2; requires a free API key |
| World Bank Pink Sheet | Copper and Japan LNG import-price proxy | Official monthly XLSX |

The Japan LNG series is deliberately named as a proxy. It is **not** Platts JKM.

### Core registry behavior

- SQLite is the internal system of record.
- Every source response or workbook is archived by SHA-256 under `data/raw/`.
- Raw files and the SQLite database stay off Git by default.
- Records have a stable natural key and payload hash.
- Unchanged observations update `last_seen_at` rather than creating weekly duplicates.
- Revisions close the prior record and insert a new current version.
- CSV and JSON exports are generated for Git and GitHub Pages.
- A failed, incomplete, stale or review-required source prevents the export refresh, so the last committed public dataset remains unchanged.
- A successful HTTP response is insufficient: every configured source-series/variable output must be present and pass its freshness threshold.
- Only records with `validated` or `approved` status enter public exports.
- The supplied legacy assumptions table is migrated to a staging CSV, not silently promoted.

### Regulatory filing boundary

The repository includes a deterministic PDF recipe engine and review queue. A recipe can locate a value by page range and regular expression, retain the evidence excerpt, and generate a candidate. Candidates remain outside the public registry until reviewed.

The initial filing engine is intentionally narrow. Source-specific BC Hydro, BCUC and FortisBC recipes should be added only after their documents, naming conventions and evidence requirements have been profiled.

## Repository layout

```text
config/                         variable, source, validation and roadmap registries
data/raw/                       content-addressed source artifacts; ignored by Git
data/cache/                     resolved StatCan vector cache; ignored by Git
data/export/                    generated public CSV and JSON
site/                           static GitHub Pages application
src/bc_assumptions/adapters/    authoritative source adapters
src/bc_assumptions/regulatory/  PDF recipe and review-queue engine
state/                          SQLite and review queue; ignored by Git
systemd/                        Raspberry Pi weekly service and timer
tests/                          offline parser, versioning and transformation tests
```

## Local quick start

Python 3.11 or newer is required.

```bash
cd bc-assumptions-registry
python3 -m venv .venv
. .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -e '.[dev,regulatory]'
cp .env.example .env
bc-assumptions init-db
pytest
```

Set a monitored contact address in `.env`. Add an EIA key; EIA is a required source in the complete release gate:

```text
BC_ASSUMPTIONS_CONTACT=your-address@example.org
EIA_API_KEY=your-key
```

Run one source first as a diagnostic. Selective runs update SQLite but never refresh the public release:

```bash
bc-assumptions run --source bank_of_canada_valet --no-export
```

Then run the complete enabled registry:

```bash
bc-assumptions run --all
bc-assumptions status
bc-assumptions validate-public
```

`run --all` refreshes `data/export/` and `site/data/` only after the complete release gate passes. `run --all --no-export` evaluates the same gate without changing Git-facing files. The standalone `export` command also enforces the gate; `export --force` is reserved for creating an empty scaffold or controlled recovery and must not be used by weekly automation.

To inspect the website locally:

```bash
python -m http.server 8000 --directory site
```

Open `http://localhost:8000` in a browser.

## Release gate

A release is eligible only when all enabled sources marked `required: true` satisfy both controls:

1. the latest source run completed with `success` within `collection_stale_after_days`; and
2. every configured source-series/variable output exists in SQLite and its newest reference period is no older than its `stale_after_days` threshold.

This catches silent upstream changes where an endpoint responds successfully but omits one series. `bc-assumptions status` shows the current blockers and series coverage. GitHub Actions validates the generated public files again before Pages deployment, including record counts, identifier integrity and a credential scan.

## Statistics Canada first-run verification

Statistics Canada vectors are resolved from current cube metadata. The YAML source registry uses anchored regular expressions for dimension and member names. This avoids brittle hard-coded vector IDs while still failing loudly if a table changes.

Inspect a table before changing its selectors:

```bash
bc-assumptions inspect-statcan 14100287
bc-assumptions inspect-statcan 18100289
```

The current configuration uses:

- `17-10-0009-01` for quarterly population;
- `14-10-0287-01` for monthly seasonally adjusted labour-force characteristics;
- `18-10-0004-01` for all-items CPI;
- `18-10-0289-01` for building construction prices; and
- `34-10-0158-01` for monthly CMHC housing starts at seasonally adjusted annual rates.

Table `18-10-0289-01` is recorded as the successor to archived table `18-10-0276-01`. Source-series replacements belong in configuration and lineage metadata, not in undocumented parser changes.

## Migrating the original seed

The seed is useful as a discovery inventory, but its generic source labels and mixed period/value formats are not sufficient for public evidence records. Convert it to a staging file with:

```bash
bc-assumptions import-legacy '/path/to/Pasted text(44).txt'
```

The result is `data/staging/legacy_seed.csv`. Each row is marked `needs_source_provenance` until an exact document, vintage, page and table are supplied.

## Regulatory recipe example

Install the optional PDF dependency, copy the example recipe, and configure an exact source document:

```bash
cp config/regulatory_recipes/example.yml config/regulatory_recipes/my_filing.yml
bc-assumptions regulatory-extract \
  --recipe config/regulatory_recipes/my_filing.yml \
  --document /path/to/filing.pdf
bc-assumptions regulatory-list --status pending
bc-assumptions regulatory-review cand_... \
  --decision approved \
  --reviewer initials \
  --note 'Confirmed against the filed table and footnote.'
```

Approval records the review decision. Promotion into the public registry should be enabled only after the source and variable have formal entries in `sources.yml` and `variables.yml`, including unit and period definitions.

## Raspberry Pi installation

The included service assumes:

- a 64-bit Raspberry Pi OS;
- repository path `/opt/bc-assumptions-registry`;
- service account `bcassumptions`; and
- environment file `/etc/bc-assumptions.env`.

Review `scripts/install_pi.sh`, then run it as root from the checked-out repository:

```bash
sudo scripts/install_pi.sh
sudo systemctl enable --now bc-assumptions.timer
systemctl list-timers bc-assumptions.timer
```

The timer runs weekly with a randomized delay and `Persistent=true`, so a missed run is started after the Pi next boots. `scripts/run_weekly.sh` commits only changed generated outputs.

Configure Git authentication outside the repository. A repository-scoped deploy key or fine-grained credential should have access only to this repository. Set `BC_ASSUMPTIONS_GIT_NAME` and `BC_ASSUMPTIONS_GIT_EMAIL` in the service environment, then follow `docs/OPERATIONS.md` for the controlled first run and recovery procedures.

## GitHub Pages

Initialize and push the project from a clean checkout:

```bash
git init
git add .
git commit -m 'chore: initialize B.C. assumptions registry'
git branch -M main
git remote add origin git@github.com:YOUR_ORG/bc-assumptions-registry.git
git push -u origin main
```

Then:

1. Create a GitHub repository and push this project.
2. In repository settings, select **GitHub Actions** as the Pages source.
3. Push generated changes under `site/`.
4. `.github/workflows/pages.yml` uploads and deploys the static site.

No database or server-side runtime is required by the public website.

## Data contract

Every public record is expected to answer:

- What variable is this?
- Is it an observation, forecast, target, scenario or model parameter?
- What geography and entity does it describe?
- What reference or target period does it apply to?
- What are the original and canonical units?
- What source series or filed document produced it?
- What publication vintage and source artifact support it?
- Was it deterministically validated or manually approved?
- Has the source revised it since first collection?

See `docs/DATA_CONTRACT.md` for the field-level contract and `docs/AUTHORITATIVE_SOURCES.md` for the implemented source register and publication gates.

## Source onboarding rule

A source is not enabled until it has:

1. an authoritative publisher and stable acquisition route;
2. a licence and redistribution note;
3. exact variable definitions and canonical units;
4. fixture-based parser tests;
5. range and schema validation;
6. a revision/versioning strategy; and
7. a failure mode that cannot partially publish misleading data.

## Immediate build sequence

1. Run and verify the five enabled authoritative source registrations on the Raspberry Pi.
2. Resolve any changed StatCan member labels with `inspect-statcan` and commit the corrected configuration.
3. Enable weekly Git commits and Pages deployment.
4. Add official BC carbon-price schedules, CER electricity-trade data, ICBC vehicle stock and River Forecast Centre indicators.
5. Profile one BC Hydro proceeding and one BCUC/FortisBC proceeding.
6. Write source-specific filing recipes and a promotion workflow with reviewer identity and evidence checks.
7. Add forecast vintages, source-family lineage and backtesting before publishing cross-source planning ranges.

## Integration verification

The 0.1.1 review build was tested against the live Bank of Canada, Statistics
Canada and World Bank endpoints on 2026-07-13. Those controlled runs completed
successfully with no rejected records. EIA still requires an operator-provided
API key and was not exercised live during this review.

## Testing limitation of this packaged starter

The automated suite remains offline and uses representative API and workbook
fixtures. Upstream publishers can still change labels, schemas, URLs or workbook
layouts after release, so the first controlled Pi run remains an integration
test. The collector fails closed when a configured output is missing or stale.
