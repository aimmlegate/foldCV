"""Group extraction notices without losing affected sources and pages."""

from .models.rich_workspace import RichWarning


def source_warnings(sources):
    grouped = {}
    for source in sources:
        details = [(detail.code, detail.page) for detail in source.warning_details] or [(code, None) for code in source.warnings]
        for code, page in details:
            row = grouped.setdefault(code, {"id": "import-" + code, "code": code,
                "blockIds": [], "recordIds": [], "evidence": [], "count": 0, "locations": []})
            row["count"] += 1
            location = {"sourceId": source.id, "page": page}
            if location not in row["locations"]:
                row["locations"].append(location)
    return [RichWarning.model_validate(row) for row in grouped.values()]
