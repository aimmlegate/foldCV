"""Technical Focus, grounded duration estimates and local logo provenance."""

from io import BytesIO
from pathlib import Path
from zipfile import ZipFile
import hashlib
import json

from lxml import etree

from packages.resume_core.models.rich_facts import WorkingFacts
from packages.resume_core.rendering.rich_docx import render_rich_docx
from packages.resume_core.rich_fields import set_text
from packages.resume_core.rich_mutations import apply_rich_mutation
from packages.resume_core.rich_panel import panel_mutation
from packages.resume_core.rich_presentation import presentation
from packages.resume_core.technologies import BY_ID, CATALOG, is_technical, logo_path, technology_identity
from packages.resume_core.technology_experience import technology_experience
from tests.facts.panel_fixtures import edit, job, technology_facts
from tests.support.rich import without_sources

ROOT = Path(__file__).resolve().parents[2]


def test_focus_requires_a_known_icon_and_keeps_unshown_technologies_as_facts():
    facts, doc = technology_facts([{"kind": "technology", "display": "Командная работа"},
        {"kind": "technology", "display": "Python", "technical": False},
        {"kind": "technology", "display": "NovelEngine", "technical": True},
        {"kind": "technology", "display": "Ansible"}, {"kind": "technology", "display": "SQL"}])
    focus = doc.regions[1].blocks[0]
    assert [b.content[0].text for b in focus.children] == ["Ansible", "SQL"]
    roles = presentation(doc, facts).blocks
    assert roles[focus.children[0].id].logo == "assets/technology-library/ansible.png"
    assert roles[focus.children[1].id].logo == "assets/technology-library/sql.png"
    assert len(facts.records) == 5
    assert not is_technical(facts.records[0])


def test_exposure_unions_overlapping_jobs_and_aliases_without_filling_gaps():
    facts, _ = technology_facts([job("2020-01", "2021-12", "Postgres"), job("2021-01", "2022-12", "PostgreSQL"),
        job("2024-01", "2024-12", "PostgreSQL"), {"kind": "technology", "display": "PostgreSQL"}])
    text, note = technology_experience(facts)["postgresql"]
    assert text == "≈ 4 года"
    assert "пересечения объединены" in note
    assert all(technology_identity(r) == "postgresql" for r in facts.records if r.kind == "technology")


def test_partial_year_bounds_and_open_periods_never_assume_today():
    facts, _ = technology_facts([job("2020", "2022")])
    assert technology_experience(facts)["python"][0] == "≈ 1 год – 3 года"
    facts, _ = technology_facts([job("2020-01", "2021-12"), job("2022-01", "настоящее время", present=True)])
    text, note = technology_experience(facts)["python"]
    assert text == "≈ 2 года+"
    assert "не включены" in note
    facts, _ = technology_facts([job("2022-01", "настоящее время", present=True),
        {"kind": "technology", "display": "SQL"}])
    assert technology_experience(facts)["python"][0] == "Срок не указан"
    assert technology_experience(facts)["sql"][0] == "Срок не указан"


def test_stated_qualified_experience_wins_is_editable_and_exports_the_same_label():
    facts, doc = technology_facts([job("2020-01", "2021-12"),
        {"kind": "technology", "display": "Python", "experience": "Более 5 лет", "technical": True}])
    selected = next(r for r in facts.records if r.kind == "technology" and r.job_id is None)
    assert technology_experience(facts)["python"][0] == "Более 5 лет"
    set_text(selected, "experience", "Около 6 лет")
    labels = [v.experience for v in presentation(doc, facts).blocks.values() if v.role == "focus_entry"]
    assert labels == ["6 years"]
    with ZipFile(BytesIO(render_rich_docx(doc, facts=facts))) as archive:
        xml = etree.fromstring(archive.read("word/document.xml"))
        assert "6 years" in xml.xpath("//w:t/text()", namespaces={"w": "http://schemas.openxmlformats.org/wordprocessingml/2006/main"})
    assert WorkingFacts.model_validate_json(facts.model_dump_json(by_alias=True)).records == facts.records


def test_conflicting_durations_and_legacy_serialization_are_retained():
    facts, _ = technology_facts([{"kind": "technology", "display": "Python", "experience": "3 years"},
        {"kind": "technology", "display": "Python", "experience": "over 5 years"}])
    label, note = technology_experience(facts, False)["python"]
    assert label == "Conflicting durations" and "3 years; over 5 years" in note
    facts, _ = technology_facts([{"kind": "technology", "display": "Python"}])
    value = facts.records[0].model_dump(by_alias=True)
    assert "experience" not in value and "technical" not in value


