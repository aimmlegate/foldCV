"""One advisory classification call with explicit technical failures."""

from pydantic import ValidationError

from packages.resume_core.resume_assessment import ResumeAssessment, assessment_input
from .gui_content import generate_admitted
from .providers.content import ContentFailure, ContentInput, GenerationPolicy, MAX_GENERATION_SECONDS


class ResumeAssessmentContentService:
    def __init__(self, provider, model):
        self.provider = provider
        self.policy = GenerationPolicy(model=model, timeout_seconds=MAX_GENERATION_SECONDS, allow_repair=False)

    def run(self, request, _rules, files, cancel):
        try:
            response = generate_admitted(self.provider, ContentInput(assessment_input(request.sources),
                ResumeAssessment, self.policy), files, cancel)
            value = response.value
        except ContentFailure as error:
            if error.code != "INVALID_RESULT" or cancel.is_set():
                raise
            value = {"verdict": "uncertain"}
        if cancel.is_set():
            raise ContentFailure("CANCELLED")
        try:
            result = ResumeAssessment.model_validate(value)
        except (ValidationError, ValueError):
            result = ResumeAssessment(verdict="uncertain")
        return result, {}
