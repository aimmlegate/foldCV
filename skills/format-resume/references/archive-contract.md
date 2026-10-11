# Version 2: complete archive and selected view

Run `scripts/archive.py INPUT CASE_FOLDER --as-of YYYY-MM-DD` first. It saves the
original file, all extracted pages, stable source units, and an archive skeleton.
Do not edit `source`, `units`, `as_of`, or `source_snapshot`. A unit ID is a stable
source reference; use it directly instead of copying quotes or inventing IDs.

## Archive annotations

Complete these fields in `archive.json` without deleting any source data:

- `classifications`: an object keyed by unit ID (not an array), exactly one entry for every unit ID, with `category`,
  `importance` (`essential`, `supporting`, `administrative`), and `job_id`
  (a job ID or null). Categories: `identity`, `profile`, `job_header`, `period`,
  `role`, `task`, `result`, `stack`, `education`, `course`, `language`, `location`,
  `preferences`, `contacts`, `personal`, `meta`. Job-related units must have their
  correct job ID. Use the primary category when a unit contains several fields.
- `jobs`: every employment record, newest first. Each has `id`, `company`,
  `period`, `role` (statement objects), `start`, `end`, `observed_at`,
  `observed_sources`, and `technologies`.
  Normalized dates are YYYY-MM or YYYY; `end` is null for an ongoing job.
  `observed_at` is the source's as-of/update date, YYYY-MM-DD, with unit IDs in
  `observed_sources`. Null is allowed when absent; never silently assume today.
- `technologies` per job and `global_technologies`: complete sourced lists of
  `{name, sources}` objects. Preserve obscure tools, versions, methods, and
  project-specific qualifications here even when they are hidden in the PDF.
  Name each technology separately. A dated subproject may use optional `start`
  and `end` on its technology entry. When a technology belongs only to an undated
  subproject in a multi-project job, set `duration_eligible: false`. Do not use
  the whole employment period as its duration.

A statement is `{text: string, sources: [unit IDs]}`. Keep original dates and
grouped employment. Full duties, results, education, certificates, interests,
contacts, and preferences remain in the immutable source units with categories
and job links. This archive is the regeneration input; the PDF is only one view.

## Selected view

Use the existing data contract, with these additions:

- `schema_version: 2`; `evidence: {}` initially (filled deterministically).
- Each detailed project has `id` matching its archive job. Include all jobs that
  ended within the last 15 years, including jobs spanning the cutoff.
- `earlier_experience`: list of `{job_ids: [...], summary: statement}`. Fully old
  jobs go here as one short comma-separated paragraph: company, role, dates,
  broad area. Do not repeat full old stacks and duties. Every archive job must
  occur exactly once in detailed projects or earlier experience.
- `recent_project_ids`: the latest one or two job IDs that inform the profile.
  The summary must cite source units from those jobs and explain current domain,
  tasks, and strengths, supplementing the source profile when needed.
- `focus`: at most eight familiar technologies with available logos, in order of
  relevance to the latest work. Fewer are fine when evidence is limited. Supply
  `label`, `icon`, `duration: null`; `finalize.py` derives approximate experience
  from the archive. Do not choose a technology with no dated project evidence.
- `coverage`: an object keyed by source unit ID (not an array), each `{decision, reason}`. Decisions:
  `shown`, `condensed`, `archive_only`, `duplicate`, `metadata`. Give a specific
  reason for anything except `shown`. Shown/condensed units must be referenced
  by public text. Do not mark a unit shown merely because one unrelated field
  cites it; use condensed and explain any omitted parts.
- `archived_technologies`: `{name, reason}` entries for any archived technology
  intentionally absent from all displayed text. Prefer retaining technical
  details in grouped skill lists rather than discarding them.

For long stacks, write the statement with newline-separated groups, each in the
form `Основное: ...`, `Данные: ...`, `Инфраструктура: ...`, `Инструменты: ...`.
Order technologies by role relevance within each group. Keep the stack statement
source references. Group labels are presentation text, not new candidate facts.
Do the same within long global skill lists where useful. Avoid dumping unrelated
technologies into a single unsorted line.

Run `scripts/finalize.py VIEW_JSON ARCHIVE_JSON` to fill evidence, archive hash,
and focus durations. Then run `scripts/check_archive.py VIEW_JSON ARCHIVE_JSON`.
Fix every failure; never weaken a check to pass. Render with `render.py VIEW PDF
--source SOURCE_JSON --archive ARCHIVE_JSON`.

## Limits of the checks

The checks prove byte/text preservation, complete disposition accounting,
employment coverage, bounded focus size, reproducible duration calculations,
and selected numeric retention. A citation alone does not prove a paraphrase
keeps every meaning. Review semantic fidelity and the complete technology
inventory against the source separately; record unresolved issues honestly.
