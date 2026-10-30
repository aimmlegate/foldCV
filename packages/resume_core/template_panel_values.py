"""An explicit unresolved human endpoint remains visible without typed inference; dates the panel sends take the
document's wording."""

from dataclasses import replace

from .dates import ISO_DATE, format_date, source_date
from .models.template_document import FieldOccurrence
from .rich_fields import field_key, working_field


def period_endpoint(period):
    value = period.present
    return 'present' if (value.value is True or value.user_corrected and value.value is None
        and bool(value.raw_text)) else 'end'


def period_field_id(key):
    if not key.startswith('period:'):
        return None
    identifier, separator, member = key.removeprefix('period:').rpartition(':')
    return identifier if separator and identifier and member in {'start', 'end', 'present'} else None


def field_occurrence(allocator, kind, record, key, ref, *seed):
    """A complete bound occurrence of one record field, with ids from the panel's allocation seeds."""
    value = working_field(record, key)
    root = allocator.allocate('occurrence', [f'panel-{kind}-occurrence', record.id, *seed])
    return FieldOccurrence(type='fact_field', bindingId=allocator.allocate('fragment', [f'panel-{kind}-fragment', root]),
        bindingRootId=root, recordId=record.id, fieldKey=key, cellId=field_key(record.id, key), occurrenceId=root,
        complete=True, presentation=ref, text=value.raw_text, styles={}, syncedFactRevision=value.revision)


def _resume_pattern(facts):
    """How the resume's periods write a month; a year alone does not say."""
    for record in facts.records:
        for period in getattr(record, 'periods', []):
            for value in (period.start, period.end):
                found = source_date(value.raw_text)
                if found is not None and found[1].precision != 'year':
                    return replace(found[1], precision='day')
    return ISO_DATE


def written_dates(facts, original, updated, keys):
    """Each period date the panel sent in ISO form takes the sibling endpoint's pattern and precision, else the field's own
    pattern, else the one the resume's periods use. Text the user wrote in another form stays as it is."""
    for key in keys:
        value = working_field(updated, key)
        written = source_date(value.raw_text) if key.startswith('period:') and not key.endswith(':present') else None
        if written is None or not (written[1].year_first or written[1].precision == 'year'):
            continue
        base, _colon, name = key.rpartition(':')
        sources = [working_field(original, base + (':end' if name == 'start' else ':start')), working_field(original, key)] \
            if original is not None else []
        pattern = next((found[1] for field in sources if field is not None and (found := source_date(field.raw_text)) is not None), None)
        value.raw_text = format_date(value.value, pattern or _resume_pattern(facts))
