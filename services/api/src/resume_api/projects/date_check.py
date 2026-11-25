"""The date dialog's warnings before Save (D182). It reads the committed project and writes nothing."""

from packages.resume_core.editing.template_panel_jobs import check_dates
from packages.resume_core.models.projects import DateCheckResultV1

from .errors import ProjectFailure


def warnings(service, project_id, request):
    project = service.repository.read(project_id).project
    if project is None or project.template_package is None:
        raise ProjectFailure('DATE_CHECK_UNAVAILABLE', 409)
    try:
        value = check_dates(project, request.record_id, request.values)
    except ValueError:
        raise ProjectFailure('DATE_CHECK_UNAVAILABLE', 422) from None
    return DateCheckResultV1.model_validate(value)
