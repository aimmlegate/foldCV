"""T0.6 of D158: what a scripted import sends to the model is pinned per fixture, so a change that makes a prompt or
a reply schema larger fails here, and a saving is locked in by lowering the pin."""

import json

import pytest

from resume_api.providers.structured_schema import StructuredSchema
from tests.templates.generic_fixtures import generic_import


# A whole scripted import per fixture (F07 alone takes about 40 s): the calls and their requests come only from the
# coordinator's run, its reviews and repairs.
pytestmark = pytest.mark.slow

# Model calls, and characters of every prompt and reply schema, of one import with rewriting at width 1. Width 1 runs
# the tasks in declaration order; at a higher width a review made before the role branch is decided lists the blocks
# of both branches, so its size would follow the timing.
PINS = {'F01': (28, 303569), 'F07': (28, 1671595), 'F10': (30, 361142)}
BELOW = 0.02


def schema_text(spec):
    # The reply schema as both CLI providers send it.
    return json.dumps(StructuredSchema(spec.provider_schema).wire, ensure_ascii=False, allow_nan=False, separators=(',', ':'))


@pytest.mark.asyncio
@pytest.mark.parametrize('name', sorted(PINS))
async def test_a_scripted_import_sends_no_more_and_not_much_less_than_its_pinned_request_size(tmp_path, monkeypatch, name):
    # The sizes do not depend on the repository's cross-checks, which make these imports four times slower; the
    # other scripted imports keep them.
    monkeypatch.delenv('FOLDCV_VERIFY', raising=False)
    sizes = []

    def wrap(script):
        def measured(request, value):
            sizes.append((len(request.text), len(schema_text(request.result_type))))
            return script(request, value)
        return measured

    _fixture, result, _workspace, _originals = await generic_import(tmp_path, name, wrap=wrap)
    assert result.state == 'published'
    calls, pinned = PINS[name]
    prompt, schema = sum(size[0] for size in sizes), sum(size[1] for size in sizes)
    total = prompt + schema
    assert len(sizes) == calls, f'{name}: {len(sizes)} model calls, pinned {calls}: set the pin to ({len(sizes)}, {total})'
    assert total <= pinned, f'{name}: {total} characters of prompt ({prompt}) and reply schema ({schema}), above the pin {pinned}'
    assert total >= pinned * (1 - BELOW), (f'{name}: {total} characters, more than {BELOW:.0%} below the pin {pinned}: '
                                           f'lower the pin to {total} to lock the saving in')
