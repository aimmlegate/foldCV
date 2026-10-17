"""Keep the account permit and shared server owned until an idle drain."""

import asyncio
from contextlib import asynccontextmanager, contextmanager

from packages.resume_core.background_store import BackgroundFailure
from ..inference_admission import AdmissionBlocked, AdmissionCancelled
from .appserver import SharedAgentRuntime, SharedContentProvider


@asynccontextmanager
async def cancelled_lock(lock, cancelled):
    acquired = asyncio.create_task(lock.acquire())
    stop = asyncio.create_task(cancelled.wait())
    try:
        await asyncio.wait([acquired, stop], return_when=asyncio.FIRST_COMPLETED)
        if cancelled.is_set():
            raise AdmissionCancelled()
        yield
    finally:
        if not acquired.done():
            acquired.cancel()
        stop.cancel()
        await asyncio.gather(acquired, stop, return_exceptions=True)
        if not acquired.cancelled() and acquired.result():
            lock.release()


class ParallelPermit:
    def __init__(self, owner, contexts=1):
        self.owner, self.active = owner, True
        self.contexts = contexts

    @contextmanager
    def hold(self, cancel, *, deadline=None):
        if not self.active or self not in self.owner.permits or self.owner.reservation is None:
            raise AdmissionBlocked()
        with self.owner.reservation.hold(cancel, deadline=deadline):
            yield

    def block(self):
        self.owner.admission.block()

    def release(self):
        if not self.active or self not in self.owner.permits:
            raise RuntimeError("Parallel permit is not held")
        self.active = False
        self.owner.permits.remove(self)
        self.owner.changed.set()


class ParallelOwner:
    def __init__(self, service, server_factory, *, native):
        self.service, self.server_factory, self.native = service, server_factory, native
        self.admission = service.admission
        self.server = self.reservation = None
        self.permits = set()
        self.lock = asyncio.Lock()
        self.changed = asyncio.Event()

    async def reserve(self, control):
        while True:
            async with cancelled_lock(self.lock, control.cancelled):
                if control.cancelled.is_set():
                    raise AdmissionCancelled()
                if self.admission.blocked:
                    raise AdmissionBlocked()
                if self.reservation is None:
                    self.reservation = await self.admission.reserve(control.cancelled)
                if self.server is None and self.server_factory is not None:
                    from .process_ownership import guard_server
                    self.server = guard_server(self.server_factory())
                    self.service.runtime = SharedAgentRuntime(self.server, native=self.native)
                    provider = SharedContentProvider(self.server, native=self.native)
                    self.service.content_provider = lambda: (provider, "gpt-6-luna")
                if self.server is not None and (self.server.fenced or self.server.cleanup_failed):
                    raise BackgroundFailure("CLEANUP_FAILED")
                contexts = len(control.job.submission.models) if self.server is not None else 1
                reserved = sum(permit.contexts for permit in self.permits)
                waiting = (self.server is not None and self.server.protocol.needs_rotation(contexts + reserved)
                    and bool(self.permits))
                if not waiting:
                    if self.server is not None and self.server.protocol.needs_rotation(contexts):
                        await self.server.prepare(planned=contexts)
                    permit = ParallelPermit(self, contexts)
                    self.permits.add(permit)
                    return permit
                self.changed.clear()
            wake = asyncio.create_task(self.changed.wait())
            stopped = asyncio.create_task(control.cancelled.wait())
            try:
                await asyncio.wait([wake, stopped], return_when=asyncio.FIRST_COMPLETED)
            finally:
                wake.cancel()
                stopped.cancel()
                await asyncio.gather(wake, stopped, return_exceptions=True)

    async def idle(self):
        async with self.lock:
            if self.permits or self.service.supervisor.active_controls:
                return
            if self.server is not None:
                try:
                    await self.server.close()
                except BaseException:
                    self.admission.block()
                    self.service.supervisor.fenced = "CLEANUP_FAILED"
                    raise
                if self.server.cleanup_failed or self.server.owner_context is not None or self.server.live:
                    self.admission.block()
                    self.service.supervisor.fenced = "CLEANUP_FAILED"
                    raise BackgroundFailure("CLEANUP_FAILED")
                self.server = None
            if self.reservation is not None:
                self.reservation.release()
                self.reservation = None

    def login_allowed(self):
        return not self.permits and self.reservation is None and self.server is None
