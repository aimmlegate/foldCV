"""D104: Focus durations counted from the jobs that list a technology when the CV states none."""

from types import SimpleNamespace

import pytest

from packages.resume_core.models.contracts import PartialDate
from packages.resume_core.templates.focus import duration_text, focus_durations


def month(year, value=None):
    return PartialDate(precision='month' if value else 'year', year=year, month=value, day=None)


def field(value, known=True):
    return SimpleNamespace(status='known' if known else 'unknown', value=value)


def job(identifier, *periods, kind='employment'):
    return SimpleNamespace(id=identifier, kind=kind, periods=[SimpleNamespace(start=field(start, start is not None),
        end=field(end, end is not None), present=field(present)) for start, end, present in periods])


def technology(identifier, name, owner=None, subproject=None):
    return SimpleNamespace(id=identifier, kind='technology', job_id=owner, subproject_id=subproject,
        canonical_id=SimpleNamespace(value=None), display=SimpleNamespace(raw_text=name))


AS_OF = PartialDate(precision='day', year=2026, month=10, day=26)


def test_overlapping_and_ongoing_jobs_count_each_month_once():
    facts = SimpleNamespace(records=[
        job('a', (month(2022, 2), month(2024, 10), False)),
        job('b', (month(2025, 2), month(2025, 9), False)),
        # Ongoing from 09.2025: it overlaps job b in September and runs to the formatting month.
        job('c', (month(2025, 9), None, True)),
        technology('t1', 'golang', 'a'), technology('t2', 'Golang', 'b'), technology('t3', 'golang', 'c'),
        technology('focus', 'Golang')])
    # 33 + 8 + 14 months, one shared: 54 months is 4.5 years, shown as 5.
    assert focus_durations(facts, AS_OF, 'ru') == {identifier: '5 лет' for identifier in ['t1', 't2', 't3', 'focus']}


def test_unknown_periods_and_unlinked_technologies_get_no_duration():
    facts = SimpleNamespace(records=[
        job('open', (month(2020, 1), None, False)), job('undated', (None, month(2021, 5), False)),
        job('short', (month(2026, 1), month(2026, 10), False), kind='subproject'),
        technology('kafka', 'Kafka', 'open'), technology('redis', 'Redis', 'undated'),
        technology('rust', 'Rust', subproject='short'), technology('lonely', 'Elixir'), technology('missing', 'Go', 'deleted-job')])
    assert focus_durations(facts, AS_OF, 'ru') == {'rust': '10 месяцев'}
    assert focus_durations(facts, AS_OF, 'en') == {'rust': '10 months'}


def test_year_precision_counts_the_middle_of_its_range():
    facts = SimpleNamespace(records=[job('old', (month(2010), month(2012), False)), technology('perl', 'Perl', 'old')])
    # Between 14 months (end of 2010 to start of 2012) and 36 months: 25 months rounds to 2 years.
    assert focus_durations(facts, AS_OF, 'ru') == {'perl': '2 года'}


@pytest.mark.parametrize(('months', 'ru', 'en'), [(0, None, None), (1, '1 месяц', '1 month'), (2, '2 месяца', '2 months'),
    (5, '5 месяцев', '5 months'), (11, '11 месяцев', '11 months'), (12, '1 год', '1 year'), (17, '1 год', '1 year'),
    (18, '2 года', '2 years'), (60, '5 лет', '5 years'), (132, '11 лет', '11 years'), (252, '21 год', '21 years')])
def test_duration_words(months, ru, en):
    assert duration_text(months, 'ru') == ru and duration_text(months, 'en') == en


@pytest.mark.parametrize(('item', 'rule'), [
    ({'technology': 'Golang', 'experience': 'Разработка сервисов учета и автозаказа ТМЦ для ПВЗ.'}, 'maxLength'),
    ({'technology': 'Golang', 'experience': 'много'}, 'pattern'),
    ({'technology': 'Golang, Kafka, PostgreSQL', 'experience': None}, 'pattern'),
])
def test_the_bundled_focus_refuses_descriptions_and_lists(item, rule):
    # The manual import of 2026-10-26 put project descriptions under experience and grouped technologies in one entry.
    from packages.resume_core.templates.compiler import compile_template
    from packages.resume_core.templates.projection import SchemaFailure, validate_payload
    from packages.resume_core.templates.store import BUNDLED_TEMPLATE
    schema = next(block for block in compile_template(BUNDLED_TEMPLATE).blocks if block.id == 'focus').full_schema
    validate_payload(schema, [{'technology': 'Golang', 'experience': '6 лет'}, {'technology': 'Kafka', 'experience': None},
        {'technology': 'Redis', 'experience': '1,5 года'}, {'technology': 'Docker', 'experience': '10 месяцев'}])
    with pytest.raises(SchemaFailure) as error:
        validate_payload(schema, [item])
    assert error.value.rule[0] == rule
    with pytest.raises(SchemaFailure):
        validate_payload(schema, [{'technology': 'Tech' + str(index), 'experience': None} for index in range(11)])
