"""Same-origin local service. Text generation remains closed by policy."""

from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager
from http.cookies import SimpleCookie
import json
from pathlib import Path
import secrets
import threading
import time
from typing import Protocol
import uuid

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import FileResponse, JSONResponse, Response, StreamingResponse
from starlette.exceptions import HTTPException as StarletteHTTPException
from pydantic import ValidationError

from .contracts import (CompletedEvent, CompletedPayload, ConnectionPayload, DraftRequest, EmptyRequest, ErrorEnvelope, ErrorPayload,
                        FailedEvent, NormalizeRequest, OperationResult, RenderRequest, RewriteRequest, StartedEvent,
                        SelectModelRequest, QuotaPayload, ValidateRequest,
                        StartedPayload, TextRequest, UsagePayload)
from .lifecycle import OperationFiles, SpikeError, has_blocked_owned, reap_owned
from .connection import ConnectionAdapter, ConnectionFailure, Metadata
from .rendering import DocumentRenderer
from .extracting import MAX_BODY as MAX_EXTRACT_BODY, UploadFailure, parse_one_part, run_extract
from packages.resume_core.rendering.template import PACKAGE_SHA256, RenderFailure, renderer_sha256, require_template
from packages.resume_core.rendering.preparation import PrepareRequest, prepare_document
from packages.resume_core.rendering.privacy import guard_render_document
from packages.resume_core.normalization import FactRequest, FactSheet, fingerprint, literal_sheet, semantic_input
from packages.resume_core.drafting import DraftRequest as ProseDraftRequest, DraftResult as ProseDraftResult, draft_input


MAX_BODY = 1_048_576
MAX_OPERATIONS = 20
MAX_CONCURRENT = 2
TIMEOUT_SECONDS = 30
BODY_TIMEOUT_SECONDS = 10
CANCEL_GRACE_SECONDS = 0.5
POST_ONLY_PATHS = frozenset({"session/exchange", "extract", "facts", "facts/normalize", "facts/draft", "normalize", "draft", "rewrite",
                            "validate", "prepare-render", "render", "host/discover", "host/status", "host/login",
                            "host/detach", "host/models", "host/select", "host/cancel-login"})
JSON_POST_PATHS = frozenset("/v1/" + path for path in POST_ONLY_PATHS if path != "extract")


class OperationTimeout(Exception):
    pass


class SyntheticRunner(Protocol):
    """Trusted in-process runner; cancellation must complete within the grace period.

    External work must use OperationFiles.spawn so its process group can be stopped.
    """
    async def run(self, kind: str, request: TextRequest, files: OperationFiles) -> tuple[OperationResult, UsagePayload]: ...


class SemanticRunner(Protocol):
    def run(self, request: FactRequest, files: OperationFiles,
            cancel: threading.Event) -> tuple[FactSheet, dict[str, int | None]]: ...


class ProseDraftRunner(Protocol):
    def run(self, request: ProseDraftRequest, files: OperationFiles,
            cancel: threading.Event) -> tuple[ProseDraftResult, dict[str, int | None]]: ...


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
                if size > (MAX_EXTRACT_BODY if path == "/v1/extract" and method == "POST" else MAX_BODY):
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


