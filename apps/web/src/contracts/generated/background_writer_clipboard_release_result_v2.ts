export type Clipboardcaptureid = string;
export type Released = true;
export type Schemaversion = 2;

export interface WriterClipboardReleaseResultV2 {
  clipboardCaptureId: Clipboardcaptureid;
  released: Released;
  schemaVersion: Schemaversion;
}
