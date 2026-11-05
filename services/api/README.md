# Local service

The FastAPI service of the browser run and the desktop helper. For the developer run on macOS arm64 it needs the
project `.venv`, Node 22.14.0 and the built web app:

```sh
.venv/bin/python -m pip install -r requirements-dev.txt
.venv/bin/python -m pip install -e .
cd apps/web && npm ci && npm run build && cd ../..
.venv/bin/python tools/run-local.py
```

`tools/run-local.py` binds `127.0.0.1` on an ephemeral port and opens the browser once the service is ready.
`--no-open` skips the browser, `--port N` takes a fixed loopback port, `--check` only checks the machine,
`--codex-executable PATH` names the Codex CLI, `--experimental-cli` uses the pinned personal CLI profile. The URL
fragment holds a one-use startup secret; the page removes it and exchanges it for an HttpOnly session cookie.

Model work (imports, rewrites, the assistant) runs through the signed-in Codex or Claude CLI the user connects in
Settings; extraction and the DOCX export run in owned worker processes, and the PDF is printed by the page.
`tools/install-local-renderer.sh` installs the pinned LibreOffice only for the slow conversion test and manual PDF
checks.
