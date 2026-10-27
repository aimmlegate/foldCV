"""Import draft models (models.importing) kept in stored workspaces: a fact needs text or a meaningful record."""

from pydantic import ValidationError
import pytest

from packages.resume_core.models.importing import ImportFact


@pytest.mark.parametrize("record", [None, {"kind": "employment"}, {"kind": "education"}, {"kind": "language", "language": "  "}])
def test_import_fact_needs_meaningful_content(record):
    with pytest.raises(ValidationError):
        ImportFact(id="fact", text=" \n", record=record)
    assert ImportFact(id="fact", text="Retained note", record=record).text == "Retained note"
