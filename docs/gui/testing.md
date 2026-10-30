# Test strategy

> One bounded run per suite (D109).

## Commands

From the repository root:

```sh
# Default run: one process; pytest.ini leaves out the slow tests.
PYTHONPATH=services/api/src .venv/bin/python -m pytest -q -p no:cacheprovider

# Slow tests only: scripted full imports and real document conversions.
PYTHONPATH=services/api/src .venv/bin/python -m pytest -q -p no:cacheprovider -m slow
```

Client, in `apps/web` with the arm64 Node 22 from nvm:

```sh
export PATH="$HOME/.nvm/versions/node/v22.14.0/bin:$PATH"
npm run test:state
npm run typecheck && npm run lint && npm run build
npm run contracts:check
```

- `pytest.ini`: `testpaths = tests skills/format-resume/tests`, `addopts = --strict-markers
  --strict-config -m "not slow"`. A `-m slow` on the command line wins. `slow` is the only
  marker.
- Without `PYTHONPATH=services/api/src`, modules that import `resume_api` do not collect.
  There is no pytest-xdist; the run is one process. Add `--durations=25` to see the slowest
  tests; pass paths for a focused run.
- The slow conversions need the pinned LibreOffice (`tools/install-local-renderer.sh`, macOS
  arm64, installs into `.tools/`).
- The default run needs neither `.tools/` nor `apps/web/dist`, and passes on any host: the
  readiness tests stub the host, frontend and renderer. `tools/run-local.py --check` checks
  the real machine.
- `test:state` runs `node --test` with `tsx` over `apps/web/unit/*.test.ts` with the default
  reporter and coverage for `src/assistant` and `src/rich`.
- Every client change runs `typecheck`, `lint`, `build` and `test:state`; every contract change
  runs `contracts:generate` and `contracts:check` ([contracts.md](contracts.md)).
- Do not edit `packages/resume_core/*.py` while a run is going: the DOCX renderer identity
  hashes those sources, so a later render in the same run fails with `RENDERER_MISMATCH`.
  Other paths are safe once collection has finished.
- macOS has no `timeout`; wait for a background run with a bounded polling loop.

## Budgets

Gates, measured on this machine and reported, not tuned past:

| Run | Budget | Measured at `405b9d06` (2026-10-27) |
|---|---|---|
| default `pytest` | 10 min wall | 511 s, 2 462 passed, 39 deselected |
| `pytest -m slow` | 15 min wall | 835 s, 39 passed |
| `npm run test:state` | 2 min wall | 32 s, 234 passed |

If the kept domain tests alone exceed a budget, report the numbers; never delete domain tests
to fit. Known failures at `405b9d06`: `tests/templates/test_identity.py` collision regex case
and the flaky `test_template_pipeline.py::test_two_findings_on_an_admitted_block_are_one_notice`.
`tests/assistant/test_agent_mcp.py` has one xfail (SDK argument errors echo input values).

## Guards

- The root `conftest.py` blocks `socket.connect`, `connect_ex` and `socket.create_connection`
  in every test; a call raises `AssertionError`. It also sets `FOLDCV_VERIFY=1`: the repository
  checks that `build` did not change the committed workspace, decodes the written bytes and
  compares them with memory, and rechecks response snapshots and cache hits. A mismatch is a
  failure, never a fallback.
- `tests/conftest.py` resets the process-wide settings limits and inference permit after each
  test and provides `frozen_clock`, `temp_root` (a temporary root whose name holds spaces,
  quotes and Cyrillic) and `fixture_random`.
- Data roots: every test uses `tmp_path` or `temp_root`, and every app, launcher or store a test
  starts gets an explicit temporary root. Never the default data root
  (`~/Library/Application Support/FoldCV`), which is the user's store. For a full run, a
  temporary `HOME` is an extra guard: `HOME="$(mktemp -d)" PYTHONPATH=services/api/src ...`.
- `tests/architecture/test_imports.py` (AST only) fails when a module of `packages/resume_core`
  or `resume_api` imports a deleted layer or carries a deleted module name, and when
  `packages/resume_core` imports `resume_api`.
- `tests/foundation/test_private_resume_git.py` covers the private resume data guard
  (`tools/check_private_resume_data.py`).

## Layout

