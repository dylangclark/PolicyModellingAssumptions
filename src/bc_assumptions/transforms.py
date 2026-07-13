from __future__ import annotations

import calendar
from datetime import date, datetime, timedelta
from typing import Any, Iterable


SCALAR_MULTIPLIERS = {
    0: 1,
    1: 10,
    2: 100,
    3: 1_000,
    4: 10_000,
    5: 100_000,
    6: 1_000_000,
    7: 10_000_000,
    8: 100_000_000,
    9: 1_000_000_000,
}

FREQUENCY_NAMES = {
    1: "daily",
    2: "weekly",
    4: "biweekly",
    6: "monthly",
    7: "bimonthly",
    9: "quarterly",
    11: "semiannual",
    12: "annual",
    13: "every_2_years",
    14: "every_3_years",
    15: "every_4_years",
    16: "every_5_years",
    17: "every_10_years",
    18: "occasional",
    19: "occasional_quarterly",
    20: "occasional_monthly",
    21: "occasional_daily",
}


def parse_iso_date(value: str) -> date:
    return datetime.fromisoformat(value[:10]).date()


def _end_of_month(year: int, month: int) -> date:
    return date(year, month, calendar.monthrange(year, month)[1])


def _add_months(start: date, months: int) -> date:
    zero_based = start.year * 12 + (start.month - 1) + months
    year, month_index = divmod(zero_based, 12)
    return _end_of_month(year, month_index + 1)


def period_end(start: date, frequency_code: int | None) -> date:
    if frequency_code in {1, 18, 21, None}:
        return start
    if frequency_code == 2:
        return start + timedelta(days=6)
    if frequency_code == 4:
        return start + timedelta(days=13)
    if frequency_code in {6, 20}:
        return _end_of_month(start.year, start.month)
    if frequency_code == 7:
        return _add_months(start, 1)
    if frequency_code in {9, 19}:
        return _add_months(start, 2)
    if frequency_code == 11:
        return _add_months(start, 5)
    if frequency_code == 12:
        return date(start.year, 12, 31)
    if frequency_code in {13, 14, 15, 16, 17}:
        years = {13: 2, 14: 3, 15: 4, 16: 5, 17: 10}[frequency_code]
        return date(start.year + years - 1, 12, 31)
    return start


def previous_year(value: date) -> date:
    try:
        return value.replace(year=value.year - 1)
    except ValueError:
        return value.replace(year=value.year - 1, day=28)


def calculate_yoy(points: Iterable[dict[str, Any]]) -> list[dict[str, Any]]:
    rows = sorted(points, key=lambda row: row["reference_period_start"])
    by_date = {parse_iso_date(row["reference_period_start"]): row for row in rows}
    output: list[dict[str, Any]] = []
    for row in rows:
        current_date = parse_iso_date(row["reference_period_start"])
        prior = by_date.get(previous_year(current_date))
        if not prior:
            continue
        current_value = row.get("value")
        prior_value = prior.get("value")
        if current_value is None or prior_value in {None, 0}:
            continue
        derived = dict(row)
        derived["value"] = (float(current_value) / float(prior_value) - 1.0) * 100.0
        derived["metadata"] = {
            **row.get("metadata", {}),
            "derived_from_reference_period": prior["reference_period_start"],
            "transform": "yoy_pct",
        }
        output.append(derived)
    return output
