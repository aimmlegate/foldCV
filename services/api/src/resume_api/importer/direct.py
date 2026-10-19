"""Direct Process uses the same importer and checkpoints as queued Process."""

import asyncio
import copy
import time

from packages.resume_core.agent_store import AgentFailure
from packages.resume_core import agent_limits
from packages.resume_core.background_history import digest_bytes
from packages.resume_core.import_agent import ImportFailure
from packages.resume_core.models.importing import IMPORT_TOOLS
from packages.resume_core.project_store import ProjectStoreFailure
from packages.resume_core.background_store import BackgroundFailure
from packages.resume_core.rules import RulesFailure
from ..agent.runtime import RuntimeInput
from ..gui_projects import ProjectFailure
from ..rendering import RenderFailure
from .result import import_workspace
from .session import ImportCoordinator, ImportSession, SKILL


async def run_import(projects, identifier, generation, rules, selected, *, allow_text_rewrite=True):
    cancel = projects.cancels[(identifier, generation.id)]
    session, operation = None, None
    generation.status = "running"
    def failed(code):
        generation.status = "cancelled" if cancel.is_set() else "failed"
        generation.error_code = code
        if operation is not None and identifier in projects.workspaces and identifier not in projects.deleted_ids:
            projects.finish_operation(identifier, operation.id, generation.status, code)
    try:
        agent = getattr(projects, "agent", None)
        runtime = copy.copy(getattr(projects, "import_runtime", None) or getattr(agent, "runtime", None))
        if runtime is None:
            raise ImportFailure("AGENT_RUNTIME_UNSUPPORTED")
        connection = agent.connection() if agent is not None else None
        def guard():
            if connection is not None:
                current = agent.connection()
                if not current.ready or current.epoch != connection.epoch:
                    raise ImportFailure("AGENT_CONNECTION_CHANGED")
        operation = projects.new_operation(identifier, "normalize_semantics")
        coordinator = ImportCoordinator(projects, identifier, generation.id, rules, cancel, guard=guard,
            allow_text_rewrite=allow_text_rewrite)
        coordinator.begin()
        session = ImportSession(coordinator)
        await session.start()
        loop = asyncio.get_running_loop()
        def close_tools(seconds):
            asyncio.run_coroutine_threadsafe(session.close(), loop).result(timeout=max(0.001, seconds))
        def ready():
            coordinator.guard()
            projects.finish_operation(identifier, operation.id, "running")
            if projects.persist(identifier) == "failed":
                raise ProjectFailure("PROJECT_SAVE_FAILED", 503)
        value = RuntimeInput(model=selected[1], prompt=session.prompt, url=session.url, token=session.token,
            tools=IMPORT_TOOLS, allow_web=False, active_seconds=agent_limits.IMPORT_ACTIVE_SECONDS,
            before_start=ready, revoke=session.revoke,
            close_tools=close_tools, developer_instructions=SKILL, queued_at=time.monotonic())
        result = await runtime.run(value, cancel, lambda _kind, _payload: None)
        if not result.cleanup_verified:
            raise AgentFailure("AGENT_CLEANUP_FAILED")
        if result.state != "completed" or result.error:
            raise ImportFailure(result.error or "IMPORT_NOT_FINISHED")
        draft = coordinator.load()
        if not draft.finished:
            raise ImportFailure("IMPORT_NOT_FINISHED")
        with projects.state_lock:
            current = coordinator.guard()
            for item in current.pre_draft.operations:
                if item.id == operation.id:
                    item.status = "completed"
            after = import_workspace(current, draft, rules)
            generation.stage = "assemble"
            projects.storage.save(after, projects.originals, projects.artifacts, projects.images)
            projects.adopt_committed(identifier, after, digest_bytes(after))
        generation.stage = "render"
        await projects.export(identifier, generation.id)
        generation.status = "completed"
    except (ImportFailure, AgentFailure, ProjectFailure, ProjectStoreFailure, BackgroundFailure, RulesFailure, RenderFailure) as error:
        failed(error.code)
        if error.code == "AGENT_CLEANUP_FAILED":
            projects.cleanup_error(error)
    except asyncio.CancelledError:
        cancel.set()
        failed("CANCELLED")
        raise
    except OSError:
        failed("PROJECT_SAVE_FAILED")
    except Exception:
        failed("IMPORT_INVALID_RESULT")
    finally:
        try:
            if session is not None:
                await session.close()
        finally:
            if identifier not in projects.deleted_ids:
                projects.persist(identifier)
