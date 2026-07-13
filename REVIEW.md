# Review and pressure-test findings

Review date: 2026-07-13

## Outcome

The architecture is sound for a starter release: immutable raw artifacts,
versioned observations, explicit source/variable configuration, a fail-closed
release gate, offline fixtures, and a static public browser are all appropriate
choices for a Raspberry Pi collector and GitHub Pages publisher.

Version 0.1.1 fixes the release-blocking issues found during live integration
testing and adds independent checks around the most consequential public-data
boundary.

## Fixed in 0.1.1

1. **Statistics Canada schema drift (release blocker).** Current metadata uses
   `Total - Gender` and `Division composite`; the original selectors matched
   neither. Both current labels are now accepted without weakening the other
   anchored selectors.
2. **World Bank stale acquisition route (release blocker).** The original URL
   returned a workbook ending in August 2016. The source now points to the
   current official workbook, and the parser accepts both the legacy `Date`
   header and the current blank period-column header.
3. **Licence-gate defence in depth (high).** Deployment validation now rejects
   any record from a source with `publish_enabled: false`, even if a malformed
   or hand-edited artifact bypasses the normal exporter. Excluded record kinds
   receive the same independent check.
4. **Unsafe data-driven links (high).** The browser now permits only HTTP and
   HTTPS source links. Unsupported or malformed URLs render as text rather than
   clickable links.

## Verification performed

- Package SHA-256 matched the supplied checksum.
- 30 automated tests pass.
- Ruff lint and formatting checks pass.
- Configuration and checked-in public artifacts validate.
- JavaScript syntax validation passes.
- Live diagnostic collection passes for Bank of Canada (13,240 records), World
  Bank (636 records), and Statistics Canada (2,284 records), with zero rejected
  records in each run.

## Recommended next improvements

1. **Add scheduled live canaries.** Run one small selector per no-key source in
   CI on a schedule and alert without publishing. Fixture tests cannot detect
   publisher label, URL, or workbook-layout drift.
2. **Make the World Bank attachment discoverable.** The corrected official URL
   is tied to the current World Bank document page. Add a narrowly scoped
   resolver for the official Pink Sheet page, with host and filename allowlists,
   so a future annual page change does not require a code release.
3. **Benchmark SQLite writes on the target Pi.** Collection currently upserts
   records one transaction at a time. If the controlled Pi run is slow, add a
   transactional batch-upsert API while preserving per-record version logic.
4. **Add browser CI.** Exercise initial load, filters, empty states, malicious
   URL fixtures, keyboard navigation, and mobile layout with an accessibility
   scan. The current review could not complete screenshot-level in-app browser
   QA because the local browser-control runtime was unavailable.
5. **Exercise EIA live before production.** Use the operator's real key only in
   the Pi environment, confirm all three configured series, and ensure logs and
   archived request metadata remain redacted.
6. **Add operational telemetry.** Record elapsed time and artifact byte count per
   source, and expose the latest successful run separately from the latest
   attempt. This makes slowdowns and transient failures easier to diagnose.

## Deliberately unchanged

- Selective source runs remain diagnostic and cannot refresh public exports.
- Failed or partial complete runs continue to preserve the last public release.
- The CMHC source remains collected internally but excluded from publication
  until its redistribution terms are reviewed.
- Regulatory extraction candidates remain in the human review queue and are not
  automatically promoted into the public registry.