def test_every_catalog_logo_is_local_and_downloaded_assets_match_pinned_sources():
    for entry in CATALOG:
        path = logo_path(entry)
        assert path is None or (ROOT / path).is_file(), entry.canonical_id
    library = ROOT / "assets/technology-library"
    source = json.loads((library / "upstream.json").read_text())
    assert len(source["revision"]) == 40 and "MIT" in (library / "LICENSE").read_text()
    for name, item in json.loads((library / "sources.json").read_text()).items():
        revision = item.get("revision", source["revision"])
        assert revision is None or revision in item["url"]
        original = library / item.get("sourceFile", name + ".svg")
        assert hashlib.sha256(original.read_bytes()).hexdigest() == item.get("sourceSha256", item.get("svgSha256"))
        assert hashlib.sha256((library / f"{name}.png").read_bytes()).hexdigest() == item["pngSha256"]
    assert BY_ID["sql"].logo is not None


def test_panel_experience_edit_refreshes_focus_without_rewriting_source_or_technology_name():
    facts, doc = technology_facts([{"kind": "technology", "display": "Python"}])
    workspace = without_sources()
    workspace.project.document, workspace.project.facts = doc, facts
    workspace.project.evidence_records = []
    sources = workspace.project.sources.copy()
    record = facts.records[0]
    mutation = panel_mutation(workspace, edit(workspace, recordId=record.id, values={"experience": "Более 4 лет"}))
    changed, *_ = apply_rich_mutation(workspace, mutation)
    assert changed.project.sources == sources
    assert changed.project.facts.records[0].display.raw_text == "Python"
    assert changed.project.facts.records[0].experience.user_corrected
    roles = presentation(changed.project.document, changed.project.facts).blocks
    assert [r.experience for r in roles.values() if r.role == "focus_entry"] == ["4 years"]


def test_invalid_and_undated_links_do_not_become_zero_or_inflate_experience():
    facts, _ = technology_facts([job("2022-12", "2020-01"), job("around 2010", "2018"),
        {"kind": "employment", "employer": "Unknown dates", "technologies": ["Python"]}])
    assert technology_experience(facts)["python"][0] == "Срок не указан"
    assert len(facts.records) == 6


def test_job_technology_metadata_keeps_its_owner_and_stated_duration_without_catalog_or_image():
    facts, doc = technology_facts([{"kind": "employment", "employer": "Orion", "technologies": [
        {"display": "NovelEngine", "technical": True, "experience": "Около 2 лет"}, "Python"]}])
    employment = next(r for r in facts.records if r.kind == "employment")
    technology = next(r for r in facts.records if r.kind == "technology" and r.display.raw_text == "NovelEngine")
    assert technology.job_id == employment.id and technology.canonical_id.value is None
    assert is_technical(technology)
    assert not any(v.experience == "Около 2 лет" for v in presentation(doc, facts).blocks.values())
    assert all(entry.display != "NovelEngine" for entry in presentation(doc, facts).focus_entries)


def test_pending_source_duration_does_not_fall_back_to_a_stale_statement_or_estimate():
    facts, _ = technology_facts([job("2020-01", "2021-12"),
        {"kind": "technology", "display": "Python", "experience": "5 лет"}])
    field = next(r.experience for r in facts.records if r.kind == "technology" and r.job_id is None)
    field.status, field.pending_raw_text = "pending", "Несколько лет"
    text, note = technology_experience(facts)["python"]
    assert text == "Срок требует проверки" and note == "Несколько лет"


def test_all_ten_focus_entries_can_use_normalized_images_without_an_eight_logo_cutoff():
    from PIL import Image
    labels = ['Python', 'Linux', 'Docker', 'Git', 'Ansible', 'Jenkins', 'Terraform', 'Kubernetes', 'Prometheus', 'Gitlab']
    facts, doc = technology_facts([{'kind': 'technology', 'display': name} for name in labels])
    views = [v for v in presentation(doc, facts).blocks.values() if v.role == 'focus_entry']
    assert len(views) == 10 and all(v.logo for v in views)
    for entry in CATALOG:
        with Image.open(ROOT / logo_path(entry)) as image:
            assert image.size == (192, 192) and image.mode == 'RGBA'
            x0, y0, x1, y1 = image.getchannel('A').getbbox()
            assert x0 >= 10 and y0 >= 10 and x1 <= 182 and y1 <= 182
    for name in ['grpc', 'jooq']:
        with Image.open(ROOT / 'assets/technology-library' / (name + '.png')) as image:
            paper = Image.new('RGBA', image.size, 'white')
            paper.alpha_composite(image)
            ink = paper.convert('L').point(lambda value: 0 if value < 128 else 255)
            assert ink.histogram()[0] > 500
