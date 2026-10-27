"""Technology identity, display and selection for the prepared render document."""

import copy
import json
from pathlib import Path

from packages.resume_core.models.contracts import Project
from packages.resume_core.selection import _latest_jobs, early_career_rows, format_early_career, group_technologies, select_focus
from packages.resume_core.technologies import resolve_technology


EXAMPLE = json.loads((Path(__file__).resolve().parents[2] / "contracts/examples/project.json").read_text())


def with_skills() -> Project:
    data = copy.deepcopy(EXAMPLE)
    for tech_id, display, scope, job in (
        ("python", "Python 3.11", "job", "job_2"),
        ("dotnet", ".NET Core 8", "job", "job_1"),
        ("rust", "Rust 1.75", "global", None),
    ):
        fact = copy.deepcopy(data["facts"][1])
        fact["id"] = f"skill_{tech_id}"
        fact["value"] = {"canonicalId": tech_id, "display": display, "scope": scope}
        fact["jobId"] = job
        data["facts"].append(fact)
        if job:
            next(item for item in data["employment"] if item["id"] == job)["factIds"].append(fact["id"])
    return Project.model_validate(data)


def test_catalog_alias_versions_and_ambiguous_names_keep_display() -> None:
    for text, expected in (("Python 3.11", "python"), ("Microsoft .NET Core 8", "dotnet"),
                           ("Apache Kafka 3.7", "kafka"), ("Go (Golang)", "golang"),
                           ("Go 1.22", "golang")):
        resolved = resolve_technology(text)
        assert resolved.canonical_id == expected
        assert resolved.display == text
    assert resolve_technology("Python 3.11").version == "3.11"
    assert resolve_technology("Go").status == "ambiguous"
    assert resolve_technology("DRF").status == "ambiguous"
    unknown = resolve_technology("ObscureTool 2.0")
    assert unknown.status == "unknown" and unknown.display == "ObscureTool 2.0"


def test_focus_uses_logos_priority_stable_ties_and_excludes_global_only() -> None:
    project = with_skills()
    logos = {"devicon/python.png", "devicon/dotnet.png", "images/golang.png"}
    focus = select_focus(project, logos, {"dotnet": 0, "python": 1})
    assert [item.canonical_id for item in focus] == ["dotnet", "python"]
    assert focus[1].display == "Python 3.11"
    assert focus[1].experience is not None  # The job-linked Python fact supports exposure.
    assert [item.canonical_id for item in select_focus(project, logos, explicit_order=("python",))] == ["python", "dotnet"]
    assert [item.canonical_id for item in select_focus(project, logos)] == ["python", "dotnet"]
    assert select_focus(project, logos) == select_focus(project, logos)
    assert len(select_focus(project, logos, limit=1)) == 1
    assert [item.canonical_id for item in select_focus(project, {"devicon/python.png"})] == ["python"]
    global_only = Project.model_validate(EXAMPLE)
    only = select_focus(global_only, logos)
    assert only == ()
    assert "Python" in group_technologies(global_only)["language"]
    undated = project.model_dump(by_alias=True)
    undated["employment"][1]["periods"] = []
    undated_project = Project.model_validate(undated)
    undated_focus = select_focus(undated_project, logos)
    python = next(item for item in undated_focus if item.canonical_id == "python")
    assert python.experience is None


def test_focus_is_capped_at_eight_with_stable_catalog_tie_break() -> None:
    data = copy.deepcopy(EXAMPLE)
    names = ("golang", "python", "csharp", "cplusplus", "dotnet", "postgresql", "redis", "kafka", "rabbitmq")
    logos = {"images/golang.png", "devicon/python.png", "devicon/csharp.png", "devicon/cplusplus.png",
             "devicon/dotnet.png", "images/postgresql.png", "images/redis.png", "images/kafka.png",
             "images/rabbitmq.png"}
    for name in names:
        fact = copy.deepcopy(data["facts"][1])
        fact["id"] = f"job_{name}"
        fact["value"].update(canonicalId=name, display=name, scope="job")
        fact["jobId"] = "job_2"
        data["facts"].append(fact)
        data["employment"][1]["factIds"].append(fact["id"])
    focus = select_focus(Project.model_validate(data), logos)
    assert len(focus) == 8
    assert [item.canonical_id for item in focus] == sorted(names)[:8]


