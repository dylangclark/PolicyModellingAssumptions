from bc_assumptions.regulatory.recipe import extract_candidates_from_pages
from bc_assumptions.regulatory.review import ReviewQueue


def test_recipe_extracts_evidence_and_requires_review(tmp_path):
    recipe = {
        "recipe_id": "cost-of-debt-test",
        "source_id": "utility_filing",
        "defaults": {
            "record_kind": "model_parameter",
            "geography_id": "CA-BC",
            "reference_period_start": "2026-01-01",
            "reference_period_end": "2026-12-31",
        },
        "extractors": [
            {
                "id": "cost_of_debt",
                "variable_id": "financial.cost_of_debt_pct",
                "page_range": [1, 2],
                "pattern": r"cost of debt[^0-9]{0,30}(?P<value>[0-9]+(?:\.[0-9]+)?)\s*%",
                "unit_original": "percent",
                "unit_canonical": "percent",
            }
        ],
    }
    candidates = extract_candidates_from_pages(
        recipe,
        ["The proposed cost of debt is 4.75% for 2026.", "No value here."],
        document_path="filing.pdf",
        document_sha256="c" * 64,
    )
    assert len(candidates) == 1
    assert candidates[0].value == 4.75
    assert candidates[0].page == 1
    assert candidates[0].status == "pending"
    assert "cost of debt" in candidates[0].evidence_text.lower()

    queue = ReviewQueue(tmp_path / "queue.json")
    assert queue.add(candidates) == (1, 0)
    approved = queue.decide(
        candidates[0].candidate_id,
        decision="approved",
        reviewer="AB",
        note="Checked against the page.",
    )
    assert approved.status == "approved"
    assert approved.reviewer == "AB"
