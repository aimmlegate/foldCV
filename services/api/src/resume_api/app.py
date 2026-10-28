"""Same-origin local service: the V7 workbench, its settings and the model connection."""

from __future__ import annotations

import asyncio
from concurrent.futures import ThreadPoolExecutor
from collections.abc import Callable
from dataclasses import dataclass
from io import BytesIO
from contextlib import asynccontextmanager
from http.cookies import SimpleCookie
import json
from pathlib import Path
import secrets
import threading
import time
from zipfile import ZipFile, ZIP_STORED

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import FileResponse, JSONResponse, Response
from starlette.exceptions import HTTPException as StarletteHTTPException
from pydantic import ValidationError

from .host_models import (ConnectionPayload, ErrorEnvelope, ErrorPayload, HostRequest, LoginCodeRequest, ProviderSummary,
                          QuotaPayload, SelectModelRequest, SelectProviderRequest, SelectReasoningRequest)
from .lifecycle import OperationFiles, SpikeError, has_blocked_owned, reap_owned
from .connection import ConnectionAdapter, ConnectionFailure, Metadata
from .cli.experimental_profile import ExperimentalCliProfile, ExperimentalProfileError
from .cli.installation import CliInstallation
from .cli.profiles.claude import ClaudeProfileError
from .providers.codex_cli import CodexCliProvider
from .providers.registry import DESCRIPTORS, ProviderRegistry, discovered
from .extracting import MAX_BODY as MAX_EXTRACT_BODY
from packages.resume_core.rendering.template import ROOT as TEMPLATE_ROOT, MANIFEST as TEMPLATE_MANIFEST, RenderFailure, require_template
from packages.resume_core.rules import PRESET_HEADINGS, RulesFailure, RulesStore, presets
from packages.resume_core.models.settings import (RulesSettings, RulesSettingsError, SaveAnalysisPreference,
    SaveImportModelPreference, SaveLimitsPreference, SaveRulesRequest)
from .projects.errors import ProjectFailure
from packages.resume_core.preferences import PreferencesStore, PreferencesFailure
from packages.resume_core.project_limits import ARCHIVE_BYTES, apply_preferences as apply_limits
from .inference_admission import INFERENCE, AdmissionBlocked, AdmissionTimeout, AdmissionCancelled
from .profile_ownership import native_profile, recover_profile
from packages.resume_core.assistant_store import AgentFailure
from .agent.runtime import CodexAgentRuntime


MAX_BODY = 1_048_576
MAX_CONCURRENT = 2
BODY_TIMEOUT_SECONDS = 10
CANCEL_GRACE_SECONDS = 0.5
# "not_provided": the provider has no sanctioned usage read (decision 15); runs stay allowed.
USABLE_QUOTA = frozenset({"available", "not_provided"})
POST_ONLY_PATHS = frozenset({"session/exchange", "host/discover", "host/status", "host/login", "host/detach", "host/models",
                            "host/select", "host/cancel-login", "host/install", "host/cancel-install",
                            "host/select-provider", "host/login-code"})
JSON_POST_PATHS = frozenset("/v1/" + path for path in POST_ONLY_PATHS)
JSON_PUT_PATHS = frozenset({"/v1/settings/rules", "/v1/settings/assistant"})


@dataclass
class ProviderSlot:
    """One provider's connection adapter, content provider, native profile, installer and assistant runtime;
    only the active slot runs processes."""
    connection: object
    provider: object | None = None
    profile: object | None = None
    installation: CliInstallation | None = None
    runtime: object | None = None
    # How a finished managed install rebinds the slot to the new executable.
    rebind: Callable[[ProviderSlot, Path], ProviderSlot] | None = None


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
        is_api = path.startswith(("/v1/", "/v2/"))
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

        if method in {"POST", "PUT", "PATCH", "DELETE"}:
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
                project_upload = path in {"/v1/rich/projects/template-input", "/v2/projects/archive"}
                body_limit = (ARCHIVE_BYTES + 4096 if path == "/v2/projects/archive" else MAX_EXTRACT_BODY if project_upload
                    else MAX_BODY)
                if path.startswith("/v2/projects/") and path.endswith("/edits"):
                    # A preparation is bounded to 1 MiB; the envelope adds the token and the base revision.
                    body_limit = MAX_BODY + 64 * 1024
                if size > body_limit:
                    await problem("INPUT_TOO_LARGE", 413)(scope, receive, send)
                    return
                chunks.append(part)
                if not message.get("more_body", False):
                    break
            body = b"".join(chunks)
            project_json = path.startswith("/v2/projects") and path != "/v2/projects/archive"
            if (method == "POST" and path in JSON_POST_PATHS) or (method == "PUT" and path in JSON_PUT_PATHS) or project_json:
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


