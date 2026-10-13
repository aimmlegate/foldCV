"""Named source dates keep exact month/day precision and reject unsupported dates."""

import pytest

from packages.resume_core.models.contracts import PartialDate
from packages.resume_core.normalization import _observed_date


def point(year=2022, month=3, day=None):
    return PartialDate(precision="day" if day is not None else "month" if month is not None else "year",
                       year=year, month=month, day=day)


@pytest.mark.parametrize("text", ["Март 2022 — Май 2023", "марта 2022", "МАРТ\n2022", "мар. 2022", "March 2022", "Mar. 2022"])
def test_named_month_matches_explicit_source_date(text):
    assert _observed_date(point(), text)
    assert not _observed_date(point(month=4), text)
    assert not _observed_date(point(year=2021), text)
    assert not _observed_date(point(day=1), text)


def test_named_day_matches_valid_calendar_date_without_losing_precision():
    assert _observed_date(point(year=2024, month=2, day=29), "Наблюдение: 29 февраля 2024")
    assert not _observed_date(point(year=2023, month=2, day=28), "29 февраля 2023")
    assert not _observed_date(point(month=2), "31 февраля 2022")
    assert not _observed_date(point(), "3 марта 2022")


@pytest.mark.parametrize("text", ["март 2022", "3 марта 2022", "31 февраля 2022"])
def test_named_date_year_cannot_be_accepted_as_a_bare_year(text):
    assert not _observed_date(point(month=None), text)
    assert _observed_date(point(month=None), text + "; отдельный год 2022")


@pytest.mark.parametrize("text", ["март", "2022", "март 20220", "супермарт 2022", "март приблизительно 2022", "03/04/2022", "маркетинг 2022"])
def test_missing_ambiguous_or_unrelated_date_words_do_not_supply_a_month(text):
    assert not _observed_date(point(), text)


def test_iso_date_behavior_remains_supported():
    assert _observed_date(point(), "2022-03")
    assert _observed_date(point(day=7), "2022-03-07")
    assert _observed_date(point(month=None), "2022")
