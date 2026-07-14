# Source-gap audit patch — July 2026

This patch adds a maintained variable-to-source matrix and a GitHub Pages view for acquisition planning. It removes the carbon-price variable from the configured inventory at user direction.

The matrix distinguishes public data already present from variables that require a structured collector, licence review, regulatory-document extraction, or longitudinal project-event derivation.

## Immediate implementation sequence

1. BC Stats household estimates and projections.
2. ICBC electric-vehicle stock, with BEV and PHEV kept separate.
3. BC Energy Regulator monthly natural-gas production.
4. B.C.-specific electricity trade only where CER data explicitly support provincial attribution.
5. BC Hydro annual sales, peak, generation and forecast vintages.
6. BCUC/utility planning assumptions, including reserve margin, ELCC and financing assumptions.
7. Technology cost datasets with explicit scenario, technology, currency and dollar-year fields.
8. LNG, mining and data-centre project-event inventories before calculating realization rates.

## Scope controls

- Carbon price is excluded.
- The River Forecast Centre is not a priority collector. Snowpack is retained only as a lower-priority alternative source in the audit.
- B.C. Major Projects Inventory is not used as the primary project-event source.
- Current CER Canada-wide trade and western price series must not be relabelled as B.C.-specific data.