def create_app(*, origin: str, secret: str, temp_root: Path, dist: Path, cli_executable: Path | None = None,
               connection_adapter: ConnectionAdapter | None = None, experimental_profile: ExperimentalCliProfile | None = None,
               data_root: Path | None = None, content_provider=None, clock=None, agent_runtime=None,
               template_import_call_cap: int | None = None, template_import_concurrency: int = 3,
               provider_registry: ProviderRegistry | None = None, provider_slots: dict[str, ProviderSlot] | None = None):
    if not origin.startswith("http://127.0.0.1:") or not origin.rsplit(":", 1)[-1].isdigit():
        raise ValueError("A concrete IPv4 loopback origin is required")
    if len(secret) < 32:
        raise ValueError("Startup secret is too short")
    if experimental_profile is not None and (content_provider is not None or agent_runtime is not None):
        raise ValueError("Experimental CLI cannot use injected generation runners")
    registry = provider_registry or ProviderRegistry()
    if any(kind == "codex_cli" or kind not in DESCRIPTORS for kind in provider_slots or {}):
        raise ValueError("Extra provider slots name other known kinds")
    reap_owned(temp_root)
    blocked_on_start = (has_blocked_owned(temp_root) or recover_profile(experimental_profile, temp_root)
                        or any(recover_profile(slot.profile, temp_root) for slot in (provider_slots or {}).values()
                               if slot.profile is not None))
    operations: dict[asyncio.Task, OperationFiles] = {}
    cancellation_pending: set[asyncio.Task] = set()
    connection_work: dict[asyncio.Task, tuple[OperationFiles, threading.Event]] = {}

    @asynccontextmanager
    async def lifespan(_app: FastAPI):
        # Externalizes import records of files written before D104, once; old job, agent and V6 files stay untouched.
        await asyncio.to_thread(project_repository.start)
        yield
        intake.request_shutdown()
        rewrite.request_shutdown()
        projects.imports.stop_all()
        await assistant.shutdown()
        # An import left running would keep its model process and block the default executor's shutdown.
        for stopping in (intake.shutdown, rewrite.shutdown, projects.imports.shutdown):
            try:
                await stopping()
            except ProjectFailure:
                pass
        for identifier in list(project_repository.sessions):
            await asyncio.to_thread(project_repository.close, identifier)
        render_executor.shutdown(wait=True, cancel_futures=True)
        for task, (files, cancel) in list(connection_work.items()):
            await stop_connection(task, files, cancel)
        for task, files in list(operations.items()):
            if task not in connection_work:
                await cancel_operation(task, files)

    app = FastAPI(docs_url=None, redoc_url=None, openapi_url=None, lifespan=lifespan)
    boundary = LocalBoundary(app, origin, secret)
    if data_root is None and (connection_adapter is not None or content_provider is not None):
        data_root = temp_root.parent / "FoldCV"
    rules_store = RulesStore(data_root)
    active = 0
    unsafe_cleanup = blocked_on_start
    gate = asyncio.Lock()
    from packages.resume_core.project_limits import RENDER_WORKERS
    from .rendering import TemplateDocxRenderer
    render_executor = ThreadPoolExecutor(max_workers=RENDER_WORKERS, thread_name_prefix="foldcv-render")
    docx_renderer = TemplateDocxRenderer(executor=render_executor)
    connection = connection_adapter or ConnectionAdapter(experimental_profile.executable if experimental_profile else cli_executable,
                                                          experimental_profile=experimental_profile)
    provider = (CodexCliProvider(experimental_profile.executable, experimental_profile=experimental_profile)
                if experimental_profile else None)
    installation = CliInstallation(experimental_profile.root.parent / "cli-runtime") if experimental_profile else None
    connection_state = ConnectionPayload(state="unchecked")
    connection_epoch = 0
    connection_namespace = secrets.token_hex(12)

    def bind_codex(slot, executable):
        # The connection object stays: the assistant connection and the routes read it.
        profile = ExperimentalCliProfile(slot.profile.root, executable)
        slot.connection.executable = executable
        slot.connection.experimental_profile = profile
        return ProviderSlot(slot.connection, CodexCliProvider(executable, experimental_profile=profile), profile,
                            slot.installation, CodexAgentRuntime(slot.connection, temp_root), bind_codex)

    # The names above always hold the active slot; a provider switch rebinds them after a clean detach.
    slots = {"codex_cli": ProviderSlot(connection, provider, experimental_profile, installation, rebind=bind_codex),
             **(provider_slots or {})}
    active_kind = "codex_cli"
    provider_notice = None

    def experimental_authorized(model=None) -> bool:
        return (experimental_profile is not None and not unsafe_cleanup and not INFERENCE.blocked
                and connection_state.state == "connected" and connection_state.metadataReady
                and connection_state.quota.state in USABLE_QUOTA
                and (model or connection_state.selectedModel) in connection_state.models)

    def experimental_ready(model=None) -> bool:
        return (experimental_authorized(model)
                and not any(not task.done() for task in connection_work))

    def lifecycle_code(error: SpikeError) -> str:
        nonlocal unsafe_cleanup
        if error.code in {"PROCESS_CLEANUP_FAILED", "CLEANUP_FAILED", "UNSAFE_TEMP_ROOT"}:
            unsafe_cleanup = True
        return error.code if error.code in {"PROCESS_CLEANUP_FAILED", "CLEANUP_FAILED", "UNSAFE_TEMP_ROOT", "TEMP_FAILED"} else "OPERATION_FAILED"

    @asynccontextmanager
    async def worker_slot(cancel):
        nonlocal active
        while True:
            async with gate:
                if unsafe_cleanup:
                    raise SpikeError("PROCESS_CLEANUP_FAILED")
                if cancel.is_set():
                    raise AdmissionCancelled()
                if active < MAX_CONCURRENT and not cancellation_pending:
                    active += 1
                    break
            await asyncio.sleep(0.025)
        try:
            yield
        finally:
            active -= 1

    def selected_provider():
        if content_provider is not None and not unsafe_cleanup:
            return content_provider, connection_state.selectedModel or "fixture"
        if experimental_ready() and provider is not None:
            return provider, connection_state.selectedModel
        return None

    preferences_store = PreferencesStore(rules_store.root)
    try:
        apply_limits(preferences_store.load() if preferences_store.path.exists() else None)
    except PreferencesFailure:
        apply_limits(None)
    def import_selected_provider():
        try:
            model = preferences_store.load().selected_import_model
        except PreferencesFailure as error:
            raise ProjectFailure(error.code, 409) from None
        if model is None:
            return selected_provider()
        if not connection_state.metadataReady or model not in connection_state.models:
            raise ProjectFailure("MODEL_DENIED", 409)
        if content_provider is not None and not unsafe_cleanup:
            return content_provider, model
        if experimental_ready(model) and provider is not None:
            return provider, model
        return None

    from packages.resume_core.project_repository import ProjectRepository
    from .projects.exports import ExportService, production_render
    from .projects.fold import register_import_fold
    from .projects.imports import ImportService
    from .projects.intake import TemplateIntake
    from .projects.routes import mount_projects_v2
    from .projects.service import ProjectService
    from .template_rewrite import TemplateRewrite
    from .templates_routes import mount_template_routes
    # Every project write goes through the repository (D109).
    project_repository = ProjectRepository(rules_store.root)
    register_import_fold(project_repository)
    projects = ProjectService(project_repository)
    app.state.projects = projects
    intake = TemplateIntake(project_repository, temp_root=temp_root, worker_slot=worker_slot, cleanup_error=lifecycle_code,
        **({"clock": clock} if clock is not None else {}))
    app.state.intake = intake
    rewrite = TemplateRewrite(selected_provider, preferences=preferences_store, temp_root=temp_root, worker_slot=worker_slot,
        cleanup_error=lifecycle_code)
    projects.rewrite_text, projects.rewrite_cancel = rewrite.text, rewrite.cancel
    mount_projects_v2(app, projects)

    from .assistant.runs import AgentConnection, AssistantService
    from .assistant.routes import mount_assistant

    def agent_connection():
        reason = ("AGENT_CLEANUP_FAILED" if unsafe_cleanup or INFERENCE.blocked else
            "AGENT_AUTH_REQUIRED" if connection_state.state in {"login_required", "login_pending", "detached"} else
            "AGENT_QUOTA" if connection_state.quota.state == "exhausted" else "AGENT_CONNECTION_UNAVAILABLE")
        ready = (not unsafe_cleanup and not INFERENCE.blocked and connection_state.state == "connected"
            and connection_state.metadataReady and connection_state.quota.state in USABLE_QUOTA
            and not connection_work)
        return AgentConnection(ready, tuple(connection_state.models),
            "connection_" + connection_namespace + "_" + str(connection_epoch), None if ready else reason,
            dict(connection_state.modelReasoning))

    resolved_agent_runtime = agent_runtime
    if resolved_agent_runtime is None and experimental_profile is not None:
        try:
            resolved_agent_runtime = CodexAgentRuntime(connection, temp_root)
        except AgentFailure:
            resolved_agent_runtime = None
    assistant = AssistantService(projects, resolved_agent_runtime, agent_connection)
    projects.on_deleted = assistant.project_deleted
    app.state.assistant = assistant
    mount_assistant(app, assistant)
    slots["codex_cli"].runtime = resolved_agent_runtime

    def activate(kind):
        nonlocal active_kind, connection, provider, experimental_profile, installation
        slot = slots[kind]
        active_kind = kind
        connection, provider, experimental_profile, installation = (slot.connection, slot.provider, slot.profile,
                                                                    slot.installation)
        assistant.runtime = slot.runtime

    def switch_preferences(kind):
        # The assistant model and effort live in their own file; they move with the provider's other choices.
        current = assistant.settings.load()
        _, (model, effort) = preferences_store.select_provider(kind, current.selected_agent_model, current.reasoning_effort)
        assistant.settings.restore_model(model, effort)

    try:
        stored = preferences_store.load().selected_provider if preferences_store.path.exists() else "codex_cli"
    except PreferencesFailure:
        stored = "codex_cli"
    if stored != "codex_cli" and registry.resolve(stored) == stored and stored in slots:
        activate(stored)
    elif stored != "codex_cli":
        provider_notice = "provider_unavailable"
        try:
            switch_preferences("codex_cli")
        except (PreferencesFailure, AgentFailure):
            pass

    def template_import_model():
        # The capture records the selected import model with its catalog default effort; nothing is chosen here.
        from packages.resume_core.models.template_import import ModelCapture
        from packages.resume_core.template_import import digest as capture_digest
        selected = import_selected_provider()
        if selected is None:
            # A known exhausted plan is named as such; "connect a model" sent the user to Settings for nothing (D104).
            raise ProjectFailure("QUOTA_EXHAUSTED" if connection_state.quota.state == "exhausted" else "CONNECTION_REQUIRED", 409)
        provider, model = selected
        reasoning = connection_state.modelReasoning.get(model)
        effort = reasoning.default if reasoning is not None else None
        if effort is None:
            raise ProjectFailure("MODEL_DENIED", 409)
        adapter = getattr(provider, "template_adapter", "codex_cli")
        return ModelCapture(adapter=adapter, model=model, effort=effort, capabilityProfile="closed-json-v1", capabilityVersion="1",
            configurationHash=capture_digest({"adapter": adapter, "model": model, "effort": effort}))

    def template_fallback_model(primary):
        # E07: the configured fallback with its catalog default effort, captured next to the primary. An unavailable
        # fallback refuses the start instead of being replaced or dropped.
        from packages.resume_core.models.template_import import ModelCapture
        from packages.resume_core.template_import import digest as capture_digest
        try:
            model = preferences_store.load().selected_fallback_model
        except PreferencesFailure as error:
            raise ProjectFailure(error.code, 409) from None
        if model is None or model == primary.model:
            return None
        reasoning = connection_state.modelReasoning.get(model)
        effort = reasoning.default if reasoning is not None else None
        if not connection_state.metadataReady or model not in connection_state.models or effort is None:
            raise ProjectFailure("MODEL_DENIED", 409)
        return ModelCapture(adapter=primary.adapter, model=model, effort=effort, capabilityProfile="closed-json-v1",
            capabilityVersion="1", configurationHash=capture_digest({"adapter": primary.adapter, "model": model, "effort": effort}))

    def template_model_provider(model):
        # An import runs the model it captured while that model stays available, whatever Settings select later.
        try:
            selected = import_selected_provider()
        except ProjectFailure:
            selected = None
        if selected is not None and selected[1] == model:
            return selected
        # Another captured model (the fallback, or the import model before a Settings change) runs while the catalog
        # offers it; it is never replaced by a different one.
        if not connection_state.metadataReady or model not in connection_state.models:
            raise ProjectFailure("MODEL_DENIED", 409)
        if content_provider is not None and not unsafe_cleanup:
            return content_provider, model
        if experimental_ready(model) and provider is not None:
            return provider, model
        return None

    v2_pipeline = None
    if template_import_call_cap is not None:
        from packages.resume_core.template_assembly import assemble_template
        from packages.resume_core.templates.operations import derive_task
        from .importer.template_pipeline import TemplatePipeline
        from .importer.template_transport import ProviderTemplateTransport
        # Registered deterministic operations over admitted facts; unimplemented kinds stay refused.
        v2_pipeline = TemplatePipeline(ProviderTemplateTransport(import_selected_provider, temp_root,
            model_provider=template_model_provider), repository=project_repository, authority=intake.validate,
            assemble=assemble_template, derive=derive_task, wall=lambda: project_repository.clock())
    intake.configure(call_cap=template_import_call_cap,
        model=template_import_model if template_import_call_cap is not None else None,
        fallback=template_fallback_model if template_import_call_cap is not None else None,
        # CT10 (LIVE-15): three blocks at once imported CV-B in 155 s against 389 s sequentially, with no transport errors.
        concurrency=template_import_concurrency)
    intake.ready = v2_pipeline is not None

    def import_command(identifier, request_id, allow_text_rewrite):
        return intake.command(identifier, request_id, allow_text_rewrite, workspace=project_repository.read(identifier))
    projects.imports = ImportService(projects, v2_pipeline, commands=import_command)

    async def render_export(request):
        return await production_render(request, temp_root=temp_root, worker_slot=worker_slot, renderer=docx_renderer,
            cleanup_error=lifecycle_code)
    projects.exports = ExportService(projects, render_export)
    mount_template_routes(app, root=rules_store.root, intake=intake, projects=projects, problem=problem)

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
        # One cookie for /v1/ and /v2/ routes (D109); it stays HttpOnly and strictly same-site.
        response.set_cookie(boundary.cookie_name, boundary.session, httponly=True, secure=False,
                            samesite="strict", path="/")
        return response

    def rules_failure(error: RulesFailure):
        status = 409 if error.code == "RULES_STALE" else 422 if error.code in {
            "RULES_PRESETS_REQUIRED", "RULES_TOO_LARGE", "RULES_INVALID_TEXT"} else 500
        payload = RulesSettingsError.model_validate({
            "error": {"code": error.code, "retryable": False, "stage": "rules"},
            "requiredHeadings": list(PRESET_HEADINGS.values()) if error.code == "RULES_PRESETS_REQUIRED" else [],
        })
        return JSONResponse(payload.model_dump(mode="json", by_alias=True), status_code=status,
                            headers={"Cache-Control": "no-store"})

    def rules_response(captured):
        value = {**captured.model_dump(mode="json", by_alias=True), "presets": presets(captured.markdown)}
        payload = RulesSettings.model_validate(value)
        return JSONResponse(payload.model_dump(mode="json", by_alias=True), headers={"Cache-Control": "no-store"})

    @app.get("/v1/settings/rules")
    async def read_rules():
        try:
            captured = rules_store.load()
            return rules_response(captured)
        except RulesFailure as error:
            return rules_failure(error)

    @app.put("/v1/settings/rules")
    async def save_rules(request: SaveRulesRequest):
        try:
            captured = rules_store.save(request.markdown, request.base_revision)
            return rules_response(captured)
        except RulesFailure as error:
            return rules_failure(error)

    @app.get("/v1/template-package")
    async def template_package():
        try:
            manifest = require_template()
            output = BytesIO()
            with ZipFile(output, "w", compression=ZIP_STORED) as archive:
                archive.write(TEMPLATE_MANIFEST, "template/manifest.json")
                for relative in sorted(manifest["assets"]):
                    archive.write(TEMPLATE_ROOT / relative, f"template/{relative}")
            if output.tell() > 2 * 1024 * 1024:
                return problem("TEMPLATE_UNAVAILABLE", 503)
            return Response(output.getvalue(), media_type="application/zip", headers={"Cache-Control": "no-store"})
        except (RenderFailure, OSError):
            return problem("TEMPLATE_UNAVAILABLE", 503)

    login_task: asyncio.Task | None = None
    install_task: asyncio.Task | None = None

    def provider_summaries() -> list[ProviderSummary]:
        summaries = []
        for item in registry.listed():
            if item.kind not in slots:
                continue
            slot = slots[item.kind]
            executable = getattr(slot.connection, "executable", None)
            # The runtime FoldCV installed is pinned by hash, not by signature, so its file is enough here.
            installed = (connection_state.state not in {"cli_missing", "launcher_unsupported"} if item.kind == active_kind
                         else executable is not None and executable.is_file() if getattr(slot.profile, "managed", False)
                         else discovered(item, executable))
            summaries.append(ProviderSummary(kind=item.kind, display=item.display, subscription=item.subscription,
                                             publisher=item.publisher, loginCode=item.login_code, installed=installed))
        return summaries

    def connection_response() -> JSONResponse:
        state = ConnectionPayload(**(connection_state.model_dump() | {"provider": active_kind, "providers": provider_summaries(),
                                                    "providerNotice": provider_notice,
                                                    "experimentalMode": experimental_profile is not None,
                                                    "generationReady": experimental_ready(),
                                                    "installation": installation.snapshot() if installation else None}))
        return JSONResponse(state.model_dump(), headers={"Cache-Control": "no-store"})

    @app.get("/v1/settings/connection")
    async def current_connection():
        return connection_response()

    @app.get("/v1/settings/preferences")
    async def preferences():
        try:
            rules_store.load()
            value = preferences_store.load()
            return JSONResponse(value.model_dump(mode="json", by_alias=True), headers={"Cache-Control": "no-store"})
        except (PreferencesFailure, RulesFailure) as error:
            return problem(error.code, 409, "settings")

    @app.put("/v1/settings/preferences")
    async def save_analysis_preferences(payload: SaveAnalysisPreference):
        try:
            rules_store.load()
            value = preferences_store.save_analysis(payload.automatic_analysis)
            return JSONResponse(value.model_dump(mode="json", by_alias=True), headers={"Cache-Control": "no-store"})
        except (PreferencesFailure, RulesFailure) as error:
            return problem(error.code, 409, "settings")

    @app.put("/v1/settings/limits")
    async def save_limits(payload: SaveLimitsPreference):
        try:
            rules_store.load()
            value = preferences_store.save_limits(payload.import_minutes, payload.project_megabytes)
            apply_limits(value)
            return JSONResponse(value.model_dump(mode="json", by_alias=True), headers={"Cache-Control": "no-store"})
        except (PreferencesFailure, RulesFailure) as error:
            return problem(error.code, 409, "settings")

    @app.put("/v1/settings/import-model")
    async def save_import_model(payload: SaveImportModelPreference):
        async with gate:
            if payload.model is not None and (not connection_state.metadataReady or payload.model not in connection_state.models):
                return problem("MODEL_DENIED", 409, "settings")
            try:
                rules_store.load()
                value = preferences_store.select_import_model(payload.model)
                return JSONResponse(value.model_dump(mode="json", by_alias=True), headers={"Cache-Control": "no-store"})
            except (PreferencesFailure, RulesFailure) as error:
                return problem(error.code, 409, "settings")

    @app.put("/v1/settings/fallback-model")
    async def save_fallback_model(payload: SaveImportModelPreference):
        async with gate:
            if payload.model is not None and (not connection_state.metadataReady or payload.model not in connection_state.models):
                return problem("MODEL_DENIED", 409, "settings")
            try:
                rules_store.load()
                value = preferences_store.select_fallback_model(payload.model)
                return JSONResponse(value.model_dump(mode="json", by_alias=True), headers={"Cache-Control": "no-store"})
            except (PreferencesFailure, RulesFailure) as error:
                return problem(error.code, 409, "settings")

    @app.put("/v1/settings/rewrite-reasoning")
    async def save_rewrite_reasoning(payload: SelectReasoningRequest):
        async with gate:
            metadata = connection_state.modelReasoning.get(payload.model)
            if (not connection_state.metadataReady or payload.model != connection_state.selectedModel
                    or payload.effort is not None and (metadata is None or payload.effort not in metadata.supported)):
                return problem("MODEL_DENIED", 409, "settings")
            try:
                value = preferences_store.select_rewrite_reasoning(payload.model, payload.effort)
                return JSONResponse(value.model_dump(mode="json", by_alias=True), headers={"Cache-Control": "no-store"})
            except PreferencesFailure as error:
                return problem(error.code, 409, "settings")

    async def connection_job(kind: str, work):
        nonlocal active, connection_epoch, connection_state, login_task, install_task
        async with gate:
            if unsafe_cleanup:
                connection_state = ConnectionPayload(state="cleanup_blocked")
                return connection_response()
            if INFERENCE.blocked:
                connection_state = ConnectionPayload(state="cleanup_blocked")
                return connection_response()
            if INFERENCE.locked():
                return connection_response() if kind not in {"login", "install"} else problem("BUSY", 429, "host", True)
            if kind == "login" and connection_state.state != "login_required":
                return problem("LOGIN_NOT_AVAILABLE", 409, "host")
            if kind == "install" and (installation is None or connection_state.state not in {
                    "cli_missing", "unsupported_version", "launcher_unsupported"}):
                return problem("INSTALL_NOT_AVAILABLE", 409, "host")
            if cancellation_pending or active >= MAX_CONCURRENT or connection_work:
                return problem("BUSY", 429, "host", True)
            if provider is not None:
                provider.invalidate_preflight()
            active += 1
            epoch = connection_epoch
            started_kind = active_kind
            files = OperationFiles(temp_root)
            cancel = threading.Event()
            if kind == "install":
                installation.cancel = cancel
                installation.update(state="downloading", downloadedBytes=0, error=None)

            def execute():
                if kind == "install":
                    with INFERENCE.hold(cancel, deadline=time.monotonic() + 15), files.open():
                        return work(files, cancel)
                if experimental_profile is not None and not experimental_profile.executable.is_file():
                    raise ConnectionFailure("CLI_MISSING")
                try:
                    with INFERENCE.hold(cancel, deadline=time.monotonic() + 15), native_profile(
                            experimental_profile, cancel, deadline=time.monotonic() + 15, blocking=False,
                            operations_root=temp_root):
                        with files.open():
                            return work(files, cancel)
                except (ExperimentalProfileError, ClaudeProfileError) as error:
                    raise ConnectionFailure("UNSUPPORTED_VERSION" if str(error) == "CLI_UNSUPPORTED" else "METADATA_FAILED") from None

            task = asyncio.create_task(asyncio.to_thread(execute))
            operations[task] = files
            connection_work[task] = (files, cancel)
            task.add_done_callback(operation_done)
            if kind in {"login", "install"}:
                connection_epoch += 1
                epoch = connection_epoch
                assistant.stop_all()
                # A running import holds the permit and makes this BUSY; one not yet admitted would call the model
                # under the new sign-in or CLI.
                projects.imports.stop_all()
                if kind == "install":
                    install_task = task
                else:
                    login_task = task
                    connection_state = ConnectionPayload(state="login_pending", version=connection_state.version)
        try:
            result = await asyncio.shield(task)
            async with gate:
                if kind == "install":
                    slot = slots[started_kind]
                    if isinstance(result, Path) and slot.profile is not None and slot.rebind is not None:
                        slots[started_kind] = slot.rebind(slot, result)
                        if started_kind == active_kind:
                            activate(started_kind)
                        if epoch == connection_epoch:
                            connection_state = ConnectionPayload(state="unchecked")
                    return connection_response()
                if epoch != connection_epoch:
                    return connection_response()
                if kind == "login":
                    connection_state = ConnectionPayload(state="login_required", version=connection_state.version)
                    return connection_response()
                assert isinstance(result, Metadata)
                selected = connection_state.selectedModel if connection_state.selectedModel in result.models else None
                if selected is None:
                    try:
                        if not rules_store.path.exists():rules_store.load()
                        preferred = preferences_store.load().selected_model
                        if preferred in result.models:selected = preferred
                    except (PreferencesFailure, RulesFailure):
                        pass
                quota = QuotaPayload(state=result.quota.state, usedPercent=result.quota.used_percent,
                                     resetsAt=result.quota.resets_at)
                state = ("unchecked" if kind == "discover" else "quota_exhausted" if quota.state == "exhausted"
                         else "unknown_limits" if quota.state == "unknown" else "connected")
                connection_state = ConnectionPayload(state=state, version=result.version, plan=result.plan,
                                                     versionStatus=result.version_status,
                                                     models=list(result.models), selectedModel=selected, quota=quota, modelReasoning=result.reasoning,
                                                     metadataReady=kind != "discover")
                return connection_response()
        except (AdmissionTimeout, AdmissionCancelled):
            if kind == "install":
                installation.update(state="cancelled" if cancel.is_set() else "failed",
                                    error="cancelled" if cancel.is_set() else "busy")
            return connection_response()
        except AdmissionBlocked:
            if kind == "install":
                installation.update(state="failed", error="install_failed")
            INFERENCE.block()
            connection_state = ConnectionPayload(state="cleanup_blocked")
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
            if kind == "install":
                installation.update(state="failed", error="install_failed")
            lifecycle_code(error)
            async with gate:
                if unsafe_cleanup:
                    connection_state = ConnectionPayload(state="cleanup_blocked")
                elif epoch == connection_epoch:
                    connection_state = ConnectionPayload(state="metadata_failed")
                return connection_response()
        except asyncio.CancelledError:
            await stop_connection(task, files, cancel)
            if kind == "install" and installation.snapshot()["state"] in {"downloading", "verifying", "extracting"}:
                installation.update(state="cancelled", error="cancelled")
            raise
        except Exception:
            if kind == "install":
                installation.update(state="failed", error="install_failed")
            async with gate:
                if unsafe_cleanup:
                    connection_state = ConnectionPayload(state="cleanup_blocked")
                elif epoch == connection_epoch:
                    connection_state = ConnectionPayload(state="metadata_failed")
                return connection_response()
        finally:
            if login_task is task:
                login_task = None
                with login_code_lock:
                    login_code.clear()
            if install_task is task:
                install_task = None

    def inactive(payload: HostRequest) -> JSONResponse | None:
        return problem("PROVIDER_INACTIVE", 409, "host") if payload.provider not in (None, active_kind) else None

    async def discover(payload: HostRequest):
        if refused := inactive(payload):
            return refused
        return await connection_job("discover", lambda files, cancel, adapter=connection: adapter.inspect(files, cancel, full=False))

    async def status(payload: HostRequest):
        if refused := inactive(payload):
            return refused
        return await connection_job("status", lambda files, cancel, adapter=connection: adapter.inspect(files, cancel))

    async def models(payload: HostRequest):
        return await status(payload)

    login_code: list[str] = []
    login_code_lock = threading.Lock()

    def take_login_code() -> str | None:
        with login_code_lock:
            return login_code.pop() if login_code else None

    async def login(payload: HostRequest):
        if refused := inactive(payload):
            return refused
        with login_code_lock:
            login_code.clear()
        if DESCRIPTORS[active_kind].login_code:
            return await connection_job("login", lambda files, cancel, adapter=connection: adapter.login(
                files, cancel, code=take_login_code))
        return await connection_job("login", connection.login)

    async def send_login_code(payload: LoginCodeRequest):
        if refused := inactive(payload):
            return refused
        async with gate:
            if (login_task is None or login_task.done() or connection_state.state != "login_pending"
                    or not DESCRIPTORS[active_kind].login_code):
                return problem("LOGIN_NOT_AVAILABLE", 409, "host")
            with login_code_lock:
                login_code[:] = [payload.code]
            return connection_response()

    async def install_cli(payload: HostRequest):
        if refused := inactive(payload):
            return refused
        if installation is None:
            return problem("INSTALL_NOT_AVAILABLE", 409, "host")
        return await connection_job("install", lambda files, _cancel: installation.install(files))

    async def cancel_install(payload: HostRequest):
        nonlocal connection_epoch
        if refused := inactive(payload):
            return refused
        async with gate:
            current = install_task
            if current is None or current not in connection_work:
                return connection_response()
            if installation.snapshot()["state"] == "ready":
                return connection_response()
            connection_epoch += 1
            files, cancel = connection_work[current]
        code = await stop_connection(current, files, cancel)
        if installation.snapshot()["state"] in {"downloading", "verifying", "extracting"}:
            installation.update(state="cancelled", error="cancelled")
        if code is not None or unsafe_cleanup:
            return problem("PROCESS_CLEANUP_FAILED", 503, "host")
        return connection_response()

    async def select(payload: SelectModelRequest):
        nonlocal connection_state
        if refused := inactive(payload):
            return refused
        async with gate:
            if not connection_state.metadataReady or payload.model not in connection_state.models:
                return problem("MODEL_DENIED", 409, "host")
            try:
                rules_store.load()
                preferences_store.select_model(payload.model)
            except (PreferencesFailure, RulesFailure) as error:
                return problem(error.code, 409, "settings")
            connection_state = connection_state.model_copy(update={"selectedModel": payload.model})
            return connection_response()

    async def detach(payload: HostRequest):
        nonlocal connection_epoch, connection_state
        if refused := inactive(payload):
            return refused
        async with gate:
            if provider is not None:
                provider.invalidate_preflight()
            connection_epoch += 1
            connection_state = ConnectionPayload(state="detached")
            current = list(connection_work.items())
            intake.request_shutdown()
            rewrite.request_shutdown()
            projects.imports.stop_all()
            assistant.stop_all()
        codes = await asyncio.gather(*(stop_connection(task, files, cancel)
                                       for task, (files, cancel) in current))
        try:
            await intake.shutdown()
            await rewrite.shutdown()
            # No import keeps calling the model under the account that signed out.
            await projects.imports.shutdown()
        except ProjectFailure:
            unsafe_code = SpikeError("PROCESS_CLEANUP_FAILED")
            lifecycle_code(unsafe_code)
        if any(code is not None for code in codes) or unsafe_cleanup:
            connection_state = ConnectionPayload(state="cleanup_blocked")
        return connection_response()

    async def cancel_login(payload: HostRequest):
        nonlocal connection_epoch, connection_state
        if refused := inactive(payload):
            return refused
        async with gate:
            current = login_task
            if current is None or current not in connection_work:
                return connection_response()
            if provider is not None:
                provider.invalidate_preflight()
            connection_epoch += 1
            assistant.stop_all()
            connection_state = ConnectionPayload(state="login_required", version=connection_state.version)
            files, cancel = connection_work[current]
        code = await stop_connection(current, files, cancel)
        if code is not None or unsafe_cleanup:
            connection_state = ConnectionPayload(state="cleanup_blocked")
        return connection_response()

    async def select_provider(payload: SelectProviderRequest):
        nonlocal connection_epoch, connection_state, provider_notice
        if payload.provider not in {item.kind for item in registry.listed()} or payload.provider not in slots:
            return problem("PROVIDER_UNAVAILABLE", 409, "host")
        if payload.provider == active_kind:
            return connection_response()
        # A clean detach first, never a CLI logout; runs in flight stop on the provider they started on.
        detached = await detach(HostRequest())
        async with gate:
            if unsafe_cleanup or connection_state.state == "cleanup_blocked":
                return detached
            if connection_work or cancellation_pending:
                return problem("BUSY", 429, "host", True)
            try:
                rules_store.load()
                switch_preferences(payload.provider)
            except (PreferencesFailure, RulesFailure, AgentFailure) as error:
                return problem(error.code, 409, "settings")
            activate(payload.provider)
            connection_epoch += 1
            connection_state = ConnectionPayload(state="unchecked")
            provider_notice = None
            return connection_response()

    for path, handler in (("discover", discover), ("status", status), ("models", models),
                          ("login", login), ("select", select), ("detach", detach),
                          ("cancel-login", cancel_login), ("install", install_cli), ("cancel-install", cancel_install),
                          ("select-provider", select_provider), ("login-code", send_login_code)):
        app.add_api_route(f"/v1/host/{path}", handler, methods=["POST"])

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
        return FileResponse(target, headers={"Cache-Control": "no-store" if target.suffix.lower() == ".html" else "public, max-age=31536000, immutable"})

    return boundary
