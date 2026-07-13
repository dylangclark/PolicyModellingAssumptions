# Raspberry Pi operations

## Initial deployment

```bash
sudo scripts/install_pi.sh
sudoedit /etc/bc-assumptions.env
sudo -u bcassumptions -H git -C /opt/bc-assumptions-registry remote -v
sudo systemctl enable --now bc-assumptions.timer
systemctl list-timers bc-assumptions.timer
```

The installer creates a dedicated Python virtual environment, initializes SQLite, writes a systemd service for the selected root/user, and installs the weekly timer. Put `EIA_API_KEY`, the monitored contact address and Git settings in `/etc/bc-assumptions.env`; do not add them to the repository.

## First controlled run

Run sources individually before enabling publication. Selective runs are diagnostic and cannot update `data/export` or `site/data`:

```bash
sudo -u bcassumptions -H /opt/bc-assumptions-registry/.venv/bin/bc-assumptions \
  --root /opt/bc-assumptions-registry run --source bank_of_canada_valet --no-export

sudo -u bcassumptions -H /opt/bc-assumptions-registry/.venv/bin/bc-assumptions \
  --root /opt/bc-assumptions-registry inspect-statcan 14100287
```

Then run the complete set without changing Git-facing files:

```bash
sudo -u bcassumptions -H /opt/bc-assumptions-registry/.venv/bin/bc-assumptions \
  --root /opt/bc-assumptions-registry run --all --no-export
```

The command returns zero only when every required source has a recent successful run and every configured series/output passes its reference-period freshness limit. Review the gate directly with:

```bash
sudo -u bcassumptions -H /opt/bc-assumptions-registry/.venv/bin/bc-assumptions \
  --root /opt/bc-assumptions-registry status
```

After the gate is ready, build and validate the release:

```bash
sudo -u bcassumptions -H /opt/bc-assumptions-registry/.venv/bin/bc-assumptions \
  --root /opt/bc-assumptions-registry export
sudo -u bcassumptions -H /opt/bc-assumptions-registry/.venv/bin/bc-assumptions \
  --root /opt/bc-assumptions-registry validate-public
```

`export --force` bypasses source completeness checks. It exists only for creating an empty repository scaffold or controlled recovery and must not appear in the timer or ordinary operating procedure.

See `FIRST_LIVE_RUN.md` for the source-by-source acceptance checklist.

## Weekly transaction

`scripts/run_weekly.sh` performs one locked transaction:

1. acquire a non-blocking filesystem lock;
2. fast-forward the local checkout from the configured branch;
3. collect all enabled sources with no export;
4. enforce run, coverage and freshness gates;
5. build and validate public files;
6. stage only `data/export` and `site/data`; and
7. commit and push only when generated output changed.

A source failure exits before any Git-facing output is regenerated. The previously committed Pages dataset remains the public version.

## Logs and diagnosis

```bash
journalctl -u bc-assumptions.service --since '14 days ago'
systemctl status bc-assumptions.timer
sudo -u bcassumptions -H /opt/bc-assumptions-registry/.venv/bin/bc-assumptions \
  --root /opt/bc-assumptions-registry status
```

Set `BC_ASSUMPTIONS_DEBUG=1` temporarily to retain tracebacks in run warnings. Do not leave it enabled in normal public operation, because detailed errors may expose paths or unexpected source content even though configured query secrets are redacted.

## Git authentication

Use a repository-scoped deploy key or similarly narrow credential owned by the service account. Configure the remote and verify a dry push before enabling the timer. The weekly script supplies a bot author name and address from environment variables and stages only generated public data.

## Recovery

Raw artifacts are content-addressed under `data/raw`; SQLite is under `state/registry.sqlite`. Back up both outside Git. Public CSV/JSON and the website can be rebuilt from SQLite only when the release gate is healthy.

Before restoring SQLite, stop the timer and service. Restore the database and raw archive together so document paths and hashes remain consistent, then run `status`, `export`, `validate-public` and the test suite before re-enabling the timer.
