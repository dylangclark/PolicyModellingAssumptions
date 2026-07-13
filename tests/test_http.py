from bc_assumptions.http import _safe_request_error, redact_url


def test_redact_url_and_errors_never_include_api_key():
    raw = "https://api.example.test/data?api_key=secret-value&frequency=monthly"
    redacted = redact_url(raw, {"api_key"})
    assert "secret-value" not in redacted
    assert "REDACTED" in redacted
    message = _safe_request_error(RuntimeError("secret-value"), None, raw, {"api_key"})
    assert "secret-value" not in message
