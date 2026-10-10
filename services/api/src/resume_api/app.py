"""Same-origin local service. Text generation remains closed by policy."""

from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager
from http.cookies import SimpleCookie
import json
from pathlib import Path
import secrets
import time
from typing import Protocol
import uuid

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import FileResponse, JSONResponse, Response, StreamingResponse
from starlette.exceptions import HTTPException as StarletteHTTPException
from pydantic import ValidationError

from .contracts import (CompletedEvent, CompletedPayload, DraftRequest, EmptyRequest, ErrorEnvelope, ErrorPayload,
                        FailedEvent, NormalizeRequest, OperationResult, RenderRequest, RewriteRequest, StartedEvent,
                        ValidateRequest,
                        StartedPayload, TextRequest, UsagePayload)
from .lifecycle import OperationFiles, SpikeError, has_blocked_owned, reap_owned
from .rendering import DocumentRenderer
from packages.resume_core.rendering.template import PACKAGE_SHA256, RenderFailure, renderer_sha256, require_template
from packages.resume_core.rendering.preparation import PrepareRequest, prepare_document


MAX_BODY = 1_048_576
MAX_OPERATIONS = 20
MAX_CONCURRENT = 2
TIMEOUT_SECONDS = 30
BODY_TIMEOUT_SECONDS = 10
CANCEL_GRACE_SECONDS = 0.5
POST_ONLY_PATHS = frozenset({"session/exchange", "extract", "normalize", "draft", "rewrite",
                            "validate", "prepare-render", "render", "host/discover", "host/status", "host/login",
                            "host/detach", "host/models"})
JSON_POST_PATHS = frozenset("/v1/" + path for path in POST_ONLY_PATHS if path != "extract")


class OperationTimeout(Exception):
    pass


class SyntheticRunner(Protocol):
    """Trusted in-process runner; cancellation must complete within the grace period.

    External work must use OperationFiles.spawn so its process group can be stopped.
    """
    async def run(self, kind: str, request: TextRequest, files: OperationFiles) -> tuple[OperationResult, UsagePayload]: ...


def problem(code: str, status: int, stage: str = "request", retryable: bool = False) -> JSONResponse:
    body = ErrorEnvelope(error=ErrorPayload(code=code, retryable=retryable, stage=stage))
    return JSONResponse(body.model_dump(), status_code=status, headers={"Cache-Control": "no-store"})


def strict_json(raw: bytes) -> object:
    def pairs(items: list[tuple[str, object]]) -> dict[str, object]:
        result: dict[str, object] = {}
        for key, value in items:
            if key in result:
                raise ValueError("duplicate field")
            result[key] = value
        return result

    def invalid_constant(_value: str):
        raise ValueError("non-finite number")

    return json.loads(raw, object_pairs_hook=pairs, parse_constant=invalid_constant)


def is_json_media_type(raw: bytes) -> bool:
    media = raw.split(b";", 1)[0].strip(b" \t").lower()
    return media == b"application/json" or (media.startswith(b"application/") and media.endswith(b"+json"))


