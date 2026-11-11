"""The pieces both CLI providers share: the best-effort cost readers and the usage sum of one call's runs."""

import pytest

from resume_api.providers.content import ReportedUsage
from resume_api.providers.shared import _combine, amount, natural


@pytest.mark.parametrize(("value", "count", "share"), [
    (3, 3, 3.0), (0, 0, 0.0), (0.25, None, 0.25), (True, None, None), (-1, None, None), (-0.5, None, None),
    (2 ** 63, None, None), ("3", None, None), (None, None, None), (float("inf"), None, None),
    (float("nan"), None, None)])
def test_a_cost_field_is_read_only_as_a_plain_non_negative_number(value, count, share):
    assert natural(value) == count and amount(value) == share


def test_one_call_sums_its_runs_numbers_and_keeps_the_last_windows():
    first = ReportedUsage(10, 2, 3, True, {"claude": {"output": 3, "costUsd": 0.5,
                                                      "fiveHour": {"utilization": 0.1, "resetsAt": 5}}})
    second = ReportedUsage(4, 0, 1, True, {"claude": {"output": 1, "fiveHour": {"utilization": 0.3}}})
    combined = _combine([first, ReportedUsage(), second])
    assert (combined.input_tokens, combined.cached_input_tokens, combined.output_tokens) == (14, 2, 4)
    assert combined.detail == {"claude": {"output": 4, "costUsd": 0.5, "fiveHour": {"utilization": 0.3}}}
    assert _combine([ReportedUsage(1, 0, 1, True)]).detail is None and _combine([]).detail is None
