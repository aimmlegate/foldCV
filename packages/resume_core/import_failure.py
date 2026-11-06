"""The coded failure of a template import step; templates and edits raise it too."""

from __future__ import annotations


class TemplateImportFailure(Exception):
    def __init__(self, code):
        self.code = code
        super().__init__(code)