class LocalBoundary:
    def __init__(self, app: FastAPI, origin: str, secret: str):
        self.app = app
        self.origin = origin
        self.host = origin.removeprefix("http://")
        self.secret: str | None = secret
        self.cookie_name = "foldcv_" + secrets.token_hex(12)
        self.session: str | None = None

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        raw_headers = scope["headers"]
        headers = {key.lower(): value for key, value in raw_headers}
        critical = (b"host", b"origin", b"cookie", b"forwarded", b"x-forwarded-host", b"x-forwarded-proto")
        if any(sum(key.lower() == name for key, _ in raw_headers) > 1 for name in critical):
            await problem("HOST_DENIED", 403)(scope, receive, send)
            return
        try:
            host = headers.get(b"host", b"").decode("ascii", "strict")
            origin = headers.get(b"origin", b"").decode("ascii", "strict")
        except UnicodeDecodeError:
            await problem("HOST_DENIED", 403)(scope, receive, send)
            return
        path = scope["path"]
        method = scope["method"]
        is_api = path.startswith("/v1/")
        response = None
        if host != self.host or b"forwarded" in headers or b"x-forwarded-host" in headers or b"x-forwarded-proto" in headers:
            response = problem("HOST_DENIED", 403)
        elif is_api and (scope.get("query_string") or (origin and origin != self.origin) or (method != "GET" and origin != self.origin)):
            response = problem("ORIGIN_DENIED", 403)
        elif is_api and path != "/v1/session/exchange" and not self._authorized(headers):
            response = problem("AUTH_REQUIRED", 401)
        if response is not None:
            await response(scope, receive, send)
            return

        if is_api and sum(key.lower() == b"content-type" for key, _ in raw_headers) > 1:
            await problem("INVALID_REQUEST", 422)(scope, receive, send)
            return

        if method in {"POST", "PUT", "PATCH"}:
            deadline = time.monotonic() + BODY_TIMEOUT_SECONDS
            size = 0
            chunks: list[bytes] = []
            while True:
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    await problem("REQUEST_TIMEOUT", 408)(scope, receive, send)
                    return
                try:
                    message = await asyncio.wait_for(receive(), timeout=remaining)
                except asyncio.TimeoutError:
                    await problem("REQUEST_TIMEOUT", 408)(scope, receive, send)
                    return
                if message["type"] == "http.disconnect":
                    return
                part = message.get("body", b"")
                size += len(part)
                if size > MAX_BODY:
                    await problem("INPUT_TOO_LARGE", 413)(scope, receive, send)
                    return
                chunks.append(part)
                if not message.get("more_body", False):
                    break
            body = b"".join(chunks)
            if method == "POST" and path in JSON_POST_PATHS:
                if not is_json_media_type(headers.get(b"content-type", b"")):
                    await problem("INVALID_REQUEST", 415)(scope, receive, send)
                    return
                try:
                    strict_json(body)
                except (ValueError, UnicodeError, RecursionError):
                    await problem("INVALID_REQUEST", 422)(scope, receive, send)
                    return
            delivered = False
            original_receive = receive

            async def replay():
                nonlocal delivered
                if not delivered:
                    delivered = True
                    return {"type": "http.request", "body": body, "more_body": False}
                return await original_receive()

            receive = replay

        started = False

        async def safe_send(message):
            nonlocal started
            if message["type"] == "http.response.start":
                started = True
            await send(message)

        try:
            await self.app(scope, receive, safe_send)
        except Exception:
            # Keep unexpected candidate-bearing exception text out of server logs.
            if not started:
                await problem("INTERNAL_ERROR", 500, "service")(scope, receive, send)

    def _authorized(self, headers: dict[bytes, bytes]) -> bool:
        if self.session is None:
            return False
        cookie = SimpleCookie()
        try:
            cookie.load(headers.get(b"cookie", b"").decode("ascii", "ignore"))
        except Exception:
            return False
        item = cookie.get(self.cookie_name)
        return item is not None and secrets.compare_digest(item.value, self.session)


