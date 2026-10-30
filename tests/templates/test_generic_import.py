"""S4: the bundled two-column template imports end to end with scripted providers (B01–B08 on F01–F07 and F10)."""

import pytest

from packages.resume_core.models.template_document import BoundLink, FieldOccurrence
from packages.resume_core.template_import import spent_calls
from tests.templates.generic_fixtures import F10_REJECTED, F10_RESULT, TABLES, generic_import, export_through_service, f06
from tests.templates.test_template_view_adapters import text


pytestmark = pytest.mark.slow

IMPORTS = {}
B02_CLAIM = 'I reduced median latency by 80%.'


def b02_review(check):
    return 'violation' if check.get('ruleId') == 'projects-attribution' and check.get('value') == B02_CLAIM else None


def b03_review(check):
    # The ownership check cannot confirm the employer the reply chose for the unowned paragraph.
    return ('uncertain' if check.get('ruleId') == 'projects-claim_ownership' and check.get('kind') == 'relation'
        and '/results/' in str(check.get('subject')) else None)


def b02_table():
    table = TABLES['F01'](True)
    payload, cites = table['projects']
    payload[0]['results'] = [{'value': B02_CLAIM}]
    table['projects'] = (payload, {**cites, '/0/results/0/value': 'Our team reduced median latency from 800 ms to 500 ms.'})
    return table


CASES = {
    'F10-on': ('F10', {'rewrite': True}),
    # Without Perl in its own group, the old job's Perl joins the fallback group after that group's own items.
    'F10-off': ('F10', {'rewrite': False, 'table': {**TABLES['F10'](False), 'programming': ({'items': ['Python']}, {})}}),
    'F02-on': ('F02', {'rewrite': True}),
    'F02-off': ('F02', {'rewrite': False}),
    'B02': ('F01', {'table': b02_table(), 'verdict': b02_review}),
    'B03': ('F03', {'verdict': b03_review}),
    'F04-on': ('F04', {'rewrite': True}),
    'F04-off': ('F04', {'rewrite': False}),
    'F06-analyst': ('F06', {}),
    'F06-technical': ('F06', {'table': f06(True, 'other')}),
    'F07': ('F07', {}),
    # D104: Focus entries without a stated length show the time the jobs listing the technology span.
    'F10-durations': ('F10', {'rewrite': True, 'table': {**TABLES['F10'](True), 'focus': ([
        {'technology': 'Python', 'experience': '3 years'}, {'technology': 'PostgreSQL', 'experience': None},
        {'technology': 'Perl', 'experience': None}, {'technology': 'Docker', 'experience': None}], {})}}),
}


async def shared(tmp_path_factory, key):
    """Each case imports once per session (about thirty durable calls); tests only read or derive from it."""
    if key not in IMPORTS:
        name, options = CASES[key]
        fixture, result, workspace, originals = await generic_import(tmp_path_factory.mktemp(key), name, **options)
        assert result.state == 'published' and result.publication.state == 'saved'
        IMPORTS[key] = fixture, result, workspace, originals
    return IMPORTS[key]


def views(workspace):
    """Each view's paragraph, heading and list texts in document order."""
    result = {}
    for block in workspace.project.document.blocks():
        if block.type != 'section':
            result.setdefault(block.presentation.view_key, []).append(text(block))
    return result


def order(workspace):
    return list(dict.fromkeys(block.presentation.view_key for region in workspace.project.document.regions
        for block in region.blocks))


def records(workspace, kind):
    return [record for record in workspace.project.facts.records if record.kind == kind]


def body(workspace):
    return '\n'.join(text(block) for block in workspace.project.document.blocks() if block.type != 'section')


