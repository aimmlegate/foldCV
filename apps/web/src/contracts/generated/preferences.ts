export type Automaticanalysis = boolean;
export type Schemaversion = 1;
export type Selectedmodel = string | null;
export type Theme = "light" | "dark" | "system";

export interface Preferences {
  automaticAnalysis: Automaticanalysis;
  schemaVersion: Schemaversion;
  selectedModel: Selectedmodel;
  theme: Theme;
}