def test_focus_recent_jobs_cap_future_ends_at_observation() -> None:
    data = copy.deepcopy(EXAMPLE)
    data.update(sources=[], facts=[], employment=[], views=[], proposals=[], renders=[],
                review={"decisions": [], "acknowledgments": []})

    def year(value: int) -> dict[str, int | str | None]:
        return {"precision": "year", "year": value, "month": None, "day": None}

    for job_id, tech_id, start, end in (
        ("long", "golang", 2000, None),
        ("middle", "python", 2022, 2023),
        ("new", "dotnet", 2024, 2025),
    ):
        fact = copy.deepcopy(EXAMPLE["facts"][1])
        fact.update(id=f"tech_{job_id}", jobId=job_id,
                    value={"canonicalId": tech_id, "display": tech_id, "scope": "job"})
        job = copy.deepcopy(EXAMPLE["employment"][1])
        job.update(id=job_id, periods=[{"start": year(start), "end": year(end) if end else None}],
                   subprojects=[], factIds=[fact["id"]])
        data["facts"].append(fact)
        data["employment"].append(job)

    logos = {"images/golang.png", "devicon/python.png", "devicon/dotnet.png"}
    project = Project.model_validate(data)
    assert _latest_jobs(project) == {"long", "new"}
    assert [item.canonical_id for item in select_focus(project, logos)] == ["golang", "dotnet", "python"]

    data["asOf"] = None
    undated = Project.model_validate(data)
    assert _latest_jobs(undated) == {"middle", "new"}
    assert [item.canonical_id for item in select_focus(undated, logos)] == ["dotnet", "python", "golang"]
    assert all(item.experience is None for item in select_focus(undated, logos))

    data["asOf"] = copy.deepcopy(EXAMPLE["asOf"])
    data["employment"][0]["periods"][0]["end"] = year(2030)
    data["employment"][1]["periods"][0]["end"] = None
    data["employment"][2]["periods"][0]["end"] = None
    future_end = Project.model_validate(data)
    assert _latest_jobs(future_end) == {"middle", "new"}
    assert [item.canonical_id for item in select_focus(future_end, logos)] == ["python", "dotnet", "golang"]


def test_latest_jobs_partial_dates_and_ties_are_stable() -> None:
    data = copy.deepcopy(EXAMPLE)
    data.update(sources=[], facts=[], employment=[], views=[], proposals=[], renders=[],
                review={"decisions": [], "acknowledgments": []}, asOf=None)
    year_2020 = {"precision": "year", "year": 2020, "month": None, "day": None}
    year_2025 = {"precision": "year", "year": 2025, "month": None, "day": None}
    october_2025 = {"precision": "month", "year": 2025, "month": 10, "day": None}
    for job_id, end in (("partial", year_2025), ("alpha", october_2025), ("beta", october_2025)):
        job = copy.deepcopy(EXAMPLE["employment"][1])
        job.update(id=job_id, periods=[{"start": year_2020, "end": end}], subprojects=[], factIds=[])
        data["employment"].append(job)
    assert _latest_jobs(Project.model_validate(data)) == {"alpha", "beta"}
    data["employment"].reverse()
    assert _latest_jobs(Project.model_validate(data)) == {"alpha", "beta"}


def test_unknown_and_versioned_skills_are_grouped_without_changing_facts() -> None:
    project = with_skills()
    before = project.model_dump()
    groups = group_technologies(project)
    assert "Rust 1.75" in groups["language"]
    assert ".NET Core 8" in groups["framework"]
    assert "Python 3.11" in groups["language"]
    assert project.model_dump() == before


def test_manual_global_skill_uses_catalog_group_without_dated_focus() -> None:
    data = copy.deepcopy(EXAMPLE)
    skill = copy.deepcopy(data["facts"][1])
    skill.update(id="manual-python", origin="user", evidence=[], jobId=None, subprojectId=None)
    skill["value"].update(canonicalId="unknown_user_0", display="Python 3.11", scope="global")
    data["facts"].append(skill)
    project = Project.model_validate(data)
    assert "Python 3.11" in group_technologies(project)["language"]
    assert all(item.canonical_id != "unknown_user_0" for item in select_focus(project, {"devicon/python.png"}))


def test_early_career_uses_exact_cutoff_and_approved_labels() -> None:
    data = copy.deepcopy(EXAMPLE)
    data["employment"][0]["periods"][0]["end"] = {"precision": "day", "year": 2011, "month": 10, "day": 9}
    data["employment"][0]["periods"][0]["start"] = {"precision": "year", "year": 2005, "month": None, "day": None}
    data["employment"][0]["subprojects"] = []
    data["facts"][0]["subprojectId"] = None
    project = Project.model_validate(data)
    rows = early_career_rows(project.employment, project.as_of, {"job_1": ("Payments",)})
    assert len(rows) == 1
    assert (rows[0].employer, rows[0].role, rows[0].labels) == ("Example One", "Engineer", ("Payments",))
    assert rows[0].periods == ("2005–2011-10-09",)
    assert format_early_career(rows[0]) == "Example One — Engineer (2005–2011-10-09): Payments"