@pytest.mark.asyncio
@pytest.mark.parametrize('rewrite', [True, False])
async def test_every_generic_block_imports_with_partial_records_and_one_rejected_result_span(tmp_path_factory, rewrite):
    # B08: all blocks of the technical branch; the rewritten result claims more than its own source line.
    fixture, result, workspace, _originals = await shared(tmp_path_factory, 'F10-on' if rewrite else 'F10-off')
    states = {task.block_id: task.state for task in result.tasks}
    # The other branch's groups, the absent portfolio and, with rewriting off, the compact list are empty.
    assert {block for block, state in states.items() if state == 'empty'} == {
        'key_skills', 'role_tools', 'portfolio', *([] if rewrite else ['other_projects'])}
    assert states['projects'] == 'accepted' and states['other_projects'] == ('accepted' if rewrite else 'empty')
    # D114: every block, the projects block included, runs the effort chosen for the import.
    assert {attempt.model.effort for attempt in result.attempts} == {result.capture.primary.effort}
    shown = views(workspace)
    assert order(workspace) == ['identity', 'focus', 'education', 'courses', 'location', 'languages', 'opensource', 'summary',
        'projects', *(['other_projects'] if rewrite else []), 'career_highlights', 'programming', 'data_and_tools', 'infrastructure']
    # Partial records show what they state, without placeholders, stray separators or empty headings.
    assert shown['education'] == ['ОБРАЗОВАНИЕ', 'Example Institute'] and shown['languages'] == ['ЯЗЫКИ', 'English']
    assert shown['location'] == ['ЛОКАЦИЯ', 'Example City, Example Country, UTC+1']
    assert shown['opensource'] == ['OPEN SOURCE', 'Queue Tools'] and 'portfolio' not in shown
    # The accepted task shows once; only the rejected result's own source line falls back, without its line break.
    projects = shown['projects']
    # Without rewriting a list item keeps the source's wording and loses only its closing punctuation.
    task = 'Implemented queue processing' + ('.' if rewrite else '')
    assert projects.count(task) == 1 and projects[-1] == F10_RESULT
    text_all = body(workspace)
    assert text_all.count(F10_RESULT) == 1 and F10_REJECTED not in text_all and 'Результаты:' not in text_all
    assert 'None' not in text_all and 'null' not in text_all
    claims = sorted(record.value.raw_text for record in records(workspace, 'claim'))
    assert claims == [task]
    fallback, *uncertain = sorted(workspace.project.import_issues, key=lambda issue: issue.code != 'IMPORT_SOURCE_FALLBACK')
    assert (fallback.code, fallback.category, fallback.rule_id) == ('IMPORT_SOURCE_FALLBACK', 'content_violation', 'projects-support')
    assert [issue.code for issue in uncertain] == ([] if rewrite else ['IMPORT_SKILL_GROUP_UNCERTAIN'])
    # With rewriting off, rewrite fields show their exact source wording.
    if rewrite:
        assert shown['summary'][1] == 'Backend engineer focused on reliable queue systems.'
        assert 'Message queue platform for internal services.' in projects
        assert shown['other_projects'] == ['ДРУГИЕ ПРОЕКТЫ', 'Old Systems'] and 'Old Systems' not in projects
    else:
        assert shown['summary'][1] == 'Summary: Backend engineer focused on reliable queue systems.'
        assert 'Product: message queue platform for internal services.' in projects and 'Old Systems' in projects
    # The career-wide highlight has no owner; both employment records and the old job's technology stay facts.
    assert shown['career_highlights'] == ['КЛЮЧЕВЫЕ ДОСТИЖЕНИЯ', 'Mentored five engineers across teams.' if rewrite
        else 'Career: Mentored five engineers across teams']
    highlight = next(record for record in workspace.project.facts.extensions if record.semantic_type == 'foldcv:career_highlights')
    assert not highlight.relations and not any(relation.subject_id == highlight.id for relation in workspace.project.facts.relations)
    assert sorted(record.employer.raw_text for record in records(workspace, 'employment')) == ['Example Labs', 'Old Systems']
    assert sorted(record.display.raw_text for record in records(workspace, 'technology') if record.job_id) == [
        'Docker', 'Perl', 'PostgreSQL', 'Python']
    if rewrite:
        assert shown['programming'] == ['ЯП, ФРЕЙМВОРКИ, БИБЛИОТЕКИ', 'Python, Perl']
        assert shown['data_and_tools'] == ['СУБД, ИНСТРУМЕНТЫ', 'PostgreSQL']
    else:
        assert shown['programming'] == ['ЯП, ФРЕЙМВОРКИ, БИБЛИОТЕКИ', 'Python']
        assert shown['data_and_tools'] == ['СУБД, ИНСТРУМЕНТЫ', 'PostgreSQL, Perl']
    assert shown['infrastructure'] == ['ИНФРАСТРУКТУРА, ТАСК-МЕНЕДЖЕРЫ', 'Docker']
    # Fourteen model blocks run with one review each; the rejected result adds one repair and its review.
    assert spent_calls(result) == len(fixture.transport.calls) == 2 * 14 + 2


