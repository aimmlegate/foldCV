# Resume data in Git

Keep real resume inputs, extracted text, facts, project dumps, exports and candidate
screenshots local. Use `experiments/` or `.private/`; both are ignored. This also
applies to QA evidence. Publish technical summaries, counters and source code
without candidate identifiers or contacts.

Use synthetic data for committed fixtures. Keep document fixtures under
`tests/fixtures/synthetic/` and synthetic contract examples under
`contracts/examples/`. Branding and technology logos are public assets.

Enable the repository checks with `git config core.hooksPath .githooks`.
The commit hook scans staged blobs. The push hook scans every blob reachable
from each outgoing tip, including old commits. Both reject private artifact
paths and serialized resume workspaces. Local candidate indicators are read
from the ignored `.private/resume-qa/indicators.json` when available; values are
never printed in failure messages.

Run `.venv/bin/python tools/check_private_resume_data.py` before a commit and
add `--history` to check the current branch history. Do not bypass a failed
privacy check. Move real data outside Git and keep a synthetic regression case.

Deleting a file in a later commit leaves the earlier version in Git history.
Prepare a filtered local copy and verify it before replacing published history.
Keep originals in private local storage. Published history replacement needs
explicit approval and an exact force-with-lease against the previously verified
remote tip. Host caches and old clones require separate handling; a successful
history rewrite alone does not prove those copies are erased.

## Local-only project files

Plans, handoffs, prompts, review records, research notes, reports and the design
prototype are not published. `.gitignore` excludes `docs/gui/*`, `reports/`,
`research_notes/` and `design/future-editor/*`, and lists the published documents and
`design/future-editor/visual/` as exceptions. To publish a new document, add it to
that list.

These files exist only in the main checkout, so new clones and worktrees do not have
them. Git does not protect ignored files. Checking out an older commit and returning
deletes the files that commit tracked, and `git clean -x` deletes all of them.
