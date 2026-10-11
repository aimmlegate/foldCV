"""Document language controls headings across normal and continued pages."""

from xml.etree import ElementTree as ET
from zipfile import ZipFile

import pytest

from packages.resume_core.rendering.layout import render_docx


@pytest.mark.parametrize("language", ["ru", "en", "mixed"])
@pytest.mark.parametrize("long", [False, True])
def test_docx_headings_follow_document_language(tmp_path, language, long):
    data = {"source_language": language, "candidate": {"name": "Synthetic Person", "title": "Engineer", "summary": "Built services."},
            "focus": [{"label": "Python", "duration": "≈ 1 year", "icon": "python"}],
            "sidebar": [], "projects": [{"company": "Example Company", "period": "2020–2024", "stack": "Python",
                "description": "Built reliable services. " * (120 if long else 1), "role": "Engineer",
                "tasks": ["Maintained reliable services. " * (100 if long else 1)],
                "results": ["Reduced response latency. " * (100 if long else 1)]}],
            "achievements": ["Delivered the migration."], "skill_groups": [], "footer": ""}
    path = tmp_path / "localized.docx"
    render_docx(data, path)
    with ZipFile(path) as archive:
        root = ET.fromstring(archive.read("word/document.xml"))
    texts = [node.text for node in root.iter("{http://schemas.openxmlformats.org/wordprocessingml/2006/main}t")]
    russian = ["ФОКУС", "О СЕБЕ", "ПРОЕКТЫ", "Роль: Engineer", "Задачи:", "Личные результаты:", "Ключевые достижения:"]
    english = ["FOCUS", "ABOUT ME", "PROJECTS", "Role: Engineer", "Tasks:", "Personal results:", "Key achievements:"]
    expected, excluded = (russian, english) if language == "ru" else (english, russian)
    assert all(label in texts for label in expected)
    assert all(label not in texts for label in excluded)
    assert "".join(texts).count("Maintained reliable services.") == (100 if long else 1)
