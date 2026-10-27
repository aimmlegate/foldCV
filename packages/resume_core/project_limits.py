"""Import time and project size from Settings (D096) under fixed ceilings.

Writes use the settings; stored records are read and validated under the ceilings, so a
lowered setting blocks growth but never makes a saved project unreadable.
"""

from dataclasses import dataclass

MIB = 1024 * 1024
# (default, minimum, maximum)
IMPORT_MINUTES = (60, 5, 240)
PROJECT_MEGABYTES = (64, 10, 256)
IMPORT_CEILING_SECONDS = IMPORT_MINUTES[2] * 60
PROJECT_CEILING_BYTES = PROJECT_MEGABYTES[2] * MIB
# An archive keeps its earlier allowance for sources, images and the package next to the project file.
ARCHIVE_EXPANDED_BYTES = PROJECT_CEILING_BYTES + 44 * MIB
ARCHIVE_BYTES = ARCHIVE_EXPANDED_BYTES + 4 * MIB
# Background storage holds a full copy of the project file during each save, plus history.
BACKGROUND_FACTOR = 2
GLOBAL_PROJECTS = 8
# A durable save rewrites and re-validates the whole project file: 2 s per MB of the size setting,
# on top of the export receipt (15 s) and the publication base (30 s).
SAVE_SECONDS_PER_MEGABYTE = 2
FINALIZATION_BASE_SECONDS = 30
FINALIZATION_CEILING_SECONDS = FINALIZATION_BASE_SECONDS + SAVE_SECONDS_PER_MEGABYTE * PROJECT_MEGABYTES[2]
# One encoded undo inverse, and the DOCX render worker threads.
INVERSE_BYTES = 512 * 1024
RENDER_WORKERS = 2


@dataclass
class UserLimits:
    import_minutes: int = IMPORT_MINUTES[0]
    project_megabytes: int = PROJECT_MEGABYTES[0]


# The service applies saved Settings here at startup and after each save.
USER_LIMITS = UserLimits()


def apply_preferences(preferences):
    """Apply saved Settings; None restores the defaults."""
    USER_LIMITS.import_minutes = IMPORT_MINUTES[0] if preferences is None else preferences.import_minutes
    USER_LIMITS.project_megabytes = PROJECT_MEGABYTES[0] if preferences is None else preferences.project_megabytes


def import_seconds(ceiling_seconds=IMPORT_CEILING_SECONDS):
    """The Settings import time, bounded by a ceiling the caller may lower."""
    return min(ceiling_seconds, USER_LIMITS.import_minutes * 60)


def project_file_bytes():
    return USER_LIMITS.project_megabytes * MIB


def save_allowance_seconds():
    return SAVE_SECONDS_PER_MEGABYTE * USER_LIMITS.project_megabytes


def finalization_seconds():
    return FINALIZATION_BASE_SECONDS + save_allowance_seconds()
