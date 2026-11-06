"""Same-origin local service: the V7 workbench, its settings and the model connection."""

from __future__ import annotations

import asyncio
from concurrent.futures import ThreadPoolExecutor
from collections.abc import Callable
from dataclasses import dataclass
from contextlib import asynccontextmanager
from http.cookies import SimpleCookie
import json
from pathlib import Path
import secrets
import time

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import FileResponse, JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException
from pydantic import ValidationError

from .host_models import ErrorEnvelope, ErrorPayload, ProviderState
from .lifecycle import has_blocked_owned, reap_owned
from .providers.codex.connection import ConnectionAdapter
from .providers.codex.profile import ExperimentalCliProfile
from .cli.installation import CliInstallation
from . import release_checks
from .providers.codex.content import CodexCliProvider
from .providers.registry import DESCRIPTORS, ProviderRegistry
from .providers.base import ConnectionPort, ContentPort, ProfilePort
from .agent.base import AgentRuntime
from .extracting import MAX_BODY as MAX_EXTRACT_BODY
from packages.resume_core.rules import RulesStore
from .projects.errors import ProjectFailure
from packages.resume_core.repository.preferences import PreferencesStore, PreferencesFailure
from packages.resume_core.project_limits import ARCHIVE_BYTES, apply_preferences as apply_limits
from packages.resume_core.templates.loading import CONFIG_BYTES
from .profile_ownership import recover_profile
from .host.connections import HostConnections
from .host.routes import mount_host_routes
from .settings_routes import SettingsContext, mount_settings_routes
from packages.resume_core.repository.assistant_store import AgentFailure
from .providers.codex.runtime import CodexAgentRuntime


MAX_BODY = 1_048_576
MAX_CONCURRENT = 2
BODY_TIMEOUT_SECONDS = 10
# A connection check waits this long behind model work, then answers BUSY.
CHECK_WAIT_SECONDS = 30
# A sign-in or install stops model work first and waits for it; the longest stop wait of that work.
MODEL_STOP_SECONDS = 65
POST_ONLY_PATHS = frozenset({"session/exchange", "host/discover", "host/status", "host/login", "host/detach", "host/models",
                            "host/select", "host/cancel-login", "host/install", "host/cancel-install",
                            "host/release-check", "host/enable", "host/login-code"})
JSON_POST_PATHS = frozenset("/v1/" + path for path in POST_ONLY_PATHS)
TEMPLATE_CONFIG_PATH = "/v1/rich/template-config/"
TEMPLATE_ASSISTANT_PATH = "/v2/templates/assistant/"
TEMPLATE_SAMPLES_PATH = TEMPLATE_ASSISTANT_PATH + "samples"


@dataclass
class ProviderSlot:
    """One provider's connection adapter, content provider, native profile, installer and assistant runtime; a slot
    runs processes only while its provider is on (D119)."""
    connection: ConnectionPort
    provider: ContentPort | None = None
    profile: ProfilePort | None = None
    installation: CliInstallation | None = None
    runtime: AgentRuntime | None = None
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


def takes_json(method: str, path: str) -> bool:
    """Every /v1/ PUT and every template-config write has one strict JSON body; the other /v1/ POSTs that do are listed."""
    return ((method == "POST" and path in JSON_POST_PATHS) or (method == "PUT" and path.startswith("/v1/"))
            or (method in {"POST", "PUT"} and template_config(path)))


