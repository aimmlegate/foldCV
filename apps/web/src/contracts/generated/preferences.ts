export type Automaticanalysis = boolean;
export type Importminutes = number;
export type Projectmegabytes = number;
export type Rewritereasoningeffort =
  ("none" | "minimal" | "low" | "medium" | "high" | "xhigh" | "max" | "ultra") | null;
export type Selectedagentmodel = string | null;
export type Selectedfallbackmodel = string | null;
export type Selectedimportmodel = string | null;
export type Selectedmodel = string | null;
export type Rewritereasoningeffort1 =
  ("none" | "minimal" | "low" | "medium" | "high" | "xhigh" | "max" | "ultra") | null;
export type Schemaversion = 1;
export type Selectedfallbackmodel1 = string | null;
export type Selectedimportmodel1 = string | null;
export type Selectedmodel1 = string | null;
export type Selectedprovider = "codex_cli" | "claude_cli";
export type Theme = "light" | "dark" | "system";

export interface Preferences {
  automaticAnalysis: Automaticanalysis;
  importMinutes?: Importminutes;
  projectMegabytes?: Projectmegabytes;
  providerSelections?: Providerselections;
  rewriteReasoningEffort?: Rewritereasoningeffort1;
  schemaVersion: Schemaversion;
  selectedFallbackModel?: Selectedfallbackmodel1;
  selectedImportModel?: Selectedimportmodel1;
  selectedModel: Selectedmodel1;
  selectedProvider?: Selectedprovider;
  theme: Theme;
}
export interface Providerselections {
  [k: string]: ProviderSelection;
}
/**
 * Choices kept for a provider while another one is active; restored when it is selected again.
 */
export interface ProviderSelection {
  rewriteReasoningEffort?: Rewritereasoningeffort;
  selectedAgentModel?: Selectedagentmodel;
  selectedFallbackModel?: Selectedfallbackmodel;
  selectedImportModel?: Selectedimportmodel;
  selectedModel?: Selectedmodel;
}
