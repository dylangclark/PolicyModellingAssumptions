from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256
import json
import mimetypes
import os
from pathlib import Path
import random
import time
from typing import Any
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

import requests

from .models import Artifact, utc_now


class AcquisitionError(RuntimeError):
    pass


@dataclass(slots=True)
class BytesResult:
    artifact: Artifact
    content: bytes


@dataclass(slots=True)
class JsonResult:
    artifact: Artifact
    data: Any


def redact_url(url: str, sensitive_parameters: set[str] | None = None) -> str:
    sensitive = {value.lower() for value in (sensitive_parameters or set())}
    parts = urlsplit(url)
    query = []
    for key, value in parse_qsl(parts.query, keep_blank_values=True):
        query.append((key, "REDACTED" if key.lower() in sensitive else value))
    return urlunsplit((parts.scheme, parts.netloc, parts.path, urlencode(query), parts.fragment))


def _safe_request_error(
    exc: Exception,
    response: requests.Response | None,
    requested_url: str,
    sensitive_parameters: set[str] | None,
) -> str:
    if response is not None:
        safe_url = redact_url(response.url, sensitive_parameters)
        return f"HTTP {response.status_code} from {safe_url}"
    safe_url = redact_url(requested_url, sensitive_parameters)
    return f"{type(exc).__name__} while requesting {safe_url}"


class HttpClient:
    def __init__(
        self,
        raw_dir: Path,
        contact: str | None = None,
        timeout_seconds: int = 90,
        max_attempts: int = 4,
        session: requests.Session | None = None,
    ):
        self.raw_dir = raw_dir
        self.raw_dir.mkdir(parents=True, exist_ok=True)
        self.timeout_seconds = timeout_seconds
        self.max_attempts = max_attempts
        self.session = session or requests.Session()
        contact_value = contact or os.environ.get(
            "BC_ASSUMPTIONS_CONTACT", "registry-operator@example.org"
        )
        self.session.headers.update(
            {
                "User-Agent": f"bc-assumptions-registry/2.0.0rc2 ({contact_value})",
                "Accept-Encoding": "gzip, deflate",
            }
        )

    def request_bytes(
        self,
        source_id: str,
        method: str,
        url: str,
        *,
        label: str,
        params: dict[str, Any] | list[tuple[str, Any]] | None = None,
        json_body: Any | None = None,
        headers: dict[str, str] | None = None,
        sensitive_parameters: set[str] | None = None,
        timeout_seconds: int | None = None,
    ) -> BytesResult:
        response: requests.Response | None = None
        for attempt in range(1, self.max_attempts + 1):
            try:
                response = self.session.request(
                    method,
                    url,
                    params=params,
                    json=json_body,
                    headers=headers,
                    timeout=timeout_seconds or self.timeout_seconds,
                )
                if response.status_code in {408, 409, 425, 429, 500, 502, 503, 504}:
                    raise AcquisitionError(
                        f"Temporary HTTP {response.status_code} from "
                        f"{redact_url(response.url, sensitive_parameters)}"
                    )
                response.raise_for_status()
                break
            except (requests.RequestException, AcquisitionError) as exc:
                safe_error = _safe_request_error(exc, response, url, sensitive_parameters)
                if attempt >= self.max_attempts:
                    raise AcquisitionError(safe_error) from exc
                retry_after = response.headers.get("Retry-After") if response is not None else None
                delay = (
                    float(retry_after)
                    if retry_after and retry_after.isdigit()
                    else 2 ** (attempt - 1)
                )
                time.sleep(delay + random.random() * 0.25)
        if response is None:
            raise AcquisitionError("No HTTP response")

        content = response.content
        digest = sha256(content).hexdigest()
        content_type = response.headers.get("Content-Type", "").split(";", 1)[0] or None
        extension = self._extension(content_type, response.url)
        safe_label = "".join(ch if ch.isalnum() or ch in "-_" else "_" for ch in label)
        relative = Path(source_id) / digest[:2] / f"{safe_label}-{digest[:16]}{extension}"
        destination = self.raw_dir / relative
        destination.parent.mkdir(parents=True, exist_ok=True)
        if not destination.exists():
            temporary = destination.with_suffix(destination.suffix + ".tmp")
            temporary.write_bytes(content)
            temporary.replace(destination)

        request_url = redact_url(response.url, sensitive_parameters)
        sensitive = {item.lower() for item in (sensitive_parameters or set())}
        parameter_items = params.items() if isinstance(params, dict) else (params or [])
        request_metadata = {
            "params": [
                [key, "REDACTED" if str(key).lower() in sensitive else value]
                for key, value in parameter_items
            ],
            "json_body_sha256": (
                sha256(
                    json.dumps(json_body, sort_keys=True, default=str).encode("utf-8")
                ).hexdigest()
                if json_body is not None
                else None
            ),
        }
        artifact = Artifact(
            source_id=source_id,
            source_url=request_url,
            local_path=str(relative),
            content_type=content_type,
            retrieved_at=utc_now(),
            sha256=digest,
            size_bytes=len(content),
            request_method=method.upper(),
            request_metadata=request_metadata,
            response_headers={
                key: value
                for key, value in response.headers.items()
                if key.lower() in {"content-type", "etag", "last-modified", "date"}
            },
        )
        return BytesResult(artifact=artifact, content=content)

    def request_json(self, *args: Any, **kwargs: Any) -> JsonResult:
        result = self.request_bytes(*args, **kwargs)
        try:
            data = json.loads(result.content.decode("utf-8-sig"))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise AcquisitionError(
                f"Expected JSON from {result.artifact.source_url}: {exc}"
            ) from exc
        return JsonResult(artifact=result.artifact, data=data)

    @staticmethod
    def _extension(content_type: str | None, url: str) -> str:
        if content_type == "application/json":
            return ".json"
        if content_type in {"application/zip", "application/x-zip-compressed"}:
            return ".zip"
        if content_type in {
            "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            "application/vnd.ms-excel",
        }:
            return ".xlsx"
        suffix = Path(urlsplit(url).path).suffix
        if suffix and len(suffix) <= 10:
            return suffix
        return mimetypes.guess_extension(content_type or "") or ".bin"
