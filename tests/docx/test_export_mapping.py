"""Current export labels, authored order and legacy/multiline OOXML mapping."""

import pytest
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / 'services/api/src'))

from packages.resume_core.gui_refresh import refresh
from packages.resume_core.gui_rendering import render_input
from packages.resume_core.models.recovery import CertificationRecord
from tests.recovery.generation_fixtures import render_workspace
from tests.docx.test_gui_docx import write, W


@pytest.mark.parametrize('language', ['ru', 'en', 'mixed'])
def test_each_empty_required_string_uses_only_localized_render_labels(language, tmp_path):
    workspace = render_workspace();workspace.editorial_plan.source_language = language
    document = workspace.project.document
    for field in [document.candidate.name, document.candidate.title, document.jobs[0].employer, document.jobs[0].role]:
        field.text = ''
    document.jobs[0].periods = []
    facts = [fact.model_dump() for fact in workspace.project.facts]
    rendered, xml, _ = write(workspace, tmp_path/'render')
    expected = ['Имя не указано','Должность не указана','Компания не указана','не указана','Даты не указаны'] if language == 'ru' else [
        'Name not specified','Title not specified','Company not specified','not specified','Dates not specified']
    assert [rendered.candidate.name, rendered.candidate.title, rendered.projects[0].company, rendered.projects[0].role, rendered.projects[0].period] == expected
    text = ' '.join(xml.itertext());prefix = 'Роль: ' if language == 'ru' else 'Role: '
    assert prefix + expected[3] in text and prefix + prefix not in text
    assert all(field.text == '' for field in [document.candidate.name, document.candidate.title, document.jobs[0].employer, document.jobs[0].role])
    assert [fact.model_dump() for fact in workspace.project.facts] == facts


def test_multiple_partial_present_periods_and_incomplete_exposure_export_verbatim(tmp_path):
    workspace = render_workspace();job = workspace.project.document.jobs[0]
    first = job.periods[0];first.start_text.text, first.end_text.text, first.present = '2017-03', '2020-02', False
    second = first.model_copy(deep=True);second.id = 'second'
    second.start_text.field_id = f'job:{job.id}/period:second/startText';second.end_text.field_id = f'job:{job.id}/period:second/endText'
    second.start_text.text, second.end_text.text, second.present = '2021-06-15', '', True
    job.periods.append(second);refresh(workspace, ['job:'+job.id])
    rendered, xml, _ = write(workspace, tmp_path/'render')
    assert rendered.projects[0].period == '2017-03–2020-02, 2021-06-15–н. в.'
    assert rendered.projects[0].period in ''.join(xml.itertext())
    assert all(entry.duration == '' for entry in rendered.focus) and workspace.source_observed_at is None
    first.start_text.text = 'unresolved start';refresh(workspace, ['job:'+job.id])
    assert render_input(workspace)[0].projects[0].period.startswith('unresolved start–2020-02')


def test_all_authored_sections_order_hidden_rows_and_legacy_text_keep_actual_word_breaks(tmp_path):
    workspace = render_workspace();workspace.editorial_plan.source_language = 'mixed';workspace.editorial_plan.profile_language = 'ru'
    doc = workspace.project.document;doc.candidate.location.text = 'Remote location'
    doc.education[0].institution.text = 'University\n\nFaculty'
    def field(key, text=''):
        return {'fieldId':'certification:certificate/'+key,'text':text,'factIds':[],'evidence':[],'origin':'user'}
    doc.certifications.append(CertificationRecord.model_validate({'kind':'certification','id':'certificate','revision':1,'visible':True,
        'name':field('name','Course\n\nPart two'),'issuer':field('issuer','Institute'),'dateText':field('dateText','2020'),'legacyText':None}))
    doc.languages[0].name.text, doc.languages[0].proficiency.text = 'English', ''
    doc.skills_focus.skills_text.text, doc.early_career.text.text = 'Python\n\nSQL', 'Early\n\nCareer'
    focus = doc.skills_focus.focus[0].model_copy(deep=True);focus.id, focus.catalog_id = 'custom-postgres','postgresql'
    focus.display.field_id, focus.display.text, focus.fact_ids = 'skills-focus/focus:custom-postgres/display','Custom Postgres',[]
    doc.skills_focus.focus.insert(0, focus);refresh(workspace, ['skills-focus'])
    rendered, xml, _ = write(workspace, tmp_path/'render')
    assert [section.title for section in rendered.sidebar] == ['LOCATION','EDUCATION','CERTIFICATIONS','LANGUAGES','EARLY CAREER']
    assert rendered.sidebar[3].items == ['English','английский — B2'] and rendered.candidate.summary == doc.profile.text.text
    assert rendered.skill_groups[0].title == 'SKILLS' and rendered.skill_groups[0].items == 'Python\n\nSQL'
    assert [entry.label for entry in rendered.focus][:2] == ['Custom Postgres',doc.skills_focus.focus[1].display.text]
    assert rendered.projects[0].description == doc.jobs[0].context.text
    assert rendered.projects[0].tasks == [line for line in doc.jobs[0].tasks.text.split('\n') if line.strip()]
    assert rendered.projects[0].results == [line for line in doc.jobs[0].results.text.split('\n') if line.strip()]
    for text in ['University\n\nFaculty','Course\n\nPart two','Python\n\nSQL','Early\n\nCareer']:
        assert any(text.replace('\n','') in ''.join(paragraph.itertext()) and len(paragraph.findall('.//w:br',W)) >= 2 for paragraph in xml.findall('.//w:p',W))
    for collection in [doc.languages, doc.education, doc.certifications]:
        for row in collection:row.visible = False
    doc.early_career.visible = False;doc.skills_focus.visible = False
    hidden = render_input(workspace)[0]
    assert [section.title for section in hidden.sidebar] == ['LOCATION'] and hidden.focus == hidden.skill_groups == []
    from tests.recovery.test_gui_mutations import new_record
    row = new_record(workspace,'education','legacy');row.legacy_text = row.institution.model_copy(update={'field_id':'education:'+row.id+'/legacyText','text':'Legacy education\n\nSecond line'})
    row.visible = True
    row.institution.text = '';row.qualification.text = '';row.specialty.text = '';row.date_text.text = '';doc.education.append(row)
    legacy = render_input(workspace)[0]
    assert legacy.sidebar[1].items == ['Legacy education\n\nSecond line'] and legacy.sidebar[1].title == 'EDUCATION'
