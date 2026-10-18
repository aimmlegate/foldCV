export type Automaticanalysis = boolean;
export type Schemaversion = 1;
export type Selectedimportmodel = string | null;
export type Selectedmodel = string | null;
export type Theme = "light" | "dark" | "system";

export interface Preferences {
  automaticAnalysis: Automaticanalysis;
  schemaVersion: Schemaversion;
  selectedImportModel?: Selectedimportmodel;
  selectedModel: Selectedmodel;
  theme: Theme;
}
