"""Independent boundary and set-of-months checks for date policies."""

import random

import pytest
from pydantic import ValidationError

from packages.resume_core.dates import format_date, month_bounds, partial_date, source_date, union_months


def test_union_matches_independent_month_set_for_overlap_nesting_and_duplicates() -> None:
    randomizer = random.Random(41)
    for _ in range(100):
        intervals = [(start, start + randomizer.randrange(1, 15))
                     for start in (randomizer.randrange(0, 35) for _ in range(9))]
        intervals += [intervals[0], (intervals[1][0] + 1, intervals[1][1] - 1)]
        expected = len({month for start, end in intervals for month in range(start, end + 1)})
        assert union_months(intervals) == expected
        assert union_months(reversed(intervals)) == expected
        assert union_months(intervals + intervals) == expected


def test_partial_dates_leap_days_precision_and_invalid_dates() -> None:
    assert month_bounds("2024") == (2024 * 12, 2024 * 12 + 11)
    assert month_bounds("2024-02-29") == (2024 * 12 + 1, 2024 * 12 + 1)
    for invalid in ("2023-02-29", "2024-13", "2024-02-30", "2024-2", "2024-01-01x"):
        with pytest.raises((ValueError, ValidationError)):
            partial_date(invalid)


@pytest.mark.parametrize('text,year,month,day', [('2020', 2020, None, None), ('2020-03', 2020, 3, None), ('03.2020', 2020, 3, None),
    ('3/2020', 2020, 3, None), ('15.03.2020', 2020, 3, 15), ('Март 2020', 2020, 3, None), ('mar 2020', 2020, 3, None)])
def test_source_dates_read_as_written(text, year, month, day):
    value, _pattern = source_date(text)
    assert (value.year, value.month, value.day) == (year, month, day)


@pytest.mark.parametrize('text', ['', 'весна 2021', '13.2020', '31.02.2020', '15.03/2020', 'н.в.'])
def test_other_text_is_no_source_date(text):
    assert source_date(text) is None


@pytest.mark.parametrize('sibling,value,expected', [('11.2023', '2020-04', '04.2020'), ('11/2023', '2020-04', '04/2020'),
    ('2023', '2020-04', '2020'), ('2023-11', '2020-04-02', '2020-04'), ('11.2023', '2020', '2020'),
    ('Ноябрь 2023', '2020-03', 'Март 2020'), ('ноя 2023', '2020-03', 'мар 2020'), ('01.11.2023', '2020-04-02', '02.04.2020')])
def test_a_date_takes_its_siblings_pattern_and_precision(sibling, value, expected):
    assert format_date(partial_date(value), source_date(sibling)[1]) == expected
