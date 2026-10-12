"""Safe project failure codes shared by project operations."""


class ProjectFailure(Exception):
    def __init__(self, code, status=409):
        self.code, self.status = code, status
        super().__init__(code)
