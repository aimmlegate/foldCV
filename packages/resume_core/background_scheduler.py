"""Eligible project/class order; runtime ownership belongs to the supervisor."""

from collections import defaultdict

from .background_limits import LIMITS

CLASSES = ("interactive", "background", "reconciliation")


class SerialOrder:
    def __init__(self):
        self.last_project = None
        self.last_class = {}
        self.interactive_streak = defaultdict(int)

    def choose(self, states, eligible=lambda _job: True, *, reserved=()):
        queues = {}
        for project, state in states.items():
            groups = {name: [] for name in CLASSES}
            for job in state.jobs:
                if job.execution == "queued" and job.id not in reserved:
                    groups[job.submission.scheduling_class].append(job)
            groups = {name: items if items and eligible(items[0]) else [] for name, items in groups.items()}
            if any(groups.values()):
                queues[project] = groups
        projects = sorted(queues)
        if not projects:
            return None
        if self.last_project is None:
            ordered = projects
        else:
            ordered = [p for p in projects if p > self.last_project] + [p for p in projects if p <= self.last_project]
        project = ordered[0]
        groups = queues[project]
        previous = self.last_class.get(project)
        start = (CLASSES.index(previous) + 1) % len(CLASSES) if previous is not None else 0
        classes = CLASSES[start:] + CLASSES[:start]
        if groups["reconciliation"] and self.interactive_streak[project] >= LIMITS.reconciliation_dispatch_bound:
            chosen = "reconciliation"
        else:
            chosen = next(name for name in classes if groups[name])
        return groups[chosen][0]

    def dispatched(self, job):
        project = job.submission.identity.project_id
        kind = job.submission.scheduling_class
        self.last_project, self.last_class[project] = project, kind
        if kind == "interactive":
            self.interactive_streak[project] += 1
        elif kind == "reconciliation":
            self.interactive_streak[project] = 0
