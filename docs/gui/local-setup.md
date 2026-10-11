# Personal local developer run

This source checkout is verified on **macOS 26.6.2 arm64** (Apple M1 Pro,
32 GiB RAM). Other macOS versions, Windows, Linux, other chips, and packaged
installers have not been tested. The local app can import, edit, review, render,
export and reopen projects without a Codex CLI. Real normalization, drafting and
rewriting remain closed by [D004](automation/decisions.md); test fixtures are not
a release model.

## Setup

Use Python 3.13.1 and Node 22.14.0 in the current shell. Keep the runtime inside this checkout.
From the repository root:

```sh
node --version
python3.13 -m venv .venv
.venv/bin/python -m pip install -r requirements-dev.txt
cd apps/web
npm ci
npm run build
cd ../..
bash tools/install-local-renderer.sh
.venv/bin/python tools/run-local.py --check
```

The renderer install script downloads the pinned LibreOffice macOS arm64 image,
checks its SHA-256, and puts LibreOffice 26.2.6.3 plus Source Sans Pro fonts under
ignored `.tools/`. It does not install a system app. The template manifest pins
the converter, fonts and image assets by hash. If a dependency, converter, font
or asset is missing or changed, `--check` reports a specific local remedy.
Do not commit the downloaded app, build output, runtime files or private resumes.

## Run and stop

```sh
.venv/bin/python tools/run-local.py
```

The launcher checks the local runtime, starts one authenticated service on an
ephemeral `127.0.0.1` port, and opens the browser. Keep that terminal open while
editing. Stop with Ctrl-C. The service cleans owned child processes and operation
files; if cleanup is uncertain, restart is blocked until it is investigated.
`--no-open` prints only the non-secret origin for diagnostics; it does not grant a
usable authenticated browser session. The default browser handoff puts a one-use
startup secret in the URL fragment and removes it after exchange. Do not share
the local origin or browser session.

If the CLI is missing, has no native login, or differs from the pinned profile,
the launcher reports a manual-ready state. `--check` and startup make only a
bounded version check and, for the exact pinned CLI, native login/catalog metadata
checks. They do not generate text. The CLI owns credentials; the app does not read
or copy its auth file. The observed installed CLI is `0.162.0-alpha.17.2`; the
reviewed profile pins `0.162.0-alpha.2`, so this host remains manual-ready.
An explicit executable may be passed with `--codex-executable` or the
`FOLDCV_CODEX_EXECUTABLE` environment variable. Neither changes global CLI
configuration. CLI login availability would not open D004 by itself.

## Data and outputs

Imported originals, extracted units, facts, edits and review state live in browser
memory. Reloading without an explicit project save loses the working project.
An explicit `.cvproject` export includes the complete original bytes and review
state so it can reopen; handle it as a private resume. PDF and editable DOCX are
explicit exports. Temporary service operations use the macOS user temp directory
and are cleaned after completion; the application does not keep a project database
or automatic resume cache. Browser downloads and OS swap/backups follow their own
storage rules. Only synthetic QA artifacts belong in this repository.

The DOCX uses ordinary editable text. The tested LibreOffice path uses Source Sans
Pro Regular/Bold; the original five-weight reference is not an exact visual match.
Pagination and editing in Microsoft Word have not been checked. Check both outputs
before sharing. Live model quality, native CLI retention and other platforms are
still release gates. See [the version manifest](local-version-manifest.json) and
[dependency notices](local-dependency-notices.md).
