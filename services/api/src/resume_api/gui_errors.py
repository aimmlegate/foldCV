"""Safe project failure codes shared by project operations; the class lives with the /v2 project routes."""

from .projects.errors import ProjectFailure

__all__ = ['ProjectFailure']
