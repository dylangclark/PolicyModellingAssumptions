# Regulatory filing engine

Regulatory filings are not treated as ordinary web-scraping targets. Values can depend on scenario labels, table footnotes, fiscal-year conventions, real/nominal dollars and answers to information requests. The engine therefore separates acquisition, extraction, review and promotion.

## Stages

1. **Acquire** the exact filed PDF and calculate SHA-256.
2. **Identify** document metadata: proceeding, filing number, applicant, filing date and document version.
3. **Extract** page text or tables using a source-specific recipe.
4. **Generate candidates** containing normalized fields plus page evidence.
5. **Review** the candidate against the rendered page and footnotes.
6. **Approve or reject** with reviewer identity and note.
7. **Promote** only after source and variable definitions exist and all required fields validate.

## Recipe design

A recipe is not a general-purpose model. It is a documented parser for one document family or stable table layout. It should specify:

- anchor text or page range;
- exact regular expression or table selector;
- named value/range capture groups;
- unit, geography and time basis;
- expected scenario/table context; and
- confidence score used only for review ordering.

An LLM may propose a recipe or help classify a candidate, but deterministic extraction and human approval remain the publication controls.

## Evidence requirements

At minimum retain:

- PDF SHA-256;
- source URL and retrieval date;
- page number;
- evidence excerpt;
- extractor ID and recipe version;
- value as printed and normalized value;
- unit interpretation;
- relevant footnote; and
- reviewer decision.

## First source-specific pilots

The first two pilots should be deliberately limited:

1. A BC Hydro planning filing with one stable forecast table and a small set of load/reliability variables.
2. A BCUC or FortisBC cost-of-capital table containing cost of debt, cost of equity and capital structure.

Only after those are reliable should the engine expand to project-event extraction for LNG, mining and data centres.
