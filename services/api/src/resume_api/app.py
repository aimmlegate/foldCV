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

from .host_models import (ConnectionPayload, EnableProviderRequest, ErrorEnvelope, ErrorPayload, HostRequest,
                          LoginCodeRequest, ProviderState, ProviderSummary, QuotaPayload, SelectModelRequest,
                          SelectReasoningRequest)
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
                            "host/enable", "host/login-code"})
JSON_POST_PATHS = frozenset("/v1/" + path for path in POST_ONLY_PATHS)
JSON_PUT_PATHS = frozenset({"/v1/settings/rules", "/v1/settings/assistant"})


@dataclass
class ProviderSlot:
    """One provider's connection adapter, content provider, native profile, installer and assistant runtime; a slot
    runs processes only while its provider is on (D119)."""
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
                project_upload = (path in {"/v1/rich/projects/template-input", "/v2/projects/archive"}
                    or path.startswith("/v1/rich/projects/template-input/"))
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
    connection_epoch = 0
    connection_namespace = secrets.token_hex(12)

    def bind_codex(slot, executable):
        # The connection object stays: the assistant connection and the routes read it.
        profile = ExperimentalCliProfile(slot.profile.root, executable)
        slot.connection.executable = executable
        slot.connection.experimental_profile = profile
        return ProviderSlot(slot.connection, CodexCliProvider(executable, experimental_profile=profile), profile,
                            slot.installation, CodexAgentRuntime(slot.connection, temp_root), bind_codex)

    # D119: every listed provider keeps its own connection at the same time; a model choice runs on the provider whose
    # catalog lists the model.
    slots = {"codex_cli": ProviderSlot(connection, provider, experimental_profile, installation, rebind=bind_codex),
             **(provider_slots or {})}
    states = {kind: ProviderState(state="unchecked") for kind in slots}
    # Bumped by sign-in, install and detach of that provider: a connection reply started before is dropped.
    epochs = {kind: 0 for kind in slots}
    connection_kinds: dict[asyncio.Task, str] = {}
    preferences_store = PreferencesStore(rules_store.root)

    def stored_preferences():
        try:
            return preferences_store.load() if preferences_store.path.exists() else None
        except PreferencesFailure:
            return None

    stored = stored_preferences()
    enabled = set(stored.enabled_providers if stored is not None else ("codex_cli",))
    try:
        apply_limits(preferences_store.load() if preferences_store.path.exists() else None)
    except PreferencesFailure:
        apply_limits(None)

    def kinds():
        return [item.kind for item in registry.listed() if item.kind in slots]

    def on(kind):
        return kind in enabled and kind in kinds()

    def busy(kind):
        return any(connection_kinds.get(task) == kind and not task.done() for task in connection_work)

    def catalog():
        """Each offered model with its provider, over every provider that is on and has its catalog. A name a provider
        listed first stays with that one; names do not overlap (Claude's catalog is a fixed list)."""
        owners = {}
        for kind in kinds():
            if on(kind) and states[kind].metadataReady:
                for model in states[kind].models:
                    owners.setdefault(model, kind)
        return owners

    def catalog_reasoning(owners=None):
        owners = catalog() if owners is None else owners
        return {model: states[kind].modelReasoning[model] for model, kind in owners.items()
                if model in states[kind].modelReasoning}

    def reasoning_of(model):
        return catalog_reasoning().get(model)

    def processing_model():
        value = stored_preferences()
        return value.selected_model if value is not None else None

    def connected(kind):
        state = states[kind]
        return (on(kind) and not unsafe_cleanup and not INFERENCE.blocked and state.state == "connected"
                and state.metadataReady and state.quota.state in USABLE_QUOTA)

    def usable(kind):
        # Structured generation also needs the provider's native profile; the assistant has its own runtime.
        return connected(kind) and slots[kind].profile is not None

    def experimental_ready(model=None) -> bool:
        kind = catalog().get(model or processing_model())
        return kind is not None and usable(kind) and not busy(kind)

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

    @asynccontextmanager
    async def model_slot(cancel):
        # A rewrite waits in the inference admission, not for one of the local workers uploads and exports need (D121).
        async with gate:
            if unsafe_cleanup:
                raise SpikeError("PROCESS_CLEANUP_FAILED")
            if cancel.is_set():
                raise AdmissionCancelled()
        yield

    def provider_for(model):
        """The provider that runs a catalog model now, with the model; None while that provider cannot run it."""
        if content_provider is not None and not unsafe_cleanup:
            return content_provider, model
        kind = catalog().get(model)
        if kind is not None and experimental_ready(model) and slots[kind].provider is not None:
            return slots[kind].provider, model
        return None

    def selected_provider():
        model = processing_model()
        if content_provider is not None and not unsafe_cleanup:
            return content_provider, (model if model in catalog() else None) or "fixture"
        return provider_for(model) if model is not None else None

    def chosen_provider(model):
        """The provider for a model chosen in preferences; None follows the processing model."""
        if model is None:
            return selected_provider()
        if model not in catalog():
            raise ProjectFailure("MODEL_DENIED", 409)
        return provider_for(model)

    def preferred_provider(field):
        try:
            model = getattr(preferences_store.load(), field)
        except PreferencesFailure as error:
            raise ProjectFailure(error.code, 409) from None
        return chosen_provider(model)

    def import_selected_provider():
        return preferred_provider("selected_import_model")

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
    rewrite = TemplateRewrite(lambda: preferred_provider("selected_rewrite_model"), preferences=preferences_store,
        temp_root=temp_root, worker_slot=model_slot, cleanup_error=lifecycle_code, reasoning=reasoning_of)
    projects.rewrite_text, projects.rewrite_cancel = rewrite.text, rewrite.cancel
    mount_projects_v2(app, projects)

    from .assistant.runs import AgentConnection, AssistantService
    from .assistant.routes import mount_assistant

    def agent_connection():
        owners = catalog()
        ready_kinds = {kind for kind in kinds() if connected(kind) and not busy(kind)}
        listed = [kind for kind in kinds() if on(kind)]
        reason = ("AGENT_CLEANUP_FAILED" if unsafe_cleanup or INFERENCE.blocked else
            "AGENT_AUTH_REQUIRED" if any(states[kind].state in {"login_required", "login_pending", "detached"} for kind in listed) else
            "AGENT_QUOTA" if any(states[kind].quota.state == "exhausted" for kind in listed) else "AGENT_CONNECTION_UNAVAILABLE")
        ready = bool(ready_kinds)
        # A ready assistant offers the models of the providers that can run now; a model of another one is unavailable.
        models = tuple(model for model, kind in owners.items() if not ready or kind in ready_kinds)
        return AgentConnection(ready, models, "connection_" + connection_namespace + "_" + str(connection_epoch),
            None if ready else reason, catalog_reasoning(owners))

    resolved_agent_runtime = agent_runtime
    if resolved_agent_runtime is None and experimental_profile is not None:
        try:
            resolved_agent_runtime = CodexAgentRuntime(connection, temp_root)
        except AgentFailure:
            resolved_agent_runtime = None
    assistant = AssistantService(projects, resolved_agent_runtime, agent_connection)
    slots["codex_cli"].runtime = resolved_agent_runtime
    # The assistant runs on the runtime of its model's provider; an injected test runtime serves every provider.
    assistant.runtime_for = lambda model: (agent_runtime if agent_runtime is not None
                                           else slots[catalog().get(model, "codex_cli")].runtime)
    projects.on_deleted = assistant.project_deleted
    app.state.assistant = assistant
    mount_assistant(app, assistant)

    def template_import_model(effort=None):
        # The capture records the selected import model with the effort the import start chose, else its catalog
        # default; a chosen effort the catalog does not offer for the model refuses the start.
        from packages.resume_core.models.template_import import ModelCapture
        from packages.resume_core.template_import import digest as capture_digest
        selected = import_selected_provider()
        if selected is None:
            # A known exhausted plan is named as such; "connect a model" sent the user to Settings for nothing (D104).
            stored = stored_preferences()
            kind = catalog().get((stored.selected_import_model if stored else None) or processing_model())
            # Without a chosen model, the plan is named when every provider that is on has used it up.
            exhausted = ([kind] if kind else [item for item in kinds() if on(item) and states[item].metadataReady])
            raise ProjectFailure("QUOTA_EXHAUSTED" if exhausted and all(states[item].quota.state == "exhausted"
                                                                        for item in exhausted)
                                 else "CONNECTION_REQUIRED", 409)
        provider, model = selected
        reasoning = reasoning_of(model)
        if effort is not None and (reasoning is None or effort not in reasoning.supported):
            raise ProjectFailure("IMPORT_EFFORT_UNSUPPORTED", 409)
        effort = effort or (reasoning.default if reasoning is not None else None)
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
        reasoning = reasoning_of(model)
        effort = reasoning.default if reasoning is not None else None
        if model not in catalog() or effort is None:
            raise ProjectFailure("MODEL_DENIED", 409)
        # The fallback may be another provider's model (D119); the capture names the adapter that runs it.
        selected = provider_for(model)
        adapter = getattr(selected[0], "template_adapter", "codex_cli") if selected else catalog()[model]
        return ModelCapture(adapter=adapter, model=model, effort=effort, capabilityProfile="closed-json-v1",
            capabilityVersion="1", configurationHash=capture_digest({"adapter": adapter, "model": model, "effort": effort}))

    def template_model_provider(model):
        # An import runs the model it captured while that model stays available, whatever Settings select later.
        try:
            selected = import_selected_provider()
        except ProjectFailure:
            selected = None
        if selected is not None and selected[1] == model:
            return selected
        # Another captured model (the fallback, or the import model before a Settings change) runs on its own provider
        # while that provider's catalog offers it; it is never replaced by a different one.
        if model not in catalog():
            raise ProjectFailure("MODEL_DENIED", 409)
        return provider_for(model)

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

    def import_command(identifier, request_id, allow_text_rewrite, effort=None):
        return intake.command(identifier, request_id, allow_text_rewrite, effort, workspace=project_repository.read(identifier))
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
        connection_kinds.pop(done, None)
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

    login_tasks: dict[str, asyncio.Task] = {}
    install_tasks: dict[str, asyncio.Task] = {}

    def provider_summaries() -> list[ProviderSummary]:
        summaries = []
        for item in registry.listed():
            if item.kind not in slots:
                continue
            slot, state = slots[item.kind], states[item.kind]
            executable = getattr(slot.connection, "executable", None)
            # The runtime FoldCV installed is pinned by hash, not by signature, so its file is enough here.
            installed = (state.state not in {"cli_missing", "launcher_unsupported"} if on(item.kind)
                         else executable is not None and executable.is_file() if getattr(slot.profile, "managed", False)
                         else discovered(item, executable))
            summaries.append(ProviderSummary(**state.model_dump(), kind=item.kind, display=item.display,
                                             subscription=item.subscription, publisher=item.publisher,
                                             loginCode=item.login_code, installed=installed, enabled=on(item.kind),
                                             installation=slot.installation.snapshot() if slot.installation else None))
        return summaries

    def connection_response(kind=None) -> JSONResponse:
        # The top level names one provider (the request's, else the first that is on) and combines the catalogs.
        kind = kind or next((item for item in kinds() if on(item)), "codex_cli")
        owners, model = catalog(), processing_model()
        state, slot = states[kind], slots[kind]
        payload = ConnectionPayload(provider=kind, providers=provider_summaries(), state=state.state, version=state.version,
                                    versionStatus=state.versionStatus, plan=state.plan, quota=state.quota,
                                    installation=slot.installation.snapshot() if slot.installation else None,
                                    models=list(owners), modelReasoning=catalog_reasoning(owners),
                                    selectedModel=model if model in owners else None, metadataReady=bool(owners),
                                    generationReady=experimental_ready(),
                                    experimentalMode=any(slots[item].profile is not None for item in kinds()))
        return JSONResponse(payload.model_dump(), headers={"Cache-Control": "no-store"})

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
            if payload.model is not None and payload.model not in catalog():
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
            if payload.model is not None and payload.model not in catalog():
                return problem("MODEL_DENIED", 409, "settings")
            try:
                rules_store.load()
                value = preferences_store.select_fallback_model(payload.model)
                return JSONResponse(value.model_dump(mode="json", by_alias=True), headers={"Cache-Control": "no-store"})
            except (PreferencesFailure, RulesFailure) as error:
                return problem(error.code, 409, "settings")

    @app.put("/v1/settings/rewrite-model")
    async def save_rewrite_model(payload: SaveImportModelPreference):
        async with gate:
            owners = catalog()
            if not owners or payload.model is not None and payload.model not in owners:
                return problem("MODEL_DENIED", 409, "settings")
            metadata = reasoning_of(payload.model or processing_model() or "")
            try:
                rules_store.load()
                value = preferences_store.select_rewrite_model(payload.model, set(metadata.supported if metadata else ()))
                return JSONResponse(value.model_dump(mode="json", by_alias=True), headers={"Cache-Control": "no-store"})
            except (PreferencesFailure, RulesFailure) as error:
                return problem(error.code, 409, "settings")

    @app.put("/v1/settings/rewrite-reasoning")
    async def save_rewrite_reasoning(payload: SelectReasoningRequest):
        async with gate:
            metadata = reasoning_of(payload.model)
            # The store checks the model against the rewrite model, which follows the processing model when unset.
            if (payload.model not in catalog()
                    or payload.effort is not None and (metadata is None or payload.effort not in metadata.supported)):
                return problem("MODEL_DENIED", 409, "settings")
            try:
                value = preferences_store.select_rewrite_reasoning(payload.model, payload.effort)
                return JSONResponse(value.model_dump(mode="json", by_alias=True), headers={"Cache-Control": "no-store"})
            except PreferencesFailure as error:
                return problem(error.code, 409, "settings")

    async def connection_job(job: str, kind: str, work):
        nonlocal active, connection_epoch
        slot = slots[kind]
        installation = slot.installation
        async with gate:
            if unsafe_cleanup or INFERENCE.blocked:
                states[kind] = ProviderState(state="cleanup_blocked")
                return connection_response(kind)
            if INFERENCE.locked():
                return connection_response(kind) if job not in {"login", "install"} else problem("BUSY", 429, "host", True)
            if job == "login" and states[kind].state != "login_required":
                return problem("LOGIN_NOT_AVAILABLE", 409, "host")
            if job == "install" and (installation is None or states[kind].state not in {
                    "cli_missing", "unsupported_version", "launcher_unsupported"}):
                return problem("INSTALL_NOT_AVAILABLE", 409, "host")
            # One connection job per provider; the other provider's checks go on.
            if cancellation_pending or active >= MAX_CONCURRENT or busy(kind):
                return problem("BUSY", 429, "host", True)
            if slot.provider is not None:
                slot.provider.invalidate_preflight()
            active += 1
            epoch = epochs[kind]
            profile = slot.profile
            files = OperationFiles(temp_root)
            cancel = threading.Event()
            if job == "install":
                installation.cancel = cancel
                installation.update(state="downloading", downloadedBytes=0, error=None)

            def execute():
                if job == "install":
                    with INFERENCE.hold(cancel, deadline=time.monotonic() + 15, exclusive=True), files.open():
                        return work(files, cancel)
                if profile is not None and not profile.executable.is_file():
                    raise ConnectionFailure("CLI_MISSING")
                try:
                    with INFERENCE.hold(cancel, deadline=time.monotonic() + 15, exclusive=True), native_profile(
                            profile, cancel, deadline=time.monotonic() + 15, blocking=False,
                            operations_root=temp_root):
                        with files.open():
                            return work(files, cancel)
                except (ExperimentalProfileError, ClaudeProfileError) as error:
                    raise ConnectionFailure("UNSUPPORTED_VERSION" if str(error) == "CLI_UNSUPPORTED" else "METADATA_FAILED") from None

            task = asyncio.create_task(asyncio.to_thread(execute))
            operations[task] = files
            connection_work[task] = (files, cancel)
            connection_kinds[task] = kind
            task.add_done_callback(operation_done)
            if job in {"login", "install"}:
                connection_epoch += 1
                epochs[kind] += 1
                epoch = epochs[kind]
                # An import may use both providers, so a new sign-in or CLI on either stops all model work.
                assistant.stop_all()
                # A running import holds the permit and makes this BUSY; one not yet admitted would call the model
                # under the new sign-in or CLI.
                projects.imports.stop_all()
                if job == "install":
                    install_tasks[kind] = task
                else:
                    login_tasks[kind] = task
                    states[kind] = ProviderState(state="login_pending", version=states[kind].version)
        try:
            result = await asyncio.shield(task)
            async with gate:
                if job == "install":
                    current = slots[kind]
                    if isinstance(result, Path) and current.profile is not None and current.rebind is not None:
                        slots[kind] = current.rebind(current, result)
                        if epoch == epochs[kind]:
                            states[kind] = ProviderState(state="unchecked")
                    return connection_response(kind)
                if epoch != epochs[kind]:
                    return connection_response(kind)
                if job == "login":
                    states[kind] = ProviderState(state="login_required", version=states[kind].version)
                    return connection_response(kind)
                assert isinstance(result, Metadata)
                quota = QuotaPayload(state=result.quota.state, usedPercent=result.quota.used_percent,
                                     resetsAt=result.quota.resets_at)
                state = ("unchecked" if job == "discover" else "quota_exhausted" if quota.state == "exhausted"
                         else "unknown_limits" if quota.state == "unknown" else "connected")
                states[kind] = ProviderState(state=state, version=result.version, plan=result.plan,
                                             versionStatus=result.version_status, models=list(result.models), quota=quota,
                                             modelReasoning=result.reasoning, metadataReady=job != "discover")
                return connection_response(kind)
        except (AdmissionTimeout, AdmissionCancelled):
            if job == "install":
                installation.update(state="cancelled" if cancel.is_set() else "failed",
                                    error="cancelled" if cancel.is_set() else "busy")
            return connection_response(kind)
        except AdmissionBlocked:
            if job == "install":
                installation.update(state="failed", error="install_failed")
            INFERENCE.block()
            states[kind] = ProviderState(state="cleanup_blocked")
            return connection_response(kind)
        except ConnectionFailure as error:
            if error.code in {"PROCESS_CLEANUP_FAILED", "CLEANUP_FAILED"}:
                lifecycle_code(SpikeError(error.code))
            async with gate:
                if unsafe_cleanup:
                    states[kind] = ProviderState(state="cleanup_blocked")
                    return connection_response(kind)
                if epoch != epochs[kind]:
                    return connection_response(kind)
                mapped = {"CLI_MISSING": "cli_missing", "CLI_LAUNCH_UNSUPPORTED": "launcher_unsupported",
                          "UNSUPPORTED_VERSION": "unsupported_version",
                          "LOGIN_REQUIRED": "login_required", "API_KEY_MODE": "api_key_mode",
                          "METADATA_FAILED": "metadata_failed"}
                state = mapped.get(error.code, "login_failed" if job == "login" else "metadata_failed")
                states[kind] = ProviderState(state=state, version=error.version)
                return connection_response(kind)
        except SpikeError as error:
            if job == "install":
                installation.update(state="failed", error="install_failed")
            lifecycle_code(error)
            async with gate:
                if unsafe_cleanup:
                    states[kind] = ProviderState(state="cleanup_blocked")
                elif epoch == epochs[kind]:
                    states[kind] = ProviderState(state="metadata_failed")
                return connection_response(kind)
        except asyncio.CancelledError:
            await stop_connection(task, files, cancel)
            if job == "install" and installation.snapshot()["state"] in {"downloading", "verifying", "extracting"}:
                installation.update(state="cancelled", error="cancelled")
            raise
        except Exception:
            if job == "install":
                installation.update(state="failed", error="install_failed")
            async with gate:
                if unsafe_cleanup:
                    states[kind] = ProviderState(state="cleanup_blocked")
                elif epoch == epochs[kind]:
                    states[kind] = ProviderState(state="metadata_failed")
                return connection_response(kind)
        finally:
            if login_tasks.get(kind) is task:
                del login_tasks[kind]
                with login_code_lock:
                    login_codes.pop(kind, None)
            if install_tasks.get(kind) is task:
                del install_tasks[kind]

    def target(payload: HostRequest):
        """The provider a host request is for (None is Codex), with the refusal when it is not listed or is off."""
        kind = payload.provider or "codex_cli"
        if kind not in kinds():
            return kind, problem("PROVIDER_UNAVAILABLE", 409, "host")
        return kind, None if on(kind) else problem("PROVIDER_INACTIVE", 409, "host")

    async def discover(payload: HostRequest):
        kind, refused = target(payload)
        if refused:
            return refused
        return await connection_job("discover", kind, lambda files, cancel, adapter=slots[kind].connection:
                                    adapter.inspect(files, cancel, full=False))

    async def status(payload: HostRequest):
        kind, refused = target(payload)
        if refused:
            return refused
        return await connection_job("status", kind, lambda files, cancel, adapter=slots[kind].connection:
                                    adapter.inspect(files, cancel))

    async def models(payload: HostRequest):
        return await status(payload)

    login_codes: dict[str, list[str]] = {}
    login_code_lock = threading.Lock()

    async def login(payload: HostRequest):
        kind, refused = target(payload)
        if refused:
            return refused
        with login_code_lock:
            login_codes[kind] = []
        adapter = slots[kind].connection
        if DESCRIPTORS[kind].login_code:
            def take_login_code() -> str | None:
                with login_code_lock:
                    codes = login_codes.get(kind)
                    return codes.pop() if codes else None
            return await connection_job("login", kind, lambda files, cancel: adapter.login(files, cancel, code=take_login_code))
        return await connection_job("login", kind, adapter.login)

    async def send_login_code(payload: LoginCodeRequest):
        kind, refused = target(payload)
        if refused:
            return refused
        async with gate:
            task = login_tasks.get(kind)
            if (task is None or task.done() or states[kind].state != "login_pending"
                    or not DESCRIPTORS[kind].login_code):
                return problem("LOGIN_NOT_AVAILABLE", 409, "host")
            with login_code_lock:
                login_codes[kind] = [payload.code]
            return connection_response(kind)

    async def install_cli(payload: HostRequest):
        kind, refused = target(payload)
        if refused:
            return refused
        installation = slots[kind].installation
        if installation is None:
            return problem("INSTALL_NOT_AVAILABLE", 409, "host")
        return await connection_job("install", kind, lambda files, _cancel: installation.install(files))

    async def cancel_install(payload: HostRequest):
        nonlocal connection_epoch
        kind, refused = target(payload)
        if refused:
            return refused
        installation = slots[kind].installation
        async with gate:
            current = install_tasks.get(kind)
            if current is None or current not in connection_work:
                return connection_response(kind)
            if installation.snapshot()["state"] == "ready":
                return connection_response(kind)
            connection_epoch += 1
            epochs[kind] += 1
            files, cancel = connection_work[current]
        code = await stop_connection(current, files, cancel)
        if installation.snapshot()["state"] in {"downloading", "verifying", "extracting"}:
            installation.update(state="cancelled", error="cancelled")
        if code is not None or unsafe_cleanup:
            return problem("PROCESS_CLEANUP_FAILED", 503, "host")
        return connection_response(kind)

    async def select(payload: SelectModelRequest):
        # The processing model may be any provider's model; it runs on the provider that lists it.
        kind, refused = target(payload)
        if refused:
            return refused
        async with gate:
            if payload.model not in catalog():
                return problem("MODEL_DENIED", 409, "host")
            try:
                rules_store.load()
                preferences_store.select_model(payload.model)
            except (PreferencesFailure, RulesFailure) as error:
                return problem(error.code, 409, "settings")
            return connection_response(kind)

    async def stop_provider(kind, state):
        """A clean detach of one provider, never a CLI logout. Model work in flight stops whatever it runs on: an import
        may use both providers."""
        nonlocal connection_epoch
        async with gate:
            if slots[kind].provider is not None:
                slots[kind].provider.invalidate_preflight()
            connection_epoch += 1
            epochs[kind] += 1
            states[kind] = ProviderState(state=state)
            current = [(task, files, cancel) for task, (files, cancel) in connection_work.items()
                       if connection_kinds.get(task) == kind]
            intake.request_shutdown()
            rewrite.request_shutdown()
            projects.imports.stop_all()
            assistant.stop_all()
        codes = await asyncio.gather(*(stop_connection(task, files, cancel) for task, files, cancel in current))
        try:
            await intake.shutdown()
            await rewrite.shutdown()
            # No import keeps calling the model under the account that signed out.
            await projects.imports.shutdown()
        except ProjectFailure:
            lifecycle_code(SpikeError("PROCESS_CLEANUP_FAILED"))
        if any(code is not None for code in codes) or unsafe_cleanup:
            states[kind] = ProviderState(state="cleanup_blocked")
        return connection_response(kind)

    async def detach(payload: HostRequest):
        kind, refused = target(payload)
        if refused:
            return refused
        return await stop_provider(kind, "detached")

    async def cancel_login(payload: HostRequest):
        nonlocal connection_epoch
        kind, refused = target(payload)
        if refused:
            return refused
        async with gate:
            current = login_tasks.get(kind)
            if current is None or current not in connection_work:
                return connection_response(kind)
            if slots[kind].provider is not None:
                slots[kind].provider.invalidate_preflight()
            connection_epoch += 1
            epochs[kind] += 1
            assistant.stop_all()
            states[kind] = ProviderState(state="login_required", version=states[kind].version)
            files, cancel = connection_work[current]
        code = await stop_connection(current, files, cancel)
        if code is not None or unsafe_cleanup:
            states[kind] = ProviderState(state="cleanup_blocked")
        return connection_response(kind)

    async def enable(payload: EnableProviderRequest):
        kind = payload.provider
        if kind not in kinds():
            return problem("PROVIDER_UNAVAILABLE", 409, "host")
        if payload.enabled == on(kind):
            return connection_response(kind)
        if not payload.enabled:
            stopped = await stop_provider(kind, "unchecked")
            if states[kind].state == "cleanup_blocked":
                return stopped
        async with gate:
            try:
                rules_store.load()
                preferences_store.enable_provider(kind, payload.enabled)
            except (PreferencesFailure, RulesFailure) as error:
                return problem(error.code, 409, "settings")
            if payload.enabled:
                enabled.add(kind)
            else:
                enabled.discard(kind)
            epochs[kind] += 1
            states[kind] = ProviderState(state="unchecked")
            return connection_response(kind)

    for path, handler in (("discover", discover), ("status", status), ("models", models),
                          ("login", login), ("select", select), ("detach", detach),
                          ("cancel-login", cancel_login), ("install", install_cli), ("cancel-install", cancel_install),
                          ("enable", enable), ("login-code", send_login_code)):
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