@pytest.mark.asyncio
@pytest.mark.parametrize('rewrite', [True, False])
async def test_missing_data_keeps_year_precision_and_adds_no_block_or_placeholder(tmp_path_factory, rewrite):
    # B01: F02 states year-only dates and no results, education, portfolio or location.
    _fixture, _result, workspace, _originals = await shared(tmp_path_factory, 'F02-on' if rewrite else 'F02-off')
    shown = views(workspace)
    assert order(workspace) == ['identity', 'projects', 'programming']
    assert shown['projects'] == ['ПРОЕКТЫ', 'Example Labs', '2020 – 2023', 'Python', 'Роль: backend engineer', 'Задачи:',
        'Implemented queue processing' + ('.' if rewrite else '')]
    [job] = records(workspace, 'employment')
    assert [(period.start.value.precision, period.end.value.precision, period.end.raw_text) for period in job.periods] == [
        ('year', 'year', '2023')]
    assert not records(workspace, 'education') and not records(workspace, 'language') and not workspace.project.import_issues


@pytest.mark.asyncio
async def test_an_unsupported_individual_metric_never_shows_and_the_team_result_stays_exact(tmp_path_factory):
    # B02: the reply turns the team result into an individual 80% claim; the attribution check rejects it.
    _fixture, _result, workspace, _originals = await shared(tmp_path_factory, 'B02')
    text_all = body(workspace)
    assert '80%' not in text_all and text_all.count('Our team reduced median latency from 800 ms to 500 ms.') == 1
    [issue] = workspace.project.import_issues
    assert (issue.code, issue.category, issue.rule_id) == ('IMPORT_SOURCE_FALLBACK', 'content_violation', 'projects-attribution')
    assert issue.block_ids
    assert sorted(record.value.raw_text for record in records(workspace, 'claim')) == ['Implemented queue processing.']


@pytest.mark.asyncio
async def test_an_unowned_claim_stays_exact_source_text_under_no_employer(tmp_path_factory):
    # B03: the reply gives the unowned paragraph to Second Works; the ownership check cannot confirm that link.
    _fixture, _result, workspace, _originals = await shared(tmp_path_factory, 'B03')
    shown = views(workspace)
    assert shown['projects'].count('Improved release reliability.') == 1
    fallback = next(block for block in workspace.project.document.blocks() if text(block) == 'Improved release reliability.')
    assert not any(isinstance(part, FieldOccurrence) for part in fallback.content) and fallback.content[0].citations
    assert not any(block.type == 'section' and fallback in block.children for block in workspace.project.document.blocks())
    [issue] = workspace.project.import_issues
    assert (issue.code, issue.category, issue.rule_id) == ('IMPORT_SOURCE_FALLBACK', 'uncertain_interpretation',
        'projects-claim_ownership')
    assert not records(workspace, 'claim') and sorted(record.employer.raw_text for record in records(workspace, 'employment')) == [
        'Example Labs', 'Second Works']


@pytest.mark.asyncio
@pytest.mark.parametrize('rewrite', [True, False])
async def test_the_fifteen_year_window_compacts_only_wholly_old_jobs_and_keeps_every_fact(tmp_path_factory, rewrite):
    # B04/B05: the cutoff is 2011-10-21; year-only 2011 and month-only 2011-10 may end after it.
    _fixture, _result, workspace, _originals = await shared(tmp_path_factory, 'F04-on' if rewrite else 'F04-off')
    shown = views(workspace)
    companies = ['Early Systems', 'Year Boundary', 'Month Boundary', 'Current Systems']
    detailed = [value for value in shown['projects'] if value in companies]
    if rewrite:
        assert detailed == companies[1:] and shown['other_projects'] == ['ДРУГИЕ ПРОЕКТЫ', 'Early Systems']
    else:
        assert detailed == companies and 'other_projects' not in shown
    assert 'summary' not in shown and sorted(record.employer.raw_text for record in records(workspace, 'employment')) == sorted(companies)
    # The old job's technology stays a fact and appears once among the active groups.
    assert sorted(record.display.raw_text for record in records(workspace, 'technology') if record.job_id) == ['Perl', 'Python']
    assert shown['programming'] == ['ЯП, ФРЕЙМВОРКИ, БИБЛИОТЕКИ', 'Perl, Python'] and 'data_and_tools' not in shown


