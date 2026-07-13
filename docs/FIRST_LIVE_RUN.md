# First live-run acceptance plan

The packaged tests use fixtures. The Raspberry Pi bootstrap is the first test against current production interfaces and must be performed source by source before enabling the weekly timer.

## Preconditions

```bash
cd /opt/bc-assumptions-registry
. .venv/bin/activate
bc-assumptions --root . validate-config
bc-assumptions --root . validate-public
```

Confirm that `/etc/bc-assumptions.env` contains a monitored contact address and a valid EIA key. Confirm that `data/raw`, `data/cache` and `state` are ignored by Git.

## 1. Bank of Canada

```bash
bc-assumptions --root . run --source bank_of_canada_valet --full-refresh
bc-assumptions --root . status
```

Verify all three configured series appear: `V39079`, `BD.CDN.10YR.DQ.YLD` and `FXUSDCAD`. Compare the newest value and two historical dates with the official Valet output. Run the source again and confirm the recent overlapping records are reported as unchanged rather than duplicated.

## 2. Statistics Canada

Inspect current cube metadata first:

```bash
bc-assumptions --root . inspect-statcan 17100009 > /tmp/statcan-population.json
bc-assumptions --root . inspect-statcan 14100287 > /tmp/statcan-labour.json
bc-assumptions --root . inspect-statcan 18100004 > /tmp/statcan-cpi.json
bc-assumptions --root . inspect-statcan 18100289 > /tmp/statcan-construction.json
bc-assumptions --root . inspect-statcan 34100158 > /tmp/statcan-housing.json
```

Confirm each configured selector resolves exactly one member. Then run `statistics_canada_wds` and `cmhc_via_statistics_canada` separately. Check that population and labour levels have the official scalar applied, year-over-year transformations agree with a manual calculation, and the latest periods are within their configured freshness thresholds.

## 3. EIA

```bash
bc-assumptions --root . run --source eia_open_data --full-refresh
```

Confirm Henry Hub, WTI and Brent are present. Search the raw archive, SQLite exports and Git working tree for the actual API key; no occurrence is acceptable. The archived URL and request metadata should show `REDACTED`.

## 4. World Bank Pink Sheet

```bash
bc-assumptions --root . run --source world_bank_pink_sheet --full-refresh
```

Confirm the workbook sheet and column headers resolved once each. Compare recent copper and Japan LNG proxy values with the official workbook. Confirm the LNG record retains `proxy_series` and `not_jkm` flags.

## 5. Complete release dry run

```bash
bc-assumptions --root . run --all --no-export
bc-assumptions --root . status
```

The command must return zero and `release_ready` must be true. A required source may not be waived merely because another source covers a similar concept.

## 6. Build and inspect

```bash
bc-assumptions --root . export
bc-assumptions --root . validate-public
python -m http.server 8000 --directory site
```

Inspect counts, units, newest dates, source links and the licence-gated absence of CMHC rows from the public data. Confirm that `data/export` and `site/data` are the only intended tracked changes.

## 7. Failure drill

Temporarily remove `EIA_API_KEY` from the service environment and run `run --all --no-export`. The command must fail, report EIA as a blocker and leave the checksums of `data/export` and `site/data` unchanged. Restore the key and repeat the healthy dry run before enabling the timer.
