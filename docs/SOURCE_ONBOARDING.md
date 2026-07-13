# Authoritative source onboarding

## 1. Define the variable first

Create a stable variable ID, precise definition, canonical unit, geography and plausible validation range in `config/variables.yml`. Split ambiguous variables before collecting them. For example, interest rates should distinguish the overnight target, prime rate and bond maturities.

## 2. Register the source

Add publisher, authority tier, adapter, source URL, cadence, licence and redistribution notes to `config/sources.yml`. API keys belong in environment variables and must never be written to archived request URLs or Git output.

## 3. Preserve the original series identity

Use the source's own series/table identifier. Derived outputs such as year-over-year growth should retain the source series in metadata and mark the transform.

## 4. Make changes explicit

When an official table replaces another table, record the predecessor/successor relationship in YAML. Do not silently point an existing identifier at a new statistical concept.

## 5. Add fixture tests

Tests should cover:

- source response shape;
- null, suppressed and revised values;
- period conversion;
- scalar/unit conversion;
- source-series replacement behavior; and
- deterministic versioning.

Live smoke tests may be run on the Pi, but CI should not depend on external services.

## 6. Validate before publication

Range checks should normally flag rather than discard a surprising authoritative value. Structural failures, unknown units or missing periods should prevent insertion. A failed source should not stop unrelated collectors from recording their own results, but any required-source failure, missing output or stale series must block the public release. Configure both collection-run and reference-period freshness limits.
