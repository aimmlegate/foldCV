"""Separate usable extracted facts from bookkeeping and uncovered source content."""

from collections import Counter
import re

from .models.rich_facts import ExtractionIssue, ExtractionReport
from .source_dates import MONTH_PATTERN

SECTIONS = {
    "employment": r"(?:опыт\s+работы|профессиональный\s+опыт|employment(?:\s+history)?|work\s+experience|career\s+history)",
    "education": r"(?:образование|education)",
    "languages": r"(?:знание\s+языков|языки|languages)",
    "certifications": r"(?:сертификаты|сертификации|certifications|certificates)",
    "technology": r"(?:ключевые\s+навыки|технические\s+навыки|technical\s+skills|technologies)",
}

_DATE = rf"(?:(?:{MONTH_PATTERN})\.?\s+\d{{4}}|\d{{1,2}}[./]\d{{4}}|\d{{4}}(?:-\d{{2}})?)"
_DATED_RANGE = re.compile(rf"(?<!\w){_DATE}\s*(?:[—–-]|to|по)\s*"
    rf"(?:{_DATE}|present|current|настоящее\s+время|н\.?\s*в\.?)(?!\w)", re.I)
_OTHER_SECTION = "|".join([*[pattern for key, pattern in SECTIONS.items() if key != "employment"],
    r"(?:personal\s+)?projects?", r"личные\s+проекты", r"courses", r"курсы", r"about\s+me", r"о\s+себе"])


def section_heading(pattern, text):
    return re.fullmatch(rf"(?:{pattern})(?:\s*[:：].*|\s*[—–-]?\s*\d[\d\s\w.,-]*)?", text, re.I)


def has_dated_employment(sources):
    for source in sources:
        active, lines = False, []
        for unit in source.units:
            for line in unit.text.splitlines():
                text = " ".join(line.split())
                employment = section_heading(SECTIONS['employment'], text)
                if employment or section_heading(_OTHER_SECTION, text):
                    if active and _DATED_RANGE.search(" ".join(lines)):
                        return True
                    active = bool(employment) and not re.search(r"[:—–-]\s*(?:нет|none|no\s+experience)\s*$", text, re.I)
                    lines = []
                if active:
                    lines.append(text)
        if active and _DATED_RANGE.search(" ".join(lines)):
            return True
    return False


def extraction_report(result, *, request_bytes, recovered_rows):
    meaningful = [fact for fact in result.facts if fact.kind not in {"name_assessment", "source_observation"}
        and (fact.kind != "text" or fact.value.text.strip())
        and (fact.kind != "technology" or fact.value.display.strip())]
    if not meaningful:
        return None
    counts = dict(Counter(fact.kind for fact in meaningful))
    counts.update(employment=len(result.employment), education=len(result.education),
        languages=len(result.languages), certifications=len(result.certifications))
    covered = {(e.source_id, e.unit_id) for fact in meaningful for e in fact.evidence}
    issues = []
    for source in result.sources:
        for unit in source.units:
            text = " ".join(unit.text.split())
            if not text or unit.disposition in {"administrative", "duplicate"}:
                continue
            section = next((key for key, pattern in SECTIONS.items()
                if any(section_heading(pattern, line.strip()) for line in unit.text.splitlines())), None)
            page = unit.location.index + 1 if unit.location.kind == "page" else None
            if section and not counts.get(section):
                issues.append(ExtractionIssue(code="FACT_SECTION_OMITTED", sourceId=source.id, unitId=unit.id, page=page, section=section))
            elif (source.id, unit.id) not in covered and not (section and re.fullmatch(SECTIONS[section] + r"[\s:]*", text, re.I)):
                issues.append(ExtractionIssue(code="FACT_SOURCE_UNRESOLVED", sourceId=source.id, unitId=unit.id, page=page, section=section or "source"))
    if recovered_rows and len(issues) < 5000:
        issues.append(ExtractionIssue(code="FACT_ROWS_RECOVERED", sourceId=result.sources[0].id, unitId=None, section="provider_result"))
    return ExtractionReport(status="partial" if issues else "complete", factCount=len(meaningful), counts=counts,
        requestBytes=request_bytes, recoveredRows=recovered_rows, unresolved=issues[:5000])
