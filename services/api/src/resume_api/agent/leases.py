"""Memory-only editor capabilities, with persisted epochs and no active-tab transfer."""

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
import hmac
import secrets
import time

from packages.resume_core import agent_limits as limits
from packages.resume_core.agent_store import AgentFailure
from packages.resume_core.models.agent import AgentLease, AgentOwner


@dataclass
class OwnerLease:
    project_id: str
    session_id: str
    token: str
    epoch: int
    expires: float


class AgentLeases:
    def __init__(self, store, state_lock, *, clock=time.monotonic, active=lambda _id: False):
        self.store, self.state_lock, self.clock, self.active = store, state_lock, clock, active
        self.leases = {}

    def open(self, project_id, session_id):
        with self.state_lock:
            self.store.load(project_id)
            previous = self.leases.get(project_id)
            if previous is not None and previous.expires > self.clock():
                if self.active(project_id) or previous.session_id != session_id:
                    raise AgentFailure("AGENT_OWNER_MISMATCH")
                return self.public(previous)
            if self.active(project_id):
                raise AgentFailure("AGENT_BUSY")
            def allocate(state):
                state.owner_epoch += 1
                return state.owner_epoch
            epoch = self.store.update(project_id, allocate)
            lease = OwnerLease(project_id, session_id, secrets.token_urlsafe(32), epoch,
                self.clock() + limits.LEASE_SECONDS)
            self.leases[project_id] = lease
            return self.public(lease)

    def require(self, project_id, owner=None, *, epoch=None):
        lease = self.leases.get(project_id)
        if lease is None:
            raise AgentFailure("AGENT_NO_OWNER")
        if lease.expires <= self.clock():
            raise AgentFailure("AGENT_LEASE_EXPIRED")
        if owner is not None and (lease.epoch != owner.epoch or not hmac.compare_digest(lease.token, owner.token)):
            raise AgentFailure("AGENT_OWNER_MISMATCH")
        if epoch is not None and lease.epoch != epoch:
            raise AgentFailure("AGENT_OWNER_MISMATCH")
        return lease

    def renew(self, project_id, owner):
        with self.state_lock:
            lease = self.require(project_id, owner)
            lease.expires = self.clock() + limits.LEASE_SECONDS
            return self.public(lease)

    def close(self, project_id, owner):
        lease = self.leases.get(project_id)
        if lease is None:
            return None
        if lease.epoch != owner.epoch or not hmac.compare_digest(lease.token, owner.token):
            raise AgentFailure("AGENT_OWNER_MISMATCH")
        # Revoke the captured lease before waiting for a publishing thread's state lock.
        lease.expires = 0
        return lease

    def invalidate(self):
        with self.state_lock:
            for lease in self.leases.values():
                lease.expires = 0

    def public(self, lease):
        remaining = max(0, lease.expires - self.clock())
        expires = datetime.now(timezone.utc) + timedelta(seconds=remaining)
        return AgentLease(projectId=lease.project_id, sessionId=lease.session_id,
            owner=AgentOwner(token=lease.token, epoch=lease.epoch), expiresAt=expires.isoformat())
