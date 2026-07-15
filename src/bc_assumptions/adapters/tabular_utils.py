from __future__ import annotations

import csv
import io
import re
import zipfile
from typing import Iterable


def norm(value: object) -> str:
    return re.sub(r"[^a-z0-9]+", "_", str(value or "").strip().lower()).strip("_")


def number(value: object) -> float | None:
    text = str(value or "").strip().replace(",", "")
    if text in {"", "-", "..", "n/a", "na", "null"}:
        return None
    try:
        return float(text)
    except ValueError:
        return None


def find_column(headers: Iterable[str], aliases: Iterable[str], *, required: bool = True) -> str | None:
    by_norm = {norm(h): h for h in headers}
    hits = [by_norm[norm(a)] for a in aliases if norm(a) in by_norm]
    hits = list(dict.fromkeys(hits))
    if len(hits) == 1:
        return hits[0]
    if not hits and not required:
        return None
    raise ValueError(f"Expected exactly one column for aliases {list(aliases)!r}; found {hits!r}")


def csv_rows(content: bytes, encoding: str = "utf-8-sig") -> list[dict[str, str]]:
    text = content.decode(encoding, errors="replace")
    reader = csv.DictReader(io.StringIO(text))
    if not reader.fieldnames:
        raise ValueError("CSV has no header row")
    return [dict(row) for row in reader]


def zip_csv_members(content: bytes) -> list[tuple[str, bytes]]:
    with zipfile.ZipFile(io.BytesIO(content)) as archive:
        names = [n for n in archive.namelist() if n.lower().endswith(".csv") and not n.endswith("/")]
        if not names:
            raise ValueError("ZIP contains no CSV files")
        return [(name, archive.read(name)) for name in names]
