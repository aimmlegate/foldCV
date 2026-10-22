"""An explicit unresolved human endpoint remains visible without typed inference."""


def period_endpoint(period):
    value = period.present
    return 'present' if (value.value is True or value.user_corrected and value.value is None
        and bool(value.raw_text)) else 'end'


def period_field_id(key):
    if not key.startswith('period:'):
        return None
    identifier, separator, member = key.removeprefix('period:').rpartition(':')
    return identifier if separator and identifier and member in {'start', 'end', 'present'} else None
