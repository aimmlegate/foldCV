"""The model connections of the service: provider state, the shared worker and model slots, and the host
operations (discover, status, sign-in, install, select, detach, enable) the Settings page calls."""

from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager
from pathlib import Path
import secrets
import threading
import time

from packages.resume_core.preferences import PreferencesFailure
from packages.resume_core.rules import RulesFailure

from ..providers.codex.profile import ExperimentalProfileError
from ..providers.claude.profile import ClaudeProfileError
from ..providers.base import ConnectionFailure, Metadata
from ..host_models import (ConnectionPayload, EnableProviderRequest, HostRequest, LoginCodeRequest, ProviderState,
                           ProviderSummary, QuotaPayload, SelectModelRequest)
from ..inference_admission import INFERENCE, AdmissionBlocked, AdmissionCancelled, AdmissionTimeout
from ..lifecycle import OperationFiles, SpikeError
from ..profile_ownership import native_profile
from ..projects.errors import ProjectFailure
from ..providers.registry import DESCRIPTORS, discovered

from fastapi.responses import JSONResponse

CANCEL_GRACE_SECONDS = 0.5
# "not_provided": the provider has no sanctioned usage read (decision 15); runs stay allowed.
USABLE_QUOTA = frozenset({"available", "not_provided"})


class HostConnections:
    """Owns what the connection closures of create_app shared: the gate, the worker count, the cleanup latch, the
    connection epochs and the task collections; the services it stops are set by create_app once they exist."""

    def __init__(self, *, registry, slots, states, epochs, connection_kinds, temp_root, preferences_store, rules_store,
                 content_provider, unsafe_cleanup, problem, max_concurrent, model_stop_seconds,
                 check_wait_seconds):
        self.registry, self.slots, self.states, self.epochs = registry, slots, states, epochs
        self.connection_kinds, self.temp_root = connection_kinds, temp_root
        self.preferences_store, self.rules_store, self.content_provider = preferences_store, rules_store, content_provider
        self.problem = problem
        # Module globals of app.py, read at each call: tests patch them there.
        self.max_concurrent, self.model_stop_seconds = max_concurrent, model_stop_seconds
        self.check_wait_seconds = check_wait_seconds
        self.operations: dict[asyncio.Task, OperationFiles] = {}
        self.cancellation_pending: set[asyncio.Task] = set()
        self.connection_work: dict[asyncio.Task, tuple[OperationFiles, threading.Event]] = {}
        self.active = 0
        self.unsafe_cleanup = unsafe_cleanup
        self.gate = asyncio.Lock()
        self.connection_epoch = 0
        self.connection_namespace = secrets.token_hex(12)
        self.login_tasks: dict[str, asyncio.Task] = {}
        self.install_tasks: dict[str, asyncio.Task] = {}
        self.login_codes: dict[str, list[str]] = {}
        self.login_code_lock = threading.Lock()
        self.release_lookups: dict[str, asyncio.Task] = {}
        self.enabled = set()
        self.intake = self.rewrite = self.projects = self.assistant = self.template_assistant = None

    def stored_preferences(self):
        try:
            return self.preferences_store.load() if self.preferences_store.path.exists() else None
        except PreferencesFailure:
            return None

    def kinds(self):
        return [item.kind for item in self.registry.listed() if item.kind in self.slots]

    def on(self, kind):
        return kind in self.enabled and kind in self.kinds()

    def busy(self, kind):
        return any(self.connection_kinds.get(task) == kind and not task.done() for task in self.connection_work)

    def catalog(self):
        """Each offered model with its provider, over every provider that is on and has its catalog. A name a provider
        listed first stays with that one; names do not overlap (Claude's catalog is a fixed list)."""
        owners = {}
        for kind in self.kinds():
            if self.on(kind) and self.states[kind].metadataReady:
                for model in self.states[kind].models:
                    owners.setdefault(model, kind)
        return owners

    def catalog_reasoning(self, owners=None):
        owners = self.catalog() if owners is None else owners
        return {model: self.states[kind].modelReasoning[model] for model, kind in owners.items()
                if model in self.states[kind].modelReasoning}

    def reasoning_of(self, model):
        return self.catalog_reasoning().get(model)

    def processing_model(self):
        value = self.stored_preferences()
        return value.selected_model if value is not None else None

    def connected(self, kind):
        state = self.states[kind]
        return (self.on(kind) and not self.unsafe_cleanup and not INFERENCE.blocked and state.state == "connected"
                and state.metadataReady and state.quota.state in USABLE_QUOTA)

    def usable(self, kind):
        # Structured generation also needs the provider's native profile; the assistant has its own runtime.
        return self.connected(kind) and self.slots[kind].profile is not None

    def experimental_ready(self, model=None) -> bool:
        kind = self.catalog().get(model or self.processing_model())
        return kind is not None and self.usable(kind)

    def lifecycle_code(self, error: SpikeError) -> str:
        if error.code in {"PROCESS_CLEANUP_FAILED", "CLEANUP_FAILED", "UNSAFE_TEMP_ROOT"}:
            self.unsafe_cleanup = True
        return error.code if error.code in {"PROCESS_CLEANUP_FAILED", "CLEANUP_FAILED", "UNSAFE_TEMP_ROOT", "TEMP_FAILED"} else "OPERATION_FAILED"

    @asynccontextmanager
    async def worker_slot(self, cancel):
        while True:
            async with self.gate:
                if self.unsafe_cleanup:
                    raise SpikeError("PROCESS_CLEANUP_FAILED")
                if cancel.is_set():
                    raise AdmissionCancelled()
                if self.active < self.max_concurrent() and not self.cancellation_pending:
                    self.active += 1
                    break
            await asyncio.sleep(0.025)
        try:
            yield
        finally:
            self.active -= 1

    @asynccontextmanager
    async def model_slot(self, cancel):
        # A rewrite waits in the inference admission, not for one of the local workers uploads and exports need (D121).
        async with self.gate:
            if self.unsafe_cleanup:
                raise SpikeError("PROCESS_CLEANUP_FAILED")
            if cancel.is_set():
                raise AdmissionCancelled()
        yield

    def provider_for(self, model):
        """The provider that runs a catalog model now, with the model; None while that provider cannot run it."""
        if self.content_provider is not None and not self.unsafe_cleanup:
            return self.content_provider, model
        kind = self.catalog().get(model)
        if kind is not None and self.experimental_ready(model) and self.slots[kind].provider is not None:
            return self.slots[kind].provider, model
        return None

    def selected_provider(self):
        model = self.processing_model()
        if self.content_provider is not None and not self.unsafe_cleanup:
            return self.content_provider, (model if model in self.catalog() else None) or "fixture"
        return self.provider_for(model) if model is not None else None

    def chosen_provider(self, model):
        """The provider for a model chosen in preferences; None follows the processing model."""
        if model is None:
            return self.selected_provider()
        if model not in self.catalog():
            raise ProjectFailure("MODEL_DENIED", 409)
        return self.provider_for(model)

    def preferred_provider(self, field):
        try:
            model = getattr(self.preferences_store.load(), field)
        except PreferencesFailure as error:
            raise ProjectFailure(error.code, 409) from None
        return self.chosen_provider(model)

    def import_selected_provider(self):
        return self.preferred_provider("selected_import_model")

    def unavailable_code(self, field):
        """Why the model chosen in `field` cannot run: a known exhausted plan is named, because "connect a model" sent
        the user to Settings for nothing (D104). So are a check still running and limits the provider never reported
        (D127): the model is connected in Settings, so a second try, not Settings, is the way out."""
        stored = self.stored_preferences()
        kind = self.catalog().get((getattr(stored, field) if stored else None) or self.processing_model())
        # Without a chosen model, the plan is named when every provider that is on has used it up.
        exhausted = ([kind] if kind else [item for item in self.kinds() if self.on(item) and self.states[item].metadataReady])
        if exhausted and all(self.states[item].quota.state == "exhausted" for item in exhausted):
            return "QUOTA_EXHAUSTED"
        # A provider that is on and not checked yet lists no models, so the chosen model names no provider either.
        checked = [kind] if kind else [item for item in self.kinds() if self.on(item)]
        if any(self.on(item) and (self.busy(item) or self.states[item].state == "unchecked") for item in checked):
            return "CONNECTION_CHECKING"
        if kind is not None and self.on(kind) and self.states[kind].state == "unknown_limits":
            return "LIMITS_UNKNOWN"
        return "CONNECTION_REQUIRED"

    def agent_connection(self):
        from ..assistant.runs import AgentConnection
        owners = self.catalog()
        ready_kinds = {kind for kind in self.kinds() if self.connected(kind)}
        listed = [kind for kind in self.kinds() if self.on(kind)]
        reason = ("AGENT_CLEANUP_FAILED" if self.unsafe_cleanup or INFERENCE.blocked else
            "AGENT_AUTH_REQUIRED" if any(self.states[kind].state in {"login_required", "login_pending", "detached"} for kind in listed) else
            "AGENT_QUOTA" if any(self.states[kind].quota.state == "exhausted" for kind in listed) else "AGENT_CONNECTION_UNAVAILABLE")
        ready = bool(ready_kinds)
        # A ready assistant offers the models of the providers that can run now; a model of another one is unavailable.
        models = tuple(model for model, kind in owners.items() if not ready or kind in ready_kinds)
        displays = {item.kind: item.display for item in self.registry.listed()}
        return AgentConnection(ready, models, "connection_" + self.connection_namespace + "_" + str(self.connection_epoch),
            None if ready else reason, self.catalog_reasoning(owners), {model: displays[kind] for model, kind in owners.items()})

    async def cancel_operation(self, task: asyncio.Task, files: OperationFiles) -> str | None:
        if not task.done():
            self.cancellation_pending.add(task)
        task.cancel()
        cleanup_code = None
        try:
            files.stop_worker()
        except SpikeError as error:
            cleanup_code = self.lifecycle_code(error)
        done, _ = await asyncio.wait((task,), timeout=CANCEL_GRACE_SECONDS)
        if task in done and not task.cancelled():
            try:
                await task
            except SpikeError as error:
                cleanup_code = self.lifecycle_code(error)
            except Exception:
                pass
        return cleanup_code

    async def stop_connection(self, task: asyncio.Task, files: OperationFiles, cancel: threading.Event) -> str | None:
        if not task.done():
            self.cancellation_pending.add(task)
        cancel.set()
        cleanup_code = None
        try:
            files.stop_worker()
        except SpikeError as error:
            cleanup_code = self.lifecycle_code(error)
        done, _ = await asyncio.wait((task,), timeout=CANCEL_GRACE_SECONDS)
        if task not in done:
            return self.lifecycle_code(SpikeError("PROCESS_CLEANUP_FAILED"))
        if task in done:
            try:
                await task
            except SpikeError as error:
                if error.code in {"PROCESS_CLEANUP_FAILED", "CLEANUP_FAILED", "UNSAFE_TEMP_ROOT"}:
                    cleanup_code = self.lifecycle_code(error)
            except ConnectionFailure as error:
                if error.code in {"PROCESS_CLEANUP_FAILED", "CLEANUP_FAILED"}:
                    cleanup_code = self.lifecycle_code(SpikeError(error.code))
            except Exception:
                pass
        return cleanup_code

    def operation_done(self, done: asyncio.Task) -> None:
        if not done.cancelled():
            error = done.exception()
            if isinstance(error, SpikeError):
                self.lifecycle_code(error)
            elif isinstance(error, ConnectionFailure) and error.code in {"PROCESS_CLEANUP_FAILED", "CLEANUP_FAILED"}:
                self.lifecycle_code(SpikeError(error.code))
        self.operations.pop(done, None)
        self.connection_work.pop(done, None)
        self.connection_kinds.pop(done, None)
        self.cancellation_pending.discard(done)
        self.active -= 1

    def provider_summaries(self) -> list[ProviderSummary]:
        summaries = []
        for item in self.registry.listed():
            if item.kind not in self.slots:
                continue
            slot, state = self.slots[item.kind], self.states[item.kind]
            executable = getattr(slot.connection, "executable", None)
            # The runtime FoldCV installed is pinned by hash, not by signature, so its file is enough here.
            installed = (state.state not in {"cli_missing", "launcher_unsupported"} if self.on(item.kind)
                         else executable is not None and executable.is_file() if getattr(slot.profile, "managed", False)
                         else discovered(item, executable))
            summaries.append(ProviderSummary(**state.model_dump(), kind=item.kind, display=item.display,
                                             subscription=item.subscription, publisher=item.publisher,
                                             loginCode=item.login_code, installed=installed, enabled=self.on(item.kind),
                                             installation=slot.installation.snapshot() if slot.installation else None))
        return summaries

    def connection_response(self, kind=None) -> JSONResponse:
        # The top level names one provider (the request's, else the first that is on) and combines the catalogs.
        kind = kind or next((item for item in self.kinds() if self.on(item)), "codex_cli")
        owners, model = self.catalog(), self.processing_model()
        state, slot = self.states[kind], self.slots[kind]
        payload = ConnectionPayload(provider=kind, providers=self.provider_summaries(), state=state.state, version=state.version,
                                    versionStatus=state.versionStatus, plan=state.plan, quota=state.quota,
                                    installation=slot.installation.snapshot() if slot.installation else None,
                                    models=list(owners), modelReasoning=self.catalog_reasoning(owners),
                                    selectedModel=model if model in owners else None, metadataReady=bool(owners),
                                    generationReady=self.experimental_ready(),
                                    experimentalMode=any(self.slots[item].profile is not None for item in self.kinds()))
        return JSONResponse(payload.model_dump(), headers={"Cache-Control": "no-store"})

    async def connection_job(self, job: str, kind: str, work):
        slot = self.slots[kind]
        installation = slot.installation
        async with self.gate:
            if self.unsafe_cleanup or INFERENCE.blocked:
                self.states[kind] = ProviderState(state="cleanup_blocked")
                return self.connection_response(kind)
            if job == "login" and self.states[kind].state != "login_required":
                return self.problem("LOGIN_NOT_AVAILABLE", 409, "host")
            # An install puts the newest release in place: for a missing or refused CLI, or as the update Settings
            # offers once a newer release is found (D146).
            if job == "install" and (installation is None or kind in self.login_tasks or (self.states[kind].state not in {
                    "cli_missing", "unsupported_version", "launcher_unsupported"} and not installation.snapshot()["update"])):
                return self.problem("INSTALL_NOT_AVAILABLE", 409, "host")
            # Beside the provider's own sign-in or install a check starts nothing: the reply is that job's state.
            if job not in {"login", "install"} and (kind in self.login_tasks or kind in self.install_tasks):
                return self.connection_response(kind)
            # One connection job per provider; jobs and model work take turns at the exclusive permit (D121).
            if self.cancellation_pending or self.active >= self.max_concurrent() or self.busy(kind):
                return self.problem("BUSY", 429, "host", True)
            self.active += 1
            epoch = self.epochs[kind]
            profile = slot.profile
            files = OperationFiles(self.temp_root)
            cancel = threading.Event()
            if job == "install":
                installation.cancel = cancel
                installation.update(state="downloading", downloadedBytes=0, error=None)

            wait = self.model_stop_seconds() if job in {"login", "install"} else self.check_wait_seconds()

            def admitted():
                return INFERENCE.hold(cancel, deadline=time.monotonic() + wait, exclusive=True)

            def run():
                # Under the permit: a check that gives up behind model work leaves the metadata of that work alone.
                if slot.provider is not None:
                    slot.provider.invalidate_preflight()
                return work(files, cancel)

            def execute():
                if job == "install":
                    with admitted(), files.open():
                        return run()
                if profile is not None and not profile.executable.is_file():
                    raise ConnectionFailure("CLI_MISSING")
                try:
                    with admitted(), native_profile(profile, cancel, deadline=time.monotonic() + 15, blocking=False,
                                                    operations_root=self.temp_root):
                        with files.open():
                            return run()
                except (ExperimentalProfileError, ClaudeProfileError) as error:
                    raise ConnectionFailure("UNSUPPORTED_VERSION" if str(error) == "CLI_UNSUPPORTED" else "METADATA_FAILED") from None

            task = asyncio.create_task(asyncio.to_thread(execute))
            self.operations[task] = files
            self.connection_work[task] = (files, cancel)
            self.connection_kinds[task] = kind
            task.add_done_callback(self.operation_done)
            if job in {"login", "install"}:
                self.connection_epoch += 1
                self.epochs[kind] += 1
                epoch = self.epochs[kind]
                # An import may use both providers, so a new sign-in or CLI on either stops all model work (D119). The
                # job's thread starts after this, and its exclusive permit then waits for that work to end.
                self.assistant.stop_all()
                self.template_assistant.stop_all()
                self.rewrite.request_shutdown()
                self.projects.imports.stop_all()
                if job == "install":
                    self.install_tasks[kind] = task
                else:
                    self.login_tasks[kind] = task
                    self.states[kind] = ProviderState(state="login_pending", version=self.states[kind].version)
        try:
            result = await asyncio.shield(task)
            async with self.gate:
                if job == "install":
                    current = self.slots[kind]
                    if isinstance(result, Path) and current.profile is not None and current.rebind is not None:
                        self.slots[kind] = current.rebind(current, result)
                        if epoch == self.epochs[kind]:
                            self.states[kind] = ProviderState(state="unchecked")
                    return self.connection_response(kind)
                if epoch != self.epochs[kind]:
                    return self.connection_response(kind)
                if job == "login":
                    self.states[kind] = ProviderState(state="login_required", version=self.states[kind].version)
                    return self.connection_response(kind)
                assert isinstance(result, Metadata)
                quota = QuotaPayload(state=result.quota.state, usedPercent=result.quota.used_percent,
                                     resetsAt=result.quota.resets_at)
                state = ("unchecked" if job == "discover" else "quota_exhausted" if quota.state == "exhausted"
                         else "unknown_limits" if quota.state == "unknown" else "connected")
                self.states[kind] = ProviderState(state=state, version=result.version, plan=result.plan,
                                             versionStatus=result.version_status, models=list(result.models), quota=quota,
                                             modelReasoning=result.reasoning, metadataReady=job != "discover")
                return self.connection_response(kind)
        except (AdmissionTimeout, AdmissionCancelled) as error:
            if job == "install":
                installation.update(state="cancelled" if cancel.is_set() else "failed",
                                    error="cancelled" if cancel.is_set() else "busy")
            elif job == "login":
                async with self.gate:
                    if epoch == self.epochs[kind]:
                        self.states[kind] = ProviderState(state="login_required", version=self.states[kind].version)
            elif isinstance(error, AdmissionTimeout):
                # The check did not run, so the old state must not read as its result.
                return self.problem("BUSY", 429, "host", True)
            return self.connection_response(kind)
        except AdmissionBlocked:
            if job == "install":
                installation.update(state="failed", error="install_failed")
            INFERENCE.block()
            self.states[kind] = ProviderState(state="cleanup_blocked")
            return self.connection_response(kind)
        except ConnectionFailure as error:
            if error.code in {"PROCESS_CLEANUP_FAILED", "CLEANUP_FAILED"}:
                self.lifecycle_code(SpikeError(error.code))
            async with self.gate:
                if self.unsafe_cleanup:
                    self.states[kind] = ProviderState(state="cleanup_blocked")
                    return self.connection_response(kind)
                if epoch != self.epochs[kind]:
                    return self.connection_response(kind)
                mapped = {"CLI_MISSING": "cli_missing", "CLI_LAUNCH_UNSUPPORTED": "launcher_unsupported",
                          "UNSUPPORTED_VERSION": "unsupported_version",
                          "LOGIN_REQUIRED": "login_required", "API_KEY_MODE": "api_key_mode",
                          "METADATA_FAILED": "metadata_failed"}
                state = mapped.get(error.code, "login_failed" if job == "login" else "metadata_failed")
                self.states[kind] = ProviderState(state=state, version=error.version)
                return self.connection_response(kind)
        except SpikeError as error:
            if job == "install":
                installation.update(state="failed", error="install_failed")
            self.lifecycle_code(error)
            async with self.gate:
                if self.unsafe_cleanup:
                    self.states[kind] = ProviderState(state="cleanup_blocked")
                elif epoch == self.epochs[kind]:
                    self.states[kind] = ProviderState(state="metadata_failed")
                return self.connection_response(kind)
        except asyncio.CancelledError:
            await self.stop_connection(task, files, cancel)
            if job == "install" and installation.snapshot()["state"] in {"downloading", "verifying", "extracting"}:
                installation.update(state="cancelled", error="cancelled")
            raise
        except Exception:
            if job == "install":
                installation.update(state="failed", error="install_failed")
            async with self.gate:
                if self.unsafe_cleanup:
                    self.states[kind] = ProviderState(state="cleanup_blocked")
                elif epoch == self.epochs[kind]:
                    self.states[kind] = ProviderState(state="metadata_failed")
                return self.connection_response(kind)
        finally:
            if self.login_tasks.get(kind) is task:
                del self.login_tasks[kind]
                with self.login_code_lock:
                    self.login_codes.pop(kind, None)
            if self.install_tasks.get(kind) is task:
                del self.install_tasks[kind]

    def target(self, payload: HostRequest):
        """The provider a host request is for (None is Codex), with the refusal when it is not listed or is off."""
        kind = payload.provider or "codex_cli"
        if kind not in self.kinds():
            return kind, self.problem("PROVIDER_UNAVAILABLE", 409, "host")
        return kind, None if self.on(kind) else self.problem("PROVIDER_INACTIVE", 409, "host")

    async def discover(self, payload: HostRequest):
        kind, refused = self.target(payload)
        if refused:
            return refused
        return await self.connection_job("discover", kind, lambda files, cancel, adapter=self.slots[kind].connection:
                                    adapter.inspect(files, cancel, full=False))

    async def status(self, payload: HostRequest):
        kind, refused = self.target(payload)
        if refused:
            return refused
        return await self.connection_job("status", kind, lambda files, cancel, adapter=self.slots[kind].connection:
                                    adapter.inspect(files, cancel))

    async def models(self, payload: HostRequest):
        return await self.status(payload)

    async def login(self, payload: HostRequest):
        kind, refused = self.target(payload)
        if refused:
            return refused
        with self.login_code_lock:
            self.login_codes[kind] = []
        adapter = self.slots[kind].connection
        if DESCRIPTORS[kind].login_code:
            def take_login_code() -> str | None:
                with self.login_code_lock:
                    codes = self.login_codes.get(kind)
                    return codes.pop() if codes else None
            return await self.connection_job("login", kind, lambda files, cancel: adapter.login(files, cancel, code=take_login_code))
        return await self.connection_job("login", kind, adapter.login)

    async def send_login_code(self, payload: LoginCodeRequest):
        kind, refused = self.target(payload)
        if refused:
            return refused
        async with self.gate:
            task = self.login_tasks.get(kind)
            if (task is None or task.done() or self.states[kind].state != "login_pending"
                    or not DESCRIPTORS[kind].login_code):
                return self.problem("LOGIN_NOT_AVAILABLE", 409, "host")
            with self.login_code_lock:
                self.login_codes[kind] = [payload.code]
            return self.connection_response(kind)

    async def install_cli(self, payload: HostRequest):
        kind, refused = self.target(payload)
        if refused:
            return refused
        installation = self.slots[kind].installation
        if installation is None:
            return self.problem("INSTALL_NOT_AVAILABLE", 409, "host")
        return await self.connection_job("install", kind, lambda files, _cancel: installation.install(files))

    async def release_check(self, payload: HostRequest):
        """Looks for a newer release of the managed CLI through the publisher's release listing; no CLI runs, no model
        work stops. One look serves every request while it runs."""
        kind, refused = self.target(payload)
        if refused:
            return refused
        installation = self.slots[kind].installation
        async with self.gate:
            if installation is None or not installation.snapshot()["available"] or kind in self.install_tasks:
                return self.connection_response(kind)
            task = self.release_lookups.get(kind)
            if task is None:
                files, cancel = OperationFiles(self.temp_root), threading.Event()

                def look():
                    with files.open():
                        installation.check(files, cancel)

                task = asyncio.create_task(asyncio.to_thread(look))
                self.release_lookups[kind] = task
                self.operations[task] = files
                self.connection_work[task] = (files, cancel)

                def finished(done: asyncio.Task, kind=kind) -> None:
                    if not done.cancelled() and isinstance(done.exception(), SpikeError):
                        self.lifecycle_code(done.exception())
                    self.operations.pop(done, None)
                    self.connection_work.pop(done, None)
                    if self.release_lookups.get(kind) is done:
                        del self.release_lookups[kind]
                task.add_done_callback(finished)
        try:
            await asyncio.shield(task)
        except asyncio.CancelledError:
            raise
        except Exception:
            pass
        async with self.gate:
            return self.connection_response(kind)

    async def cancel_install(self, payload: HostRequest):
        kind, refused = self.target(payload)
        if refused:
            return refused
        installation = self.slots[kind].installation
        async with self.gate:
            current = self.install_tasks.get(kind)
            if current is None or current not in self.connection_work:
                return self.connection_response(kind)
            if installation.snapshot()["state"] == "ready":
                return self.connection_response(kind)
            self.connection_epoch += 1
            self.epochs[kind] += 1
            files, cancel = self.connection_work[current]
        code = await self.stop_connection(current, files, cancel)
        if installation.snapshot()["state"] in {"downloading", "verifying", "extracting"}:
            installation.update(state="cancelled", error="cancelled")
        if code is not None or self.unsafe_cleanup:
            return self.problem("PROCESS_CLEANUP_FAILED", 503, "host")
        return self.connection_response(kind)

    async def select(self, payload: SelectModelRequest):
        # The processing model may be any provider's model; it runs on the provider that lists it.
        kind, refused = self.target(payload)
        if refused:
            return refused
        async with self.gate:
            if payload.model not in self.catalog():
                return self.problem("MODEL_DENIED", 409, "host")
            try:
                self.rules_store.load()
                self.preferences_store.select_model(payload.model)
            except (PreferencesFailure, RulesFailure) as error:
                return self.problem(error.code, 409, "settings")
            return self.connection_response(kind)

    async def stop_provider(self, kind, state):
        """A clean detach of one provider, never a CLI logout. Model work in flight stops whatever it runs on: an import
        may use both providers."""
        async with self.gate:
            if self.slots[kind].provider is not None:
                self.slots[kind].provider.invalidate_preflight()
            self.connection_epoch += 1
            self.epochs[kind] += 1
            self.states[kind] = ProviderState(state=state)
            current = [(task, files, cancel) for task, (files, cancel) in self.connection_work.items()
                       if self.connection_kinds.get(task) == kind]
            self.intake.request_shutdown()
            self.rewrite.request_shutdown()
            self.projects.imports.stop_all()
            self.assistant.stop_all()
            self.template_assistant.stop_all()
        codes = await asyncio.gather(*(self.stop_connection(task, files, cancel) for task, files, cancel in current))
        try:
            await self.intake.shutdown()
            await self.rewrite.shutdown()
            # No import keeps calling the model under the account that signed out.
            await self.projects.imports.shutdown()
        except ProjectFailure:
            self.lifecycle_code(SpikeError("PROCESS_CLEANUP_FAILED"))
        if any(code is not None for code in codes) or self.unsafe_cleanup:
            self.states[kind] = ProviderState(state="cleanup_blocked")
        return self.connection_response(kind)

    async def detach(self, payload: HostRequest):
        kind, refused = self.target(payload)
        if refused:
            return refused
        return await self.stop_provider(kind, "detached")

    async def cancel_login(self, payload: HostRequest):
        kind, refused = self.target(payload)
        if refused:
            return refused
        async with self.gate:
            current = self.login_tasks.get(kind)
            if current is None or current not in self.connection_work:
                return self.connection_response(kind)
            if self.slots[kind].provider is not None:
                self.slots[kind].provider.invalidate_preflight()
            self.connection_epoch += 1
            self.epochs[kind] += 1
            self.assistant.stop_all()
            self.template_assistant.stop_all()
            self.states[kind] = ProviderState(state="login_required", version=self.states[kind].version)
            files, cancel = self.connection_work[current]
        code = await self.stop_connection(current, files, cancel)
        if code is not None or self.unsafe_cleanup:
            self.states[kind] = ProviderState(state="cleanup_blocked")
        return self.connection_response(kind)

    async def enable(self, payload: EnableProviderRequest):
        kind = payload.provider
        if kind not in self.kinds():
            return self.problem("PROVIDER_UNAVAILABLE", 409, "host")
        if payload.enabled == self.on(kind):
            return self.connection_response(kind)
        if not payload.enabled:
            stopped = await self.stop_provider(kind, "unchecked")
            if self.states[kind].state == "cleanup_blocked":
                return stopped
        async with self.gate:
            try:
                self.rules_store.load()
                self.preferences_store.enable_provider(kind, payload.enabled)
            except (PreferencesFailure, RulesFailure) as error:
                return self.problem(error.code, 409, "settings")
            if payload.enabled:
                self.enabled.add(kind)
            else:
                self.enabled.discard(kind)
            self.epochs[kind] += 1
            self.states[kind] = ProviderState(state="unchecked")
            return self.connection_response(kind)