@pytest.mark.asyncio
@pytest.mark.parametrize(('key', 'family', 'groups'), [
    ('F06-analyst', 'business_analyst', {'role_tools': ['ИНСТРУМЕНТЫ', 'Python, SQL, UnknownTool']}),
    ('F06-technical', 'other', {'programming': ['ЯП, ФРЕЙМВОРКИ, БИБЛИОТЕКИ', 'Python'],
        'data_and_tools': ['СУБД, ИНСТРУМЕНТЫ', 'SQL, UnknownTool']})])
async def test_the_role_branch_selects_the_skill_groups(tmp_path_factory, key, family, groups):
    # B06: analysts use key skills and tools; any other role the three technical groups.
    _fixture, result, workspace, _originals = await shared(tmp_path_factory, key)
    shown = views(workspace)
    skill_views = ['programming', 'data_and_tools', 'infrastructure', 'key_skills', 'role_tools']
    assert {view: shown[view] for view in skill_views if view in shown} == groups
    tasks = {task.id: task.block_id for task in result.tasks}
    branch = next(value.value for value in result.task_results if tasks[value.task_id] == 'role-branch')
    assert branch == {'branch': 'skills_and_tools' if family == 'business_analyst' else 'technical', 'family': family}


@pytest.mark.asyncio
async def test_sidebar_records_keep_their_wording_and_degree_and_courses_stay_separate(tmp_path_factory):
    # B07 import part: Focus durations as stated, one degree and two courses, the language level and the portfolio link.
    _fixture, _result, workspace, _originals = await shared(tmp_path_factory, 'F06-analyst')
    shown = views(workspace)
    assert shown['focus'] == ['ФОКУС', 'Python', '10 months', 'SQL', 'about 2.5 years', 'UnknownTool', '7 weeks']
    assert shown['education'] == ['ОБРАЗОВАНИЕ', 'Example University', '2019', 'Information Systems', 'BSc']
    assert shown['courses'] == ['СЕРТИФИКАТЫ', 'Example Academy, Queue Design, 2021', 'Systems School, Reliability Basics, 2022']
    assert shown['languages'] == ['ЯЗЫКИ', 'English working proficiency'] and shown['portfolio'] == ['ПОРТФОЛИО', 'Portfolio']
    [link] = [part for block in workspace.project.document.blocks() for part in block.content if isinstance(part, BoundLink)]
    assert link.href == 'https://example.org/portfolio'
    [degree], courses = records(workspace, 'education'), records(workspace, 'certification')
    assert (degree.qualification.raw_text, degree.completion.value.precision, degree.completion.raw_text) == ('BSc', 'year', '2019')
    assert sorted((course.name.raw_text, course.issuer.raw_text, course.date.raw_text) for course in courses) == [
        ('Queue Design', 'Example Academy', '2021'), ('Reliability Basics', 'Systems School', '2022')]
    [language] = records(workspace, 'language')
    assert (language.language.raw_text, language.level.raw_text) == ('English', 'working proficiency')
    [candidate] = records(workspace, 'candidate')
    assert (candidate.name.raw_text, candidate.title.raw_text, candidate.location.status) == (
        'Alex Example', 'Business analyst', 'unknown')
    focus = sorted((record.display.raw_text, record.experience.raw_text) for record in records(workspace, 'technology')
        if record.experience.raw_text)
    assert focus == [('Python', '10 months'), ('SQL', 'about 2.5 years'), ('UnknownTool', '7 weeks')]


