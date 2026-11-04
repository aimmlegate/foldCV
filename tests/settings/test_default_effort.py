"""D144: without a chosen level a run takes high when the model offers levels above it, medium when high is its top."""

import pytest

from packages.resume_core.reasoning import default_effort, model_reasoning
from resume_api.cli.qualification import Version
from resume_api.providers import claude_catalog


def item(levels, default):
    return {'model': 'gpt-test', 'supportedReasoningEfforts': [{'reasoningEffort': level} for level in levels],
            'defaultReasoningEffort': default}


@pytest.mark.parametrize('levels, reported, expected', [
    (['low', 'medium', 'high', 'xhigh', 'max', 'ultra'], 'low', 'high'),
    (['low', 'medium', 'high', 'xhigh'], 'medium', 'high'),
    (['low', 'medium', 'high'], 'low', 'medium'),
    (['low', 'medium', 'high'], 'high', 'medium'),
    (['minimal', 'low', 'medium', 'high'], 'minimal', 'medium'),
    # Without medium or high the catalog's own default stays.
    (['low', 'xhigh'], 'low', 'low'),
    (['none'], 'none', 'none'),
])
def test_a_codex_catalog_default_follows_the_levels_the_model_offers(levels, reported, expected):
    reasoning = model_reasoning(item(levels, reported))
    assert reasoning.supported == levels and reasoning.default == expected


def test_a_model_without_levels_keeps_no_default():
    assert model_reasoning({'model': 'gpt-test'}).default is None
    assert default_effort([], None) is None


def test_a_reported_default_outside_the_levels_is_still_refused():
    with pytest.raises(ValueError):
        model_reasoning(item(['low', 'medium', 'high'], 'max'))


def test_every_claude_model_defaults_to_high_on_its_five_levels():
    reasoning = claude_catalog.reasoning_for(Version.parse('2.1.320'))
    assert reasoning and {model: value.default for model, value in reasoning.items()} == dict.fromkeys(reasoning, 'high')
