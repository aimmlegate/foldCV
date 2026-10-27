export type Filename = string;
export type Format = "docx" | "foldcv";
export type Id = string;
export type Size = number;
export type Url = string;

export interface AssistantFileV1 {
  filename: Filename;
  format: Format;
  id: Id;
  size: Size;
  url: Url;
}
