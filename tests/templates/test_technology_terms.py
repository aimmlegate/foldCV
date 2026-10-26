"""Technology blocks of the bundled template list short names, never sentences about their use."""

import pytest

from packages.resume_core.templates.compiler import compile_template
from packages.resume_core.templates.projection import SchemaFailure, validate_payload
from packages.resume_core.templates.store import BUNDLED_TEMPLATE

BLOCKS = ('programming', 'data_and_tools', 'infrastructure', 'role_tools')


def schema(block):
    return next(value for value in compile_template(BUNDLED_TEMPLATE).blocks if value.id == block).full_schema


@pytest.mark.parametrize('block', BLOCKS)
def test_short_names_from_the_generic_examples_are_accepted(block):
    validate_payload(schema(block), {'items': ['PostgreSQL', 'Kafka 4.0', 'Docker Compose', 'Node.js', 'C/C++', 'CTE (WITH)',
        'isolation levels (REPEATABLE READ)', 'Full-Text Search (tsvector/tsquery)', 'JavaScript (React, Node.js)', 'Laravel 5.1']})


@pytest.mark.parametrize('block', BLOCKS)
@pytest.mark.parametrize(('item', 'rule'), [
    # The 2026-10-26 import put whole source lines into the databases and tools block.
    ('Redis: кеш страниц', 'pattern'),
    ('Redis: использовался в интернет-магазине для ускорения загрузки страниц', 'maxLength'),
    ('MySQL; опыт работы с B-Tree (MVCC) базами данных', 'pattern'),
    ('Опыт работы с брокерами сообщений Kafka и RabbitMQ в нескольких проектах', 'maxLength'),
    ('Kafka\nRabbitMQ', 'pattern'),
    ('', 'minLength'),
])
def test_sentences_descriptions_and_line_breaks_are_refused(block, item, rule):
    with pytest.raises(SchemaFailure) as error:
        validate_payload(schema(block), {'items': ['Go', item]})
    assert error.value.rule[0] == rule


def test_a_block_lists_at_most_forty_names_and_key_skills_stay_phrases():
    with pytest.raises(SchemaFailure):
        validate_payload(schema('data_and_tools'), {'items': ['Tool ' + str(index) for index in range(41)]})
    # Analyst skills are phrases by design; only named technologies are limited.
    validate_payload(schema('key_skills'), {'items': ['Сбор и анализ требований: интервью, workshops, BPMN-моделирование процессов']})


@pytest.mark.parametrize('block', BLOCKS)
def test_the_model_reads_the_name_only_rule_in_its_prompt_and_its_review(block):
    # The model is told before it answers, and the reviewing model fails a non-name; the server limits come last.
    from packages.resume_core.template_review import required_rules
    package = compile_template(BUNDLED_TEMPLATE)
    declaration = next(value for value in package.definition.blocks if value.id == block)
    item = declaration.content_schema['properties']['items']['items']
    assert item['description'].startswith('One technology, tool or library name') and item['pattern'] == '^[^:;\\n]+$'
    assert any('names only' in rule for rule in package.definition.model.extract)
    support = [rule for rule in required_rules(declaration) if rule.id == block + '-support']
    assert support and support[0].parameters.instructions[0].startswith('Fail an item that is not a single name')
