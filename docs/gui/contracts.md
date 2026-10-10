# Version 3 contracts

`packages/resume_core/models/contracts.py` is the authority for the wire shape.
`contracts/json-schema/*.schema.json` and `apps/web/src/contracts/generated/*.ts`
are generated from it. Wire keys use camelCase. Python attributes use snake_case.
Both runtimes reject unknown fields. The JSON Schemas check structure; the Python
model validators and `apps/web/src/contracts/validate.ts` also check relationships,
date precision and ordering, metric ranges, operation scope, and safe ZIP paths.

`schemaVersion: 3` is the first complete project contract. It is an integer major
version and is unrelated to the experiment's `schema_version: 2`. A project or
ZIP manifest with any other version is rejected. No implicit fallback or
reinterpretation is allowed. A changed wire field or meaning requires a new
major version and an explicit migration. Template package versions and content
policy versions are separate from the project contract version.

The v2 migration belongs to T14. It must preserve original bytes, extracted
units, and the old accepted view; mark unstructured content as needing
normalization; and save a new v3 archive separately. Reopening that view must
not start generation. Fact-aware rewriting waits for explicit normalization.

A partial v3 project can have no facts, jobs, blocks, template, or renders.
`asOf: null` records that no observation date was given, so duration is omitted
until an operator supplies one. Source original-byte references and extraction
remain in the project. An imported project may contain stale blocks or proposals;
their base revisions prevent silent application. Fact IDs stay stable when a
manual value edit increments the fact revision. Source edits are overlays;
original units remain unchanged. Source facts require current evidence references.
User facts carry `origin: "user"` and no fabricated source evidence.

Unit representation, evidence, job membership, and subproject membership must
agree in both directions. Saved block, review, render, and operation revisions
may refer to historical state but never to a future revision. The ZIP has
exactly one project-role entry, at `project.json`.

Proposals replace only one prose block's text, identified by block ID, base
revision, and dependency hash. Arbitrary patch paths are invalid. Only
`normalize_semantics`, `draft_prose`, and `rewrite_prose` are model operation
kinds. Usage records logical attempts separately from nullable internal request
counts and nullable reported tokens. Unknown usage is `null`, never zero.

The ZIP manifest lists entry paths, roles, SHA-256 hashes, and uncompressed
sizes. Current contract validation rejects duplicate or unsafe paths. T14 must
verify archive bytes, sizes, hashes, symlinks, and expansion limits before
loading a project. SHA-256 here detects corruption; it does not prove authorship.

Run from the repository root with Python 3.13 and Node 22.14.0:

```sh
.venv/bin/python -m pytest tests/contracts -q
cd apps/web
npm run contracts:check
npm run test:contracts
npm run typecheck
npm run lint
```

`contracts/examples/cases.json` is the shared list of independent expected
results. Both runners apply each edit to the same synthetic base data. T01 covers
structural and reference safety; it does not prove that generated prose is true.