def create_app(*, origin: str, secret: str, temp_root: Path, dist: Path, runner: SyntheticRunner | None = None,
               cli_executable: Path | None = None, connection_adapter: ConnectionAdapter | None = None,
               semantic_runner: SemanticRunner | None = None, draft_runner: ProseDraftRunner | None = None,
               fixture_generation_ready: bool = False):
    if not origin.startswith("http://127.0.0.1:") or not origin.rsplit(":", 1)[-1].isdigit():
        raise ValueError("A concrete IPv4 loopback origin is required")
    if len(secret) < 32:
        raise ValueError("Startup secret is too short")
    if fixture_generation_ready and (semantic_runner is None or draft_runner is None):
        raise ValueError("Fixture generation requires both injected runners")
    reap_owned(temp_root)
    blocked_on_start = has_blocked_owned(temp_root)
    operations: dict[asyncio.Task, OperationFiles] = {}
    cancellation_pending: set[asyncio.Task] = set()
    connection_work: dict[asyncio.Task, tuple[OperationFiles, threading.Event]] = {}
    semantic_work: dict[asyncio.Task, tuple[OperationFiles, threading.Event]] = {}

    @asynccontextmanager
    async def lifespan(_app: FastAPI):
        yield
        for task, (files, cancel) in list(connection_work.items()):
            await stop_connection(task, files, cancel)
        for task, (files, cancel) in list(semantic_work.items()):
            await stop_semantic(task, files, cancel)
        for task, files in list(operations.items()):
            if task not in connection_work and task not in semantic_work:
                await cancel_operation(task, files)

    app = FastAPI(docs_url=None, redoc_url=None, openapi_url=None, lifespan=lifespan)
    boundary = LocalBoundary(app, origin, secret)
    active = 0
    import_active = False
    count = 0
    unsafe_cleanup = blocked_on_start
    gate = asyncio.Lock()
    document_renderer = DocumentRenderer()
    connection = connection_adapter or ConnectionAdapter(cli_executable)
    connection_state = ConnectionPayload(state="unchecked")
    connection_epoch = 0

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

    async def stop_semantic(task: asyncio.Task, files: OperationFiles, cancel: threading.Event) -> str | None:
        cancel.set()
        try:
            files.stop_worker()
        except SpikeError as error:
            return lifecycle_code(error)
        done, _ = await asyncio.wait((task,), timeout=CANCEL_GRACE_SECONDS)
        if task not in done:
            return lifecycle_code(SpikeError("PROCESS_CLEANUP_FAILED"))
        try:
            await task
        except SpikeError as error:
            if error.code in {"PROCESS_CLEANUP_FAILED", "CLEANUP_FAILED", "UNSAFE_TEMP_ROOT"}:
                return lifecycle_code(error)
        except Exception:
            pass
        return None

    async def stop_connection(task: asyncio.Task, files: OperationFiles, cancel: threading.Event) -> str | None:
        if not task.done():
            cancellation_pending.add(task)
        cancel.set()
        cleanup_code = None
        try:
            files.stop_worker()
        except SpikeError as error:
            cleanup_code = lifecycle_code(error)
        done, _ = await asyncio.wait((task,), timeout=CANCEL_GRACE_SECONDS)
        if task not in done:
            return lifecycle_code(SpikeError("PROCESS_CLEANUP_FAILED"))
        if task in done:
            try:
                await task
            except SpikeError as error:
                if error.code in {"PROCESS_CLEANUP_FAILED", "CLEANUP_FAILED", "UNSAFE_TEMP_ROOT"}:
                    cleanup_code = lifecycle_code(error)
            except ConnectionFailure as error:
                if error.code in {"PROCESS_CLEANUP_FAILED", "CLEANUP_FAILED"}:
                    cleanup_code = lifecycle_code(SpikeError(error.code))
            except Exception:
                pass
        return cleanup_code

    def operation_done(done: asyncio.Task) -> None:
        nonlocal active
        if not done.cancelled():
            error = done.exception()
            if isinstance(error, SpikeError):
                lifecycle_code(error)
            elif isinstance(error, ConnectionFailure) and error.code in {"PROCESS_CLEANUP_FAILED", "CLEANUP_FAILED"}:
                lifecycle_code(SpikeError(error.code))
        operations.pop(done, None)
        connection_work.pop(done, None)
        semantic_work.pop(done, None)
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
            "generationReady": fixture_generation_ready, "renderers": ["docx", "pdf"] if ready else [],
            "formats": ["docx", "pdf"] if ready else [],
            "templates": [{"id": "generic", "version": "1.0.0", "packageSha256": PACKAGE_SHA256}] if ready else [],
            "rendererSha256": renderer_sha256() if ready else None,
            "providers": [{"kind": "codex_cli", "ready": False, "reason": "CLI_PROFILE_UNSAFE"}],
            "limits": {"maxBodyBytes": MAX_BODY, "maxTextOperations": MAX_OPERATIONS,
                       "maxConcurrent": MAX_CONCURRENT, "timeoutSeconds": TIMEOUT_SECONDS,
                       "maxExtractBodyBytes": MAX_EXTRACT_BODY},
        }, headers={"Cache-Control": "no-store"})

    async def extract(request: Request):
        nonlocal active, import_active
        if not request.headers.get("content-type", "").lower().startswith("multipart/form-data;"):
            return problem("INVALID_REQUEST", 415, "extract")
        try:
            data, name, pasted = parse_one_part(await request.body(), request.headers.get("content-type", ""))
        except (UploadFailure, UnicodeError) as error:
            code = error.code if isinstance(error, UploadFailure) else "INVALID_REQUEST"
            return problem(code, 413 if code == "INPUT_TOO_LARGE" else 422, "extract")
        async with gate:
            if unsafe_cleanup or cancellation_pending or active >= MAX_CONCURRENT or import_active:
                return problem("BUSY", 429, "extract", True)
            active += 1
            import_active = True
        files = OperationFiles(temp_root)

        async def execute():
            with files.open():
                return await run_extract(data, name, pasted, files)

        task = asyncio.create_task(execute())
        operations[task] = files

        def import_done(done: asyncio.Task) -> None:
            nonlocal import_active
            operation_done(done)
            import_active = False

        task.add_done_callback(import_done)

        async def disconnected() -> None:
            while not await request.is_disconnected():
                await asyncio.sleep(0.05)

        watcher = asyncio.create_task(disconnected())
        try:
            done, _ = await asyncio.wait((task, watcher), timeout=TIMEOUT_SECONDS,
                                         return_when=asyncio.FIRST_COMPLETED)
            if task in done:
                result = await task
                return JSONResponse(result.model_dump(mode="json", by_alias=True),
                                    headers={"Cache-Control": "no-store"})
            cleanup_code = await cancel_operation(task, files)
            if cleanup_code:
                return problem(cleanup_code, 503, "extract")
            return problem("OPERATION_CANCELLED" if watcher in done else "OPERATION_TIMEOUT",
                           499 if watcher in done else 504, "extract")
        except UploadFailure as error:
            code = error.code
            status = 413 if code.endswith(("LIMIT", "LARGE")) else 503 if code in {"EXTRACT_FAILED", "EXTRACT_MONITOR_UNAVAILABLE"} else 422
            return problem(code, status, "extract")
        except SpikeError as error:
            return problem(lifecycle_code(error), 503, "extract")
        except asyncio.CancelledError:
            await cancel_operation(task, files)
            raise
        except Exception:
            return problem("EXTRACT_FAILED", 500, "extract")
        finally:
            watcher.cancel()

    async def validate(_payload: ValidateRequest):
        return problem("FEATURE_UNAVAILABLE", 501, "validate")

    async def facts(payload: FactRequest):
        try:
            sheet = literal_sheet(payload)
            encoded = sheet.model_dump_json(by_alias=True).encode("utf-8")
            if len(encoded) > 4 * 1024 * 1024:
                return problem("INPUT_TOO_LARGE", 413, "facts")
            return Response(encoded, media_type="application/json", headers={"Cache-Control": "no-store"})
        except ValueError:
            return problem("INVALID_REQUEST", 422, "facts")

    async def normalize_facts(payload: FactRequest):
        nonlocal active, count
        if semantic_runner is None:
            return problem("CLI_PROFILE_UNSAFE", 503, "normalize")
        try:
            semantic_input(literal_sheet(payload), payload)
        except ValueError as error:
            return problem("INPUT_TOO_LARGE" if str(error) == "INPUT_TOO_LARGE" else "INVALID_REQUEST",
                           413 if str(error) == "INPUT_TOO_LARGE" else 422, "normalize")
        request_id = "op_" + uuid.uuid4().hex

        async def events():
            nonlocal active, count
            reject_code: str | None = None
            async with gate:
                if unsafe_cleanup or cancellation_pending or active >= MAX_CONCURRENT or count >= MAX_OPERATIONS:
                    reject_code = "OPERATION_LIMIT" if count >= MAX_OPERATIONS else "BUSY"
                else:
                    active += 1
                    count += 1
            if reject_code:
                yield (json.dumps({"transportVersion": 1, "requestId": request_id, "sequence": 1,
                                   "baseRevision": payload.base_revision, "type": "operation.failed",
                                   "payload": {"code": reject_code, "retryable": reject_code == "BUSY",
                                               "stage": "normalize"}}) + "\n").encode()
                return
            files = OperationFiles(temp_root)
            cancel = threading.Event()

            def execute():
                with files.open():
                    return semantic_runner.run(payload, files, cancel)

            task = asyncio.create_task(asyncio.to_thread(execute))
            operations[task] = files
            semantic_work[task] = (files, cancel)
            task.add_done_callback(operation_done)
            try:
                yield (json.dumps({"transportVersion": 1, "requestId": request_id, "sequence": 1,
                                   "baseRevision": payload.base_revision, "type": "operation.started",
                                   "payload": {"stage": "normalize"}}) + "\n").encode()
                sheet, usage = await asyncio.wait_for(asyncio.shield(task), timeout=TIMEOUT_SECONDS)
                sheet = FactSheet.model_validate(sheet.model_dump(mode="json", by_alias=True))
                expected_units = {(source.result.source_id, unit.id) for source in payload.sources for unit in source.result.units}
                expected_units.update((source.result.source_id, f"gap:{index}") for source in payload.sources
                                      for index in range(len(source.result.gaps))
                                      if source.overlays.get(f"gap:{index}", "").strip())
                if sheet.source_fingerprint != fingerprint(payload) or {(unit.source_id, unit.unit_id)
                                                                         for unit in sheet.units} != expected_units:
                    raise ValueError("semantic response has stale source references")
                usage = UsagePayload.model_validate(usage).model_dump()
                if len(sheet.model_dump_json(by_alias=True).encode("utf-8")) > 4 * 1024 * 1024:
                    raise ValueError("result too large")
                yield (json.dumps({"transportVersion": 1, "requestId": request_id, "sequence": 2,
                                   "baseRevision": payload.base_revision, "type": "operation.completed",
                                   "payload": {"result": sheet.model_dump(mode="json", by_alias=True), "usage": usage}},
                                  ensure_ascii=False, separators=(",", ":")) + "\n").encode()
            except asyncio.CancelledError:
                await stop_semantic(task, files, cancel)
                raise
            except Exception as error:
                cancel.set()
                code = "OPERATION_TIMEOUT" if isinstance(error, asyncio.TimeoutError) else "INVALID_RESULT"
                if isinstance(error, SpikeError):
                    code = lifecycle_code(error)
                if not task.done():
                    cleanup_code = await stop_semantic(task, files, cancel)
                    if cleanup_code:
                        code = cleanup_code
                yield (json.dumps({"transportVersion": 1, "requestId": request_id, "sequence": 2,
                                   "baseRevision": payload.base_revision, "type": "operation.failed",
                                   "payload": {"code": code, "retryable": False, "stage": "normalize"}}) + "\n").encode()
            finally:
                if not task.done():
                    await stop_semantic(task, files, cancel)

        return StreamingResponse(events(), media_type="application/x-ndjson", headers={"Cache-Control": "no-store"})

    async def draft_facts(payload: ProseDraftRequest):
        nonlocal active, count
        if draft_runner is None:
            return problem("CLI_PROFILE_UNSAFE", 503, "draft")
        try:
            draft_input(payload)
        except ValueError as error:
            return problem("INPUT_TOO_LARGE" if str(error) == "INPUT_TOO_LARGE" else "INVALID_REQUEST",
                           413 if str(error) == "INPUT_TOO_LARGE" else 422, "draft")
        request_id = "op_" + uuid.uuid4().hex

        async def events():
            nonlocal active, count
            reject_code: str | None = None
            async with gate:
                if unsafe_cleanup or cancellation_pending or active >= MAX_CONCURRENT or count >= MAX_OPERATIONS:
                    reject_code = "OPERATION_LIMIT" if count >= MAX_OPERATIONS else "BUSY"
                else:
                    active += 1
                    count += 1
            if reject_code:
                yield (json.dumps({"transportVersion": 1, "requestId": request_id, "sequence": 1,
                                   "baseRevision": payload.base_revision, "type": "operation.failed",
                                   "payload": {"code": reject_code, "retryable": reject_code == "BUSY",
                                               "stage": "draft"}}) + "\n").encode()
                return
            files = OperationFiles(temp_root)
            cancel = threading.Event()

            def execute():
                with files.open():
                    return draft_runner.run(payload, files, cancel)

            task = asyncio.create_task(asyncio.to_thread(execute))
            operations[task] = files
            semantic_work[task] = (files, cancel)
            task.add_done_callback(operation_done)
            try:
                yield (json.dumps({"transportVersion": 1, "requestId": request_id, "sequence": 1,
                                   "baseRevision": payload.base_revision, "type": "operation.started",
                                   "payload": {"stage": "draft"}}) + "\n").encode()
                draft, usage = await asyncio.wait_for(asyncio.shield(task), timeout=TIMEOUT_SECONDS)
                draft = ProseDraftResult.model_validate(draft.model_dump(mode="json", by_alias=True))
                if draft.source_fingerprint != payload.source_fingerprint or draft.base_revision != payload.base_revision:
                    raise ValueError("stale draft")
                usage = UsagePayload.model_validate(usage).model_dump()
                encoded = draft.model_dump(mode="json", by_alias=True)
                if len(json.dumps(encoded, ensure_ascii=False).encode("utf-8")) > 4 * 1024 * 1024:
                    raise ValueError("result too large")
                yield (json.dumps({"transportVersion": 1, "requestId": request_id, "sequence": 2,
                                   "baseRevision": payload.base_revision, "type": "operation.completed",
                                   "payload": {"result": encoded, "usage": usage}},
                                  ensure_ascii=False, separators=(",", ":")) + "\n").encode()
            except asyncio.CancelledError:
                await stop_semantic(task, files, cancel)
                raise
            except Exception as error:
                cancel.set()
                code = "OPERATION_TIMEOUT" if isinstance(error, asyncio.TimeoutError) else "INVALID_RESULT"
                if isinstance(error, SpikeError):
                    code = lifecycle_code(error)
                if not task.done():
                    cleanup_code = await stop_semantic(task, files, cancel)
                    if cleanup_code:
                        code = cleanup_code
                yield (json.dumps({"transportVersion": 1, "requestId": request_id, "sequence": 2,
                                   "baseRevision": payload.base_revision, "type": "operation.failed",
                                   "payload": {"code": code, "retryable": False, "stage": "draft"}}) + "\n").encode()
            finally:
                if not task.done():
                    await stop_semantic(task, files, cancel)

        return StreamingResponse(events(), media_type="application/x-ndjson", headers={"Cache-Control": "no-store"})

    async def prepare_render(payload: PrepareRequest):
        try:
            prepared = prepare_document(payload)
            return JSONResponse(prepared.model_dump(mode="json", by_alias=True), headers={"Cache-Control": "no-store"})
        except RenderFailure as error:
            return problem(error.code if error.code.startswith("PRIVATE_OUTPUT_") else "PREPARATION_FAILED", 422, "prepare")
        except ValueError:
            return problem("PREPARATION_FAILED", 422, "prepare")

    async def render(request: Request, payload: RenderRequest):
        nonlocal active
        try:
            guard_render_document(payload.document)
        except RenderFailure as error:
            return problem(error.code, 422, "render")
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
            status = 422 if error.code in {"RENDER_UNSUPPORTED_CONTENT", "UNSUPPORTED_FOCUS_ICON"} or error.code.startswith("PRIVATE_OUTPUT_") else 503 if error.code.endswith(("UNAVAILABLE", "MISMATCH")) else 500
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

    login_task: asyncio.Task | None = None

    def connection_response() -> JSONResponse:
        return JSONResponse(connection_state.model_dump(), headers={"Cache-Control": "no-store"})

    async def connection_job(kind: str, work):
        nonlocal active, connection_epoch, connection_state, login_task
        async with gate:
            if kind == "login" and connection_state.state != "login_required":
                return problem("LOGIN_NOT_AVAILABLE", 409, "host")
            if unsafe_cleanup:
                connection_state = ConnectionPayload(state="cleanup_blocked")
                return connection_response()
            if cancellation_pending or active >= MAX_CONCURRENT or connection_work:
                return problem("BUSY", 429, "host", True)
            active += 1
            epoch = connection_epoch
            files = OperationFiles(temp_root)
            cancel = threading.Event()

            def execute():
                with files.open():
                    return work(files, cancel)

            task = asyncio.create_task(asyncio.to_thread(execute))
            operations[task] = files
            connection_work[task] = (files, cancel)
            task.add_done_callback(operation_done)
            if kind == "login":
                login_task = task
                connection_state = ConnectionPayload(state="login_pending", version=connection_state.version)
        try:
            result = await asyncio.shield(task)
            async with gate:
                if epoch != connection_epoch:
                    return connection_response()
                if kind == "login":
                    connection_state = ConnectionPayload(state="login_required", version=connection_state.version)
                    return connection_response()
                assert isinstance(result, Metadata)
                selected = connection_state.selectedModel if connection_state.selectedModel in result.models else None
                quota = QuotaPayload(state=result.quota.state, usedPercent=result.quota.used_percent,
                                     resetsAt=result.quota.resets_at)
                state = ("unchecked" if kind == "discover" else "quota_exhausted" if quota.state == "exhausted"
                         else "unknown_limits" if quota.state == "unknown" else "connected")
                connection_state = ConnectionPayload(state=state, version=result.version, plan=result.plan,
                                                     models=list(result.models), selectedModel=selected, quota=quota,
                                                     metadataReady=kind != "discover")
                return connection_response()
        except ConnectionFailure as error:
            if error.code in {"PROCESS_CLEANUP_FAILED", "CLEANUP_FAILED"}:
                lifecycle_code(SpikeError(error.code))
            async with gate:
                if unsafe_cleanup:
                    connection_state = ConnectionPayload(state="cleanup_blocked")
                    return connection_response()
                if epoch != connection_epoch:
                    return connection_response()
                mapped = {"CLI_MISSING": "cli_missing", "CLI_LAUNCH_UNSUPPORTED": "launcher_unsupported",
                          "UNSUPPORTED_VERSION": "unsupported_version",
                          "LOGIN_REQUIRED": "login_required", "API_KEY_MODE": "api_key_mode",
                          "METADATA_FAILED": "metadata_failed"}
                state = mapped.get(error.code, "login_failed" if kind == "login" else "metadata_failed")
                connection_state = ConnectionPayload(state=state, version=error.version)
                return connection_response()
        except SpikeError as error:
            lifecycle_code(error)
            async with gate:
                if unsafe_cleanup:
                    connection_state = ConnectionPayload(state="cleanup_blocked")
                elif epoch == connection_epoch:
                    connection_state = ConnectionPayload(state="metadata_failed")
                return connection_response()
        except asyncio.CancelledError:
            await stop_connection(task, files, cancel)
            raise
        except Exception:
            async with gate:
                if unsafe_cleanup:
                    connection_state = ConnectionPayload(state="cleanup_blocked")
                elif epoch == connection_epoch:
                    connection_state = ConnectionPayload(state="metadata_failed")
                return connection_response()
        finally:
            if login_task is task:
                login_task = None

    async def discover(_payload: EmptyRequest):
        return await connection_job("discover", lambda files, cancel: connection.inspect(files, cancel, full=False))

    async def status(_payload: EmptyRequest):
        return await connection_job("status", lambda files, cancel: connection.inspect(files, cancel))

    async def models(_payload: EmptyRequest):
        return await status(_payload)

    async def login(_payload: EmptyRequest):
        return await connection_job("login", connection.login)

    async def select(payload: SelectModelRequest):
        nonlocal connection_state
        async with gate:
            if not connection_state.metadataReady or payload.model not in connection_state.models:
                return problem("MODEL_DENIED", 409, "host")
            connection_state = connection_state.model_copy(update={"selectedModel": payload.model})
            return connection_response()

    async def detach(_payload: EmptyRequest):
        nonlocal connection_epoch, connection_state
        async with gate:
            connection_epoch += 1
            connection_state = ConnectionPayload(state="detached")
            current = list(connection_work.items())
        codes = await asyncio.gather(*(stop_connection(task, files, cancel)
                                       for task, (files, cancel) in current))
        if any(code is not None for code in codes) or unsafe_cleanup:
            connection_state = ConnectionPayload(state="cleanup_blocked")
        return connection_response()

    async def cancel_login(_payload: EmptyRequest):
        nonlocal connection_epoch, connection_state
        async with gate:
            current = login_task
            if current is None or current not in connection_work:
                return connection_response()
            connection_epoch += 1
            connection_state = ConnectionPayload(state="login_required", version=connection_state.version)
            files, cancel = connection_work[current]
        code = await stop_connection(current, files, cancel)
        if code is not None or unsafe_cleanup:
            connection_state = ConnectionPayload(state="cleanup_blocked")
        return connection_response()

    app.add_api_route("/v1/extract", extract, methods=["POST"])
    app.add_api_route("/v1/facts", facts, methods=["POST"])
    app.add_api_route("/v1/facts/normalize", normalize_facts, methods=["POST"])
    app.add_api_route("/v1/facts/draft", draft_facts, methods=["POST"])
    app.add_api_route("/v1/validate", validate, methods=["POST"])
    app.add_api_route("/v1/prepare-render", prepare_render, methods=["POST"])
    app.add_api_route("/v1/render", render, methods=["POST"])
    for path, handler in (("discover", discover), ("status", status), ("models", models),
                          ("login", login), ("select", select), ("detach", detach),
                          ("cancel-login", cancel_login)):
        app.add_api_route(f"/v1/host/{path}", handler, methods=["POST"])

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