@pytest.mark.asyncio
async def test_a_manual_focus_duration_and_order_stay_exact_through_transfer_and_docx(tmp_path_factory, tmp_path):
    # B07 editing part: Focus rows are technology facts; nothing recomputes them from years and icons stay decorative.
    from packages.resume_core.templates.presentation_plan import editor_plan
    from tests.templates.test_captured_docx import emitted, xml
    from tests.templates.test_template_g02_views import edit, find, text_range, transferred
    from tests.templates.test_template_view_adapters import render
    _fixture, _result, workspace, originals = await shared(tmp_path_factory, 'F06-analyst')
    stated = find(workspace, 'about 2.5 years')
    typed = edit(workspace, {'kind': 'replace_text', 'range': text_range(stated, 0, len('about 2.5 years')),
        'text': 'about 3 years', 'styles': {}}, 'duration')
    [sql] = [record for record in records(typed, 'technology') if record.display.raw_text == 'SQL' and record.experience.raw_text]
    assert (sql.experience.raw_text, sql.experience.user_corrected) == ('about 3 years', True)
    sections = [block for block in typed.project.document.blocks() if block.type == 'section' and block.presentation.view_key == 'focus']
    moved = next(block for block in sections if text(block.children[0]) == 'SQL')
    heading = find(typed, 'ФОКУС', 'heading')
    region = next(region for region in typed.project.document.regions if heading in region.blocks)
    ordered = edit(typed, {'kind': 'move_block', 'blockId': moved.id, 'beforeRevision': moved.revision,
        'placement': {'parentId': region.id, 'afterId': heading.id}}, 'order')
    plan = editor_plan(ordered.project)
    icons = [(text(block.children[0]), plan['blocks'][block.id]['focus']['icon']) for block in ordered.project.document.blocks()
        if block.id in plan['blocks'] and 'focus' in plan['blocks'][block.id]]
    # A row without a catalog icon shows the template's first-letter placeholder (D113).
    assert [name for name, _icon in icons] == ['SQL', 'Python', 'UnknownTool'] and icons[1][1] == 'python'
    assert icons[0][1].startswith('initial-') and icons[2][1].startswith('initial-') and icons[0][1] != icons[2][1]
    copy = transferred(ordered, originals)
    assert views(copy)['focus'] == ['ФОКУС', 'SQL', 'about 3 years', 'Python', '10 months', 'UnknownTool', '7 weeks']
    shown = emitted(xml(render(copy, tmp_path)))
    expected = ['SQL', 'about 3 years', 'Python', '10 months', 'UnknownTool', '7 weeks']
    assert [shown.index(value) for value in expected] == sorted(shown.index(value) for value in expected)
    assert '2.5' not in shown and 'Example University' in shown and 'Reliability Basics' in shown


@pytest.mark.asyncio
async def test_a_long_document_keeps_every_marker_once_and_in_order_and_exports(tmp_path_factory):
    # F07 import part of V02 (S4-7 under the default Settings limits, D096): 250 project and 100 sidebar markers, a long
    # name, title and URL; the stored project with its whole import record also exports through the service.
    from tests.templates.storage_fixtures import source_fixture
    from tests.templates.test_captured_docx import emitted, xml
    _fixture, result, workspace, originals = await shared(tmp_path_factory, 'F07')
    lines = source_fixture('F07')[0].units[0].text.splitlines()
    shown = views(workspace)
    for view, prefix, count in [('projects', 'PROJECT-MARKER-', 250), ('courses', 'SIDEBAR-MARKER-', 100)]:
        expected = [line for line in lines if line.startswith(prefix)]
        values = [value for value in shown[view] if value.startswith(prefix)]
        assert len(expected) == count and values == expected
    assert shown['identity'] == lines[:2] and shown['portfolio'] == ['ПОРТФОЛИО', lines[-1]]
    [link] = [part for block in workspace.project.document.blocks() for part in block.content if isinstance(part, BoundLink)]
    assert link.href == lines[-1] and link.label_binding is None
    assert len(records(workspace, 'claim')) == 250 and len(records(workspace, 'certification')) == 100
    assert not workspace.project.import_issues
    body = emitted(xml(await export_through_service(tmp_path_factory.mktemp('f07-export'), workspace, originals)))
    markers = [line for line in lines if line.startswith(('SIDEBAR-MARKER-', 'PROJECT-MARKER-'))]
    assert all(body.count(marker) == 1 for marker in markers)
    for prefix in ('SIDEBAR-MARKER-', 'PROJECT-MARKER-'):
        positions = [body.index(marker) for marker in markers if marker.startswith(prefix)]
        assert positions == sorted(positions)


