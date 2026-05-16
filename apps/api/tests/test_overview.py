from __future__ import annotations

import pytest
from prism.services.ga4.queries import resolve_date_range, compare_period
from datetime import date, timedelta


def test_resolve_preset_last_30d() -> None:
    start, end = resolve_date_range(None, None, "last_30d")
    today = date.today()
    assert end == today - timedelta(days=1)
    assert start == today - timedelta(days=30)


def test_resolve_explicit_dates() -> None:
    start, end = resolve_date_range("2024-01-01", "2024-01-31", None)
    assert start == date(2024, 1, 1)
    assert end == date(2024, 1, 31)


def test_resolve_preset_takes_precedence() -> None:
    # preset overrides explicit dates when both provided
    start, end = resolve_date_range("2024-01-01", "2024-01-31", "last_7d")
    today = date.today()
    assert end == today - timedelta(days=1)


def test_compare_previous_period() -> None:
    start = date(2024, 2, 1)
    end = date(2024, 2, 29)  # 29 days
    cstart, cend = compare_period(start, end, "previous_period")
    delta = (end - start).days + 1  # 29
    assert cend == start - timedelta(days=1)   # 2024-01-31
    assert (cend - cstart).days + 1 == delta   # same window length


def test_compare_same_period_last_year() -> None:
    start = date(2024, 3, 1)
    end = date(2024, 3, 31)
    cstart, cend = compare_period(start, end, "same_period_last_year")
    assert cstart == date(2023, 3, 1) - timedelta(days=365) + timedelta(days=365)
    # simpler: 365 days back
    assert cstart == start - timedelta(days=365)
    assert cend == end - timedelta(days=365)


def test_invalid_preset_raises() -> None:
    with pytest.raises(ValueError, match="Unknown preset"):
        resolve_date_range(None, None, "last_forever")


def test_kpi_delta() -> None:
    from prism.services.ga4.queries import _delta
    assert _delta(110, 100) == pytest.approx(10.0)
    assert _delta(90, 100) == pytest.approx(-10.0)
    assert _delta(50, 0) is None
    assert _delta(50, None) is None
