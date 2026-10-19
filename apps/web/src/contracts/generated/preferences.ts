export type Automaticanalysis = boolean;
export type Rewritereasoningeffort =
  ("none" | "minimal" | "low" | "medium" | "high" | "xhigh" | "max" | "ultra") | null;
export type Schemaversion = 1;
export type Selectedimportmodel = string | null;
export type Selectedmodel = string | null;
export type Theme = "light" | "dark" | "system";

export interface Preferences {
  automaticAnalysis: Automaticanalysis;
  rewriteReasoningEffort?: Rewritereasoningeffort;
  schemaVersion: Schemaversion;
  selectedImportModel?: Selectedimportmodel;
  selectedModel: Selectedmodel;
  theme: Theme;
}
