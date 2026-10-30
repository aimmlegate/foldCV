"""Independent boundary and set-of-months checks for date policies."""

import copy
import json
import random
from datetime import date
from pathlib import Path

import pytest
from pydantic import ValidationError

from packages.resume_core.dates import (
    estimate_exposure, format_date, month_bounds, old_job, partial_date, project_experience, source_date, union_months,
)
from packages.resume_core.models.contracts import Period, Project


EXAMPLE = json.loads((Path(__file__).resolve().parents[2] / "contracts/examples/project.json").read_text())


def project_with_technology(*, as_of=True, duplicate=False) -> Project:
    data = copy.deepcopy(EXAMPLE)
    if not as_of:
        data["asOf"] = None
    fact = copy.deepcopy(data["facts"][1])
    fact["id"] = "tech_sub"
    fact["value"] = {"canonicalId": "python", "display": "Python 3.11", "scope": "subproject"}
    fact["jobId"] = "job_1"
    fact["subprojectId"] = "sub_1"
    data["facts"].append(fact)
    data["employment"][0]["factIds"].append(fact["id"])
    data["employment"][0]["subprojects"][0]["factIds"].append(fact["id"])
    if duplicate:
        again = copy.deepcopy(fact)
        again["id"] = "tech_duplicate"
        data["facts"].append(again)
        data["employment"][0]["factIds"].append(again["id"])
        data["employment"][0]["subprojects"][0]["factIds"].append(again["id"])
    return Project.model_validate(data)


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


def test_exposure_preserves_precision_and_requires_explicit_as_of() -> None:
    period = Period(start=partial_date("2020"), end=partial_date("2021"))
    assert estimate_exposure([("job", None, period)], None) is None
    estimate = estimate_exposure([("job", None, period)], partial_date("2026-10-10"))
    assert estimate is not None
    assert (estimate.months_min, estimate.months_max) == (2, 24)
    ongoing = Period(start=partial_date("2026-09"), end=None)
    assert estimate_exposure([("job", None, ongoing)], None) is None
    assert estimate_exposure([("job", None, ongoing)], partial_date("2026-10-10")).months_min == 2
    with pytest.raises(ValueError, match="future interval"):
        estimate_exposure([("job", None, ongoing)], partial_date("2026-08-31"))
    same_month_future = Period(start=partial_date("2026-10-20"), end=None)
    with pytest.raises(ValueError, match="future interval"):
        estimate_exposure([("job", None, same_month_future)], partial_date("2026-10-10"))


def test_subproject_exposure_is_bounded_and_duplicate_facts_do_not_add_months() -> None:
    project = project_with_technology()
    result = project_experience(project, "python")
    assert result is not None
    assert (result.months_min, result.months_max) == (28, 28)
    assert [(item.job_id, item.subproject_id) for item in result.intervals] == [("job_1", "sub_1")]
    duplicate = project_experience(project_with_technology(duplicate=True), "python")
    assert duplicate is not None
    assert (duplicate.months_min, duplicate.months_max) == (28, 28)
    assert project_experience(project_with_technology(as_of=False), "python") is None
    invalid = copy.deepcopy(EXAMPLE)
    invalid["employment"][0]["subprojects"][0]["period"]["end"]["year"] = 2025
    with pytest.raises(ValidationError, match="subproject period outside job"):
        Project.model_validate(invalid)
    no_subproject_dates = copy.deepcopy(EXAMPLE)
    no_subproject_dates["employment"][0]["subprojects"][0]["period"] = None
    fact = copy.deepcopy(no_subproject_dates["facts"][1])
    fact.update(id="tech_undated_sub", jobId="job_1", subprojectId="sub_1")
    fact["value"].update(scope="subproject")
    no_subproject_dates["facts"].append(fact)
    no_subproject_dates["employment"][0]["factIds"].append(fact["id"])
    no_subproject_dates["employment"][0]["subprojects"][0]["factIds"].append(fact["id"])
    assert project_experience(Project.model_validate(no_subproject_dates), "python") is None
    unresolved_link = project_with_technology().model_dump(by_alias=True)
    linked_fact = next(fact for fact in unresolved_link["facts"] if fact["id"] == "tech_sub")
    linked_fact["subprojectId"] = None
    unresolved_link["employment"][0]["subprojects"][0]["factIds"].remove("tech_sub")
    assert project_experience(Project.model_validate(unresolved_link), "python") is None


def test_nested_duplicate_job_periods_do_not_change_exposure_or_order() -> None:
    data = project_with_technology().model_dump(by_alias=True)
    nested_job = {"id": "job_nested", "employer": "Example Nested", "role": "Consultant",
                  "periods": [{"start": {"precision": "month", "year": 2021, "month": 6, "day": None},
                               "end": {"precision": "month", "year": 2022, "month": 2, "day": None}}],
                  "subprojects": [], "factIds": ["tech_nested"]}
    nested_fact = copy.deepcopy(next(fact for fact in data["facts"] if fact["id"] == "tech_sub"))
    nested_fact.update(id="tech_nested", jobId="job_nested", subprojectId=None)
    nested_fact["value"]["scope"] = "job"
    data["employment"].append(nested_job)
    data["facts"].append(nested_fact)
    first = project_experience(Project.model_validate(data), "python")
    assert first is not None and (first.months_min, first.months_max) == (28, 28)
    data["employment"].reverse()
    data["facts"].reverse()
    second = project_experience(Project.model_validate(data), "python")
    assert second is not None and (second.months_min, second.months_max) == (28, 28)


def test_exact_fifteen_year_cutoff_including_leap_day() -> None:
    assert old_job("2011-10-09", "2026-10-10")
    assert not old_job("2011-10-10", "2026-10-10")
    assert not old_job("2011-10", "2026-10-10")
    assert old_job("2009-02-27", "2024-02-29")
    assert not old_job("2009-02-28", "2024-02-29")
    assert old_job("2010", "2026")
    assert not old_job("2011", "2026")
    assert not old_job("0001", "0015")
    assert date(*partial_date("2024-02-29").lower()).day == 29


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