| Directory | Subject |
|---|---|
| `tests/repository` | repository commit, atomic save, revisions and replay, build isolation, journal, editor token, concurrency, tasks |
| `tests/projects` | `/v2` project routes: golden authored operations, edits, history, clipboard, import task, resume and permit, export, archive, images, sources, metadata, store and catalog; F10 composition (slow) |
| `tests/assistant` | runs, tools, compiler, proposals, permissions, actions, store, MCP listener, runtime, web fetcher, skills |
| `tests/templates` | V7 template domain: preparation, mutations, paste, scopes, relations, sync, import pipeline, sidecar, review, captured DOCX; scripted Generic and second-template imports (slow); golden corpus in `golden/` |
| `tests/facts` | facts panel, fact mutations, sync, dependencies, dates, technology lists |
| `tests/render` | DOCX rendering, layout, Focus, localization; real conversions (slow) |
| `tests/rewrite` | rewrite preview route, timing, text rewrite |
| `tests/import` | import models |
| `tests/extract`, `tests/docx` | PDF and DOCX extraction; DOCX basics |
| `tests/providers` | Codex adapter, structured schema, preflight cache, inference admission, admitted provider, profile ownership |
| `tests/service` | boundary, launcher, lifecycle, CLI install and runner, process groups, extract and render workers, readiness, GC tuning, uvicorn |
| `tests/settings` | rules, preferences, limits, model settings, assistant settings, error catalog |
| `tests/contracts` | generated schemas, examples and cases |
| `tests/foundation` | contract drift check, private git guard |
| `tests/architecture` | import rules |
| `tests/support`, `tests/fixtures` | helpers and synthetic fixtures |
| `skills/format-resume/tests` | skill archive and policy regressions |
| `apps/web/unit` | client: V7 extraction, translation and projection, edit transport, history, panel, structure, rewrite, export, assistant, import notices, settings, tab lock |

## Rules for tests

- Useful tests (D076): observable behavior, edge cases and concrete failure risks, not
  implementation mirrors or counts. Every behavior defect found in review gets a regression
  that fails without the fix. A GUI-only defect gets repeatable T3 steps with the revision and
  the expected and actual result. Documentation-only changes need no tests.
- One subject per file, named by the module or route it covers. No corpora or variant
  generators that replay hundreds of cases.
- No `sleep` above 50 ms and no wall-clock waits; time comes from an injected clock or a
  deadline. Timing-sensitive tests are rewritten with injected clocks, not retried.
- Fault injection in process (monkeypatched `os.replace`, `os.fsync`, `atomic_write`, provider
  returns). At most one real subprocess kill test per subject.
- No test asserts on documentation, handoff or log files; policy checks stay in `tools/check_*`
  scripts that run on demand.
- A test that only restates another test or a pydantic validator is not kept.
- Synthetic data only: no real candidate data, credentials or subscription in routine tests.
  Paths that must not call a model (extraction, editing, facts, export, archive, reopen) run
  with `ForbiddenContentProvider` (`tests/support/foundation.py`), which fails on any call.
- A deleted test is listed in its slice handoff with its subject and the test that now covers
  it, or the reason the subject is gone.

## GUI checks in T3

No automated browser scenarios. GUI behavior is checked by hand in the T3 preview on a
synthetic store; steps, results and screenshots go into the slice handoff.

```sh
cd apps/web && npm run build && cd ../..
.venv/bin/python tools/serve_synthetic.py --root /private/tmp/foldcv-<name> --dist apps/web/dist
```

- The root must be a new `/private/tmp/foldcv-*` directory; `--reopen` reuses a root of this
  tool. Delete the root afterwards.
- Projects are created through the repository. The connection, content provider, assistant
  runtime and web fetcher are scripted, so no model or native process starts.
  `--employment` picks the fixture (`issues`, `views`, `generic-f06`, `generic-f10`);
  `--template-call-cap N` allows template imports; `--template-delay S` holds each scripted
  template call S seconds, so a running or queued import can be watched and stopped.
- `--live-assistant` runs the assistant on the real Codex sign-in (`cli-experiment`, used in
  place) with synthetic projects in the temp root. Every start is charged before it runs to
  `docs/gui/handoffs/SIMPLIFY/logs/sr08-live-ledger.jsonl`, and starts past the allowance are
  refused. Rewrites are refused and `--template-call-cap` is not accepted, because the ledger
  does not count them. Only with an explicit user allowance.
- stdout prints the origin and the one-shot URL; the secret is only in `<root>/launch.json`.
- T3 cannot prove native IME, clipboard, drag or Word; those stay manual.

## Benchmark

`tools/save_bench/bench.py` measures one V7 edit through `/v2` on the synthetic 3.3 MB
fixture in a new temporary store:

```sh
SPC_GC=freeze .venv/bin/python -I tools/save_bench/bench.py . --api v2 --edits 4
```

Gate: 1.5 s per edit with `SPC_GC=freeze`. Measured 2026-10-27: 830–918 ms (default GC
1 221–1 278 ms). Run it before and after any change to the edit path.

## Live model checks and manual gates

Live model runs are never part of routine runs. They need an explicit user allowance (model and
number of starts); failed starts count. Judge results against source-derived facts, not exact
sentences: schema validity, required-fact recall, invented claims, preserved units and
ownership, latency and reported usage. Word on macOS stays a separate manual gate for DOCX
appearance and editing.