def template_config(path: str) -> bool:
    return path.startswith(TEMPLATE_CONFIG_PATH) or path == TEMPLATE_CONFIG_PATH.rstrip("/")


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
                project_upload = (path in {"/v1/rich/projects/template-input", "/v2/projects/archive", TEMPLATE_SAMPLES_PATH}
                    or path.startswith("/v1/rich/projects/template-input/"))
                body_limit = (ARCHIVE_BYTES + 4096 if path == "/v2/projects/archive" else MAX_EXTRACT_BODY if project_upload
                    else MAX_BODY)
                if path.startswith("/v2/projects/") and path.endswith("/edits"):
                    # A preparation is bounded to 1 MiB; the envelope adds the token and the base revision.
                    body_limit = MAX_BODY + 64 * 1024
                if template_config(path):
                    # The compiler's own limit, plus the JSON escapes of a text of that size (its line ends and quotes).
                    body_limit = 2 * CONFIG_BYTES
                if size > body_limit:
                    await problem("INPUT_TOO_LARGE", 413)(scope, receive, send)
                    return
                chunks.append(part)
                if not message.get("more_body", False):
                    break
            body = b"".join(chunks)
            project_json = ((path.startswith("/v2/projects") and path != "/v2/projects/archive")
                or (path.startswith(TEMPLATE_ASSISTANT_PATH) and path != TEMPLATE_SAMPLES_PATH))
            if takes_json(method, path) or project_json:
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

    @asynccontextmanager
    async def lifespan(_app: FastAPI):
        # Externalizes import records of files written before D104, once; old job, agent and V6 files stay untouched.
        await asyncio.to_thread(project_repository.start)
        yield
        intake.request_shutdown()
        rewrite.request_shutdown()
        projects.imports.stop_all()
        await assistant.shutdown()
        await template_assistant.shutdown()
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
    from packages.resume_core.project_limits import RENDER_WORKERS
    from .rendering import TemplateDocxRenderer
    render_executor = ThreadPoolExecutor(max_workers=RENDER_WORKERS, thread_name_prefix="foldcv-render")
    docx_renderer = TemplateDocxRenderer(executor=render_executor)
    connection = connection_adapter or ConnectionAdapter(experimental_profile.executable if experimental_profile else cli_executable,
                                                          experimental_profile=experimental_profile)
    provider = (CodexCliProvider(experimental_profile.executable, experimental_profile=experimental_profile)
                if experimental_profile else None)
    installation = (CliInstallation(experimental_profile.root.parent / "cli-runtime",
                                    qualify=release_checks.codex(experimental_profile.root))
                    if experimental_profile else None)

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
    # The connection state and its functions (MT06); the closures below keep using them under their names.
    host = HostConnections(registry=registry, slots=slots, states=states, epochs=epochs, connection_kinds=connection_kinds,
                           temp_root=temp_root, preferences_store=preferences_store, rules_store=rules_store,
                           content_provider=content_provider, unsafe_cleanup=blocked_on_start, problem=problem,
                           max_concurrent=lambda: MAX_CONCURRENT, model_stop_seconds=lambda: MODEL_STOP_SECONDS,
                           check_wait_seconds=lambda: CHECK_WAIT_SECONDS)
    operations, connection_work = host.operations, host.connection_work
    stored_preferences, catalog, reasoning_of, processing_model = (host.stored_preferences, host.catalog,
                                                                   host.reasoning_of, host.processing_model)
    worker_slot, model_slot, lifecycle_code = host.worker_slot, host.model_slot, host.lifecycle_code
    provider_for, preferred_provider, unavailable_code = host.provider_for, host.preferred_provider, host.unavailable_code
    import_selected_provider, agent_connection = host.import_selected_provider, host.agent_connection
    cancel_operation, stop_connection = host.cancel_operation, host.stop_connection

    stored = stored_preferences()
    enabled = set(stored.enabled_providers if stored is not None else ("codex_cli",))
    host.enabled = enabled
    try:
        apply_limits(preferences_store.load() if preferences_store.path.exists() else None)
    except PreferencesFailure:
        apply_limits(None)

    from packages.resume_core.repository.project_repository import ProjectRepository
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
    from packages.resume_core.repository.focus_icons import FocusIconStore
    projects = ProjectService(project_repository, icons=FocusIconStore(rules_store.root))
    app.state.projects = projects
    intake = TemplateIntake(project_repository, temp_root=temp_root, worker_slot=worker_slot, cleanup_error=lifecycle_code,
        **({"clock": clock} if clock is not None else {}))
    app.state.intake = intake
    rewrite = TemplateRewrite(lambda: preferred_provider("selected_rewrite_model"), preferences=preferences_store,
        temp_root=temp_root, worker_slot=model_slot, cleanup_error=lifecycle_code, reasoning=reasoning_of,
        unavailable=lambda: unavailable_code("selected_rewrite_model"))
    projects.rewrite_text, projects.rewrite_cancel = rewrite.text, rewrite.cancel
    mount_projects_v2(app, projects)

    from .assistant.runs import AssistantService
    from .assistant.routes import mount_assistant, mount_template_assistant
    from .assistant.template_tools import TemplateScope

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
    # The template assistant (D141) has no project repository, so its tools cannot reach a resume.
    template_assistant = AssistantService(None, resolved_agent_runtime, agent_connection,
        scope=TemplateScope(rules_store.root), root=rules_store.root)
    template_assistant.runtime_for = assistant.runtime_for
    app.state.template_assistant = template_assistant
    # The services sign-in, install and detach stop.
    host.intake, host.rewrite, host.projects = intake, rewrite, projects
    host.assistant, host.template_assistant = assistant, template_assistant
    mount_assistant(app, assistant, companions=(template_assistant,))
    mount_template_assistant(app, template_assistant, problem=problem, temp_root=temp_root, worker_slot=worker_slot,
        cleanup_error=lifecycle_code)

    def template_import_model(effort=None):
        # The capture records the selected import model with the effort the import start chose, else its catalog
        # default; a chosen effort the catalog does not offer for the model refuses the start.
        from packages.resume_core.models.template_import import ModelCapture
        from packages.resume_core.importing.template_import import digest as capture_digest
        selected = import_selected_provider()
        if selected is None:
            raise ProjectFailure(unavailable_code("selected_import_model"), 409)
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
        from packages.resume_core.importing.template_import import digest as capture_digest
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
        from packages.resume_core.importing.template_assembly import assemble_template
        from packages.resume_core.templates.operations import derive_task
        from .importer.template_pipeline import TemplatePipeline
        from .importer.template_transport import ProviderTemplateTransport
        # Registered deterministic operations over admitted facts; unimplemented kinds stay refused.
        # The Focus icons the user chose are read when the document is assembled (D122).
        v2_pipeline = TemplatePipeline(ProviderTemplateTransport(import_selected_provider, temp_root,
            model_provider=template_model_provider), repository=project_repository, authority=intake.validate,
            assemble=lambda workspace, operation: assemble_template(workspace, operation,
                remembered=projects.remembered_icons()),
            derive=derive_task, wall=lambda: project_repository.clock())
    intake.configure(call_cap=template_import_call_cap,
        model=template_import_model if template_import_call_cap is not None else None,
        fallback=template_fallback_model if template_import_call_cap is not None else None,
        # Measured live: three blocks at once imported a QA resume in 155 s against 389 s sequentially, with no
        # transport errors.
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

    mount_settings_routes(app, SettingsContext(rules_store, preferences_store, host.gate, catalog, reasoning_of,
                                               processing_model, host.connection_response, problem))
    mount_host_routes(app, host)

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
