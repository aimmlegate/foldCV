export type Available = boolean;
export type Downloadedbytes = number;
export type Error =
  | (
      | "unsafe_directory"
      | "busy"
      | "cancelled"
      | "unsupported_platform"
      | "download_failed"
      | "invalid_package"
      | "checksum_failed"
      | "install_failed"
      | "incompatible_release"
    )
  | null;
export type Installed = string | null;
export type Latest = string | null;
export type State = "idle" | "downloading" | "verifying" | "extracting" | "ready" | "failed" | "cancelled";
export type Totalbytes = number;
export type Update = boolean;

export interface CliInstallationPayload {
  available: Available;
  downloadedBytes: Downloadedbytes;
  error: Error;
  installed: Installed;
  latest: Latest;
  state: State;
  totalBytes: Totalbytes;
  update: Update;
}