def create_app(*, origin: str, secret: str, temp_root: Path, dist: Path, runner: SyntheticRunner | None = None):
    if not origin.startswith("http://127.0.0.1:") or not origin.rsplit(":", 1)[-1].isdigit():
        raise ValueError("A concrete IPv4 loopback origin is required")
    if len(secret) < 32:
        raise ValueError("Startup secret is too short")
    reap_owned(temp_root)
    blocked_on_start = has_blocked_owned(temp_root)
    operations: dict[asyncio.Task, OperationFiles] = {}
    cancellation_pending: set[asyncio.Task] = set()

    @asynccontextmanager
    async def lifespan(_app: FastAPI):
        yield
        for task, files in list(operations.items()):
            await cancel_operation(task, files)

    app = FastAPI(docs_url=None, redoc_url=None, openapi_url=None, lifespan=lifespan)
    boundary = LocalBoundary(app, origin, secret)
    active = 0
    count = 0
    unsafe_cleanup = blocked_on_start
    gate = asyncio.Lock()
    document_renderer = DocumentRenderer()

    def lifecycle_code(error: SpikeError) -> str:
        nonlocal unsafe_cleanup
        if error.code in {"PROCESS_CLEANUP_FAILED", "CLEANUP_FAILED", "UNSAFE_TEMP_ROOT"}:
            unsafe_cleanup = True
        return error.code if error.code in {"PROCESS_CLEANUP_FAILED", "CLEANUP_FAILED", "UNSAFE_TEMP_ROOT", "TEMP_FAILED"} else "OPERATION_FAILED"

    async def cancel_operation(task: asyncio.Task, files: OperationFiles) -> str | None:
        if not task.done():
            cancellation_pending.add(task)
        task.cancel()
        cleanup_code = None
        try:
            files.stop_worker()
        except SpikeError as error:
            cleanup_code = lifecycle_code(error)
        done, _ = await asyncio.wait((task,), timeout=CANCEL_GRACE_SECONDS)
        if task in done and not task.cancelled():
            try:
                await task
            except SpikeError as error:
                cleanup_code = lifecycle_code(error)
            except Exception:
                pass
        return cleanup_code

    def operation_done(done: asyncio.Task) -> None:
        nonlocal active
        if not done.cancelled():
            error = done.exception()
            if isinstance(error, SpikeError):
                lifecycle_code(error)
        operations.pop(done, None)
        cancellation_pending.discard(done)
        active -= 1

    @app.exception_handler(RequestValidationError)
    async def invalid_request(_request: Request, _error: RequestValidationError):
        return problem("INVALID_REQUEST", 422)

    @app.exception_handler(ValidationError)
    async def invalid_model(_request: Request, _error: ValidationError):
        return problem("INVALID_RESULT", 500, "service")

    @app.exception_handler(Exception)
    async def unexpected(_request: Request, _error: Exception):
        return problem("INTERNAL_ERROR", 500, "service")

    @app.exception_handler(StarletteHTTPException)
    async def http_error(_request: Request, error: StarletteHTTPException):
        code = {404: "NOT_FOUND", 405: "METHOD_NOT_ALLOWED"}.get(error.status_code, "HTTP_ERROR")
        return problem(code, error.status_code)

    @app.post("/v1/session/exchange")
    async def exchange(request: Request):
        try:
            supplied = (await request.json())["secret"]
        except (ValueError, TypeError, KeyError):
            return problem("INVALID_REQUEST", 422)
        if not isinstance(supplied, str) or boundary.secret is None or not secrets.compare_digest(supplied, boundary.secret):
            return problem("AUTH_REQUIRED", 401)
        boundary.secret = None
        boundary.session = secrets.token_urlsafe(32)
        response = JSONResponse({"sessionReady": True}, headers={"Cache-Control": "no-store"})
        response.set_cookie(boundary.cookie_name, boundary.session, httponly=True, secure=False,
                            samesite="strict", path="/v1/")
        return response

    @app.get("/v1/capabilities")
    async def capabilities():
        try:
            require_template()
            ready = not unsafe_cleanup
        except RenderFailure:
            ready = False
        return JSONResponse({
            "appVersion": "0.1.0", "projectSchemaVersion": 3, "transportVersion": 1,
            "generationReady": False, "renderers": ["docx", "pdf"] if ready else [],
            "formats": ["docx", "pdf"] if ready else [],
            "templates": [{"id": "generic", "version": "1.0.0", "packageSha256": PACKAGE_SHA256}] if ready else [],
            "rendererSha256": renderer_sha256() if ready else None,
            "providers": [{"kind": "codex_cli", "ready": False, "reason": "CLI_PROFILE_UNSAFE"}],
            "limits": {"maxBodyBytes": MAX_BODY, "maxTextOperations": MAX_OPERATIONS,
                       "maxConcurrent": MAX_CONCURRENT, "timeoutSeconds": TIMEOUT_SECONDS},
        }, headers={"Cache-Control": "no-store"})

    async def extract(request: Request):
        if not request.headers.get("content-type", "").startswith("multipart/form-data;"):
            return problem("INVALID_REQUEST", 415)
        return problem("FEATURE_UNAVAILABLE", 501, "extract")

    async def validate(_payload: ValidateRequest):
        return problem("FEATURE_UNAVAILABLE", 501, "validate")

    async def prepare_render(payload: PrepareRequest):
        try:
            prepared = prepare_document(payload)
            return JSONResponse(prepared.model_dump(mode="json", by_alias=True), headers={"Cache-Control": "no-store"})
        except (ValueError, RenderFailure):
            return problem("PREPARATION_FAILED", 422, "prepare")

    async def render(request: Request, payload: RenderRequest):
        nonlocal active
        async with gate:
            if unsafe_cleanup or cancellation_pending or active >= MAX_CONCURRENT:
                return problem("BUSY", 429, "render", True)
            active += 1
        files = OperationFiles(temp_root)

        async def execute() -> bytes:
            with files.open():
                return await document_renderer.render(payload, files)

        task = asyncio.create_task(execute())
        operations[task] = files
        task.add_done_callback(operation_done)

        async def disconnected() -> None:
            while not await request.is_disconnected():
                await asyncio.sleep(0.05)

        watcher = asyncio.create_task(disconnected())
        try:
            done, _ = await asyncio.wait((task, watcher), timeout=TIMEOUT_SECONDS,
                                         return_when=asyncio.FIRST_COMPLETED)
            if task in done:
                data = await task
                return Response(data, media_type="application/zip", headers={"Cache-Control": "no-store"})
            if task not in done:
                cleanup_code = await cancel_operation(task, files)
                if cleanup_code:
                    return problem(cleanup_code, 503, "render")
                if watcher in done:
                    return problem("OPERATION_CANCELLED", 499, "render")
                return problem("OPERATION_TIMEOUT", 504, "render")
            return problem("RENDER_FAILED", 500, "render")
        except RenderFailure as error:
            status = 422 if error.code in {"RENDER_UNSUPPORTED_CONTENT", "UNSUPPORTED_FOCUS_ICON"} else 503 if error.code.endswith(("UNAVAILABLE", "MISMATCH")) else 500
            return problem(error.code, status, "render")
        except SpikeError as error:
            return problem(lifecycle_code(error), 503, "render")
        except asyncio.CancelledError:
            await cancel_operation(task, files)
            raise
        except Exception:
            return problem("RENDER_FAILED", 500, "render")
        finally:
            watcher.cancel()

    async def host_unavailable(_payload: EmptyRequest):
        return problem("FEATURE_UNAVAILABLE", 501, "host")

    app.add_api_route("/v1/extract", extract, methods=["POST"])
    app.add_api_route("/v1/validate", validate, methods=["POST"])
    app.add_api_route("/v1/prepare-render", prepare_render, methods=["POST"])
    app.add_api_route("/v1/render", render, methods=["POST"])
    for path in ("discover", "status", "login", "detach", "models"):
        app.add_api_route(f"/v1/host/{path}", host_unavailable, methods=["POST"])

    async def text_operation(kind: str, request: Request, payload: TextRequest):
        nonlocal active, count
        if runner is None:
            return problem("FEATURE_UNAVAILABLE", 501, kind)
        request_id = "op_" + uuid.uuid4().hex

        async def events():
            nonlocal active, count
            acquired = False
            handed_off = False
            task: asyncio.Task | None = None
            files: OperationFiles | None = None
            sequence = 1
            try:
                reject_code: str | None = None
                async with gate:
                    if unsafe_cleanup or cancellation_pending or active >= MAX_CONCURRENT:
                        reject_code = "BUSY"
                    elif count >= MAX_OPERATIONS:
                        reject_code = "OPERATION_LIMIT"
                    else:
                        count += 1
                        active += 1
                        acquired = True
                if reject_code is not None:
                    failed = FailedEvent(requestId=request_id, sequence=1, type="operation.failed",
                                         baseRevision=payload.baseRevision,
                                         payload=ErrorPayload(code=reject_code, retryable=reject_code == "BUSY", stage=kind))
                    yield (failed.model_dump_json() + "\n").encode()
                    return
                started = StartedEvent(requestId=request_id, sequence=sequence, type="operation.started",
                                       baseRevision=payload.baseRevision, payload=StartedPayload(stage=kind))
                yield (started.model_dump_json() + "\n").encode()
                files = OperationFiles(temp_root)

                async def execute():
                    with files.open():
                        return await runner.run(kind, payload, files)

                task = asyncio.create_task(execute())
                operations[task] = files
                task.add_done_callback(operation_done)
                handed_off = True
                try:
                    result, usage = await asyncio.wait_for(asyncio.shield(task), timeout=TIMEOUT_SECONDS)
                except asyncio.TimeoutError:
                    raise OperationTimeout() from None
                completed = CompletedEvent(requestId=request_id, sequence=sequence + 1, type="operation.completed",
                                           baseRevision=payload.baseRevision,
                                           payload=CompletedPayload(result=result, usage=usage))
                yield (completed.model_dump_json() + "\n").encode()
            except asyncio.CancelledError:
                if task is not None and files is not None:
                    await cancel_operation(task, files)
                raise
            except Exception as error:
                code = lifecycle_code(error) if isinstance(error, SpikeError) else "OPERATION_TIMEOUT" if isinstance(error, OperationTimeout) else "OPERATION_FAILED"
                if task is not None and files is not None and not task.done():
                    cleanup_code = await cancel_operation(task, files)
                    if cleanup_code:
                        code = cleanup_code
                failed = FailedEvent(requestId=request_id, sequence=sequence + 1, type="operation.failed",
                                     baseRevision=payload.baseRevision,
                                     payload=ErrorPayload(code=code, retryable=False, stage=kind))
                yield (failed.model_dump_json() + "\n").encode()
            finally:
                if acquired and not handed_off:
                    async with gate:
                        active -= 1

        return StreamingResponse(events(), media_type="application/x-ndjson", headers={"Cache-Control": "no-store"})

    async def normalize(request: Request, payload: NormalizeRequest):
        return await text_operation("normalize", request, payload)

    async def draft(request: Request, payload: DraftRequest):
        return await text_operation("draft", request, payload)

    async def rewrite(request: Request, payload: RewriteRequest):
        return await text_operation("rewrite", request, payload)

    app.add_api_route("/v1/normalize", normalize, methods=["POST"])
    app.add_api_route("/v1/draft", draft, methods=["POST"])
    app.add_api_route("/v1/rewrite", rewrite, methods=["POST"])

    @app.get("/{path:path}")
    async def static(path: str):
        if path.startswith("v1/"):
            code = "METHOD_NOT_ALLOWED" if path[3:] in POST_ONLY_PATHS else "NOT_FOUND"
            return problem(code, 405 if code == "METHOD_NOT_ALLOWED" else 404)
        root = dist.resolve()
        target = (root / path).resolve()
        if not target.is_relative_to(root) or not root.is_dir():
            return problem("NOT_FOUND", 404)
        if not target.is_file():
            target = (root / "index.html").resolve()
        if not target.is_relative_to(root):
            return problem("NOT_FOUND", 404)
        if not target.is_file():
            return problem("FRONTEND_UNAVAILABLE", 503)
        return FileResponse(target, headers={"Cache-Control": "no-store" if target.name == "index.html" else "public, max-age=31536000, immutable"})

    return boundary
