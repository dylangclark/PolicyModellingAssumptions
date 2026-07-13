# Data contract

## Public record classes

`record_kind` uses a controlled value such as:

- `observation`
- `forecast`
- `policy_target`
- `scenario`
- `sensitivity`
- `model_parameter`
- `cost_estimate`

Qualitative statements should be retained as filing evidence but should not be forced into the numeric records table.

## Time fields

- `publication_date`: date the source released or filed the value.
- `vintage_date`: date/version of the forecast or dataset represented by the record.
- `reference_period_start` and `reference_period_end`: period measured by an observation.
- `target_period_start` and `target_period_end`: future period addressed by a forecast, target or parameter.
- `period_basis`: daily, monthly, quarterly, annual, fiscal year or other explicit basis.

Retrieval date is document metadata, not a substitute for publication or target period.

## Value fields

Use `value` for a point. Use `range_low` and `range_high` for a stated range. Do not store `450-500` or `Included` in a numeric column.

Every record retains both `unit_original` and `unit_canonical`. Currency-denominated values must also specify currency, price base year and real/nominal basis when those dimensions are relevant.

## Provenance

API and workbook observations retain:

- source ID and source-series ID;
- source URL;
- content-addressed artifact SHA-256;
- retrieval timestamp;
- parser/extraction method; and
- source-specific metadata such as vector, coordinate or workbook column.

Filing-derived assumptions additionally require:

- exact document identity and version;
- page number;
- table or section when available;
- evidence excerpt;
- extractor recipe and version; and
- reviewer and approval decision.

## Versioning

A natural key identifies the conceptual source record: variable, source series, geography/entity, period, record kind and scenario. The payload hash identifies its current content.

- Same natural key and same payload: update `last_seen_at`.
- Same natural key and different payload: close the old record and insert a revision.
- Different publication vintage or target period: retain a distinct record.

No current forecast or observation is overwritten in place without a recoverable historical row.

## Publication status

- `validated`: passed deterministic structured-source checks.
- `approved`: filing candidate approved by a reviewer.
- `needs_review`: acquired but excluded from public export.
- `rejected`: invalid or rejected evidence; excluded from public export.

The current site exports only `validated` and `approved` rows.
