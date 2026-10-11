# FoldCV

Original file → complete archive → selected resume JSON → fixed Generic PDF.

The supplied outputs define the layout, not the candidate's facts. The skill
handles extraction and rewriting; Python checks preservation and renders the
layout. No provider API or model benchmark is implemented yet.

The planned local browser application is described in
[the GUI implementation handoff](docs/gui/README.md), with an interactive
wireframe, CLI subscription integration, and explicit code/model boundaries.
These files are a design, not an implemented application.

## Setup

```sh
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements.txt
```

## Run

```sh
.venv/bin/python skills/format-resume/scripts/archive.py INPUT.pdf experiments/case --as-of 2026-10-10
```

Apply [the skill](skills/format-resume/SKILL.md) to every source unit. Complete
`archive.json` and create `view.json` using the
[archive contract](skills/format-resume/references/archive-contract.md). Keep
original bytes and extracted text unchanged. Do not supply reference candidate
facts to this step. Then run:

```sh
.venv/bin/python skills/format-resume/scripts/finalize.py experiments/case/view.json experiments/case/archive.json
.venv/bin/python skills/format-resume/scripts/check_archive.py experiments/case/view.json experiments/case/archive.json
.venv/bin/python skills/format-resume/scripts/render.py experiments/case/view.json output/pdf/resume.pdf --source experiments/case/source.json --archive experiments/case/archive.json
```

Render the resulting PDF to images and inspect every page before delivery.
The render command runs the archive checks before writing a version 2 PDF.
For another presentation, create a new view from the full archive, never from
the shortened PDF. Keep each accepted archive version with its matching view.

## Preservation and checks

- Keep original bytes, full page text, stable source units, all employment, and
  sourced technology catalogs, including details excluded from the PDF.
- Give every source unit a disposition and every omission a reason. A partly
  represented unit is condensed, not fully shown.
- Recheck the source hash and freshly extracted text. Reject missing coverage,
  missing jobs, unsupported dates, altered duration estimates, and lost numeric
  markers in essential recent duties/results.
- Limit focus to eight known technologies with logos. Estimate experience by
  merging dated project periods; bound current jobs by the source observation
  date. Global skills and undated subprojects do not establish duration.
- Focus the profile on recent projects, group long technology lists, and shorten
  jobs wholly older than 15 years into a comma-separated early-career paragraph.

These checks establish preservation and accounting, not semantic completeness.
Source classification and importance still need review. A cited paragraph can
contain several facts; a rewrite may retain its numbers while losing ownership,
qualifiers, or context. Check these against the complete source before delivery.
Experience estimates describe project exposure, not continuous full-time use.

```sh
.venv/bin/python -m unittest discover -s skills/format-resume/tests -v
```

## Current scope

- PDF with extractable text, TXT, and Markdown inputs. Other formats and scans
  need a separate extraction or OCR step.
- One fixed PDF layout with the supplied logo, reference technology icons,
  additional Devicon icons, and Source Sans Pro fonts. Unknown technologies are
  excluded from focus but can remain in project and global skill lists.
- Source-linked candidate statements and a separate review list.
- Private data and generated files stay in ignored `experiments/`, `tmp/`, and
  `output/` folders. The reusable skill contains no candidate records.

The latest trial is in `experiments/luna-batch-02/`, with PDFs under
`output/pdf/luna-v2/`. Earlier trials remain intact. These examples informed the
rules and received editorial corrections, so they are not a held-out quality
benchmark. Private artifacts are not committed.
