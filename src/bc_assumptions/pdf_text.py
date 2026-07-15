from __future__ import annotations

from hashlib import sha256
from io import BytesIO
from pathlib import Path
import re
import shutil
import subprocess
import tempfile

from pypdf import PdfReader


class PDFTextExtractionError(RuntimeError):
    """Raised when a PDF cannot be converted to trustworthy text."""


def normalize_document_text(text: str, *, preserve_lines: bool = True) -> str:
    substitutions = {
        "\u00a0": " ",
        "\u2212": "-",
        "\u2013": "-",
        "\u2014": "-",
        "\ufb01": "fi",
        "\ufb02": "fl",
        "\u2026": "...",
        "/uni00A0": " ",
    }
    for old, new in substitutions.items():
        text = text.replace(old, new)
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    if preserve_lines:
        lines = [re.sub(r"[ \t]+", " ", line).rstrip() for line in text.splitlines()]
        return "\n".join(lines)
    return re.sub(r"\s+", " ", text).strip()


def structural_fingerprint(text: str) -> str:
    normalized = re.sub(r"\d+(?:[.,]\d+)*", "#", normalize_document_text(text, preserve_lines=False).lower())
    normalized = re.sub(r"[^a-z#%$]+", " ", normalized)
    return sha256(normalized.encode("utf-8")).hexdigest()


def extract_pdf_text(
    content: bytes,
    *,
    require_pdftotext: bool = True,
    layout: bool = True,
    mode: str | None = None,
    minimum_characters: int = 500,
) -> str:
    """Extract text while preferring Poppler's pdftotext.

    Several B.C. government PDFs use embedded fonts that pypdf does not decode
    reliably. Production historical collectors therefore require pdftotext and
    fail closed when it is unavailable. The pypdf fallback exists for unit tests
    and explicitly non-critical sources only.
    """

    executable = shutil.which("pdftotext")
    if executable:
        with tempfile.TemporaryDirectory(prefix="bc-assumptions-pdf-") as temporary:
            source = Path(temporary) / "document.pdf"
            target = Path(temporary) / "document.txt"
            source.write_bytes(content)
            command = [executable]
            selected_mode = mode or ("layout" if layout else "raw")
            if selected_mode not in {"layout", "raw"}:
                raise PDFTextExtractionError(f"Unsupported pdftotext mode: {selected_mode}")
            command.append(f"-{selected_mode}")
            command.extend([str(source), str(target)])
            completed = subprocess.run(command, capture_output=True, text=True, check=False)
            if completed.returncode != 0:
                raise PDFTextExtractionError(
                    f"pdftotext failed with exit code {completed.returncode}: "
                    f"{completed.stderr.strip()[:500]}"
                )
            text = normalize_document_text(target.read_text(encoding="utf-8", errors="replace"))
            if len(text.strip()) < minimum_characters:
                raise PDFTextExtractionError(
                    f"pdftotext returned only {len(text.strip())} characters"
                )
            return text

    if require_pdftotext:
        raise PDFTextExtractionError(
            "pdftotext is required for historical PDF extraction. Install poppler-utils."
        )

    reader = PdfReader(BytesIO(content))
    text = normalize_document_text("\n".join(page.extract_text() or "" for page in reader.pages))
    if len(text.strip()) < minimum_characters:
        raise PDFTextExtractionError(f"pypdf returned only {len(text.strip())} characters")
    return text
