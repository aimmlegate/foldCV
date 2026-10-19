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
    )
  | null;
export type State = "idle" | "downloading" | "verifying" | "extracting" | "ready" | "failed" | "cancelled";
export type Totalbytes = number;
export type Version = string;

export interface CliInstallationPayload {
  available: Available;
  downloadedBytes: Downloadedbytes;
  error: Error;
  state: State;
  totalBytes: Totalbytes;
  version: Version;
}
