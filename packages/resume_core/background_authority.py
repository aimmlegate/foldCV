"""A durable writer record alone cannot revive a short-lived publication barrier."""

from dataclasses import dataclass
from .background_clock import Deadlines
from .background_limits import LIMITS
from .background_store import BackgroundFailure


@dataclass(frozen=True)
class WriterClaim:
    epoch: int | None
    incarnation: str | None
    generation: int | None


class PublicationAuthority:
    def __init__(self, *, clock=None):
        self.clock = clock or Deadlines()
        self.acks = {}

    def acknowledged(self, writer, barrier):
        previous = self.acks.get(writer.project_id)
        if previous is not None and previous[0] == barrier:
            return
        self.acks[writer.project_id] = (barrier.model_copy(deep=True), self.clock.now() + LIMITS.local_barrier_ms / 1000)

    def require(self, state, workspace):
        writer = state.writer
        if writer is None or writer.status not in {"attached", "clean_detached"} or writer.draft_id is not None:
            raise BackgroundFailure("WRITER_UNKNOWN")
        if writer.status == "clean_detached":
            return WriterClaim(None, None, None)
        barrier, known = state.barrier, self.acks.get(state.project_id)
        if (barrier is None or barrier.state != "acked" or known is None or known[0] != barrier
                or self.clock.now() >= known[1]
                or (barrier.writer_epoch, barrier.incarnation, barrier.generation, barrier.acknowledged_revision,
                    barrier.action_cursor, barrier.touch_generation) !=
                (writer.epoch, writer.incarnation, writer.barrier_generation, workspace.project_revision,
                    writer.acknowledged_cursor, writer.touch_generation)
                or writer.acknowledged_revision != workspace.project_revision):
            raise BackgroundFailure("WRITER_UNKNOWN")
        return WriterClaim(writer.epoch, writer.incarnation, barrier.generation)