@pytest.mark.asyncio
async def test_a_focus_entry_without_a_stated_length_shows_the_time_its_jobs_span(tmp_path_factory):
    # D104: the user chose durations counted from projects. PostgreSQL and Docker are listed in 03.2020–11.2023 (45
    # months, 4 years); Perl in 2006–2008, year precision (between 14 and 36 months, the middle rounds to 2 years).
    _fixture, _result, workspace, _originals = await shared(tmp_path_factory, 'F10-durations')
    assert views(workspace)['focus'] == ['ФОКУС', 'Python', '3 years', 'PostgreSQL', '4 года', 'Perl', '2 года', 'Docker', '4 года']
    # The computed text is shown, not stored as stated experience.
    stated = {record.display.raw_text: record.experience.raw_text for record in records(workspace, 'technology')
        if record.display.raw_text in {'PostgreSQL', 'Perl', 'Docker'} and record.job_id is None}
    assert stated and set(stated.values()) == {''}


@pytest.mark.asyncio
@pytest.mark.parametrize(('name', 'key', 'groups'), [('F10', 'F10-on', 2), ('F04', 'F04-on', 3)])
async def test_with_three_calls_at_once_the_projects_block_runs_in_groups_and_shows_what_the_whole_block_shows(
        tmp_path_factory, name, key, groups):
    # D117: the outline names every job, the jobs run in at most three groups beside the other blocks, and the document
    # is the one the sequential whole-block import publishes, F10's rejected result and F04's fifteen-year window too.
    _whole_fixture, whole, whole_workspace, _originals = await shared(tmp_path_factory, key)
    fixture, result, workspace, _originals = await generic_import(tmp_path_factory.mktemp(key + '-split'), name, rewrite=True,
        concurrency=3)
    assert result.state == 'published' and result.publication.state == 'saved'
    parent = next(task for task in result.tasks if task.block_id == 'projects' and task.parent_task_id is None)
    entries = [task for task in result.tasks if task.parent_task_id == parent.id and task.entry is not None]
    assert len(entries) == groups and [attempt.slot for attempt in result.attempts].count('outline') == 1
    assert sum(len(task.entry.parts) for task in entries) == len(TABLES[name](True)['projects'][0])
    assert views(workspace) == views(whole_workspace)
    assert sorted(record.employer.raw_text for record in records(workspace, 'employment')) == sorted(
        record.employer.raw_text for record in records(whole_workspace, 'employment'))
    assert [(issue.code, issue.rule_id) for issue in workspace.project.import_issues] == [
        (issue.code, issue.rule_id) for issue in whole_workspace.project.import_issues]
    # The outline and its review, then one call and one review per group, replace the block's call and review.
    assert spent_calls(result) == spent_calls(whole) - 2 + 2 + 2 * groups


@pytest.mark.asyncio
async def test_an_old_job_without_a_company_stays_in_the_document(tmp_path):
    table = TABLES['F10'](True)
    table['projects'][0][0]['company'] = None
    _fixture, _result, workspace, _originals = await generic_import(tmp_path, 'F10', rewrite=True, table=table)
    shown = views(workspace)
    assert 'other_projects' not in shown and '2006 – 2008' in shown['projects']


@pytest.mark.asyncio
async def test_an_generic_repair_without_item_refs_keeps_one_record_per_job_and_technology(tmp_path):
    def wrap(script):
        def wrapped(request, value):
            reply = script(request, value)
            if value.get('slot') != 'primary_repair':
                return reply
            for job in reply['payload']:
                job['results'] = []
            return {'schemaVersion': 3, 'payload': reply['payload'], 'discoveries': None, 'fields': [], 'lineage': None, 'relations': None}
        return wrapped
    _fixture, result, workspace, _originals = await generic_import(tmp_path, 'F10', wrap=wrap)
    assert 'primary_repair' in [attempt.slot for attempt in result.attempts]
    records = workspace.project.facts.records
    assert sorted(record.employer.raw_text for record in records if record.kind == 'employment') == ['Example Labs', 'Old Systems']
    owned = [(record.job_id, record.display.raw_text) for record in records if record.kind == 'technology' and record.job_id]
    assert len(owned) == len(set(owned)) == 4
    text = '\n'.join(getattr(part, 'text', '') for block in workspace.project.document.blocks() for part in block.content)
    assert text.count('Example Labs') == 1 and 'Old Systems, Old Systems' not in text
    assert not result.issues
