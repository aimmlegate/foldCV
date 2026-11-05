# FoldCV

Local resume editor. It imports a PDF, DOCX, TXT or Markdown resume, extracts its
facts into a template, lets you edit and rewrite the text, and exports DOCX, or PDF
through the system print window.

Projects stay on your computer in `~/Library/Application Support/FoldCV`. Model work
runs through your own Codex or Claude CLI sign-in. FoldCV has no server of its own
and uses no API keys.

## Run from source

Verified on macOS arm64 with Python 3.13 and Node 22.14.

```sh
python3.13 -m venv .venv
.venv/bin/python -m pip install -r requirements-dev.txt
.venv/bin/python -m pip install -e .
npm --prefix apps/web ci
npm --prefix apps/web run build
bash tools/install-local-renderer.sh
.venv/bin/python tools/run-local.py --experimental-cli
```

The launcher starts one local service on `127.0.0.1` and opens the browser. Stop it
with Ctrl-C. Without `--experimental-cli` the app works with no model calls. See
[local setup](docs/gui/local-setup.md) for details.

## macOS app

`tools/build-macos-dmg.sh` builds `foldCV Beta.app` and its DMG from this checkout in one step: the frontend, the
local service frozen with PyInstaller, and the Tauri window around it (`apps/desktop-tauri`), which shows the page in
the system WebKit. It needs Apple Silicon, arm64 Node 22, python.org Python 3.13 and Rust from
[rustup](https://rustup.rs), and writes to `output/foldcv-macos-<version>-<commit>/`. The app runs on macOS 12 or later
with Safari 17.4 or later, whose WebKit it uses. It keeps its data in `~/Library/Application Support/foldCV Beta`, as
the earlier Electron builds did, apart from the browser service's `FoldCV` root. The signature is ad hoc: on another
Mac, allow the app once in System Settings → Privacy & Security.

## Windows app

The `Windows` workflow builds the portable `foldCV-Beta-<version>-win-x64.zip` on a Windows runner and checks it there
(helper, both CLIs, app start, second start, close and kill; artifact `foldcv-windows`): the frontend, the python.org
embeddable Python with the service's Windows wheels, and the Tauri window (`apps/desktop-tauri`), which shows the page in
the system WebView2 that Windows 11 has. Its shell needs the Windows toolchain, so the zip is built on the runner only.
Unpack the zip anywhere and run `foldCV Beta.exe`; there is no installer. Data stays in `%LOCALAPPDATA%\foldCV Beta`, so
a newer zip in another folder keeps projects and sign-ins. The zip is not signed: Windows SmartScreen asks once (More
info → Run anyway). Codex and Claude run in a Job Object that lets them start no other program and ends them with the
app; unlike the macOS sandbox it does not limit which files they read or write.

## Repository

| Path | Contents |
| --- | --- |
| `apps/web` | React and TypeScript frontend |
| `apps/desktop-tauri` | Tauri window of the macOS and Windows apps |
| `services/api` | FastAPI local service, CLI providers, import and assistant |
| `packages/resume_core` | Project storage, templates and DOCX rendering |
| `contracts` | Generated JSON Schemas and contract examples |
| `templates` | Bundled resume templates |
| `design/future-editor/visual` | Visual layer used by the frontend |
| `skills/format-resume/assets` | Fonts and technology icons of the catalog |
| `tools` | Launcher, checks and benchmarks |
| `tests` | Python test suites |

## Private templates

Put a template YAML and its `assets/` folder into the ignored `templates/local/`. A local
run or desktop build lists it first and uses it as the default. A clean clone ships only
the bundled generic templates; `FOLDCV_PUBLIC_TEMPLATES=1` keeps the private ones out of a run or desktop build.

## Documentation

- [Architecture](docs/gui/architecture.md): service, storage, API, CLI adapter and rendering.
- [Contracts](docs/gui/contracts.md): versioned JSON contracts and their generation.
- [Local setup](docs/gui/local-setup.md): setup, launcher modes and CLI sign-in.
- [Testing](docs/gui/testing.md): suites, budgets, GUI checks and the benchmark.
- [Resume data in Git](docs/gui/git-data-policy.md): what may be committed.
- [Dependency notices](docs/gui/local-dependency-notices.md): third-party licenses.

## Tests

```sh
.venv/bin/python -m pytest -q -p no:cacheprovider
```
