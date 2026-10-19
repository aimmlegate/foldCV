"""Public metadata for explicit CLI installation."""

from typing import Literal

from pydantic import Field, model_validator

from .contracts import Wire


class CliInstallationPayload(Wire):
    state: Literal["idle", "downloading", "verifying", "extracting", "ready", "failed", "cancelled"]
    downloadedBytes: int = Field(ge=0)
    totalBytes: int = Field(gt=0)
    version: str = Field(pattern=r"^[0-9a-zA-Z.-]{1,60}$")
    error: Literal["unsafe_directory", "busy", "cancelled", "unsupported_platform", "download_failed",
                   "invalid_package", "checksum_failed", "install_failed"] | None
    available: bool

    @model_validator(mode="after")
    def bounded_download(self):
        if self.downloadedBytes > self.totalBytes:
            raise ValueError("download exceeds package size")
        return self
