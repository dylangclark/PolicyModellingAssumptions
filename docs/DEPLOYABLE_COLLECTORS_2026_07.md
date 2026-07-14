# Deployable collector tranche — July 2026

This tranche enables three non-blocking production collectors and publishes the existing CMHC/Statistics Canada housing-start series.

## Enabled collectors

### Canada Energy Regulator electricity trade

Adapter: `cer_electricity_trade`

Collects monthly:

- Canadian international electricity imports and exports (MWh)
- import and export values (CAD)
- Western Canada weighted import and export prices (CAD/MWh)

The CER workbook does not identify B.C. imports separately. Western price observations are labelled `CA-WEST`, not B.C.

### B.C. Budget forecasts

Adapter: `bc_budget_forecast`

The first configured vintage is Budget 2026. It extracts reviewed page-local values for:

- B.C. real GDP growth (2025–2027)
- Bank of Canada overnight-rate assumptions (2026–2027)
- Government of Canada 10-year bond-yield assumptions (2026–2027)
- CAD per USD exchange-rate assumptions (2026–2027)

Each value is stored as a forecast with publication date, target year, page evidence, and budget edition. Future budgets can be added by appending a document recipe to `config/sources.yml`.

### NRCan NEUD residential heating systems

Adapter: `nrcan_neud`

Collects annual B.C. residential heating-system estimates from NEUD Table 21:

- heat-pump stock
- heat-pump share
- electric heating-system stock

The source is annual and published with a lag. The collector is non-blocking so a delayed NRCan update cannot prevent the main weekly release.

## Deployment posture

All three new sources are:

```yaml
enabled: true
required: false
publish_enabled: true
```

This means the weekly service will run them and publish successful records, but a temporary source failure will not block the five established required sources. After several stable scheduled runs, individual sources can be promoted to `required: true` with explicit coverage requirements.

## First deployment commands

After merging and pushing from Windows, on the Raspberry Pi:

```bash
sudo -u bcassumptions git -C /opt/bc-assumptions-registry pull --ff-only origin main
sudo -u bcassumptions /opt/bc-assumptions-registry/.venv/bin/pip install -e /opt/bc-assumptions-registry
```

Run each new source independently and do not overlap runs:

```bash
sudo -u bcassumptions bash -c '
set -a
source /etc/bc-assumptions.env
set +a
cd /opt/bc-assumptions-registry
.venv/bin/bc-assumptions --root . run --source cer_electricity_trade --no-export
.venv/bin/bc-assumptions --root . run --source bc_budget_economic_forecasts --no-export
.venv/bin/bc-assumptions --root . run --source nrcan_energy_use_database --no-export
.venv/bin/bc-assumptions --root . status
'
```

Then publish:

```bash
sudo systemctl start bc-assumptions.service
sudo journalctl -u bc-assumptions.service -n 200 --no-pager
```

## Not included in this tranche

The B.C. Energy Regulator production report uses an Oracle APEX interactive-report workflow. It needs a source-specific export/session implementation before it can be called deployable. ICBC remains subject to licence review. BC Hydro, LNG, mining, and Zero Carbon Step Code sources remain document/review-engine work.
