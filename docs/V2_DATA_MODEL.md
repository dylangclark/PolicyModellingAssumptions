# Version 2 evidence and assumption model

Version 2 separates three questions that were previously easy to conflate:

1. **What is the value?** The variable ID and canonical unit define the measure.
2. **What kind of evidence is it?** `evidence_type` identifies whether it is observed data, a government forecast, a utility forecast, an approved regulatory assumption, private-sector guidance, a scenario, target, derived value or cost estimate.
3. **How does time apply?** Observations use reference periods; forecasts use publication/vintage and target periods; non-temporal parameters use publication, effective and decision context without pretending to be a time series.

## Record kinds

- `observation`: measured or administratively reported outcome.
- `forecast`: central expectation for a future target period.
- `scenario`: conditional model result rather than a prediction.
- `policy_target`: intended outcome.
- `model_parameter`: decision-specific parameter such as a social discount rate.
- `cost_estimate`: estimated cost with a named basis.
- `sensitivity`: alternative parameter or outcome used for testing.
- `qualitative_assumption`: structured non-numeric evidence where supported.

## Evidence types

The controlled v2 evidence types are:

`observed`, `government_forecast`, `utility_forecast`, `approved_regulatory_assumption`, `government_policy_assumption`, `private_sector_guidance`, `market_consensus`, `scenario`, `target`, `derived`, and `cost_estimate`.

These classifications are not quality rankings. An approved regulatory assumption is authoritative for a rate decision, while an observed Statistics Canada series is authoritative for a measured economic outcome. They answer different questions.

## Forecast vintages

Forecasts preserve:

- publication and vintage date;
- target period;
- scenario and entity;
- service territory or geography;
- assumption owner and decision context;
- source document, page, table and extraction evidence.

A revised forecast is retained as a new vintage. It does not overwrite the prior forecast.

## Non-temporal discount rates

Discount rates are not stored as ordinary annual observations. Version 2 separates:

- `financial.social_discount_rate_pct`;
- `financial.utility_regulatory_discount_rate_pct`;
- `financial.pension_discount_rate_pct`;
- the legacy generic `financial.discount_rate_pct`, retained only for compatibility.

A non-temporal parameter must have `record_kind=model_parameter`, no target period, and metadata for `time_basis=non_temporal_parameter`, `decision_context`, and `evidence_type`. Publication and effective dates establish provenance; they do not turn the parameter into a time series.

Allowed ROE, deemed equity, WACC, cost of debt and pension discount rates are distinct concepts and must not be substituted for one another.

## Population and utility growth

Version 2 records three separate forms of evidence:

- B.C. government population-growth forecasts from the Budget and Fiscal Plan;
- BC Stats population estimates and projections, staged behind live schema verification;
- utility customer-growth forecasts and the stated population, housing and economic drivers used in utility planning.

Utility customer growth is not relabelled as population growth. Proprietary third-party population forecasts referenced by utilities are not reproduced unless the underlying values are publicly disclosed and redistributable.

## Forecast performance

`forecast_performance.json` and `.csv` match forecasts to later observations only when variable, unit, geography, entity and target/reference period agree exactly. The output includes signed error, absolute error, absolute percentage error, lead time and the selected actual source. Broad or approximate matching is intentionally excluded.
