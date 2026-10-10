# Local service

This launcher is for the personal macOS arm64 developer run. It needs the project
`.venv`, Node 22.14.0, and the built web app. Install packages into `.venv`:

```sh
.venv/bin/python -m pip install -r requirements-service.txt
cd apps/web && npm ci && npm run build && cd ../..
.venv/bin/python tools/run-local.py
```

The launcher binds `127.0.0.1` on an ephemeral port and opens the browser after
readiness. Use `--no-open` for a local test, or `--port N` for a fixed loopback port.
The URL fragment contains a one-use startup secret. The browser removes it before
normal use and exchanges it for a local HttpOnly session cookie.

Generation, extraction, validation, rendering, and host connection routes are
currently unavailable. The capabilities endpoint reports their actual readiness.
This launcher does not inspect CLI login or send inference requests.

The test-only in-process text runner must cooperate with cancellation. External
work must use the operation's managed child process so cancellation can stop its
process group. If a runner exceeds the cancellation grace, its locked workspace
and concurrency slot stay active until that task exits. A timeout response does
not mean the residual task has finished. Arbitrary Python that never yields
cannot be forcibly stopped in this process.
