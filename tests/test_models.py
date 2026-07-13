from dataclasses import replace

from bc_assumptions.models import Artifact


def test_document_identity_includes_request_context():
    first = Artifact(
        source_id="source",
        source_url="https://example.test/data?series=a",
        local_path="source/aa/file.json",
        content_type="application/json",
        retrieved_at="2026-07-13T00:00:00Z",
        sha256="a" * 64,
        size_bytes=10,
        request_metadata={"params": [["series", "a"]]},
    )
    second = replace(
        first,
        source_url="https://example.test/data?series=b",
        request_metadata={"params": [["series", "b"]]},
    )
    assert first.document_id != second.document_id
