"""Public metadata for explicit CLI installation."""

from typing import Literal

from pydantic import Field, model_validator

from .contracts import Wire

RELEASE = r"^[0-9a-zA-Z.-]{1,60}$"


class CliInstallationPayload(Wire):
    state: Literal["idle", "downloading", "verifying", "extracting", "ready", "failed", "cancelled"]
    downloadedBytes: int = Field(ge=0)
    # 0 until the install has found the release it downloads.
    totalBytes: int = Field(ge=0)
    error: Literal["unsafe_directory", "busy", "cancelled", "unsupported_platform", "download_failed",
                   "invalid_package", "checksum_failed", "install_failed", "incompatible_release"] | None
    available: bool
    # The managed release in place, the newest one found, and whether Settings offers it as an update (D146).
    installed: str | None = Field(pattern=RELEASE)
    latest: str | None = Field(pattern=RELEASE)
    update: bool

    @model_validator(mode="after")
    def bounded_download(self):
        if self.totalBytes and self.downloadedBytes > self.totalBytes:
            raise ValueError("download exceeds package size")
        if self.update and (self.installed is None or self.latest is None):
            raise ValueError("an update needs both releases")
        return self
